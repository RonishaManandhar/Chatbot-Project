import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def get_database_url():
    url = os.getenv("DATABASE_URL") or os.getenv("MYSQL_URL")

    if not url:
        raise RuntimeError(
            "DATABASE_URL or MYSQL_URL must be configured in production."
        )

    if url.startswith("mysql://"):
        url = url.replace("mysql://", "mysql+pymysql://", 1)

    return url


class BaseConfig(object):
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    MAIL_SERVER = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))
    MAIL_USE_TLS = _env_bool("MAIL_USE_TLS", True)
    MAIL_USE_SSL = _env_bool("MAIL_USE_SSL", False)
    MAIL_SUPPRESS_SEND = _env_bool("MAIL_SUPPRESS_SEND", False)
    MAIL_USERNAME = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = (
        os.getenv("MAIL_SENDER_NAME", "NEF IT Service Desk"),
        os.getenv("MAIL_DEFAULT_SENDER") or os.getenv("MAIL_USERNAME"),
    )

    MAX_CONTENT_LENGTH = 4 * 1024 * 1024

    # Local/default path. For persistent Railway storage, set PROFILE_DIR
    # to a directory inside a mounted Railway Volume.
    PROFILE_DIR = os.getenv(
        "PROFILE_DIR",
        os.path.join(BASE_DIR, "app", "static", "uploads", "profiles"),
    )


class TestConfig(BaseConfig):
    DEBUG = True
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "mysql+pymysql://root:Ronishamdr12!@localhost/tickette",
    )


class ProductionConfig(BaseConfig):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = get_database_url()
    SECRET_KEY = os.getenv("SECRET_KEY")

    if not SECRET_KEY:
        raise RuntimeError("SECRET_KEY must be configured in production.")
