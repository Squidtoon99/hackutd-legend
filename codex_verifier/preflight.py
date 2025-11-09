import yaml
from typing import Dict
from .models import ToDoDSL, ExecPlan, ExecStep


class Catalog:
    def __init__(self, data: Dict):
        self.data = data
        self.actions = data.get("actions", {})
        self.validators = data.get("validators", {})
        self.profiles = data.get("profiles", {})

    @staticmethod
    def load(path="catalog.yaml") -> "Catalog":
        with open(path, "r") as f:
            return Catalog(yaml.safe_load(f))


def compile_plan(dsl: ToDoDSL, catalog: Catalog) -> ExecPlan:
    steps: list[ExecStep] = []
    for step in dsl.steps:
        if step.action not in catalog.actions:
            raise ValueError(f"Unknown action: {step.action}")
        entry = catalog.actions[step.action]
        cmd_tpl: str = entry["cmd"]
        # Safe formatting: only keys present in args/target
        fmt_vars = {**step.args, "host": dsl.target.host}
        try:
            cmd = cmd_tpl.format(**fmt_vars)
        except KeyError as e:
            raise ValueError(f"Missing arg {e} for action {step.action}")
        steps.append(
            ExecStep(
                id=step.id,
                cmd=cmd,
                timeout_s=min(
                    step.timeout_s, catalog.profiles[dsl.profile]["max_timeout_s"]
                ),
                parser=step.parser or entry.get("parser"),
                validator=step.validator,
            )
        )
    return ExecPlan(steps=steps)


DENY_PATTERNS = [
    " rm ",
    " mkfs",
    " dd ",
    " :(){:|:&};:",
    "shutdown",
    "reboot",
    "iptables",
    "sysctl -w ",
    "chown ",
    "chmod ",
]


def policy_gate(dsl: ToDoDSL, catalog: Catalog) -> None:
    if dsl.profile not in catalog.profiles:
        raise ValueError(f"Unknown profile {dsl.profile}")
    # Ensure every action exists and is read-only
    for s in dsl.steps:
        a = catalog.actions.get(s.action)
        if not a:
            raise ValueError(f"Unknown action {s.action}")
        if not a.get("read_only", False):
            raise ValueError(f"Action {s.action} is not read-only")
        # sudo checks
        if a.get("requires_sudo"):
            allowed = catalog.profiles[dsl.profile].get("allow_sudo", [])
            # crude check: ensure binary path is allowed
            bin_path = a["cmd"].split()[2] if a["cmd"].startswith("sudo") else ""
            if bin_path not in allowed:
                raise ValueError(
                    f"sudo binary not allowed for action {s.action}: {bin_path}"
                )
    # success criteria format (optional, relaxed)


def static_audit(exec_cmd: str) -> None:
    low = f" {exec_cmd} ".lower()
    for p in DENY_PATTERNS:
        if p in low:
            raise ValueError(f"Denied pattern in cmd: {p.strip()}")
