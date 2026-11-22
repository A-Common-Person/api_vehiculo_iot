from pydantic import FilePath, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


ORIGEN_PUBLICO = "https://a-common-person.github.io"
ORIGENES_LOCALES = (
    "http://localhost:5500",
    "http://127.0.0.1:5500",
    "http://localhost:8001",
    "http://127.0.0.1:8001",
)


class Settings(BaseSettings):
    db_host: str
    db_port: int
    db_user: str
    db_password: str
    db_name: str
    api_key: str | None = None
    db_ssl_ca: FilePath | None = None
    administracion_habilitada: bool = False
    publicacion_habilitada: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @model_validator(mode="after")
    def validar_modo(self):
        if self.publicacion_habilitada and not self.administracion_habilitada:
            raise ValueError("PUBLICACION_HABILITADA requiere la administración habilitada")
        if self.administracion_habilitada and self.db_ssl_ca is None:
            raise ValueError("La administración requiere DB_SSL_CA para verificar la identidad de RDS")
        if not self.administracion_habilitada and not self.api_key:
            raise ValueError("El modo compatible de Control y Monitoreo requiere API_KEY")
        return self


settings = Settings()
ORIGENES_CLIENTE = (ORIGEN_PUBLICO,) if settings.publicacion_habilitada else (ORIGEN_PUBLICO, *ORIGENES_LOCALES)
