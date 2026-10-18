"""Scheduled runs never authorize; standing trust runs only on a human dispatch with authorize=true."""
from pathlib import Path

import yaml

WF = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "colony-evolve.yml"


def test_authorize_is_off_unless_human_dispatch_says_true():
    wf = yaml.safe_load(WF.read_text(encoding="utf-8"))
    on = wf.get("on", wf.get(True))
    assert on["workflow_dispatch"]["inputs"]["authorize"]["default"] == "false"
    steps = [s for j in wf["jobs"].values() for s in j["steps"]]
    auth = [s for s in steps if "Authorizer(" in s.get("run", "")]
    assert auth, "the mechanism is kept"
    for s in auth:
        cond = s.get("if", "")
        assert "github.event_name == 'workflow_dispatch'" in cond
        assert "github.event.inputs.authorize == 'true'" in cond
        assert "!=" not in cond
