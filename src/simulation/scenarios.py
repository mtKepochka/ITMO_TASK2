from __future__ import annotations

from .config import SimulationConfig


def baseline() -> SimulationConfig:
    return SimulationConfig()


SCENARIOS = {"baseline": baseline}


def get_scenario(name: str) -> SimulationConfig:
    try:
        return SCENARIOS[name]()
    except KeyError as error:
        raise ValueError(f"unknown simulation scenario: {name}") from error
