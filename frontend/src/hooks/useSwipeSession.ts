import { useCallback, useEffect, useState } from "react";
import type { Answer, Question, SwipeDirection } from "../types";
import { directionToResponse } from "../types";
import { getAuthToken } from "../auth";

type Phase = "loading" | "swiping" | "finished";

interface SessionState {
  phase: Phase;
  questions: Question[];
  index: number;
  answers: Answer[];
  error: string | null;
}

// Worker API エンドポイント (build時に env から注入、未設定時はローカル sample へフォールバック)
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

function authHeaders(): Record<string, string> {
  const token = getAuthToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function fetchQuestions(limit = 20): Promise<Question[]> {
  if (API_BASE) {
    const res = await fetch(`${API_BASE}/api/questions?limit=${limit}`, {
      headers: authHeaders(),
    });
    if (!res.ok) throw new Error(`fetch failed: ${res.status}`);
    const data = (await res.json()) as { questions: Question[] };
    return data.questions;
  }
  // ローカル開発: sample JSON
  const res = await fetch(`${import.meta.env.BASE_URL}questions-sample.json`);
  if (!res.ok) throw new Error("no sample questions available");
  return res.json();
}

async function postAnswers(answers: Answer[]): Promise<void> {
  if (!API_BASE) {
    console.log("[dev] answers (would POST):", answers);
    return;
  }
  const res = await fetch(`${API_BASE}/api/answers`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ answers }),
  });
  if (!res.ok) throw new Error(`post failed: ${res.status}`);
}

export function useSwipeSession() {
  const [state, setState] = useState<SessionState>({
    phase: "loading",
    questions: [],
    index: 0,
    answers: [],
    error: null,
  });

  useEffect(() => {
    fetchQuestions()
      .then((qs) => {
        setState({
          phase: qs.length > 0 ? "swiping" : "finished",
          questions: qs,
          index: 0,
          answers: [],
          error: null,
        });
      })
      .catch((e: Error) => {
        setState((s) => ({ ...s, phase: "finished", error: e.message }));
      });
  }, []);

  const handleSwipe = useCallback((direction: SwipeDirection) => {
    setState((s) => {
      const current = s.questions[s.index];
      if (!current) return s;
      const newAnswer: Answer = {
        question_id: current.question_id,
        response: directionToResponse(direction),
      };
      const newAnswers = [...s.answers, newAnswer];
      const nextIndex = s.index + 1;
      if (nextIndex >= s.questions.length) {
        // 終了 → POST
        postAnswers(newAnswers).catch((e) => console.error(e));
        return { ...s, index: nextIndex, answers: newAnswers, phase: "finished" };
      }
      return { ...s, index: nextIndex, answers: newAnswers };
    });
  }, []);

  return {
    ...state,
    currentQuestion: state.questions[state.index] ?? null,
    handleSwipe,
  };
}
