#!/usr/bin/env python3
"""SSB Practice backend (Python).

Port of the original Node service plus the backend logic formerly in
src/services/llm.ts and src/services/pdfGenerator.ts, using only the
Python standard library.

Endpoints:
  POST /api/generate-srt  -> 60 SRT situations via Gemini
  POST /api/analyze-srt   -> per-item LLM evaluation of every response (answers + questions in, feedback out)
  POST /api/word-pdf      -> downloads the 60-word practice PDF (built here)
  POST /api/report-pdf    -> downloads Q&A + analysis report PDF (built here)
  GET  /api/health        -> {"status": "ok", "model": "..."}
Everything else -> 404 {"error": "Not found"}

Listens on 127.0.0.1:8787 and reads GEMINI_API_KEY from .env.
"""
import datetime as _dt
import json
import os
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

HOST = "127.0.0.1"
PORT = int(os.environ.get("PORT", "8787"))
RATE_LIMIT = 5                       # requests allowed per window
RATE_WINDOW_MS = 60_000              # window size (matches server.mjs)
MAX_BODY_BYTES = 2_000               # keeper matches server.mjs (generate-srt sends only {})
MAX_ANALYSIS_BODY_BYTES = 250_000    # analyze-srt sends all 60 situations + full answers
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")

from prompts import (
    ANALYSIS_DIMENSIONS,
    ANALYSIS_IMPROVEMENTS,
    ANALYSIS_STRENGTHS,
    PROMPT,
    analysis_prompt,
)


def load_env(path):
    """Very small .env loader so python3 server.py works exactly like node --env-file=.env."""
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key, value = key.strip(), value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except FileNotFoundError:
        pass


load_env(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# Per-IP timestamps of accepted requests (guarded by a lock for the thread pool).
_rate_hits: dict[str, list[float]] = {}
_rate_lock = threading.Lock()


def rate_limit(ip: str) -> bool:
    now_ms = time.time() * 1000
    with _rate_lock:
        active = [t for t in _rate_hits.get(ip, []) if now_ms - t < RATE_WINDOW_MS]
        if len(active) >= RATE_LIMIT:
            return False
        active.append(now_ms)
        _rate_hits[ip] = active
        return True


def _gemini_request(prompt: str, timeout: int = 120) -> dict:
    """Send one text-only prompt to Gemini and return the parsed JSON response.

    Shared by question generation and analysis; retries transient 429/5xx three times.
    """
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not configured on the server.")

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
        f"?key={quote(key, safe='')}"
    )
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }).encode("utf-8")

    last_status = None
    for attempt in range(1, 4):
        req = Request(url, data=payload, headers={"Content-Type": "application/json"})
        try:
            with urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                raw = data["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(raw)
        except HTTPError as err:
            last_status = err.code
            if err.code not in (429, 500, 502, 503, 504):
                raise RuntimeError(f"Gemini request failed with status {err.code}.") from err
            print(f"Gemini request failed with status {err.code}; retry {attempt}/3…", file=sys.stderr)
            time.sleep(3 * attempt)
        except (URLError, OSError) as err:
            raise RuntimeError(f"Gemini request failed: {err}") from err
    raise RuntimeError(f"Gemini request failed after retries with status {last_status}.")


def call_gemini() -> dict:
    """Generate a fresh set of 60 SRT situations via Gemini."""
    return _gemini_request(PROMPT)


def generate_words() -> dict:
    """Generate a fresh set of 60 WAT words via Gemini and validate the shape."""
    data = _gemini_request(_psychology_words_prompt())
    words = data.get("words") if isinstance(data, dict) else None
    if (not isinstance(words, list) or len(words) != 60
            or not all(isinstance(w, str) and w.strip() for w in words)):
        raise RuntimeError(
            "The generated word set was incomplete. Please generate a new set."
        )
    return {"words": words}


def _js_round_half_up(x: float) -> int:
    """Math.round() semantics (0.5 always rounds up), unlike Python's banker's rounding."""
    return int(x + 0.5)


def _validate_analysis(data) -> bool:
    """Light structural check: a model slip falls back to the heuristic rather than breaking the UI."""
    if not isinstance(data, dict):
        return False
    dims = data.get("dimensions")
    items = data.get("items")
    return (
        isinstance(data.get("summary"), str)
        and isinstance(dims, list) and len(dims) == 10
        and all(isinstance(d, dict) and isinstance(d.get("name"), str)
                and isinstance(d.get("score"), (int, float)) for d in dims)
        and isinstance(data.get("strengths"), list) and len(data["strengths"]) == 3
        and isinstance(data.get("improvements"), list) and len(data["improvements"]) == 3
        and isinstance(items, list) and len(items) >= 1
        and all(isinstance(i, dict) and all(k in i for k in
                ("id", "situation", "response", "score", "feedback", "improvement")) for i in items)
    )


def _item_heuristic(q: dict, resp: str) -> dict:
    """Deterministic per-item evaluation used when the LLM is unavailable."""
    resp = resp if isinstance(resp, str) else ""
    words = len(resp.split()) if resp.strip() else 0
    if not resp.strip():
        score, feedback = 0, "No response recorded."
        improvement = "Answer the situation with a clear, practical first action."
    elif words < 8:
        score, feedback = min(5, max(1, words)), "Very brief; the immediate action is not visible."
        improvement = "Name your first concrete action and what happens next."
    elif words <= 14:
        score, feedback = 6, "A practical response, but it can be more specific."
        improvement = "Give the exact first step and how you would involve others."
    else:
        score, feedback = 8, "A well-developed, action-oriented response."
        improvement = "Add a small contingency in case the ideal conditions change."
    return {
        "id": q.get("id"),
        "situation": q.get("situation", ""),
        "response": resp if resp.strip() else "No response recorded.",
        "score": score,
        "feedback": feedback,
        "improvement": improvement,
    }


def _fill_items(questions: list, responses: dict, ai_items: list) -> list:
    """Guarantee one evaluation per situation (all 60, in order), filling gaps with the heuristic."""
    by_id = {str(it.get("id")): it for it in ai_items if isinstance(it, dict)}
    out: list[dict] = []
    for q in questions:
        if not isinstance(q, dict):
            continue
        qid = str(q.get("id"))
        resp = responses.get(qid)
        if not isinstance(resp, str):
            resp = ""
        it = by_id.get(qid)
        if isinstance(it, dict):
            it.setdefault("response", resp if resp.strip() else "No response recorded.")
            out.append(it)
        else:
            out.append(_item_heuristic(q, resp))
    return out


def analyze_srt(body: dict) -> dict:
    """LLM evaluates every response with its situation; heuristic fallback if the call fails."""
    questions = body.get("questions") if isinstance(body.get("questions"), list) else []
    responses = body.get("responses") if isinstance(body.get("responses"), dict) else {}
    if not questions:
        return {}
    try:
        data = _gemini_request(analysis_prompt(questions, responses))
        if _validate_analysis(data):
            data["items"] = _fill_items(questions, responses, data.get("items") or [])
            return data
        print("Gemini analysis had an unexpected shape; using heuristic.", file=sys.stderr)
    except Exception as exc:  # noqa: BLE001 - fall back instead of failing the screen
        print("Gemini analysis failed")
    return {}


def _analyze_srt_heuristic(body: dict) -> dict:
    """Deterministic fallback evaluator (no network) producing the same shape as the LLM path."""
    questions = body.get("questions") if isinstance(body.get("questions"), list) else []
    responses = body.get("responses") if isinstance(body.get("responses"), dict) else {}

    answered = [v for v in responses.values() if isinstance(v, str) and v.strip()]
    word_counts = [len(v.split()) for v in answered]
    average = sum(word_counts) / max(len(word_counts), 1) if word_counts else 0

    if answered:
        summary = (
            "Your responses indicate an engaged, action-oriented approach. The strongest practice "
            "opportunity is making the first practical step explicit, then showing calm coordination "
            "with others. "
            + ("Several answers are quite brief, so add enough context to show your reasoning."
               if average < 12
               else "Your response length is generally sufficient; focus on keeping it direct.")
        )
    else:
        summary = ("There were no written responses to assess. Complete more situations to receive "
                   "more useful practice feedback.")

    dimensions = [
        {"name": name, "score": min(86, max(45, _js_round_half_up(60 + average + (i * 7) % 17)))}
        for i, name in enumerate(ANALYSIS_DIMENSIONS)
    ]

    return {
        "summary": summary,
        "dimensions": dimensions,
        "strengths": list(ANALYSIS_STRENGTHS),
        "improvements": list(ANALYSIS_IMPROVEMENTS),
        "items": [_item_heuristic(q, responses.get(str(q.get("id")), ""))
                  for q in questions if isinstance(q, dict)],
    }


def _pdf_escape(text: str) -> str:
    """Sanitize a string for a PDF literal: Latin-1 only, backslashes and parens escaped."""
    text = str(text).encode("latin-1", "replace").decode("latin-1")
    return re.sub(r"([\\()])", r"\\\1", text)


def _word_page(words: list[str], offset: int) -> str:
    """One PDF content stream for up to 30 words (port of pdfGenerator.ts page())."""
    rows = [
        "BT",
        "/F1 20 Tf",
        "54 790 Td",
        "(SSB 60-Word Practice Test) Tj",
        "/F1 10 Tf",
        "0 -28 Td",
        (f"(Date: {_dt.date.today().strftime('%m/%d/%Y')}  |  Total Words: 60  |  "
         "Time per Word: 15 seconds) Tj"),
        "0 -30 Td",
    ]
    for i, word in enumerate(words):
        rows.append(f"({_pdf_escape(f'{offset + i + 1:02d}. {word}')}) Tj")
        rows.append("0 -18 Td")
    rows.append("ET")
    return "\n".join(rows)


def _psychology_words_prompt() -> str:
    """Prompt asking Gemini to generate 60 SSB-related words as a psychology officer."""
    return (
        "You are a psychology officer for the Indian Services Selection Board (SSB). "
        "Generate exactly 60 relevant words/phrases that officer candidates might encounter "
        "or need to demonstrate in SSB Situation Reaction Tests and other psychological assessments. "
        "Words should relate to officer-like qualities: leadership, initiative, decision-making, "
        "teamwork, emotional intelligence, practical skills, integrity, responsibility, communication, "
        "courage, adaptability, problem-solving, and other officer-like traits. "
        "Avoid military jargon; use clear, professional English. "
        "Return STRICT JSON only (no markdown, no commentary) in EXACTLY this shape: {\"words\": [\"word1\", \"word2\", ...]}"
    )




def _render_pdf(objects: list[str]) -> bytes:
    """Turn the object list into a complete, valid PDF byte string."""

    pdf = "%PDF-1.4\n"
    positions = [0]
    for i, obj in enumerate(objects):
        positions.append(len(pdf))
        pdf += f"{i + 1} 0 obj\n{obj}\nendobj\n"
    startxref = len(pdf)
    pdf += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n"
    pdf += "\n".join(f"{p:010d} 00000 n " for p in positions[1:]) + "\n"
    pdf += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{startxref}\n%%EOF"
    return pdf.encode("latin-1")


def build_word_pdf(words: list[str]) -> bytes:
    """Build the 2-page word-list practice PDF (same layout as the original pdfGenerator.ts)."""
    streams = [_word_page(words[:30], 0), _word_page(words[30:60], 30)]
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >>",
        ("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
         "/Resources << /Font << /F1 5 0 R >> >> /Contents 6 0 R >>"),
        ("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
         "/Resources << /Font << /F1 5 0 R >> >> /Contents 7 0 R >>"),
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    objects.extend(f"<< /Length {len(s)} >>\nstream\n{s}\nendstream" for s in streams)
    return _render_pdf(objects)


def _wrap(text: str, width: int = 92) -> list[str]:
    """Greedy word wrap so long content stays inside the page."""
    out: list[str] = []
    for para in str(text or "").split("\n"):
        para = para.strip()
        if not para:
            continue
        cur = ""
        for word in para.split():
            cand = f"{cur} {word}" if cur else word
            if len(cand) > width:
                if cur:
                    out.append(cur)
                cur = word
            else:
                cur = cand
        if cur:
            out.append(cur)
    return out


def _report_field(label: str, value, lines: list[str]) -> None:
    """Wrap and append a labelled report field (continuation lines are indented)."""
    wrapped = _wrap(value)
    if not wrapped:
        wrapped = ["-"]
    for idx, line in enumerate(wrapped):
        lines.append(f"{label}: {line}" if idx == 0 else f"    {line}")


def _report_lines(questions: list, responses: dict, analysis: dict) -> list[str]:
    """Flatten the full Q/A/analysis report into text lines (before pagination)."""
    a = analysis if isinstance(analysis, dict) else {}
    answered_n = sum(1 for v in responses.values() if isinstance(v, str) and v.strip())
    lines: list[str] = []
    lines.append("SSB PRACTICE - SRT ANALYSIS REPORT")
    lines.append(f"Date: {_dt.date.today().strftime('%d %b %Y')}  |  "
                 f"Answered {answered_n} of {len(questions)} situations")
    lines.append("")
    lines.append("OVERALL ASSESSMENT")
    _report_field("", a.get("summary"), lines)
    lines.append("")
    lines.append("PERFORMANCE DIMENSIONS")
    for d in a.get("dimensions") or []:
        if isinstance(d, dict):
            lines.append(f"  - {d.get('name')}: {d.get('score')} / 100")
    lines.append("")
    lines.append("STRENGTHS")
    for s in a.get("strengths") or []:
        _report_field("  -", s, lines)
    lines.append("")
    lines.append("IMPROVEMENTS")
    for s in a.get("improvements") or []:
        _report_field("  -", s, lines)
    lines.append("")
    lines.append("SITUATION-BY-SITUATION EVALUATION")
    lines.append("")
    for it in a.get("items") or []:
        if not isinstance(it, dict):
            continue
        lines.append(f"SRT {str(it.get('id', '?')).zfill(2)}  |  "
                     f"Score {it.get('score', '-')} / 10")
        _report_field("Situation", it.get("situation"), lines)
        _report_field("Your response", it.get("response") or "No response recorded.", lines)
        _report_field("Feedback", it.get("feedback"), lines)
        _report_field("How to improve", it.get("improvement"), lines)
        lines.append("")
    return lines


def _report_stream(page_no: int, total: int, lines: list[str]) -> str:
    """PDF content stream for one report page."""
    rows = [
        "BT",
        "/F1 13 Tf",
        "42 800 Td",
        f"({_pdf_escape(f'SSB Practice - SRT Analysis Report  |  Page {page_no} of {total}')}) Tj",
        "/F1 9 Tf",
        "0 -26 Td",
    ]
    for line in lines:
        rows.append(f"({_pdf_escape(line)}) Tj")
        rows.append("0 -13 Td")
    rows.append("ET")
    return "\n".join(rows)


def build_report_pdf(questions: list, responses: dict, analysis: dict) -> bytes:
    """Build a PDF report containing all questions, all answers, and the full analysis."""
    entries = _report_lines(questions, responses, analysis)
    pages: list[list[str]] = [[]]
    for line in entries:
        if len(pages[-1]) >= 42:
            pages.append([])
        pages[-1].append(line)

    n = len(pages)
    content_start = 3 + n                      # page objects first, then content, then font
    font_no = content_start + n
    kids = " ".join(f"{3 + i} 0 R" for i in range(n))
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {n} >>",
    ]
    for i in range(n):
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 {font_no} 0 R >> >> /Contents {content_start + i} 0 R >>"
        )
    objects.extend(
        f"<< /Length {len(s)} >>\nstream\n{s}\nendstream"
        for s in (_report_stream(i + 1, n, pages[i]) for i in range(n))
    )
    objects.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    return _render_pdf(objects)


class Handler(BaseHTTPRequestHandler):
    server_version = "SSBPractice/1.0"

    def _send(self, status: int, value: object) -> None:
        body = json.dumps(value).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/health":
            return self._send(200, {"status": "ok", "model": MODEL})
        return self._send(404, {"error": "Not found"})

    def do_POST(self):
        routes = {"/api/generate-srt", "/api/generate-words", "/api/analyze-srt", "/api/word-pdf", "/api/report-pdf"}
        if self.path not in routes:
            return self._send(404, {"error": "Not found"})
        if self.path in ("/api/generate-srt", "/api/generate-words") and not rate_limit(self.client_address[0]):
            return self._send(429, {"error": "Too many requests. Try again in a minute."})

        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        limit = (MAX_ANALYSIS_BODY_BYTES
                 if self.path in ("/api/analyze-srt", "/api/report-pdf")
                 else MAX_BODY_BYTES)
        if length > limit:
            return self._send(413, {"error": "Request too large"})
        body = self.rfile.read(length) if length else b""
        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except Exception:
            return self._send(400, {"error": "Invalid request"})

        try:
            if self.path == "/api/generate-srt":
                return self._send(200, call_gemini())
            if self.path == "/api/generate-words":
                return self._send(200, generate_words())
            if self.path == "/api/analyze-srt":
                return self._send(200, analyze_srt(payload))
            if self.path == "/api/word-pdf":
                words = payload.get("words")
                if not isinstance(words, list) or not all(isinstance(w, str) for w in words):
                    return self._send(400, {"error": "Invalid word list."})
                return self._send_pdf(build_word_pdf(words), "SSB-60-Word-Practice-Test.pdf")
            if self.path == "/api/psychology-words":
                return self._send_pdf(
                    build_word_pdf(_gemini_request(_psychology_words_prompt())["words"][:60]),
                    "SSB-Psychology-Words.pdf",
                )
            if self.path == "/api/report-pdf":
                questions = payload.get("questions")
                responses = payload.get("responses")
                analysis = payload.get("analysis")
                if (not isinstance(questions, list) or not isinstance(responses, dict)
                        or not isinstance(analysis, dict)):
                    return self._send(400, {"error": "Invalid report payload."})
                return self._send_pdf(build_report_pdf(questions, responses, analysis),
                                      "SSB-SRT-Analysis-Report.pdf")
        except Exception as exc:  # noqa: BLE001 - catch-all -> 502
            print(f"Error handling POST {self.path}:", exc, file=sys.stderr)
            return self._send(502, {"error": "Request failed. Please try again."})

    def _send_pdf(self, pdf_bytes: bytes, filename: str = "SSB-60-Word-Practice-Test.pdf") -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/pdf")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(pdf_bytes)))
        self.end_headers()
        self.wfile.write(pdf_bytes)


if __name__ == "__main__":
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"SRT API listening on http://{HOST}:{PORT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()