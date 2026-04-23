"""유튜브 셀럽 언급 댓글/영상 스크래퍼"""
import asyncio
import re
from datetime import date, timedelta
from dataclasses import dataclass
from typing import Optional
import httpx
from loguru import logger
from app.config import settings
from tenacity import retry, stop_after_attempt, wait_exponential


@dataclass
class YouTubeItem:
    video_id: str
    title: str
    comment_count: int
    like_count: int
    view_count: int
    published_at: Optional[date]
    top_comments: list[str]


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def scrape_celebrity_youtube(
    celebrity_name: str,
    week_start: date,
    max_videos: int = 10,
) -> list[YouTubeItem]:
    """셀럽 관련 유튜브 영상 및 댓글 수집"""
    if settings.youtube_api_key:
        return await _fetch_via_youtube_api(celebrity_name, week_start, max_videos)
    return await _fetch_via_scraping(celebrity_name, week_start, max_videos)


async def _fetch_via_youtube_api(
    query: str,
    week_start: date,
    max_videos: int,
) -> list[YouTubeItem]:
    week_end = week_start + timedelta(days=6)
    published_after = f"{week_start.isoformat()}T00:00:00Z"
    published_before = f"{(week_end + timedelta(days=1)).isoformat()}T00:00:00Z"

    search_url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "publishedAfter": published_after,
        "publishedBefore": published_before,
        "maxResults": max_videos,
        "regionCode": "KR",
        "relevanceLanguage": "ko",
        "key": settings.youtube_api_key,
    }

    items = []
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(search_url, params=params)
        if resp.status_code != 200:
            logger.warning(f"[YouTube API] 오류: {resp.status_code}")
            return []

        data = resp.json()
        video_ids = [i["id"]["videoId"] for i in data.get("items", [])]

        if not video_ids:
            return []

        # 통계 데이터 조회
        stats_url = "https://www.googleapis.com/youtube/v3/videos"
        stats_resp = await client.get(stats_url, params={
            "part": "statistics,snippet",
            "id": ",".join(video_ids),
            "key": settings.youtube_api_key,
        })
        stats_data = stats_resp.json()

        for video in stats_data.get("items", []):
            stats = video.get("statistics", {})
            snippet = video.get("snippet", {})
            pub_str = snippet.get("publishedAt", "")[:10]

            try:
                pub_date = date.fromisoformat(pub_str)
            except ValueError:
                pub_date = None

            items.append(YouTubeItem(
                video_id=video["id"],
                title=snippet.get("title", ""),
                comment_count=int(stats.get("commentCount", 0)),
                like_count=int(stats.get("likeCount", 0)),
                view_count=int(stats.get("viewCount", 0)),
                published_at=pub_date,
                top_comments=[],
            ))

    logger.info(f"[YouTube API] {query}: {len(items)}건")
    return items


async def _fetch_via_scraping(
    query: str,
    week_start: date,
    max_videos: int,
) -> list[YouTubeItem]:
    """YouTube 검색 결과 스크래핑 (API 키 없을 때 폴백)"""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return []

    search_url = f"https://www.youtube.com/results?search_query={query}&sp=EgIIAQ%3D%3D"
    items = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            await page.goto(search_url, wait_until="networkidle", timeout=25000)
            await asyncio.sleep(2)

            html = await page.content()
            video_ids = list(set(re.findall(r'"videoId":"([A-Za-z0-9_-]{11})"', html)))[:max_videos]

            for vid_id in video_ids:
                items.append(YouTubeItem(
                    video_id=vid_id,
                    title="",
                    comment_count=0,
                    like_count=0,
                    view_count=0,
                    published_at=None,
                    top_comments=[],
                ))
        finally:
            await browser.close()

    logger.info(f"[YouTube 스크래핑] {query}: {len(items)}건")
    return items
