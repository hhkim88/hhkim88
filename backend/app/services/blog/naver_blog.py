"""네이버 블로그 자동 포스팅 클라이언트 (OAuth 2.0)"""
import httpx
from loguru import logger
from app.config import settings
from .content_generator import BlogPost


NAVER_TOKEN_URL = "https://nid.naver.com/oauth2.0/token"
NAVER_BLOG_WRITE_URL = "https://openapi.naver.com/blog/writePost.json"


async def _refresh_access_token() -> str | None:
    """Refresh token으로 access token 갱신"""
    if not (settings.naver_client_id and settings.naver_client_secret and settings.naver_refresh_token):
        return None

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(NAVER_TOKEN_URL, data={
            "grant_type": "refresh_token",
            "client_id": settings.naver_client_id,
            "client_secret": settings.naver_client_secret,
            "refresh_token": settings.naver_refresh_token,
        })

    if resp.status_code != 200:
        logger.error(f"[NaverBlog] 토큰 갱신 실패: {resp.status_code} {resp.text}")
        return None

    data = resp.json()
    if "error" in data:
        logger.error(f"[NaverBlog] 토큰 갱신 오류: {data}")
        return None

    return data.get("access_token")


async def post_to_naver_blog(blog_post: BlogPost) -> dict:
    """네이버 블로그에 포스트 게시

    Returns:
        {"success": bool, "post_url": str | None, "error": str | None}
    """
    access_token = await _refresh_access_token()
    if not access_token:
        logger.warning("[NaverBlog] 액세스 토큰 없음 — 게시 스킵 (설정 확인 필요)")
        return {"success": False, "post_url": None, "error": "no_access_token"}

    tags_str = ",".join(blog_post.tags)

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            NAVER_BLOG_WRITE_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            data={
                "title": blog_post.title,
                "contents": blog_post.content_html,
                "tags": tags_str,
                "isOpen": "1",          # 1=공개, 0=비공개
            },
        )

    if resp.status_code == 200:
        data = resp.json()
        post_url = data.get("result", {}).get("postUrl") or data.get("postUrl")
        logger.info(f"[NaverBlog] 게시 완료: {blog_post.title} → {post_url}")
        return {"success": True, "post_url": post_url, "error": None}

    logger.error(f"[NaverBlog] 게시 실패: {resp.status_code} {resp.text}")
    return {"success": False, "post_url": None, "error": resp.text[:200]}
