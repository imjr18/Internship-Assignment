## Implementation Plan

### Guiding Principles
- No LangChain, LlamaIndex, or agent frameworks
- All agent logic hand-written in Python
- LLM inference via Groq API (default: llama-3.1-8b-instant)
- Tool calling via JSON schema, not code generation
- MCP server as a separate FastAPI process
- SQLite for structured data, FAISS for semantic search
- Streamlit for frontend

### Sub-Problem Breakdown

#### Sub-Problem 1: Data Layer
Goal: A reliable, queryable database of 75 restaurant profiles 
with full availability tracking.
Files: database/, embeddings/
Dependencies: None
Success criteria: Can query available tables for any 
restaurant/time/party_size combination in under 50ms.

#### Sub-Problem 2: Tool Layer  
Goal: 8 deterministic, tested Python functions that read/write 
the database, each with a JSON schema for LLM consumption.
Files: tools/
Dependencies: Sub-Problem 1
Success criteria: Every tool has 100% test coverage, handles 
all error cases, and returns consistent JSON.

#### Sub-Problem 3: MCP Server
Goal: A running FastAPI JSON-RPC server that exposes all tools 
to the LLM with authentication and validation.
Files: mcp_server/
Dependencies: Sub-Problem 2
Success criteria: tools/list returns correct schemas, tools/call 
correctly executes and returns results, invalid inputs are rejected 
with proper error codes.

#### Sub-Problem 4: Agent Core
Goal: A hand-written agent loop that takes a user message, 
manages multi-turn context, calls tools via MCP, and returns 
a final grounded response.
Files: agent/
Dependencies: Sub-Problem 3
Success criteria: Agent correctly handles 20 test conversations, 
never hallucinates availability, correctly escalates when needed.

#### Sub-Problem 5: Recommendation Engine
Goal: A scoring system that ranks restaurants by multi-factor 
relevance to user intent and generates transparent explanations.
Files: tools/recommendations.py, embeddings/
Dependencies: Sub-Problem 1
Success criteria: Recommendations are diverse, correctly filtered 
by hard constraints, and include specific explanations citing 
database fields.

#### Sub-Problem 6: Frontend
Goal: A Streamlit UI with streaming chat, booking summary, 
restaurant browser, and debug panel.
Files: frontend/
Dependencies: Sub-Problem 4, Sub-Problem 5
Success criteria: Full conversation flow works end-to-end 
in the UI, streaming works, booking confirmation is displayed.

### Technology Stack
- Python 3.11+
- Groq API (default: llama-3.1-8b-instant) for LLM inference
- FastAPI for MCP server
- SQLite + aiosqlite for database
- FAISS + sentence-transformers for semantic search
- Streamlit for frontend
- pytest for testing
- python-dotenv for config
- structlog for logging

### Environment Variables Required
GROQ_API_KEY=
MCP_SERVER_URL=http://127.0.0.1:8100/mcp
MCP_API_KEY=
DATABASE_PATH=./goodfoods.db
FAISS_INDEX_PATH=./embeddings/restaurant_index.faiss
LOG_LEVEL=INFO
ENVIRONMENT=development

---
### Self-Check Answers

1. **Does every file in the structure have a placeholder with a docstring? List any missing ones.**
   Yes, every `.py` file generated in the structure has a module-level docstring detailing its responsibility and containing code comments for functions to be implemented. No missing ones.

2. **Does TASK_CHECKLIST.md have at least 50 checklist items? Count them and report the number.**
   Yes, the checklist contains exactly 64 items across 5 phases.

3. **Does every sub-problem in the implementation plan have: a goal, files, dependencies, and success criteria? Check each one.**
   Yes, Sub-Problems 1 through 6 all strictly define a Goal, Files, Dependencies, and Success criteria as verified above.

4. **Are all environment variables referenced in any file also present in .env.example? Cross-reference and list any gaps.**
   Variables referenced: `GROQ_API_KEY`, `MCP_SERVER_URL`, `MCP_API_KEY`, `DATABASE_PATH`, `FAISS_INDEX_PATH`, `LOG_LEVEL`, `ENVIRONMENT`. All 7 variables are provided in `.env.example`. No gaps exist.

5. **Does requirements.txt include every library mentioned anywhere in the implementation plan? List any missing ones.**
   Yes, all libraries mentioned in the implementation plan (`groq`, `fastapi`, `aiosqlite`, `faiss-cpu`, `sentence-transformers`, `streamlit`, `pytest`, `python-dotenv`, `structlog`) are included in `requirements.txt` with their requested exact versions, alongside explicitly requested ones (`uvicorn`, `pytest-asyncio`, `httpx`, `pydantic`). No missing ones.
