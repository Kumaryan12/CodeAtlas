from sqlalchemy import Engine, create_engine, text

from codeatlas.core.config import Settings


def create_database_engine(settings: Settings) -> Engine:
    # Connections are lazy; liveness remains available when PostgreSQL is down.
    return create_engine(
        settings.database_url.get_secret_value(),
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=0,
        pool_timeout=3,
        connect_args={"connect_timeout": 3, "options": "-c statement_timeout=3000"},
    )


def check_database(engine: Engine) -> None:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
