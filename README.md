# GoodFoods AI Reservation Concierge

End-to-end restaurant reservation assistant with:
- Next.js frontend (`frontend_next/`)
- FastAPI backend + MCP server (`mcp_server/`)
- Hand-written Python orchestrator (`agent/`)
- Deterministic booking tools (`tools/`)
- SQLite + FAISS data stack (`database/`, `embeddings/`)
- Extensive reliability and edge-case tests (`tests/`)

## Evaluator Quick Path

Review these artifacts in this order:

1. Business strategy and use-case design  
   [`docs/GoodFoods_Business_Strategy_Use_Case.pdf`](docs/GoodFoods_Business_Strategy_Use_Case.pdf)
2. Technical design and prompt-engineering rationale  
   [`docs/GoodFoods_Technical_Design_Engineering.pdf`](docs/GoodFoods_Technical_Design_Engineering.pdf)
3. Exact setup/run flow for evaluation  
   [`docs/evaluator_setup.md`](docs/evaluator_setup.md)
4. Structured conversation screenshot evidence  
   [`docs/assets/journey_sequences/INDEX.md`](docs/assets/journey_sequences/INDEX.md)

## Architecture Snapshot

- `frontend_next` streams chat to backend (`POST /chat`) and polls booking context (`GET /booking-state/{session_id}`).
- `mcp_server.server` exposes:
  - JSON-RPC MCP endpoint: `POST /mcp` (`initialize`, `tools/list`, `tools/call`)
  - Frontend endpoints: `POST /chat`, `GET /restaurants`, `GET /booking-state/{session_id}`, `GET /health`
- `agent.orchestrator` runs the multi-turn control loop and calls tools via MCP with direct-call fallback.
- Tool truth is grounded in deterministic Python functions:
  - `search_restaurants`
  - `check_availability`
  - `create_reservation`
  - `modify_reservation`
  - `cancel_reservation`
  - `get_guest_history`
  - `add_to_waitlist`
  - `escalate_to_human`

## Repository Map

| Area | Path | Purpose |
|---|---|---|
| Business deliverable | `docs/GoodFoods_Business_Strategy_Use_Case.pdf` | Submission-grade strategy and use-case writeup |
| Technical deliverable | `docs/GoodFoods_Technical_Design_Engineering.pdf` | Submission-grade architecture and prompt-engineering writeup |
| Evaluator runbook | `docs/evaluator_setup.md` | Setup, run, validation, troubleshooting |
| Conversation evidence | `docs/assets/journey_sequences/` | Full turn-by-turn screenshots for standard and edge journeys |
| Backend API + MCP | `mcp_server/` | FastAPI app and JSON-RPC dispatch |
| Agent orchestration | `agent/` | Context, prompting, LLM client, tool dispatch |
| Deterministic tools | `tools/` | Reservation/search/availability/waitlist/escalation logic |
| Persistence layer | `database/` | SQLite schema, queries, seed logic (75 restaurants) |
| Semantic search | `embeddings/` | Sentence-transformers + FAISS index logic |
| Primary frontend | `frontend_next/` | Next.js evaluator interface |
| Optional alt UI | `frontend/` | Streamlit interface |
| Automated tests | `tests/` | Unit, integration, regression, brutal edge-case coverage |

## Setup and Run (Fast Path)

From repo root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cd frontend_next
npm install
cd ..
```

Create `.env` from `.env.example`, then run backend:

```powershell
python -m uvicorn mcp_server.server:app --host 127.0.0.1 --port 8100
```

In a second terminal:

```powershell
cd frontend_next
npm run dev
```

Open:
- Frontend: `http://localhost:3000`
- Backend health: `http://127.0.0.1:8100/health`

## Verified Validation Commands

Run from repo root:

```powershell
pytest -q
```

Run from `frontend_next/`:

```powershell
npm run build
```

Current local result (2026-03-06): backend tests pass (`153 passed, 17 skipped`), frontend production build succeeds.

## Screenshot and Demo Assets

- Primary evidence index: [`docs/assets/journey_sequences/INDEX.md`](docs/assets/journey_sequences/INDEX.md)

## Assumptions and Limitations

- Live conversational quality depends on Groq quota/rate limits (`GROQ_API_KEY`).
- External POS/CRM integrations are not included; this is a local simulation stack.
- `tests/test_recommendations.py` and `tests/test_validators.py` are placeholders and do not currently add assertions.
- `frontend/v0/` and some handoff files are legacy artifacts; evaluator flow should use `frontend_next/`, `docs/evaluator_setup.md`, and the PDF deliverables.
