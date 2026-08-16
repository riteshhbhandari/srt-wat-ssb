import { testWords } from '../data/words';

/**
 * The PDF layout/building logic now lives in the Python backend (server.py,
 * /api/word-pdf, ported from the old pdfGenerator.ts). This client only asks
 * the backend to build it and downloads the resulting blob.
 */
export async function downloadWordList() {
  const res = await fetch('/api/word-pdf', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ words: testWords }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => null);
    throw new Error(err?.error || `Download failed (${res.status}).`);
  }
  const blob = await res.blob();
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = 'SSB-60-Word-Practice-Test.pdf';
  link.click();
  URL.revokeObjectURL(link.href);
}

/**
 * Ask the backend to build a combined Q+A + AI-feedback PDF report and
 * download it. Mirrors server.py -> /api/report-pdf.
 */
import type { SRTQuestion } from '../data/srtQuestions';
import type { Analysis } from './llm';

export async function downloadAnalysisReport(
  questions: SRTQuestion[],
  responses: Record<number, string>,
  analysis: Analysis,
) {
  const res = await fetch('/api/report-pdf', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ questions, responses, analysis }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => null);
    throw new Error(err?.error || `Download failed (${res.status}).`);
  }
  const blob = await res.blob();
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = 'SSB-SRT-Analysis-Report.pdf';
  link.click();
  URL.revokeObjectURL(link.href);
}