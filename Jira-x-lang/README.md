# Jira x LangChain

Conversational Jira companion that lets you inspect and update tickets in plain English. Under the hood it uses LangChain with Anthropic's Claude models plus Jira's REST API to translate natural language into concrete actions such as running JQL queries, moving issues across workflow states, or leaving comments.

## Setup

1. **Create a virtual environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Configure environment variables**  
   Copy `.env.example` to `.env` and fill in your secrets:
   ```
   ANTHROPIC_API_KEY=...
   ANTHROPIC_MODEL=claude-3-sonnet-20240229  # optional override
   # Domain **only** – no extra /jira/... paths
   JIRA_BASE_URL=https://your-domain.atlassian.net
   JIRA_EMAIL=you@company.com
   JIRA_API_TOKEN=...
   ```
   The Jira token must be generated from https://id.atlassian.com/manage-profile/security/api-tokens.

## Running the agent

```
python main.py
```

You'll drop into a simple REPL:

```
you> find bugs assigned to me
agent> I translated that to JQL ...
```

Type natural language requests such as:

- “Show me ACME-42”
- “Move ACME-42 to In Progress”
- “Comment on ACME-42 saying blocked by backend migration”
- “List all tickets in the Mobile board scheduled for this sprint”

Type `exit` or `quit` to leave the session.

## How it works

- `main.py` wires up LangChain's tool-calling agent with four tools backed by the Jira REST API: search issues, describe a single issue, transition workflow state, and add comments.
- `jira_client.py` contains a small, typed wrapper around the Jira HTTP endpoints plus helper formatting for LangChain responses.
- Anthropic's Claude model (configurable via `ANTHROPIC_MODEL`) receives a tailored system prompt instructing it to rely on the tools and summarize its actions back to you.

Extend the tooling by adding new helper methods to `JiraClient` and registering additional `StructuredTool` instances in `build_tools`.

## Running the Flask API

1. Ensure dependencies are installed and environment configured (see Setup above).
2. Start the server:
   ```bash
   python app.py
   ```
   By default it listens on `http://0.0.0.0:8000`. Override with `PORT=...`.

### Endpoints

- `GET /health`  
  Simple health check.

- `GET /api/issues/search?jql=<JQL>&max_results=5`  
  Search issues via JQL. Returns lightweight summaries.

- `GET /api/issues/{issue_key}`  
  Fetch full issue JSON from Jira.

- `POST /api/issues/{issue_key}/transition`  
  Body: `{"target_status": "In Progress"}`  
  Moves an issue to the given workflow status.

- `POST /api/issues/{issue_key}/comment`  
  Body: `{"body": "Text of the comment"}`  
  Adds a comment to the issue.

- `PUT /api/issues/{issue_key}/assignee`  
  Body: `{"account_id": "<Jira account id>"}`  
  Assigns the issue to the specified account.

- `PUT /api/issues/{issue_key}/fields`  
  Body: `{"fields": { /* Jira fields */ }}`  
  Directly updates Jira fields. Supports custom fields if you provide the correct field keys/IDs (e.g. `"customfield_12345"`).

- `POST /api/issues/{issue_key}/work-info`  
  Upload structured work details and optionally log time and update fields.  
  Body (any subset is accepted):
  ```json
  {
    "summary_of_work": "Investigated outage and applied fix",
    "server_status": "Healthy",
    "notes": "Rolled back to v1.2.3; added alert",
    "time_spent_seconds": 1800,
    "fields": { "labels": ["incident", "hotfix"] }
  }
  ```
  - Posts a single structured comment including any of summary_of_work, server_status, notes
  - If `time_spent_seconds` > 0, adds a worklog with a concise comment
  - If `fields` provided, updates the issue with those fields

All responses are JSON with the envelope:
```
{ "ok": true|false, "data": ... } // or { "ok": false, "error": { message, status } }
```

## Natural-language via LangChain

The Flask API also exposes a LangChain-powered chat endpoint so you can use plain English.

- Start the server (ensure `ANTHROPIC_API_KEY` is set in your environment or `.env`):
  ```bash
  python app.py
  ```

- Send a command in English:
  ```bash
  curl -s -X POST http://localhost:8000/api/agent/chat \
    -H "Content-Type: application/json" \
    -d '{"input":"Move SCRUM-7 to Testing"}' | jq
  ```

- More examples:
  ```bash
  # Describe an issue
  curl -s -X POST http://localhost:8000/api/agent/chat \
    -H "Content-Type: application/json" \
    -d '{"input":"Show me details for SCRUM-5"}' | jq

  # Comment in natural language
  curl -s -X POST http://localhost:8000/api/agent/chat \
    -H "Content-Type: application/json" \
    -d '{"input":"Comment on SCRUM-5 saying regression tests passed"}' | jq
  ```

### Examples

```bash
# Health
curl -s http://localhost:8000/health

# Search issues
curl -s "http://localhost:8000/api/issues/search?jql=project=ACME%20ORDER%20BY%20updated%20DESC&max_results=3"

# Get issue
curl -s http://localhost:8000/api/issues/ACME-123

# Transition issue
curl -s -X POST http://localhost:8000/api/issues/ACME-123/transition \
  -H "Content-Type: application/json" \
  -d '{"target_status":"In Progress"}'

# Comment on issue
curl -s -X POST http://localhost:8000/api/issues/ACME-123/comment \
  -H "Content-Type: application/json" \
  -d '{"body":"Blocked by backend migration"}'

# Assign issue
curl -s -X PUT http://localhost:8000/api/issues/ACME-123/assignee \
  -H "Content-Type: application/json" \
  -d '{"account_id":"<your-account-id>"}'
```
