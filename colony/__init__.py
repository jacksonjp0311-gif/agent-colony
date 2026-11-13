"""Agent Colony — We light the spark and witness. We do not micromanage the city."""

__version__ = "0.2.1"
__authority__ = "human-principal"
__ethos__ = "We light the spark and witness. We do not micromanage the city."

# Path redirect and Hive learning guard for the control arm. Must run
# before submodule imports compute ``ROOT / "society"`` constants, so
# a control process (COLONY_ARM set before start) writes only under
# control/. Failures here must never break an import.
try:
    from colony.arm import install_runtime_hooks as _install_arm_hooks
    _install_arm_hooks()
except Exception:
    pass

