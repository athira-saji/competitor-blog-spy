import asyncio
import json
from datetime import datetime, timezone

from sqlalchemy import create_engine, select, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import Session

from app.config import DATABASE_URL
from app.models import Competitor, Article, CheckLog, Base


SQLITE_URL = "sqlite:///./blogspy.db"


def normalize_json(value):
    """
    SQLite currently contains some JSON columns as JSON strings.
    Convert them back into Python lists/dicts before inserting into
    PostgreSQL JSON columns.
    """
    if value is None:
        return None

    if isinstance(value, (dict, list)):
        return value

    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value

    return value


def normalize_datetime(value):
    """
    SQLite does not preserve timezone information in these columns.
    The monitoring application recorded these timestamps in UTC,
    so restore UTC timezone information before inserting into
    PostgreSQL TIMESTAMP WITH TIME ZONE.
    """
    if value is None:
        return None

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def row_to_dict(row, model):
    data = {}

    for column in model.__table__.columns:
        value = getattr(row, column.name)

        if column.name in {
            "config_json",
            "inline_images",
            "categories",
            "tags",
            "relevant_links",
            "metadata_json",
            "methods_used",
        }:
            value = normalize_json(value)

        elif column.name in {
            "created_at",
            "last_checked_at",
            "last_successful_detection",
            "published_at",
            "discovered_at",
            "started_at",
            "finished_at",
        }:
            value = normalize_datetime(value)

        data[column.name] = value

    return data


async def main():

    print("=" * 60)
    print("SQLite → Supabase migration")
    print("=" * 60)

    print("\nChecking SQLite database...")

    # ---------------------------------------------------------
    # SOURCE DATABASE
    # ---------------------------------------------------------

    source_engine = create_engine(
        SQLITE_URL,
        echo=False,
    )

    source_session = Session(source_engine)

    competitors = source_session.scalars(
        select(Competitor).order_by(Competitor.id)
    ).all()

    articles = source_session.scalars(
        select(Article).order_by(Article.id)
    ).all()

    checks = source_session.scalars(
        select(CheckLog).order_by(CheckLog.id)
    ).all()

    print(f"SQLite competitors : {len(competitors)}")
    print(f"SQLite articles    : {len(articles)}")
    print(f"SQLite checks      : {len(checks)}")

    # ---------------------------------------------------------
    # DESTINATION DATABASE
    # ---------------------------------------------------------

    print("\nConnecting to Supabase...")

    destination_engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
    )

    DestinationSession = async_sessionmaker(
        destination_engine,
        expire_on_commit=False,
    )

    async with destination_engine.begin() as conn:

        print("Creating Supabase tables if needed...")

        await conn.run_sync(Base.metadata.create_all)

    # ---------------------------------------------------------
    # SAFETY CHECK
    # ---------------------------------------------------------

    async with DestinationSession() as session:

        existing_competitors = await session.scalar(
            select(Competitor.id).limit(1)
        )

        existing_articles = await session.scalar(
            select(Article.id).limit(1)
        )

        existing_checks = await session.scalar(
            select(CheckLog.id).limit(1)
        )

        if (
            existing_competitors is not None
            or existing_articles is not None
            or existing_checks is not None
        ):
            print("\nSTOPPED FOR SAFETY.")
            print("The Supabase database already contains data.")
            print("No migration was performed.")
            print("\nThis script will NOT overwrite existing data.")
            await destination_engine.dispose()
            source_session.close()
            return

    # ---------------------------------------------------------
    # INSERT DATA
    # ---------------------------------------------------------

    print("\nMigrating competitors...")

    async with DestinationSession() as session:

        for row in competitors:
            data = row_to_dict(row, Competitor)
            session.add(Competitor(**data))

        await session.commit()

    print(f"✓ {len(competitors)} competitors migrated")

    # ---------------------------------------------------------

    print("\nMigrating articles...")

    async with DestinationSession() as session:

        for row in articles:
            data = row_to_dict(row, Article)
            session.add(Article(**data))

        await session.commit()

    print(f"✓ {len(articles)} articles migrated")

    # ---------------------------------------------------------

    print("\nMigrating check logs...")

    async with DestinationSession() as session:

        for row in checks:
            data = row_to_dict(row, CheckLog)
            session.add(CheckLog(**data))

        await session.commit()

    print(f"✓ {len(checks)} check logs migrated")

    # ---------------------------------------------------------
    # RESET POSTGRES SEQUENCES
    # ---------------------------------------------------------

    print("\nResetting PostgreSQL ID sequences...")

    async with destination_engine.begin() as conn:

        await conn.execute(
            text("""
                SELECT setval(
                    pg_get_serial_sequence('competitors', 'id'),
                    COALESCE((SELECT MAX(id) FROM competitors), 1),
                    true
                )
            """)
        )

        await conn.execute(
            text("""
                SELECT setval(
                    pg_get_serial_sequence('articles', 'id'),
                    COALESCE((SELECT MAX(id) FROM articles), 1),
                    true
                )
            """)
        )

        await conn.execute(
            text("""
                SELECT setval(
                    pg_get_serial_sequence('check_logs', 'id'),
                    COALESCE((SELECT MAX(id) FROM check_logs), 1),
                    true
                )
            """)
        )

    # ---------------------------------------------------------
    # VERIFY
    # ---------------------------------------------------------

    print("\nVerifying Supabase data...")

    async with DestinationSession() as session:

        competitor_count = await session.scalar(
            text("SELECT COUNT(*) FROM competitors")
        )

        article_count = await session.scalar(
            text("SELECT COUNT(*) FROM articles")
        )

        check_count = await session.scalar(
            text("SELECT COUNT(*) FROM check_logs")
        )

        detection = await session.execute(
            text("""
                SELECT
                    id,
                    title,
                    detection_delay_seconds,
                    detection_method,
                    check_id
                FROM articles
                WHERE is_detection = true
                ORDER BY id
            """)
        )

        detection_rows = detection.fetchall()

    print("\nSupabase counts:")
    print(f"Competitors : {competitor_count}")
    print(f"Articles    : {article_count}")
    print(f"Checks      : {check_count}")

    print("\nDetection records:")

    for row in detection_rows:
        print(
            f"  ID={row.id} | "
            f"delay={row.detection_delay_seconds:.6f}s | "
            f"method={row.detection_method} | "
            f"check={row.check_id}"
        )

    # ---------------------------------------------------------

    if (
        competitor_count == len(competitors)
        and article_count == len(articles)
        and check_count == len(checks)
    ):
        print("\n" + "=" * 60)
        print("MIGRATION SUCCESSFUL")
        print("=" * 60)

    else:
        print("\nWARNING: Row counts do not match.")

    await destination_engine.dispose()
    source_session.close()


if __name__ == "__main__":
    asyncio.run(main())