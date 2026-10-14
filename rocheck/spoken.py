"""Technician speech (as a transcriber writes it) -> written forms the story uses.

  "pee zero three oh three"            -> P0303
  "eleven point eight volts"           -> 11.8 V
  "point four ohms"                    -> 0.4 ohm
  "twelve and a half volts"            -> 12.5 V
  "one two six three five two seven three" -> 12635273   (6+ single digits read one by one)
  "connector ex two", "X two"          -> X2
  "forty eight thousand two hundred eleven miles" -> 48211 miles
"""
import re

UNITS = {
    "volts": "V", "volt": "V", "v": "V",
    "ohms": "ohm", "ohm": "ohm", "ω": "ohm",
    "psi": "psi", "p.s.i.": "psi",
    "kpa": "kPa", "kilopascals": "kPa",
    "amps": "A", "amp": "A", "amperes": "A",
    "millimeters": "mm", "millimeter": "mm", "mm": "mm", "mil": "mm",
    "degrees": "deg", "degree": "deg", "°f": "deg", "f": "deg",
    "percent": "%",
    "miles": "miles", "mi": "miles",
    "cca": "CCA",
}
TWO_WORD_UNITS = {("foot", "pounds"): "ft-lb", ("foot", "pound"): "ft-lb", ("ft", "lbs"): "ft-lb", ("newton", "meters"): "Nm",
                  ("cold", "cranking"): "CCA"}
DIG = {"zero": 0, "oh": 0, "o": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9}
TEENS = {"ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
         "seventeen": 17, "eighteen": 18, "nineteen": 19}
TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
SCALE = {"hundred": 100, "thousand": 1000}
LETTERS = {"pee": "P", "p": "P", "bee": "B", "b": "B", "see": "C", "cee": "C", "c": "C", "you": "U", "u": "U",
           "ex": "X", "x": "X"}
NUMWORDS = set(DIG) | set(TEENS) | set(TENS) | set(SCALE)


def _tokens(text):
    return re.findall(r"[A-Za-z]+(?:'[a-z]+)?|\d+(?:\.\d+)?|[^\sA-Za-z\d]", text)


def _cardinal(ws):
    """Parse number words (no 'point') -> int, or None.
    'two three five' (digits one by one) -> 235; 'two fifty' (shop shorthand) -> 250."""
    if len(ws) >= 2 and all(w in DIG for w in ws):
        return int("".join(str(DIG[w]) for w in ws))
    if len(ws) >= 2 and ws[0] in DIG and DIG[ws[0]] > 0 and (ws[1] in TENS or ws[1] in TEENS) and not set(ws) & set(SCALE):
        rest = _cardinal(ws[1:])
        if rest is not None and rest < 100:
            return DIG[ws[0]] * 100 + rest
    total, cur, seen = 0, 0, False
    for w in ws:
        if w in DIG and w != "oh" and w != "o":
            cur += DIG[w]
        elif w in TEENS:
            cur += TEENS[w]
        elif w in TENS:
            cur += TENS[w]
        elif w == "hundred":
            cur = max(cur, 1) * 100
        elif w == "thousand":
            total += max(cur, 1) * 1000
            cur = 0
        else:
            return None
        seen = True
    return total + cur if seen else None


def _digit_run(toks, i):
    """Single digits read one by one (words or 1-char numerals) starting at i -> (digits, end)."""
    out, j = "", i
    while j < len(toks):
        t = toks[j].lower()
        if t in DIG:
            out += str(DIG[t])
        elif re.fullmatch(r"\d", t):
            out += t
        elif t == "-" and out:
            j += 1
            continue
        else:
            break
        j += 1
    return out, j


HEX = {"a": "A", "bee": "B", "b": "B", "see": "C", "c": "C", "cee": "C", "dee": "D", "d": "D", "ee": "E", "e": "E", "ef": "F", "f": "F"}


def _dtc_run(toks, i):
    """Four DTC characters after the system letter: digits, or A-F after the first two."""
    out, j = "", i
    while j < len(toks) and len(out) < 4:
        t = toks[j].lower()
        if t in DIG:
            out += str(DIG[t])
        elif re.fullmatch(r"\d+", t) and len(out) + len(t) <= 4:
            out += t
        elif len(out) >= 1 and t in HEX:
            out += HEX[t]
        else:
            break
        j += 1
    return out, j


def normalize(text):
    toks = _tokens(text)
    out, i = [], 0
    while i < len(toks):
        t, low = toks[i], toks[i].lower()
        # DTC: letter + four digits ("pee zero three oh three", "P 0 3 0 3", "P-0303")
        if low in LETTERS and LETTERS[low] in "PBCU":
            j = i + 1
            if j < len(toks) and toks[j] == "-":
                j += 1
            digits, end = _dtc_run(toks, j)
            if not digits and j < len(toks) and re.fullmatch(r"\d{4}", toks[j]):
                digits, end = toks[j], j + 1
            if len(digits) == 4:
                out.append(LETTERS[low] + digits)
                i = end
                continue
        # connector: "ex two", "X two", "X 2", "X1"
        if low in ("ex", "x") and i + 1 < len(toks):
            nxt = toks[i + 1].lower()
            if nxt in DIG or re.fullmatch(r"\d{1,3}", nxt):
                digits, end = _digit_run(toks, i + 1)
                if not digits:
                    digits, end = nxt, i + 2
                out.append("X" + digits)
                i = end
                continue
        # long single-digit runs: part numbers, document ids
        digits, end = _digit_run(toks, i)
        if len(digits) >= 6:
            out.append(digits)
            i = end
            continue
        # cardinal numbers with optional "point d d" / "and a half"
        if low in NUMWORDS or low == "point" or re.fullmatch(r"\d+(?:\.\d+)?", t):
            j = i
            ws = []
            while j < len(toks) and toks[j].lower() in NUMWORDS:
                ws.append(toks[j].lower())
                j += 1
            num = None
            if ws:
                num = _cardinal(ws)
            elif re.fullmatch(r"\d+(?:\.\d+)?", t):
                num, j = t, i + 1
            if j < len(toks) and toks[j].lower() == "point":
                d, k = _digit_run(toks, j + 1)
                if d:
                    num = f"{num if num is not None else 0}.{d}"
                    j = k
            elif j + 2 < len(toks) and [x.lower() for x in toks[j:j + 3]] == ["and", "a", "half"] and num is not None:
                num = f"{num}.5"
                j += 3
            if num is not None:
                out.append(str(num))
                i = j
                continue
        out.append(t)
        i += 1
    s = " ".join(out)
    s = re.sub(r" ([.,;:!?)])", r"\1", s).replace("( ", "(")
    return s


PRESSURE = ("pressure", "side", "psi", "tire", "fuel", "line", "rail", "boost", "vacuum")
TORQUE = ("torque", "torqued", "bolts", "bolt", "nut", "nuts", "lug")


def unit_at(words, k):
    """Unit starting at words[k] -> (unit, words consumed).
    Shop slang 'pounds' alone is psi next to a pressure word and ft-lb next to a torque word
    (held-out run 1 fix)."""
    if k < len(words) and words[k].lower().strip(".,;:") in ("pounds", "pound", "lbs"):
        before, after = [], []
        for w in reversed(words[max(0, k - 8):k]):      # same sentence only
            if w.endswith((".", ";")):
                break
            before.append(w)
        for w in words[k:k + 10]:
            after.append(w)
            if w.endswith((".", ";")):
                break
        ctx = " ".join(before + after).lower()
        if any(w in ctx for w in TORQUE):
            return "ft-lb", 1
        if any(w in ctx for w in PRESSURE):
            return "psi", 1
    if k + 2 < len(words) and [w.lower().strip(".,;") for w in words[k:k + 3]] == ["cold", "cranking", "amps"]:
        return "CCA", 3
    if k + 1 < len(words):
        pair = (words[k].lower().strip(".,;:"), words[k + 1].lower().strip(".,;:"))
        if pair in TWO_WORD_UNITS:
            return TWO_WORD_UNITS[pair], 2
    if k < len(words):
        w = words[k].lower().strip(".,;")
        if w in UNITS:
            return UNITS[w], 1
        if w in ("ft-lb", "ft-lbs", "ftlb", "lb-ft"):
            return "ft-lb", 1
        if w == "nm":
            return "Nm", 1
    return None, 0
