from app.core.config import Settings, get_settings

INSECURE_DEFAULT_JWT_SECRET = "change-me-in-env"


class InsecureConfigurationError(Exception):
    pass


def validate_production_settings(settings: Settings | None = None) -> None:
    """Fail fast at startup rather than silently running with an insecure
    configuration — a wrong-but-quiet default is far more dangerous than a
    loud crash on boot, since the former can run in production for months
    unnoticed. Only enforced outside local/test, where an insecure default
    is expected and convenient (see backend/.env.example)."""
    settings = settings or get_settings()
    if settings.environment in ("local", "test"):
        return

    if settings.jwt_secret_key == INSECURE_DEFAULT_JWT_SECRET:
        raise InsecureConfigurationError(
            "JWT_SECRET_KEY is still set to its insecure placeholder default. "
            "Set a long, random secret before running in this environment."
        )

    if "*" in settings.cors_origins:
        raise InsecureConfigurationError(
            'CORS_ORIGINS includes a wildcard ("*"), which combined with '
            "allow_credentials=True would let any site read authenticated "
            "responses. Set explicit allowed origins instead."
        )
