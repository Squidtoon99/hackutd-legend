import re
from typing import Dict


def parse_meminfo(text: str) -> Dict:
    m = re.search(r"MemTotal:\s+(\d+)\s+kB", text)
    gib = (int(m.group(1)) / (1024**2)) if m else 0.0
    return {"total_gib": round(gib, 2)}


def parse_dmidecode(text: str) -> Dict:
    # Minimal: extract Memory Device blocks
    slots = []
    block = []
    for line in text.splitlines():
        if line.strip().startswith("Memory Device"):
            if block:
                slots.append(_parse_memdev_block(block))
                block = []
        block.append(line)
    if block:
        slots.append(_parse_memdev_block(block))
    return {"dimms": [s for s in slots if s]}


def _parse_memdev_block(lines):
    get = lambda k: next(
        (l.split(":", 1)[1].strip() for l in lines if l.strip().startswith(k)), None
    )
    size = get("Size")
    if not size or size.lower().startswith("no module"):
        return None
    speed = get("Configured Memory Speed") or get("Speed") or ""
    typ = get("Type") or ""
    loc = get("Locator") or get("Bank Locator") or ""
    ecc = (get("Error Correction Type") or "").lower() in [
        "single-bit ecc",
        "multi-bit ecc",
        "multi-bit, single-bit ecc",
        "ecc",
    ]

    def to_gib(s):
        try:
            if "MB" in s:
                return round(float(s.split()[0]) / 1024, 2)
            if "GB" in s:
                return float(s.split()[0])
        except:
            return None

    def to_mt(s):
        try:
            return int(re.search(r"(\d+)", s).group(1))
        except:
            return None

    return {
        "slot": loc,
        "size_gib": to_gib(size),
        "speed_mt": to_mt(speed),
        "type": typ,
        "ecc": ecc,
    }


def parse_ethtool(text: str) -> Dict:
    link = "up" if re.search(r"Link detected:\s*yes", text, re.I) else "down"
    sp = re.search(r"Speed:\s*(\d+)\s*Mb/s", text)
    gbps = int(sp.group(1)) / 1000 if sp else None
    return {"link": link, "speed_gbps": gbps}


def parse_ethtool_stats(text: str) -> Dict:
    errs = {}
    for line in text.splitlines():
        if any(k in line for k in ["err", "drop", "fault"]):
            parts = line.strip().split()
            if len(parts) >= 2 and parts[-1].isdigit():
                errs[parts[0]] = int(parts[-1])
    return {"errors": errs}


def parse_sysfs_nic(text: str) -> Dict:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    state = lines[0] if lines else "unknown"
    speed = int(lines[1]) if len(lines) > 1 and lines[1].isdigit() else None
    return {
        "link": "up" if state == "up" else "down",
        "speed_gbps": (speed / 1000 if speed else None),
    }


def parse_smart(text: str) -> Dict:
    ok = "PASSED" in text.upper()
    return {"smart_pass": ok}


def parse_ipmi_psu(text: str) -> Dict:
    ok = not any("fail" in l.lower() for l in text.splitlines())
    return {"psu_ok": ok}


def parse_ipmi_fans(text: str) -> Dict:
    return {"fan_lines": len(text.splitlines())}


def parse_ipmi_thermal(text: str) -> Dict:
    return {"thermal_lines": len(text.splitlines())}


def parse_dmesg(text: str) -> Dict:
    crit = [
        l
        for l in text.splitlines()
        if re.search(r"(fatal|panic|mce|uncorrected)", l, re.I)
    ]
    return {"critical": crit}


def parse_os_release(text: str) -> Dict:
    return {
        "os_release": {
            k: v for k, v in (x.split("=", 1) for x in text.splitlines() if "=" in x)
        }
    }
