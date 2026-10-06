from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from typing import Generator
from encaminhamento.config import DATABASE_URL, DATABASE_ECHO
from encaminhamento.database.models import Base

engine = create_engine(
    DATABASE_URL,
    echo=DATABASE_ECHO,
    future=True,
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
)

# expire_on_commit=False mantem os atributos carregados apos o commit.
# Sem isso, qualquer objeto usado fora do with get_session() dispara
# DetachedInstanceError (o commit expira todos os atributos).
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    future=True,
)


def init_db() -> None:
    # Enable WAL mode for SQLite: see committed writes across connections
    # (critical when the DB is modified by an external script and the
    # Streamlit server needs to see the changes immediately).
    if DATABASE_URL.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_conn, conn_record):
            dbapi_conn.execute("PRAGMA journal_mode=WAL")
            dbapi_conn.execute("PRAGMA busy_timeout=5000")
    Base.metadata.create_all(bind=engine)


@contextmanager
def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()