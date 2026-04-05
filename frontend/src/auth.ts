// パスフレーズによるクライアントサイド簡易ゲート
//
// 目的: 湧心くん専用ツールのため、他人が URL を踏んで回答を送信しないようにする
// 性質: これは暗号学的「認証」ではなく「ゲート」。ソースを読めばハッシュが見える。
//       パスフレーズが十分長ければ実用的なブルートフォースは困難。
// 本当のセキュリティは Phase 5 で n8n webhook 側の秘密ヘッダー検証に委ねる。

// 正解パスフレーズの SHA-256 ハッシュ (ハードコード)
const EXPECTED_HASH =
  "66f742a8e1405c89c390fc8b1c34e7f07a094139f162902dfe2713b11e12f7b9";

const STORAGE_KEY = "sp_auth_token";

async function sha256(input: string): Promise<string> {
  const bytes = new TextEncoder().encode(input);
  const hash = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(hash))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export async function verifyPassphrase(input: string): Promise<boolean> {
  const hash = await sha256(input);
  return hash === EXPECTED_HASH;
}

export function isUnlocked(): boolean {
  return localStorage.getItem(STORAGE_KEY) === EXPECTED_HASH;
}

export function markUnlocked(): void {
  // 格納値 = ハッシュ自体。平文パスフレーズは localStorage にも残さない
  localStorage.setItem(STORAGE_KEY, EXPECTED_HASH);
}

export function lock(): void {
  localStorage.removeItem(STORAGE_KEY);
}

/** 将来 Phase 5 で webhook 呼び出し時に Authorization ヘッダーに使う用 */
export function getAuthToken(): string | null {
  return localStorage.getItem(STORAGE_KEY);
}
