"""Health checks."""

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession


async def database_ready(db: AsyncSession) -> bool:
    try:
        await db.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError):
        return False
    return True
