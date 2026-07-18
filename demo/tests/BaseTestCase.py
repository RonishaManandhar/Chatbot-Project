import shutil
import tempfile
import unittest
from pathlib import Path

from flask import g
from werkzeug.security import generate_password_hash

from app import create_app
from app.exts import db
from app.models import (
    Category,
    Priority,
    Status,
    User,
)


class TestingConfig:
    TESTING = True

    SECRET_KEY = "tests-secret-key"

    SQLALCHEMY_DATABASE_URI = (
        "sqlite:///:memory:"
    )

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    WTF_CSRF_ENABLED = False

    MAIL_SUPPRESS_SEND = True

    LOGIN_DISABLED = False

    SERVER_NAME = "localhost"


class BaseTestCase(unittest.TestCase):

    def setUp(self):
        self.temp_dir = Path(
            tempfile.mkdtemp(
                prefix="chatbot_tests_"
            )
        )

        TestingConfig.PROFILE_DIR = str(
            self.temp_dir / "profiles"
        )

        Path(
            TestingConfig.PROFILE_DIR
        ).mkdir(
            parents=True,
            exist_ok=True
        )

        self.app = create_app(
            TestingConfig
        )

        self.ctx = (
            self.app.app_context()
        )

        self.ctx.push()

        db.create_all()

        # ==================================================
        # SEEDED USERS
        # ==================================================

        self.admin = (
            User.query
            .filter_by(
                email="admin@chatbot.com"
            )
            .first()
        )

        self.agent = (
            User.query
            .filter_by(
                email="agent@chatbot.com"
            )
            .first()
        )

        self.customer = (
            User.query
            .filter_by(
                email="customer@chatbot.com"
            )
            .first()
        )

        self._reset_user(
            self.admin,
            role="Administrator",
            password="Admin123!"
        )

        self._reset_user(
            self.agent,
            role="Agent",
            password="Agent123!"
        )

        self._reset_user(
            self.customer,
            role="Customer",
            password="Customer123!"
        )

        # ==================================================
        # REQUIRED DATABASE RECORDS
        # ==================================================

        self.open_status = self._get_or_create(
            Status,
            status="Open"
        )

        self.closed_status = self._get_or_create(
            Status,
            status="Closed"
        )

        self.category = self._get_or_create(
            Category,
            category="Account Access"
        )

        self.priority = self._get_or_create(
            Priority,
            priority="Medium"
        )

        db.session.commit()

        # Store IDs because objects may expire after requests.
        self.admin_id = self.admin.id
        self.agent_id = self.agent.id
        self.customer_id = self.customer.id

        self.client = (
            self.app.test_client()
        )

    def tearDown(self):
        self.logout_session()

        db.session.remove()
        db.drop_all()

        self.ctx.pop()

        shutil.rmtree(
            self.temp_dir,
            ignore_errors=True
        )

    def _reset_user(
        self,
        user,
        role,
        password
    ):
        self.assertIsNotNone(
            user,
            f"Seeded {role} user was not found."
        )

        user.role = role

        user.password = generate_password_hash(
            password
        )

        user.email_verified = True
        user.failed_login_attempts = 0
        user.locked_until = None

    @staticmethod
    def _get_or_create(
        model,
        **kwargs
    ):
        obj = (
            model.query
            .filter_by(**kwargs)
            .first()
        )

        if obj is None:
            obj = model(
                **kwargs
            )

            db.session.add(
                obj
            )

            db.session.flush()

        return obj

    # ======================================================
    # LOGIN HELPERS
    # ======================================================

    def _clear_cached_login_user(self):
        """
        Flask-Login stores the loaded user in g._login_user.

        Because this test class keeps an application context
        open, that cached user must be cleared whenever the
        test switches from Admin to Agent or Customer.
        """

        g.pop(
            "_login_user",
            None
        )

    def login_as(self, user):
        self.assertIsNotNone(
            user,
            "login_as() received no user."
        )

        self._clear_cached_login_user()

        with self.client.session_transaction() as session:
            session.clear()

            session["_user_id"] = str(
                user.id
            )

            session["_fresh"] = True

        self._clear_cached_login_user()

    def logout_session(self):
        self._clear_cached_login_user()

        if hasattr(self, "client"):
            with self.client.session_transaction() as session:
                session.clear()

        self._clear_cached_login_user()

    # ======================================================
    # USER HELPERS
    # ======================================================

    def get_admin(self):
        return db.session.get(
            User,
            self.admin_id
        )

    def get_agent(self):
        return db.session.get(
            User,
            self.agent_id
        )

    def get_customer(self):
        return db.session.get(
            User,
            self.customer_id
        )