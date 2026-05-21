"""Investment YouTube channel transcripts.

Two-step:
  1. yt-dlp finds recent video URLs matching the company query (channel-scoped).
  2. youtube-transcript-api fetches the auto/manual transcript.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime
from typing import Any

from .. import cache
from ..schema import CompanyDoc

# Channel handles (curated). Override via env or arg.
KO_CHANNELS = [
    "@syukaworld",          # 슈카월드
    "@삼프로TV_경제의신과함께",   # 삼프로TV
    "@understanding.",      # 언더스탠딩
    "@kimprotv",            # 김프로TV
    "@박곰희TV",
]
EN_CHANNELS = [
    "@AswathDamodaranonValuation",
    "@JosephCarlson",
    "@BenFelixCSI",
]


def _yt_search(query: str, channels: list[str], max_per_channel: int = 3) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for ch in channels:
        cmd = [
            "yt-dlp",
            "--dump-json",
            "--flat-playlist",
            "--no-warnings",
            "--playlist-end", str(max_per_channel),
            f"https://www.youtube.com/{ch}/search?query={query}",
        ]
        try:
            out = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=45,
            ).stdout
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            continue
        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            vid = obj.get("id") or obj.get("video_id")
            if not vid:
                continue
            items.append(
                {
                    "id": vid,
                    "title": obj.get("title", ""),
                    "url": f"https://www.youtube.com/watch?v={vid}",
                    "channel": ch,
                    "duration": obj.get("duration"),
                    "upload_date": obj.get("upload_date"),
                }
            )
    return items


def _fetch_transcript(video_id: str, lang_priority: list[str]) -> str:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        api = YouTubeTranscriptApi()
        for lang in lang_priority:
            try:
                fetched = api.fetch(video_id, languages=[lang])
                return " ".join(seg.text for seg in fetched)
            except Exception:
                continue
    except Exception:
        return ""
    return ""


@cache.cached("youtube", ttl=12 * 3600)
def search_youtube(
    company: str,
    limit: int = 5,
    market: str = "KR",
    channels: list[str] | None = None,
) -> list[dict[str, Any]]:
    if channels is None:
        channels = KO_CHANNELS if market == "KR" else EN_CHANNELS
    lang_priority = ["ko", "en"] if market == "KR" else ["en", "ko"]
    raw = _yt_search(company, channels, max_per_channel=max(2, limit // len(channels) + 1))
    out: list[dict[str, Any]] = []
    for v in raw[:limit]:
        transcript = _fetch_transcript(v["id"], lang_priority)
        if not transcript:
            continue
        published_at = None
        if v.get("upload_date"):
            try:
                published_at = datetime.strptime(v["upload_date"], "%Y%m%d")
            except ValueError:
                pass
        doc = CompanyDoc(
            company=company,
            ticker=None,
            market=market,
            source="youtube",
            url=v["url"],
            title=v["title"],
            body_md=transcript[:15000],
            published_at=published_at,
            metadata={"channel": v["channel"], "video_id": v["id"]},
        )
        out.append(doc.to_dict())
    return out
