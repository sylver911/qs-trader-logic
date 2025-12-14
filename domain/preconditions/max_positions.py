"""Max positions precondition."""

from typing import Any, Dict, Optional

from domain.models.signal import Signal
from domain.preconditions.base import Precondition


class MaxPositionsPrecondition(Precondition):
    """Blocks trading when maximum concurrent positions reached."""

    name = "max_positions"
    description = "Limits concurrent open positions"
    live_mode_only = True

    def check(self, signal: Signal, context: Dict[str, Any]) -> Optional[str]:
        max_positions = context["trading_config"].max_concurrent_positions
        broker = context["broker"]

        positions = broker.get_positions()
        if len(positions) >= max_positions:
            return f"Max concurrent positions ({max_positions}) reached"

        return None
