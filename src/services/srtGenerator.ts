import type { SRTQuestion } from "../data/srtQuestions";

const parse = (text: string): SRTQuestion[] => {
  const json = text.match(/\{[\s\S]*\}/)?.[0];
  if (!json) throw new Error("The model did not return structured questions.");
  const questions = JSON.parse(json).questions as SRTQuestion[];
  if (
    !Array.isArray(questions) ||
    questions.length !== 60 ||
    questions.some((q, i) => !q?.situation || q.id !== i + 1)
  )
    throw new Error(
      "The generated set was incomplete. Please generate a new set.",
    );
  return questions;
};
export async function generateSRTQuestions(): Promise<SRTQuestion[]> {
  const res = await fetch("/api/generate-srt", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  });
  if (!res.ok) {
    const error = await res.json().catch(() => null);
    throw new Error(
      error?.error || `Generation request failed (${res.status}).`,
    );
  }
  return parse(JSON.stringify(await res.json()));
}
