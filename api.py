import os
import sys
from datetime import datetime, timezone
import json
import threading
import asyncio
import time

from flask import Flask, jsonify, request, Response, render_template, abort
from flask_cors import CORS
from typing import TYPE_CHECKING

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# create the app
app = Flask(__name__)

CORS(app)
# configure the database. Prefer a Neon/Postgres URL from the environment
# (commonly set as DATABASE_URL). Fall back to a local sqlite file for dev.
db_url = os.environ.get("DEV_POSTGRES_URI")
if not db_url:
    raise RuntimeError(
        "DEV_POSTGRES_URI environment variable is not set. Set it to your Neon/Postgres connection string."
    )
app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Ensure project root is on sys.path so sibling package `db_models` can be imported
ROOT = os.path.dirname(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# import the shared db and models from the db_models package
if TYPE_CHECKING:
    from codex_verifier.models import VerificationResult
from db_models import db, Server, Stream, Test, Ticket, Todo, Result

# initialize the db extension with the app
db.init_app(app)


# --- routes ---
@app.route("/")
def index():
    return "Hello, World!"


@app.route("/server/<server_id>", methods=["GET"])
def get_server_info(server_id):
    server = Server.query.get(server_id)
    if not server:
        return jsonify({"error": "Server not found"}), 404
    tickets = Ticket.query.filter_by(server_id=server_id).all()
    return jsonify(
        {"server": server.to_dict(), "tickets": [t.to_dict() for t in tickets]}
    )


@app.route("/server/<server_id>/tests", methods=["GET"])
def get_server_tests(server_id):
    tests = Test.query.filter_by(server_id=server_id).all()
    todos = Todo.query.filter(Todo.test_id.in_([t.id for t in tests])).all()
    return jsonify([{"test": t.to_dict(), "todos": [td.to_dict() for td in todos if td.test_id == t.id]} for t in tests])


@app.route("/server/tickets", methods=["GET"])
def get_ticket_counts():
    ticket_counts = (
        db.session.query(Ticket.server_id, db.func.count(Ticket.id))
        .group_by(Ticket.server_id)
        .all()
    )
    return jsonify({server_id: count for server_id, count in ticket_counts})


@app.route("/tests/create", methods=["POST"])
def create_test():
    """Create a new test."""
    req = request.get_json()
    test = Test(
        server_id=req.get("server_id"),
        name=req.get("name", "test"),
        status="running",
        started_at=datetime.now(),
    )
    db.session.add(test)
    db.session.commit()
    return jsonify(test.to_dict()), 201


@app.route("/tests", methods=["GET"])
def get_tests():
    tests = Test.query.all()
    return jsonify([t.to_dict() for t in tests])


@app.route("/tests/<test_id>", methods=["GET"])
def get_test(test_id):
    test = Test.query.get(test_id)
    if not test:
        return jsonify({"error": "Test not found"}), 404
    todo = Todo.query.filter_by(test_id=test_id).all()

    return jsonify({"test": test.to_dict(), "todo": [t.to_dict() for t in todo]})


@app.route("/tests/<test_id>/stream", methods=["GET"])
def get_test_stream(test_id):
    streams = (
        Stream.query.filter_by(test_id=test_id).order_by(Stream.timestamp.asc()).all()
    )
    return jsonify([s.to_dict() for s in streams])


@app.route("/tests/build", methods=["POST"])
def build_test():
    """
    Build a test using the deep agent.

    Accepts:
        - prompt: Natural language test request (e.g., "Run test xyz")
        - target_host: Target host to test (e.g., "raspberrypi.local")
        - server_id: (optional) Server ID for tracking

    Returns:
        - test_id: Unique test identifier
        - status: "success" or "error"
        - message: Status message
    """
    req = request.get_json()

    if not req:
        return jsonify({"error": "Request body required"}), 400

    prompt = req.get("prompt")
    target_host = req.get("target_host")

    if not prompt:
        return jsonify({"error": "prompt is required"}), 400
    if not target_host:
        return jsonify({"error": "target_host is required"}), 400

    server_id = req.get("server_id")

    try:
        # Import deep agent integration
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "deep_agent"))
        from agent_runner import create_test_from_prompt
        from langgraph.store.postgres import PostgresStore

        # Create PostgresStore for agent persistence
        postgres_uri = app.config["SQLALCHEMY_DATABASE_URI"]

        with PostgresStore.from_conn_string(postgres_uri) as store:
            # Run the agent
            result = create_test_from_prompt(
                db_session=db.session,
                store=store,
                user_prompt=prompt,
                target_host=target_host,
                server_id=server_id,
            )

        status_code = 201 if result["status"] == "success" else 500
        return jsonify(result), status_code

    except Exception as e:
        app.logger.error(f"Error building test: {e}", exc_info=True)
        return (
            jsonify({"status": "error", "message": f"Failed to build test: {str(e)}"}),
            500,
        )


@app.route("/server/create", methods=["POST"])
def create_server():
    """Create a new server."""
    req = request.get_json()
    app.logger.debug("create_server payload: %s", req)
    server = Server(id=req.get("id"), status="active")
    db.session.add(server)
    db.session.commit()
    return jsonify(server.to_dict()), 201


@app.route("/tests/<test_id>/streams", methods=["GET"])
def get_streams_for_test(test_id):
    """Return all stream messages for a given test id as JSON list.

    Example: GET /tests/abc-123/streams
    """
    # Query DB for streams with matching test_id
    streams = (
        Stream.query.filter_by(test_id=test_id).order_by(Stream.timestamp.asc()).all()
    )

    return jsonify([s.to_dict() for s in streams])


# --- Codex Verifier Routes ---


def sse_fmt(ev: dict) -> bytes:
    """Format event dict as Server-Sent Event."""
    return f"data: {json.dumps(ev)}\n\n".encode()


@app.route("/verifier/tests/create", methods=["GET"])
def create_verifier_test():
    req = request.get_json()
    print(req)
    print("\nCreating verifier test\n")
    return jsonify({"id": 1}), 201


@app.route("/verifier/jobs", methods=["POST"])
def submit_verification_job():
    """Submit a verification job (codex_verifier integration).

    Expects a ToDoDSL JSON payload. Creates a Test record and runs verification
    in the background, writing Stream events and Result to Postgres.
    """
    try:
        payload = request.get_json(force=True, silent=False)
        dsl = ToDoDSL(**payload)
    except Exception as e:
        abort(400, f"Invalid DSL payload: {e}")

    print(f"Got verification job submission: {payload}")
    # 1) Policy checks
    try:
        policy_gate(dsl, catalog)
    except Exception as e:
        abort(400, f"Policy gate failed: {e}")

    # 2) Compile
    try:
        plan = compile_plan(dsl, catalog)
    except Exception as e:
        abort(400, f"Compile error: {e}")

    # 3) Static safety audit
    try:
        for s in plan.steps:
            static_audit(s.cmd)
    except Exception as e:
        abort(400, f"Safety audit failed: {e}")

    job_id = dsl.job_id
    # check if job_id already exists in the DB
    existing_test = Test.query.filter_by(name=job_id).first()
    if existing_test:
        return jsonify(message="Job ID already exists"), 409

    # 4) Create Test record in database
    test = Test(
        server_id=dsl.target.host,
        name=dsl.job_id,
        status="QUEUED",
        started_at=datetime.now(timezone.utc),
        target=dsl.target.model_dump_json(),
        context=dsl.context,
        prechecks=dsl.prechecks,
        steps=[s.model_dump_json() for s in dsl.steps],
        postchecks=dsl.postchecks,
    )
    db.session.add(test)
    db.session.commit()
    test_id = test.id

    # 5) Create job tracking and start background worker

    JOBS[job_id] = {
        "dsl": dsl,
        "plan": plan,
        "result": None,
        "test_id": test_id,
    }

    t = threading.Thread(target=_run_verification_job, args=(job_id,), daemon=True)
    t.start()

    return jsonify({"job_id": job_id, "test_id": test_id}), 202


@app.route("/verifier/jobs/<job_id>/events", methods=["GET"])
def stream_verification_events(job_id: str):
    """Stream SSE events for a verification job from the database.

    This endpoint streams events from the Stream table, allowing clients to:
    - Reconnect and get all events from the beginning
    - Poll for updates without maintaining in-memory state
    - Access historical event streams
    """
    # Look up the test_id for this job
    if job_id not in JOBS:
        # Try to find the test by name (job_id is stored as test name)
        test = Test.query.filter_by(name=job_id).first()
        if not test:
            abort(404, "Unknown job_id")
        test_id = test.id
    else:
        test_id = JOBS[job_id]["test_id"]

    import time

    def gen():
        """Generator that streams events from database."""
        last_id = 0  # Track the last event ID we've seen
        test = Test.query.get(test_id)

        # Send initial plan preview if test has steps
        if test and test.steps:
            yield sse_fmt(
                {
                    "t": "plan_preview",
                    "plan": {"steps": test.steps},
                }
            )

        # Poll for new stream events
        while True:
            # Fetch new stream events since last_id
            new_streams = (
                Stream.query.filter_by(test_id=test_id)
                .filter(Stream.id > last_id)
                .order_by(Stream.timestamp.asc())
                .all()
            )

            for stream in new_streams:
                # Send the event
                if stream.meta:
                    yield sse_fmt(stream.meta)
                else:
                    # Fallback if meta is not available
                    yield sse_fmt({"t": stream.message, "id": stream.id})

                last_id = stream.id

                # Check if this is the final verdict
                if stream.meta and stream.meta.get("t") == "verdict":
                    return  # Stop streaming

            # Check test status to see if we should stop
            test = Test.query.get(test_id)
            if test and test.status in ["SUCCESS", "FAILED"]:
                # Job completed, check if we've sent the verdict
                final_verdict = (
                    Stream.query.filter_by(test_id=test_id)
                    .filter(Stream.id > last_id)
                    .order_by(Stream.timestamp.asc())
                    .first()
                )
                if not final_verdict:
                    # No more events and job is done, stop streaming
                    return

            # Wait a bit before checking again
            time.sleep(0.5)

    return Response(gen(), mimetype="text/event-stream")


@app.route("/verifier/jobs/<job_id>/result", methods=["GET"])
def get_verification_result(job_id: str):
    """Get final result for a verification job."""
    if job_id not in JOBS:
        abort(404, "Unknown job_id")
    res: "VerificationResult" = JOBS[job_id]["result"]
    if res is None:
        abort(404, "Result not ready")
    return jsonify(res.dict())


# create tables at startup
with app.app_context():
    db.create_all()


if __name__ == "__main__":
    app.run(debug=True)
