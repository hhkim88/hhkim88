"""네이버 블로그/카페 셀럽 언급 스크래퍼 (Playwright + BeautifulSoup)"""
import asyncio
import re
from datetime import datetime, date, timedelta
from typing import Optional
from dataclasses import dataclass, field
import httpx
from bs4 import BeautifulSoup
from loguru import logger
from app.config import settings
from tenacity import retry, stop_after_attempt, wait_exponential


@dataclass
class NaverPost:
    title: str
    content_preview: str
    url: str
    likes: int = 0
    comments: int = 0
    published_at: Optional[date] = None
    platform: str = "naver_blog"


async def _fetch_naver_search(query: str, display: int = 30, start: int = 1, search_type: str = "blog") -> dict:
    """네이버 검색 API 호출 (공식 API 우선, 없으면 웹 스크래핑 폴백)"""
    if settings.naver_client_id and settings.naver_client_secret:
        return await _fetch_via_naver_api(query, display, start, search_type)
    return await _fetch_via_playwright(query, search_type)


async def _fetch_via_naver_api(query: str, display: int, start: int, search_type: str) -> dict:
    url = f"https://openapi.naver.com/v1/search/{search_type}.json"
    headers = {
        "X-Naver-Client-Id": settings.naver_client_id,
        "X-Naver-Client-Secret": settings.naver_client_secret,
    }
    params = {"query": query, "display": display, "start": start, "sort": "date"}

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, headers=headers, params=params)
        resp.raise_for_status()
        return resp.json()


async def _fetch_via_playwright(query: str, search_type: str) -> dict:
    """Playwright로 네이버 검색 결과 스크래핑"""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.warning("Playwright 미설치 - 빈 결과 반환")
        return {"items": []}

    where = "blog" if search_type == "blog" else "cafearticle"
    search_url = f"https://search.naver.com/search.naver?query={query}&where={where}&sm=tab_opt&nso=so%3Add"

    items = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            await page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(1)

            html = await page.content()
            soup = BeautifulSoup(html, "lxml")

            # 네이버 블로그 검색 결과 파싱
            for item in soup.select("li.bx")[:20]:
                title_el = item.select_one(".title_link, .api_txt_lines")
                desc_el = item.select_one(".dsc_link, .desc_txt")
                date_el = item.select_one(".sub_time, .date")

                if not title_el:
                    continue

                pub_date = None
                if date_el:
                    date_text = date_el.get_text(strip=True)
                    pub_date = _parse_korean_date(date_text)

                items.append({
                    "title": title_el.get_text(strip=True),
                    "description": desc_el.get_text(strip=True) if desc_el else "",
                    "link": title_el.get("href", ""),
                    "pubDate": pub_date.isoformat() if pub_date else "",
                })
        finally:
            await browser.close()

    return {"items": items}


def _parse_korean_date(text: str) -> Optional[date]:
    """'2024.01.15', '3일 전', '1시간 전' 형식 파싱"""
    today = date.today()
    text = text.strip()

    # YYYY.MM.DD 형식
    m = re.search(r"(\d{4})\.(\d{2})\.(\d{2})", text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass

    # N일 전
    m = re.search(r"(\d+)일 전", text)
    if m:
        return today - timedelta(days=int(m.group(1)))

    # N시간 전 / 방금 전
    if "시간 전" in text or "분 전" in text or "방금" in text:
        return today

    return None


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def scrape_celebrity_mentions(
    celebrity_name: str,
    week_start: date,
    platforms: list[str] = None,
) -> list[NaverPost]:
    """셀럽 이름으로 네이버 블로그/카페 언급 수집"""
    if platforms is None:
        platforms = ["blog", "cafearticle"]

    week_end = week_start + timedelta(days=6)
    posts = []

    for search_type in platforms:
        try:
            data = await _fetch_naver_search(celebrity_name, display=30, search_type=search_type)
            platform_name = "naver_blog" if search_type == "blog" else "naver_cafe"

            for item in data.get("items", []):
                pub_date = _parse_korean_date(item.get("pubDate", ""))
                if pub_date and not (week_start <= pub_date <= week_end):
                    continue

                title = re.sub(r"<[^>]+>", "", item.get("title", ""))
                desc = re.sub(r"<[^>]+>", "", item.get("description", ""))

                posts.append(NaverPost(
                    title=title,
                    content_preview=desc,
                    url=item.get("link", ""),
                    published_at=pub_date,
                    platform=platform_name,
                ))

            logger.info(f"[네이버 {platform_name}] {celebrity_name}: {len(posts)}건 수집")
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.error(f"[네이버] {celebrity_name} 수집 실패: {e}")

    return posts
