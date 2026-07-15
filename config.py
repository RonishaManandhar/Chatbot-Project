import os

path = os.getcwd()


def get_database_url():
    url = os.getenv("DATABASE_URL")

    if url and url.startswith("mysql://"):
        url = url.replace("mysql://", "mysql+pymysql://", 1)

    return url


class BaseConfig(object):
    SECRET_KEY = os.getenv(
        "SECRET_KEY",
        "dev-secret-key"
    )

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # =====================================
    # SMTP
    # =====================================

    MAIL_SERVER = os.getenv(
        "MAIL_SERVER",
        "smtp.gmail.com"
    )

    MAIL_PORT = int(
        os.getenv(
            "MAIL_PORT",
            587
        )
    )

    MAIL_USE_TLS = True
    MAIL_USE_SSL = False

    MAIL_USERNAME = os.getenv(
        "MAIL_USERNAME"
    )

    MAIL_PASSWORD = os.getenv(
        "MAIL_PASSWORD"
    )

    MAIL_DEFAULT_SENDER = (
        "NEF IT Service Desk",
        os.getenv("MAIL_USERNAME")
    )

    MAX_CONTENT_LENGTH = (
        4 * 1024 * 1024
    )

    PROFILE_DIR = os.path.join(
        path,
        "app/static/uploads/profiles"
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
        "mysql+pymysql://root:Ronishamdr12!@localhost/tickette"
    )


class ProductionConfig(BaseConfig):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = get_database_url()