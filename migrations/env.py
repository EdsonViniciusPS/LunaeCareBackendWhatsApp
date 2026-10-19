import asyncio
from logging.config import fileConfig
import os
import sys

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Adiciona o diretório do projeto ao sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.core.config import settings
from app.core.database import Base
import app.models  # Garante que todos os modelos são registrados

# Configuração do Alembic
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Configura a URL dinamicamente a partir das configurações do projeto
database_url = settings.DATABASE_SYNC_URL or settings.DATABASE_URL
# Se for asyncpg, converte para sincronous se necessário ou usa driver async
config.set_main_option("sqlalchemy.url", database_url)


def run_migrations_offline() -> None:
    """Executa migrações no modo 'offline'."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Executa migrações no modo assíncrono."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = settings.DATABASE_URL

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Executa migrações no modo 'online'."""
    if settings.DATABASE_URL.startswith("postgresql+asyncpg") or settings.DATABASE_URL.startswith("sqlite+aiosqlite"):
        asyncio.run(run_async_migrations())
    else:
        from sqlalchemy import engine_from_config
        connectable = engine_from_config(
            config.get_section(config.config_ini_section, {}),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )
        with connectable.connect() as connection:
            do_run_migrations(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
