"""Scheduled runs never authorize; standing trust runs only on a human dispatch with authorize=true."""
import re
from pathlib import Path

WF = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "colony-evolve.yml"


def test_authorize_is_off_unless_human_dispatch_says_true():
    s = WF.read_text(encoding="utf-8")
    inp = s[s.index("      authorize:"):]
    assert re.search(r'default:\s*"false"', inp[:400])
    steps = s.split("\n      - name: ")
    auth = [st for st in steps if "Authorizer(" in st]
    assert auth, "the mechanism is kept"
    for st in auth:
        cond = next(l for l in st.splitlines() if l.strip().startswith("if:"))
        assert "github.event_name == 'workflow_dispatch'" in cond
        assert "github.event.inputs.authorize == 'true'" in cond
        assert "!=" not in cond
