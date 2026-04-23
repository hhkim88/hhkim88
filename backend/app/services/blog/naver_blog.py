"""네이버 블로그 자동 포스팅 — Playwright 브라우저 자동화"""
import asyncio
import json
import re
from loguru import logger
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

from app.config import settings
from .content_generator import BlogPost

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


async def post_to_naver_blog(blog_post: BlogPost) -> dict:
    """Playwright로 네이버 블로그에 로그인 후 포스트 자동 게시

    Returns:
        {"success": bool, "post_url": str | None, "error": str | None}
    """
    username = settings.naver_username
    password = settings.naver_password

    if not username or not password:
        logger.warning("[NaverBlog] NAVER_USERNAME / NAVER_PASSWORD 미설정 — 포스팅 건너뜀")
        return {"success": False, "post_url": None, "error": "credentials_missing"}

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = await browser.new_context(
            user_agent=_UA,
            locale="ko-KR",
            viewport={"width": 1280, "height": 900},
        )
        page = await context.new_page()

        try:
            # ── 1. 네이버 로그인 ──────────────────────────────────────────────
            await page.goto("https://nid.naver.com/nidlogin.login", wait_until="domcontentloaded")
            await page.locator("#id").fill(username)
            await page.locator("#pw").fill(password)
            await page.locator(".btn_login").click()
            await page.wait_for_url(re.compile(r"naver\.com(?!/nid)"), timeout=20000)
            logger.info("[NaverBlog] 로그인 완료")

            # ── 2. 글쓰기 페이지 이동 ────────────────────────────────────────
            await page.goto(
                f"https://blog.naver.com/PostWriteForm.naver?blogId={username}",
                wait_until="networkidle",
                timeout=30000,
            )
            await page.wait_for_timeout(3000)   # SmartEditor ONE 로딩 대기

            # ── 3. 제목 입력 ─────────────────────────────────────────────────
            for sel in [".se-title-input", "#title", "input[placeholder='제목']",
                        "[data-placeholder='제목']"]:
                el = page.locator(sel).first
                if await el.count() > 0:
                    await el.click()
                    await page.keyboard.type(blog_post.title, delay=20)
                    break

            # ── 4. 본문 입력 (SmartEditor ONE iframe) ────────────────────────
            content_typed = False

            # iframe 내부 contenteditable 탐색
            for frame in page.frames:
                try:
                    body = frame.locator(
                        "body[contenteditable='true'], .se-content[contenteditable='true']"
                    ).first
                    if await body.count() > 0:
                        await body.click()
                        await body.type(blog_post.content_text, delay=5)
                        content_typed = True
                        break
                except Exception:
                    continue

            if not content_typed:
                # SmartEditor API 또는 contenteditable fallback
                await page.evaluate(
                    "text => { const el = document.querySelector("
                    "'.se-content,[contenteditable=\"true\"]'); if (el) el.textContent = text; }",
                    blog_post.content_text,
                )

            # ── 5. 태그 입력 ─────────────────────────────────────────────────
            for sel in [".se-tag-input input", "input[placeholder*='태그']", "#tagInput"]:
                tag_el = page.locator(sel).first
                if await tag_el.count() > 0:
                    await tag_el.click()
                    for tag in blog_post.tags[:10]:
                        await page.keyboard.type(tag, delay=20)
                        await page.keyboard.press("Enter")
                        await page.wait_for_timeout(200)
                    break

            # ── 6. 발행 ──────────────────────────────────────────────────────
            for sel in ["button:has-text('발행')", ".publish-btn", "#publishBtn",
                        "button[class*='publish']"]:
                btn = page.locator(sel).first
                if await btn.count() > 0:
                    await btn.click()
                    break

            await page.wait_for_timeout(2000)

            # 발행 확인 팝업
            for sel in ["button:has-text('발행'):visible", ".se-popup-button-publish",
                        "[class*='confirm']:has-text('발행')"]:
                confirm = page.locator(sel).first
                if await confirm.count() > 0:
                    await confirm.click()
                    break

            await page.wait_for_timeout(3000)
            post_url = page.url
            logger.info(f"[NaverBlog] 게시 완료: {post_url}")
            return {"success": True, "post_url": post_url, "error": None}

        except PWTimeout as e:
            logger.error(f"[NaverBlog] 타임아웃: {e}")
            return {"success": False, "post_url": None, "error": f"timeout: {e}"}
        except Exception as e:
            logger.error(f"[NaverBlog] 포스팅 실패: {e}")
            return {"success": False, "post_url": None, "error": str(e)}
        finally:
            await browser.close()
