import type { SRTQuestion } from "../data/srtQuestions";

export interface AnalysisItem {
  id: number;
  situation: string;
  response: string;
  score: number;
  feedback: string;
  improvement: string;
}

export interface Analysis {
  summary: string;
  dimensions: { name: string; score: number }[];
  strengths: string[];
  improvements: string[];
  items: AnalysisItem[];
}

/**
 * The analysis logic now lives in the Python backend (server.py -> /api/analyze-srt,
 * ported from the old llm.ts heuristic). The frontend just posts the answers and
 * situations and renders whatever the backend returns.
 */
export async function analyzeSRTResponses(
  responses: Record<number, string>,
  questions: SRTQuestion[],
): Promise<Analysis> {
  const res = await fetch("/api/analyze-srt", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ questions, responses }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => null);
    throw new Error(err?.error || `Analysis request failed (${res.status}).`);
  }
  return await res.json();
}
