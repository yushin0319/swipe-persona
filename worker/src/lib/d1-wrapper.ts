/**
 * D1 クエリラッパー (M10).
 *
 * すべての D1 呼び出しを queryD1(label, fn) 経由にして:
 * 1. duration_ms を計測
 * 2. 例外を必ず明示的に throw
 * 3. console.log で構造化 JSON を吐く（observability=true で Dashboard 検索可）
 *
 * Workers Logs Dashboard で `type=d1_query` で絞り込み観測。
 */

export type D1QueryFn<T> = () => Promise<T>;

export async function queryD1<T>(label: string, fn: D1QueryFn<T>): Promise<T> {
	const start = performance.now();
	try {
		const result = await fn();
		const duration_ms = Math.round(performance.now() - start);
		let row_count: number | null = null;
		if (Array.isArray(result)) {
			row_count = result.length;
		} else if (result == null) {
			row_count = 0;
		} else if (typeof result === "object") {
			const maybeResults = (result as Record<string, unknown>).results;
			if (Array.isArray(maybeResults)) {
				row_count = maybeResults.length;
			}
		}
		console.log(
			JSON.stringify({
				type: "d1_query",
				label,
				duration_ms,
				status: "ok",
				row_count,
			}),
		);
		return result;
	} catch (err) {
		const duration_ms = Math.round(performance.now() - start);
		const message = err instanceof Error ? err.message : String(err);
		console.error(
			JSON.stringify({
				type: "d1_query",
				label,
				duration_ms,
				status: "error",
				error: message,
			}),
		);
		throw err;
	}
}
