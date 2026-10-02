"""Alembic environment. Imports every model module so autogenerate sees all tables."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from sfincs_ui.db.base import Base
from sfincs_ui.models import audit_log  # noqa: F401
from sfincs_ui.models import project  # noqa: F401
from sfincs_ui.models import setting  # noqa: F401
from sfincs_ui.models import user  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata

if not config.get_main_option("sqlalchemy.url"):
    from sfincs_ui.config import get_config

    config.set_main_option("sqlalchemy.url", get_config().database_url_resolved)


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
