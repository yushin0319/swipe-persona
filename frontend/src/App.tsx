import { SwipeCard } from "./components/SwipeCard";
import { useSwipeSession } from "./hooks/useSwipeSession";

function App() {
  const session = useSwipeSession();

  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-4 bg-neutral-950">
      <header className="mb-6 text-center">
        <h1 className="text-2xl font-bold text-neutral-100 tracking-wide">
          swipe-persona
        </h1>
        <p className="text-neutral-500 text-sm mt-1">
          {session.phase === "swiping"
            ? `${session.index + 1} / ${session.questions.length}`
            : session.phase === "loading"
              ? "読み込み中..."
              : "完了"}
        </p>
      </header>

      <main className="relative w-full max-w-md h-[480px]">
        {session.phase === "loading" && (
          <div className="absolute inset-0 flex items-center justify-center text-neutral-500">
            Loading questions...
          </div>
        )}

        {session.phase === "swiping" && session.currentQuestion && (
          <SwipeCard
            key={session.currentQuestion.question_id}
            question={session.currentQuestion}
            onSwipe={session.handleSwipe}
          />
        )}

        {session.phase === "finished" && (
          <div className="absolute inset-0 flex flex-col items-center justify-center text-center p-6 rounded-2xl bg-neutral-900">
            <h2 className="text-xl text-neutral-100 mb-2">お疲れさまでした</h2>
            {session.error ? (
              <p className="text-red-400 text-sm">{session.error}</p>
            ) : (
              <p className="text-neutral-400 text-sm">
                {session.answers.length} 問の回答を受け取りました
              </p>
            )}
          </div>
        )}
      </main>

      <footer className="mt-6 text-xs text-neutral-600">
        ← NO / ↑ SKIP / YES →
      </footer>
    </div>
  );
}

export default App;
