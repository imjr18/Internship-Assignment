# GoodFoods Reservation Management System

A production-grade AI reservation management system built in Python without external agent frameworks.

## Setup
1. Create a `.env` file from `.env.example`.
2. Install dependencies: `pip install -r requirements.txt`.
3. Follow the `IMPLEMENTATION_PLAN.md` for phases.

## Running the Full Stack

### 1. Start the MCP + API Server
```bash
uvicorn mcp_server.server:app --port 8100 --reload
```

### 2. Option A: Streamlit Frontend (simple)
```bash
streamlit run frontend/app.py
```

### 2. Option B: Next.js Frontend (production UI)
```bash
cd frontend_next
npm install
npm run dev
# Open http://localhost:3000
```

