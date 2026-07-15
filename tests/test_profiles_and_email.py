from app.exts import db
from app.models import User
from tests.BaseTestCase import BaseTestCase


class ProfileAndEmailTests(BaseTestCase):
    CASES = (("admin", "Administrator"), ("agent", "Agent"), ("customer", "Customer"))

    def test_profile_pages_load(self):
        for prefix, role in self.CASES:
            with self.subTest(role=role):
                self.logout_session()
                user = User.query.filter_by(role=role).first()
                self.login_as(user)
                self.assertEqual(200, self.client.get(f"/{prefix}/my-profile").status_code)

    def test_profile_name_updates(self):
        for prefix, role in self.CASES:
            with self.subTest(role=role):
                self.logout_session()
                user = User.query.filter_by(role=role).first()
                user_id = user.id
                self.login_as(user)
                response = self.client.post(
                    f"/{prefix}/my-profile",
                    data={"name": f"Updated {role}"},
                    follow_redirects=True,
                )
                self.assertEqual(200, response.status_code)
                db.session.expire_all()
                self.assertEqual(f"Updated {role}", db.session.get(User, user_id).name)

    def test_customer_email_change_is_lowercase(self):
        self.login_as(self.customer)
        response = self.client.post("/customer/change-email", data={
            "email": "UPDATED.CUSTOMER@EXAMPLE.COM",
            "password": "Customer123!",
        }, follow_redirects=True)
        self.assertEqual(200, response.status_code)
        db.session.expire_all()
        self.assertEqual("updated.customer@example.com", db.session.get(User, self.customer.id).email)

    def test_duplicate_customer_email_is_rejected(self):
        original = self.customer.email
        self.login_as(self.customer)
        response = self.client.post("/customer/change-email", data={
            "email": self.agent.email,
            "password": "Customer123!",
        }, follow_redirects=True)
        self.assertEqual(200, response.status_code)
        db.session.expire_all()
        self.assertEqual(original, db.session.get(User, self.customer.id).email)
