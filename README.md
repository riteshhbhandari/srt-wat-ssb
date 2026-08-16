# SSB Practice

## Run locally

Open two VS Code terminals.

```bash
# Terminal 1 — the Gemini key stays in .env, never in the browser
npm run server

# Terminal 2 — React app
npm run dev
```

The Python backend (`server.py`, standard-library only) reads `GEMINI_API_KEY` from `.env`, listens only on `127.0.0.1:8787`, and Vite forwards `/api` requests to it during development. `npm run server` starts it with `python3`; the original Node implementation is kept at `server.mjs` for reference.

├── index.html                    # single entry: <div id="root"> + /src/main.tsx
├── package.json                  # scripts: dev | server | build | preview
├── vite.config.ts (+ .js copy)   # React plugin + dev proxy: /api → http://127.0.0.1:8787
├── server.py                    # <-- the backend: Python stdlib HTTP -> Gemini proxy (8787)
├── server.mjs                   # legacy Node backend, kept for reference
├── .env                          # GEMINI_API_KEY  (gitignored — good)
├── .gitignore                    # node_modules / dist / .env
├── tsconfig.json / tsconfig.node.json
├── dist/                         # production build (built OK)
├── src/
│   ├── main.tsx                  # ENTIRE app: 8 screens in one file (state machine)
│   ├── styles.css                # 3 lines (inline-styled UI elsewhere)
│   ├── data/
│   │   ├── srtQuestions.ts       # SRTQuestion interface {id, situation}
│   │   └── words.ts              # 60 static words for the Word test
│   └── services/
│       ├── srtGenerator.ts       # POST /api/generate-srt → validates 60 Q's
│       ├── llm.ts                # client for POST /api/analyze-srt (Gemini AI analysis, heuristic fallback)
│       └── pdfGenerator.ts       # client for POST /api/word-pdf (PDF built server-side)
├── outputs/, work/               # empty scratch dirs
└── node_modules/