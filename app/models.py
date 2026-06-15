from flask import current_app
from flask_login import UserMixin

from app.exts import db, login_manager
from sqlalchemy.sql import func
from sqlalchemy import event
from datetime import datetime

from itsdangerous import URLSafeTimedSerializer
from werkzeug.security import generate_password_hash

@login_manager.user_loader
def load_user(user_id):
    try:
        return User.query.get(int(user_id))
    except Exception:
        return None
    

# Database models
class User(db.Model, UserMixin):
	__tablename__ = 'users'

	id = db.Column(db.Integer, primary_key=True)
	name = db.Column(db.String(255), nullable=False)
	email = db.Column(db.String(255), unique=True, nullable=False)
	password = db.Column(db.String(255), nullable=False)
	role = db.Column(db.String(255), nullable=False)
	image = db.Column(db.String(255), nullable=False)
	failed_login_attempts = db.Column(db.Integer, default=0, nullable=False)
	locked_until = db.Column(db.DateTime, nullable=True)
	
	created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())
	updated_at = db.Column(db.DateTime(timezone=True), onupdate=func.now())

	# Relationship
	author_tickets = db.relationship('Ticket', foreign_keys='Ticket.author_id',
		backref='author', cascade='all, delete-orphan', lazy=True)
	owner_tickets = db.relationship('Ticket', foreign_keys='Ticket.owner_id',
		backref='owner', passive_deletes=True, lazy=True)
	
	comments = db.relationship('Comment', backref='user', cascade='all, delete-orphan', lazy=True)
	
	receivers = db.relationship('Notification', foreign_keys='Notification.receiver_id',
		backref='receiver', cascade='all, delete-orphan', lazy=True)
	senders = db.relationship('Notification', foreign_keys='Notification.sender_id',
		backref='sender', cascade='all, delete-orphan', lazy=True)
	
	def get_reset_token(self, expires_sec=1800):
		from flask import current_app
		s = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
		return s.dumps({"user_id": self.id})

	@staticmethod
	def verify_reset_token(token, expires_sec=1800):
		from flask import current_app
		s = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
		try:
			data = s.loads(token, max_age=expires_sec)
		except Exception:
			return None
		from app.models import User
		return User.query.get(data.get("user_id"))

	def __init__(self, name, email, password, role, image):
		self.name = name
		self.email = email
		self.password = password
		self.role = role
		self.image = image

@event.listens_for(User.__table__, 'after_create')
def create_users(*args, **kwargs):
	profile = 'default-profile.png'
	db.session.add(User(name='Ryan Reynolds', email='admin@chatbot.com', password=generate_password_hash('admindemo'), role='Administrator', image=profile))
	db.session.add(User(name='Robert Downey', email='agent@chatbot.com', password=generate_password_hash('agentdemo'), role='Agent', image=profile))
	db.session.add(User(name='Jeremy Renner', email='customer@chatbot.com', password=generate_password_hash('customerdemo'), role='Customer', image=profile))
	db.session.commit()

class Ticket(db.Model):
    __tablename__ = 'tickets'

    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(255), unique=True, nullable=False)
    subject = db.Column(db.String(255), nullable=False)
    body = db.Column(db.Text, nullable=False)

    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)

    category_id = db.Column(db.Integer, db.ForeignKey('categories.id', ondelete='SET NULL'), nullable=True)
    priority_id = db.Column(db.Integer, db.ForeignKey('priorities.id', ondelete='SET NULL'), nullable=True)
    status_id = db.Column(db.Integer, db.ForeignKey('statuses.id', ondelete='SET NULL'), nullable=True)

    orig_file = db.Column(db.String(255), nullable=True)
    file_link = db.Column(db.String(255), nullable=True)

    waiting_customer_since = db.Column(db.DateTime, nullable=True)
    inactive_reminder_sent = db.Column(
        db.Boolean,
        default=False,
        nullable=False
    )
    unassigned_15min_sent = db.Column(
        db.Boolean,
        default=False,
        nullable=False
    )

    unassigned_30min_sent = db.Column(
        db.Boolean,
        default=False,
        nullable=False
    )

    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())
    updated_at = db.Column(db.DateTime(timezone=True), onupdate=func.now())
    __table_args__ = (
        db.Index("idx_ticket_author_status", "author_id", "status_id"),
        db.Index("idx_ticket_owner_status", "owner_id", "status_id"),
        db.Index("idx_ticket_created_at", "created_at"),
    )

    # Relationships
    comments = db.relationship(
        'Comment',
        backref='ticket_comment',
        cascade='all, delete-orphan',
        lazy=True
    )

    notifications = db.relationship(
        'Notification',
        back_populates='ticket_notification',
        cascade='all, delete-orphan',
        lazy=True
    )

    def __init__(
        self,
        number,
        subject,
        body,
        author_id,
        owner_id,
        category_id,
        priority_id,
        status_id,
        orig_file,
        file_link
    ):
        self.number = number
        self.subject = subject
        self.body = body

        self.author_id = author_id
        self.owner_id = owner_id

        self.category_id = category_id
        self.priority_id = priority_id
        self.status_id = status_id

        self.orig_file = orig_file
        self.file_link = file_link


class Category(db.Model):
	__tablename__ = 'categories'

	id = db.Column(db.Integer, primary_key=True)
	category = db.Column(db.String(255), nullable=False)
	
	created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())
	updated_at = db.Column(db.DateTime(timezone=True), onupdate=func.now())

	# Relationship
	tickets = db.relationship('Ticket', backref='category', passive_deletes=True, lazy=True)

	def __init__(self, category):
		self.category = category

@event.listens_for(Category.__table__, 'after_create')
def create_categories(*args, **kwargs):
	db.session.add(Category(category='Help and support'))
	db.session.commit()

class Priority(db.Model):
	__tablename__ = 'priorities'

	id = db.Column(db.Integer, primary_key=True)
	priority = db.Column(db.String(255), nullable=False)
	
	created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())
	updated_at = db.Column(db.DateTime(timezone=True), onupdate=func.now())

	# Relationship
	tickets = db.relationship('Ticket', backref='priority', passive_deletes=True, lazy=True)

	def __init__(self, priority):
		self.priority = priority

@event.listens_for(Priority.__table__, 'after_create')
def create_priorities(*args, **kwargs):
	db.session.add(Priority(priority='Low'))
	db.session.add(Priority(priority='Medium'))
	db.session.add(Priority(priority='High'))
	db.session.add(Priority(priority='Urgent'))
	db.session.commit()

class Status(db.Model):
	__tablename__ = 'statuses'

	id = db.Column(db.Integer, primary_key=True)
	status = db.Column(db.String(255), nullable=False)
	
	created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())

	# Relationship
	tickets = db.relationship('Ticket', backref='status', passive_deletes=True, lazy=True)

	def __init__(self, status):
		self.status = status

@event.listens_for(Status.__table__, 'after_create')
def create_statuses(*args, **kwargs):
    db.session.add(Status(status='Open'))
    db.session.add(Status(status='Solved'))
    db.session.add(Status(status='Pending'))
    db.session.add(Status(status='Closed'))
    db.session.add(Status(status='Escalated'))
    db.session.add(Status(status='Waiting For Customer'))
    db.session.commit()


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)

    message = db.Column(db.String(255), nullable=False)

    receiver_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    ticket_id = db.Column(db.Integer, db.ForeignKey("tickets.id"), nullable=True)
    agent_report_id = db.Column(db.Integer, db.ForeignKey("agent_reports.id"), nullable=True)

    notification_type = db.Column(db.String(80), default="general", nullable=False)
    receiver_role = db.Column(db.String(50), default="", nullable=False)

    title = db.Column(db.String(255), default="", nullable=False)
    url = db.Column(db.String(500), default="#", nullable=False)

    seen = db.Column(db.Boolean, default=False, nullable=False)
    opened = db.Column(db.Boolean, default=False, nullable=False)

    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())
    
    __table_args__ = (
        db.Index("idx_notification_receiver_seen", "receiver_id", "seen"),
        db.Index("idx_notification_receiver_created", "receiver_id", "created_at"),
    )

    ticket_notification = db.relationship(
        "Ticket",
        foreign_keys=[ticket_id],
        back_populates="notifications"
    )

    agent_report_notification = db.relationship(
        "AgentReport",
        foreign_keys=[agent_report_id]
    )

    def __init__(
        self,
        message,
        receiver_id,
        sender_id=None,
        ticket_id=None,
        agent_report_id=None,
        notification_type="general",
        receiver_role="",
        title="",
        url="#",
        seen=False,
        opened=False
    ):
        self.message = message
        self.receiver_id = receiver_id
        self.sender_id = sender_id
        self.ticket_id = ticket_id
        self.agent_report_id = agent_report_id
        self.notification_type = notification_type
        self.receiver_role = receiver_role
        self.title = title
        self.url = url
        self.seen = seen
        self.opened = opened

    @classmethod
    def send_notification(cls, **kw):
        receiver = User.query.get(kw.get("receiver_id"))
        sender = User.query.get(kw.get("sender_id"))
        if not receiver:
            return None

        if receiver and not kw.get("receiver_role"):
            kw["receiver_role"] = receiver.role

        obj = cls(**kw)

        db.session.add(obj)
        db.session.commit()

        try:
            from app.socketio_ext import socketio

            ticket_number = ""
            item_type = obj.notification_type or "general"
            title = obj.title or "Notification"
            url = obj.url or "#"

            if obj.ticket_notification:
                ticket_number = obj.ticket_notification.number

            if url == "#" and obj.ticket_id:
                if receiver.role == "Administrator":
                    url = f"/admin/notification/open/{obj.id}"
                elif receiver.role == "Agent":
                    url = f"/agent/notification/open/{obj.id}"
                else:
                    url = f"/customer/notification/open/{obj.id}"

            if obj.agent_report_id:
                if receiver.role == "Administrator":
                    url = f"/admin/notification/open/{obj.id}"
                elif receiver.role == "Agent":
                    url = f"/agent/notification/open/{obj.id}"
                elif receiver.role == "Customer":
                    url = f"/customer/notification/open/{obj.id}"

            if url == "#" and receiver:
                if receiver.role == "Administrator":
                    url = f"/admin/notification/open/{obj.id}"
                elif receiver.role == "Agent":
                    url = f"/agent/notification/open/{obj.id}"
                elif receiver.role == "Customer":
                    url = f"/customer/notification/open/{obj.id}"

            obj.url = url
            db.session.commit()

            socketio.emit(
                "new_notification",
                {
                    "notification_id": obj.id,
                    "receiver_id": obj.receiver_id,
                    "receiver_role": obj.receiver_role,
                    "sender": sender.name if sender else "System",
                    "message": obj.message,
                    "title": title,
                    "ticket_id": obj.ticket_id,
                    "ticket_number": ticket_number,
                    "agent_report_id": obj.agent_report_id,
                    "item_type": item_type,
                    "notification_type": obj.notification_type,
                    "url": url,
                    "created_at": obj.created_at.strftime("%d %b %Y %H:%M") if obj.created_at else ""
                },
                room=f"user_{obj.receiver_id}"
            )

            socketio.emit(
                "notification_updated",
                {
                    "receiver_id": obj.receiver_id,
                    "receiver_role": obj.receiver_role,
                    "notification_type": obj.notification_type
                },
                room=f"user_{obj.receiver_id}"
            )

        except Exception as e:
            print("LIVE NOTIFICATION ERROR:", e)

        return obj

class ChatbotSetting(db.Model):
    __tablename__ = "chatbot_settings"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    ai_enabled = db.Column(
        db.Boolean,
        default=True,
        nullable=False
    )

    fallback_message = db.Column(
        db.Text,
        nullable=False,
        default="Our support team is currently unavailable. Please create a support ticket."
    )

    auto_escalation_enabled = db.Column(
        db.Boolean,
        default=True,
        nullable=False
    )

    escalation_keywords = db.Column(
        db.Text,
        default="angry,refund,complaint,manager,lawyer,cancel"
    )
    chatbot_tone = db.Column(
        db.String(50),
        default="Professional",
        nullable=False
    )

    response_length = db.Column(
        db.String(50),
        default="Medium",
        nullable=False
    )

    confidence_threshold = db.Column(
        db.Integer,
        default=70,
        nullable=False
    )

    system_prompt = db.Column(
        db.Text,
        nullable=True
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )
    
class FAQ(db.Model):
    __tablename__ = "faqs"

    id = db.Column(db.Integer, primary_key=True)

    question = db.Column(
        db.String(255),
        nullable=False
    )

    answer = db.Column(
        db.Text,
        nullable=False
    )

    category_id = db.Column(
        db.Integer,
        db.ForeignKey('categories.id', ondelete='SET NULL'),
        nullable=True
    )

    tags = db.Column(
        db.String(255),
        nullable=True
    )

    is_active = db.Column(
        db.Boolean,
        default=True
    )
    view_count = db.Column(
        db.Integer,
        default=0,
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    category = db.relationship(
        'Category',
        backref='faqs',
        lazy=True
    )

class ChatMessage(db.Model):
    __tablename__ = "chat_messages"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey("tickets.id", ondelete="SET NULL"), nullable=True)
    role = db.Column(db.String(20), nullable=False)
    message = db.Column(db.Text, nullable=False)

    faq_matched = db.Column(db.Boolean, default=False)
    ai_used = db.Column(db.Boolean, default=False)
    escalated = db.Column(db.Boolean, default=False)
    guest_user = db.Column(db.Boolean, default=False)
    customer_visible = db.Column(
        db.Boolean,
        default=True,
        nullable=False
    )
    
    resolution_status = db.Column(
        db.String(50),
        default="Pending",
        nullable=False
    )
    review_status = db.Column(
        db.String(50),
        default="Pending",
        nullable=False
    )

    reviewed_by_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=True
    )

    reviewed_at = db.Column(
        db.DateTime,
        nullable=True
    )

    reviewed_by = db.relationship(
        "User",
        foreign_keys=[reviewed_by_id]
    )

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.Index("idx_chat_user_visible", "user_id", "customer_visible"),
        db.Index("idx_chat_user_resolution", "user_id", "resolution_status"),
        db.Index("idx_chat_ticket", "ticket_id"),
    )

    user = db.relationship("User", foreign_keys=[user_id], backref="chat_messages")

    ticket = db.relationship(
        "Ticket",
        foreign_keys=[ticket_id],
        backref="chat_messages"
    )

class AgentReport(db.Model):
    __tablename__ = "agent_reports"

    id = db.Column(db.Integer, primary_key=True)

    report_type = db.Column(db.String(50), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    category = db.Column(db.String(100), nullable=False)
    severity = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(50), default="Open", nullable=False)

    orig_file = db.Column(db.String(255), nullable=True)
    file_link = db.Column(db.String(255), nullable=True)

    reported_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    reported_by = db.relationship("User", backref="agent_reports")
    

class KnowledgeArticle(db.Model):
    __tablename__ = "knowledge_articles"

    id = db.Column(db.Integer, primary_key=True)

    title = db.Column(db.String(255), nullable=False)

    content = db.Column(db.Text, nullable=False)

    category_id = db.Column(
        db.Integer,
        db.ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True
    )

    tags = db.Column(db.String(255), nullable=True)

    is_active = db.Column(db.Boolean, default=True, nullable=False)
    view_count = db.Column(
        db.Integer,
        default=0,
        nullable=False
    )

    created_by_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=True
    )

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    category = db.relationship(
        "Category",
        backref="knowledge_articles",
        lazy=True
    )

    created_by = db.relationship(
        "User",
        foreign_keys=[created_by_id]
    )
    
class AgentSolution(db.Model):
    __tablename__ = "agent_solutions"

    id = db.Column(db.Integer, primary_key=True)

    title = db.Column(
        db.String(255),
        nullable=False
    )

    solution = db.Column(
        db.Text,
        nullable=False
    )

    category_id = db.Column(
        db.Integer,
        db.ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True
    )

    submitted_by_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=True
    )

    ticket_id = db.Column(
        db.Integer,
        db.ForeignKey("tickets.id", ondelete="SET NULL"),
        nullable=True,
        unique=True
    )

    tags = db.Column(
        db.String(255),
        nullable=True
    )

    status = db.Column(
        db.String(50),
        default="Pending"
    )

    view_count = db.Column(
        db.Integer,
        default=0
    )

    reuse_count = db.Column(
        db.Integer,
        default=0
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    category = db.relationship(
        "Category",
        backref="agent_solutions"
    )

    submitted_by = db.relationship(
        "User",
        foreign_keys=[submitted_by_id]
    )

    ticket = db.relationship(
        "Ticket"
    )
    
class Comment(db.Model):
    __tablename__ = 'comments'

    id = db.Column(db.Integer, primary_key=True)
    comment = db.Column(db.Text, nullable=False)

    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    ticket_id = db.Column(db.Integer, db.ForeignKey('tickets.id'), nullable=False)

    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        db.Index("idx_comment_ticket_created", "ticket_id", "created_at"),
    )

    def __init__(self, comment, author_id, ticket_id):
        self.comment = comment
        self.author_id = author_id
        self.ticket_id = ticket_id

    
class CustomerSatisfaction(db.Model):
    __tablename__ = "customer_satisfaction"

    id = db.Column(db.Integer, primary_key=True)

    ticket_id = db.Column(
        db.Integer,
        db.ForeignKey("tickets.id", ondelete="CASCADE"),
        nullable=False
    )

    customer_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )

    rating = db.Column(
        db.Integer,
        nullable=False
    )

    feedback = db.Column(
        db.Text,
        nullable=True
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )
    
    __table_args__ = (
        db.UniqueConstraint("ticket_id", "customer_id", name="uq_ticket_customer_rating"),
    )

    ticket = db.relationship(
        "Ticket",
        backref="satisfaction_rating"
    )

    customer = db.relationship(
        "User",
        foreign_keys=[customer_id]
    )

class SystemEvent(db.Model):
    __tablename__ = "system_events"

    id = db.Column(db.Integer, primary_key=True)

    event_type = db.Column(
        db.String(100),
        nullable=False
    )

    severity = db.Column(
        db.String(50),
        default="Info",
        nullable=False
    )

    message = db.Column(
        db.Text,
        nullable=False
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=True
    )

    related_ticket_id = db.Column(
        db.Integer,
        db.ForeignKey("tickets.id"),
        nullable=True
    )
    

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    user = db.relationship(
        "User",
        foreign_keys=[user_id]
    )

    ticket = db.relationship(
        "Ticket",
        foreign_keys=[related_ticket_id]
    )


class MaintenanceSetting(db.Model):
    __tablename__ = "maintenance_settings"

    id = db.Column(db.Integer, primary_key=True)

    enabled = db.Column(
        db.Boolean,
        default=False,
        nullable=False
    )

    title = db.Column(
        db.String(255),
        default="System Maintenance",
        nullable=False
    )

    message = db.Column(
        db.Text,
        default="The chatbot is currently under maintenance. Please try again later or create a support ticket.",
        nullable=False
    )

    start_time = db.Column(
        db.DateTime,
        nullable=True
    )

    end_time = db.Column(
        db.DateTime,
        nullable=True
    )

    allow_ticket_creation = db.Column(
        db.Boolean,
        default=True,
        nullable=False
    )

    updated_by_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=True
    )

    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    updated_by = db.relationship(
        "User",
        foreign_keys=[updated_by_id]
    )