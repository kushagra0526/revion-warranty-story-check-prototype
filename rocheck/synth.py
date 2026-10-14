"""Synthetic repair orders: technician voice transcript (spoken forms), scan report, RO lines and an
AI-drafted 3C story, either correct or with one planted defect. Truth = the planted defect.

Phrasing (how techs say things, how the draft writes them) comes from a phrase bank, so the
held-out bank can differ from the one used while building.
"""
import copy
import random
import re

ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen",
        "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def words(n):
    n = int(n)
    if n < 20:
        return ONES[n]
    if n < 100:
        return TENS[n // 10] + ("" if n % 10 == 0 else " " + ONES[n % 10])
    if n < 1000:
        return ONES[n // 100] + " hundred" + ("" if n % 100 == 0 else " " + words(n % 100))
    return words(n // 1000) + " thousand" + ("" if n % 1000 == 0 else " " + words(n % 1000))


def say_num(x, rng, B):
    if float(x).is_integer():
        n = int(x)
        if 100 < n < 1000 and n % 100 >= 10 and rng.random() < B.get("shop_shorthand", 0):
            return ONES[n // 100] + " " + words(n % 100)      # "two fifty"
        return words(n)
    ip, dp = f"{x}".split(".")
    lead = "" if ip == "0" and rng.random() < 0.5 else words(int(ip)) + " "
    return lead + "point " + " ".join(ONES[int(d)] for d in dp)


def say_digits(s, rng, B):
    return " ".join(("oh" if c == "0" and rng.random() < B["oh_rate"] else ONES[int(c)]) for c in s)


def say_dtc(code, rng, B):
    letter = rng.choice(B["dtc_letter"][code[0]])
    rest = []
    for c in code[1:]:
        rest.append(("oh" if c == "0" and rng.random() < B["oh_rate"] else ONES[int(c)]) if c.isdigit() else rng.choice(B["hex_letter"][c]))
    return rng.choice(B["dtc_join"]).format(l=letter, d=" ".join(rest), dd="-".join(rest))


# ---------- the vehicles' facts (shared by both banks) ----------
SCENARIOS = {
    "misfire": {"conds": ["mil_on", "flashing", "cold_start", "shakes"], "dtcs": [("P0303", "stored")],
                "meas": [(0.4, "ohm", "coil primary resistance")], "doc": "4518032", "cyl": 3,
                "parts": [("12635273", "ignition coil", True)], "ops": [("J4510", "ignition coil replace", 0.6)],
                "cause": "Misfire on cylinder 3 followed the coil when swapped to another cylinder."},
    "battery": {"conds": ["no_start", "cold_start"], "dtcs": [], "meas": [(11.8, "V", "open circuit voltage"), (290, "CCA", "tested")],
                "doc": "5530118", "parts": [("24262323", "battery", True)], "ops": [("N0100", "battery test and replace", 0.3)],
                "cause": "Battery failed load test.", "battery": True},
    "abs_ccnd": {"conds": ["abs_light", "intermittent"], "dtcs": [("C0035", "history")], "meas": [(1150, "ohm", "LF wheel speed sensor")],
                 "doc": "3307714", "parts": [], "ops": [("H9991", "ABS light CCND", 0.2)], "ccnd": True,
                 "cause": "History code only; no fault present.", "conn": "X1"},
    "mil_ccnd": {"conds": ["mil_on"], "dtcs": [("P00C6", "history")], "meas": [(58, "psi", "fuel rail pressure")], "doc": "4790265",
                 "parts": [], "ops": [("J9992", "engine controls CCND", 0.3)], "ccnd": True, "dep": "P00C6",
                 "cause": "P00C6 in history; fault tree found no mechanical or electrical concern."},
    "ac": {"conds": ["not_cold", "hot_day", "constant"], "dtcs": [], "meas": [(250, "psi", "high side"), (25, "psi", "low side"), (58, "deg", "center vent")],
           "doc": "2264051", "parts": [("23353245", "condenser", True)], "ops": [("D3150", "condenser replace", 1.4)],
           "cause": "UV dye shows refrigerant leak at condenser core."},
    "oil_leak": {"conds": ["fluid_brown"], "dtcs": [], "meas": [(10, "ft-lb", "pan bolts")], "doc": "1983340",
                 "parts": [("12612350", "oil pan gasket", True)], "ops": [("J0200", "oil pan gasket replace", 1.8)],
                 "cause": "Oil leak at oil pan gasket rear corner, area cleaned and dye confirmed."},
    "evap": {"conds": ["mil_on"], "dtcs": [("P0455", "stored")], "meas": [], "doc": "6021447", "conn": "X1", "circ": "1310",
             "parts": [("12581336", "purge valve", True)], "ops": [("J7040", "purge valve replace", 0.8)],
             "cause": "Smoke test found leak at purge valve."},
    "tpms": {"conds": ["tpms_light", "cold_start"], "dtcs": [("C0750", "stored")], "meas": [(28, "psi", "LF tire")], "doc": "3410982",
             "parts": [("13598772", "TPMS sensor", True)], "ops": [("N3800", "TPMS sensor replace", 0.5)],
             "cause": "LF sensor not transmitting."},
    "bearing": {"conds": ["noise_hum", "highway", "turning"], "dtcs": [], "meas": [(0.3, "mm", "hub end play"), (150, "ft-lb", "hub bolts")],
                "doc": "2875503", "parts": [("13502778", "hub bearing", True)], "ops": [("E4100", "front hub bearing replace", 1.1)],
                "cause": "LF hub bearing worn, noise louder turning right."},
    "trans": {"conds": ["harsh_shift", "warm"], "dtcs": [("P0751", "stored"), ("P0700", "stored")], "meas": [(90, "psi", "line pressure")],
              "doc": "5102236", "parts": [("24259853", "shift solenoid", True)], "ops": [("K6640", "shift solenoid replace", 2.0)],
              "cause": "Shift solenoid A performance."},
}
UNIT_SAY = {"ohm": "ohms", "V": "volts", "CCA": "cold cranking amps", "psi": "psi", "deg": "degrees", "ft-lb": "foot pounds", "mm": "millimeters"}


def vin(rng):
    return "1G1" + "".join(rng.choice("ABCDEFGHJKLMNPRSTUVWXYZ0123456789") for _ in range(14))


def battery_code(rng, n=20):
    return "".join(rng.choice("ABCDEFGHJKLMNPQRSTUVWX0123456789") for _ in range(n))


def build(name, rng, B):
    sc = SCENARIOS[name]
    v = vin(rng)
    tr = []
    cond_say = [rng.choice(B["cond_say"][c]) for c in sc["conds"]]
    tr.append({"who": "advisor", "text": rng.choice(B["advisor"]).format(conds=", ".join(cond_say))})
    lines = []
    for code, status in sc["dtcs"]:
        lines.append(rng.choice(B["say_dtc"]).format(dtc=say_dtc(code, rng, B), status=status))
    for val, unit, what in sc["meas"]:
        lines.append(rng.choice(B["say_meas"]).format(what=what, val=say_num(val, rng, B), unit=rng.choice(B["unit_say"].get(unit, [UNIT_SAY[unit]]))))
    if sc.get("conn"):
        lines.append(rng.choice(B["say_conn"]).format(conn=rng.choice(B["conn_letter"]) + " " + ONES[int(sc["conn"][1:])]))
    if sc.get("circ"):
        lines.append(rng.choice(B["say_circ"]).format(circ=say_digits(sc["circ"], rng, B)))
    for pn, desc, _ in sc["parts"]:
        lines.append(rng.choice(B["say_part"]).format(desc=desc, pn=say_digits(pn, rng, B)))
    lines.append(rng.choice(B["say_doc"]).format(doc=say_digits(sc["doc"], rng, B)))
    rng.shuffle(lines)
    for i in range(0, len(lines), 2):
        tr.append({"who": "tech", "text": " ".join(lines[i:i + 2])})
    # the AI draft (correct version)
    cw = [rng.choice(B["cond_write"][c]) for c in sc["conds"]]
    complaint = rng.choice(B["complaint"]).format(conds=", ".join(cw))
    dt = " ".join(f"{c} {s}." for c, s in sc["dtcs"])
    cause = (dt + " " + sc["cause"]).strip()
    mtxt = [rng.choice(B["write_meas"]).format(what=w, val=f"{val:g}", unit=rng.choice(B["unit_write"][u])) for val, u, w in sc["meas"]]
    extra = []
    if sc.get("conn"):
        extra.append(f"Checked connector {sc['conn']}.")
    if sc.get("circ"):
        extra.append(f"Circuit {sc['circ']} OK.")
    parts = " ".join(rng.choice(B["write_part"]).format(desc=d, pn=p) for p, d, _ in sc["parts"])
    if not sc["parts"]:
        parts = rng.choice(B["write_nff"])
    correction = " ".join(mtxt + extra + [parts, rng.choice(B["write_doc"]).format(doc=sc["doc"]), rng.choice(B["write_verify"])])
    ops = [{"op": o, "desc": d, "hours": h, "approval": True if sc.get("ccnd") else None, "dep_dtc": sc.get("dep") if o == "J9992" else None}
           for o, d, h in sc["ops"]]
    punches = [{"op": o["op"], "hours": round(o["hours"] + rng.choice([0.0, 0.1, 0.2]), 1)} for o in ops]
    ro = {"name": name, "vin": v, "transcript": tr, "scan": {"dtcs": [{"code": c, "status": s} for c, s in sc["dtcs"]]},
          "ops": ops, "punches": punches, "parts": [{"pn": p, "desc": d, "causal": c} for p, d, c in sc["parts"]],
          "story": {"complaint": complaint, "cause": cause, "correction": correction}}
    if sc.get("battery"):
        ro["battery_code"] = {"code": battery_code(rng), "vin": v}
    return ro


# defect -> (expected codes (any of them counts as caught), codes that may also legitimately fire)
DEFECTS = {
    "hallucinated_dtc": ({"UNSUPPORTED", "CONTRADICTED"}, set()),
    "wrong_dtc_digit": ({"CONTRADICTED"}, {"CAUSE_NO_DTC", "UNSUPPORTED"}),
    "wrong_meas": ({"CONTRADICTED"}, {"MISSING_FACT"}),
    "invented_meas": ({"UNSUPPORTED", "CONTRADICTED"}, set()),
    "wrong_pn": ({"CONTRADICTED"}, set()),
    "missing_condition": ({"MISSING_CONDITION"}, set()),
    "recap_correction": ({"RECAP_ONLY"}, {"MISSING_FACT", "CAUSAL_PART_NOT_IN_STORY"}),
    "drop_meas": ({"MISSING_FACT"}, set()),
    "cause_no_dtc": ({"CAUSE_NO_DTC"}, set()),
    "j9992_no_pcode": ({"J9992_NO_PCODE"}, set()),
    "j9992_p0700": ({"J9992_BAD_CODE"}, set()),
    "ccnd_hours": ({"CCND_HOURS"}, {"CCND_CLOCK"}),
    "ccnd_no_approval": ({"CCND_NO_APPROVAL"}, set()),
    "no_punch": ({"NO_PUNCH"}, set()),
    "battery_code_invalid": ({"BATTERY_CODE_INVALID"}, set()),
    "battery_code_reused": ({"BATTERY_CODE_REUSED"}, set()),
    "battery_code_vin": ({"BATTERY_CODE_VIN"}, set()),
    # removing every mention of the part also removes sentences/words that carried other facts
    "causal_omitted": ({"CAUSAL_PART_NOT_IN_STORY"}, {"UNSUPPORTED", "MISSING_FACT", "MISSING_CONDITION"}),
}


def usable(ro, d):
    sc = SCENARIOS[ro["name"]]
    if d in ("wrong_dtc_digit", "cause_no_dtc"):
        return any(s == "stored" for _, s in sc["dtcs"])
    if d in ("wrong_meas", "drop_meas"):
        return bool(sc["meas"])
    if d in ("wrong_pn", "causal_omitted"):
        return bool(sc["parts"])
    if d.startswith("j9992"):
        return any(o["op"] == "J9992" for o in ro["ops"])
    if d.startswith("ccnd"):
        return bool(sc.get("ccnd"))
    if d.startswith("battery"):
        return bool(sc.get("battery"))
    return True


def plant(ro, d, rng, B):
    ro = copy.deepcopy(ro)
    st = ro["story"]
    sc = SCENARIOS[ro["name"]]
    if d == "hallucinated_dtc":
        extra = rng.choice([c for c in ("P0171", "P0420", "P0128", "U0100", "B1325") if c not in {x for x, _ in sc["dtcs"]}])
        st["cause"] = f"DTC {extra} stored. " + st["cause"]
    elif d == "wrong_dtc_digit":
        code = next(c for c, s in sc["dtcs"] if s == "stored")
        new = code[:4] + str((int(code[4]) + rng.randint(1, 8)) % 10)
        for k in st:
            st[k] = st[k].replace(code, new)
    elif d == "wrong_meas":
        val, u, w = rng.choice(sc["meas"])
        new = val
        while f"{new:g}" == f"{val:g}":  # a mutation that rounds back to the same value plants nothing
            new = round(val * rng.choice([0.8, 1.15, 1.3, 1.5]) + (0.1 if val < 5 else 3), 1)
            new = int(new) if float(val).is_integer() else new
        st["correction"] = re.sub(rf"(?<![\d.]){re.escape(f'{val:g}')}(?![\d])", f"{new:g}", st["correction"], count=1)
    elif d == "invented_meas":
        st["correction"] += " " + rng.choice(B["invented"])
    elif d == "wrong_pn":
        pn = sc["parts"][0][0]
        i = rng.randrange(len(pn) - 1)
        new = pn[:i] + pn[i + 1] + pn[i] + pn[i + 2:] if pn[i] != pn[i + 1] else pn[:i] + str((int(pn[i]) + 1) % 10) + pn[i + 1:]
        st["correction"] = st["correction"].replace(pn, new)
    elif d == "missing_condition":
        c = rng.choice(sc["conds"])
        for ph in B["cond_write"][c]:
            st["complaint"] = st["complaint"].replace(", " + ph, "").replace(ph + ", ", "").replace(ph, "")
        st["complaint"] = re.sub(r"\s+", " ", st["complaint"]).replace(" .", ".")
    elif d == "recap_correction":
        desc = sc["parts"][0][1] if sc["parts"] else "system"
        st["correction"] = rng.choice(B["recap"]).format(desc=desc)
    elif d == "drop_meas":
        val, u, w = rng.choice(sc["meas"])
        sents = re.split(r"(?<=\.)\s+", st["correction"])
        st["correction"] = " ".join(s for s in sents if not re.search(rf"(?<![\d.]){re.escape(f'{val:g}')}(?![\d])", s))
    elif d == "cause_no_dtc":
        for c, s in sc["dtcs"]:
            for k in st:
                st[k] = st[k].replace(f"{c} {s}. ", "").replace(f"{c} {s}.", "").replace(c, "the code")
    elif d == "j9992_no_pcode":
        ro["ops"][0]["dep_dtc"] = None
    elif d == "j9992_p0700":
        ro["ops"][0]["dep_dtc"] = "P0700"
    elif d == "ccnd_hours":
        ro["ops"][0]["hours"] = 0.5
        ro["punches"][0]["hours"] = 0.5
    elif d == "ccnd_no_approval":
        ro["ops"][0]["approval"] = False
    elif d == "no_punch":
        ro["punches"] = []
    elif d == "battery_code_invalid":
        c = ro["battery_code"]["code"]
        ro["battery_code"]["code"] = rng.choice([c[:17], c[:10] + "O" + c[11:], c[:6] + "-" + c[7:]])
    elif d == "battery_code_reused":
        ro["reused"] = True
    elif d == "battery_code_vin":
        ro["battery_code"]["vin"] = ro["vin"][:-3] + "999"
    elif d == "causal_omitted":
        pn, desc, _ = sc["parts"][0]
        sents = re.split(r"(?<=\.)\s+", st["correction"])
        st["correction"] = " ".join(s for s in sents if pn not in s and desc.split()[-1] not in s.lower())
        for k in st:
            st[k] = re.sub(re.escape(desc), "part", st[k], flags=re.I)
            for w in desc.lower().split():
                if len(w) > 3:
                    st[k] = re.sub(rf"\b{re.escape(w)}\b", "unit", st[k], flags=re.I)
    return ro


def scenario(seed, B):
    rng = random.Random(seed)
    name = rng.choice(sorted(SCENARIOS))
    ro = build(name, rng, B)
    d = None if rng.random() < 0.3 else rng.choice(sorted(DEFECTS))
    if d and not usable(ro, d):
        d = rng.choice([x for x in sorted(DEFECTS) if usable(ro, x)])
    if d:
        ro = plant(ro, d, rng, B)
    exp, may = DEFECTS.get(d, (set(), set()))
    used = {ro["battery_code"]["code"]} if ro.get("reused") else set()
    return {"seed": seed, "defect": d, "ro": ro, "expect": exp, "may": may, "used_codes": used}
