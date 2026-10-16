"""Instruments: measuring tools colony agents may call from their own Oracle-gated checks.

Instruments only *measure*. They never accept, enable, authorize or change a gate;
every claim built on an instrument reading still goes through the Oracle and the
0.70 P gate like any other proposal.
"""
from __future__ import annotations

INSTRUMENTS = {
    "sieve.count_pattern": "colony.instruments.sieve:count_pattern",
    "sieve.hl_constant": "colony.instruments.sieve:hl_constant",
    "sieve.hl_predict": "colony.instruments.sieve:hl_predict",
    "sieve.forecast_and_count": "colony.instruments.sieve:forecast_and_count",
}


def available() -> dict[str, str]:
    """Registry of instruments (name -> 'module:function')."""
    return dict(INSTRUMENTS)
