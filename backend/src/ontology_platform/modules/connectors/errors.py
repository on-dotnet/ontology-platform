"""What `connectors.service.select` and `sample_values` raise (spec 003, sections 5.3 and 7).

Callers map these to their own error codes; the query module decides, for example, whether an
invalid value is `query.invalid_filter` or `query.object_not_found`. None of them carries the
driver's message: it can name hosts, users or connection strings, so the connector replaces
the driver's exception with one of these (`raise ... from None`) and keeps only stable facts.
"""


class ConnectorError(Exception):
    """Base class. `code` is stable; `sqlstate` is the database's class of error, if any."""

    code = "connector.error"

    def __init__(self, *, sqlstate: str | None = None) -> None:
        super().__init__(self.code)
        self.sqlstate = sqlstate


class SourceUnavailableError(ConnectorError):
    """The data source cannot be reached or refused the sign-in."""

    code = "source_unavailable"


class SourceDisabledError(ConnectorError):
    """The data source is archived, or its stored credentials cannot be decrypted."""

    code = "source_disabled"


class SourceBusyError(ConnectorError):
    """Too many statements are already waiting for this data source in this process."""

    code = "busy"


class QueryTimeoutError(ConnectorError):
    """The statement ran past the statement timeout and was cancelled."""

    code = "timeout"


class SourceMismatchError(ConnectorError):
    """A bound table or column no longer exists in the data source, or a bound view failed
    while running (SQLSTATE other than class 22)."""

    code = "source_mismatch"


class InvalidValueError(ConnectorError):
    """The database refused a parameter value (SQLSTATE class 22), e.g. an unknown enum label.
    `column` is the column the value was compared with, when the connector can tell."""

    code = "invalid_value"

    def __init__(self, *, column: str | None = None, sqlstate: str | None = None) -> None:
        super().__init__(sqlstate=sqlstate)
        self.column = column
