import os
from typing import Any, Dict, List

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

from jira_client import JiraClient, JiraError, JiraIssueSummary
from main import AppConfig, build_agent
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage


def create_app() -> Flask:
    load_dotenv()

    jira_base = os.getenv("JIRA_BASE_URL")
    jira_email = os.getenv("JIRA_EMAIL")
    jira_token = os.getenv("JIRA_API_TOKEN")

    client = JiraClient(jira_base or "", jira_email or "", jira_token or "")

    app = Flask(__name__)
    # Accept both with/without trailing slashes for all routes
    app.url_map.strict_slashes = False

    # Lazy-load a LangChain agent for natural-language commands
    _agent = {"instance": None}

    def get_agent():
        if _agent["instance"] is None:
            cfg = AppConfig.from_env()
            _agent["instance"] = build_agent(cfg)
        return _agent["instance"]

    @app.errorhandler(JiraError)
    def handle_jira_error(exc: JiraError):
        status = getattr(exc, "status_code", 502) or 502
        return jsonify({"ok": False, "error": {"message": exc.message, "status": status}}), status
    
    @app.errorhandler(HTTPException)
    def handle_http_exception(exc: HTTPException):
        # Return JSON for all HTTP errors (e.g., 404 Not Found)
        return jsonify({"ok": False, "error": {"message": exc.description, "status": exc.code}}), exc.code

    @app.errorhandler(Exception)
    def handle_unexpected_error(exc: Exception):
        return jsonify({"ok": False, "error": {"message": str(exc), "status": 500}}), 500

    @app.get("/")
    def index() -> Any:
        return jsonify(
            {
                "ok": True,
                "endpoints": [
                    {"method": "GET", "path": "/health"},
                    {"method": "GET", "path": "/api/issues/search?jql=<JQL>&max_results=5"},
                    {"method": "GET", "path": "/api/issues/<issue_key>"},
                    {"method": "POST", "path": "/api/issues/<issue_key>/transition"},
                    {"method": "POST", "path": "/api/issues/<issue_key>/comment"},
                    {"method": "PUT", "path": "/api/issues/<issue_key>/assignee"},
                    {"method": "PUT", "path": "/api/issues/<issue_key>/fields"},
                    {"method": "POST", "path": "/api/issues/<issue_key>/work-info"},
                    {"method": "POST", "path": "/api/agent/chat"},
                ],
            }
        )

    @app.get("/health")
    def health() -> Any:
        return jsonify({"ok": True, "status": "healthy"})

    @app.get("/api/issues/search")
    def search_issues() -> Any:
        jql = request.args.get("jql", type=str)
        max_results = request.args.get("max_results", default=5, type=int)
        if not jql:
            return jsonify({"ok": False, "error": {"message": "Query parameter 'jql' is required", "status": 400}}), 400
        results: List[JiraIssueSummary] = client.search_issues(jql, max_results=max_results)
        return jsonify({"ok": True, "data": [r.to_dict() for r in results]})

    @app.get("/api/issues/<issue_key>")
    def get_issue(issue_key: str) -> Any:
        issue: Dict[str, Any] = client.get_issue(issue_key)
        return jsonify({"ok": True, "data": issue})

    @app.post("/api/issues/<issue_key>/transition")
    def transition_issue(issue_key: str) -> Any:
        body = request.get_json(silent=True) or {}
        target_status = body.get("target_status")
        if not target_status or not isinstance(target_status, str):
            return (
                jsonify({"ok": False, "error": {"message": "Field 'target_status' is required", "status": 400}}),
                400,
            )
        result = client.transition_issue(issue_key, target_status)
        return jsonify({"ok": True, "data": {"message": result}})

    @app.post("/api/issues/<issue_key>/comment")
    def comment_issue(issue_key: str) -> Any:
        body = request.get_json(silent=True) or {}
        comment = body.get("body")
        if not comment or not isinstance(comment, str):
            return (
                jsonify({"ok": False, "error": {"message": "Field 'body' is required", "status": 400}}),
                400,
            )
        result = client.add_comment(issue_key, comment)
        return jsonify({"ok": True, "data": {"message": result}})

    @app.put("/api/issues/<issue_key>/assignee")
    def assign_issue(issue_key: str) -> Any:
        body = request.get_json(silent=True) or {}
        account_id = body.get("account_id")
        if not account_id or not isinstance(account_id, str):
            return (
                jsonify({"ok": False, "error": {"message": "Field 'account_id' is required", "status": 400}}),
                400,
            )
        result = client.assign_issue(issue_key, account_id)
        return jsonify({"ok": True, "data": {"message": result}})

    @app.put("/api/issues/<issue_key>/fields")
    def update_fields(issue_key: str) -> Any:
        body = request.get_json(silent=True) or {}
        fields = body.get("fields")
        if not isinstance(fields, dict) or not fields:
            return (
                jsonify({"ok": False, "error": {"message": "Field 'fields' must be a non-empty object", "status": 400}}),
                400,
            )
        result = client.update_issue_fields(issue_key, fields)
        return jsonify({"ok": True, "data": {"message": result}})

    @app.post("/api/issues/<issue_key>/work-info")
    def upload_work_info(issue_key: str) -> Any:
        """
        Accepts a payload like:
        {
          "summary_of_work": "Investigated outage and applied fix",
          "server_status": "Healthy",
          "notes": "Rolled back to v1.2.3; added alert",
          "time_spent_seconds": 1800,
          "fields": { "labels": ["incident", "hotfix"] } // optional direct field updates
        }
        """
        body = request.get_json(silent=True) or {}
        summary_of_work = body.get("summary_of_work")
        server_status = body.get("server_status")
        notes = body.get("notes")
        time_spent_seconds = body.get("time_spent_seconds")
        fields = body.get("fields")

        if not any([summary_of_work, server_status, notes, time_spent_seconds, fields]):
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": {
                            "message": "Provide at least one of: summary_of_work, server_status, notes, time_spent_seconds, fields",
                            "status": 400,
                        },
                    }
                ),
                400,
            )

        actions: List[Dict[str, Any]] = []

        # Post a structured comment if any textual info is present
        comment_parts: List[str] = []
        if summary_of_work:
            comment_parts.append(f"*Summary of work*: {summary_of_work}")
        if server_status:
            comment_parts.append(f"*Server status*: {server_status}")
        if notes:
            comment_parts.append(f"*Notes*: {notes}")
        if comment_parts:
            comment_text = "\n".join(comment_parts)
            msg = client.add_comment(issue_key, comment_text)
            actions.append({"type": "comment", "message": msg})

        # Optionally add a worklog
        if isinstance(time_spent_seconds, int) and time_spent_seconds > 0:
            # Prefer a concise worklog comment; fall back to summary if present
            worklog_comment = summary_of_work or notes or "Work logged via API"
            msg = client.add_worklog(issue_key, time_spent_seconds, worklog_comment)
            actions.append({"type": "worklog", "message": msg})

        # Optionally update fields directly (supports custom fields if caller provides correct field IDs)
        if isinstance(fields, dict) and fields:
            msg = client.update_issue_fields(issue_key, fields)
            actions.append({"type": "fields", "message": msg})

        return jsonify({"ok": True, "data": {"actions": actions}})

    @app.post("/api/agent/chat")
    def agent_chat() -> Any:
        """
        Body:
        { "input": "Move SCRUM-7 to Testing" }
        Returns the agent's natural-language response after using Jira tools.
        """
        body = request.get_json(silent=True) or {}
        user_input = body.get("input")
        if not user_input or not isinstance(user_input, str):
            return (
                jsonify({"ok": False, "error": {"message": "Field 'input' is required", "status": 400}}),
                400,
            )
        try:
            agent = get_agent()
            messages: List[BaseMessage] = [HumanMessage(content=user_input)]
            result = agent.invoke({"messages": messages})
            updated_messages = result.get("messages", [])
            last_ai = next((m for m in reversed(updated_messages) if isinstance(m, AIMessage)), None)
            output = last_ai.content if last_ai else "No response."
            return jsonify({"ok": True, "data": {"output": output}})
        except JiraError as exc:
            status = getattr(exc, "status_code", 502)
            return jsonify({"ok": False, "error": {"message": exc.message, "status": status}}), status
        except Exception as exc:
            return jsonify({"ok": False, "error": {"message": str(exc), "status": 500}}), 500

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=True)


