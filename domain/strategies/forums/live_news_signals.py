"""Strategy for 📰live-news-signals forum.

News-based trading signals. NOT YET IMPLEMENTED.
"""

from domain.strategies.base import SkipStrategy


class LiveNewsStrategy(SkipStrategy):
    """News-based trading strategy. (NOT IMPLEMENTED)"""

    name = "live_news"
    description = "News-based trading signals"

    forum_id = "1392947656837562450"
    forum_name_pattern = r"live-news-signals"

    def __init__(self):
        super().__init__(reason="News signals strategy not implemented")

    # TODO: Implement news-based trading logic
    # Consider: sentiment analysis, event-driven trades, etc.
