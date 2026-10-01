from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from typing import Generator
from encaminhamento.config import DATABASE_URL, DATABASE_ECHO
from encaminhamento.database.models import Base

engine = create_engine(DATABASE_URL, echo=DATABASE_ECHO, future=True)

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