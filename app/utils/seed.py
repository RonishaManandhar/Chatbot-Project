from app.exts import db
from app.models import FAQ

def seed_faq():
    if FAQ.query.count() > 0:
        print("FAQs already exist. Skipping.")
        return

    db.session.add(FAQ(
        question="How do I reset my password?",
        answer="Go to Login > Forgot Password and follow the instructions.",
        tags="password,login"
    ))
    db.session.add(FAQ(
        question="How can I create a support ticket?",
        answer="You must log in, then go to Customer > Create Ticket.",
        tags="ticket,customer"
    ))
    db.session.add(FAQ(
        question="Can I chat without logging in?",
        answer="Yes, guests can ask general questions, but must log in to create tickets or see chat history.",
        tags="guest,login"
    ))

    db.session.commit()
    print("FAQ seed completed ✅")
