import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests


class JiraError(RuntimeError):
    """Raised when the JiraClient receives an error response."""
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


@dataclass
class JiraIssueSummary:
    key: str
    summary: str
    status: str
    assignee: Optional[str]
    url: str

    def __str__(self) -> str:
        assignee = self.assignee or "Unassigned"
        return f"{self.key} [{self.status}] {self.summary} (Assignee: {assignee}) -> {self.url}"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "summary": self.summary,
            "status": self.status,
            "assignee": self.assignee,
            "url": self.url,
        }


class JiraClient:
    """Thin wrapper around the Jira Cloud REST API."""

    def __init__(self, base_url: str, email: str, api_token: str) -> None:
        if not base_url:
            raise ValueError("JIRA_BASE_URL is required")
        if not email:
            raise ValueError("JIRA_EMAIL is required")
        if not api_token:
            raise ValueError("JIRA_API_TOKEN is required")

        parsed = urlparse(base_url)
        if not parsed.scheme:
            parsed = urlparse(f"https://{base_url}")
        if not parsed.netloc:
            raise ValueError("JIRA_BASE_URL must include a hostname, e.g. https://company.atlassian.net")

        self.base_url = f"{parsed.scheme}://{parsed.netloc}"
        self.session = requests.Session()
        self.session.auth = (email, api_token)
        self.session.headers.update(
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )

    def _request(
        self, method: str, path: str, *, params: Optional[Dict[str, Any]] = None, json_body: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        response = self.session.request(method, url, params=params, json=json_body, timeout=30)
        if not response.ok:
            # Try to extract a concise error message; fall back to raw text
            message = response.text
            try:
                payload = response.json()
                message = payload.get("message") or payload.get("errorMessages") or payload.get("errors") or response.text
                if isinstance(message, list):
                    message = "; ".join(message)
                if isinstance(message, dict):
                    message = json.dumps(message)
            except Exception:
                pass
            raise JiraError(response.status_code, f"Jira API error {response.status_code}: {message}")
        if response.content:
            return response.json()
        return {}

    def search_issues(self, jql: str, max_results: int = 5) -> List[JiraIssueSummary]:
        payload = self._request(
            "GET",
            "/rest/api/3/search",
            params={"jql": jql, "maxResults": max_results, "fields": "summary,status,assignee"},
        )
        issues: List[JiraIssueSummary] = []
        for issue in payload.get("issues", []):
            fields = issue.get("fields", {})
            issues.append(
                JiraIssueSummary(
                    key=issue.get("key", ""),
                    summary=fields.get("summary", "No summary"),
                    status=(fields.get("status") or {}).get("name", "Unknown"),
                    assignee=((fields.get("assignee") or {}).get("displayName")),
                    url=f"{self.base_url}/browse/{issue.get('key')}",
                )
            )
        return issues

    def get_issue(self, issue_key: str) -> Dict[str, Any]:
        return self._request("GET", f"/rest/api/3/issue/{issue_key}", params={"expand": "renderedFields,changelog"})

    def get_transitions(self, issue_key: str) -> List[Dict[str, Any]]:
        payload = self._request("GET", f"/rest/api/3/issue/{issue_key}/transitions")
        return payload.get("transitions", [])

    def transition_issue(self, issue_key: str, target_status: str) -> str:
        transitions = self.get_transitions(issue_key)
        match = None
        for transition in transitions:
            name = transition.get("name", "")
            if name.lower() == target_status.lower():
                match = transition
                break

        if not match:
            available = ", ".join(t.get("name", "Unknown") for t in transitions) or "No transitions"
            raise JiraError(
                400,
                f"Cannot move {issue_key} to '{target_status}'. Available transitions: {available}",
            )

        transition_id = match.get("id")
        self._request("POST", f"/rest/api/3/issue/{issue_key}/transitions", json_body={"transition": {"id": transition_id}})
        return f"Issue {issue_key} moved to {match.get('name')}"

    def add_comment(self, issue_key: str, body: str) -> str:
        # Jira Cloud expects comment bodies in Atlassian Document Format (ADF).
        # Convert simple text into a minimal ADF document where each line is a paragraph.
        adf_content: List[Dict[str, Any]] = []
        for line in (body or "").splitlines():
            if line.strip() == "":
                adf_content.append({"type": "paragraph", "content": []})
            else:
                adf_content.append({"type": "paragraph", "content": [{"type": "text", "text": line}]})
        adf_body: Dict[str, Any] = {"type": "doc", "version": 1, "content": adf_content or [{"type": "paragraph", "content": []}]}
        self._request("POST", f"/rest/api/3/issue/{issue_key}/comment", json_body={"body": adf_body})
        return f"Added comment to {issue_key}"

    def assign_issue(self, issue_key: str, account_id: str) -> str:
        self._request("PUT", f"/rest/api/3/issue/{issue_key}/assignee", json_body={"accountId": account_id})
        return f"Assigned {issue_key} to account {account_id}"
    
    def add_worklog(self, issue_key: str, time_spent_seconds: int, comment: Optional[str] = None) -> str:
        payload: Dict[str, Any] = {"timeSpentSeconds": time_spent_seconds}
        if comment:
            payload["comment"] = comment
        self._request("POST", f"/rest/api/3/issue/{issue_key}/worklog", json_body=payload)
        return f"Logged {time_spent_seconds} seconds to {issue_key}"

    def update_issue_fields(self, issue_key: str, fields: Dict[str, Any]) -> str:
        if not isinstance(fields, dict) or not fields:
            raise JiraError(400, "Fields payload must be a non-empty object")
        self._request("PUT", f"/rest/api/3/issue/{issue_key}", json_body={"fields": fields})
        return f"Updated fields on {issue_key}"


def format_issue(issue: Dict[str, Any]) -> str:
    fields = issue.get("fields", {})
    status = (fields.get("status") or {}).get("name", "Unknown")
    assignee = ((fields.get("assignee") or {}).get("displayName")) or "Unassigned"
    description = fields.get("description")
    rendered_desc = ""
    if isinstance(description, dict) and description.get("content"):
        rendered_desc = json.dumps(description)
    elif isinstance(description, str):
        rendered_desc = description

    summary = fields.get("summary", "No summary provided")
    lines = [
        f"{issue.get('key')} — {summary}",
        f"Status: {status}",
        f"Assignee: {assignee}",
        f"Priority: {(fields.get('priority') or {}).get('name', 'Unspecified')}",
    ]
    if rendered_desc:
        lines.append(f"Description: {rendered_desc[:800]}")
    return "\n".join(lines)
