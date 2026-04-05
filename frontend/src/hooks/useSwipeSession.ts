import { useCallback, useEffect, useState } from "react";
import type { Answer, Question, SwipeDirection } from "../types";
import { directionToResponse } from "../types";

type Phase = "loading" | "swiping" | "finished";

interface SessionState {
  phase: Phase;
  questions: Question[];
  index: number;
  answers: Answer[];
  error: string | null;
}

// 開発用: ローカル JSON を fetch するダミーソース
// 本番では n8n webhook に差し替え (VITE_API_BASE_URL)
async function fetchQuestions(): Promise<Question[]> {
  const baseUrl = import.meta.env.VITE_API_BASE_URL;
  if (baseUrl) {
    const res = await fetch(`${baseUrl}/swipe-persona/questions`);
    if (!res.ok) throw new Error(`fetch failed: ${res.status}`);
    return res.json();
  }
  // ローカル開発: public/questions-sample.json から読む
  const res = await fetch(`${import.meta.env.BASE_URL}questions-sample.json`);
  if (!res.ok) throw new Error("no sample questions available");
  return res.json();
}

async function postAnswers(answers: Answer[]): Promise<void> {
  const baseUrl = import.meta.env.VITE_API_BASE_URL;
  if (!baseUrl) {
    console.log("[dev] answers (would POST):", answers);
    return;
  }
  await fetch(`${baseUrl}/swipe-persona/answers`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ answers }),
  });
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

  const handleSwipe = useCallback(
    (direction: SwipeDirection) => {
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
    },
    [],
  );

  return {
    ...state,
    currentQuestion: state.questions[state.index] ?? null,
    handleSwipe,
  };
}
