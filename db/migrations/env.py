"""Alembic environment: URL from our settings, metadata from db.models (for autogenerate)."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from config.settings import get_settings
from db.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
URL = config.get_main_option("sqlalchemy.url") or get_settings().database_url


def include_object(obj, name, type_, reflected, compare_to):
    """LangGraph's PostgresSaver owns the checkpoint* tables; Alembic must not try to drop them."""
    return not (type_ in ("table", "index") and reflected and compare_to is None
                and (name or "").startswith("checkpoint"))


def run_migrations_offline() -> None:
    context.configure(url=URL, target_metadata=target_metadata, literal_binds=True,
                      dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with create_engine(URL).connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True,
                          include_object=include_object)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
