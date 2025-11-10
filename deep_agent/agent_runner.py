"""
Deep Agent Runner for Flask API Integration

This module provides the interface between the Flask API and the Deep Agent,
handling test generation, execution, and result storage.
"""

import os
import sys
import uuid
import threading
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import json
from api import app as flask_app

from langchain_core.messages import HumanMessage, ToolMessage

# Add parent directory to path for db_models import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend
from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.store.postgres import PostgresStore

from tools import get_catalog
from model import model

# Import codex_verifier components
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "codex_verifier"))
from codex_verifier.models import ToDoDSL, VerificationResult, VerificationDetail
from codex_verifier.preflight import Catalog, compile_plan, policy_gate, static_audit
from codex_verifier.exec_pool import execute_plan
from codex_verifier.parsers import (
    parse_meminfo,
    parse_dmidecode,
    parse_ethtool,
    parse_ethtool_stats,
    parse_sysfs_nic,
    parse_smart,
    parse_ipmi_psu,
    parse_ipmi_fans,
    parse_ipmi_thermal,
    parse_dmesg,
    parse_os_release,
)
from codex_verifier.validators import (
    total_mem_within_pct,
    all_expected_dimms,
    nic_link_up,
    nic_speed_at_least,
    nic_no_errors,
    disk_smart_pass,
    no_critical_logs,
)

from db_models import Test, Todo, Result, Stream

# Catalog for verifier
catalog = Catalog.load(
    os.path.join(os.path.dirname(__file__), "..", "codex_verifier", "catalog.yaml")
)

# Registry
PARSERS = {
    "parse_meminfo": parse_meminfo,
    "parse_dmidecode": parse_dmidecode,
    "parse_ethtool": parse_ethtool,
    "parse_ethtool_stats": parse_ethtool_stats,
    "parse_sysfs_nic": parse_sysfs_nic,
    "parse_smart": parse_smart,
    "parse_ipmi_psu": parse_ipmi_psu,
    "parse_ipmi_fans": parse_ipmi_fans,
    "parse_ipmi_thermal": parse_ipmi_thermal,
    "parse_dmesg": parse_dmesg,
    "parse_os_release": parse_os_release,
}

VALIDATORS = {
    "total_mem_within_pct": total_mem_within_pct,
    "all_expected_dimms": all_expected_dimms,
    "nic_link_up": nic_link_up,
    "nic_speed_at_least": nic_speed_at_least,
    "nic_no_errors": nic_no_errors,
    "disk_smart_pass": disk_smart_pass,
    "no_critical_logs": no_critical_logs,
}

# In-memory job tracking (for SSE streaming) - kept for backward compatibility with /verifier/jobs endpoint
JOBS = {}


def _parse_validator_spec(spec: str):
    """Return (name, args:list) from 'name' or 'name(x,y)'."""
    if "(" not in spec:
        return spec, []
    name, rest = spec.split("(", 1)
    rest = rest.rstrip(")")
    raw_args = [a.strip() for a in rest.split(",") if a.strip()]
    # best-effort cast
    args = []
    for a in raw_args:
        if a.isdigit():
            args.append(int(a))
        else:
            try:
                args.append(float(a))
            except ValueError:
                args.append(a)
    return name, args


def make_backend(runtime):
    """Create the backend for the agent."""
    return CompositeBackend(
        default=StateBackend(runtime),  # Ephemeral storage
        routes={"/memories/": StoreBackend(runtime)},  # Persistent storage
    )


def load_agent_prompt() -> str:
    """Load the deep agent system prompt."""
    prompt_path = os.path.join(os.path.dirname(__file__), "DEEP_AGENT_PROMPT.md")
    with open(prompt_path, "r") as f:
        return f.read()


class AgentRunner:
    """Handles deep agent execution and database integration."""

    def __init__(self, db_session, store: PostgresStore):
        """
        Initialize the agent runner.

        Args:
            db_session: SQLAlchemy database session
            store: PostgresStore for agent persistence
        """
        self.db = db_session
        self.store = store
        self.content = ""
        self.system_prompt = load_agent_prompt()

    def create_test_from_prompt(
        self, user_prompt: str, target_host: str, server_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a test from a user prompt and target host.

        This function:
        1. Creates a Test record in the database
        2. Spawns a background thread to run the deep agent
        3. Returns immediately with the test_id

        The background thread will:
        - Generate a verification plan using the deep agent
        - Store todos in the database
        - Execute the verification plan
        - Update the test with results

        Args:
            user_prompt: User's natural language request (e.g., "Run test xyz")
            target_host: Target host to test (e.g., "raspberrypi.local")
            server_id: Optional server ID for tracking

        Returns:
            Dict containing test_id and status
        """
        from db_models import Test

        # Generate unique test ID
        test_id_str = str(uuid.uuid4())

        # Create initial test record
        test = Test(
            name=f"agent-test-{test_id_str[:8]}",
            server_id=server_id or target_host,
            status="GENERATING",
            started_at=datetime.now(timezone.utc),
            context={"user_prompt": user_prompt, "target_host": target_host},
        )
        self.db.add(test)
        self.db.commit()
        test_id = test.id

        # Spawn background thread to run the agent
        thread = threading.Thread(
            target=self._run_agent_in_background,
            args=(user_prompt, target_host, test_id),
            daemon=True,
        )
        thread.start()

        # Return immediately with test_id
        return {
            "test_id": test_id,
            "status": "success",
            "message": "Test created and generation started in background",
        }

    def _run_agent_in_background(
        self, user_prompt: str, target_host: str, test_id: int
    ):
        """
        Run the agent in a background thread.

        This method handles the entire test generation and execution process.
        The agent will generate a plan, execute it, and update the test results.
        """
        from db_models import Test

        try:
            with flask_app.app_context():
                # Run the agent - it will handle everything including execution
                self._generate_plan(user_prompt, target_host, test_id)

        except Exception as e:
            # Update test with error
            with flask_app.app_context():
                try:
                    test = Test.query.get(test_id)
                    if test:
                        test.status = "FAILED"
                        test.summary = f"Agent error: {str(e)}"
                        test.ended_at = datetime.now(timezone.utc)
                        self.db.commit()
                except Exception as db_error:
                    self.db.rollback()
                    flask_app.logger.error(
                        f"Failed to update test {test_id} with error status: {db_error}"
                    )
            flask_app.logger.error(
                f"Agent background error for test {test_id}: {e}", exc_info=True
            )

    def _generate_plan(self, user_prompt: str, target_host: str, test_id: int):
        """
        Use the deep agent to generate a verification plan and execute it.

        This is the main event loop that runs in the background thread.
        The agent has access to tools to execute verification plans and update test results.
        """
        from db_models import Stream, Todo

        # Store test_id for tool access
        self.current_test_id = test_id

        # Create tool functions that have access to self
        def execute_verification_plan(plan_dsl: Dict[str, Any]) -> Dict[str, Any]:
            """Execute a verification plan on the target host."""
            return self._execute_verification_plan_tool(plan_dsl)

        def update_test(
            status: str,
            summary: str,
            target: Dict[str, Any] = None,
            prechecks: list = None,
            steps: list = None,
            postchecks: list = None,
            evidence: str = None,
        ) -> Dict[str, Any]:
            """Update the test record with new information."""
            return self._update_test_results_tool(
                status, summary, target, prechecks, steps, postchecks, evidence
            )

        runner = {
            "name": "runner-agent",
            "description": "Used to execute a verification plan and update test results",
            "system_prompt": "You are a hardware verification agent. Execute the plan given. Your supervisor can only see your FINAL MESSAGE. So include all the context of your actions, the results, the data to back it up and the final verdict. Constantly update the todo list when you start and end verification tasks. Before you finish, make sure that all todo items have been marked has successful or failed.",
            "tools": [get_catalog, execute_verification_plan],
        }
        # Create the agent with tools
        agent = create_deep_agent(
            tools=[get_catalog, update_test, execute_verification_plan],
            system_prompt=self.system_prompt,
            # system_prompt="Build and execute a verification plan for the target host as per the user's request. Keep the todo list updated with your tasks and progress.",
            model=model,
            backend=make_backend,
            subagents=[runner],
            store=self.store,
        )

        # Construct the prompt with target info
        full_prompt = f"""
{user_prompt}

Target host: {target_host}

Generate a verification plan for this target, use a runner to execute it, and then you will update the test results.

Fill the todo list with the verification tasks needed so your runner can stay on task and avoid distractions.
"""

        self.current_todos = None

        # Stream the agent execution - this is the main event loop
        for chunk in agent.stream(
            {"messages": [{"role": "user", "content": full_prompt}]},
            stream_mode=["messages", "updates"],
            subgraphs=True,
        ):
            if not isinstance(chunk, tuple) or len(chunk) != 3:
                continue

            namespace, stream_mode, data = chunk
            print(stream_mode, end="\r")
            if stream_mode == "updates":
                if not isinstance(data, dict):
                    continue
                chunk_data = list(data.values())[0] if data else None
                if chunk_data and isinstance(chunk_data, dict):
                    if "todos" in chunk_data:
                        from db_models import Todo, db

                        print("TODO UPDATE")
                        new_todos = chunk_data["todos"]
                        if new_todos != self.current_todos:
                            self.current_todos = new_todos
                            try:
                                # Remove old todos
                                Todo.query.filter(Todo.test_id == test_id).delete()
                                for todo_item in new_todos:
                                    todo = Todo(
                                        test_id=test_id,
                                        name=todo_item.get("content", "Unknown task"),
                                        status=todo_item.get("status", "pending"),
                                    )
                                    db.session.add(todo)
                                db.session.commit()
                            except Exception as e:
                                db.session.rollback()
                                flask_app.logger.error(f"Failed to write todos: {e}")
            elif stream_mode == "messages":
                self._process_message_chunk(data, test_id, namespace)
            else:
                print("mode: ", stream_mode, data)

    def _process_message_chunk(self, data: Any, test_id: int, namespace: str):
        """Process a message chunk and write to stream."""
        from db_models import Stream, db

        if not isinstance(data, tuple) or len(data) != 2:
            return
        message, _metadata = data
        temp = None
        if isinstance(message, HumanMessage):
            return

        if isinstance(message, ToolMessage):
            tool_name = getattr(message, "name", "")
            tool_status = getattr(message, "status", "success")
            tool_content = message.content

            print(f"[TOOL MESSAGE] {tool_name} ({tool_status}): {tool_content}")

        if not hasattr(message, "content_blocks"):
            return

        for block in message.content_blocks:
            if block["type"] == "text":
                if text := block["text"]:
                    self.content += text
                    # print(self.content)
        if getattr(message, "chunk_position", None) == "last":
            # Final chunk - write to stream
            try:
                # Use a fresh session for this operation
                stream = Stream(
                    test_id=test_id,
                    message=self.content,
                    meta={"type": "agent_message", "namespace": namespace},
                )

                db.session.add(stream)
                db.session.commit()
                print(f"\n[AGENT MESSAGE] {self.content}")
                temp = self.content
            except Exception as e:
                db.session.rollback()
                flask_app.logger.error(f"Failed to write agent message to stream: {e}")
            finally:
                self.content = ""
        return temp
        
    def _execute_verification_plan_tool(
        self, plan_dsl: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Tool for the agent to execute a verification plan.

        This runs synchronously in the background thread (no additional threads).
        """
        import asyncio

        try:
            dsl = ToDoDSL(**plan_dsl)
        except Exception as e:
            return {"error": f"Invalid DSL payload: {e}"}

        print(f"Got verification job submission: {plan_dsl}")

        # 1) Policy checks
        try:
            policy_gate(dsl, catalog)
        except Exception as e:
            return {"error": f"Policy gate failed: {e}"}

        # 2) Compile
        try:
            plan = compile_plan(dsl, catalog)
        except Exception as e:
            return {"error": f"Compile error: {e}"}

        # 3) Static safety audit
        try:
            for s in plan.steps:
                static_audit(s.cmd)
        except Exception as e:
            return {"error": f"Safety audit failed: {e}"}

        from db_models import Stream, Test

        test_id = self.current_test_id

        def on_event(ev: dict):
            """Callback to write events to DB Stream."""
            from db_models import Stream, db

            with flask_app.app_context():
                try:
                    # Use a fresh session for this operation
                    stream = Stream(
                        test_id=test_id,
                        message=ev.get("t", "event"),
                        meta=ev,
                    )
                    db.session.add(stream)
                    db.session.commit()
                except Exception as e:
                    db.session.rollback()
                    flask_app.logger.error(f"Failed to write stream event: {e}")

        # Update test status to EXECUTING
        # test = Test.query.get(test_id)
        # if test:
        #     test.status = "EXECUTING"
        #     self.db.commit()

        # Execute plan synchronously in this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            raw = loop.run_until_complete(
                execute_plan(
                    "raspberrypi.tail56986c.ts.net",
                    plan,
                    key_path="~/.ssh/runner_key",
                    user="verifier",
                    port=22,
                    on_event=on_event,
                )
            )
        except Exception as e:
            flask_app.logger.error(f"Execution failed: {e}")
            on_event({"t": "verdict", "status": "FAILED", "summary": str(e)})
            return {"status": "FAILED", "summary": f"Execution error: {e}"}
        finally:
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()

        # Parse & validate (sync)
        per_step = []
        ctx = dsl.context
        ok_all = True

        for step, rr in zip(plan.steps, raw):
            parser_fn = PARSERS.get(step.parser) if step.parser else None
            parsed = parser_fn(rr.stdout) if parser_fn else {"raw_len": len(rr.stdout)}
            step_ok = True
            note = ""

            if step.validator:
                v_name, args = _parse_validator_spec(step.validator)
                vfn = VALIDATORS.get(v_name)
                if vfn:
                    if v_name == "total_mem_within_pct" and not args:
                        exp = ctx.get("expected_total_gib") or ctx.get(
                            "expected", {}
                        ).get("total_gib", 16)
                        pct = ctx.get("pct", 2)
                        args = [exp, pct]
                    if v_name == "all_expected_dimms" and not args:
                        args = [ctx.get("expected_dimms", [])]

                    ok, note = vfn(parsed, *args)
                    step_ok = bool(ok)
                else:
                    step_ok = False
                    note = f"Unknown validator {v_name}"

            per_step.append({"id": step.id, "ok": step_ok, "notes": note})
            ok_all &= step_ok

        status = "SUCCESS" if ok_all else "FAILED"
        summary = "All criteria passed." if ok_all else "One or more criteria failed."

        # Create VerificationResult
        result = VerificationResult(
            status=status,
            summary=summary,
            details=VerificationDetail(per_step=per_step),
            evidence=[],
        )

        # Send final verdict event to stream
        on_event({"t": "verdict", "status": status, "summary": summary})

        return {
            "status": status,
            "summary": summary,
            "evidence": result.model_dump_json(),
            "per_step": per_step,
        }

    def _update_test_results_tool(
        self,
        status: str,
        summary: str,
        target: Dict[str, Any] = None,
        prechecks: list = None,
        steps: list = None,
        postchecks: list = None,
        evidence: str = None,
    ) -> Dict[str, Any]:
        """
        Tool for the agent to update the test record with final results.
        """
        from db_models import Test, Result
        with flask_app.app_context():
            test_id = self.current_test_id
            test = Test.query.get(test_id)

            if not test:
                return {"error": f"Test {test_id} not found"}

            # Update test record
            test.status = status
            test.summary = summary
            test.ended_at = datetime.now(timezone.utc)

            if target:
                test.target = target
            if prechecks:
                test.prechecks = prechecks
            if steps:
                test.steps = steps
            if postchecks:
                test.postchecks = postchecks
            if evidence:
                test.evidence = evidence

            # Create Result record
            result_record = Result(
                test_id=str(test_id),
                status=status,
                started_at=test.started_at,
                ended_at=test.ended_at,
                summary=summary,
                evidence=evidence or "{}",
            )
            self.db.add(result_record)
            self.db.commit()

            return {
                "success": True,
                "test_id": test_id,
                "status": status,
                "message": "Test results updated successfully",
            }


def create_test_from_prompt(
    db_session,
    store: PostgresStore,
    user_prompt: str,
    target_host: str,
    server_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Convenience function to create a test from a prompt.

    This is the main entry point from the Flask API.

    Args:
        db_session: SQLAlchemy database session
        store: PostgresStore instance
        user_prompt: User's natural language request
        target_host: Target host to test
        server_id: Optional server ID

    Returns:
        Dict with test_id and status
    """
    runner = AgentRunner(db_session, store)
    return runner.create_test_from_prompt(user_prompt, target_host, server_id)
