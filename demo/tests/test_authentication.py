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

    @patch("app.auth.views.send_login_otp_email", return_value=True)
    def test_correct_password_starts_otp_without_logging_in(self, _send):
        response = self.client.post("/login", data={
            "email": self.customer.email,
            "password": "Customer123!",
        })
        self.assertEqual(302, response.status_code)
        self.assertIn("/verify-login-otp", response.headers["Location"])
        with self.client.session_transaction() as session:
            self.assertEqual(self.customer.id, session.get("pending_login_user_id"))
            self.assertNotIn("_user_id", session)
        self.assertIsNotNone(EmailVerificationCode.query.filter_by(
            user_id=self.customer.id, purpose="login", used=False
        ).first())

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
