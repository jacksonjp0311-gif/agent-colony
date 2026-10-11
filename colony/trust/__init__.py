"""Trust loop (2026-10-11): enforceable gates, promotion categories, ablation switches,
rollback journal and the out-of-loop holdout harness.

Boundary: nothing under ``colony/`` imports or reads ``evaluation/`` (the frozen holdout and
its independent evaluator). ``tests/test_trust_isolation.py`` enforces that statically.
"""
