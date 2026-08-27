"""Encryption service for data at rest."""
from __future__ import annotations

import base64
import hashlib
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2

from app.core.config import settings


class EncryptionService:
    """Service for encrypting/decrypting sensitive data."""

    def __init__(self):
        self._cipher = self._get_cipher()

    def _get_cipher(self) -> Fernet:
        """Get Fernet cipher from secret key."""
        # Derive 32-byte key from SECRET_KEY
        kdf = PBKDF2(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"aeimps_encryption_salt",  # In production, store separately
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(settings.SECRET_KEY.encode()))
        return Fernet(key)

    def encrypt(self, data: str | bytes) -> str:
        """Encrypt data and return base64-encoded ciphertext."""
        if isinstance(data, str):
            data = data.encode()
        encrypted = self._cipher.encrypt(data)
        return base64.b64encode(encrypted).decode()

    def decrypt(self, encrypted_data: str) -> str:
        """Decrypt base64-encoded ciphertext."""
        encrypted_bytes = base64.b64decode(encrypted_data.encode())
        decrypted = self._cipher.decrypt(encrypted_bytes)
        return decrypted.decode()


# Singleton instance
_encryption_service: EncryptionService | None = None


def get_encryption_service() -> EncryptionService:
    """Get encryption service singleton."""
    global _encryption_service
    if _encryption_service is None:
        _encryption_service = EncryptionService()
    return _encryption_service
