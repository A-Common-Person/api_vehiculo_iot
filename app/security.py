import secrets

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from app.config import settings

_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verificar_api_key(api_key: str | None = Security(_header)):
    if not api_key:
        raise HTTPException(status_code=401, detail="Falta la API key")
    if not secrets.compare_digest(api_key.encode(), settings.api_key.encode()):
        raise HTTPException(status_code=403, detail="API key inválida")