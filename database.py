"""
Database configuration and session management.
Uses SQLite with aiosqlite for async operations.
"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
import os

# Use the same directory as this file for the database
DATABASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite+aiosqlite:///{os.path.join(DATABASE_DIR, 'medical_monitor.db')}"
)

# Create async engine
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True
)

# Async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)

# Base class for models
Base = declarative_base()


async def get_db():
    """Dependency: yields a database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Create all tables on startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
