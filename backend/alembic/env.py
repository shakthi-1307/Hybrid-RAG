from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.db.models import Base
from app.db.url import build_database_url, describe_database_target

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=build_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Printed rather than logged: alembic.ini pins the root logger to WARNING,
    # and this line is what makes a misconfigured URL obvious instead of
    # arriving as an opaque resolver error further down.
    print(f"alembic: connecting to {describe_database_target()}")

    # The URL goes straight to create_engine rather than through
    # config.set_main_option, because Alembic stores that value in a
    # configparser which applies %-interpolation and chokes on '%' in a
    # password.
    connectable = create_engine(build_database_url(), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
