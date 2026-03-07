# GoodFoods AI Reservation Concierge

This repository contains an end-to-end conversational reservation system built for the GoodFoods AI Agent Challenge.
It combines business strategy deliverables with a working product implementation, so an evaluator can review both:
- the thinking (use case, ROI, expansion, positioning)
- the engineering (agent loop, tool calling, backend/frontend behavior, test coverage)

## What Is Implemented

- A Next.js frontend experience for browsing, chat, and confirmation views (`frontend_next/`)
- A FastAPI backend and MCP-style tool endpoint (`mcp_server/`)
- A custom Python orchestration loop with explicit state handling (`agent/`)
- Deterministic operational tools for search/availability/reservation workflows (`tools/`)
- SQLite persistence + FAISS-based semantic retrieval (`database/`, `embeddings/`)
- Automated reliability and regression test coverage (`tests/`)

## How To Evaluate This Submission

Use this sequence for the quickest complete review:

1. Understand business framing and value:
   [`docs/GoodFoods_Business_Strategy_Use_Case.pdf`](docs/GoodFoods_Business_Strategy_Use_Case.pdf)
2. Understand technical design and prompt approach:
   [`docs/GoodFoods_Technical_Design_Engineering.pdf`](docs/GoodFoods_Technical_Design_Engineering.pdf)
3. Run the project exactly as intended:
   [`docs/evaluator_setup.md`](docs/evaluator_setup.md)
4. Review scenario evidence:
   [`docs/assets/journey_sequences/INDEX.md`](docs/assets/journey_sequences/INDEX.md)
5. Watch end-to-end demonstration:
   [`docs/assets/Videos/Demo Video.mp4`](docs/assets/Videos/Demo%20Video.mp4)

## System At A Glance

High-level runtime flow:
- Frontend sends chat input to backend (`POST /chat`)
- Agent orchestrator interprets intent and chooses tool calls
- Backend tools execute deterministic actions (search, hold, create, modify, cancel)
- Frontend reads live session state (`GET /booking-state/{session_id}`)

Backend endpoints exposed:
- `POST /mcp`
- `POST /chat`
- `GET /restaurants`
- `GET /booking-state/{session_id}`
- `GET /health`

## Repository Orientation

Key directories and what they are for:
- A Next.js frontend (`frontend_next/`)
- A FastAPI backend + MCP endpoint (`mcp_server/`)
- A custom Python orchestration loop (`agent/`)
- Deterministic booking/search tools (`tools/`)
- SQLite + FAISS data stack (`database/`, `embeddings/`)
- Automated test coverage (`tests/`)

## Quick Run Pointer

For environment setup, startup commands, and troubleshooting, follow:
- [`docs/evaluator_setup.md`](docs/evaluator_setup.md)

In short:
- start backend on `127.0.0.1:8100`
- start frontend on `localhost:3000`
- verify health on `GET /health`

## Detailed Materials (Source Of Truth)

- Business strategy, metrics, stakeholders, expansion:  
  [`docs/GoodFoods_Business_Strategy_Use_Case.pdf`](docs/GoodFoods_Business_Strategy_Use_Case.pdf)
- Technical architecture, prompt engineering, implementation details:  
  [`docs/GoodFoods_Technical_Design_Engineering.pdf`](docs/GoodFoods_Technical_Design_Engineering.pdf)
- Setup, execution, and validation instructions:  
  [`docs/evaluator_setup.md`](docs/evaluator_setup.md)
- Structured scenario and edge-case screenshots:  
  [`docs/assets/journey_sequences/INDEX.md`](docs/assets/journey_sequences/INDEX.md)
- Demo recording:  
  [`docs/assets/Videos/Demo Video.mp4`](docs/assets/Videos/Demo%20Video.mp4)
