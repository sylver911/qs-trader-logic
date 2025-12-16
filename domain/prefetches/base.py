"""Base class for prefetch modules.

Prefetches are modular data fetchers that run in parallel before LLM analysis.
Each prefetch provides data that can be used directly in Jinja2 templates.

Usage in Jinja2 templates:
    {{ time.is_market_open }}
    {{ time.time_est }}
    {{ account.buying_power }}
    {{ option_chain.calls[0].strike }}
    {{ positions.count }}

Each prefetch has TEMPLATE_DOCS that describes available variables for the dashboard.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from domain.models.signal import Signal


@dataclass
class TemplateVariable:
    """Documentation for a single template variable."""
    name: str           # Variable name (e.g., "is_market_open")
    type: str           # Type (e.g., "bool", "string", "float", "list")
    description: str    # Human-readable description
    example: str        # Example value as string

    def to_dict(self) -> Dict[str, str]:
        return {
            "name": self.name,
            "type": self.type,
            "description": self.description,
            "example": self.example,
        }


@dataclass
class PrefetchResult:
    """Result of a prefetch operation.

    This class provides easy access to prefetched data in Jinja2 templates.
    All fields are accessible via dot notation: {{ result.field_name }}
    """
    success: bool = True
    error: Optional[str] = None
    _data: Dict[str, Any] = field(default_factory=dict)

    def __getattr__(self, name: str) -> Any:
        """Allow dot notation access to _data fields.

        This enables {{ time.is_market_open }} in templates.
        """
        if name.startswith('_'):
            raise AttributeError(name)
        return self._data.get(name)

    def __getitem__(self, key: str) -> Any:
        """Allow dict-style access: result['field']."""
        return self._data.get(key)

    def get(self, key: str, default: Any = None) -> Any:
        """Dict-compatible get method."""
        return self._data.get(key, default)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return {
            "success": self.success,
            "error": self.error,
            **self._data,
        }

    def to_template_context(self) -> Dict[str, Any]:
        """Get data ready for Jinja2 template context.

        Returns the raw data dict for easy template access.
        """
        if not self.success:
            return {"error": self.error, "success": False}
        return {**self._data, "success": True}

    @classmethod
    def from_data(cls, data: Dict[str, Any]) -> "PrefetchResult":
        """Create a successful result from data dict."""
        return cls(success=True, _data=data)

    @classmethod
    def from_error(cls, error: str) -> "PrefetchResult":
        """Create a failed result with error message."""
        return cls(success=False, error=error, _data={})


class Prefetch(ABC):
    """Base class for prefetch modules.

    Each prefetch module fetches specific data before LLM analysis.
    The data is made available in Jinja2 templates via the `key` attribute.

    TEMPLATE_DOCS provides documentation for the dashboard prompt editor.

    Example:
        class TimePrefetch(Prefetch):
            name = "current_time"
            key = "time"  # Accessible as {{ time.is_market_open }} in templates

            TEMPLATE_DOCS = [
                TemplateVariable("is_market_open", "bool", "NYSE is open", "true"),
                TemplateVariable("time_est", "string", "Current time in EST", "10:30:45"),
            ]

            def fetch(self, signal, context) -> PrefetchResult:
                return PrefetchResult.from_data({
                    "is_market_open": True,
                    "time_est": "10:30:00",
                })
    """

    # Unique identifier for this prefetch
    name: str = "base_prefetch"

    # Key used in Jinja2 templates (e.g., "time" -> {{ time.field }})
    key: str = "data"

    # Human-readable description
    description: str = "Base prefetch"

    # Whether this prefetch requires a ticker
    requires_ticker: bool = False

    # Whether this prefetch requires live broker connection
    requires_broker: bool = False

    # Whether to skip in dry run mode
    skip_in_dry_run: bool = False

    # Template variable documentation for dashboard
    # Override in subclasses with list of TemplateVariable
    TEMPLATE_DOCS: List[TemplateVariable] = []

    @classmethod
    def get_docs(cls) -> Dict[str, Any]:
        """Get documentation for this prefetch (for dashboard).

        Returns dict with:
        - key: Template key (e.g., "time")
        - name: Prefetch name
        - description: Human-readable description
        - variables: List of variable documentation
        - example_usage: Example Jinja2 code
        """
        return {
            "key": cls.key,
            "name": cls.name,
            "description": cls.description,
            "variables": [v.to_dict() for v in cls.TEMPLATE_DOCS],
            "example_usage": cls._generate_example_usage(),
        }

    @classmethod
    def _generate_example_usage(cls) -> str:
        """Generate example Jinja2 usage code."""
        if not cls.TEMPLATE_DOCS:
            return f"{{{{ {cls.key} }}}}"

        examples = []
        for var in cls.TEMPLATE_DOCS[:3]:  # First 3 variables
            examples.append(f"{{{{ {cls.key}.{var.name} }}}}")
        return "\n".join(examples)

    @abstractmethod
    def fetch(self, signal: "Signal", context: Dict[str, Any]) -> PrefetchResult:
        """Fetch the data.

        Args:
            signal: The trading signal being processed
            context: Shared context with broker, market_data, trading_config

        Returns:
            PrefetchResult with the fetched data
        """
        pass

    def should_run(self, signal: "Signal", context: Dict[str, Any]) -> bool:
        """Check if this prefetch should run.

        Override for custom logic (e.g., skip if no ticker).
        """
        if self.requires_ticker and not signal.ticker:
            return False

        if self.skip_in_dry_run:
            trading_config = context.get("trading_config")
            if trading_config and not trading_config.execute_orders:
                return False

        return True

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} key='{self.key}'>"
