# Sample RCA Reports

This directory holds the per-ticket Markdown RCA reports produced by the agent. Each `INC-*.md` is the output of one full pipeline run (fetch ticket via MCP, retrieve top-K KB chunks, two-call LLM analysis + remediation, render Markdown).

## What is committed and what is not

`reports/*.md` is gitignored except this README. The generated reports are reproducible from the running stack and would otherwise churn on every run; keeping them out of version control keeps the diff signal high.

```
reports/
├── README.md      <- committed (this file)
├── INC-1001.md    <- generated, gitignored
├── INC-1002.md    <- generated, gitignored
└── ...
```

## Regenerating the sample reports

With the compose stack up and healthy:

```powershell
# All 8 sample tickets, ~14 min on CPU
.\e2e_batch.ps1
```

Or one ticket at a time:

```bash
curl -X POST http://localhost:8002/rca/INC-1001
curl http://localhost:8002/jobs/<job_id>            # poll until "succeeded"
curl http://localhost:8002/reports/INC-1001 > reports/INC-1001.md
```

## What the reports look like

Each report has six sections plus a footer that names the LLM model, the number of KB chunks used, and the MCP source. See `docs/architecture.md` for the rendering logic and `agent/src/itsm_agent/infrastructure/reports/markdown_renderer.py` for the template.
