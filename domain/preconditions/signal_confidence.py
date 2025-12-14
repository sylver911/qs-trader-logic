"""Signal confidence precondition."""

from typing import Any, Dict, Optional

from domain.models.signal import Signal
from domain.preconditions.base import Precondition


class SignalConfidencePrecondition(Precondition):
    """Checks if signal confidence meets minimum threshold."""

    name = "signal_confidence"
    description = "Requires minimum signal confidence score"
    live_mode_only = False

    def check(self, signal: Signal, context: Dict[str, Any]) -> Optional[str]:
        min_confidence = context["trading_config"].min_ai_confidence_score

        if signal.confidence and signal.confidence < min_confidence:
            return f"Signal confidence {signal.confidence:.0%} below minimum {min_confidence:.0%}"

        return None
