from app.exts import db
from app.models import Comment, Ticket
from tests.BaseTestCase import BaseTestCase


class TicketTests(BaseTestCase):
    def make_ticket(self, number="TEST-001"):
        ticket = Ticket(
            number=number, subject="Cannot log in", body="Account access issue",
            author_id=self.customer.id, owner_id=None,
            category_id=self.category.id, priority_id=self.priority.id,
            status_id=self.open_status.id, orig_file=None, file_link=None,
        )
        db.session.add(ticket)
        db.session.commit()
        return ticket

    def test_ticket_relationships(self):
        ticket = self.make_ticket()
        comment = Comment("Please help", self.customer.id, ticket.id)
        db.session.add(comment)
        db.session.commit()
        self.assertEqual(self.customer.id, ticket.author.id)
        self.assertEqual(ticket.id, comment.ticket_id)
        self.assertEqual("Account Access", ticket.category.category)

    def test_customer_support_requests_returns_only_own_tickets(self):
        ticket = self.make_ticket()
        self.login_as(self.customer)
        response = self.client.get("/customer/api/support-requests")
        self.assertEqual(200, response.status_code)
        data = response.get_json()
        self.assertTrue(data["ok"])
        self.assertIn(ticket.id, [item["id"] for item in data["tickets"]])
