# Technical Decisions

Each section covers a decision by stating what was chosen, what other options were considered, and the reasons for the final choice. Decisions are organized based on their place in the system.

## Architecture style

### DDD / n-tier with Hexagonal port-adapter boundaries

- **Picked:** `domain` (pure model and ports) → `application` (use cases and LangGraph DAG) → `infrastructure` (port adapters) → `composition` (wiring) → `interfaces` (CLI / REST).
- **Alternatives:** flat module layout; service-oriented (one `services.py`); Clean Architecture with explicit `entities/` and `usecases/` folders.
- **Why:** Five external concerns (MCP, RAG, LLM, render, persist) each fit well with a separate port. By keeping the domain free of frameworks, testing becomes simple. Using `Protocol` and `runtime_checkable` allows easy use of fakes through the builder's `with_custom_*` slots. The composition root pattern keeps all wiring in one place and prevents framework imports from spreading into the application.

### Five ports = five case requirements (1 : 1 mapping)

- **Picked:** `TicketRepository`, `LlmService`, `KnowledgeRepository`, `ReportRenderer`, `ReportRepository`.
- **Why:** The case description lists five concerns. Assigning one port to each makes the architecture self-explanatory. For example, if a reviewer asks "where does the MCP requirement live?", the answer is "the `TicketRepository` port and its `McpTicketRepository` adapter". Separating render and persist keeps "what the report looks like" apart from "where it goes".

### Async ports for I/O, sync ports for CPU/local

- **Picked:** `TicketRepository.fetch_bundle` and `LlmService.complete` are `async def`. `KnowledgeRepository.retrieve`, `ReportRenderer.render`, and `ReportRepository.save` are sync.
- **Alternatives:** make everything async; make everything sync.
- **Why:** Chroma's Python client is synchronous, rendering uses only the CPU, and filesystem writes are very fast. Making these async would add complexity without real benefit. The pipeline only crosses between async and sync at one point, using `asyncio.to_thread` in `_node_retrieve`, where it is actually needed.

## Pipeline / orchestration

### LangGraph for the per-ticket DAG

- **Picked:** `langgraph.graph.StateGraph` with five linear nodes and a `TypedDict` state.
- **Alternatives:** raw async function chain; LangChain `RunnableSequence`; hand-rolled state machine.
- **Why:** Node-level features like logging, retries and conditional edges are built-in. The DAG is linear for now, but the framework makes future branching possible, such as running "analyze" and "summarize" in parallel, without needing to rewrite the orchestrator. Using `TypedDict(total=False)` for state fits LangGraph's merge behavior, since each node returns only the keys it updates.

### Two LLM calls per ticket: analyze, then propose

- **Picked:** First call produces the **Root Cause Analysis** section; second call produces the **Remediation** section, prompted with `{analysis}` from the first.
- **Alternatives:** single combined call asking for both sections.
- **Why:** The output from the first call is used as input for the second. This approach creates clearer sections and reduces hallucinations. The prompt ("Do NOT include solution steps in this section") helps keep the sections separate. The two-call process is verified by `test_use_cases.test_llm_called_twice_per_ticket_analysis_then_remediation`.

### Result-as-data over the async-job boundary

- **Picked:** `RcaResponse(ticket_id, report_path, error)`. Both `report_path` and `error` are `str | None`.
- **Alternatives:** raise exceptions, let the caller catch.
- **Why:** Errors pass through `asyncio.Task` and a JSON REST boundary. Wrapping errors as data avoids the need for exception serialization and keeps the REST layer simple. Each pipeline node also writes `state["error"]` and stops early if needed. This way, every node handles errors the same way, so the JobStore's `try/except` is a true last-resort catch, not just a workaround.

## Models

### Ollama with `qwen2.5:3b` as the default

- **Picked:** `qwen2.5:3b` via `langchain_ollama.ChatOllama`. `temperature=0.2`, `num_ctx=8192`.
- **Alternatives:** `llama3.2:3b`, `phi3.5:3.8b`, hosted APIs (OpenAI / Anthropic).
- **Why:** Hosted APIs are not an option because the case requires offline use. Of the local 3B-class models, `qwen2.5:3b` follows structured-output prompts most reliably for SRE/RCA tone in the author's tests. A low temperature setting gives consistent outputs, and the 8K context window easily fits ticket evidence and the top four KB chunks. Upgrading is simple: set `OLLAMA_MODEL=qwen2.5:7b` and re-run `ollama-init`.

### `intfloat/multilingual-e5-small` for embeddings

- **Picked:** 384-dim, multilingual, ~120 MB.
- **Alternatives:** `all-MiniLM-L6-v2` (English-only), `bge-small`, OpenAI `text-embedding-3-small`.
- **Why:** The ITSM tickets here are in English, but real-world tickets could be in Turkish, mixed languages, or contain non-English log lines. Using a multilingual model is a simple way to cover these cases. The model is small enough for acceptable cold-start times on CPU. The query and passage prefix convention is handled inside `E5Embedder`, so the rest of the system does not need to worry about it.

## RAG

### Chroma with L2 distance and cosine reconstruction

- **Picked:** `chromadb.PersistentClient` with the default L2 metric; embeddings normalized at write time; cosine score reconstructed in code as `1.0 - dist/2.0`.
- **Alternatives:** FAISS, Qdrant, in-memory NumPy similarity; configure Chroma for cosine directly.
- **Why:** Chroma is the easiest option that works in a single container, and `PersistentClient` keeps the index available after restarts. Using normalized vectors with L2 distance is mathematically the same as cosine similarity and avoids relying on Chroma-specific metric settings.

### Fingerprint-based incremental indexing

- **Picked:** SHA-256 of `(name, size, mtime)` for every `*.md` in `kb/`. Stored in `persist_dir/fingerprint.txt`.
- **Alternatives:** rebuild index every cold-start; manual `--reindex` flag.
- **Why:** Reading 10 small files on cold-start is easy, but re-encoding about 50 chunks takes 30 to 60 seconds on CPU. The fingerprint check makes later boots instant if the KB has not changed.

### `## ` (H2) section-based chunking

- **Picked:** A `MarkdownChunker` that splits on H2 headings; H1 lines fold into the leading "Overview" section.
- **Alternatives:** fixed-size sliding window; sentence-tokenizer-based; LangChain's `MarkdownHeaderTextSplitter`.
- **Why:** The runbooks in `kb/` all follow the same structure, with an H1 title and H2 sections like "Symptoms", "Likely Cause", and "Mitigation". A custom chunker that matches this structure is simple, easy to test, and produces meaningful chunks without needing extra context tricks.

### `top_k=4`

- **Picked:** Default in `RagConfig`, env-overridable as `TOP_K`.
- **Alternatives:** 2, 6, 8.
- **Why:** In practice, four chunks fit well within the 8K context limit, along with ticket evidence and prompt scaffolding. This number also gives the LLM enough options to consider. The setting can be easily adjusted for different environments.

## MCP layer

### `mcp-server` as a thin proxy in front of the mock REST

- **Picked:** Separate container running `FastMCP` over streamable-HTTP, registering four tools (`list_tickets`, `get_ticket`, `get_ticket_comments`, `get_ticket_history`).
- **Alternatives:** call the mock REST directly from the agent; merge MCP and mock into one process.
- **Why:** The case specifically asks for "ITSM data via MCP", so having this extra layer is intentional. Keeping MCP separate from the mock keeps the contract clear. If you swap `itsm-mock` for a real ServiceNow or Jira backend, only the MCP tool implementation changes, and the agent does not need to be updated.

### Stateless agent-side MCP client (per-call session)

- **Picked:** `McpTicketRepository.fetch_bundle` opens `streamablehttp_client` and `ClientSession` per call, performs three tool calls, then closes.
- **Alternatives:** long-lived session held in the adapter.
- **Why:** The volume is low, with at most one ticket every 110 seconds. Per-call sessions are simpler, safe to restart, and avoid "session went stale" bugs. The docstring explains this trade-off, so future readers know where to add pooling if traffic increases.

### `_decode` is defensive about MCP response shapes

- **Picked:** Three-way fallback: `structuredContent` → single-key unwrap → `content[0].text` JSON parse → raw text.
- **Why:** MCP servers built with different libraries, and at different stages of the spec's development, wrap responses in different ways. The defensive decoder handles these differences at the boundary, so the rest of the system always receives `dict` or `list[dict]`.

## REST surface

### Async job pattern (`POST /rca` returns `202` with `job_id`)

- **Picked:** Send, poll, fetch. `JobStore` runs jobs as `asyncio.Task` with `Semaphore=1`.
- **Alternatives:** synchronous request that blocks for 110 s; SSE streaming.
- **Why:** A 110-second synchronous request is unreliable due to proxy timeouts, retries and client uncertainty. The async job pattern is the standard REST approach for long-running tasks. SSE adds streaming complexity, but no improvement of user experience, since only `curl` and `e2e_batch.ps1` use it.

### `Semaphore=1` for job execution

- **Picked:** One job at a time, serialised.
- **Alternatives:** unbounded concurrency; thread pool sized to CPU count.
- **Why:** Ollama already processes requests one at a time, so running eight LLM calls in parallel doesn't make things faster. It only adds context switching overhead and makes log timelines harder to follow. Adding concurrency at the REST layer does not help the LLM, therefore the best approach is to enforce serialization.

### Process-local `JobStore`, no persistence

- **Picked:** In-memory `dict` with a `_lock` and a bounded FIFO eviction (`max_records=500`).
- **Alternatives:** Redis, SQLite, Postgres.
- **Why:** RCA artifacts are already saved on disk under `reports/`. The job registry only exists so the REST poller can read while a job is running. Restarting loses job history, but not outputs. For a case study, this is the right trade-off. Adding Redis or SQL would add real complexity without meeting any requirements from the brief.

### Lifespan factory for test injection

- **Picked:** `_make_lifespan(application=None, config=None, jobs=None)`. Production builds defaults; tests pass an injected `AgentApplication`.
- **Alternatives:** override FastAPI dependencies in tests; spin up the real stack for tests.
- **Why:** Tests run in milliseconds without ever touching Ollama, Chroma, or MCP. The lifespan boundary is the natural injection point because that's exactly where the application is "born" in production too.

### Path traversal hardening on `/reports/{ticket_id}`

- **Picked:** Regex `^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$` and `path.resolve().is_relative_to(out_dir)`.
- **Alternatives:** trust FastAPI's path-parameter handling.
- **Why:** The endpoint reads from the host filesystem using a segment controlled by the user. Even if FastAPI or Starlette already block `../`, adding extra protection is easy with one regex and one resolve check. A parametric test covers also seven hostile inputs.

## Configuration

### `AgentConfig` is the only thing that reads `os.environ`

- **Picked:** `AgentConfig.from_env()` and nowhere else. Frozen dataclass passed to everything.
- **Alternatives:** read env at every call site; use Pydantic Settings.
- **Why:** There is a single source of truth, since searching for `os.environ` in `agent/src` finds only one file. Using a frozen dataclass prevents downstream code from accidentally changing the config. Pydantic Settings could work, but it adds a dependency for something that 30 lines of code already handle.

### `_int_env` and `_float_env` raise descriptive errors

- **Picked:** Wrap parse failures with `ValueError(f"Environment variable {NAME}={raw!r} is not a valid integer")`.
- **Why:** If `int(os.environ["TOP_K"])` fails during container startup, it just gives a stack trace ending in `int("oops")`, which is not helpful. The wrapper changes this into a message that is easier to debug during deployment.

## Tooling

### `ruff` for both linting and formatting

- **Picked:** `ruff check` and `ruff format --check` in CI; same on the dev machine.
- **Alternatives:** `black`, `flake8` and `isort`.
- **Why:** Using one tool with a single config block in `pyproject.toml` is faster than the alternatives. The selected rule set (`E, W, F, I, B, UP, SIM, RUF`) covers everything the other three tools would, with `B` (bugbear) and `SIM` (simplify) as extra benefits.

### `pytest-asyncio` in `mode=auto`

- **Picked:** `asyncio_mode = "auto"` in `pyproject.toml`.
- **Why:** This eliminates the need to add `@pytest.mark.asyncio` to every async test. Setting `asyncio_default_fixture_loop_scope` to `"function"` means that each test has its own isolated fixture, corresponding to the production setup.

### Tests use port-level fakes, not mocks

- **Picked:** Hand-rolled `FakeTicketRepository`, `FakeKnowledgeRepository`, `FakeLlmService`, `FakeReportRenderer`, `FakeReportRepository` in `conftest.py`. They implement the same `Protocol`s as the real adapters.
- **Alternatives:** `unittest.mock.MagicMock`, `pytest-mock`.
- **Why:** Mocks let you check call shapes, while fakes let you check behavior. `FakeTicketRepository` raises `LookupError` just like the real one, as noted in the comment "to mirror the real adapter" in the file. The fakes also record their calls (`fetch_calls`, `llm.calls`, etc.), so you can still do interaction testing where it matters.

## Container topology

### Five services, three named volumes

- **Picked:** `ollama`, `ollama-init`, `itsm-mock`, `mcp-server`, `agent`. Volumes: `ollama_data`, `chroma_data`, `hf_cache`.
- **Why:** Each service has a single job, such as LLM, model pull, mock backend, MCP proxy, or agent REST. The volumes store the three slowest-to-rebuild artifacts: model weights, embedded KB, and the sentence-transformers cache. The first start is cold, but every start after that is fast.

### `ollama-init` as a separate one-shot service

- **Picked:** Reuse the `ollama/ollama` image with an entrypoint that calls `ollama pull`, then exits. Agent depends on `ollama-init: condition: service_completed_successfully`.
- **Alternatives:** bake the model into a custom image; pull at agent start.
- **Why:** Baking the model into the image creates a large build context whenever the model changes. Pulling the model at agent start ties boot time to network speed. A dedicated init service runs once and finishes, so the "model is ready" state is built into the compose graph, instead of relying on a timed delay.

### `start_period: 90s` on the agent healthcheck

- **Picked:** A long `start_period` is used because loading the Chroma index, `SentenceTransformer` model, and warming up Ollama can easily take 60 seconds on a fresh start.
- **Why:** Without this, Compose would mark the agent as unhealthy and keep restarting it. The other services use shorter `start_period`s because they do not have a heavy load step.

### `kb/` mounted read-only into the agent

- **Picked:** `./kb:/app/kb:ro` in `docker-compose.yml`.
- **Why:** The agent should not write to the KB. Mounting it as read-only (`:ro`) enforces this rule. Re-indexing only happens when the host edits a file and the fingerprint changes, so the container can never corrupt the source.
