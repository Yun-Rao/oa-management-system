from app.core.config import settings


def test_settings_has_required_fields():
    assert settings.DATABASE_URL
    assert settings.JWT_SECRET_KEY
    assert settings.JWT_EXPIRE_MINUTES == 1440
    assert settings.SEED_ADMIN_EMAIL
    assert settings.SEED_ADMIN_PASSWORD
