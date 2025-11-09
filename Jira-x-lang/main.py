import os
from dataclasses import dataclass
from typing import List, Sequence

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool

from jira_client import JiraClient, JiraError, format_issue


@dataclass
class AppConfig:
    anthropic_api_key: str
    jira_base_url: str
    jira_email: str
    jira_api_token: str
    anthropic_model: str = "claude-3-sonnet-20240229"

    @classmethod
    def from_env(cls) -> "AppConfig":
        load_dotenv()
        api_key = os.getenv("ANTHROPIC_API_KEY")
        jira_base = os.getenv("JIRA_BASE_URL")
        jira_email = os.getenv("JIRA_EMAIL")
        jira_token = os.getenv("JIRA_API_TOKEN")
        model = os.getenv("ANTHROPIC_MODEL", cls.anthropic_model)

        missing = [name for name, value in [("ANTHROPIC_API_KEY", api_key), ("JIRA_BASE_URL", jira_base), ("JIRA_EMAIL", jira_email), ("JIRA_API_TOKEN", jira_token)] if not value]
        if missing:
            raise RuntimeError(f"Missing environment variables: {', '.join(missing)}")

        return cls(
            anthropic_api_key=api_key or "",
            jira_base_url=jira_base or "",
            jira_email=jira_email or "",
            jira_api_token=jira_token or "",
            anthropic_model=model,
        )


def build_tools(client: JiraClient) -> List[StructuredTool]:
    class SearchIssuesInput(BaseModel):
        jql: str = Field(..., description="A valid JQL query")
        max_results: int = Field(5, ge=1, le=50, description="Maximum number of results")

    class DescribeIssueInput(BaseModel):
        issue_key: str = Field(..., description="Issue key like PROJ-123")

    class TransitionIssueInput(BaseModel):
        issue_key: str = Field(..., description="Issue key to move")
        target_status: str = Field(..., description="Target status/column name")

    class CommentIssueInput(BaseModel):
        issue_key: str = Field(..., description="Issue key to comment on")
        body: str = Field(..., description="Text for the Jira comment")

    def safe_call(fn):
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except JiraError as exc:
                return f"Jira error: {exc}"
            except Exception as exc:  # pragma: no cover - defensive logging
                return f"Unexpected error: {exc}"

        return wrapper

    def search_issues(jql: str, max_results: int = 5) -> str:
        issues = client.search_issues(jql, max_results)
        if not issues:
            return "No issues match that query."
        return "\n".join(str(issue) for issue in issues)

    def describe_issue(issue_key: str) -> str:
        issue = client.get_issue(issue_key)
        return format_issue(issue)

    def transition_issue(issue_key: str, target_status: str) -> str:
        return client.transition_issue(issue_key, target_status)

    def comment_issue(issue_key: str, body: str) -> str:
        return client.add_comment(issue_key, body)

    return [
        StructuredTool.from_function(
            name="search_jira_issues",
            func=safe_call(search_issues),
            description="Search Jira using JQL to find tickets relevant to a question.",
            args_schema=SearchIssuesInput,
        ),
        StructuredTool.from_function(
            name="describe_jira_issue",
            func=safe_call(describe_issue),
            description="Fetch rich details for a specific issue key, including status and description.",
            args_schema=DescribeIssueInput,
        ),
        StructuredTool.from_function(
            name="transition_jira_issue",
            func=safe_call(transition_issue),
            description="Move an issue to a new workflow state by specifying the desired status name.",
            args_schema=TransitionIssueInput,
        ),
        StructuredTool.from_function(
            name="comment_on_jira_issue",
            func=safe_call(comment_issue),
            description="Leave a comment on an issue to provide updates or ask questions.",
            args_schema=CommentIssueInput,
        ),
    ]


def build_agent(config: AppConfig):
    client = JiraClient(config.jira_base_url, config.jira_email, config.jira_api_token)
    tools = build_tools(client)
    llm = ChatAnthropic(model=config.anthropic_model, temperature=0, api_key=config.anthropic_api_key)
    system_prompt = (
        "You are a helpful Jira copilot. Use the available tools to inspect Jira issues, update their state, "
        "and log comments. Ask for clarification when needed, translate natural language into JQL when the user "
        "is imprecise, and summarize your actions for the user."
    )
    return create_agent(llm, tools, system_prompt=system_prompt)


def run_cli() -> None:
    config = AppConfig.from_env()
    agent = build_agent(config)
    messages: List[BaseMessage] = []
    print("Jira LangChain Agent\nType natural language commands. Type 'exit' to quit.")
    while True:
        try:
            user_input = input("you> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            break

        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit"}:
            print("Goodbye!")
            break

        messages.append(HumanMessage(content=user_input))

        try:
            # create_agent returns a langgraph compiled graph; invoke yields the updated AgentState
            result = agent.invoke({"messages": messages})
            updated_messages: Sequence[BaseMessage] = result.get("messages", [])
            messages = list(updated_messages)
            last_ai = next((msg for msg in reversed(messages) if isinstance(msg, AIMessage)), None)
            output = last_ai.content if last_ai else "Agent did not return a response."
        except Exception as exc:
            output = f"Agent error: {exc}"
            messages.append(AIMessage(content=output))

        print(f"agent> {output}")


if __name__ == "__main__":
    run_cli()
