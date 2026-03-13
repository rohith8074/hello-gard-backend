# HelloGuard Voice AI — Backend

FastAPI backend for the HelloGuard Voice AI platform. Handles voice session orchestration, real-time transcription, post-call intelligence, and all dashboard analytics.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Framework | FastAPI (async Python) |
| Server | Uvicorn (ASGI) |
| Database | MongoDB via Motor (async driver) |
| AI / Voice | Lyzr AI (agents, LiveKit sessions) |
| Auth | JWT (python-jose) + bcrypt |
| HTTP Client | httpx |
| Telephony | Twilio (webhook ready) |
| Speech | Deepgram SDK, ElevenLabs |

---

## Project Structure

```
gard-backend/
├── app/
│   ├── main.py              # App init, CORS, startup/shutdown hooks
│   ├── config.py            # Settings loaded from .env
│   ├── database.py          # MongoDB Motor async client
│   ├── routes/
│   │   ├── auth.py          # Register, login, current user
│   │   ├── admin.py         # User approval, roles, suspension
│   │   ├── agents.py        # Chat with Lyzr agents
│   │   ├── session.py       # LiveKit session start/end/poll
│   │   ├── transcripts.py   # Transcript fetch and Lyzr sync
│   │   ├── post_call.py     # Post-call analysis, auto-escalations, sales leads
│   │   ├── dashboard.py     # All dashboard metrics and data endpoints
│   │   └── websocket.py     # WebSocket proxy (browser ↔ Lyzr voice)
│   ├── middleware/
│   │   └── auth_deps.py     # JWT validation, role guards
│   └── lib/
│       └── agents.py        # LyzrAgentManager (API wrapper)
├── agent_prompts/           # Markdown prompts for all GARD sub-agents
├── requirements.txt
└── .env
```

---

## Setup

### 1. Install dependencies

```bash
cd gard-backend
pip install -r requirements.txt
```

### 2. Configure environment

Copy `.env` and fill in your values:

```bash
cp .env .env.local
```

| Variable | Description |
|----------|-------------|
| `LYZR_API_KEY` | Lyzr platform API key |
| `LYZR_Managerial_Agent_ID` | Lyzr agent ID for voice sessions |
| `LYZR_POST_CALL_AGENT_ID` | Lyzr agent ID for post-call analysis |
| `LYZR_AGENT_URL` | Lyzr chat inference endpoint |
| `LYZR_VOICE_BASE` | Lyzr LiveKit voice API base URL |
| `LYZR_CHAT_BASE` | Lyzr chat API base URL |
| `Mongodb_URI` | MongoDB connection string |
| `Databse_name` | MongoDB database name (default: `HelloGard`) |
| `JWT_SECRET_KEY` | Secret key for signing JWT tokens |
| `CORS_ORIGINS` | Comma-separated allowed frontend origins |
| `ADMIN_USERNAME` | Default admin username (seeded on startup) |
| `ADMIN_NAME` | Default admin display name |
| `ADMIN_PASSWORD` | Default admin password |

### 3. Run the server

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

- API: `http://localhost:8000`
- Swagger docs: `http://localhost:8000/docs`
- Health check: `GET /health`

On first startup, the default admin account is seeded automatically using the credentials in `.env`.

---

## API Reference

### Auth — `/api/v1/auth`

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/auth/register` | Register a new operator (requires admin approval) |
| POST | `/auth/login` | Login — returns a JWT access token |
| GET | `/auth/me` | Get the current authenticated user |

### Admin — `/api/v1/admin`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/admin/users` | List all users |
| PATCH | `/admin/users/{user_id}/approve` | Approve a pending user |
| PATCH | `/admin/users/{user_id}/role` | Toggle admin / operator role |
| PATCH | `/admin/users/{user_id}/suspend` | Suspend or reactivate a user |
| DELETE | `/admin/users/{user_id}/reject` | Reject and remove a pending user |

### Session — `/api/v1/session`

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/session/start` | Start a Lyzr LiveKit voice session |
| POST | `/session/end` | End session and save transcript |
| GET | `/session/active-count` | Count currently active sessions |
| GET | `/session/transcript/{session_id}` | Poll live transcript during a call |

### Transcripts — `/api/v1`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/transcripts` | List all transcripts (web + phone) |
| POST | `/transcripts/sync` | Sync transcripts from Lyzr API |
| GET | `/transcripts/lyzr` | Paginated Lyzr phone call transcripts |
| GET | `/health/mongodb` | MongoDB connection health check |

### Post-Call — `/api/v1`

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/post-call/{session_id}` | Run AI post-call analysis; auto-creates escalation tickets and sales leads |

### Dashboard — `/api/v1/dashboard`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/dashboard/active-calls` | Active call count |
| GET | `/dashboard/metrics` | Daily rolling performance metrics |
| GET | `/dashboard/summary` | Aggregated KPIs (FCR, containment, CSAT) |
| GET | `/dashboard/calls` | Paginated call list with filters |
| GET | `/dashboard/calls/{call_id}` | Call detail including transcript |
| GET | `/dashboard/calls/{call_id}/audio` | Audio playback for a call |
| GET | `/dashboard/rag-metrics` | Knowledge base retrieval metrics |
| GET | `/dashboard/escalations` | Escalation ticket list |
| GET | `/dashboard/sales-leads` | Detected sales opportunity list |
| GET | `/dashboard/customers` | Customer profiles with search |
| GET | `/dashboard/customers/{user_id}` | Customer detail and call history |
| GET | `/dashboard/customers/insights` | Customer sentiment and behavior analytics |
| GET | `/dashboard/events` | Priority event feed |
| GET | `/dashboard/calendar` | Monthly call activity calendar |
| POST | `/dashboard/refresh` | Trigger async dashboard data refresh |
| GET | `/dashboard/refresh/status/{job_id}` | Poll refresh job status |

### Fleet — `/api/v1/fleet`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/fleet/robots` | Live fleet status (online / offline / error) |
| GET | `/fleet/maintenance-schedule` | Maintenance events by robot model |

### WebSocket — `/ws`

| Endpoint | Description |
|----------|-------------|
| `/ws/web?sessionId={id}&lyzrWs={url}` | Transparent proxy — bridges browser audio to Lyzr LiveKit |

---

## Database Collections

| Collection | Contents |
|------------|----------|
| `login` | Users, roles (admin/operator), approval status, session quotas |
| `sessions` | Active and completed voice sessions |
| `transcripts` | Web call transcripts (captured by LiveKit) |
| `lyzr_transcripts` | Phone call transcripts synced from Lyzr |
| `calls` | Post-call analysis results |
| `call_audios` | Audio recordings (Binary BSON) |
| `interaction_logs` | Real-time message turn logs |
| `escalation_tickets` | Auto-created escalation tickets |
| `sales_leads` | Detected sales opportunities |
| `dashboard_metrics` | Daily rolling metrics (upserted per day) |
| `security_events` | Priority event feed entries |

---

## Agent Prompts

All GARD sub-agent prompts live in `../agent_prompts/`:

| File | Agent |
|------|-------|
| `GARD_Manager_Agent.md` | Primary voice agent — orchestrates all sub-agents |
| `Post_Call_Intelligence_Agent.md` | Silent background agent — analyzes every transcript |
| `Troubleshooting_Agent.md` | Robot malfunction diagnosis |
| `Maintenance_Agent.md` | Routine maintenance guidance |
| `Product_Knowledge_Agent.md` | Product specs and how-to |
| `Fleet_Intelligence_Agent.md` | Fleet status queries |
| `Sales_Demo_Agent.md` | Pricing, ROI, demo requests |
| `Scheduling_Agent.md` | Technician and demo booking |
| `Ticket_Escalation_Agent.md` | Escalation ticket creation |
| `Cybersecurity_Advisory_Agent.md` | Security concern handling |
