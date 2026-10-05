import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
from sqlalchemy import desc, func, select

from .config import CHECK_INTERVAL_SECONDS, ENABLE_MONITORING, FRONTEND_ORIGINS, MAX_CONCURRENT_CHECKS
from .db import SessionLocal, init_db
from .models import Article, CheckLog, Competitor
from .monitor import discover_sources, monitor_all

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)
monitor_task = None


class CompetitorCreate(BaseModel):
    name: str
    website_url: HttpUrl
    blog_url: Optional[HttpUrl] = None
    feed_url: Optional[HttpUrl] = None
    sitemap_url: Optional[HttpUrl] = None


class TogglePayload(BaseModel):
    enabled: bool


def dt(value):
    return value.isoformat() if value else None


def competitor_dict(c: Competitor):
    return {
        "id": c.id,
        "name": c.name,
        "website_url": c.website_url,
        "blog_url": c.blog_url,
        "feed_url": c.feed_url,
        "sitemap_url": c.sitemap_url,
        "enabled": c.enabled,
        "status": c.status,
        "strategy": c.strategy,
        "config_json": c.config_json or {},
        "last_checked_at": dt(c.last_checked_at),
        "last_successful_detection": dt(c.last_successful_detection),
        "last_error": c.last_error,
        "created_at": dt(c.created_at),
    }


def article_dict(a: Article, competitor_name=None):
    return {
        "id": a.id,
        "competitor_id": a.competitor_id,
        "competitor_name": competitor_name,
        "title": a.title,
        "body": a.body,
        "featured_image": a.featured_image,
        "inline_images": a.inline_images or [],
        "author": a.author,
        "published_at": dt(a.published_at),
        "discovered_at": dt(a.discovered_at),
        "detection_delay_seconds": a.detection_delay_seconds,
        "detection_method": a.detection_method,
        "check_id": a.check_id,
        "status": a.status,
        "categories": a.categories or [],
        "tags": a.tags or [],
        "meta_description": a.meta_description,
        "canonical_url": a.canonical_url,
        "source_url": a.source_url,
        "relevant_links": a.relevant_links or [],
        "metadata_json": a.metadata_json or {},
    }


async def analyze_competitor(cid: int):
    async with SessionLocal() as db:
        comp = await db.get(Competitor, cid)
        if not comp:
            return
        try:
            import httpx
            async with httpx.AsyncClient(
                timeout=20,
                follow_redirects=True,
                headers={"User-Agent": "CompetitorBlogSpy/1.0"},
            ) as client:
                sources = await discover_sources(client, comp)
            comp.feed_url = comp.feed_url or next(iter(sources["feeds"]), None)
            comp.sitemap_url = comp.sitemap_url or next(iter(sources["sitemaps"]), None)
            comp.blog_url = comp.blog_url or sources["blog"]
            methods = []
            if sources["feeds"]:
                methods.append("RSS/Atom")
            if sources["sitemaps"]:
                methods.append("Sitemap")
            if sources["blog"]:
                methods.append("Direct page")
            comp.strategy = ", ".join(methods) or "No source discovered"
            comp.config_json = {
                "feeds": sorted(sources["feeds"]),
                "sitemaps": sorted(sources["sitemaps"]),
                "blog": sources["blog"],
            }
            comp.status = "ready" if methods else "degraded"
            comp.last_error = None
            await db.commit()
        except Exception as exc:
            comp.status = "degraded"
            comp.last_error = str(exc)
            await db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global monitor_task
    await init_db()
    if ENABLE_MONITORING:
        from .monitor import monitoring_loop
        monitor_task = asyncio.create_task(
            monitoring_loop(SessionLocal, CHECK_INTERVAL_SECONDS)
        )
    yield
    if monitor_task:
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Competitor Blog Spy API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "monitoring_interval_seconds": CHECK_INTERVAL_SECONDS,
        "max_concurrent_checks": MAX_CONCURRENT_CHECKS,
    }


@app.get("/api/dashboard/stats")
async def dashboard_stats():
    async with SessionLocal() as db:
        competitors = await db.scalar(
            select(func.count(Competitor.id))
        ) or 0

        enabled = await db.scalar(
            select(func.count(Competitor.id)).where(
                Competitor.enabled.is_(True)
            )
        ) or 0

        # Only genuinely newly detected articles count here.
        articles = await db.scalar(
            select(func.count(Article.id)).where(
                Article.is_detection.is_(True)
            )
        ) or 0

        # Detection performance is calculated only from
        # genuinely detected articles, not baseline articles.
        detection_filter = (
            Article.is_detection.is_(True),
            Article.detection_delay_seconds.is_not(None),
        )

        avg = await db.scalar(
            select(func.avg(Article.detection_delay_seconds)).where(
                *detection_filter
            )
        )

        fastest = await db.scalar(
            select(func.min(Article.detection_delay_seconds)).where(
                *detection_filter
            )
        )

        slowest = await db.scalar(
            select(func.max(Article.detection_delay_seconds)).where(
                *detection_filter
            )
        )

        failed = await db.scalar(
            select(func.count(CheckLog.id)).where(
                CheckLog.success.is_(False)
            )
        ) or 0

        # Only show genuinely detected articles in
        # "Latest detected articles".
        recent = (
            await db.scalars(
                select(Article)
                .where(Article.is_detection.is_(True))
                .order_by(desc(Article.discovered_at))
                .limit(8)
            )
        ).all()

        names = {}

        for a in recent:
            if a.competitor_id not in names:
                c = await db.get(
                    Competitor,
                    a.competitor_id
                )
                names[a.competitor_id] = (
                    c.name if c else "Unknown"
                )

    return {
        "competitors": competitors,
        "enabled_competitors": enabled,
        "articles": articles,
        "average_detection_seconds": avg,
        "fastest_detection_seconds": fastest,
        "slowest_detection_seconds": slowest,
        "failed_checks": failed,
        "recent_articles": [
            article_dict(
                a,
                names.get(a.competitor_id)
            )
            for a in recent
        ],
    }

@app.get("/api/competitors")
async def get_competitors():
    async with SessionLocal() as db:
        rows = (await db.scalars(select(Competitor).order_by(Competitor.name))).all()
        return [competitor_dict(c) for c in rows]


@app.post("/api/competitors", status_code=201)
async def create_competitor(payload: CompetitorCreate):
    c = Competitor(
        name=payload.name.strip(),
        website_url=str(payload.website_url),
        blog_url=str(payload.blog_url) if payload.blog_url else None,
        feed_url=str(payload.feed_url) if payload.feed_url else None,
        sitemap_url=str(payload.sitemap_url) if payload.sitemap_url else None,
        enabled=True,
        status="investigating",
    )
    async with SessionLocal() as db:
        db.add(c)
        await db.commit()
        await db.refresh(c)
        cid = c.id
    asyncio.create_task(analyze_competitor(cid))
    return competitor_dict(c)


@app.post("/api/competitors/{cid}/analyze")
async def analyze(cid: int):
    async with SessionLocal() as db:
        if not await db.get(Competitor, cid):
            raise HTTPException(404, "Competitor not found")
    await analyze_competitor(cid)
    async with SessionLocal() as db:
        return competitor_dict(await db.get(Competitor, cid))


@app.patch("/api/competitors/{cid}/toggle")
async def toggle(cid: int, payload: TogglePayload):
    async with SessionLocal() as db:
        c = await db.get(Competitor, cid)
        if not c:
            raise HTTPException(404, "Competitor not found")
        c.enabled = payload.enabled
        c.status = "paused" if not payload.enabled else (c.status if c.status != "paused" else "ready")
        await db.commit()
        await db.refresh(c)
        return competitor_dict(c)


@app.delete("/api/competitors/{cid}")
async def delete_competitor(cid: int):
    async with SessionLocal() as db:
        c = await db.get(Competitor, cid)
        if not c:
            raise HTTPException(404, "Competitor not found")
        await db.delete(c)
        await db.commit()
    return {"ok": True}


@app.post("/api/monitoring/run")
async def run_monitoring():
    asyncio.create_task(monitor_all(SessionLocal))
    return {"started": True, "message": "Monitoring cycle started"}


@app.get("/api/articles")
async def get_articles(limit: int = 100):
    limit = min(max(limit, 1), 500)

    async with SessionLocal() as db:
        rows = (await db.execute(
            select(Article, Competitor.name)
            .join(Competitor, Competitor.id == Article.competitor_id)
            .where(Article.is_detection.is_(True))
            .order_by(desc(Article.discovered_at))
            .limit(limit)
        )).all()

        return [article_dict(a, name) for a, name in rows]

@app.get("/api/articles/{article_id}")
async def get_article(article_id: int):
    async with SessionLocal() as db:
        row = (await db.execute(
            select(Article, Competitor.name)
            .join(Competitor, Competitor.id == Article.competitor_id)
            .where(Article.id == article_id)
        )).first()
        if not row:
            raise HTTPException(404, "Article not found")
        return article_dict(row[0], row[1])


@app.get("/api/checks")
async def get_checks(limit: int = 100):
    limit = min(max(limit, 1), 500)
    async with SessionLocal() as db:
        rows = (await db.execute(
            select(CheckLog, Competitor.name)
            .join(Competitor, Competitor.id == CheckLog.competitor_id)
            .order_by(desc(CheckLog.finished_at))
            .limit(limit)
        )).all()
        return [{
            "id": c.id,
            "competitor_id": c.competitor_id,
            "competitor_name": name,
            "check_id": c.check_id,
            "started_at": dt(c.started_at),
            "finished_at": dt(c.finished_at),
            "success": c.success,
            "methods_used": c.methods_used or [],
            "articles_found": c.articles_found,
            "error": c.error,
        } for c, name in rows]
