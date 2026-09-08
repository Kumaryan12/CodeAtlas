from alembic import context
from sqlalchemy import create_engine

from codeatlas.core.config import Settings
from codeatlas.models.repository import Base

# A supplied connection lets tests run the exact migrations without a local database.
connection = context.config.attributes.get("connection")


def migrate(connection):
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    context.configure(
        url=Settings().database_url.get_secret_value(),
        target_metadata=Base.metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
elif connection is not None:
    migrate(connection)
else:
    engine = create_engine(Settings().database_url.get_secret_value())
    try:
        with engine.connect() as connection:
            migrate(connection)
    finally:
        engine.dispose()
