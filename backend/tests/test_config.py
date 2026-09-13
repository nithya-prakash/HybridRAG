from app.core.config import Settings


def test_postgres_url_rewrites_plain_postgres_scheme():
    settings = Settings(postgres_url="postgres://user:pw@host:5432/db")

    assert settings.postgres_url == "postgresql+asyncpg://user:pw@host:5432/db"


def test_postgres_url_rewrites_plain_postgresql_scheme():
    settings = Settings(postgres_url="postgresql://user:pw@host:5432/db")

    assert settings.postgres_url == "postgresql+asyncpg://user:pw@host:5432/db"


def test_postgres_url_leaves_asyncpg_scheme_untouched():
    url = "postgresql+asyncpg://user:pw@host:5432/db"

    settings = Settings(postgres_url=url)

    assert settings.postgres_url == url
