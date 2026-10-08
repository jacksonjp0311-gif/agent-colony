"""Claims reach the Oracle through the real CommBus (genuine, validated receipts), and
genuinely new Oracle-passed checks can register as novelty hits under the unchanged gate."""
from __future__ import annotations

import json

import pytest

import colony.claim_pipeline as CP
import colony.lessons as L
import colony.novelty_gate as NG
import colony.oracle as O
from colony.bus import CommBus
from colony.oracle import OracleVerdict
from colony.registry import AgentRegistry


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Every persisted artifact goes to tmp; nothing in the repo is touched."""
    monkeypatch.setattr(O, "ORACLE_LOG", tmp_path / "oracle.jsonl")
    monkeypatch.setattr(O, "ORACLE_SYSTEM", tmp_path / "oracle.json")
    monkeypatch.setattr(O, "WITNESS_NOTE", tmp_path / "WITNESS_ORACLE.md")
    monkeypatch.setattr(L, "LESSONS_JSONL", tmp_path / "lessons.jsonl")
    monkeypatch.setattr(L, "LEDGER_SYSTEM", tmp_path / "lesson_ledger.json")
    for attr, fn in (("LESSONS", "lessons.jsonl"), ("HISTORY", "conjecture_history.jsonl"),
                     ("KNOWN", "known_identities.json"), ("GATE_LOG", "novelty_gate.jsonl"),
                     ("GATE_SYSTEM", "novelty_gate.json")):
        monkeypatch.setattr(NG, attr, tmp_path / fn)
    monkeypatch.setattr(CP, "CLAIMS_JSONL", tmp_path / "extracted_claims.jsonl")
    monkeypatch.setattr(CP, "PIPELINE_SYSTEM", tmp_path / "claim_pipeline.json")
    monkeypatch.setattr(CP, "_oracle_seen_claims", lambda limit=500: set())
    monkeypatch.setattr(CP, "_theme_pass_count", lambda theme_id, limit=500: 0)
    monkeypatch.setenv("ORACLE_STRICT_CLAIMS", "1")
    return tmp_path


def _bus():
    state: dict = {}
    reg = AgentRegistry(state)
    return CommBus(state, reg), state


def _claim(theme="catalan", cid="cl_catalan_x1"):
    return CP.ExtractedClaim(
        claim_id=cid, theme_id=theme, text=f"CLAIM CANDIDATE (not discovered): `{theme}` …",
        provenance={"arxiv_id": "2610.00001", "url": "https://arxiv.org/abs/2610.00001"},
        bench_hint="lemma_microbench hard:catalan*", status="hard_checked", hard_ok=True,
        note="lemma score=0.9 hard_pass=40/41",
    )


def _sense_pass(monkeypatch):
    monkeypatch.setattr(O, "sense", lambda **kw: {"kills": [], "sense_pass": True})


def _oracle_rows(sandbox):
    p = sandbox / "oracle.jsonl"
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


# ------------------------------------------------------------------ bus receipts

def test_claim_posted_on_real_bus_receipt_validated_and_oracle_bus_ok(sandbox, monkeypatch):
    _sense_pass(monkeypatch)
    bus, state = _bus()
    c = _claim()
    out = CP.propose_checked([c], cycle_id="c1", bus=bus)
    assert len(out) == 1
    rec = c.provenance["bus_receipt"]
    assert rec["channel"] == "math" and rec["cycle_id"] == "c1" and rec["claim_id"] == c.claim_id
    # the claim post really is in the CommBus log (society state) on its channel
    msgs = {m["id"]: m for m in state["bus"]["messages"]}
    assert msgs[rec["msg_id"]]["channel"] == "math" and msgs[rec["msg_id"]]["cycle_id"] == "c1"
    assert any(x.get("id") == rec["msg_id"] for x in state["communications"])
    rows = _oracle_rows(sandbox)
    assert len(rows) == 1  # one Oracle run per claim (novelty uses that verdict)
    r = rows[0]
    assert r["passed"] is True and r["hear"]["bus_ok"] is True
    # the Oracle's own HEAR debate landed in the same real log
    assert r["hear"]["msg_ids"] and all(m in msgs for m in r["hear"]["msg_ids"])
    assert "oracle_blocked_no_bus" not in json.dumps(rows)


def test_no_bus_still_blocked(sandbox, monkeypatch):
    _sense_pass(monkeypatch)
    c = _claim()
    assert CP.propose_checked([c], cycle_id="c1", bus=None) == []
    rows = _oracle_rows(sandbox)
    assert rows[-1]["kills"] == ["oracle_blocked_no_bus"] and rows[-1]["passed"] is False
    assert "bus_receipt_invalid_or_missing" in c.note


class _GhostBus:
    """Old _NullBus shape: hands out ids but logs nothing."""

    def __init__(self):
        self.n = 0

    def post(self, **kw):
        self.n += 1
        return {"id": f"nullbus_{self.n}"}

    def messages(self):
        return []

    def record_peer_cite(self, **kw):
        return None

    def record_action_changed(self, **kw):
        return None


def test_ghost_bus_receipt_is_rejected_and_oracle_blocked(sandbox, monkeypatch):
    _sense_pass(monkeypatch)
    c = _claim()
    assert CP.propose_checked([c], cycle_id="c1", bus=_GhostBus()) == []
    rows = _oracle_rows(sandbox)
    assert rows[-1]["kills"] == ["oracle_blocked_no_bus"]
    assert "bus_receipt_invalid_or_missing" in c.note


def test_forged_or_mismatched_receipts_fail_validation():
    bus, _state = _bus()
    c = _claim()
    rec = CP.post_claim(bus, c, cycle_id="c1")
    ok = dict(rec)
    assert CP.validate_bus_receipt(bus, ok, claim_id=c.claim_id, cycle_id="c1") is True
    assert CP.validate_bus_receipt(bus, None, claim_id=c.claim_id, cycle_id="c1") is False
    assert CP.validate_bus_receipt(bus, {**ok, "msg_id": "msg_forged00"}, claim_id=c.claim_id, cycle_id="c1") is False
    assert CP.validate_bus_receipt(bus, {**ok, "channel": "science"}, claim_id=c.claim_id, cycle_id="c1") is False
    assert CP.validate_bus_receipt(bus, {**ok, "channel": "forum"}, claim_id=c.claim_id, cycle_id="c1") is False
    assert CP.validate_bus_receipt(bus, ok, claim_id=c.claim_id, cycle_id="c2") is False
    assert CP.validate_bus_receipt(bus, ok, claim_id="cl_other", cycle_id="c1") is False
    assert CP.validate_bus_receipt(None, ok, claim_id=c.claim_id, cycle_id="c1") is False
    # theme → channel routing
    assert CP.claim_channel("fft_signal") == "science" and CP.claim_channel("fibonacci_identities") == "math"


def test_oracle_bus_requirement_itself_unchanged(sandbox):
    v = O.evaluate(mutation="catalan", kind="claim_theme", source="t", cycle_id="c1", bus=None)
    assert v.passed is False and v.kills == ["oracle_blocked_no_bus"]


# ------------------------------------------------------------------ novelty

NAME = "authored_motzkin_bounded__legendre_duplication_small_w1"
BASELINE = f'("{NAME}", check_{NAME}, False),\n'
ENABLED = f'("{NAME}", check_{NAME}, True),\n'


def _authored_record(sandbox):
    row = {"id": "les_auth", "type": "authored_check", "decision": "skip", "source": "conjecture_desk",
           "mutation": NAME, "family": "hard_tier", "what": f"authored disabled hard check `{NAME}`"}
    (sandbox / "lessons.jsonl").write_text(json.dumps(row) + "\n")


def _verdict(passed=True, mutation=NAME, kind="hard_enable", cycle_id="c1"):
    return OracleVerdict(passed=passed, fitness_credit=passed, mutation=mutation, kind=kind,
                         cycle_id=cycle_id, kills=[] if passed else ["held_out:x"])


@pytest.fixture
def no_second_oracle(monkeypatch):
    def boom(**kw):
        raise AssertionError("novelty gate must use the caller's verdict, not run the Oracle again")
    monkeypatch.setattr(O, "evaluate", boom)
    # held-out = live hard tier green (as in CI); keep the test independent of bench timing
    monkeypatch.setattr(NG, "held_out_harder_survives",
                        lambda m, k: {"survives": k == "hard_enable", "reason": "hard_tier_green_and_hard_enable"})


def _eval(**kw):
    args = dict(mutation=NAME, kind="hard_enable", claim_text=f"Kept `{NAME}` (hard_enable)",
                cycle_id="c1", oracle_verdict=_verdict(), oracle_verdict_required=True,
                baseline_src=BASELINE)
    args.update(kw)
    return NG.evaluate(**args)


def test_new_oracle_passed_authored_check_registers_as_novelty_hit(sandbox, no_second_oracle):
    _authored_record(sandbox)
    v = _eval()
    assert v["novel_to_commons"] is True, v["kills"]
    assert v["own_authoring_record_only"] is True and v["oracle_used"] == "caller_verdict"
    sysj = json.loads((sandbox / "novelty_gate.json").read_text())
    assert sysj["hits"] == 1 and sysj["kills"] == 0


def test_repeat_is_not_novel(sandbox, no_second_oracle):
    _authored_record(sandbox)
    assert _eval()["novel_to_commons"] is True
    # the desk recorded its judgment → a second claim of the same check is a repeat
    (sandbox / "conjecture_history.jsonl").write_text(json.dumps({"decision": "keep", "mutation": NAME}) + "\n")
    v = _eval(cycle_id="c2", oracle_verdict=_verdict(cycle_id="c2"))
    assert v["novel_to_commons"] is False
    assert "already_in_lesson_ledger_or_history" in v["kills"]


def test_other_traces_still_make_it_known(sandbox, no_second_oracle):
    _authored_record(sandbox)
    title = {"id": "les_t", "type": "oracle_kill", "source": "novelty_gate", "family": "process",
             "mutation": f"Chain `{NAME}` citing Some paper"}
    with (sandbox / "lessons.jsonl").open("a") as f:
        f.write(json.dumps(title) + "\n")
    assert "already_in_lesson_ledger_or_history" in _eval()["kills"]


def test_no_authoring_record_means_known_fail_closed(sandbox, no_second_oracle):
    (sandbox / "known_identities.json").write_text(json.dumps({"identities": [NAME]}))
    v = _eval()
    assert v["novel_to_commons"] is False and v["own_authoring_record_only"] is False


def test_other_gate_conditions_unchanged(sandbox, no_second_oracle):
    _authored_record(sandbox)
    assert "stripped_baseline_does_not_fail_usefulness" in _eval(baseline_src=ENABLED)["kills"]
    assert any(k.startswith("oracle_kill") for k in _eval(oracle_verdict=_verdict(passed=False))["kills"])
    assert "oracle_verdict_mismatch_fail_closed" in _eval(oracle_verdict=_verdict(cycle_id="other"))["kills"]
    assert "oracle_verdict_mismatch_fail_closed" in _eval(oracle_verdict=_verdict(mutation="x_y"))["kills"]
    assert "oracle_verdict_missing_fail_closed" in _eval(oracle_verdict=None)["kills"]
    # held-out still requires kind=hard_enable → a claim theme can never be a novelty hit
    v = _eval(kind="claim_theme", oracle_verdict=_verdict(kind="claim_theme"))
    assert v["novel_to_commons"] is False
    # textbook reuse still kills
    tb = "authored_cassini__catalan_w1"
    assert any(k.startswith("textbook_reuse") for k in
               _eval(mutation=tb, oracle_verdict=_verdict(mutation=tb))["kills"])
