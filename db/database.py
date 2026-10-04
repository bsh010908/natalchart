import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import URL, create_engine
from sqlalchemy.orm import DeclarativeBase, Session


class Base(DeclarativeBase):
    pass


@lru_cache
def get_engine():
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    required = ("MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE")
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise RuntimeError("Missing database settings: " + ", ".join(missing))
    url = URL.create(
        "mysql+pymysql",
        username=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASSWORD"],
        # Local API connects to the port published by Docker Compose.
        # For a containerized API use MYSQL_HOST=mysql and MYSQL_PORT=3306.
        host=os.getenv("MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("MYSQL_PORT", "3309")),
        database=os.environ["MYSQL_DATABASE"],
        query={"charset": "utf8mb4"},
    )
    return create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 10})


def get_db():
    """FastAPI dependency; callers explicitly commit their transactions."""
    with Session(get_engine()) as session:
        yield session


def init_db():
    """Create missing tables in an existing MySQL database."""
    from db import models

    models.Base.metadata.create_all(get_engine())


if __name__ == "__main__":
    init_db()
    print("MySQL tables created.")
