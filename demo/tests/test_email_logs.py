from app.exts import db
from app.models import EmailLog
from tests.BaseTestCase import BaseTestCase


class EmailLogTests(BaseTestCase):
    def make_log(self, status="Sent"):
        log = EmailLog(
            recipient="customer@example.com", subject="Ticket update",
            email_type="ticket_update", status=status,
            user_id=self.customer.id,
        )
        db.session.add(log)
        db.session.commit()
        return log

    def test_admin_email_logs_page_loads(self):
        self.make_log()
        self.login_as(self.admin)
        self.assertEqual(200, self.client.get("/admin/email-logs").status_code)

    def test_email_log_filters_work(self):
        self.make_log("Sent")
        self.make_log("Failed")
        self.login_as(self.admin)
        response = self.client.get("/admin/email-logs?status=Failed")
        self.assertEqual(200, response.status_code)
        self.assertIn(b"Failed", response.data)

    def test_delete_single_email_log(self):
        log = self.make_log()
        log_id = log.id
        self.login_as(self.admin)
        response = self.client.post(f"/admin/email-logs/delete/{log_id}")
        self.assertEqual(302, response.status_code)
        self.assertIsNone(db.session.get(EmailLog, log_id))
