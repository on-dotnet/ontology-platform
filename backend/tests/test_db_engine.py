import pytest
from sqlalchemy import text
from sqlalchemy.exc import DataError

from ontology_platform.db import create_database_engine


async def test_database_errors_hide_bound_parameters(database_url: str) -> None:
    marker = "op-hidden-param-marker"
    engine = create_database_engine(database_url)
    try:
        async with engine.connect() as conn:
            with pytest.raises(DataError) as caught:
                await conn.execute(text("SELECT 1 / 0, CAST(:v AS text)"), {"v": marker})
        assert marker not in str(caught.value)
    finally:
        await engine.dispose()
