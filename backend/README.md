# Complaint Compass API

## Run locally

From the repository root:

```powershell
python -m pip install -r backend/requirements.txt
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Health check: <http://127.0.0.1:8000/api/health>  
Interactive API docs: <http://127.0.0.1:8000/docs>

The database adapter uses Supabase PostgreSQL when `DATABASE_URL` is configured, with SSL required. For local work without credentials it uses SQLite at `backend/data/complaint_compass.db`; override that path with `COMPLAINT_COMPASS_DB`. Copy `backend/.env.example` to `backend/.env` and paste the URI from the Supabase project's **Connect** panel to enable PostgreSQL.

## Complaint endpoints

- `POST /api/complaints` — create a complaint and optional customer profile
- `POST /api/complaints/upload` — import UTF-8 CSV (up to 10 MB), skipping invalid and duplicate IDs with row-level errors
- `GET /api/complaints` — search/filter complaint records
- `GET /api/complaints/{complaint_id}` — retrieve one complaint
- `POST /api/customers` and `GET /api/customers` — create/update and list customer profiles
- `GET /api/analytics/overview` — counts used by the dashboard
- `GET /api/analytics/trends` — monthly complaint totals and emerging issue counts
- `GET /api/analytics/segments` — customer profiles with complaint counts for segment analysis
- `GET /api/analytics/report.csv` — download all complaints with customer and issue fields
- `POST /api/analysis/run` — generate embeddings, cluster issues, link same-customer repeats, and label clusters
- `GET /api/issues` — latest analysis and issue clusters
- `GET /api/issues/top10` — highest priority issues (accepts an optional `limit`)
- `GET /api/issues/{cluster_id}` — issue details and member complaints
- `PATCH /api/issues/{cluster_id}/workflow` — save issue status, owner, and investigation notes
- `POST /api/complaints/analyze` — analysis route alias for `POST /api/analysis/run`

CSV headers accept `complaint_id` or `ID`, and `complaint_text`, `complaint`, or `description`. Optional fields include customer ID, channel/source, timestamp, severity (1–5 or minor/low/medium/high/critical), country, state, age group, student status and income bracket.

## Email, voice, chatbot and social intake

The API exposes an authenticated generic JSON webhook at `POST /api/intake` and channel-specific aliases for email, voice, chatbot, and social messages:

| Channel | Endpoint | Required message field | Common sender / event fields |
| --- | --- | --- | --- |
| Email | `POST /api/intake` with `channel: "email"` or `POST /api/intake/email` | `text`, `body`, `body_plain`, or `TextBody` | `from`, `sender`, `email`; `message_id`, `MessageID`, or `id`; optional `subject` |
| Voice | `POST /api/intake` with `channel: "voice"` or `POST /api/intake/voice` | `transcript`, `transcription`, or `speech_result` | `caller`, `from`, `phone_number`; `call_sid`, `CallSid`, or `id` |
| Chatbot | `POST /api/intake` with `channel: "chatbot"` or `POST /api/intake/chatbot` | `text`, `content`, or `message_text` | `user_id`, `from`; `message_id` or `id` |
| Social | `POST /api/intake` with `channel: "social"` or `POST /api/intake/social` | `text`, `content`, or `message_text` | `author_id`, `user_id`; `post_id`, `message_id`, or `id` |

Set `INTAKE_WEBHOOK_TOKEN` in the backend environment to a long random secret. Providers or an integration service must send it as `Authorization: Bearer <token>` or `X-Intake-Token: <token>`. The webhook accepts JSON up to 64 KB, returns `202` for a newly received complaint, and returns `202` with `status: duplicate` when the same provider event is retried. Provider event IDs make retries idempotent. Sender IDs become customer IDs; optional customer demographics can be included at the top level or under `customer`.

In production, set `WORKSPACE_AUTH_ENABLED=true` and `WORKSPACE_ACCESS_TOKEN` to a separate long random secret. The web dashboard prompts authorized staff for that token, keeps it in the current browser session, and sends it on API calls. All complaint/customer/issue/analytics/report routes require it; `/api/health` remains public and intake routes continue to use their separate webhook token. Keep both values in the host's secret store. For local development, leave `WORKSPACE_AUTH_ENABLED=false`.

To merge sender identifiers across channels, have the integration provide the same CRM `customer_id` (or `canonical_customer_id`, `identity_id`, or `crm_customer_id`) along with the channel's sender field at least once. Complaint Compass stores that channel-qualified sender as an alias. Later reports from the same address, phone, or provider ID resolve to the canonical customer automatically. Do not use this mapping for unverified identities; the CRM or integration is responsible for establishing that two identifiers belong to the same person.

Example email event:

```json
{
  "message_id": "mail-98314",
  "from": "customer@example.com",
  "subject": "Refund has not arrived",
  "body": "My refund was approved two weeks ago but has not reached my account.",
  "received_at": "2026-11-08T12:15:00Z"
}
```

For a single automation webhook, add the source channel to the JSON and send the event to `https://complaint-compass-demo-api.onrender.com/api/intake` (or `http://127.0.0.1:8000/api/intake` while running locally):

```json
{
  "channel": "chatbot",
  "event_id": "chat-7821",
  "user_id": "customer-104",
  "text": "The payment screen freezes when I submit my order."
}
```

For each source, configure its webhook or an automation service to map the source event into the fields above and forward it to the matching HTTPS endpoint. The hosted endpoints are `https://complaint-compass-demo-api.onrender.com/api/intake/email`, `/api/intake/voice`, `/api/intake/chatbot`, and `/api/intake/social`. Voice providers must submit a transcription or speech-to-text result; this API does not receive or transcribe raw audio. Email providers must forward parsed message text, and social integrations must have the platform's required webhook permissions. Keep the token in the provider's secret store. The Render blueprint sets `WORKSPACE_AUTH_ENABLED=true`; configure both `INTAKE_WEBHOOK_TOKEN` and `WORKSPACE_ACCESS_TOKEN` as separate secrets. Workspace complaint, CSV, analysis, and workflow writes stay behind the workspace token, while intake endpoints use their separate webhook token. If workspace authentication is enabled without its token, protected API calls fail closed with HTTP 503. Render installs `sentence-transformers` and uses `sentence-transformers/all-MiniLM-L6-v2`; the first analysis downloads model weights to the service's local cache.

In production, set `WORKSPACE_AUTH_ENABLED=true` and `WORKSPACE_ACCESS_TOKEN` to a separate long random secret. The dashboard asks staff for this token and keeps it only in the current browser session. It protects dashboard, complaint, customer, issue, analytics, and report routes; `/api/health` stays public and intake routes continue to use their separate webhook token. Local development keeps `WORKSPACE_AUTH_ENABLED=false`.

For identity matching, include the same verified CRM `customer_id` (or `canonical_customer_id`, `identity_id`, or `crm_customer_id`) with the channel sender field at least once. The API records the channel-qualified sender as an alias and resolves later reports from that sender to the CRM customer. When an integration supplies a verified canonical ID after earlier complaints arrived under a sender ID, those earlier records are merged into the canonical profile. Only configure mappings after your CRM or integration has verified the identities.

## Analysis behavior

The first analysis downloads `sentence-transformers/all-MiniLM-L6-v2` into `backend/data/model-cache`. The model and embeddings run locally. HDBSCAN is provided by scikit-learn. Defaults require 2 reports to form a cluster and link repeat submissions only for the same customer ID when cosine similarity is at least `0.92` and the reports are within 30 days. These settings can be sent to `POST /api/analysis/run` (`min_cluster_size`, `duplicate_similarity_threshold`, `duplicate_window_days`).

Issue labels try the local Ollama endpoint at `OLLAMA_BASE_URL` with `OLLAMA_MODEL` (default `qwen2.5:3b`). If Ollama is unavailable, local keyword labels are used. Ollama is optional; complaint text is sent only to the configured local Ollama server, never to a hosted LLM by this code.

Each analysis records `Priority = wS·S + wF·F + wI·I`. Severity `S` maps the average supplied 1–5 values to 0–100. Missing values are excluded from the average and reduce severity coverage; `wS = 0.4 × coverage`, while the unused share is split evenly between `wF` and `wI`. With complete severity data, the weights are 40% / 30% / 30%; if all severity values are missing, frequency and impact each receive 50%. Frequency `F` maps unique reports and impact `I` maps affected customers relative to the largest issue in that run. Effective weights and severity coverage are persisted. Repeat submissions remain visible in issue evidence but do not increase unique report frequency or severity coverage. Each issue also stores mean pairwise within-cluster cosine similarity; groups below 65% are flagged for human review. This is a review signal, not an accuracy estimate. A representative labeled evaluation set is still needed to quantify real-world grouping quality. `GET /api/issues` returns the 10 highest scoring issues by default, with `total_issues` giving the full count; pass `limit` to change the page size.

## Database integration

The physical tables are `customers`, `customer_aliases`, `complaints`, `analysis_runs`, `issue_clusters`, and `issue_work_items`. The roadmap's logical names are exposed as read-only compatibility views: `clusters` (issue clusters), `complaint_clusters` (complaint-to-cluster links), `benchmark_runs` (analysis settings and results), and `issue_scores` (priority components). These views preserve existing records and are created idempotently for SQLite and Supabase PostgreSQL. Issue follow-up is keyed by normalized issue labels and survives analysis runs when labels remain stable. The issue list reports when complaint volume has grown since the latest run; run analysis to refresh groupings and scores. Missing severity is stored as medium for schema compatibility but marked as assumed and excluded from the severity score. Pre-migration records with a medium value are marked unverified because their original severity provenance cannot be recovered. The health endpoint checks a live database query and reports which adapter is active without returning connection details.
