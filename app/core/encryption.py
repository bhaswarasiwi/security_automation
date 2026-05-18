"""
app/core/encryption.py
----------------------
Enkripsi/dekripsi API key menggunakan Fernet (AES-128-CBC + HMAC-SHA256).
Kunci enkripsi dibaca dari ENCRYPTION_KEY di environment variable.

Setup di Render ENV:
    ENCRYPTION_KEY=<generate dengan: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">

JANGAN hardcode key di kode. JANGAN commit ke git.
"""

from __future__ import annotations
import os
import logging
from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

def _get_fernet() -> Fernet:
    key = os.environ.get("ENCRYPTION_KEY")
    if not key:
        raise RuntimeError(
            "ENCRYPTION_KEY tidak ditemukan di environment. "
            "Generate dengan: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return Fernet(key.encode())

def encrypt_api_key(plaintext: str) -> str:
    """Enkripsi API key sebelum disimpan ke DB. Return string base64."""
    if not plaintext or not plaintext.strip():
        raise ValueError("API key tidak boleh kosong")
    return _get_fernet().encrypt(plaintext.encode()).decode()

def decrypt_api_key(encrypted: str) -> str:
    """Dekripsi API key saat akan digunakan untuk AI call. Jangan log hasilnya."""
    try:
        return _get_fernet().decrypt(encrypted.encode()).decode()
    except InvalidToken:
        logger.error("Gagal mendekripsi API key — token tidak valid atau key berubah")
        raise ValueError("API key tidak dapat didekripsi. Mungkin key enkripsi berubah.")
