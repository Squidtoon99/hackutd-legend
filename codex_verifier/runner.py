import json
import threading
import queue
import asyncio
from typing import Dict, Callable

from flask import Flask, request, Response, abort

from .models import ToDoDSL, VerificationResult, VerificationDetail
from .preflight import Catalog, compile_plan
from .exec_pool import execute_plan
from .preflight import policy_gate, static_audit

# Parsers & validators
from .parsers import (
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
from .validators import (
    total_mem_within_pct,
    all_expected_dimms,
    nic_link_up,
    nic_speed_at_least,
    nic_no_errors,
    disk_smart_pass,
    no_critical_logs,
)

app = Flask(__name__)
catalog = Catalog.load()

# In-memory job store
JOBS: Dict[str, Dict] = {}

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


def sse_fmt(ev: dict) -> bytes:
    return f"data: {json.dumps(ev)}\n\n".encode()


@app.post("/runner/jobs")
def submit_job():
    try:
        payload = request.get_json(force=True, silent=False)
        dsl = ToDoDSL(**payload)
    except Exception as e:
        abort(400, f"Invalid DSL payload: {e}")

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

    # 4) Create job and start background worker
    job_id = dsl.job_id
    if job_id in JOBS:
        abort(409, "job_id already exists")

    evq: queue.Queue = queue.Queue()
    JOBS[job_id] = {"dsl": dsl, "plan": plan, "events": evq, "result": None}

    t = threading.Thread(target=_run_job_thread, args=(job_id,), daemon=True)
    t.start()

    return {"job_id": job_id}, 202


@app.get("/runner/jobs/<job_id>/events")
def stream_events(job_id: str):
    if job_id not in JOBS:
        abort(404, "Unknown job_id")
    evq: queue.Queue = JOBS[job_id]["events"]
    plan = JOBS[job_id]["plan"]

    def gen():
        # Initial plan preview
        yield sse_fmt(
            {"t": "plan_preview", "plan": {"steps": [s.dict() for s in plan.steps]}}
        )
        # Stream events until verdict
        while True:
            ev = evq.get()  # blocking
            yield sse_fmt(ev)
            if ev.get("t") == "verdict":
                break

    return Response(gen(), mimetype="text/event-stream")


@app.get("/runner/jobs/<job_id>/result")
def get_result(job_id: str):
    if job_id not in JOBS:
        abort(404, "Unknown job_id")
    res: VerificationResult = JOBS[job_id]["result"]
    if res is None:
        abort(404, "Result not ready")
    return res.dict()


# ------------------------
# Background job execution
# ------------------------


def _run_job_thread(job_id: str):
    """Runs the SSH execution + parse + validate pipeline in a thread.
    Uses its own asyncio loop to await the async SSH executor.
    """
    bundle = JOBS[job_id]
    dsl = bundle["dsl"]
    plan = bundle["plan"]
    evq: queue.Queue = bundle["events"]

    def on_event(ev: dict):
        try:
            evq.put_nowait(ev)
        except Exception:
            pass

    # Create and run a private asyncio loop in this thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        raw = loop.run_until_complete(
            execute_plan(
                dsl.target.host,
                plan,
                key_path="~/.ssh/runner_key",
                user="verifier",
                on_event=on_event,
            )
        )
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
            # support "validator_name(args...)" or plain "validator_name"
            v_name, args = _parse_validator_spec(step.validator)
            vfn = VALIDATORS.get(v_name)
            if vfn:
                # supply context-driven defaults where needed
                if v_name == "total_mem_within_pct" and not args:
                    exp = ctx.get("expected_total_gib") or ctx.get("expected", {}).get(
                        "total_gib"
                    )
                    pct = ctx.get("pct", 2)
                    args = [exp, pct]
                if v_name == "all_expected_dimms" and not args:
                    args = [ctx.get("expected_dimms", [])]

                ok, note = vfn(parsed, *args)  # type: ignore
                step_ok = bool(ok)
            else:
                step_ok = False
                note = f"Unknown validator {v_name}"

        per_step.append({"id": step.id, "ok": step_ok, "notes": note})
        ok_all &= step_ok

    status = "SUCCESS" if ok_all else "FAILED"
    summary = "All criteria passed." if ok_all else "One or more criteria failed."
    result = VerificationResult(
        status=status,
        summary=summary,
        details=VerificationDetail(per_step=per_step),
        evidence=[],
    )
    bundle["result"] = result
    evq.put({"t": "verdict", "status": status, "summary": summary})


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


# -------------
# Dev server
# -------------
if __name__ == "__main__":
    # Run: python runner.py
    # Then:
    #   POST  /runner/jobs
    #   GET   /runner/jobs/<job_id>/events
    #   GET   /runner/jobs/<job_id>/result
    app.run(host="0.0.0.0", port=8081, threaded=True)
