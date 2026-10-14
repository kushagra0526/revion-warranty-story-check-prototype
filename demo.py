"""One repair order end to end -> out/report.html

    python demo.py

A misfire RO. The technician talked through the job; the AI draft of the 3C story reads well but
has the wrong cylinder's code, a changed reading, a dropped condition, and the RO has no time punch.
"""
import html
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from rocheck.bank_dev import BANK  # noqa: E402
from rocheck.check import check  # noqa: E402
from rocheck.spoken import normalize  # noqa: E402
from rocheck.synth import build, plant  # noqa: E402

e = html.escape


def build_demo():
    rng = random.Random(11)
    ro = build("misfire", rng, BANK)
    for d in ("wrong_dtc_digit", "wrong_meas", "missing_condition", "no_punch"):
        ro = plant(ro, d, rng, BANK)
    return ro, check(ro)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ro, r = build_demo()
    print("== technician (as transcribed) -> normalized")
    for t in ro["transcript"]:
        print(f"  [{t['who']}] {t['text']}\n      -> {normalize(t['text'])}")
    print("\n== AI draft")
    for k, v in ro["story"].items():
        print(f"  {k:<10} {v}")
    print(f"\n== verdict: {r['verdict']}")
    for f in r["findings"]:
        print(f"  {f['level']:<4} {f['code']:<18} {f['msg']}  [{f['cite']}; {f['rule']}]")
    print("\n== repaired draft (grounded facts only)")
    for k, v in r["repaired"].items():
        print(f"  {k:<10} {v}")
    ev = {}
    for k, f in (("dev", "out/eval_dev.json"), ("heldout_first_run", "out/heldout_first_run.json"), ("heldout", "out/eval_heldout.json")):
        if (HERE / f).exists():
            ev[k] = json.loads((HERE / f).read_text(encoding="utf-8"))
    (HERE / "out").mkdir(exist_ok=True)
    (HERE / "out/report.html").write_text(render(ro, r, ev), encoding="utf-8")
    print("\nwrote out/report.html")


def render(ro, r, ev):
    tr = "".join(f"<div class='turn'><span class='who'>{e(t['who'])}</span> {e(t['text'])}<div class='norm'>→ {e(normalize(t['text']))}</div></div>"
                 for t in ro["transcript"])
    draft = "".join(f"<div class='sec'><b>{k}</b> {e(v)}</div>" for k, v in ro["story"].items())
    fixed = "".join(f"<div class='sec'><b>{k}</b> {e(v)}</div>" for k, v in r["repaired"].items())
    rows = "".join(f"<tr><td class='{f['level'].lower()}'>{f['level']}</td><td><b>{e(f['code'])}</b></td><td>{e(f['msg'])}</td><td>{e(f['cite'])}</td><td>{e(f['rule'])}</td></tr>"
                   for f in r["findings"])
    ops = "".join(f"<li>{e(o['op'])} {e(o['desc'])}: {o['hours']} h</li>" for o in ro["ops"])
    parts = "".join(f"<li>{e(p['pn'])} {e(p['desc'])}{' (causal)' if p['causal'] else ''}</li>" for p in ro["parts"])
    scan = "".join(f"<li>{e(d['code'])} {e(d['status'])}</li>" for d in ro["scan"]["dtcs"])
    bench = ""
    lab = {"dev": "dev (400 ROs)", "heldout_first_run": "held-out, first run", "heldout": "held-out, after fixes"}
    for k in ("dev", "heldout_first_run", "heldout"):
        if k not in ev:
            continue
        x = ev[k]
        c, cf = x["caught"], x["clean_flagged"]
        bench += (f"<tr><td>{lab[k]}</td>" + "".join(f"<td>{c[n][0]}/{c[n][1]}</td>" for n in ("checklist", "exact")) +
                  f"<td><b>{c['rocheck'][0]}/{c['rocheck'][1]}</b></td><td>{cf['exact']}/{x['clean']}</td><td><b>{cf['rocheck']}/{x['clean']}</b></td></tr>")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Warranty story check</title><style>
:root{{--bg:#f4f5f7;--fg:#15181d;--mut:#5c6472;--card:#fff;--line:#e0e3e9}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}}
main{{max-width:1150px;margin:0 auto;padding:26px 16px 60px}}h1{{font-size:25px;margin:0 0 4px}}h2{{font-size:17px;margin:24px 0 8px}}
.sub{{color:var(--mut)}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}@media(max-width:820px){{.grid{{grid-template-columns:1fr}}}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px}}.turn{{margin:6px 0;font-size:14px}}
.who{{display:inline-block;background:#e8ecf3;border-radius:5px;padding:0 6px;font-size:12px;color:#334}}.norm{{color:#1d6b45;font-family:Consolas,monospace;font-size:13px}}
.sec{{margin:6px 0;font-size:14px}}.sec b{{display:inline-block;width:92px;color:var(--mut);text-transform:capitalize}}
table{{width:100%;border-collapse:collapse;background:var(--card);font-size:13.5px}}td,th{{border:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}}
td.hold{{color:#fff;background:#b3261e;font-weight:700}}td.fix{{background:#f6c445;font-weight:700}}ul{{margin:4px 0;padding-left:18px;font-size:14px}}
.verdict{{display:inline-block;padding:2px 12px;border-radius:6px;background:#b3261e;color:#fff;font-weight:700}}
</style></head><body><main>
<h1>AI-written warranty story, checked before it reaches the DMS</h1>
<div class="sub">Synthetic repair order. Rules: GM Service Bulletin 06-00-89-026J (3C fields, CCND labor ops), GM TechLink battery tester codes. Unofficial prototype by Kushagra Pratap Singh, not affiliated with Revion.</div>
<div class="grid" style="margin-top:14px">
<div class="card"><b>What the technician said</b> (transcribed, then normalized){tr}</div>
<div class="card"><b>Scan report</b><ul>{scan}</ul><b>RO lines</b><ul>{ops}</ul><b>Parts</b><ul>{parts}</ul><b>Time punches</b><ul>{''.join(f"<li>{e(p['op'])} {p['hours']} h</li>" for p in ro['punches']) or '<li>none</li>'}</ul></div>
</div>
<h2>AI draft of the 3C story → <span class="verdict">{r['verdict']}</span></h2><div class="card">{draft}</div>
<h2>Findings (every one cites its evidence and rule)</h2><div style="overflow-x:auto"><table><tr><th></th><th>code</th><th>finding</th><th>evidence</th><th>rule</th></tr>{rows}</table></div>
<h2>Repaired draft (grounded facts only)</h2><div class="card">{fixed}</div>
<h2>Benchmark: planted problems caught, clean ROs wrongly flagged</h2><div style="overflow-x:auto"><table><tr><th>set</th><th>required-field checklist</th><th>exact-string match</th><th>rocheck</th><th>clean flagged (exact)</th><th>clean flagged (rocheck)</th></tr>{bench}</table></div>
</main></body></html>"""


if __name__ == "__main__":
    main()
