# Evaluator Setup Guide

This guide is the exact setup path for evaluating the GoodFoods application locally. It is written for the repository in its current state, including the Python backend, the Next.js frontend, the optional Streamlit UI, and the backend test suite.

## 1. Prerequisites

- Python 3.11 or newer
- Node.js 20 or newer
- npm 10 or newer
- A Groq API key for full conversational testing

## 2. Install dependencies

From the project root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Install frontend dependencies:

```bash
cd frontend_next
npm install
cd ..
```

## 3. Create environment files

Create a root `.env` file from `.env.example`.

Recommended root `.env`:

```env
GROQ_API_KEY=your_groq_key_here
GROQ_MODEL=llama-3.1-8b-instant
LLM_MAX_TOKENS=450
LLM_TEMPERATURE=0.2
MCP_SERVER_URL=http://127.0.0.1:8100/mcp
MCP_API_KEY=
MCP_TIMEOUT_SECONDS=8
MCP_COOLDOWN_SECONDS=15
DATABASE_PATH=./goodfoods.db
FAISS_INDEX_PATH=./embeddings/restaurant_index.faiss
MAX_CONTEXT_TOKENS=3200
MAX_TOOL_ROUNDS=5
LOG_LEVEL=INFO
ENVIRONMENT=development
```

Optional frontend environment:

Create `frontend_next/.env.local` only if you want to override the backend URL. The frontend defaults to `http://localhost:8100`.

```env
NEXT_PUBLIC_API_URL=http://localhost:8100
```

## 4. Start the backend

From the project root:

```bash
python -m uvicorn mcp_server.server:app --host 127.0.0.1 --port 8100
```

What happens on startup:

- the SQLite database is initialized or reused
- seed data is loaded if needed
- semantic search assets are warmed
- the FastAPI server exposes both the MCP endpoint and frontend-facing endpoints

Health check:

Open `http://127.0.0.1:8100/health`

Expected result:

- JSON with `status: healthy`
- server name
- version
- tool count

## 5. Start the Next.js frontend

In a second terminal:

```bash
cd frontend_next
npm run dev
```

Open:

`http://localhost:3000`

The frontend communicates with:

- `POST /chat`
- `GET /restaurants`
- `GET /booking-state/{session_id}`

## 6. Optional Streamlit UI

The repository also includes a Streamlit-based UI for quick testing.

```bash
streamlit run frontend/app.py
```

This UI can auto-start the MCP server if it is not already running, but the primary evaluation surface should be the Next.js app.

## 7. Recommended evaluator test flow

### Flow A: standard reservation

Use the Next.js UI and try:

`I need an Italian restaurant for 4 people this Friday around 8 pm. One guest needs gluten-free options.`

Evaluate:

- whether the system asks only for missing details
- whether it uses search before making claims
- whether it offers grounded restaurant options
- whether it checks availability before promising a slot

### Flow B: fully booked or alternate time

Ask for an unusually constrained reservation or change the time after options are shown.

Evaluate:

- whether the assistant offers alternate times cleanly
- whether waitlist behavior is sensible
- whether the wording stays natural instead of leaking raw timestamps or tool output

### Flow C: modification or cancellation

After creating a reservation, attempt a change or cancellation.

Evaluate:

- confirmation code handling
- state continuity
- operational correctness of modify and cancel paths

### Flow D: escalation / safety

Try:

`I am furious about your service and I want a manager right now.`

Evaluate:

- whether the assistant de-escalates and routes appropriately
- whether it avoids arguing
- whether it stops treating the interaction like a normal booking flow

## 8. Run validation checks

### Backend tests

From the project root:

```bash
pytest -q
```

### Frontend production build

```bash
cd frontend_next
npm run build
```

### Optional targeted backend checks

```bash
pytest tests/test_regressions.py -q
pytest tests/test_agent_loop.py -q
pytest tests/test_brutal.py -q
```

Notes:

- `tests/test_brutal.py` includes stress and integration scenarios and may take longer.
- Live LLM tests are skipped when `GROQ_API_KEY` is not present.

## 9. Troubleshooting

### Problem: the UI says the AI service is busy

Cause:

- Groq quota exhaustion or rate limiting

What to do:

- wait for the quota window to reset
- reduce repeated long prompts
- use a different Groq key or higher service tier

### Problem: backend is running but chat fails immediately

Check:

- `GROQ_API_KEY` is present
- `http://127.0.0.1:8100/health` returns healthy
- the frontend is pointed to `http://localhost:8100` or `http://127.0.0.1:8100`

### Problem: recommendations are slow on first request

Cause:

- first-time model and embedding warmup

What to do:

- allow the backend startup to complete before opening the UI
- retry the first semantic search once assets are warmed

### Problem: evaluator sees a Next.js red overlay for a backend issue

Status:

- the frontend was patched to downgrade expected stream errors from `console.error` to `console.warn` in development for quota-style failures

If it still happens:

- stop the frontend
- delete `frontend_next/.next`
- restart `npm run dev`

## 10. What the evaluator should expect to work

- restaurant browsing
- conversational recommendation search
- availability checks
- reservation creation
- modification and cancellation flows
- waitlist path
- guest history lookup when identity details are provided
- human escalation path
- backend test suite
- frontend build

The two biggest external constraints are Groq quota availability and the absence of production POS/CRM integrations, both of which are documented elsewhere in this repository.
