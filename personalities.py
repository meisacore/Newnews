"""Cheap, explainable trader personalities. Wealth and judgment are independent."""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Personality:
    label: str
    strategy: str
    exposure: float
    order_min: float
    order_max: float
    impact_bps: int
    activation: float
    cooldown: tuple
    disciplined: bool = False


PERSONALITIES = {
    "patient_value": Personality(
        "Patient value investor", "value", 0.12, 0.005, 0.025, 200, 0.10, (5, 15), True
    ),
    "careful_trend": Personality(
        "Disciplined trend trader",
        "momentum",
        0.15,
        0.01,
        0.04,
        400,
        0.18,
        (4, 10),
        True,
    ),
    "contrarian": Personality(
        "Cautious contrarian", "value", 0.18, 0.01, 0.04, 350, 0.12, (5, 14), True
    ),
    "fomo": Personality(
        "FOMO chaser", "momentum", 0.45, 0.05, 0.18, 10000, 0.24, (4, 12)
    ),
    "gambler": Personality(
        "Impulsive gambler", "noise", 0.55, 0.06, 0.25, 18000, 0.18, (5, 18)
    ),
    "reckless_whale": Personality(
        "Reckless whale", "noise", 0.65, 0.08, 0.30, 25000, 0.08, (15, 40)
    ),
    "retail_noise": Personality(
        "Casual small trader", "noise", 0.20, 0.01, 0.06, 1500, 0.22, (2, 7)
    ),
}

# New entrants are funded once on upgrade, not refilled on tick or restart.
WEALTHY_ENTRANTS = (
    ("agent-whale-01", "Atlas", "patient_value", 500_000),
    ("agent-whale-02", "Sage", "contrarian", 350_000),
    ("agent-whale-03", "Comet", "reckless_whale", 1_500_000),
    ("agent-whale-04", "Lucky", "gambler", 750_000),
    ("agent-whale-05", "Echo", "fomo", 250_000),
    ("agent-whale-06", "Vector", "careful_trend", 400_000),
)


def intention(persona, price, reference, momentum, has_position, rng):
    """Return desired exposure fraction, perceived value, and an honest reason."""
    p = PERSONALITIES[persona]
    if persona in ("patient_value", "contrarian"):
        estimate = reference * math.exp(rng.gauss(0, 0.012))
        edge = math.log(estimate / price)
        if persona == "contrarian":
            edge -= 5 * momentum
        conviction = min(1, max(0, (edge - 0.008) / 0.12))
        return (
            p.exposure * conviction,
            estimate,
            "buy only at a perceived discount; otherwise hold or reduce exposure",
        )
    if persona == "careful_trend":
        conviction = min(1, max(0, (momentum - 0.001) * 35))
        estimate = price * math.exp(min(0.12, max(-0.12, momentum * 8)))
        return (
            p.exposure * conviction,
            estimate,
            "follow a sustained trend only when execution costs leave an edge",
        )
    if persona == "fomo":
        if has_position and (momentum < -0.003 or rng.random() < 0.08):
            return 0, None, "panic sell after a reversal or a sudden loss of confidence"
        if momentum > 0.001 or rng.random() < 0.12:
            return (
                p.exposure * rng.uniform(0.65, 1),
                None,
                "chase excitement without checking perceived value",
            )
        return None, None, "wait for excitement"
    if persona == "reckless_whale":
        choice = rng.random()
        if choice < 0.62:
            return (
                p.exposure * rng.uniform(0.7, 1),
                None,
                "oversized impulse buy; ignores perceived value and tolerates expensive execution",
            )
        if choice < 0.90 and has_position:
            return (
                0,
                None,
                "abandon the bet and dump the position, even at an unfavorable price",
            )
        return None, None, "sit out this opportunity"
    if persona == "gambler":
        if has_position and rng.random() < 0.3:
            return 0, None, "change their mind and sell without a valuation check"
        return (
            p.exposure * rng.choice([0, 0.3, 0.7, 1]),
            None,
            "make a speculative bet with a large slice of available cash",
        )
    if rng.random() < 0.35:
        return None, None, "hold"
    return p.exposure * rng.random(), None, "make a small discretionary trade"
