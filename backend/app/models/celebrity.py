from sqlalchemy import Column, Integer, String, Text, DateTime, Float, BigInteger, Date, UniqueConstraint, JSON
from sqlalchemy.sql import func
from app.db.database import Base


class Celebrity(Base):
    __tablename__ = "celebrities"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    name_en = Column(String(100))
    category = Column(String(50))          # 가수/배우/스포츠/인플루언서
    instagram_handle = Column(String(100))
    youtube_channel_id = Column(String(100))
    profile_image_url = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class WeeklyMention(Base):
    __tablename__ = "weekly_mentions"

    id = Column(Integer, primary_key=True)
    celebrity_id = Column(Integer, nullable=False)
    week_start = Column(Date, nullable=False)
    platform = Column(String(50))          # naver_blog/naver_cafe/instagram/youtube
    mention_count = Column(Integer, default=0)
    total_likes = Column(BigInteger, default=0)
    total_comments = Column(Integer, default=0)
    sentiment_score = Column(Float)        # -1.0 ~ 1.0

    __table_args__ = (
        UniqueConstraint("celebrity_id", "week_start", "platform", name="uq_mention"),
    )


class WeeklyRanking(Base):
    __tablename__ = "weekly_rankings"

    id = Column(Integer, primary_key=True)
    celebrity_id = Column(Integer, nullable=False)
    week_start = Column(Date, nullable=False)
    rank = Column(Integer, nullable=False)
    marketing_score = Column(Float)
    mention_total = Column(Integer)
    engagement_rate = Column(Float)
    sentiment_avg = Column(Float)

    __table_args__ = (
        UniqueConstraint("celebrity_id", "week_start", name="uq_ranking"),
    )


class CelebrityProfile(Base):
    __tablename__ = "celebrity_profiles"

    id = Column(Integer, primary_key=True)
    celebrity_id = Column(Integer, nullable=False)
    week_start = Column(Date, nullable=False)
    image_tags = Column(JSON)              # ["신뢰감", "트렌디", ...]
    personality_summary = Column(Text)
    brand_fit_description = Column(Text)

    __table_args__ = (
        UniqueConstraint("celebrity_id", "week_start", name="uq_profile"),
    )


class IndustryRanking(Base):
    __tablename__ = "industry_rankings"

    id = Column(Integer, primary_key=True)
    celebrity_id = Column(Integer, nullable=False)
    industry = Column(String(50))
    week_start = Column(Date, nullable=False)
    fit_score = Column(Float)
    rank = Column(Integer)

    __table_args__ = (
        UniqueConstraint("celebrity_id", "industry", "week_start", name="uq_industry_rank"),
    )
