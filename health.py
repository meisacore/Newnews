"""Simulation liveness, sampled after reading the committed heartbeat."""

LIVE_SECONDS = 10
PAUSED_SECONDS = 30


def simulation_status(last_tick, observed_at):
    age = max(0, observed_at - last_tick) if last_tick is not None else None
    status = (
        "paused"
        if age is None or age > PAUSED_SECONDS
        else "delayed"
        if age > LIVE_SECONDS
        else "live"
    )
    return {
        "running": status != "paused",
        "status": status,
        "last_tick_at": last_tick,
        "age_seconds": age,
    }
