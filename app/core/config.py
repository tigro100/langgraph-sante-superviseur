from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration applicative.

    Les valeurs peuvent être surchargées via un fichier .env
    ou des variables d'environnement Railway/GitHub/Docker.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # =========================
    # LLM / Groq
    # =========================
    groq_api_key: str | None = None
    groq_model: str = "llama-3.3-70b-versatile"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    mock_llm: bool = False

    # =========================
    # Base de données / observabilité
    # =========================
    db_path: str = "data/observability.db"

    token_price_input_1m: float = 0.59
    token_price_output_1m: float = 0.79
    latency_threshold_ms: int = 8000
    cost_threshold_usd: float = 0.02

    # =========================
    # Application
    # =========================
    app_name: str = "Chatbot pré-diagnostique santé"

    # =========================
    # Rapport d'alertes
    # =========================
    alert_report_threshold: int = 3
    alert_report_cooldown_minutes: int = 60

    # Provider d'envoi email :
    # - "smtp"   = Gmail SMTP
    # - "resend" = API HTTPS Resend, recommandé pour Railway
    email_provider: str = "smtp"

    # =========================
    # Gmail SMTP
    # Utilisé seulement si EMAIL_PROVIDER=smtp
    # =========================
    gmail_enabled: bool = False
    gmail_smtp_host: str = "smtp.gmail.com"
    gmail_smtp_port: int = 587
    gmail_user: str | None = None
    gmail_app_password: str | None = None
    gmail_sender: str | None = None
    gmail_recipients: str | None = None

    # =========================
    # Resend API
    # Utilisé si EMAIL_PROVIDER=resend
    # =========================
    resend_api_key: str | None = None
    resend_from: str | None = None
    resend_recipients: str | None = None

    @property
    def db_file(self) -> Path:
        path = Path(self.db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()