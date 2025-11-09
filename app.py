from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend
from langchain_core.messages import HumanMessage
from langgraph.store.postgres import PostgresStore
import os
from tools import internet_search, execute_verification_plan, get_catalog
from model import model

research_instructions_path = os.path.join(
    os.path.dirname(__file__), "DEEP_AGENT_PROMPT.md"
)
with open(research_instructions_path, "r") as f:
    research_instructions = f.read()


def make_backend(runtime):
    return CompositeBackend(
        default=StateBackend(runtime),  # Ephemeral storage
        routes={"/memories/": StoreBackend(runtime)},  # Persistent storage
    )


def main(content: str, store: PostgresStore):
    agent = create_deep_agent(
        tools=[internet_search],
        system_prompt=research_instructions,
        model=model,
        backend=make_backend,
        store=store,
    )
    current_todos = None

    for chunk in agent.stream(
        {
            "messages": [
                {
                    "role": "user",
                    # "content": "I'm testing a backend system. Can you store some todos in the make_todos backend?",
                    "content": content,
                }
            ]
        },
        stream_mode=["messages", "updates"],
        subgraphs=True,
    ):
        if not isinstance(chunk, tuple) or len(chunk) != 3:
            continue
        namespace, current_stream_mode, data = chunk

        if current_stream_mode == "updates":
            if not isinstance(data, dict):
                continue

            chunk_data = list(data.values())[0] if data else None
            if chunk_data and isinstance(chunk_data, dict):
                # Check for todo updates
                if "todos" in chunk_data:
                    new_todos = chunk_data["todos"]
                    if new_todos != current_todos:
                        current_todos = new_todos
                        render_todo_list(new_todos)
        elif current_stream_mode == "messages":
            if not isinstance(data, tuple) or len(data) != 2:
                continue

            message, _metadata = data

            if isinstance(message, HumanMessage):
                content = message.text
                print(f"\n[{namespace} MESSAGE] {content}", end="")
            else:
                # print("[AI]: ", end="")
                for block in message.content_blocks:
                    if block["type"] == "text":
                        print(block["text"], end="")
                # print()

    # print(json.dumps(result, indent=2, default=str))


db_conn_string = os.environ["DEV_POSTGRES_URI"]
if __name__ == "__main__":
    with PostgresStore.from_conn_string(db_conn_string) as store:
        store.setup()
        main(store)
