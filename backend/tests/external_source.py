"""The steel sample as an "external" data source for the M3 tests (spec 003, section 11).

Batch 3 fills this in: a throwaway database in the same PostgreSQL server per test process,
loaded from fixtures/connectors/steel, with a read-only account and an account that may write
(for proving that the connector still cannot). Role names get a random suffix, since roles are
shared by the whole server and several workspaces run tests at the same time.
"""

from dataclasses import dataclass

import pytest


@dataclass(frozen=True, slots=True)
class ExternalSource:
    host: str
    port: int
    database: str
    reader: str
    reader_password: str
    # An account with write privileges: the read-only guarantees must hold even for it.
    writer: str
    writer_password: str


@pytest.fixture(scope="session")
def external_source() -> ExternalSource:
    raise NotImplementedError("The external data source fixture arrives with M3 batch 3.")
