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

    def test_manual_ticket_form_is_available_from_my_chats(self):
        self.login_as(self.customer)

        response = self.client.get(
            "/customer/my-tickets"
        )

        self.assertEqual(
            200,
            response.status_code
        )

        self.assertIn(
            b"New Support Ticket",
            response.data
        )

        self.assertIn(
            b"/customer/create-ticket",
            response.data
        )

    def test_customer_can_create_manual_ticket_without_triage(self):
        self.login_as(self.customer)

        response = self.client.post(
            "/customer/create-ticket",
            data={
                "subject": "Manual network support request",
                "category": str(self.category.id),
                "body": "The office Wi-Fi disconnects every few minutes."
            },
            follow_redirects=False
        )

        self.assertEqual(
            302,
            response.status_code
        )

        self.assertIn(
            "/customer/my-tickets",
            response.headers["Location"]
        )

        ticket = Ticket.query.filter_by(
            author_id=self.customer.id,
            subject="Manual network support request"
        ).first()

        self.assertIsNotNone(ticket)
        self.assertIsNone(ticket.owner_id)
        self.assertEqual(self.open_status.id, ticket.status_id)
        self.assertEqual(self.category.id, ticket.category_id)

        history_response = self.client.get(
            "/customer/my-tickets"
        )

        self.assertEqual(
            200,
            history_response.status_code
        )

        self.assertIn(
            b"Manual network support request",
            history_response.data
        )
