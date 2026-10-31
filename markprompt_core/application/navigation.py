"""Remember the search results a document was opened from."""
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SearchReturn:
    workspace: Path
    directory: Path
    term: str
    hits: frozenset
    rows: tuple
    history: tuple
    listed: dict
    scroll: float
    pending: bool = False
    top_index: str = '1.0'


class NavigationMemory:
    """Remember the workspace search to resume when a document is closed."""

    def __init__(self):
        self.search = None

    def clear(self):
        self.search = None

    def remember(self, point):
        self.search = point

