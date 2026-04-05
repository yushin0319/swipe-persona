import { useState } from "react";
import { markUnlocked, verifyPassphrase } from "../auth";

interface Props {
  onUnlock: () => void;
}

export function AuthGate({ onUnlock }: Props) {
  const [value, setValue] = useState("");
  const [error, setError] = useState(false);
  const [checking, setChecking] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setChecking(true);
    setError(false);
    const ok = await verifyPassphrase(value);
    setChecking(false);
    if (ok) {
      markUnlocked();
      onUnlock();
    } else {
      setError(true);
      setValue("");
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-neutral-950 p-4">
      <form
        onSubmit={submit}
        className="w-full max-w-sm p-8 rounded-2xl bg-neutral-900 shadow-2xl flex flex-col gap-4"
      >
        <h1 className="text-neutral-100 text-xl font-bold text-center tracking-wide">
          swipe-persona
        </h1>
        <p className="text-neutral-500 text-xs text-center">
          パスフレーズを入力してください
        </p>
        <input
          type="password"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          autoFocus
          className="bg-neutral-800 text-neutral-100 rounded-lg px-4 py-3 outline-none focus:ring-2 focus:ring-neutral-500"
          placeholder="passphrase"
        />
        {error && (
          <p className="text-red-400 text-xs text-center">
            認証に失敗しました
          </p>
        )}
        <button
          type="submit"
          disabled={checking || !value}
          className="bg-neutral-100 text-neutral-900 rounded-lg py-3 font-semibold disabled:opacity-50 hover:bg-white transition"
        >
          {checking ? "確認中..." : "入る"}
        </button>
      </form>
    </div>
  );
}
