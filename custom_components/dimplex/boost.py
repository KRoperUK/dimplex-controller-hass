"""Track Home Assistant-initiated boost engagements.

The cloud exposes no boost-expiry field — ``BoostDuration`` is a configured
length, not a countdown — so the boost-remaining sensor synthesises its
countdown from the engage time and chosen duration recorded here. Recording
happens at the two places a boost can start inside Home Assistant (the
climate boost preset and the ``dimplex.set_boost`` action); a boost begun on
the heater or in the app has no record and reads unknown by design (#302).
"""

from __future__ import annotations

from typing import Any

from homeassistant.util import dt as dt_util


def record_boost_start(runtime: Any, appliance_id: str, duration_minutes: int) -> None:
    """Record a boost engagement for the countdown sensor."""
    starts = getattr(runtime, "boost_starts", None)
    if not isinstance(starts, dict):
        return
    starts[appliance_id] = {
        "started_at": dt_util.utcnow().isoformat(),
        "duration_minutes": int(duration_minutes),
    }


def clear_boost_start(runtime: Any, appliance_id: str) -> None:
    """Forget a boost engagement once it has been cleared."""
    starts = getattr(runtime, "boost_starts", None)
    if isinstance(starts, dict):
        starts.pop(appliance_id, None)
