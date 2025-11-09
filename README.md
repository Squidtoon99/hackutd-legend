# HackUTD Lost in the Pages


Data Centers are the future. With that comes maintenance. How do we efficiently support the labor needed to maintain large scale data centers. This is why we created Relay. Relay offers a way for data center technicians to efficiently work through their tasks and run checks with agentic systems and ai tooling therefore not having to do time consuming tasks such as typing in tests on the laptop, waiting for the engineer to check your tests, waiting for no reason.

## Repository layout

| Path | Description |
| --- | --- |
| `api.py`, `db_models/`, `migrate_db.py` | Flask surface area and SQLAlchemy models for servers, tests, todos, result streams, and Jira tickets. Exposes REST + SSE endpoints for creating/running tests and streaming verifier output. |
| `deep_agent/` | LangGraph “deep agent” runner that turns natural language into verification plans, syncs todos, calls the Codex verifier tools, and writes progress/results back to Postgres. |
| `codex_verifier/` | Self-contained execution engine: parses a ToDo DSL, compiles it with the YAML catalog, runs SSH commands via `asyncssh`, parses/validates output, and emits SSE events/verdicts. |
| `middleware/` | Custom LangChain middleware (currently todo tracking). |
| `VisualServer/` | OpenCV + AprilTags AR overlay that can project live server health onto a tag anchored to the hardware (see `VisualServer/README.md`). |
| `Jira-x-lang/` | LangChain + Claude agent plus Flask API for conversational Jira workflows (see nested README). |
| `main.py`, `model.py`, `test_deep_agent_integration.py`, `sample_job.json` | Scratchpad scripts: NVIDIA Llama streaming demo, model loader stub, integration tester for `/tests/build`, and sample ToDo DSL payload. |

## Quick start

1. **Python + system deps**
   - Python 3.10+ (3.11 works best with LangChain / AsyncSSH)
   - Postgres 14+ (Neon/Cloud-hosted works fine) for both SQLAlchemy tables and the LangGraph `PostgresStore`
   - Optional: `ffmpeg`, OpenCV extras, iPhone Continuity Camera (for `VisualServer`)
2. **Create a virtual environment**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install flask flask_sqlalchemy psycopg2-binary deepagents langgraph-store langchain_core asyncssh tavily pydantic python-dotenv
   # plus any extras you need (anthropic, opencv-python==, etc.)
   ```
3. **Environment variables (`.env` or shell)**
   ```bash
   DEV_POSTGRES_URI=postgresql+psycopg2://user:pass@host:5432/dbname
   NVIDIA_API_KEY=...
   TAVILY_API_KEY=...                      # optional for internet search tool
   VERIFIER_URL=http://localhost:5000      # defaults to local Flask server
   ```
   Additional services may require: `ANTHROPIC_API_KEY`, `JIRA_*` credentials (see sub READMEs), or camera calibration files.
4. **Initialize the database**
   ```bash
   python migrate_db.py   # adds the JSON columns, FK fixes, and Result table if missing
   ```
5. **Run the Flask API**
   ```bash
   python api.py
   # listens on http://127.0.0.1:5000 by default
   ```

## Running the verification workflow

1. **Create a test via natural language**  
   POST `/tests/build` with a prompt and target host:
   ```bash
   curl -X POST http://localhost:5000/tests/build \
     -H "Content-Type: application/json" \
     -d '{"prompt":"Verify memory is healthy","target_host":"raspberrypi","server_id":"R200123A32"}'
   ```
   - `deep_agent/agent_runner.py` spins up a LangGraph agent configured with `deepagents`, the prompt from `deep_agent/DEEP_AGENT_PROMPT.md`, and tools (`get_catalog`, `execute_verification_plan`, `update_test`).
   - Todos emitted by the agent are persisted to `todos` so the UI/backend can show live progress.

2. **Execution + validation**  
   - The agent calls `execute_verification_plan`, which wraps `codex_verifier` functions: policy checks → plan compilation via `codex_verifier/catalog.yaml` → safety guardrails → SSH execution (default host/user/key in `deep_agent/agent_runner.py`) → parser/validator pipeline.
   - SSE-style events are written to the `streams` table; subscribe through `/tests/<id>/stream` or `/verifier/jobs/<job_id>/events`.

3. **Results**  
   - The agent finalizes the `tests` row (status, summary, evidence JSON) and creates a `results` entry.
   - Fetch summaries via `GET /tests`, `GET /tests/<id>`, or `GET /tests/<id>/stream`.

## Codex verifier as a standalone service

You can run the executor without the deep agent by launching the lightweight runner:

```bash
python codex_verifier/runner.py   # serves /runner/jobs, /runner/jobs/<id>/events, /runner/jobs/<id>/result on :8081
```

- Submit a job by POSTing `sample_job.json`:
  ```bash
  curl -X POST http://localhost:8081/runner/jobs \
    -H "Content-Type: application/json" \
    -d @sample_job.json
  ```
- The catalog (`codex_verifier/catalog.yaml`) defines allowed read-only actions, parsers, and validators plus sudo allowances.
- Parsers live in `codex_verifier/parsers.py`; validators in `codex_verifier/validators.py`. Edit those or the catalog to add telemetry.

## VisualServer AR overlay

The `VisualServer/` folder contains an OpenCV + AprilTags application that can project a live status panel over a server tagged with `tag36h11`. Follow `VisualServer/README.md` for:

- Installing via `pip install -r VisualServer/requirements.txt`
- Listing Continuity Camera / AVFoundation IDs
- Launching `python VisualServer/app.py --camera-index 0 --tag-size-m 0.05`
- Optional calibration files under `VisualServer/calib/`

Swap the placeholder data in `VisualServer/data.py` with real metrics from the Flask API if you want the AR overlay to reflect actual verification runs.

## Jira companion

`Jira-x-lang/` is an optional LangChain + Claude toolchain for conversational Jira updates. Key points (see its README for detail):

- Copy `.env.example` → `.env` with Atlassian credentials + Anthropic key.
- `python Jira-x-lang/main.py` launches a REPL agent; `python Jira-x-lang/app.py` starts the REST facade on `:8000`.
- Tools include search, describe, transition, comment, assign, and structured work logs.

## Database + schema tips

- Models live in `db_models/` and are imported once through `db_models/__init__.py`.
- `migrate_db.py` is idempotent and updates old schemas (UUID → int FK, todo simplification, JSON columns).
- Streams use an auto-incrementing bigint so SSE consumers can resume from the last ID without missing events.

## Testing and diagnostics

- `test_deep_agent_integration.py` pings `/tests/build`, asserts input validation, and tails the stream endpoint—handy sanity check while iterating on prompts/tools.
- Use `curl` or a simple SSE client to watch `/verifier/jobs/<job>/events` for real-time plan previews and verdicts.
- The `main.py` script shows how to make a streaming call against NVIDIA’s hosted Llama models; update the API key/env var before running.

## Next steps

- Flesh out a shared `requirements.txt` / `pyproject.toml`.
- Wire the VisualServer data feed to the Flask API.
- Finish the missing `_run_verification_job` helper inside `api.py` if you plan to rely on `/verifier/jobs`.

Happy hacking, and feel free to trim or expand this README as the project evolves!
