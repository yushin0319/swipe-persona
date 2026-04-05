// swipe-persona フロント型定義

export interface Question {
  question_id: string;
  text: string;
  loadings: Record<string, number>;
  difficulty?: number;
  discrimination?: number;
}

export interface Answer {
  question_id: string;
  response: -1 | 0 | 1; // LEFT / SKIP / RIGHT
}

export type SwipeDirection = "left" | "right" | "skip";

export function directionToResponse(d: SwipeDirection): Answer["response"] {
  if (d === "right") return 1;
  if (d === "left") return -1;
  return 0;
}
