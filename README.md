# Complaint Compass

Customer complaint intake and intelligence platform.

## Chosen stack

| Layer | Technology |
| --- | --- |
| Frontend | React + Vite |
| Styling | Tailwind CSS + shadcn/ui |
| Backend | Python + FastAPI |
| Database | Supabase PostgreSQL (SQLite local fallback) |
| Embeddings | `all-MiniLM-L6-v2` |
| Clustering | HDBSCAN |
| Classification | Scikit-learn |
| LLM | Ollama + Qwen2.5 |
| Charts | Recharts |
| Deployment | Vercel + Render |

The app uses React + Vite, Tailwind CSS, FastAPI, and a database adapter that selects PostgreSQL when `DATABASE_URL` is set or SQLite locally. Complaint analysis uses Sentence Transformers (`all-MiniLM-L6-v2`), HDBSCAN from scikit-learn, and optional local Ollama/Qwen2.5 naming. Production workspace/API access uses a workspace token; channel webhooks use their own token.

## Requirements

- Python 3.10+
- Node.js 20.19+ or 22.12+
- Git

## Start the backend

From the repository root in PowerShell:

```powershell
python -m pip install -r backend/requirements.txt
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

For Supabase, copy `backend/.env.example` to `backend/.env`, then replace its `DATABASE_URL` with the connection URI from your Supabase project's **Connect** panel. Use a session pooler URI when your network only supports IPv4. If `DATABASE_URL` is not set, the API creates a local SQLite database automatically.

## Start the frontend

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. The dashboard header shows whether the API connection is live. The backend API docs are at <http://127.0.0.1:8000/docs>.

## Complaint analysis

Add complaints or upload `dataset/complaints.csv`, then open **Issues** and choose **Analyze complaints**. The first analysis downloads `sentence-transformers/all-MiniLM-L6-v2` into the ignored `backend/data/model-cache` folder. Optional labels use local Ollama with `qwen2.5:3b` when available; otherwise the API generates keyword-based labels. To use the LLM labels, install Ollama and pull that model before analysis.

Email, voice, chatbot, and social integrations can forward normalized JSON events to authenticated channel webhooks. See [backend/README.md](backend/README.md#email-voice-chatbot-and-social-intake) for payload fields and deployment requirements. Voice events need a transcript from the voice provider.

Analysis normalizes text, creates semantic embeddings, groups reports with HDBSCAN, links likely repeat submissions only when they share a customer ID, meet the similarity threshold, and fall within the time window, then ranks issue clusters. Defaults are cosine similarity `0.92` and 30 days. Repeat reports remain visible but do not increase a cluster's unique report or affected-customer count. Similar complaints from different customers count as separate affected customers.

### Issue priority

Each analysis run records the transparent score `Priority = 0.4S + 0.3F + 0.3I`. Severity `S` maps average complaint severity from 1–5 to 0–100 with `((average - 1) / 4) × 100`. Frequency `F` is each issue's unique report count relative to the largest issue in that run; customer impact `I` uses affected-customer count relative to that run's largest issue. Each component and the weighted result are stored with the cluster. Since frequency and impact are relative, scores compare issues within the same analysis run and can shift when the dataset changes. Repeat submissions are excluded from the unique report count.

## Current scope

Current capabilities include local SQLite or Supabase PostgreSQL, complaint intake, customer profiles, CSV validation, semantic embeddings, HDBSCAN issue groups, cross-channel repeat linking when providers supply a verified shared customer ID, readable labels, transparent issue prioritization, complaint trends, demographic filters with cohort-to-workspace comparisons, emerging issue summaries, CSV / print-to-PDF reporting, issue owner/status/notes, staleness notices, and database compatibility views. Production API access uses a shared workspace token. Trained severity classification, provider account configuration, per-user roles, and multi-organization isolation remain future work.

## Run checks

From the repository root, install backend test dependencies and run the test suite:

```powershell
python -m pip install -r backend/requirements-dev.txt
python -m pytest -q
```

The backend checks cover CSV encodings, headers, delimiters and row validation; a manually labeled semantic grouping sample using the local embedding model; repeat linking across intake channels; API/database integration; and priority calculations. The semantic test uses the cached model when available or downloads it on first run. Frontend customer-segment filter checks run with `npm test` from `frontend/`.

## Public demo deployment

The included `render.yaml` creates a Render API service with Sentence Transformers and `sentence-transformers/all-MiniLM-L6-v2` available for analysis. Set `DATABASE_URL`, `INTAKE_WEBHOOK_TOKEN`, and `WORKSPACE_ACCESS_TOKEN` in Render's secret settings. Use different long random values for workspace access and webhook intake. If workspace authentication is enabled without its token, protected API routes fail closed with HTTP 503. The first analysis downloads the model; Render's temporary filesystem may require another download after a service restart.

1. In Render, create a Blueprint from this repository using `render.yaml`. Set its `DATABASE_URL` to the Supabase pooler URI and configure different long random values for `INTAKE_WEBHOOK_TOKEN` and `WORKSPACE_ACCESS_TOKEN`. The health check is `/api/health`.
2. Before making the API public, run `python -m backend.seed_demo` once from the repository root with `backend/.env` pointing to the dedicated demo Supabase project. This loads the six synthetic complaints and computes the initial analysis. The script refuses to seed unrelated complaint records.
3. In Vercel, import the same repository and set the project root to `frontend`. Add `VITE_API_BASE_URL` with the Render service URL, for example `https://complaint-compass-demo-api.onrender.com`, then deploy or redeploy after setting it.

The app uses same-origin relative `/api` requests locally through the Vite proxy. `VITE_API_BASE_URL` switches those calls to the hosted API. Render uses `DEMO_MODE=false` to accept writes and requires `WORKSPACE_ACCESS_TOKEN` for dashboard and API access; the frontend presents a token prompt. `VITE_DEMO_MODE` only controls initial UI state; the API health response sets the final mode.

The free Render API sleeps after 15 minutes without traffic and can take about a minute to wake. This is suitable for a competition or portfolio demo, but expect a delay on the first visit after idle time.
