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

## Deploy to production

The built frontend is a static SPA. The recommended setup is nginx as a reverse proxy that serves `dist/` and forwards `/api/*` to the Python backend:

```bash
# 1. Build the frontend
npm run build

# 2. Copy dist/ and server files to your server
rsync -av dist/ /var/www/ssb-practice/dist/
scp server.py prompts.py /var/www/ssb-practice/

# 3. Set GEMINI_API_KEY as a real environment variable on the server
# 4. Install nginx and copy the example config
sudo cp nginx.conf /etc/nginx/sites-available/ssb-practice
sudo ln -s /etc/nginx/sites-available/ssb-practice /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# 5. Run the Python backend as a managed service (restarts on crash)
sudo cp ssb-backend.service /etc/systemd/system/
# Edit the service file to set your real GEMINI_API_KEY, then:
sudo systemctl daemon-reload
sudo systemctl enable ssb-backend
sudo systemctl start ssb-backend

# 6. Add HTTPS (highly recommended)
sudo certbot --nginx -d your-domain.com
```

See `nginx.conf` for the full reverse-proxy configuration and `ssb-backend.service` for the systemd unit file.

├── index.html                    # entry with SEO meta tags + <div id="root">
├── package.json                  # scripts: dev | server | build | preview
├── vite.config.ts                # React plugin + dev proxy: /api → http://127.0.0.1:8787
├── server.py                    # <-- the backend: Python stdlib HTTP -> Gemini proxy (8787)
├── prompts.py                   # centralized LLM prompt strings
├── nginx.conf                   # production reverse-proxy config (static + /api proxy)
├── ssb-backend.service          # systemd unit file for running server.py on Linux
├── server.mjs                   # legacy Node backend, kept for reference
├── .env                          # GEMINI_API_KEY  (gitignored — good)
├── .gitignore                    # node_modules / dist / .env
├── tsconfig.json / tsconfig.node.json
├── dist/                         # production build (built OK)
├── src/
│   ├── main.tsx                  # ENTIRE app: 8 screens in one file (state machine)
│   ├── styles.css                # global styles (flexbox layout, typography, darkbtn, etc.)
│   ├── data/
│   │   ├── srtQuestions.ts       # SRTQuestion interface {id, situation}
│   │   └── words.ts              # 60 static words for the Word test
│   └── services/
│       ├── srtGenerator.ts       # POST /api/generate-srt → validates 60 Q's
│       ├── llm.ts                # client for POST /api/analyze-srt (Gemini AI analysis, heuristic fallback)
│       └── pdfGenerator.ts       # client for POST /api/word-pdf (PDF built server-side)
├── outputs/, work/               # empty scratch dirs
└── node_modules/