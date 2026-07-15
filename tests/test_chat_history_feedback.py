from app.exts import db
from app.models import ChatMessage, ChatSession, CustomerSatisfaction
from tests.BaseTestCase import BaseTestCase


class ChatHistoryFeedbackTests(BaseTestCase):
    def make_session(self, title="Network problem"):
        session = ChatSession(user_id=self.customer.id, title=title, issue_type="Network")
        db.session.add(session)
        db.session.flush()
        message = ChatMessage(
            user_id=self.customer.id, session_id=session.id, ticket_id=None,
            role="user", message="Wi-Fi is disconnected", customer_visible=True,
        )
        db.session.add(message)
        db.session.commit()
        return session, message

    def test_chat_history_search_returns_matching_session(self):
        session, _ = self.make_session()
        self.login_as(self.customer)
        response = self.client.get("/customer/api/chat/sessions?search=Network")
        self.assertEqual(200, response.status_code)
        ids = [item["id"] for item in response.get_json()["sessions"]]
        self.assertIn(session.id, ids)

    def test_chat_session_and_messages_persist(self):
        session, message = self.make_session()
        db.session.expire_all()
        self.assertIsNotNone(db.session.get(ChatSession, session.id))
        self.assertIsNotNone(db.session.get(ChatMessage, message.id))

    def test_feedback_is_unique_and_history_remains(self):
        session, message = self.make_session()
        self.login_as(self.customer)
        response = self.client.post(
            f"/customer/api/chat/session/{session.id}/rate",
            json={"rating": 5, "feedback": "Helpful"},
        )
        self.assertEqual(200, response.status_code)
        self.assertEqual(1, CustomerSatisfaction.query.filter_by(
            customer_id=self.customer.id, session_id=session.id
        ).count())
        self.assertIsNotNone(db.session.get(ChatMessage, message.id))

        second = self.client.post(
            f"/customer/api/chat/session/{session.id}/rate",
            json={"rating": 4, "feedback": "Updated"},
        )
        self.assertIn(second.status_code, (200, 400, 409))
        self.assertEqual(1, CustomerSatisfaction.query.filter_by(
            customer_id=self.customer.id, session_id=session.id
        ).count())
