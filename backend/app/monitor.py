import asyncio
import hashlib
import logging
import re
import uuid
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import feedparser
import httpx
import trafilatura
from bs4 import BeautifulSoup
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from .config import MAX_CONCURRENT_CHECKS, REQUEST_TIMEOUT_SECONDS
from .models import Competitor, Article, CheckLog

log = logging.getLogger(__name__)

MAX_CANDIDATES_PER_CYCLE = 50


def now():
    return datetime.now(timezone.utc)


def clean_url(url: str) -> str:
    return url.strip()


def normalize_date(dt):
    if not dt:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_feed(content: bytes, feed_url: str):
    parsed = feedparser.parse(content)
    items = []

    for e in parsed.entries:
        link = e.get("link")
        if not link:
            continue

        pub = e.get("published_parsed") or e.get("updated_parsed")
        published = None

        if pub:
            try:
                import calendar

                published = datetime.fromtimestamp(
                    calendar.timegm(pub),
                    tz=timezone.utc
                )
            except Exception:
                pass

        items.append({
            "url": urljoin(feed_url, link),
            "title": e.get("title", "").strip(),
            "published_at": published,
            "method": "rss_atom",
        })

    return items


async def fetch(client, url):
    r = await client.get(url, follow_redirects=True)
    r.raise_for_status()
    return r.content, str(r.url), r.headers.get("content-type", "")


async def discover_sources(client, competitor: Competitor):
    base = competitor.website_url.rstrip("/") + "/"

    candidates = {
        "feeds": set(),
        "sitemaps": set(),
        "blog": competitor.blog_url,
    }

    if competitor.feed_url:
        candidates["feeds"].add(competitor.feed_url)

    if competitor.sitemap_url:
        candidates["sitemaps"].add(competitor.sitemap_url)

    try:
        html, final_url, _ = await fetch(
            client,
            competitor.blog_url or competitor.website_url
        )

        soup = BeautifulSoup(html, "html.parser")

        for link in soup.find_all("link"):
            rel = " ".join(link.get("rel", []))
            typ = (link.get("type") or "").lower()
            href = link.get("href")

            if (
                href
                and "alternate" in rel
                and (
                    "rss" in typ
                    or "atom" in typ
                    or "feed" in typ
                )
            ):
                candidates["feeds"].add(
                    urljoin(final_url, href)
                )

        for a in soup.find_all("a", href=True):
            href = urljoin(final_url, a["href"])

            if re.search(
                r"(blog|article|news|insight|stories|resources)",
                href,
                re.I
            ):
                if candidates["blog"] is None:
                    candidates["blog"] = href
                break

    except Exception as e:
        log.warning(
            "Page discovery failed for %s: %s",
            competitor.name,
            e
        )

    robots = urljoin(base, "robots.txt")

    try:
        body, _, _ = await fetch(client, robots)
        text = body.decode("utf-8", errors="ignore")

        for line in text.splitlines():
            if line.lower().startswith("sitemap:"):
                candidates["sitemaps"].add(
                    line.split(":", 1)[1].strip()
                )

    except Exception:
        pass

    for path in ("sitemap.xml", "sitemap_index.xml"):
        candidates["sitemaps"].add(
            urljoin(base, path)
        )

    return candidates


async def sitemap_urls(client, url, max_urls=500):
    body, final, _ = await fetch(client, url)
    soup = BeautifulSoup(body, "xml")

    locs = [
        x.get_text(strip=True)
        for x in soup.find_all("loc")
    ]

    # Sitemap index
    if (
        soup.find("sitemapindex")
        or re.search(r"sitemap(_index)?", final, re.I)
    ):
        all_urls = []

        for child in locs[:10]:
            try:
                b, _, _ = await fetch(client, child)
                s = BeautifulSoup(b, "xml")

                for url_tag in s.find_all("url"):
                    loc = url_tag.find("loc")

                    if not loc:
                        continue

                    last_modified = None
                    lastmod = url_tag.find("lastmod")

                    if lastmod:
                        try:
                            from dateutil import parser

                            last_modified = parser.parse(
                                lastmod.get_text(strip=True)
                            ).astimezone(timezone.utc)

                        except Exception:
                            pass

                    all_urls.append({
                        "url": loc.get_text(strip=True),
                        "last_modified": last_modified,
                    })

            except Exception:
                continue

        return all_urls[:max_urls]

    # Normal sitemap
    results = []

    for url_tag in soup.find_all("url"):
        loc = url_tag.find("loc")

        if not loc:
            continue

        last_modified = None
        lastmod = url_tag.find("lastmod")

        if lastmod:
            try:
                from dateutil import parser

                last_modified = parser.parse(
                    lastmod.get_text(strip=True)
                ).astimezone(timezone.utc)

            except Exception:
                pass

        results.append({
            "url": loc.get_text(strip=True),
            "last_modified": last_modified,
        })

    return results[:max_urls]


def likely_article(url, competitor):
    path = urlparse(url).path.lower()

    if any(
        x in path
        for x in [
            "/blog/",
            "/article/",
            "/articles/",
            "/news/",
            "/insights/",
            "/resources/",
            "/posts/",
        ]
    ):
        return True

    if competitor.blog_url:
        bp = urlparse(
            competitor.blog_url
        ).path.rstrip("/")

        return bp and path.startswith(bp + "/")

    return False


async def direct_page_items(client, competitor):
    url = competitor.blog_url or competitor.website_url

    body, final, _ = await fetch(client, url)
    soup = BeautifulSoup(body, "html.parser")

    items = []

    for a in soup.find_all("a", href=True):
        href = urljoin(final, a["href"])
        title = a.get_text(" ", strip=True)

        if len(title) < 8 or not likely_article(
            href,
            competitor
        ):
            continue

        items.append({
            "url": href,
            "title": title,
            "published_at": None,
            "method": "direct_page",
        })

    if soup.find("article") and soup.title:
        items.append({
            "url": final,
            "title": soup.title.get_text(
                " ",
                strip=True
            ),
            "published_at": extract_date(soup),
            "method": "direct_page",
        })

    seen, out = set(), []

    for x in items:
        if x["url"] not in seen:
            seen.add(x["url"])
            out.append(x)

    return out[:200]


def extract_date(soup):
    for selector in [
        ("meta", {"property": "article:published_time"}),
        ("meta", {"name": "article:published_time"}),
        ("meta", {"property": "og:article:published_time"}),
        ("time", {}),
    ]:
        tag = soup.find(*selector)

        if tag:
            value = (
                tag.get("content")
                or tag.get("datetime")
                or tag.get_text(strip=True)
            )

            if value:
                try:
                    from dateutil import parser

                    return parser.parse(
                        value
                    ).astimezone(timezone.utc)

                except Exception:
                    pass

    tag = soup.find(
        attrs={"itemprop": "datePublished"}
    )

    if tag:
        value = (
            tag.get("content")
            or tag.get("datetime")
            or tag.get_text(strip=True)
        )

        try:
            from dateutil import parser

            return parser.parse(
                value
            ).astimezone(timezone.utc)

        except Exception:
            pass

    return None


async def extract_article(client, item):
    url = item["url"]

    body_bytes, final, content_type = await fetch(
        client,
        url
    )

    html = body_bytes.decode(
        "utf-8",
        errors="ignore"
    )

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    title = (
        item.get("title")
        or (
            soup.title.get_text(
                " ",
                strip=True
            )
            if soup.title
            else url
        )
    )

    meta = soup.find(
        "meta",
        attrs={"name": "description"}
    )

    canonical = soup.find(
        "link",
        rel="canonical"
    )

    author = soup.find(
        "meta",
        attrs={"name": "author"}
    )

    pub = (
        item.get("published_at")
        or extract_date(soup)
    )

    main_html = trafilatura.extract(
        html,
        output_format="html",
        include_links=True,
        include_images=True
    )

    text_body = (
        trafilatura.extract(
            html,
            include_links=True
        )
        or ""
    )

    if not main_html:
        article = (
            soup.find("article")
            or soup.find("main")
            or soup.body
        )

        main_html = (
            str(article)
            if article
            else html
        )

    imgs = []

    root = (
        soup.find("article")
        or soup.find("main")
        or soup.body
    )

    if root:
        for img in root.find_all(
            "img",
            src=True
        )[:50]:
            imgs.append(
                urljoin(
                    final,
                    img["src"]
                )
            )

    links = []

    if root:
        for a in root.find_all(
            "a",
            href=True
        )[:100]:
            href = urljoin(
                final,
                a["href"]
            )

            if href.startswith("http"):
                links.append(href)

    categories = []

    for x in soup.select(
        '[rel="category"], .category, .categories a'
    ):
        t = x.get_text(
            " ",
            strip=True
        )

        if t and t not in categories:
            categories.append(t)

    tags = []

    for x in soup.select(
        '[rel="tag"], .tag, .tags a'
    ):
        t = x.get_text(
            " ",
            strip=True
        )

        if t and t not in tags:
            tags.append(t)

    return {
        "title": title[:1000],
        "body": text_body,
        "featured_image": imgs[0] if imgs else None,
        "inline_images": imgs[1:],
        "author": (
            author.get("content")
            if author
            else None
        ),
        "published_at": pub,
        "meta_description": (
            meta.get("content")
            if meta
            else None
        ),
        "canonical_url": (
            canonical.get("href")
            if canonical
            else final
        ),
        "source_url": final,
        "relevant_links": links[:50],
        "categories": categories[:30],
        "tags": tags[:30],
        "metadata_json": {
            "content_type": content_type,
            "html_length": len(html)
        },
    }


async def monitor_competitor(
    session: AsyncSession,
    competitor_id: int
):
    competitor = await session.get(
        Competitor,
        competitor_id
    )

    if not competitor or not competitor.enabled:
        return

    started = now()
    check_id = uuid.uuid4().hex[:12]
    methods = []
    found = 0
    errors = []

    try:
        timeout = httpx.Timeout(
            REQUEST_TIMEOUT_SECONDS
        )

        async with httpx.AsyncClient(
            timeout=timeout,
            headers={
                "User-Agent":
                    "CompetitorBlogSpy/1.0"
            }
        ) as client:

            sources = await discover_sources(
                client,
                competitor
            )

            candidate_items = []

            # Check whether this is the first
            # monitoring cycle for this competitor.
            existing_count = await session.scalar(
                select(func.count(Article.id)).where(
                    Article.competitor_id == competitor.id
                )
            )

            is_baseline = existing_count == 0

            # RSS / Atom
            for feed in sources["feeds"]:
                try:
                    body, _, _ = await fetch(
                        client,
                        feed
                    )

                    candidate_items.extend(
                        parse_feed(
                            body,
                            feed
                        )
                    )

                    methods.append("rss_atom")

                except Exception as e:
                    errors.append(
                        f"feed {feed}: {e}"
                    )

            # Sitemaps
            for sm in sources["sitemaps"]:
                try:
                    sitemap_items = await sitemap_urls(
                        client,
                        sm
                    )

                    for entry in sitemap_items:
                        url = entry["url"]
                        last_modified = entry.get(
                            "last_modified"
                        )

                        if not likely_article(
                            url,
                            competitor
                        ):
                            continue

                        candidate_items.append({
                            "url": url,
                            "title": "",
                            "published_at": last_modified,
                            "method": "sitemap",
                        })

                    methods.append("sitemap")

                except Exception as e:
                    errors.append(
                        f"sitemap {sm}: {e}"
                    )

            # Direct blog/article page
            if sources["blog"]:
                try:
                    candidate_items.extend(
                        await direct_page_items(
                            client,
                            competitor
                        )
                    )

                    methods.append(
                        "direct_page"
                    )

                except Exception as e:
                    errors.append(
                        f"direct page: {e}"
                    )

            # De-duplicate candidate URLs.
            # Prefer RSS/Atom when the same article
            # appears in multiple sources.
            unique = {}

            for item in candidate_items:
                url = item.get("url")

                if not url:
                    continue

                if url not in unique:
                    unique[url] = item
                else:
                    existing = unique[url]

                    if (
                        existing.get("method")
                        != "rss_atom"
                        and item.get("method")
                        == "rss_atom"
                    ):
                        unique[url] = item

            # Only fetch a limited number of candidates
            # per monitoring cycle.
            urls = list(unique.values())[
                :MAX_CANDIDATES_PER_CYCLE
            ]

            for item in urls:

                exists = await session.scalar(
                    select(Article.id).where(
                        Article.competitor_id
                        == competitor.id,
                        Article.source_url
                        == item["url"]
                    )
                )

                if exists:
                    continue

                # Exact time when our monitoring system
                # discovered this previously unseen article.
                discovered = now()

                try:
                    article_data = await extract_article(
                        client,
                        item
                    )

                    pub = normalize_date(
                        article_data.get(
                            "published_at"
                        )
                    )

                    # Detection delay =
                    # time we discovered it - time it was published.
                    delay = (
                        (
                            discovered - pub
                        ).total_seconds()
                        if pub
                        else None
                    )

                    article = Article(
                        competitor_id=competitor.id,
                        title=article_data["title"],
                        body=article_data["body"],
                        featured_image=article_data[
                            "featured_image"
                        ],
                        inline_images=article_data[
                            "inline_images"
                        ],
                        author=article_data["author"],
                        published_at=pub,
                        discovered_at=discovered,
                        detection_delay_seconds=delay,
                        is_detection=not is_baseline,
                        detection_method=item.get(
                            "method",
                            "unknown"
                        ),
                        check_id=check_id,
                        status="new",
                        categories=article_data[
                            "categories"
                        ],
                        tags=article_data["tags"],
                        meta_description=article_data[
                            "meta_description"
                        ],
                        canonical_url=article_data[
                            "canonical_url"
                        ],
                        source_url=article_data[
                            "source_url"
                        ],
                        relevant_links=article_data[
                            "relevant_links"
                        ],
                        metadata_json=article_data[
                            "metadata_json"
                        ],
                    )

                    session.add(article)

                    # Baseline articles are stored but are
                    # not counted as new detections.
                    if not is_baseline:
                        found += 1

                except Exception as e:
                    errors.append(
                        f"article {item.get('url')}: {e}"
                    )

            competitor.last_checked_at = now()

            competitor.status = (
                "online"
                if not errors
                else "degraded"
            )

            competitor.last_error = (
                "\n".join(errors[-5:])
                if errors
                else None
            )

            if found:
                competitor.last_successful_detection = now()

            finished = now()

            session.add(
                CheckLog(
                    competitor_id=competitor.id,
                    check_id=check_id,
                    started_at=started,
                    finished_at=finished,
                    success=True,
                    methods_used=sorted(
                        set(methods)
                    ),
                    articles_found=found,
                    error=(
                        "\n".join(errors[-10:])
                        if errors
                        else None
                    )
                )
            )

            await session.commit()

    except Exception as e:
        competitor.last_checked_at = now()
        competitor.status = "offline"
        competitor.last_error = str(e)

        session.add(
            CheckLog(
                competitor_id=competitor.id,
                check_id=check_id,
                started_at=started,
                finished_at=now(),
                success=False,
                methods_used=methods,
                articles_found=found,
                error=str(e)
            )
        )

        await session.commit()


async def monitor_all(session_factory):
    async with session_factory() as session:
        competitors = (
            await session.scalars(
                select(Competitor).where(
                    Competitor.enabled == True
                )
            )
        ).all()

    sem = asyncio.Semaphore(
        MAX_CONCURRENT_CHECKS
    )

    async def one(cid):
        async with sem:
            async with session_factory() as s:
                await monitor_competitor(
                    s,
                    cid
                )

    await asyncio.gather(
        *(one(c.id) for c in competitors),
        return_exceptions=True
    )


async def monitoring_loop(
    session_factory,
    interval
):
    while True:
        try:
            await monitor_all(
                session_factory
            )
        except Exception:
            log.exception(
                "Monitoring cycle failed"
            )

        await asyncio.sleep(interval)
