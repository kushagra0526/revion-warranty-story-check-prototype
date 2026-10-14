"""Pre-submit check of an AI-written repair-order story (complaint / cause / correction).

Evidence: what the technician said (voice transcript, spoken forms), the scan-tool report, the RO lines.
Rules: GM Service Bulletin 06-00-89-026J (Warranty Administration, Nov 2012, public on NHTSA) and
GM TechLink on battery tester codes. Every finding cites its evidence line and rule.

READY  nothing to fix
FIX    incomplete story / RO housekeeping (the claim would be weak)
HOLD   a fact that isn't backed or contradicts the evidence, or a rule the claim would be charged back on
"""
import re

from .facts import conditions, extract

GM_3C = "GM bulletin 06-00-89-026J (3C fields)"
GM_CCND = "GM bulletin 06-00-89-026J (CCND labor ops)"
GM_BATT = "GM TechLink: battery tester code"
AUDIT = "dealer burden of proof; time punches"
HOLD = {"UNSUPPORTED", "CONTRADICTED", "J9992_NO_PCODE", "J9992_BAD_CODE", "CCND_NO_APPROVAL", "BATTERY_NO_CODE",
        "BATTERY_CODE_INVALID", "BATTERY_CODE_REUSED", "BATTERY_CODE_VIN", "NO_PUNCH"}
RECAP = re.compile(r"\b(per (the )?(si|service information|procedure)|followed (the )?(si|procedure|diagnostics)|verified (the )?repair|repair verified|replaced and verified|performed repair)\b", re.I)
CCND = re.compile(r"^[A-Z]999\d$")


def label(kind, v):
    if kind == "meas":
        return f"{v[0]:g} {v[1]}"
    if kind == "cyl":
        return f"cylinder {v}"
    return str(v)


def evidence(ro):
    """-> {(kind, value): citation} from transcript turns, scan report, RO lines."""
    ev = {}
    for i, turn in enumerate(ro["transcript"]):
        for k, v, _ in extract(turn["text"], spoken=True):
            ev.setdefault((k, v), f"transcript turn {i + 1} ({turn['who']})")
    for d in ro["scan"]["dtcs"]:
        ev.setdefault(("dtc", d["code"]), f"scan report: {d['code']} {d['status']}")
        m = re.fullmatch(r"P030([1-8])", d["code"])
        if m:
            ev.setdefault(("cyl", int(m.group(1))), f"scan report: {d['code']} = cylinder {m.group(1)}")
    for p in ro["parts"]:
        ev.setdefault(("pn", p["pn"]), f"RO part line: {p['pn']} {p['desc']}")
    return ev


def _ndiff(a, b):
    return sum(x != y for x, y in zip(a, b)) + abs(len(a) - len(b))


def check(ro, used_battery_codes=()):
    story = ro["story"]
    ev = evidence(ro)
    found = []

    def add(code, msg, cite, rule):
        found.append({"code": code, "msg": msg, "cite": cite, "rule": rule, "level": "HOLD" if code in HOLD else "FIX"})

    # 1. every fact in the story is backed
    story_facts = {}
    for part in ("complaint", "cause", "correction"):
        for k, v, txt in extract(story[part]):
            story_facts.setdefault((k, v), (part, txt))
    for (k, v), (part, txt) in story_facts.items():
        if (k, v) in ev:
            continue
        same = [(kk, vv) for (kk, vv) in ev if kk == k and (k != "meas" or vv[1] == v[1])]
        if k == "meas":
            near = [vv for _, vv in same if abs(vv[0] - v[0]) <= 0.011 * max(1.0, abs(v[0]))]
            if near:
                continue
        if k == "pn":
            same = [s for s in same if _ndiff(s[1], v) <= 2]
        if k == "dtc":
            same = [s for s in same if s[1][:4] == v[:4]]
        if same:
            alt = ", ".join(label(*s) for s in same[:3])
            add("CONTRADICTED", f"{part} says {label(k, v)}; the evidence says {alt}", ev[same[0]], GM_3C)
        else:
            add("UNSUPPORTED", f"{part} says {label(k, v)}, which the technician never said and no scan/RO line shows", "none", GM_3C)

    # 2. completeness (GM 3C: complaint conditions, DTC in cause, measurements in correction, no recap)
    said_cond = set()
    for turn in ro["transcript"]:
        said_cond |= conditions(turn["text"])
    told = conditions(story["complaint"])  # GM: the complaint description carries the conditions
    for c in sorted(said_cond - told):
        add("MISSING_CONDITION", f"complaint leaves out '{c.replace('_', ' ')}', which the technician/customer described", "transcript", GM_3C)
    stored = [d["code"] for d in ro["scan"]["dtcs"] if d["status"] == "stored"]
    story_dtcs = {v for (k, v) in story_facts if k == "dtc"}
    if stored and not story_dtcs & set(stored):
        add("CAUSE_NO_DTC", f"cause doesn't name the stored DTC {', '.join(stored)}", f"scan report: {', '.join(stored)} stored", GM_3C)
    for (k, v), cite in ev.items():
        if k in ("meas", "conn", "circ", "sidoc") and cite.startswith("transcript") and (k, v) not in story_facts:
            add("MISSING_FACT", f"correction leaves out {label(k, v)}", cite, GM_3C)
    corr_facts = [kv for kv, (part, _) in story_facts.items() if part == "correction" and kv[0] in ("meas", "dtc", "conn", "circ", "sidoc", "pn")]
    if not corr_facts and RECAP.search(story["correction"]):
        add("RECAP_ONLY", "correction recaps the procedure with no measurements, codes or document id", "story", GM_3C)

    # 3. RO lines
    ops = ro["ops"]
    for op in ops:
        code = op["op"]
        if code == "J9992":
            dep = op.get("dep_dtc")
            if not dep:
                add("J9992_NO_PCODE", "J9992 needs the engine P-code in the labor-code dependency field", "RO op J9992", GM_CCND)
            elif not dep.startswith("P") or dep == "P0700":
                add("J9992_BAD_CODE", f"J9992 dependency {dep} is not allowed (engine P-codes only; P0700 is transmission)", "RO op J9992", GM_CCND)
            elif dep not in {d["code"] for d in ro["scan"]["dtcs"]}:
                add("J9992_NO_PCODE", f"J9992 dependency {dep} is not in the scan report", "RO op J9992", GM_CCND)
        if CCND.match(code):
            if not 0.1 <= op["hours"] <= 0.3 + 1e-9:
                add("CCND_HOURS", f"{code} claims {op['hours']} h; CCND allowance is 0.1–0.3 h", f"RO op {code}", GM_CCND)
            if not op.get("approval"):
                add("CCND_NO_APPROVAL", f"{code} has no service-manager approval noted", f"RO op {code}", GM_CCND)
            punched = sum(p["hours"] for p in ro["punches"] if p["op"] == code)
            if punched and punched + 1e-9 < op["hours"]:
                add("CCND_CLOCK", f"{code} claims {op['hours']} h but the clock shows {punched:.1f} h", f"RO op {code}", GM_CCND)
            for other in ops:
                if other is not op and other["op"][0] == code[0] and not CCND.match(other["op"]):
                    add("CCND_SAME_GROUP", f"{code} on the same RO as {other['op']} (same group)", f"RO ops {code}, {other['op']}", GM_CCND)
        if op["hours"] > 0 and not any(p["op"] == code for p in ro["punches"]):
            add("NO_PUNCH", f"{code} claims {op['hours']} h with no technician time punch", f"RO op {code}", AUDIT)
    text = " ".join(story.values()).lower()
    for p in ro["parts"]:
        if p.get("causal") and p["pn"] not in text and not any(w in text for w in p["desc"].lower().split() if len(w) > 3):
            add("CAUSAL_PART_NOT_IN_STORY", f"causal part {p['pn']} {p['desc']} isn't named in the story", f"RO part line {p['pn']}", GM_3C)
    if any("battery" in p["desc"].lower() for p in ro["parts"]):
        bc = ro.get("battery_code")
        if not bc:
            add("BATTERY_NO_CODE", "battery replaced with no tester warranty code", "RO", GM_BATT)
        else:
            code = bc["code"]
            if len(code) not in (15, 20) or re.search(r"[IOYZ]|[^A-Z0-9]", code):
                add("BATTERY_CODE_INVALID", f"tester code {code} is not 15/20 characters without I, O, Y, Z", "RO battery code", GM_BATT)
            if code in used_battery_codes:
                add("BATTERY_CODE_REUSED", f"tester code {code} was already used on another claim", "claims history", GM_BATT)
            if bc.get("vin") != ro["vin"]:
                add("BATTERY_CODE_VIN", f"tester printout VIN {bc.get('vin')} doesn't match the RO VIN {ro['vin']}", "RO battery code", GM_BATT)
    verdict = "HOLD" if any(f["level"] == "HOLD" for f in found) else "FIX" if found else "READY"
    return {"verdict": verdict, "findings": found, "repaired": repair(ro, found, ev, story_facts)}


def repair(ro, found, ev, story_facts):
    """Story rebuilt from grounded facts: wrong values replaced, unbacked sentences dropped, gaps filled."""
    st = {k: v for k, v in ro["story"].items()}
    bad = {}
    for f in found:
        if f["code"] in ("UNSUPPORTED", "CONTRADICTED"):
            bad[f["msg"]] = f
    for part in st:
        sents = re.split(r"(?<=[.;])\s+", st[part])
        keep = []
        for s in sents:
            facts = extract(s)
            if any((k, v) not in ev and not (k == "meas" and any(kk == "meas" and vv[1] == v[1] and abs(vv[0] - v[0]) <= 0.011 * max(1, abs(v[0])) for kk, vv in ev))
                   for k, v, _ in facts):
                continue
            keep.append(s)
        st[part] = " ".join(keep)
    miss_c = [f["msg"].split("'")[1] for f in found if f["code"] == "MISSING_CONDITION"]
    if miss_c:
        st["complaint"] = (st["complaint"].rstrip(". ") + ". Occurs: " + ", ".join(miss_c) + ".").strip()
    stored = [d["code"] for d in ro["scan"]["dtcs"] if d["status"] == "stored"]
    if any(f["code"] == "CAUSE_NO_DTC" for f in found) or not re.search(r"[PBCU][0-3][0-9A-F]{3}", st["cause"]):
        if stored:
            st["cause"] = (st["cause"].rstrip(". ") + f". DTC {', '.join(stored)} stored.").strip(". ") + "."
    add = [label(k, v) for (k, v), cite in ev.items() if k in ("meas", "conn", "circ", "sidoc") and cite.startswith("transcript")
           and label(k, v) not in st["correction"]]
    if add:
        st["correction"] = (st["correction"].rstrip(". ") + ". Recorded: " + "; ".join(add) + ".").strip()
    return st
