import asyncio
import time
import traceback
from typing import List

import asyncssh
from .models import ExecPlan, RawResult, ToDoDSL, ToDoStep

OUTPUT_CAP = 262144  # 256 KiB
ERR_CAP = 131072  # 128 KiB


async def run_cmd(
    host: str, cmd: str, timeout: int, key_path: str, user: str, port: int
) -> RawResult:
    start = time.time()
    try:
        async with asyncssh.connect(
            host=host,
            port=port,
            username=user,
            client_keys=[key_path],
            known_hosts=None,
            request_pty=False,
        ) as conn:
            res = await asyncio.wait_for(conn.run(cmd, check=False), timeout=timeout)
            out = (res.stdout or "")[:OUTPUT_CAP]
            err = (res.stderr or "")[:ERR_CAP]
            print(res)
            return RawResult(
                step_id="",
                exit_code=res.exit_status,
                stdout=out,
                stderr=err,
                duration_ms=int((time.time() - start) * 1000),
                truncated=(len(res.stdout or "") > OUTPUT_CAP)
                or (len(res.stderr or "") > ERR_CAP),
            )
    except asyncio.TimeoutError:
        return RawResult(
            step_id="",
            exit_code=124,
            stdout="",
            stderr="TIMEOUT",
            duration_ms=int((time.time() - start) * 1000),
        )
    except Exception as e:
        traceback.print_exc()
        return RawResult(
            step_id="",
            exit_code=255,
            stdout="",
            stderr=str(e),
            duration_ms=int((time.time() - start) * 1000),
        )


async def execute_plan(
    host: str, plan: ExecPlan, key_path: str, user: str, port: int = 22, on_event=None
) -> List[RawResult]:
    results = []
    for s in plan.steps:
        if on_event:
            on_event({"t": "step_start", "id": s.id, "cmd": s.cmd})
        rr = await run_cmd(host, s.cmd, s.timeout_s, key_path, user, port=port)
        rr.step_id = s.id
        if on_event:
            print("Step result: ", rr)
            on_event(
                {
                    "t": "step_result",
                    "id": s.id,
                    "exit": rr.exit_code,
                    "ms": rr.duration_ms,
                }
            )
        results.append(rr)
    return results


def critic_propose_patch(dsl: ToDoDSL, failure: dict) -> ToDoDSL | None:
    """Very small heuristic patcher to add a clarifier/fallback step."""
    comp = dsl.context.get("component")
    if comp == "nic" and failure.get("parser") == "parse_ethtool":
        iface = next(
            (s.args.get("iface") for s in dsl.steps if s.action.startswith("read_nic")),
            "eth0",
        )
        patch = ToDoStep(
            id="s_fallback_sysfs",
            action="read_sysfs_nic",
            args={"iface": iface},
            timeout_s=5,
            parser="parse_sysfs_nic",
            validator=None,
        )
        if not any(s.id == patch.id for s in dsl.steps):
            dsl.steps.append(patch)
            return dsl
    return None
