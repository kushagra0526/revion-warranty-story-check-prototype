"""Facts an auditor checks, pulled out of written or (normalized) spoken text.

kinds: dtc, meas (value + unit), pn (8-digit part number), sidoc (7-digit SI document id),
conn (X2), circ (circuit 235), cyl (cylinder 3), miles, cond (complaint condition, canonical)
"""
import re

from .spoken import normalize, unit_at

DTC = re.compile(r"\b([PBCU][0-3][0-9A-F]{3})\b")
GLUED = re.compile(r"\b(\d+(?:\.\d+)?)\s?(V|volts|psi|PSI|kPa|Nm|mm|A|%|Ω|ohms?|ft-lbs?|lb-ft|°F|degrees|deg|CCA)(?![A-Za-z])")

CONDITIONS = {
    "cold_start": ["cold start", "first start", "in the morning", "when it's cold", "when cold", "sitting overnight", "after sitting"],
    "warm": ["when warm", "warmed up", "at operating temp", "fully warm", "hot engine"],
    "idle": ["at idle", "idling", "while idling"],
    "highway": ["highway", "freeway", "at speed", "over 50", "over 60"],
    "braking": ["when braking", "under braking", "on the brakes", "brakes applied", "stopping"],
    "turning": ["turning", "in turns", "corners"],
    "bumps": ["over bumps", "bumpy"],
    "intermittent": ["intermittent", "comes and goes", "sometimes", "on and off", "now and then"],
    "constant": ["all the time", "constant", "consistent", "every time"],
    # "mil" alone is also shop talk for millimetre; only the lamp counts (held-out run 1 fix)
    "mil_on": ["check engine light", "engine light", "mil on", "mil light", "mil lamp", "mil illuminated", "flashing mil",
               "the mil ", "service engine soon"],
    "flashing": ["flashing", "blinking"],
    "abs_light": ["abs light", "abs warning", "abs lamp", "traction light", "stability light"],
    "tpms_light": ["tire pressure light", "tpms light", "low tire light", "low tire lamp"],
    "hot_day": ["hot days", "hot weather", "in the heat", "over 90"],
    "rain": ["in the rain", "when wet", "rainy"],
    "fluid_brown": ["brown fluid", "brown oil", "dark oil", "black oil"],
    "fluid_red": ["red fluid"],
    "fluid_green": ["green fluid", "coolant"],
    "no_start": ["won't start", "no start", "would not start", "doesn't crank", "no crank", "dead in the morning"],
    "shakes": ["shakes", "shaking", "rough", "stumbles"],
    "noise_squeal": ["squeal", "squeak"],
    "noise_hum": ["hum", "humming", "drone", "growl"],
    "harsh_shift": ["harsh shift", "slams", "bangs into", "hard shift", r"re:harsh\W+(?:\d-\d\W+)?(?:up)?shift"],
    "not_cold": ["not cold", "blowing warm", "warm air"],
    "smell": ["smell", "odor"],
}


def conditions(text):
    low = " " + text.lower() + " "
    return {k for k, pats in CONDITIONS.items()
            if any((re.search(p[3:], low) if p.startswith("re:") else p in low) for p in pats)}


def extract(text, spoken=False):
    """-> list of (kind, value, span_text)."""
    s = normalize(text) if spoken else text
    # spec ranges come from service information, not from this vehicle: not facts to ground
    s = re.sub(r"\(?\b(?:spec|specification|should be|within)\b(?:[^.;)]|\.\d)*\)?", " ", s, flags=re.I)
    out = []
    for m in DTC.finditer(s):
        out.append(("dtc", m.group(1), m.group(0)))
    words = s.split()
    used = set()
    for i, w in enumerate(words):
        core = w.strip(",;:().")
        if re.fullmatch(r"\d+(?:\.\d+)?", core.rstrip(".")):
            num = core.rstrip(".")
            unit, n = unit_at(words, i + 1)
            back = []
            for w2 in reversed(words[max(0, i - 3):i]):   # keyword context stays inside the sentence
                if w2.endswith((".", ";")):
                    break
                back.insert(0, w2)
            prev = " ".join(back).lower()
            if unit and not core.endswith(".") or unit and n:
                if unit == "miles":
                    out.append(("miles", int(float(num)), f"{num} miles"))
                else:
                    out.append(("meas", (round(float(num), 3), unit), f"{num} {unit}"))
                used.add(i)
                continue
            near = re.findall(r"[a-z]+", prev)
            key = next((x for x in reversed(near) if x in ("circuit", "document", "doc", "si", "id", "part", "number")), None)
            if key == "circuit":
                out.append(("circ", num, num))
            elif re.fullmatch(r"\d{8}", num):
                out.append(("pn", num, num))
            elif re.fullmatch(r"\d{7}", num) or key in ("document", "doc", "si", "id"):
                out.append(("sidoc", num, num))
            elif re.search(r"\b(cylinder|cyl)\b", prev.split()[-1] if prev else ""):
                out.append(("cyl", int(float(num)), f"cylinder {num}"))
    for m in GLUED.finditer(s):
        u = m.group(2)
        u = {"PSI": "psi", "volts": "V", "degrees": "deg", "Ω": "ohm", "ohms": "ohm", "ohm": "ohm", "ft-lbs": "ft-lb", "ft-lb": "ft-lb", "lb-ft": "ft-lb", "°F": "deg"}.get(u, u)
        if m.group(0).count(" ") == 0:  # glued "11.8V"; spaced forms are already taken above
            out.append(("meas", (round(float(m.group(1)), 3), u), m.group(0)))
    for m in re.finditer(r"\bX(\d{1,3})\b", s):
        out.append(("conn", "X" + m.group(1), m.group(0)))
    for m in re.finditer(r"#(\d)\b|\bcyl(?:inder)?\s*#?(\d)\b", s, re.I):
        out.append(("cyl", int(m.group(1) or m.group(2)), m.group(0)))
    seen, uniq = set(), []
    for k, v, t in out:
        if (k, v) not in seen:
            seen.add((k, v))
            uniq.append((k, v, t))
    return uniq
