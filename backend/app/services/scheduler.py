"""주간 배치 스케줄러 - 매주 월요일 02:00 KST 자동 실행"""
import asyncio
from datetime import date, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.dialects.postgresql import insert

from app.db.database import AsyncSessionLocal
from app.models.celebrity import (
    Celebrity, WeeklyMention, WeeklyRanking,
    CelebrityProfile, IndustryRanking,
)
from app.services.scrapers.naver_scraper import scrape_celebrity_mentions
from app.services.scrapers.instagram_scraper import (
    scrape_celebrity_instagram, scrape_celebrity_hashtag
)
from app.services.scrapers.youtube_scraper import scrape_celebrity_youtube
from app.services.analyzer.mention_extractor import (
    aggregate_naver_mentions, aggregate_instagram_mentions, aggregate_youtube_mentions
)
from app.services.analyzer.ranker import calculate_marketing_scores, INDUSTRIES
from app.services.analyzer.claude_analyzer import analyze_celebrity
from app.services.blog.content_generator import generate_blog_post
from app.services.blog.naver_blog import post_to_naver_blog


scheduler = AsyncIOScheduler(timezone="Asia/Seoul")


def get_last_monday(ref: date = None) -> date:
    d = ref or date.today()
    return d - timedelta(days=d.weekday())


async def run_weekly_update(week_start: date = None):
    """주간 전체 업데이트 파이프라인"""
    week_start = week_start or get_last_monday()
    logger.info(f"[스케줄러] 주간 업데이트 시작: {week_start}")

    async with AsyncSessionLocal() as db:
        # 1. 셀럽 목록 로드
        result = await db.execute(select(Celebrity))
        celebrities = result.scalars().all()
        celebrity_names = {c.id: c.name for c in celebrities}

        logger.info(f"[스케줄러] 대상 셀럽: {len(celebrities)}명")

        # 2. 각 셀럽별 SNS 데이터 수집 (병렬)
        all_summaries: dict[int, list] = {}

        semaphore = asyncio.Semaphore(5)  # 동시 5개 제한

        async def collect_one(celeb: Celebrity):
            async with semaphore:
                summaries = []
                try:
                    # 네이버 블로그/카페
                    naver_posts = await scrape_celebrity_mentions(celeb.name, week_start)
                    summaries.extend(aggregate_naver_mentions(celeb.id, celeb.name, week_start, naver_posts))

                    # 인스타그램
                    ig_posts = await scrape_celebrity_instagram(
                        celeb.instagram_handle or "", celeb.name, week_start
                    )
                    if not ig_posts and celeb.name:
                        ig_posts = await scrape_celebrity_hashtag(celeb.name, week_start)
                    ig_summary = aggregate_instagram_mentions(celeb.id, celeb.name, week_start, ig_posts)
                    if ig_summary.mention_count > 0:
                        summaries.append(ig_summary)

                    # 유튜브
                    yt_videos = await scrape_celebrity_youtube(celeb.name, week_start)
                    yt_summary = aggregate_youtube_mentions(celeb.id, celeb.name, week_start, yt_videos)
                    if yt_summary.mention_count > 0:
                        summaries.append(yt_summary)

                    all_summaries[celeb.id] = summaries

                    # DB에 플랫폼별 언급 저장
                    for s in summaries:
                        stmt = insert(WeeklyMention).values(
                            celebrity_id=s.celebrity_id,
                            week_start=s.week_start,
                            platform=s.platform,
                            mention_count=s.mention_count,
                            total_likes=s.total_likes,
                            total_comments=s.total_comments,
                            sentiment_score=s.sentiment_score,
                        ).on_conflict_do_update(
                            constraint="uq_mention",
                            set_=dict(
                                mention_count=s.mention_count,
                                total_likes=s.total_likes,
                                total_comments=s.total_comments,
                                sentiment_score=s.sentiment_score,
                            )
                        )
                        await db.execute(stmt)

                except Exception as e:
                    logger.error(f"[스케줄러] {celeb.name} 수집 오류: {e}")
                    all_summaries[celeb.id] = []

        tasks = [collect_one(c) for c in celebrities]
        await asyncio.gather(*tasks)
        await db.commit()

        # 3. 마케팅 점수 계산
        scores = calculate_marketing_scores(all_summaries, week_start, celebrity_names)

        # 4. 랭킹 저장 (TOP 10)
        for rank, score in enumerate(scores[:10], start=1):
            stmt = insert(WeeklyRanking).values(
                celebrity_id=score.celebrity_id,
                week_start=week_start,
                rank=rank,
                marketing_score=score.marketing_score,
                mention_total=score.mention_total,
                engagement_rate=score.engagement_rate,
                sentiment_avg=score.sentiment_avg,
            ).on_conflict_do_update(
                constraint="uq_ranking",
                set_=dict(
                    rank=rank,
                    marketing_score=score.marketing_score,
                    mention_total=score.mention_total,
                    engagement_rate=score.engagement_rate,
                    sentiment_avg=score.sentiment_avg,
                )
            )
            await db.execute(stmt)

        await db.commit()
        logger.info(f"[스케줄러] TOP 10 랭킹 저장 완료")

        # 5. Claude API 분석 (TOP 20)
        analysis_targets = scores[:20]
        analyze_semaphore = asyncio.Semaphore(3)

        async def analyze_one(score):
            async with analyze_semaphore:
                summaries = all_summaries.get(score.celebrity_id, [])
                analysis = await analyze_celebrity(
                    score.celebrity_id, score.celebrity_name, week_start, summaries
                )
                if not analysis:
                    return

                # 프로파일 저장
                stmt = insert(CelebrityProfile).values(
                    celebrity_id=analysis.celebrity_id,
                    week_start=analysis.week_start,
                    image_tags=analysis.image_tags,
                    personality_summary=analysis.personality_summary,
                    brand_fit_description=analysis.brand_fit_description,
                ).on_conflict_do_update(
                    constraint="uq_profile",
                    set_=dict(
                        image_tags=analysis.image_tags,
                        personality_summary=analysis.personality_summary,
                        brand_fit_description=analysis.brand_fit_description,
                    )
                )
                await db.execute(stmt)

                # 산업군 랭킹 저장
                for industry, fit_score in analysis.industry_fit.items():
                    stmt = insert(IndustryRanking).values(
                        celebrity_id=analysis.celebrity_id,
                        industry=industry,
                        week_start=analysis.week_start,
                        fit_score=float(fit_score),
                        rank=0,  # 아래서 일괄 업데이트
                    ).on_conflict_do_update(
                        constraint="uq_industry_rank",
                        set_=dict(fit_score=float(fit_score))
                    )
                    await db.execute(stmt)

        analyze_tasks = [analyze_one(s) for s in analysis_targets]
        await asyncio.gather(*analyze_tasks)
        await db.commit()

        # 6. 산업군 내 순위 업데이트
        for industry in INDUSTRIES:
            result = await db.execute(
                select(IndustryRanking)
                .where(IndustryRanking.week_start == week_start)
                .where(IndustryRanking.industry == industry)
                .order_by(IndustryRanking.fit_score.desc())
            )
            industry_rows = result.scalars().all()
            for rank, row in enumerate(industry_rows, start=1):
                row.rank = rank
        await db.commit()

        logger.info(f"[스케줄러] 분석 완료: {week_start}")

        # 7. 네이버 블로그 자동 포스팅
        await _post_weekly_blog(scores, week_start)

        logger.info(f"[스케줄러] 주간 업데이트 완료: {week_start}")


async def _post_weekly_blog(scores: list, week_start: date):
    """분석 결과를 네이버 블로그에 자동 포스팅"""
    try:
        # 랭킹 데이터 직렬화
        rankings = [
            {
                "rank": i + 1,
                "name": s.celebrity_name,
                "score": s.marketing_score,
                "mention_total": s.mention_total,
                "sentiment": s.sentiment_avg,
            }
            for i, s in enumerate(scores[:10])
        ]

        # 프로파일 (Claude 분석 결과)
        profiles = {}
        async with AsyncSessionLocal() as db:
            from app.models.celebrity import CelebrityProfile
            result = await db.execute(
                select(CelebrityProfile)
                .where(CelebrityProfile.week_start == week_start)
            )
            for profile in result.scalars().all():
                celeb_name = next(
                    (s.celebrity_name for s in scores if s.celebrity_id == profile.celebrity_id), ""
                )
                if celeb_name:
                    profiles[celeb_name] = {
                        "image_tags": profile.image_tags or [],
                        "summary": profile.personality_summary or "",
                        "brand_fit": profile.brand_fit_description or "",
                    }

            # 산업군 랭킹
            from app.models.celebrity import IndustryRanking as IRModel
            ir_result = await db.execute(
                select(IRModel).where(IRModel.week_start == week_start)
            )
            industry_raw: dict[str, list] = {}
            for ir in ir_result.scalars().all():
                celeb_name = next(
                    (s.celebrity_name for s in scores if s.celebrity_id == ir.celebrity_id), ""
                )
                if celeb_name:
                    industry_raw.setdefault(ir.industry, []).append(
                        (celeb_name, ir.fit_score or 0, ir.rank or 0)
                    )

        blog_post = await generate_blog_post(rankings, profiles, industry_raw, week_start)
        if not blog_post:
            return

        result = await post_to_naver_blog(blog_post)
        if result["success"]:
            logger.info(f"[블로그] 포스팅 성공: {result['post_url']}")
        else:
            logger.warning(f"[블로그] 포스팅 실패: {result['error']}")

    except Exception as e:
        logger.error(f"[블로그] 포스팅 오류: {e}")


def setup_scheduler():
    """APScheduler 등록"""
    scheduler.add_job(
        run_weekly_update,
        trigger=CronTrigger(day_of_week="mon", hour=2, minute=0, timezone="Asia/Seoul"),
        id="weekly_update",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.start()
    logger.info("[스케줄러] 주간 배치 등록 완료 (매주 월요일 02:00 KST)")
