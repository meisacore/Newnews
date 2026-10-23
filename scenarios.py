"""Fixed, isolated simulation scenarios; no external price feeds or real funds."""

SCENARIOS = {
    "balanced": {
        "label": "Balanced",
        "description": "Mixed sentiment, patient investors and speculative traders.",
        "drift": 0,
        "activity": 1,
        "appetite": 1,
    },
    "bull": {
        "label": "Bull run",
        "description": "Stronger buying interest, with profit taking and pullbacks.",
        "drift": 0.0005,
        "activity": 1.25,
        "appetite": 1.25,
    },
    "bear": {
        "label": "Bear market",
        "description": "Lower risk appetite, defensive exits and bargain hunters.",
        "drift": -0.0005,
        "activity": 1.1,
        "appetite": 0.55,
    },
    "mania": {
        "label": "Meme mania",
        "description": "Fast turnover, impulsive entries and frequent reversals.",
        "drift": 0,
        "activity": 1.7,
        "appetite": 1.15,
    },
}
