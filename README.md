# ITSM RCA Agent

A fully-local Root-Cause-Analysis agent for ITSM tickets. Pulls ticket data from a mock ITSM **through MCP**, retrieves grounding context from a 10-document knowledge base via RAG, and asks an **offline LLM (Ollama)** to produce a Markdown RCA report per ticket.

Five-node LangGraph pipeline. Five containers. One `docker compose up`.

## Architecture (one-line view)

```
ITSM mock ──► MCP server ──► Agent ─┬─► RAG (Chroma and E5)
                                    └─► LLM (Ollama qwen2.5:3b)
                                    └─► reports/<ticket>.md
```

Full design, technical decisions, and explicit non-goals live under [`docs/`](./docs):

- [`docs/architecture.md`](./docs/architecture.md) system design, component diagram, sequence diagram, layer breakdown
- [`docs/tech-decisions.md`](./docs/tech-decisions.md) every choice and why
- [`docs/assumptions.md`](./docs/assumptions.md) assumptions and explicit non-goals

## Prerequisites

- Docker Desktop (Windows / macOS) or Docker Engine and Compose plugin (Linux). **No GPU required.**
- ~6 GB free disk for the Ollama model, embedding model and base images.
- First run downloads `qwen2.5:3b` (~2 GB) and `intfloat/multilingual-e5-small` (~120 MB). All subsequent runs are fully offline.

## Quick start

```bash
# Bring the platform up (first run pulls the model ~2-3 min)
docker compose up --build -d

# Wait for readiness
curl http://localhost:8002/ready
# {"ready":true,"checks":[{"name":"ollama","ok":true},{"name":"mcp","ok":true}]}

# List the open tickets
curl http://localhost:8002/tickets

# Submit one RCA returns 202 Accepted and job_id
curl -X POST http://localhost:8002/rca/INC-1001
# {"job_id":"<uuid>","ticket_id":"INC-1001","status":"queued"}

# Poll until status == "succeeded" (~110 s on CPU)
curl http://localhost:8002/jobs/<job_id>

# Fetch the rendered Markdown report
curl http://localhost:8002/reports/INC-1001
```

The report is also written to `reports/INC-1001.md` on the host (volume-mounted).

## Batch end-to-end (PowerShell)

```powershell
# Submits all 8 sample tickets, polls every 15 s with a live status table.
.\e2e_batch.ps1
```

Total wall-clock ~14 min on CPU (Ollama serializes inside the agent `Semaphore=1`).

## REST surface

| Endpoint | Method | Purpose                                 |
|---|---|-----------------------------------------|
| `/health` | GET | Liveness                                |
| `/ready` | GET | Readiness probes Ollama and MCP         |
| `/tickets` | GET | List open ticket ids                    |
| `/rca/{ticket_id}` | POST | Enqueue an RCA job → `202` and `job_id` |
| `/jobs/{job_id}` | GET | Poll job status                         |
| `/reports/{ticket_id}` | GET | Fetch the rendered Markdown             |
| `/docs` | GET | Swagger UI                              |

Open `http://localhost:8002/docs` for the interactive Swagger.

## What the agent does, step by step

For each ticket the LangGraph pipeline runs five nodes:

1. **fetch_ticket** calls `get_ticket`, `get_ticket_comments`, `get_ticket_history` over MCP.
2. **retrieve** embeds the ticket text and pulls the top-K runbook chunks from ChromaDB.
3. **analyze** first LLM call: produces the *Root Cause Analysis* section.
4. **propose_solution** second LLM call, prompted with the analysis above and the same KB chunks: produces the *Remediation* section.
5. **write_report** assembles the full Markdown RCA at `reports/<TICKET_ID>.md`.

Sample reports under `reports/` show the output format without running the stack.

## Project layout

```
itsm-agent-example/
├── docker-compose.yml         # 5 services and 3 named volumes
├── e2e_batch.ps1              # Batch E2E helper (8 tickets, live status table)
├── docs/
│   ├── architecture.md
│   ├── tech-decisions.md
│   └── assumptions.md
├── itsm_mock/                 # FastAPI in-memory ITSM (8 sample tickets)
├── mcp_server/                # FastMCP server (streamable-HTTP) 4 tools
├── kb/                        # 10 runbook Markdown files (the RAG corpus)
├── agent/                     # DDD / n-tier agent pipeline, ports, adapters, REST
│   ├── pyproject.toml
│   ├── Dockerfile
│   ├── src/itsm_agent/
│   │   ├── domain/            # pure model, 5 ports and 1 service
│   │   ├── application/       # DTO, use cases, LangGraph pipeline, prompts and formatting
│   │   ├── infrastructure/    # 4 port adapters (llm, rag, mcp, reports)
│   │   ├── composition/       # AgentConfig, AgentBuilder and AgentApplication façade
│   │   └── interfaces/        # CLI, REST and JobStore
│   └── tests/                 # 34 tests, ~7 s, port-level fakes
├── reports/                   # Generated RCAs (one per ticket)
└── .github/workflows/ci.yml   # ruff and pytest on push/PR
```

## Configuration

All env vars are optional defaults work out of the box. Override in `docker-compose.yml` or your shell.

| Env var | Default | What it controls |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://ollama:11434` | LLM endpoint |
| `OLLAMA_MODEL` | `qwen2.5:3b` | Model name (must be pullable) |
| `OLLAMA_TEMPERATURE` | `0.2` | LLM temperature |
| `OLLAMA_NUM_CTX` | `8192` | LLM context window |
| `MCP_SERVER_URL` | `http://mcp-server:8001/mcp` | MCP endpoint |
| `KB_DIR` | `/app/kb` | Knowledge-base directory |
| `CHROMA_PERSIST_DIR` | `/app/chroma_data` | Chroma persistence directory |
| `CHROMA_COLLECTION` | `itsm_kb` | Chroma collection name |
| `EMBEDDING_MODEL` | `intfloat/multilingual-e5-small` | Sentence-transformers model |
| `TOP_K` | `4` | RAG top-K |
| `REPORTS_DIR` | `/app/reports` | Output directory |
| `LOG_LEVEL` | `INFO` | Python logging level |

## Changing the model

```bash
OLLAMA_MODEL=qwen2.5:7b docker compose up ollama-init
docker compose restart agent
```

`qwen2.5:7b` produces noticeably better RCAs but takes ~2× longer on CPU. `qwen2.5:3b` is the default for portability.

## Inspecting components individually

```bash
# Mock ITSM REST
curl http://localhost:8000/tickets
curl http://localhost:8000/tickets/INC-1001

# MCP server (streamable-HTTP) bare GET returns 405/406, that's expected
curl -i http://localhost:8001/mcp

# Ollama
curl http://localhost:11434/api/tags

# Agent live logs (LLM output, pipeline progress)
docker compose logs -f agent
```

## Running the tests

Tests use port-level fakes no Ollama, Chroma, or MCP needed.

```bash
# Inside the agent image (Linux, where ChromaDB wheels resolve cleanly):
docker run --rm \
  -v "$PWD/agent/src:/app/src" \
  -v "$PWD/agent/tests:/app/tests" \
  -v "$PWD/agent/pyproject.toml:/app/pyproject.toml" \
  --entrypoint bash itsm-agent-example-agent:latest \
  -c "pip install -q -e '/app[dev]' && cd /app && python -m pytest tests/ -ra"
```

Expected: **34 passed in ~7 s**.

CI (GitHub Actions) runs `ruff check`, `ruff format --check` and `pytest` on every push to `main` and every pull request.

## Stopping and cleaning up

```bash
docker compose down              # stop services, keep volumes (model cache survives)
docker compose down -v           # also drop volumes (forces re-pull on next run)
```

## Performance notes

- **CPU-only baseline:** ~110 s/ticket (i5-1155G7, no GPU, qwen2.5:3b). Two LLM calls (analyze and propose) account for ~95 % of wall-clock time.
- **Batch of 8:** ~14 min, serialized inside the agent (Ollama itself serializes; parallelism would only thrash).
- **GPU host (e.g. RTX 3060):** ~10–15 s/ticket. The architecture does not need to change.
