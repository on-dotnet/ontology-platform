"""Data source credentials at rest (spec 003, 5.4): the only place that decrypts them.

AES-256-GCM with a key derived from OP_SECRET_KEY by HKDF-SHA256. The data source id is the
associated data, so ciphertext copied to another row does not open. The stored value is
version byte + 12-byte nonce + ciphertext with tag; `secret_key_id` is the derived key's
fingerprint, which picks the key among OP_SECRET_KEY and OP_SECRET_KEY_PREVIOUS when decrypting.
"""

import hashlib
import json
import os
from dataclasses import dataclass
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from pydantic import SecretStr

from ontology_platform.modules.connectors.errors import CredentialUnreadableError
from ontology_platform.settings import Settings

_INFO = b"op/datasource-credentials/v1"
_VERSION = b"\x01"
_NONCE_BYTES = 12


@dataclass(frozen=True, slots=True)
class SealedCredential:
    """What the `secret` and `secret_key_id` columns store."""

    secret: bytes
    key_id: str


@dataclass(frozen=True, slots=True)
class _Key:
    id: str
    value: bytes


def _derive(secret: SecretStr) -> _Key:
    value = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=_INFO).derive(
        secret.get_secret_value().encode()
    )
    return _Key(id=hashlib.sha256(value).hexdigest()[:16], value=value)


def current_key_id(settings: Settings) -> str:
    return _derive(settings.secret_key).id


def seal(settings: Settings, data_source_id: UUID, password: SecretStr) -> SealedCredential:
    """Encrypt the password for one data source with the current key."""
    key = _derive(settings.secret_key)
    nonce = os.urandom(_NONCE_BYTES)
    plaintext = json.dumps({"password": password.get_secret_value()}).encode()
    sealed = AESGCM(key.value).encrypt(nonce, plaintext, data_source_id.bytes)
    return SealedCredential(secret=_VERSION + nonce + sealed, key_id=key.id)


def open_password(
    settings: Settings, data_source_id: UUID, secret: bytes, key_id: str | None
) -> SecretStr:
    """The stored password; CredentialUnreadableError when no configured key opens it. Called
    right before connecting, and by `rekey`."""
    keys = {
        key.id: key for key in map(_derive, [settings.secret_key, *settings.previous_secret_keys])
    }
    key = keys.get(key_id or "")
    if key is None or len(secret) <= 1 + _NONCE_BYTES or secret[:1] != _VERSION:
        raise CredentialUnreadableError
    nonce, sealed = secret[1 : 1 + _NONCE_BYTES], secret[1 + _NONCE_BYTES :]
    try:
        plaintext = AESGCM(key.value).decrypt(nonce, sealed, data_source_id.bytes)
        password = json.loads(plaintext)["password"]
    except (InvalidTag, ValueError, KeyError, TypeError):
        raise CredentialUnreadableError from None
    if not isinstance(password, str):
        raise CredentialUnreadableError
    return SecretStr(password)
