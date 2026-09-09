/**
 * Ask the backend (server.py -> /api/generate-words) to generate a fresh,
 * varied set of 60 WAT words via Gemini. Throws if the request fails or the
 * response is malformed; the caller (Intro.begin) surfaces the error and keeps
 * the user on the intro screen. The static testWords list in main.tsx serves as
 * the initial/default state so the word-test screen never renders undefined.
 */
export async function generateWords(): Promise<string[]> {
  const res = await fetch("/api/generate-words", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  });
  if (!res.ok) {
    const error = await res.json().catch(() => null);
    throw new Error(
      error?.error || `Word generation request failed (${res.status}).`,
    );
  }
  const { words } = await res.json();
  if (
    !Array.isArray(words) ||
    words.length !== 60 ||
    words.some((w: unknown) => typeof w !== "string" || !w.trim())
  ) {
    throw new Error(
      "The generated set was incomplete. Please generate a new set.",
    );
  }
  return words as string[];
}
