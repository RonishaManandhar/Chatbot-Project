from app.exts import db
from app.models import Category, Priority, Status, FAQ, KnowledgeArticle, ChatbotSetting


# ============================================================
# RESET OLD GENERAL SUPPORT DATA
# ============================================================

def clear_support_seed_data():
    FAQ.query.delete()
    KnowledgeArticle.query.delete()

    # Only delete categories/priorities/statuses if you want a clean IT setup
    Category.query.delete()
    Priority.query.delete()
    Status.query.delete()

    db.session.commit()
    print("Old support seed data deleted.")


# ============================================================
# CREATE BASE IT CATEGORIES
# ============================================================

def seed_categories():
    categories = [
        "Help and support",
        "Account Access",
        "Password Reset",
        "Email",
        "Network",
        "Software",
        "Hardware",
        "Security",
        "Printer",
        "System Performance"
    ]

    for name in categories:
        if not Category.query.filter(Category.category.ilike(name)).first():
            db.session.add(Category(category=name))

    db.session.commit()
    print("IT categories seeded.")


# ============================================================
# CREATE PRIORITIES
# ============================================================

def seed_priorities():
    priorities = ["Low", "Medium", "High", "Urgent"]

    for name in priorities:
        if not Priority.query.filter(Priority.priority.ilike(name)).first():
            db.session.add(Priority(priority=name))

    db.session.commit()
    print("Priorities seeded.")


# ============================================================
# CREATE STATUSES
# ============================================================

def seed_statuses():
    statuses = [
        "Open",
        "Solved",
        "Pending",
        "Closed",
        "Escalated",
        "Waiting For Customer"
    ]

    for name in statuses:
        if not Status.query.filter(Status.status.ilike(name)).first():
            db.session.add(Status(status=name))

    db.session.commit()
    print("Statuses seeded.")


# ============================================================
# HELPER
# ============================================================

def get_category_id(name):
    category = Category.query.filter(Category.category.ilike(name)).first()
    if category:
        return category.id

    fallback = Category.query.filter(Category.category.ilike("Help and support")).first()
    return fallback.id if fallback else None


# ============================================================
# CREATE IT FAQs
# ============================================================

def seed_faqs():
    faqs = [
        {
            "category": "Password Reset",
            "question": "How do I reset my password?",
            "answer": "Go to the login page, click Forgot Password, enter your registered email address, and follow the reset link sent to your email. If you do not receive the email, check your spam folder or contact IT support.",
            "tags": "password, reset, forgot password, login"
        },
        {
            "category": "Account Access",
            "question": "Why is my account locked?",
            "answer": "Your account may be locked because of multiple failed login attempts or security protection rules. Wait for the lock period to expire or create a support ticket so IT staff can verify your identity and unlock the account.",
            "tags": "account locked, login failed, access"
        },
        {
            "category": "Email",
            "question": "Why am I not receiving emails?",
            "answer": "Check your internet connection, spam or junk folder, mailbox storage, and email filters. If emails are still missing, create a support ticket because IT may need to check mail server rules or account settings.",
            "tags": "email, not receiving, mailbox, spam"
        },
        {
            "category": "Network",
            "question": "What should I do if Wi-Fi is not working?",
            "answer": "Restart your device, turn Wi-Fi off and on, forget and reconnect to the network, and check whether other users are affected. If multiple users are affected, create a high priority support ticket.",
            "tags": "wifi, network, internet, connection"
        },
        {
            "category": "Software",
            "question": "What should I do if an application keeps crashing?",
            "answer": "Close and reopen the application, restart your device, check for updates, and clear temporary files if available. If the application still crashes, create a support ticket with the app name, error message, and steps already tried.",
            "tags": "software, app crash, application, error"
        },
        {
            "category": "Hardware",
            "question": "What should I do if my computer will not turn on?",
            "answer": "Check the power cable, charger, power socket, and battery. Hold the power button for 10 seconds, then try turning it on again. If there is still no response, create a support ticket because hardware inspection may be required.",
            "tags": "hardware, computer, laptop, power"
        },
        {
            "category": "Security",
            "question": "What should I do if I clicked a suspicious link?",
            "answer": "Disconnect from the internet if possible, do not enter any passwords, take a screenshot of the message, and report it immediately. Create an urgent support ticket so IT can investigate the possible phishing or security risk.",
            "tags": "security, phishing, suspicious link, hacked"
        },
        {
            "category": "Printer",
            "question": "Why is the printer not printing?",
            "answer": "Check that the printer is powered on, has paper and toner, and is connected to the network. Restart the printer and try printing again. If the issue continues, create a support ticket with the printer name and error message.",
            "tags": "printer, printing, paper, toner"
        },
        {
            "category": "System Performance",
            "question": "Why is my computer running slowly?",
            "answer": "Restart your computer, close unused applications, check storage space, and make sure updates are not running in the background. If the device is still slow, create a support ticket for further diagnosis.",
            "tags": "slow computer, performance, lag, freezing"
        },
        {
            "category": "Help and support",
            "question": "When should I create a support ticket?",
            "answer": "Create a support ticket when the FAQ or AI answer does not solve your issue, when the issue requires account access, admin permission, hardware replacement, security investigation, or when multiple users are affected.",
            "tags": "support ticket, human support, escalation"
        }
    ]

    for item in faqs:
        existing = FAQ.query.filter(FAQ.question.ilike(item["question"])).first()

        if not existing:
            db.session.add(FAQ(
                question=item["question"],
                answer=item["answer"],
                category_id=get_category_id(item["category"]),
                tags=item["tags"],
                is_active=True
            ))

    db.session.commit()
    print("IT FAQs seeded.")


# ============================================================
# CREATE KNOWLEDGE BASE ARTICLES
# ============================================================

def seed_knowledge_articles():
    articles = [
        {
            "category": "Password Reset",
            "title": "Password Reset Troubleshooting Guide",
            "content": """
If a user cannot reset their password, first confirm they are using the correct registered email address.
Ask them to check spam or junk folders for the reset email.
If the reset link has expired, request a new link.
If the account is locked, IT staff must verify the user identity before unlocking it.
For repeated password reset failures, create a support ticket and include the user email, time of attempt, and any error message.
""",
            "tags": "password, reset, login, account"
        },
        {
            "category": "Account Access",
            "title": "Account Locked or Login Failure Process",
            "content": """
Common causes of account lockout include incorrect password attempts, expired passwords, disabled accounts, or suspicious login protection.
The customer should confirm username/email, try password reset, and wait if a temporary lock is active.
Support staff should verify identity before unlocking or changing account access.
If the user reports suspicious activity, escalate as a security issue.
""",
            "tags": "account locked, login failed, access denied"
        },
        {
            "category": "Email",
            "title": "Email Delivery Troubleshooting",
            "content": """
For missing incoming emails, check spam, junk, filters, blocked senders, and mailbox storage.
For outgoing email issues, check internet connection, attachment size, and email client errors.
If only one sender is affected, verify the sender address and blocked list.
If many users are affected, treat it as a possible service outage and raise priority.
""",
            "tags": "email, inbox, outgoing, mailbox"
        },
        {
            "category": "Network",
            "title": "Network and Wi-Fi Troubleshooting",
            "content": """
Start by checking whether the issue affects one user, multiple users, or the entire team.
For one user, restart the device, reconnect to Wi-Fi, and test another website.
For multiple users, check router, access point, or network outage.
If the network is unavailable for a whole team or business area, create a high priority ticket.
""",
            "tags": "wifi, network, internet, outage"
        },
        {
            "category": "Software",
            "title": "Application Crash Troubleshooting",
            "content": """
Ask the user for the application name, version, device, and exact error message.
Basic steps include restarting the app, restarting the device, checking updates, clearing cache, and testing again.
If the app is business critical or affects many users, increase priority.
If admin installation or licence access is required, create a support ticket.
""",
            "tags": "software, crash, app, licence"
        },
        {
            "category": "Hardware",
            "title": "Hardware Fault Initial Checks",
            "content": """
For power issues, check charger, cable, battery, socket, and power button.
For display issues, check brightness, external monitor, cables, and restart the device.
For keyboard, mouse, or peripheral issues, reconnect the device and test another port.
Hardware replacement or repair must be handled by support staff.
""",
            "tags": "hardware, laptop, monitor, keyboard, mouse"
        },
        {
            "category": "Security",
            "title": "Phishing and Suspicious Activity Response",
            "content": """
If a user clicked a suspicious link, advise them not to enter passwords or personal information.
Ask them to capture details such as sender, link, screenshot, and time received.
If credentials were entered, treat the issue as urgent and escalate immediately.
Support staff may need to reset passwords, review account activity, and block malicious senders.
""",
            "tags": "security, phishing, suspicious, hacked"
        },
        {
            "category": "Printer",
            "title": "Printer Issue Troubleshooting",
            "content": """
Check printer power, network connection, paper tray, toner, and display errors.
Ask whether the issue affects one user or multiple users.
Restart the printer and try printing a test page.
If the printer shows a hardware fault or network error, create a support ticket with the printer location and error message.
""",
            "tags": "printer, print queue, toner, paper"
        },
        {
            "category": "System Performance",
            "title": "Slow Device Troubleshooting",
            "content": """
A slow device may be caused by low storage, too many applications, pending updates, malware, or hardware limitations.
Ask the user to restart the device, close unused apps, check storage, and note when the slowness started.
If the device freezes regularly or affects work, create a support ticket for deeper diagnosis.
""",
            "tags": "slow, performance, freezing, lag"
        }
    ]

    for item in articles:
        existing = KnowledgeArticle.query.filter(
            KnowledgeArticle.title.ilike(item["title"])
        ).first()

        if not existing:
            db.session.add(KnowledgeArticle(
                title=item["title"],
                content=item["content"].strip(),
                category_id=get_category_id(item["category"]),
                tags=item["tags"],
                is_active=True
            ))

    db.session.commit()
    print("Knowledge Base articles seeded.")


# ============================================================
# CHATBOT SETTINGS
# ============================================================

def seed_chatbot_settings():
    setting = ChatbotSetting.query.first()

    if not setting:
        setting = ChatbotSetting()
        db.session.add(setting)

    setting.ai_enabled = True
    setting.auto_escalation_enabled = True
    setting.fallback_message = "AI is temporarily unavailable. Please create a support ticket."
    setting.escalation_keywords = "urgent,hacked,phishing,breach,security,account locked,not working,cannot work,whole team,everyone"
    setting.chatbot_tone = "Professional"
    setting.response_length = "Medium"
    setting.confidence_threshold = 70
    setting.system_prompt = """
You are an AI-powered IT Service Desk assistant.
Use FAQ and Knowledge Base content first.
If no exact answer exists, provide safe general IT troubleshooting.
Recommend creating a support ticket when the issue needs account access, admin permission, hardware repair, security investigation, or human support.
"""

    db.session.commit()
    print("Chatbot settings seeded.")


# ============================================================
# MAIN SEED FUNCTION
# ============================================================

def seed_it_service_desk(reset=True):
    if reset:
        clear_support_seed_data()

    seed_categories()
    seed_priorities()
    seed_statuses()
    seed_faqs()
    seed_knowledge_articles()
    seed_chatbot_settings()

    print("IT Service Desk seed completed successfully.")