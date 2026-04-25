// swipe-persona API Worker
//
// ルート:
//   GET  /api/questions?limit=N  — 未回答問題を最大N件返す (問題プールは埋め込み)
//   POST /api/answers            — 回答を保存 (auth 必須)
//   GET  /api/persona            — 全回答を返す (ベイズ推定は将来ローカルCLIで実行)
//
// 認証:
//   Authorization: Bearer <sha256-hash>
//   ハッシュが env.AUTH_TOKEN_HASH と一致すれば通過。
//   (フロントの localStorage に入っているハッシュをそのまま渡す想定)

// data/questions/questions.json を直接参照 (複製を避けて単一情報源を維持)
import * as Sentry from "@sentry/cloudflare";
import questionPool from "../../data/questions/questions.json";
import { queryD1 } from "./lib/d1-wrapper";

interface Env {
	DB: D1Database;
	AUTH_TOKEN_HASH: string;
	CORS_ORIGIN: string;
	// L15: Sentry エラートラッキング（DSN は wrangler secret、release は CI で git SHA）
	SENTRY_DSN?: string;
	SENTRY_RELEASE?: string;
}

interface Question {
	question_id: string;
	text: string;
	loadings: Record<string, number>;
	difficulty?: number;
	discrimination?: number;
}

interface AnswerInput {
	question_id: string;
	response: -1 | 0 | 1;
}

function corsHeaders(env: Env): Record<string, string> {
	return {
		"Access-Control-Allow-Origin": env.CORS_ORIGIN,
		"Access-Control-Allow-Methods": "GET, POST, OPTIONS",
		"Access-Control-Allow-Headers": "Content-Type, Authorization",
		"Access-Control-Max-Age": "86400",
	};
}

function json(data: unknown, status: number, env: Env): Response {
	return new Response(JSON.stringify(data), {
		status,
		headers: {
			"Content-Type": "application/json",
			...corsHeaders(env),
		},
	});
}

function verifyAuth(request: Request, env: Env): boolean {
	const header = request.headers.get("Authorization");
	if (!header?.startsWith("Bearer ")) return false;
	const token = header.slice(7).trim();
	// timingSafeEqual 相当 (Worker runtime)
	if (token.length !== env.AUTH_TOKEN_HASH.length) return false;
	let mismatch = 0;
	for (let i = 0; i < token.length; i++) {
		mismatch |= token.charCodeAt(i) ^ env.AUTH_TOKEN_HASH.charCodeAt(i);
	}
	return mismatch === 0;
}

async function getUnansweredQuestions(
	env: Env,
	limit: number,
): Promise<Question[]> {
	// D1 から回答済み question_id を取得
	const { results } = await queryD1("answers.question_ids", () =>
		env.DB.prepare("SELECT question_id FROM answers").all<{
			question_id: string;
		}>(),
	);
	const answered = new Set(results.map((r) => r.question_id));
	const unanswered = (questionPool as unknown as Question[]).filter(
		(q) => !answered.has(q.question_id),
	);
	// シャッフル (Fisher-Yates)
	for (let i = unanswered.length - 1; i > 0; i--) {
		const j = Math.floor(Math.random() * (i + 1));
		[unanswered[i], unanswered[j]] = [unanswered[j], unanswered[i]];
	}
	return unanswered.slice(0, limit);
}

async function saveAnswers(env: Env, answers: AnswerInput[]): Promise<number> {
	if (answers.length === 0) return 0;
	const stmt = env.DB.prepare(
		`INSERT INTO answers (question_id, response, updated_at)
     VALUES (?, ?, datetime('now'))
     ON CONFLICT(question_id) DO UPDATE SET
       response = excluded.response,
       updated_at = datetime('now')`,
	);
	const batch = answers.map((a) => stmt.bind(a.question_id, a.response));
	await queryD1("answers.upsert_batch", () => env.DB.batch(batch));
	return answers.length;
}

async function getAllAnswers(env: Env): Promise<AnswerInput[]> {
	const { results } = await queryD1("answers.all", () =>
		env.DB.prepare(
			"SELECT question_id, response FROM answers ORDER BY updated_at DESC",
		).all<AnswerInput>(),
	);
	return results;
}

function validateAnswersPayload(payload: unknown): AnswerInput[] | null {
	if (!payload || typeof payload !== "object") return null;
	const obj = payload as { answers?: unknown };
	if (!Array.isArray(obj.answers)) return null;
	const result: AnswerInput[] = [];
	for (const a of obj.answers) {
		if (!a || typeof a !== "object") return null;
		const ans = a as { question_id?: unknown; response?: unknown };
		if (typeof ans.question_id !== "string") return null;
		if (ans.response !== -1 && ans.response !== 0 && ans.response !== 1)
			return null;
		result.push({
			question_id: ans.question_id,
			response: ans.response as -1 | 0 | 1,
		});
	}
	return result;
}

// L15: Sentry でラップ。SENTRY_DSN 未設定なら no-op。
const handler = {
	async fetch(request: Request, env: Env): Promise<Response> {
		const url = new URL(request.url);

		// CORS preflight
		if (request.method === "OPTIONS") {
			return new Response(null, { status: 204, headers: corsHeaders(env) });
		}

		try {
			// GET /api/questions?limit=N
			if (request.method === "GET" && url.pathname === "/api/questions") {
				if (!verifyAuth(request, env)) {
					return json({ error: "unauthorized" }, 401, env);
				}
				const limit = Math.min(
					parseInt(url.searchParams.get("limit") ?? "20", 10) || 20,
					100,
				);
				const questions = await getUnansweredQuestions(env, limit);
				return json({ questions }, 200, env);
			}

			// POST /api/answers
			if (request.method === "POST" && url.pathname === "/api/answers") {
				if (!verifyAuth(request, env)) {
					return json({ error: "unauthorized" }, 401, env);
				}
				const payload = await request.json();
				const answers = validateAnswersPayload(payload);
				if (answers === null) {
					return json({ error: "invalid payload" }, 400, env);
				}
				const saved = await saveAnswers(env, answers);
				return json({ saved }, 200, env);
			}

			// GET /api/persona — ベイズ推定用に全回答を返す (将来ローカルCLIで読む)
			if (request.method === "GET" && url.pathname === "/api/persona") {
				if (!verifyAuth(request, env)) {
					return json({ error: "unauthorized" }, 401, env);
				}
				const answers = await getAllAnswers(env);
				return json({ answers }, 200, env);
			}

			// ヘルスチェック (認証不要)
			if (request.method === "GET" && url.pathname === "/health") {
				return json(
					{
						status: "ok",
						questionPoolSize: (questionPool as unknown as Question[]).length,
					},
					200,
					env,
				);
			}

			return json({ error: "not found" }, 404, env);
		} catch (e) {
			console.error("worker error:", e);
			Sentry.captureException(e);
			return json({ error: "internal error" }, 500, env);
		}
	},
};

export default Sentry.withSentry(
	(env: Env) => ({
		dsn: env.SENTRY_DSN ?? "",
		release: env.SENTRY_RELEASE ?? undefined,
		tracesSampleRate: 0.1,
		enabled: Boolean(env.SENTRY_DSN),
	}),
	handler,
);
