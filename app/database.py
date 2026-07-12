from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

# Pool sized to concurrency. The default (pool_size=5, max_overflow=10 → 15 max)
# saturated at 2–3 concurrent readers, because get_db holds a connection for the
# whole request — including the multi-second Modal/OpenAI calls — so requests then
# blocked up to pool_timeout (30s) and 500'd with a QueuePool timeout that looked
# like GPU slowness. See notes/multi_user_performance.md §3. pool_pre_ping discards
# connections Postgres has dropped (idle timeout, restart) before handing them out.
engine = create_engine(
    settings.database_url,
    echo=False,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()