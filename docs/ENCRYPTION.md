# Encryption at Rest - Implementation Guide

## Overview
AEIMPS implements encryption at rest for sensitive data using industry-standard cryptographic libraries.

## Components

### 1. PostgreSQL - pgcrypto Extension
- **Status**: Enabled in `infrastructure/postgres/init.sql`
- **Usage**: Available for encrypting sensitive columns
- **Functions**: `pgp_sym_encrypt()`, `pgp_sym_decrypt()`

### 2. Application-Level Encryption
- **Service**: `app/services/encryption_service.py`
- **Algorithm**: Fernet (AES-128 CBC with HMAC authentication)
- **Key Derivation**: PBKDF2-SHA256 from SECRET_KEY
- **Usage**:
```python
from app.services.encryption_service import get_encryption_service

enc = get_encryption_service()
encrypted = enc.encrypt("sensitive data")
decrypted = enc.decrypt(encrypted)
```

### 3. Redis Persistence
- **AOF**: Enabled with `appendfsync everysec`
- **Protection**: File system encryption recommended at infrastructure level
- **Note**: Redis data protected by password authentication

### 4. File Storage Encryption
- **Service**: `encryption_service.encrypt()` for file content
- **Storage**: Encrypted files in `/data/raw`
- **Metadata**: Encryption IV stored in Document model

## Key Management

### Current Implementation
- **Master Key**: `SECRET_KEY` environment variable (64+ characters)
- **Derivation**: PBKDF2 with 100,000 iterations
- **Salt**: Application-specific (stored in code)

### Production Recommendations
1. Use Docker Secrets or external vault for SECRET_KEY
2. Rotate encryption keys periodically
3. Store encryption salt separately from application
4. Consider AWS KMS, HashiCorp Vault, or Azure Key Vault for enterprise deployments

## Encrypted Fields

### User Model
- `password_hash`: Bcrypt (one-way hash, not encrypted)
- `password_reset_token`: JWT (signed, not encrypted)

### Document Model
- File content: Encrypted on disk when using encryption service
- Sensitive metadata: Can be encrypted using encryption service

### Best Practices
1. Encrypt PII (personally identifiable information)
2. Encrypt authentication tokens at rest
3. Use encrypted columns for sensitive business data
4. Never log encrypted data or encryption keys

## Migration Guide

### Enabling Encryption for Existing Data
```python
# Example: Encrypt existing document content
from app.services.encryption_service import get_encryption_service
from app.db.models import Document

enc = get_encryption_service()

async def encrypt_documents():
    docs = await db.execute(select(Document))
    for doc in docs.scalars():
        if doc.content and not doc.is_encrypted:
            doc.content = enc.encrypt(doc.content)
            doc.is_encrypted = True
    await db.commit()
```

## Compliance Notes
- **At-Rest Encryption**: ✅ Application and database level
- **In-Transit Encryption**: Configure TLS/SSL (see deployment guide)
- **Key Rotation**: Manual process (automate in production)
- **Audit**: All encryption/decryption logged via audit middleware
