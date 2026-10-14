import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rocheck.bank_dev import BANK  # noqa: E402
from rocheck.check import check  # noqa: E402
from rocheck.facts import conditions, extract  # noqa: E402
from rocheck.spoken import normalize  # noqa: E402
from rocheck.synth import scenario  # noqa: E402


def test_spoken_forms():
    assert normalize("scan shows pee zero three oh three stored") == "scan shows P0303 stored"
    assert normalize("history code pee zero zero see six") == "history code P00C6"
    assert normalize("eleven point eight volts and point four ohms") == "11.8 volts and 0.4 ohms"
    assert normalize("part number one two six three five two seven three") == "part number 12635273"
    assert normalize("high side two fifty psi, circuit two three five, connector ex two") == "high side 250 psi, circuit 235, connector X2"


def test_fact_kinds_and_context():
    f = dict((k, v) for k, v, _ in extract("SI doc ID 3410982. measured 28 pounds at the LF tire. hub bolts 150 pounds.", spoken=True)
             if k in ("sidoc",))
    assert f == {"sidoc": "3410982"}
    meas = {v for k, v, _ in extract("measured 28 pounds at the LF tire. hub bolts 150 pounds.", spoken=True) if k == "meas"}
    assert meas == {(28.0, "psi"), (150.0, "ft-lb")}
    assert {v for k, v, _ in extract("Coil 0.4 ohm (spec 0.3-0.6 ohm). Vent 58°F, 11.8V.") if k == "meas"} == {(0.4, "ohm"), (58.0, "deg"), (11.8, "V")}
    assert conditions("end play 0.3 mil") == set() and "mil_on" in conditions("MIL on at cold start")


def test_clean_drafts_pass():
    for seed in range(1, 200):
        s = scenario(seed, BANK)
        if s["defect"] is None:
            r = check(s["ro"], s["used_codes"])
            assert r["verdict"] == "READY", (seed, r["findings"])


def test_planted_defects_caught_with_citations():
    for seed in range(1, 200):
        s = scenario(seed, BANK)
        if s["defect"]:
            r = check(s["ro"], s["used_codes"])
            codes = {f["code"] for f in r["findings"]}
            assert codes & s["expect"], (seed, s["defect"], codes)
            assert all(f["rule"] and f["cite"] for f in r["findings"])


def test_contradiction_cites_the_evidence():
    from demo import build_demo
    ro, r = build_demo()
    c = [f for f in r["findings"] if f["code"] == "CONTRADICTED"]
    assert any("P0303" in f["msg"] and f["cite"].startswith("transcript") for f in c)
    assert any("0.4 ohm" in f["msg"] for f in c)
    assert r["verdict"] == "HOLD"


def test_repaired_story_only_keeps_grounded_facts():
    from demo import build_demo
    ro, r = build_demo()
    again = dict(ro, story=r["repaired"], punches=[{"op": "J4510", "hours": 0.6}])
    res = check(again)
    assert not [f for f in res["findings"] if f["code"] in ("UNSUPPORTED", "CONTRADICTED", "MISSING_CONDITION", "CAUSE_NO_DTC", "MISSING_FACT")]


def test_ccnd_and_battery_rules():
    base = scenario(1, BANK)["ro"]
    ro = dict(base, ops=[{"op": "J9992", "desc": "CCND", "hours": 0.5, "approval": False, "dep_dtc": "P0700"}],
              punches=[{"op": "J9992", "hours": 0.2}], parts=[{"pn": "24262323", "desc": "battery", "causal": False}],
              battery_code={"code": "ABCDEFGHJKLMNOPQRSTU", "vin": "X"})
    codes = {f["code"] for f in check(ro, used_battery_codes={"ABCDEFGHJKLMNOPQRSTU"})["findings"]}
    assert {"J9992_BAD_CODE", "CCND_HOURS", "CCND_NO_APPROVAL", "CCND_CLOCK", "BATTERY_CODE_INVALID", "BATTERY_CODE_REUSED", "BATTERY_CODE_VIN"} <= codes
