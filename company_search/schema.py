from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Literal

Market = Literal["KR", "US"]
SourceType = Literal[
    "news",
    "filing",
    "report",
    "social",
    "price",
    "fundamentals",
    "youtube",
    "consensus",
    "ir",
    "macro",
]
Stance = Literal["bull", "bear", "neutral"]


@dataclass
class CompanyDoc:
    company: str
    market: Market
    source: SourceType
    url: str
    title: str
    body_md: str
    ticker: str | None = None
    published_at: datetime | None = None
    sentiment: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.published_at is not None:
            d["published_at"] = self.published_at.isoformat()
        return d
