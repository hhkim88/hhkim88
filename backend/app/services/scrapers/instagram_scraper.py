"""인스타그램 셀럽 언급 스크래퍼 (instaloader 기반)"""
import asyncio
from datetime import date, timedelta, datetime, timezone
from dataclasses import dataclass
from typing import Optional
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential


@dataclass
class InstagramPost:
    shortcode: str
    caption: str
    likes: int
    comments: int
    published_at: date
    is_tagged: bool = False


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=2, min=5, max=30))
async def scrape_celebrity_instagram(
    instagram_handle: str,
    celebrity_name: str,
    week_start: date,
    max_posts: int = 20,
) -> list[InstagramPost]:
    """셀럽 인스타그램 계정에서 주간 게시물 수집"""
    if not instagram_handle:
        logger.debug(f"[Instagram] {celebrity_name}: 핸들 없음 - 스킵")
        return []

    return await asyncio.to_thread(
        _scrape_instagram_sync, instagram_handle, celebrity_name, week_start, max_posts
    )


def _scrape_instagram_sync(
    handle: str,
    celebrity_name: str,
    week_start: date,
    max_posts: int,
) -> list[InstagramPost]:
    try:
        import instaloader
    except ImportError:
        logger.warning("instaloader 미설치 - 빈 결과 반환")
        return []

    L = instaloader.Instaloader(
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        quiet=True,
    )

    week_end = week_start + timedelta(days=6)
    posts = []

    try:
        profile = instaloader.Profile.from_username(L.context, handle)
        for post in profile.get_posts():
            post_date = post.date_utc.date()

            # 주간 범위 외 이전 게시물이면 중단
            if post_date < week_start:
                break

            if week_start <= post_date <= week_end:
                posts.append(InstagramPost(
                    shortcode=post.shortcode,
                    caption=post.caption or "",
                    likes=post.likes,
                    comments=post.comments,
                    published_at=post_date,
                ))

            if len(posts) >= max_posts:
                break

        logger.info(f"[Instagram] {celebrity_name} (@{handle}): {len(posts)}건")
    except Exception as e:
        logger.warning(f"[Instagram] {celebrity_name} 수집 실패: {e}")

    return posts


async def scrape_celebrity_hashtag(
    celebrity_name: str,
    week_start: date,
    max_posts: int = 30,
) -> list[InstagramPost]:
    """셀럽 이름 해시태그 게시물 수집"""
    return await asyncio.to_thread(
        _scrape_hashtag_sync, celebrity_name, week_start, max_posts
    )


def _scrape_hashtag_sync(
    celebrity_name: str,
    week_start: date,
    max_posts: int,
) -> list[InstagramPost]:
    try:
        import instaloader
    except ImportError:
        return []

    L = instaloader.Instaloader(
        download_pictures=False,
        download_videos=False,
        quiet=True,
    )

    week_end = week_start + timedelta(days=6)
    hashtag = celebrity_name.replace(" ", "")
    posts = []

    try:
        for post in instaloader.Hashtag.from_name(L.context, hashtag).get_posts():
            post_date = post.date_utc.date()
            if post_date < week_start:
                break
            if week_start <= post_date <= week_end:
                posts.append(InstagramPost(
                    shortcode=post.shortcode,
                    caption=post.caption or "",
                    likes=post.likes,
                    comments=post.comments,
                    published_at=post_date,
                ))
            if len(posts) >= max_posts:
                break

        logger.info(f"[Instagram #{hashtag}]: {len(posts)}건")
    except Exception as e:
        logger.warning(f"[Instagram #{hashtag}] 해시태그 수집 실패: {e}")

    return posts
