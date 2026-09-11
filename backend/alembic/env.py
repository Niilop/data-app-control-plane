"""Alembic configuration and migration environment."""

import os
import sys
from importlib.util import module_from_spec, spec_from_file_location
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Add the backend directory to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.config import get_settings
from models import database as runtime_models

# Retain historical AI table metadata without importing it into the application.
# This also avoids a name collision with the installed Alembic package.
legacy_spec = spec_from_file_location(
    "platform_legacy_models",
    os.path.join(os.path.dirname(__file__), "legacy_models.py"),
)
assert legacy_spec is not None and legacy_spec.loader is not None
legacy_spec.loader.exec_module(module_from_spec(legacy_spec))

# this is the Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set the SQLAlchemy URL from environment
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

# Model's MetaData object for 'autogenerate' support
target_metadata = runtime_models.Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
