from unittest.mock import patch

from werkzeug.security import check_password_hash

from app.exts import db
from app.models import EmailVerificationCode, User
from tests.BaseTestCase import BaseTestCase


class AuthenticationTests(BaseTestCase):
    def test_login_page_loads(self):
        self.assertEqual(200, self.client.get("/login").status_code)

    def test_incorrect_login_does_not_authenticate(self):
        response = self.client.post("/login", data={
            "email": self.customer.email,
            "password": "wrong-password",
        })
        self.assertEqual(200, response.status_code)
        with self.client.session_transaction() as session:
            self.assertNotIn("_user_id", session)

    @patch("app.auth.views.send_verification_email", return_value=True)
    def test_signup_creates_unverified_customer(self, _send):
        response = self.client.post("/signup", data={
            "name": "New Customer",
            "email": "new.customer@example.com",
            "password": "StrongPass123!",
            "agree": "y",
        })
        self.assertEqual(302, response.status_code)
        user = User.query.filter_by(email="new.customer@example.com").first()
        self.assertIsNotNone(user)
        self.assertFalse(user.email_verified)
        self.assertTrue(check_password_hash(user.password, "StrongPass123!"))

    def test_role_protected_route_rejects_wrong_role(self):
        self.login_as(self.customer)
        response = self.client.get("/admin/dashboard")
        self.assertEqual(302, response.status_code)
        self.assertIn("/login", response.headers["Location"])

    def test_verified_user_logs_in_without_login_otp(self):
        response = self.client.post(
            "/login",
            data={
                "email": self.customer.email,
                "password": "Customer123!",
            },
            follow_redirects=False,
        )

        self.assertEqual(302, response.status_code)

        with self.client.session_transaction() as session:
            self.assertEqual(
                str(self.customer.id),
                session.get("_user_id"),
            )

            self.assertNotIn(
                "pending_login_user_id",
                session,
            )