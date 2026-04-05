import { useRef, useState } from "react";
import type { Question, SwipeDirection } from "../types";

interface Props {
  question: Question;
  onSwipe: (direction: SwipeDirection) => void;
}

// 閾値: この px 以上ドラッグされたらスワイプ確定
const THRESHOLD = 80;

export function SwipeCard({ question, onSwipe }: Props) {
  const [drag, setDrag] = useState({ x: 0, y: 0 });
  const startRef = useRef<{ x: number; y: number } | null>(null);

  function onPointerDown(e: React.PointerEvent) {
    startRef.current = { x: e.clientX, y: e.clientY };
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  }

  function onPointerMove(e: React.PointerEvent) {
    if (!startRef.current) return;
    setDrag({
      x: e.clientX - startRef.current.x,
      y: e.clientY - startRef.current.y,
    });
  }

  function onPointerUp() {
    if (!startRef.current) return;
    startRef.current = null;
    const { x, y } = drag;
    // 上方向優先 (スキップ)
    if (y < -THRESHOLD && Math.abs(y) > Math.abs(x)) {
      setDrag({ x: 0, y: 0 });
      onSwipe("skip");
      return;
    }
    if (x > THRESHOLD) {
      setDrag({ x: 0, y: 0 });
      onSwipe("right");
      return;
    }
    if (x < -THRESHOLD) {
      setDrag({ x: 0, y: 0 });
      onSwipe("left");
      return;
    }
    // 閾値未達 → 元に戻る
    setDrag({ x: 0, y: 0 });
  }

  const rotate = drag.x / 20;
  const opacity = 1 - Math.min(Math.abs(drag.x) / 300, 0.3);

  // ラベル表示 (スワイプ方向ヒント)
  const leaningRight = drag.x > 30;
  const leaningLeft = drag.x < -30;
  const leaningUp = drag.y < -30 && Math.abs(drag.y) > Math.abs(drag.x);

  return (
    <div
      className="absolute inset-0 flex flex-col items-center justify-center p-8 select-none cursor-grab active:cursor-grabbing rounded-2xl bg-gradient-to-br from-neutral-800 to-neutral-900 shadow-2xl touch-none"
      style={{
        transform: `translate(${drag.x}px, ${drag.y}px) rotate(${rotate}deg)`,
        opacity,
      }}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
    >
      <p className="text-neutral-100 text-xl leading-relaxed text-center max-w-md">
        {question.text}
      </p>
      <div className="mt-8 flex gap-8 text-xs text-neutral-500">
        <span className={leaningLeft ? "text-red-400 font-bold" : ""}>← NO</span>
        <span className={leaningUp ? "text-yellow-400 font-bold" : ""}>↑ SKIP</span>
        <span className={leaningRight ? "text-green-400 font-bold" : ""}>YES →</span>
      </div>
    </div>
  );
}
