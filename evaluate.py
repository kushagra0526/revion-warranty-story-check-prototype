"""Benchmark: AI-drafted repair-order stories with planted warranty problems.

    python evaluate.py dev        # seeds 1-400, dev phrase bank
    python evaluate.py heldout    # seeds 9001-9400, held-out phrase bank (frozen in git first)

Compared:
  trust      submit the draft as written
  checklist  required fields: story parts non-empty, a DTC in the cause when one is stored, battery code
             present, J9992 has a dependency code, CCND approval ticked, every op has a punch
  exact      every number/code in the story must appear verbatim in the transcript, scan or RO
  rocheck    this repo
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from rocheck.check import check  # noqa: E402
from rocheck.synth import scenario  # noqa: E402


def checklist(ro, used):
    out = set()
    st = ro["story"]
    if any(not st[k].strip() for k in st):
        out.add("EMPTY")
    stored = [d["code"] for d in ro["scan"]["dtcs"] if d["status"] == "stored"]
    if stored and not re.search(r"\b[PBCU][0-3][0-9A-F]{3}\b", st["cause"]):
        out.add("CAUSE_NO_DTC")
    if any("battery" in p["desc"].lower() for p in ro["parts"]) and not (ro.get("battery_code") or {}).get("code"):
        out.add("BATTERY_NO_CODE")
    for op in ro["ops"]:
        if op["op"] == "J9992" and not op.get("dep_dtc"):
            out.add("J9992_NO_PCODE")
        if op.get("approval") is False:
            out.add("CCND_NO_APPROVAL")
        if not any(p["op"] == op["op"] for p in ro["punches"]):
            out.add("NO_PUNCH")
    return out


def exact(ro, used):
    hay = " ".join(t["text"] for t in ro["transcript"]) + " " + json.dumps(ro["scan"]) + " " + json.dumps(ro["parts"])
    out = set()
    for tok in re.findall(r"\b[PBCU]?\d[\dA-F.]*\b", " ".join(ro["story"].values())):
        tok = tok.rstrip(".")
        if tok and tok not in hay:
            out.add("UNSUPPORTED")
    return out


def run(split):
    if split == "heldout":
        from eval.bank_heldout import BANK
        seeds = range(9001, 9401)
    else:
        from rocheck.bank_dev import BANK
        seeds = range(1, 401)
    names = ("trust", "checklist", "exact", "rocheck")
    fam = {n: defaultdict(lambda: [0, 0]) for n in names}
    clean_flagged = defaultdict(int)
    wrong = defaultdict(int)
    verdict_ok = defaultdict(int)
    n_clean = 0
    misses, false_flags = [], []
    for seed in seeds:
        s = scenario(seed, BANK)
        ro = s["ro"]
        r = check(ro, s["used_codes"])
        codes = {
            "trust": set(),
            "checklist": checklist(ro, s["used_codes"]),
            "exact": exact(ro, s["used_codes"]),
            "rocheck": {f["code"] for f in r["findings"]},
        }
        if s["defect"] is None:
            n_clean += 1
            for n in names:
                clean_flagged[n] += bool(codes[n])
                verdict_ok[n] += not codes[n]
            if codes["rocheck"]:
                false_flags.append({"seed": seed, "scenario": ro["name"], "findings": [(f["code"], f["msg"]) for f in r["findings"]]})
            continue
        for n in names:
            hit = bool(codes[n] & s["expect"])
            fam[n][s["defect"]][0] += hit
            fam[n][s["defect"]][1] += 1
            verdict_ok[n] += bool(codes[n])
            if n == "rocheck":
                extra = codes[n] - s["expect"] - s["may"]
                wrong[n] += bool(extra)
                if not hit or extra:
                    misses.append({"seed": seed, "scenario": ro["name"], "defect": s["defect"], "hit": hit,
                                   "findings": [(f["code"], f["msg"]) for f in r["findings"]]})

    def tot(n):
        return [sum(v[0] for v in fam[n].values()), sum(v[1] for v in fam[n].values())]
    return {"split": split, "ros": len(seeds), "clean": n_clean,
            "families": {d: {n: fam[n][d] for n in names} for d in sorted(fam["rocheck"])},
            "caught": {n: tot(n) for n in names},
            "clean_flagged": dict(clean_flagged), "rocheck_defect_ros_with_extra_findings": wrong["rocheck"],
            "verdict_correct": dict(verdict_ok), "misses": misses[:80], "false_flags": false_flags[:40]}


def show(r):
    print(f"\n== {r['split']}: {r['ros']} ROs ({r['clean']} clean)")
    print(f"{'planted defect':<22}" + "".join(f"{n:>12}" for n in ("trust", "checklist", "exact", "rocheck")))
    for d, v in r["families"].items():
        print(f"{d:<22}" + "".join(f"{f'{v[n][0]}/{v[n][1]}':>12}" for n in ("trust", "checklist", "exact", "rocheck")))
    print(f"{'caught':<22}" + "".join(f"{f'{r['caught'][n][0]}/{r['caught'][n][1]}':>12}" for n in ("trust", "checklist", "exact", "rocheck")))
    print(f"{'clean ROs flagged':<22}" + "".join(f"{f'{r['clean_flagged'][n]}/{r['clean']}':>12}" for n in ("trust", "checklist", "exact", "rocheck")))
    print(f"{'verdict right':<22}" + "".join(f"{f'{r['verdict_correct'][n]}/{r['ros']}':>12}" for n in ("trust", "checklist", "exact", "rocheck")))
    print(f"rocheck: defect ROs with an extra (wrong) finding: {r['rocheck_defect_ros_with_extra_findings']}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    split = sys.argv[1] if len(sys.argv) > 1 else "dev"
    res = run(split)
    (HERE / "out").mkdir(exist_ok=True)
    (HERE / f"out/eval_{split}.json").write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    show(res)
