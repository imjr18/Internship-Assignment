## Phase 1: Foundation
### Database
- [x] DB-01: Define SQLite schema for restaurants table
- [x] DB-02: Define SQLite schema for tables table
- [x] DB-03: Define SQLite schema for reservations table
- [x] DB-04: Define SQLite schema for guests table
- [x] DB-05: Define SQLite schema for waitlist table
- [x] DB-06: Implement connection pool with context manager
- [x] DB-07: Implement all read queries (availability, guest lookup, etc.)
- [x] DB-08: Implement all write queries (create/modify/cancel reservation)
- [x] DB-09: Seed 75 realistic restaurant profiles
- [x] DB-10: Write unit tests for all queries

### Embeddings
- [x] EMB-01: Install and configure sentence-transformers (all-MiniLM-L6-v2)
- [x] EMB-02: Generate embeddings for all restaurant profiles on DB seed
- [x] EMB-03: Store embeddings in FAISS index
- [x] EMB-04: Implement semantic_search(query, top_k) function
- [x] EMB-05: Write unit tests for semantic search

## Phase 2: Core Agent
### Config & Prompts
- [ ] CFG-01: Load all settings from environment variables
- [ ] CFG-02: Write production system prompt
- [ ] CFG-03: Write tool schemas in correct JSON format for Llama 3.3
- [ ] CFG-04: Implement prompt versioning

### Tool Layer
- [x] TL-01: Implement search_restaurants tool
- [x] TL-02: Implement check_availability tool
- [x] TL-03: Implement create_reservation tool
- [x] TL-04: Implement modify_reservation tool
- [x] TL-05: Implement cancel_reservation tool
- [x] TL-06: Implement get_guest_history tool
- [x] TL-07: Implement add_to_waitlist tool
- [x] TL-08: Implement escalate_to_human tool
- [x] TL-09: Implement idempotency keys on all write tools
- [x] TL-10: Write unit tests for every tool (happy path + error cases)

### MCP Server
- [ ] MCP-01: Implement JSON-RPC server with tools/list endpoint
- [ ] MCP-02: Implement tools/call endpoint with dispatch logic
- [ ] MCP-03: Implement input validation for all tool schemas
- [ ] MCP-04: Implement rate limiting (max N calls per session per minute)
- [ ] MCP-05: Implement API key authentication
- [ ] MCP-06: Write integration tests for MCP server

### Agent Core
- [x] AGT-01: Implement context_manager (conversation history, token budget)
- [x] AGT-02: Implement prompt_builder (system prompt + history + tools)
- [x] AGT-03: Implement LLM client (Groq API + streaming support)
- [x] AGT-04: Implement tool_dispatcher (parse JSON tool call, route to tool)
- [x] AGT-05: Implement main orchestrator loop
- [x] AGT-06: Implement conversation state machine
- [x] AGT-07: Implement hallucination detection layer
- [x] AGT-08: Implement prompt injection defense
- [x] AGT-09: Implement sentiment monitor
- [x] AGT-10: Write integration tests for full agent loop

## Phase 3: Recommendation Engine
- [ ] REC-01: Implement weighted scoring matrix
- [ ] REC-02: Implement cold-start fallback logic
- [ ] REC-03: Implement diversity penalty in results
- [ ] REC-04: Implement explanation generator
- [ ] REC-05: Write unit tests for recommendation logic

## Phase 4: Frontend
- [x] FE-01: Implement main Streamlit app layout
- [x] FE-02: Implement chat panel with streaming
- [x] FE-03: Implement booking summary sidebar
- [x] FE-04: Implement restaurant browser tab
- [x] FE-05: Implement debug/tool call panel (toggleable)
- [x] FE-06: Implement confirmation card UI
- [x] FE-07: Implement demo mode with preset scenarios
- [x] FE-08: Implement consent capture banner

## Phase 5: Quality & Security
- [ ] SEC-01: Implement PII detection and redaction
- [ ] SEC-02: Implement structured logging with session IDs
- [ ] SEC-03: Implement rate limiting on frontend
- [ ] SEC-04: Write adversarial prompt tests
- [ ] SEC-05: Write full evaluation dataset (20 test conversations)
- [ ] SEC-06: Performance profiling report
