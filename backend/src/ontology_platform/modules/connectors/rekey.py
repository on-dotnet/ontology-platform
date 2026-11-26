"""Re-encrypt every stored credential with the current OP_SECRET_KEY (spec 003, 5.4, step 2).

Run in the api container while OP_SECRET_KEY_PREVIOUS still holds the old key:
    python -m ontology_platform.modules.connectors.rekey
It prints only counts.
"""

import asyncio
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.db import create_database_engine, create_session_factory
from ontology_platform.modules.connectors.errors import CredentialUnreadableError
from ontology_platform.modules.connectors.models import DataSource
from ontology_platform.modules.connectors.secrets import current_key_id, open_password, seal
from ontology_platform.settings import Settings


@dataclass(frozen=True, slots=True)
class RekeyResult:
    rekeyed: int
    # Credentials no configured key opens: left as they are, the data source asks for the
    # password again.
    unreadable: int


async def rekey(db: AsyncSession, settings: Settings) -> RekeyResult:
    """Re-encrypt in the caller's transaction; the caller commits."""
    key_id = current_key_id(settings)
    rows = await db.scalars(
        select(DataSource)
        .where(DataSource.secret.is_not(None), DataSource.secret_key_id.is_distinct_from(key_id))
        .order_by(DataSource.id)
        .with_for_update()
    )
    rekeyed = unreadable = 0
    for row in rows:
        if row.secret is None:
            continue
        try:
            password = open_password(settings, row.id, row.secret, row.secret_key_id)
        except CredentialUnreadableError:
            unreadable += 1
            continue
        sealed = seal(settings, row.id, password)
        row.secret, row.secret_key_id = sealed.secret, sealed.key_id
        rekeyed += 1
    await db.flush()
    return RekeyResult(rekeyed=rekeyed, unreadable=unreadable)


async def _main() -> None:
    settings = Settings()
    engine = create_database_engine(settings.database_url)
    try:
        async with create_session_factory(engine).begin() as db:
            result = await rekey(db, settings)
    finally:
        await engine.dispose()
    print(f"re-encrypted: {result.rekeyed}, unreadable: {result.unreadable}")


if __name__ == "__main__":
    asyncio.run(_main())
