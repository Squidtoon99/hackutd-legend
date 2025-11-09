from typing import Dict, Tuple


def ok_note(ok: bool, note: str) -> Tuple[bool, str]:
    return ok, note


def total_mem_within_pct(parsed: Dict, expected_gib: float = 16.0, pct: float = 2.0):
    actual = parsed.get("total_gib", 0) or 0
    ok = abs(actual - expected_gib) <= expected_gib * (pct / 100.0)
    return ok_note(ok, f"MemTotal {actual} GiB vs expected {expected_gib} ±{pct}%")


def all_expected_dimms(parsed: Dict, expected_dimms: list[Dict]):
    have = {
        (
            d["slot"],
            round(d.get("size_gib") or 0, 2),
            d.get("speed_mt"),
            bool(d.get("ecc")),
        )
        for d in parsed.get("dimms", [])
        if d
    }
    missing = []
    for e in expected_dimms:
        tup = (
            e["slot"],
            round(e["size_gib"], 2),
            e.get("speed_mt"),
            bool(e.get("ecc", True)),
        )
        if tup not in have:
            missing.append(e["slot"])
    ok = len(missing) == 0
    return ok_note(ok, "All DIMMs present" if ok else f"Missing/mismatch: {missing}")


def nic_link_up(parsed: Dict):
    ok = parsed.get("link") == "up"
    return ok_note(ok, f"Link {parsed.get('link')}")


def nic_speed_at_least(parsed: Dict, gbps: int):
    sp = parsed.get("speed_gbps") or 0
    ok = sp >= gbps
    return ok_note(ok, f"Speed {sp} Gbps >= {gbps}")


def nic_no_errors(parsed: Dict):
    errs = parsed.get("errors", {})
    bad = {k: v for k, v in errs.items() if v > 0}
    ok = len(bad) == 0
    return ok_note(ok, "No NIC error counters > 0" if ok else f"Errors: {bad}")


def disk_smart_pass(parsed: Dict):
    ok = bool(parsed.get("smart_pass"))
    return ok_note(ok, "SMART PASSED" if ok else "SMART not passed")


def no_critical_logs(parsed: Dict):
    crit = parsed.get("critical", [])
    ok = len(crit) == 0
    return ok_note(
        ok, "No critical dmesg entries" if ok else f"{len(crit)} critical lines"
    )
