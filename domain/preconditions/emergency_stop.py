"""Emergency stop precondition."""

from typing import Any, Dict, Optional

from domain.models.signal import Signal
from domain.preconditions.base import Precondition


class EmergencyStopPrecondition(Precondition):
    """Blocks all trading when emergency stop is active."""

    name = "emergency_stop"
    description = "Kill switch - blocks all trading immediately"
    live_mode_only = False

    def check(self, signal: Signal, context: Dict[str, Any]) -> Optional[str]:
        if context["trading_config"].emergency_stop:
            return "Emergency stop is active"
        return None
