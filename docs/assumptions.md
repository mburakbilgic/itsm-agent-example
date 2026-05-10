# Assumptions and Non-Goals

This document lists the assumptions behind the design and what is not included. Each item is a deliberate trade-off. Reviewers should be able to see where to raise questions and where choices were made intentionally.

## Environment assumptions

1. **Local-only execution.** No external network calls during inference. The Ollama image and the embedding model are downloaded once at first boot; everything afterwards runs offline.
2. **The system is designed for CPU-only hardware.** On an Intel i5-1155G7 without a GPU, it takes about 110 seconds per ticket when running `qwen2.5:3b`. Each ticket requires two LLM calls, each taking about 50 to 60 seconds, which makes up most of the processing time. Using a GPU like an RTX 3060 reduces this to about 10-15 seconds per ticket, but the system's design remains the same.
3. **Docker Desktop or Docker Engine with the Compose plugin is required.** Five services are managed together, and while you can run them outside Compose, this is not supported.
4. **~6 GB of free disk** for the Ollama model, the embedding model, and the base images.
5. **The knowledge base is stored in `kb/*.md`** and contains about 10 documents. If you edit a file, its fingerprint changes and the system re-indexes it the next time it starts. The agent updates with new content through re-indexing, not while running.
6. **The mock ITSM is just a placeholder.** It provides eight sample tickets from JSON files. Its purpose is only to show how the MCP-fed flow works.

## Hardware sizing: practical notes

| Resource | Minimum | Comfortable | Reason |
|---|---|---|---|
| RAM | 8 GB | 16 GB | Ollama (~3 GB), Chroma and embedder (~1 GB), Python services (~1 GB) |
| Disk | 6 GB free | 10 GB | Model weights, image layers, reports |
| CPU | 2 cores | 4 or more cores | Ollama saturates a core during inference |
| GPU | Not required | Helpful | ~10× speedup for the LLM calls; nothing else benefits |

## Ticket volume and load

- The system is meant for one user and low ticket volume. The goal is to provide a root cause analysis for each ticket, not to handle large numbers of requests.
- `JobStore.Semaphore=1` makes sure only one job runs at a time. You can submit jobs in parallel, but they will be queued instead of being rejected.
- If many POST requests come in at once, the in-memory registry limits them to 500 records, removing the oldest first. There is no other admission control.

## Data assumptions

- Tickets, comments, and history are all stored as strings, including timestamps in the `at` fields, at the MCP boundary. The `Ticket.created_at`, `Comment.at`, and `HistoryEvent.at` fields remain as strings and are not converted to `datetime`. The agent does not process times; the LLM handles that.
- The `affected_users` field can be either an integer or a string. The MCP adapter passes along whatever it receives, and later code formats it as text. In a real backend, this could be standardised at the adapter level.
- `Priority` is mapped to `P1`, `P2`, `P3`, or `P4`. If an unexpected value appears, it defaults to `UNKNOWN` and logs a warning. The `is_high_priority` function returns `True` only for `P1` and `P2`.
- Knowledge base chunks are returned with a cosine-style similarity score between `0` and `1`. This is calculated from the L2 distance over normalised vectors as `1.0` minus half the distance.

## Security posture

The system is intended for authorized local use in a case study. Some production-level security features are not included on purpose. The following items are in scope:

- **Path traversal hardening on `/reports/{ticket_id}`**: input regex and `is_relative_to(out_dir)` check.
- **`kb/` mounted read-only**: the agent cannot corrupt its source corpus.
- **Outbound HTTP timeouts**: Ollama and MCP probes use `httpx` with explicit 5 s timeouts.
- **`raise_for_status()` on every MCP outbound call**: failures surface as exceptions rather than silent zero-row responses.

What is out of scope (see "Non-goals" below for the full list): authentication, authorisation, TLS, rate limiting, audit logging, and secret management.

## Non-goals (out of scope, on purpose)

These choices are important in production but would add unnecessary complexity for an interview case study. Each one is a deliberate trade-off, not a mistake.

### Process / release

- No semantic versioning, no `__version__`, no CHANGELOG. This repo is a snapshot, not a released artefact.
- No release pipeline. CI runs lint and tests on push/PR; that is the entire promotion process.
- No GitHub release tags. Same reason.

### Multi-user / multi-tenant

- No authentication or authorisation. All endpoints are open; the trust boundary is the host machine.
- No per-user state, no rate limiting, no quotas. Single user, low volume.
- No audit log of who triggered which RCA.

### High availability / scale

- No retry, no DLQ. A failed RCA writes an error into the job record and stops; the operator can re-POST.
- No persistence of job records. Restart loses job history; the RCA artefacts on disk under `reports/` survive.
- No horizontal scaling story. `JobStore` is process-local; running two agent containers would not share state.
- No external observability stack (Prometheus, OpenTelemetry, structured JSON logs). Plain Python logging is enough to diagnose a case-sized run.

### LLM / RAG governance

- Hardcoded prompt strings. No prompt registry, no A/B variant testing, no prompt versioning.
- No evaluation harness. Quality is judged by reading the eight sample reports.
- No RAG re-ranker, no hybrid search. Top-K cosine over E5 embeddings is the entire retrieval strategy.
- No streaming LLM output. The async-job pattern returns the final text only.
- No guardrails on output content beyond what the system prompt instructs.

### Container / deployment hardening

- No multi-stage Dockerfile. Build dependencies (`build-essential`) ship in the runtime image. Image size is not optimized.
- No non-root user inside the container. Root is the default.
- No image scanning (Trivy, Snyk).
- No SBOM, no signed images.

### Integration tests

- There are no unit tests for adapters. `OllamaLlmService`, `McpTicketRepository`, and `ChromaKnowledgeRepository` are tested end-to-end using the real stack with `e2e_batch.ps1`, but not with separate unit tests. Port-level fakes provide the same contract-level coverage.
- No load tests, no chaos tests.

## Things that look like assumptions but are decisions

Some items may seem like assumptions that a reviewer should question, but they are actually explicit decisions. The reasons for these choices are explained in [`tech-decisions.md`](./tech-decisions.md):

- Two LLM calls per ticket instead of one combined call. → "Two LLM calls per ticket: analyse, then propose."
- `Semaphore=1` instead of parallel job execution. → "`Semaphore=1` for job execution."
- Sync `KnowledgeRepository` instead of async. → "Async ports for I/O, sync ports for CPU/local."
- Stateless per-call MCP session instead of a pooled long-lived session. → "Stateless agent-side MCP client."
- Result-as-data DTO instead of raising exceptions. → "Result-as-data over the async-job boundary."

If a reviewer pushes back on any of those, the answer is in `tech-decisions.md`, not here.
