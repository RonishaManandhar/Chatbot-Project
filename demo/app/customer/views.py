
from flask import Blueprint, current_app, render_template as _render, send_file, redirect, request, url_for, flash, jsonify, session
from flask_login import current_user
from flask_socketio import join_room
from app.socketio_ext import socketio
from openai import OpenAI
from app.services.ai_service import ask_chatgpt
import os
import datetime
import uuid
from werkzeug.utils import secure_filename
from app.services.email_service import (
    send_password_changed_email,
    send_satisfaction_email,
    send_ticket_closed_email,
    send_ticket_created_email,
    send_ticket_deleted_email,
    send_ticket_escalated_email,
    send_ticket_reopened_email
)
from flask import (
    current_app,
    flash,
    redirect,
    request,
    url_for
)
import json

from sqlalchemy import desc, or_, func
from werkzeug.utils import secure_filename
from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from app.exts import db, csrf
from app.customer.forms import ChangeEmailForm, TicketForm, UpdateTicketForm, CommentForm, ChangeProfileForm, ChangePasswordForm
from app.models import (
    User,
    Ticket,
    Comment,
    Notification,
    FAQ,
    ChatMessage,
    ChatSession,
    Category,
    Priority,
    Status,
    ChatbotSetting,
    KnowledgeArticle,
    CustomerSatisfaction,
    MaintenanceSetting,
    SystemEvent,
    EmailPreference
)
from app.utils.generate_digits import random_numbers
from app.utils.authorized_role import login_required


customer_blueprint = Blueprint("customer", __name__)
path = os.getcwd()
def log_system_event(event_type, message, severity="Info", user_id=None, ticket_id=None):
    try:
        event = SystemEvent(
            event_type=event_type,
            severity=severity,
            message=message,
            user_id=user_id,
            related_ticket_id=ticket_id
        )

        db.session.add(event)
        db.session.commit()

        return event

    except Exception as e:
        db.session.rollback()
        print("CUSTOMER SYSTEM EVENT LOG ERROR:", e)
        return None



def save_or_update_rating_message(
    customer_id,
    rating,
    feedback="",
    ticket_id=None,
    session_id=None
):
    message = (
        f"<strong>Customer Satisfaction Rating</strong><br>"
        f"Rating: {rating}/5<br>"
        f"Feedback: {feedback if feedback else 'No feedback provided.'}"
    )

    existing_message = ChatMessage.query.filter(
        ChatMessage.user_id == customer_id,
        ChatMessage.role == "system",
        ChatMessage.message.ilike("%Customer Satisfaction Rating%"),
        ChatMessage.ticket_id == ticket_id,
        ChatMessage.session_id == session_id
    ).first()

    if existing_message:
        existing_message.message = message
        existing_message.resolution_status = "Solved"
        existing_message.customer_visible = True
        existing_message.created_at = datetime.datetime.utcnow()
    else:
        db.session.add(ChatMessage(
            user_id=customer_id,
            session_id=session_id,
            ticket_id=ticket_id,
            role="system",
            message=message,
            resolution_status="Solved",
            customer_visible=True,
            faq_matched=False,
            ai_used=False,
            escalated=False
        ))

# ============================================================
# TEMPLATE HELPER
# ============================================================

def render_template(*args, **kwargs):
    year = datetime.date.today().year

    if not current_user.is_authenticated:
        return _render(*args, **kwargs, notifications=[], year=year)

    notifications = (
        Notification.query
        .filter(Notification.receiver_id == current_user.id)
        .filter(Notification.seen == False)
        .order_by(desc(Notification.created_at))
        .all()
    )

    return _render(*args, **kwargs, notifications=notifications, year=year)


# ============================================================
# STATUS HELPERS
# ============================================================
def get_active_maintenance():
    setting = MaintenanceSetting.query.first()

    if not setting or not setting.enabled:
        return None

    now = datetime.datetime.utcnow()

    if setting.start_time and now < setting.start_time:
        return None

    if setting.end_time and now > setting.end_time:
        return None

    return setting

def get_status_id(status_name, fallback=None):
    row = Status.query.filter_by(status=status_name).first()
    return row.id if row else fallback

def get_waiting_customer_status_id():
    return get_status_id("Waiting For Customer", None)

def get_open_status_id():
    return get_status_id("Open", 1)


def get_pending_status_id():
    return get_status_id("Pending", 3)


def get_closed_status_id():
    return get_status_id("Closed", 4)

def get_escalated_status_id():
    return get_status_id("Escalated", None)

def get_category_by_name(name, fallback_id=1):
    if not name:
        return fallback_id

    category = Category.query.filter(
        Category.category.ilike(name)
    ).first()

    return category.id if category else fallback_id


def get_priority_by_name(name, fallback_id=2):
    if not name:
        return fallback_id

    priority = Priority.query.filter(
        Priority.priority.ilike(name)
    ).first()

    return priority.id if priority else fallback_id



def get_active_ticket_for_user(user_id):
    return None

def auto_close_waiting_customer_tickets():
    """
    Automatically close tickets that have remained in
    'Waiting For Customer' for at least 48 hours.

    For every ticket automatically closed:

        1. Change the ticket status to Closed.
        2. Add a system comment.
        3. Hide the old customer chat.
        4. Commit the ticket closure.
        5. Send the ticket-closed email.
        6. Send the satisfaction-rating email.
        7. Record both email attempts through EmailLog.
        8. Create a SystemEvent record.
        9. Publish real-time Socket.IO updates.
    """

    waiting_id = get_waiting_customer_status_id()
    closed_id = get_closed_status_id()

    if not waiting_id or not closed_id:
        return

    now = datetime.datetime.utcnow()

    tickets = (
        Ticket.query
        .filter(Ticket.status_id == waiting_id)
        .all()
    )

    for ticket in tickets:
        if not ticket.waiting_customer_since:
            if ticket.updated_at:
                ticket.waiting_customer_since = (
                    ticket.updated_at.replace(
                        tzinfo=None
                    )
                )

            elif ticket.created_at:
                ticket.waiting_customer_since = (
                    ticket.created_at.replace(
                        tzinfo=None
                    )
                )

            else:
                ticket.waiting_customer_since = now

        waiting_since = ticket.waiting_customer_since

        if waiting_since.tzinfo is not None:
            waiting_since = waiting_since.replace(
                tzinfo=None
            )

        waiting_hours = (
            now - waiting_since
        ).total_seconds() / 3600

        if waiting_hours < 48:
            continue

        # ----------------------------------------------------
        # CLOSE TICKET
        # ----------------------------------------------------

        ticket.status_id = closed_id
        ticket.waiting_customer_since = None
        ticket.inactive_reminder_sent = False

        close_message = (
            "Ticket automatically closed because the customer "
            "did not respond within 48 hours."
        )

        close_comment = Comment(
            comment=close_message,
            author_id=(
                ticket.owner_id
                or ticket.author_id
            ),
            ticket_id=ticket.id
        )

        db.session.add(close_comment)

        ChatMessage.query.filter(
            ChatMessage.user_id == ticket.author_id
        ).update({
            "customer_visible": False
        })

        # Commit before rendering email templates so the ticket
        # has its final Closed status.
        db.session.commit()

        # Refresh relationships and status values after commit.
        db.session.refresh(ticket)

        # ----------------------------------------------------
        # SEND CLOSED AND SATISFACTION EMAILS
        # ----------------------------------------------------

        customer = ticket.author

        closed_email_sent = False
        satisfaction_email_sent = False

        if customer and customer.email:
            closed_email_sent = send_ticket_closed_email(
                customer,
                ticket
            )

            if not closed_email_sent:
                current_app.logger.error(
                    "Automatic ticket-closed email failed "
                    "for ticket_id=%s customer_id=%s",
                    ticket.id,
                    ticket.author_id
                )

            satisfaction_email_sent = send_satisfaction_email(
                customer,
                ticket
            )

            if not satisfaction_email_sent:
                current_app.logger.error(
                    "Automatic satisfaction email failed "
                    "for ticket_id=%s customer_id=%s",
                    ticket.id,
                    ticket.author_id
                )

        # ----------------------------------------------------
        # SYSTEM EVENT LOG
        # ----------------------------------------------------

        log_system_event(
            event_type="Ticket Automatically Closed",
            severity="Info",
            message=(
                f"Ticket #{ticket.number} was automatically "
                "closed after 48 hours without a customer reply. "
                f"Closed email result: {closed_email_sent}. "
                f"Satisfaction email result: "
                f"{satisfaction_email_sent}."
            ),
            user_id=ticket.author_id,
            ticket_id=ticket.id
        )

        # ----------------------------------------------------
        # REAL-TIME UPDATES
        # ----------------------------------------------------

        payload = {
            **serialize_ticket(ticket),
            "message": close_message,
            "closed_email_sent": closed_email_sent,
            "satisfaction_email_sent": (
                satisfaction_email_sent
            )
        }

        socketio.emit(
            "new_comment",
            {
                **payload,
                "comment_id": close_comment.id,
                "sender_role": (
                    close_comment.user.role
                    if close_comment.user
                    else "System"
                ),
                "sender_name": (
                    close_comment.user.name
                    if close_comment.user
                    else "System"
                ),
                "author_id": close_comment.author_id,
                "is_attachment": False,
                "created_at": (
                    close_comment.created_at.strftime(
                        "%d %b %Y, %H:%M %p"
                    )
                    if close_comment.created_at
                    else ""
                )
            },
            room=f"ticket_{ticket.id}"
        )

        socketio.emit(
            "ticket_closed",
            payload,
            room=f"ticket_{ticket.id}"
        )

        socketio.emit(
            "global_ticket_updated",
            payload
        )

        socketio.emit(
            "sidebar_counts_updated",
            payload
        )

        socketio.emit(
            "notification_updated",
            payload
        )

        socketio.emit(
            "analytics_updated",
            payload
        )

        emit_customer_refresh(
            ticket.author_id,
            "ticket_auto_closed"
        )


# ============================================================
# SERIALIZERS
# ============================================================

def serialize_ticket(ticket):
    if not ticket:
        return {}

    return {
        "ticket_id": ticket.id,
        "ticket_number": ticket.number,
        "subject": ticket.subject,
        "status": ticket.status.status if ticket.status else "",
        "status_id": ticket.status_id,
        "owner": ticket.owner.name if ticket.owner else None,
        "owner_id": ticket.owner_id,
        "author": ticket.author.name if ticket.author else "",
        "author_id": ticket.author_id,
        "category": ticket.category.category if ticket.category else "",
        "priority": ticket.priority.priority if ticket.priority else "",
        "created_at": ticket.created_at.strftime("%d %b %Y %H:%M") if ticket.created_at else "",
        "updated_at": ticket.updated_at.strftime("%d %b %Y %H:%M") if ticket.updated_at else ""
    }


def serialize_comment(comment):
    return {
        "id": comment.id,
        "message": comment.comment,
        "author": comment.user.name,
        "author_id": comment.author_id,
        "role": comment.user.role,
        "created_at": comment.created_at.strftime("%d %b %Y %H:%M") if comment.created_at else ""
    }


def serialize_chat_message(msg):
    if not msg:
        return None

    return {
        "id": msg.id,
        "role": msg.role,
        "message": msg.message,
        "faq_matched": msg.faq_matched,
        "ai_used": msg.ai_used,
        "escalated": msg.escalated,
        "resolution_status": msg.resolution_status,
        "created_at": msg.created_at.strftime("%d %b %Y %H:%M") if msg.created_at else ""
    }
def serialize_chat_session(chat_session):
    if not chat_session:
        return None

    ticket = (
        chat_session.ticket
        if chat_session.ticket_id
        else None
    )

    ticket_status = (
        ticket.status.status
        if ticket and ticket.status
        else ""
    )

    try:
        triage_data = json.loads(
            chat_session.triage_data or "{}"
        )

        if not isinstance(triage_data, dict):
            triage_data = {}

    except (TypeError, ValueError, json.JSONDecodeError):
        triage_data = {}

    current_stage = (
        chat_session.current_stage
        or "triage"
    )

    # A closed ticket always opens read-only.
    if ticket_status.lower() == "closed":
        current_stage = "closed"

    read_only = current_stage in {
        "solved",
        "closed"
    }

    can_type = False

    if current_stage == "triage":
        can_type = True

    elif (
        current_stage == "ticket_created"
        and ticket
        and ticket_status.lower() != "closed"
    ):
        can_type = True

    return {
        "id": chat_session.id,
        "title": (
            chat_session.title
            or "New IT Support Chat"
        ),
        "issue_type": (
            chat_session.issue_type
            or ""
        ),
        "status": (
            chat_session.status
            or "Active"
        ),
        "current_stage": current_stage,
        "triage_step": (
            chat_session.triage_step
            or 0
        ),
        "triage_data": triage_data,
        "triage_summary": (
            chat_session.triage_summary
            or ""
        ),
        "ticket_id": chat_session.ticket_id,
        "ticket_number": (
            ticket.number
            if ticket
            else None
        ),
        "ticket_status": ticket_status,
        "ticket_subject": (
            ticket.subject
            if ticket
            else ""
        ),
        "ticket_priority": (
            ticket.priority.priority
            if ticket and ticket.priority
            else ""
        ),
        "ticket_category": (
            ticket.category.category
            if ticket and ticket.category
            else ""
        ),
        "read_only": read_only,
        "can_type": can_type,
        "created_at": (
            chat_session.created_at.strftime(
                "%d %b %Y %H:%M"
            )
            if chat_session.created_at
            else ""
        ),
        "updated_at": (
            chat_session.updated_at.strftime(
                "%d %b %Y %H:%M"
            )
            if chat_session.updated_at
            else ""
        )
    }

# ============================================================
# GLOBAL SOCKET HELPERS
# ============================================================

def emit_global_event(event_name, ticket=None, message=None):
    payload = {
        "event": event_name,
        "message": message or ""
    }

    if ticket:
        payload.update(serialize_ticket(ticket))

    socketio.emit(event_name, payload)
    socketio.emit("global_ticket_updated", payload)
    socketio.emit("sidebar_counts_updated", payload)
    socketio.emit("notification_updated", payload)
    socketio.emit("analytics_updated", payload)


def emit_customer_refresh(user_id, reason="updated"):
    if not user_id:
        return

    socketio.emit(
        "customer_live_refresh",
        {
            "user_id": user_id,
            "reason": reason
        },
        room=f"user_{user_id}"
    )


def emit_customer_chat_event(user_id, event_name, payload):
    if not user_id:
        return

    payload["user_id"] = user_id

    socketio.emit(
        event_name,
        payload,
        room=f"user_{user_id}"
    )


def emit_ticket_comment(ticket, comment, is_attachment=False):
    payload = {
        **serialize_ticket(ticket),
        "comment_id": comment.id,
        "message": comment.comment,
        "sender_role": comment.user.role,
        "sender_name": comment.user.name,
        "author_id": comment.author_id,
        "is_attachment": is_attachment,
        "created_at": comment.created_at.strftime("%d %b %Y, %H:%M %p") if comment.created_at else ""
    }

    socketio.emit(
        "new_comment",
        payload,
        room=f"ticket_{ticket.id}"
    )

def emit_ticket_system(ticket, event_name, message):
    payload = {
        **serialize_ticket(ticket),
        "message": message
    }

    # Send ticket-specific event once.
    socketio.emit(
        event_name,
        payload,
        room=f"ticket_{ticket.id}"
    )

    # Silent updates for lists, badges, and analytics.
    socketio.emit("global_ticket_updated", payload)
    socketio.emit("sidebar_counts_updated", payload)
    socketio.emit("notification_updated", payload)
    socketio.emit("analytics_updated", payload)

    if ticket.author_id:
        emit_customer_refresh(
            ticket.author_id,
            event_name
        )


# ============================================================
# NOTIFICATION HELPERS
# ============================================================

def notify_user(message, receiver_id, sender_id, ticket_id):
    try:
        return Notification.send_notification(
            message=message,
            receiver_id=receiver_id,
            sender_id=sender_id,
            ticket_id=ticket_id,
            notification_type="ticket",
            seen=False
        )

    except Exception as e:
        print("NOTIFICATION ERROR:", e)
        return None


def notify_staff(message, sender_id, ticket_id, include_agents=True, include_admins=True):
    roles = []

    if include_agents:
        roles.append("Agent")

    if include_admins:
        roles.append("Administrator")

    if not roles:
        return

    staff_users = User.query.filter(User.role.in_(roles)).all()

    for staff in staff_users:
        if staff.id != sender_id:
            notify_user(
                message=message,
                receiver_id=staff.id,
                sender_id=sender_id,
                ticket_id=ticket_id
            )


# ============================================================
# PAGE ROUTES
# ============================================================

@customer_blueprint.route("/dashboard")
@login_required(role="Customer")
def dashboard():
    auto_close_waiting_customer_tickets()
    user_id = current_user.id

    open_tickets = Ticket.query.filter_by(author_id=user_id, status_id=get_open_status_id()).all()
    solved = Ticket.query.filter_by(author_id=user_id, status_id=get_status_id("Solved", 2)).all()
    pending = Ticket.query.filter_by(author_id=user_id, status_id=get_pending_status_id()).all()
    closed = Ticket.query.filter_by(author_id=user_id, status_id=get_closed_status_id()).all()

    active_ticket = get_active_ticket_for_user(user_id)

    return render_template(
        "customer/dashboard.html",
        open=open_tickets,
        solved=solved,
        pending=pending,
        closed=closed,
        active_ticket=active_ticket
    )


@customer_blueprint.route("/my-tickets", methods=["GET"])
@login_required(role="Customer")
def my_tickets():
    auto_close_waiting_customer_tickets()

    chat_sessions = (
        ChatSession.query
        .filter(ChatSession.user_id == current_user.id)
        .order_by(ChatSession.updated_at.desc(), ChatSession.created_at.desc())
        .all()
    )

    tickets = (
        Ticket.query
        .filter(Ticket.author_id == current_user.id)
        .order_by(desc(Ticket.created_at))
        .all()
    )

    form = TicketForm()

    return render_template(
        "customer/my_tickets.html",
        form=form,
        tickets=tickets,
        chat_sessions=chat_sessions,
        active_ticket=None
    )

@customer_blueprint.route(
    "/view-chat/<int:session_id>",
    methods=["GET"]
)
@login_required(role="Customer")
def view_chat(session_id):
    chat_session = ChatSession.query.filter_by(
        id=session_id,
        user_id=current_user.id
    ).first()

    if not chat_session:
        flash(
            "Chat session not found.",
            "warning"
        )

        return redirect(
            url_for("customer.my_tickets")
        )

    return redirect(
        url_for(
            "customer.chat",
            session_id=chat_session.id
        )
    )
@csrf.exempt
@customer_blueprint.route("/chat/delete/<int:session_id>", methods=["GET", "POST"])
@login_required(role="Customer")
def delete_chat_session_page(session_id):
    chat_session = ChatSession.query.filter_by(
        id=session_id,
        user_id=current_user.id
    ).first()

    if not chat_session:
        flash("Chat session not found.", "warning")
        return redirect(url_for("customer.my_tickets"))

    if chat_session.ticket_id:
        flash("This chat is linked to a support ticket. Please delete the ticket instead.", "warning")
        return redirect(url_for("customer.my_tickets"))

    ChatMessage.query.filter_by(
        session_id=chat_session.id,
        user_id=current_user.id
    ).delete()

    db.session.delete(chat_session)
    db.session.commit()

    flash("Chat session deleted.", "primary")
    return redirect(url_for("customer.my_tickets"))


@customer_blueprint.route(
    "/create-ticket",
    methods=["GET", "POST"]
)
@login_required(role="Customer")
def create_ticket():
    auto_close_waiting_customer_tickets()

    form = TicketForm()

    if form.validate_on_submit():
        file = form.attachment.data
        attachment = None
        original_f = None

        # ----------------------------------------------------
        # SAVE OPTIONAL ATTACHMENT
        # ----------------------------------------------------

        if file and file.filename:
            folder_id = os.path.join(
                path,
                "app",
                "static",
                "uploads",
                "attachments",
                str(current_user.id)
            )

            os.makedirs(
                folder_id,
                exist_ok=True
            )

            original_f = secure_filename(
                file.filename
            )

            _, ext = os.path.splitext(
                original_f
            )

            attachment = secure_filename(
                uuid.uuid4().hex + ext.lower()
            )

            file.save(
                os.path.join(
                    folder_id,
                    attachment
                )
            )

        # ----------------------------------------------------
        # CREATE TICKET
        # ----------------------------------------------------

        ticket = Ticket(
            number=random_numbers(),
            subject=form.subject.data,
            body=form.body.data,
            author_id=current_user.id,
            owner_id=None,
            category_id=int(form.category.data),
            priority_id=Priority.query.first().id,
            status_id=get_open_status_id(),
            orig_file=original_f,
            file_link=attachment
        )

        db.session.add(ticket)
        db.session.flush()

        manual_chat_session = ChatSession(
            user_id=current_user.id,
            ticket_id=ticket.id,
            title=ticket.subject,
            issue_type=(
                ticket.category.category
                if ticket.category
                else "Manual Support Ticket"
            ),
            status="Open",
            current_stage="ticket_created",
            triage_step=0,
            triage_data="{}",
            triage_summary=(
                "This support ticket was created manually "
                "without AI triage."
            )
        )

        db.session.add(manual_chat_session)
        db.session.flush()

        initial_message = ChatMessage(
            user_id=current_user.id,
            session_id=manual_chat_session.id,
            ticket_id=ticket.id,
            role="user",
            message=ticket.body,
            resolution_status="Active",
            customer_visible=True,
            faq_matched=False,
            ai_used=False,
            escalated=True,
            guest_user=False
        )

        db.session.add(initial_message)
        db.session.commit()

        # ----------------------------------------------------
        # SEND TICKET-CREATED EMAIL
        # ----------------------------------------------------

        email_sent = send_ticket_created_email(
            current_user,
            ticket
        )

        if not email_sent:
            current_app.logger.error(
                "Customer ticket-created email failed "
                "for ticket_id=%s user_id=%s",
                ticket.id,
                current_user.id
            )

        # ----------------------------------------------------
        # SYSTEM EVENT
        # ----------------------------------------------------

        log_system_event(
            event_type="Ticket Created",
            severity="Info",
            message=(
                f"Ticket #{ticket.number} was created "
                f"by customer {current_user.email}."
            ),
            user_id=current_user.id,
            ticket_id=ticket.id
        )

        # ----------------------------------------------------
        # NOTIFY STAFF
        # ----------------------------------------------------

        notify_staff(
            message="created a new support ticket",
            sender_id=current_user.id,
            ticket_id=ticket.id
        )

        # ----------------------------------------------------
        # REAL-TIME UPDATE
        # ----------------------------------------------------

        emit_global_event(
            "ticket_created",
            ticket,
            "Customer created a new support ticket."
        )

        if email_sent:
            flash(
                "Ticket has been created. "
                "A confirmation email was sent.",
                "success"
            )
        else:
            flash(
                "Ticket has been created, but the confirmation "
                "email could not be sent.",
                "warning"
            )

        return redirect(
            url_for("customer.my_tickets")
        )

    return render_template(
        "customer/create_ticket.html",
        form=form
    )


@customer_blueprint.route("/view-ticket/<int:id>", methods=["GET", "POST"])
@login_required(role="Customer")
def view_ticket(id):

    ticket = (
        Ticket.query
        .filter(Ticket.author_id == current_user.id)
        .filter_by(id=id)
        .first()
    )

    if not ticket:
        flash("Ticket not found.", "warning")
        return redirect(url_for("customer.my_tickets"))

    comments = (
        Comment.query
        .filter(Comment.ticket_id == id)
        .order_by(Comment.created_at.asc())
        .all()
    )

    form = UpdateTicketForm(category=ticket.category_id)
    comment_form = CommentForm()

    chat_session = ChatSession.query.filter_by(
        ticket_id=ticket.id,
        user_id=current_user.id
    ).first()

    # ====================================================
    # NEW
    # ====================================================
    prefill_rating = request.args.get(
        "rating",
        type=int
    )

    if prefill_rating not in [1, 2, 3, 4, 5]:
        prefill_rating = None
    # ====================================================

    existing_rating = CustomerSatisfaction.query.filter_by(
        ticket_id=ticket.id,
        customer_id=current_user.id
    ).first()

    if not existing_rating and chat_session:
        existing_rating = CustomerSatisfaction.query.filter_by(
            session_id=chat_session.id,
            customer_id=current_user.id
        ).first()

    return render_template(
        "customer/view_ticket.html",
        form=form,
        chat_session=chat_session,
        comment_form=comment_form,
        ticket=ticket,
        comments=comments,
        existing_rating=existing_rating,
        prefill_rating=prefill_rating
    )


@customer_blueprint.route("/comment-ticket/<int:id>", methods=["GET", "POST"])
@login_required(role="Customer")
def comment_ticket(id):
    return redirect(url_for("customer.chat"))


@customer_blueprint.route("/faqs", methods=["GET"])
@login_required(role="Customer")
def faqs():
    categories = Category.query.order_by(Category.category.asc()).all()
    return render_template("customer/faqs.html", categories=categories)


@customer_blueprint.route(
    "/chat",
    methods=["GET"]
)
@login_required(role="Customer")
def chat():
    auto_close_waiting_customer_tickets()

    requested_session_id = request.args.get(
        "session_id",
        type=int
    )

    if requested_session_id:
        chat_session = ChatSession.query.filter_by(
            id=requested_session_id,
            user_id=current_user.id
        ).first()

        if not chat_session:
            flash(
                "The selected chat session could not be found.",
                "warning"
            )

            return redirect(
                url_for("customer.chat")
            )

    return render_template(
        "customer/chat.html",
        requested_session_id=requested_session_id
    )


@customer_blueprint.route("/support-requests", methods=["GET"])
@login_required(role="Customer")
def support_requests():
    return redirect(url_for("customer.chat"))


# ============================================================
# PROFILE / ACCOUNT
# ============================================================

@customer_blueprint.route(
    "/my-profile",
    methods=["GET", "POST"]
)
@login_required(role="Customer")
def my_profile():
    user = db.session.get(
        User,
        current_user.id
    )

    if not user:
        flash(
            "Your account could not be found.",
            "danger"
        )

        return redirect(
            url_for("auth.logout")
        )

    form = ChangeProfileForm()

    if request.method == "GET":
        form.name.data = user.name

    if form.validate_on_submit():
        new_name = (
            form.name.data or ""
        ).strip()

        if not new_name:
            flash(
                "Your name is required.",
                "danger"
            )

            return redirect(
                url_for("customer.my_profile")
            )

        user.name = new_name

        file = form.profile.data

        if file and file.filename:
            os.makedirs(
                current_app.config["PROFILE_DIR"],
                exist_ok=True
            )

            original_filename = secure_filename(
                file.filename
            )

            _, extension = os.path.splitext(
                original_filename
            )

            extension = extension.lower()

            profile_filename = secure_filename(
                f"{user.id}_{uuid.uuid4().hex}{extension}"
            )

            old_image = user.image

            new_image_path = os.path.join(
                current_app.config["PROFILE_DIR"],
                profile_filename
            )

            file.save(
                new_image_path
            )

            user.image = profile_filename

            if (
                old_image
                and old_image != "default-profile.png"
                and old_image != profile_filename
            ):
                old_image_path = os.path.join(
                    current_app.config["PROFILE_DIR"],
                    old_image
                )

                if os.path.isfile(old_image_path):
                    try:
                        os.remove(
                            old_image_path
                        )

                    except OSError:
                        current_app.logger.exception(
                            "Could not remove old customer "
                            "profile image for user_id=%s",
                            user.id
                        )

        try:
            db.session.commit()

        except Exception:
            db.session.rollback()

            current_app.logger.exception(
                "Customer profile update failed "
                "for user_id=%s",
                user.id
            )

            flash(
                "Your profile could not be updated.",
                "danger"
            )

            return redirect(
                url_for("customer.my_profile")
            )

        socketio.emit(
            "profile_updated",
            {
                "user_id": user.id,
                "name": user.name,
                "image": user.image,
                "message": (
                    "Customer profile updated."
                )
            }
        )

        flash(
            "Your profile has been updated.",
            "success"
        )

        return redirect(
            url_for("customer.my_profile")
        )

    return render_template(
        "customer/my_profile.html",
        form=form,
        user=user
    )

@customer_blueprint.route(
    "/change-password",
    methods=["GET", "POST"]
)
@login_required(role="Customer")
def change_password():
    user = db.session.get(
        User,
        current_user.id
    )

    if not user:
        flash(
            "Your account could not be found.",
            "danger"
        )

        return redirect(
            url_for("auth.logout")
        )

    form = ChangePasswordForm()

    if form.validate_on_submit():
        current_password = (
            form.current_password.data or ""
        )

        new_password = (
            form.password.data or ""
        )

        if not check_password_hash(
            user.password,
            current_password
        ):
            flash(
                "Current password is incorrect.",
                "danger"
            )

            return redirect(
                url_for("customer.change_password")
            )

        user.password = generate_password_hash(
            new_password
        )

        user.failed_login_attempts = 0
        user.locked_until = None

        if hasattr(user, "updated_at"):
            user.updated_at = (
                datetime.datetime.utcnow()
            )

        try:
            db.session.commit()

        except Exception:
            db.session.rollback()

            current_app.logger.exception(
                "Customer password update failed "
                "for user_id=%s",
                user.id
            )

            flash(
                "The password could not be updated.",
                "danger"
            )

            return redirect(
                url_for("customer.change_password")
            )

        socketio.emit(
            "password_updated",
            {
                "user_id": user.id,
                "message": (
                    "Customer password updated."
                )
            }
        )

        flash(
            "Password updated successfully.",
            "success"
        )

        return redirect(
            url_for("customer.change_password")
        )

    return render_template(
        "customer/change_password.html",
        form=form
    )


@customer_blueprint.route(
    "/change-email",
    methods=["GET", "POST"]
)
@login_required(role="Customer")
def change_email():
    form = ChangeEmailForm()

    if request.method == "GET":
        form.email.data = (
            current_user.email
        )

    if form.validate_on_submit():
        password = (
            form.password.data or ""
        )

        if not check_password_hash(
            current_user.password,
            password
        ):
            flash(
                "Password incorrect.",
                "danger"
            )

            return redirect(
                url_for("customer.change_email")
            )

        new_email = (
            form.email.data or ""
        ).strip().lower()

        existing = (
            User.query
            .filter(
                func.lower(User.email)
                == new_email,
                User.id != current_user.id
            )
            .first()
        )

        if existing:
            flash(
                "Email already exists.",
                "danger"
            )

            return redirect(
                url_for("customer.change_email")
            )

        current_user.email = new_email

        try:
            db.session.commit()

        except Exception:
            db.session.rollback()

            current_app.logger.exception(
                "Customer email update failed "
                "for user_id=%s",
                current_user.id
            )

            flash(
                "Your email could not be updated.",
                "danger"
            )

            return redirect(
                url_for("customer.change_email")
            )

        flash(
            "Email updated.",
            "success"
        )

        return redirect(
            url_for("customer.my_profile")
        )

    return render_template(
        "customer/change_email.html",
        form=form
    )


# ============================================================
# NOTIFICATIONS
# ============================================================

@customer_blueprint.route("/notifications", methods=["GET"])
@login_required(role="Customer")
def notifications():
    my_notifications = (
        Notification.query
        .filter(Notification.receiver_id == current_user.id)
        .order_by(desc(Notification.created_at))
        .all()
    )

    return render_template("customer/notifications.html", my_notifications=my_notifications)


@customer_blueprint.route("/read-notification/<int:tid>/<int:nid>", methods=["GET"])
@login_required(role="Customer")
def read_notification(tid, nid):
    return redirect(url_for("customer.open_notification", nid=nid))


@customer_blueprint.route("/notifications/mark-all-read", methods=["POST"])
@login_required(role="Customer")
def mark_all_notifications_read():
    Notification.query.filter(
        Notification.receiver_id == current_user.id,
        Notification.seen == False
    ).update({"seen": True})

    db.session.commit()

    socketio.emit(
        "notification_read",
        {
            "receiver_id": current_user.id,
            "notification_id": None
        },
        room=f"user_{current_user.id}"
    )

    socketio.emit(
        "notification_updated",
        {
            "receiver_id": current_user.id
        }
    )

    socketio.emit(
        "sidebar_counts_updated",
        {
            "receiver_id": current_user.id
        }
    )

    flash("All notifications marked as read.", "primary")
    return redirect(url_for("customer.notifications"))


# ============================================================
# DOWNLOAD / DELETE
# ============================================================

@customer_blueprint.route("/download/attachment/<int:id>/<filename>")
def download_attachment(id, filename):
    folder_id = os.path.join(path, "app/static/uploads/attachments", str(id))
    location = os.path.join(folder_id, filename)
    return send_file(location, as_attachment=True)


@customer_blueprint.route(
    "/ticket/delete/<int:uid>/<int:tid>",
    methods=["GET", "POST"]
)
@login_required(role="Customer")
def delete_ticket(uid, tid):
    ticket = Ticket.query.get_or_404(tid)

    if ticket.author_id != current_user.id:
        flash(
            "Unauthorized access.",
            "danger"
        )

        return redirect(
            url_for("customer.my_tickets")
        )

    if request.method == "POST":
        # Save all required values before deleting the ticket.
        ticket_id = ticket.id
        ticket_number = ticket.number
        ticket_subject = ticket.subject or "No subject"

        customer = ticket.author

        # ----------------------------------------------------
        # SEND DELETION EMAIL BEFORE DATABASE DELETE
        # ----------------------------------------------------

        email_sent = False

        if customer and customer.email:
            email_sent = send_ticket_deleted_email(
                customer,
                ticket_number=str(ticket_number),
                ticket_subject=ticket_subject,
                deleted_by=current_user.name,
                deleted_ticket_id=None
            )

            if not email_sent:
                current_app.logger.error(
                    "Customer ticket-deleted email failed "
                    "for ticket_id=%s customer_id=%s",
                    ticket.id,
                    ticket.author_id
                )

        # ----------------------------------------------------
        # DELETE PHYSICAL ATTACHMENT
        # ----------------------------------------------------

        if ticket.file_link:
            folder_id = os.path.join(
                path,
                "app",
                "static",
                "uploads",
                "attachments",
                str(uid)
            )

            file_path = os.path.join(
                folder_id,
                ticket.file_link
            )

            if os.path.exists(file_path):
                try:
                    os.remove(file_path)

                except OSError as error:
                    current_app.logger.exception(
                        "Could not delete attachment for "
                        "ticket_id=%s: %s",
                        ticket.id,
                        error
                    )

        # ----------------------------------------------------
        # DELETE DATABASE TICKET
        # ----------------------------------------------------
        SystemEvent.query.filter_by(
            related_ticket_id=ticket.id
        ).delete(
            synchronize_session=False
        )

        db.session.delete(ticket)
        db.session.commit()

        log_system_event(
            event_type="Ticket Deleted",
            severity="Warning",
            message=(
                f"Ticket #{ticket_number} was deleted "
                f"by customer {current_user.email}."
            ),
            user_id=current_user.id,
            ticket_id=None
        )

        payload = {
            "ticket_id": ticket_id,
            "ticket_number": ticket_number,
            "message": "Ticket deleted by customer."
        }

        socketio.emit(
            "ticket_deleted",
            payload
        )

        socketio.emit(
            "global_ticket_updated",
            payload
        )

        socketio.emit(
            "sidebar_counts_updated",
            payload
        )

        socketio.emit(
            "notification_updated",
            payload
        )

        socketio.emit(
            "analytics_updated",
            payload
        )

        emit_customer_refresh(
            current_user.id,
            "ticket_deleted"
        )

        if email_sent:
            flash(
                "Ticket has been deleted. "
                "A confirmation email was sent.",
                "success"
            )
        else:
            flash(
                "Ticket has been deleted, but the confirmation "
                "email could not be sent.",
                "warning"
            )

        return redirect(
            url_for("customer.my_tickets")
        )

    return redirect(
        url_for(
            "customer.view_ticket",
            id=tid
        )
    )

@customer_blueprint.route("/ticket/rate/<int:ticket_id>", methods=["POST"])
@login_required(role="Customer")
def rate_ticket(ticket_id):
    ticket = Ticket.query.filter_by(
        id=ticket_id,
        author_id=current_user.id
    ).first()

    if not ticket:
        flash("Ticket not found.", "warning")
        return redirect(url_for("customer.my_tickets"))

    rating = request.form.get("rating", type=int)
    feedback = (request.form.get("feedback") or "").strip()

    if not rating or rating < 1 or rating > 5:
        flash("Please select a rating between 1 and 5.", "warning")
        return redirect(url_for("customer.view_ticket", id=ticket.id))

    chat_session = ChatSession.query.filter_by(
        ticket_id=ticket.id,
        user_id=current_user.id
    ).first()

    existing_rating = CustomerSatisfaction.query.filter_by(
        ticket_id=ticket.id,
        customer_id=current_user.id
    ).first()

    if not existing_rating and chat_session:
        existing_rating = CustomerSatisfaction.query.filter_by(
            session_id=chat_session.id,
            customer_id=current_user.id
        ).first()

    if existing_rating:
        existing_rating.ticket_id = ticket.id
        existing_rating.session_id = chat_session.id if chat_session else None
        existing_rating.rating = rating
        existing_rating.feedback = feedback
        existing_rating.updated_at = datetime.datetime.utcnow()
    else:
        existing_rating = CustomerSatisfaction(
            ticket_id=ticket.id,
            session_id=chat_session.id if chat_session else None,
            customer_id=current_user.id,
            rating=rating,
            feedback=feedback
        )
        db.session.add(existing_rating)

    save_or_update_rating_message(
        customer_id=current_user.id,
        rating=rating,
        feedback=feedback,
        ticket_id=ticket.id,
        session_id=chat_session.id if chat_session else None
    )

    db.session.commit()

    flash("Thank you. Your rating has been saved.", "success")
    return redirect(url_for("customer.view_ticket", id=ticket.id))

@csrf.exempt
@customer_blueprint.route(
    "/api/ticket/rate/<int:ticket_id>",
    methods=["POST"]
)
@login_required(role="Customer")
def api_rate_ticket(ticket_id):
    ticket = (
        Ticket.query
        .filter_by(
            id=ticket_id,
            author_id=current_user.id
        )
        .first()
    )

    if not ticket:
        return jsonify({
            "ok": False,
            "reason": "ticket_not_found",
            "message": "Ticket not found."
        }), 404

    # Only closed tickets should receive feedback.
    if (
        ticket.status_id
        != get_closed_status_id()
    ):
        return jsonify({
            "ok": False,
            "reason": "ticket_not_closed",
            "message": (
                "Feedback can only be submitted "
                "after the ticket is closed."
            )
        }), 400

    data = (
        request.get_json(
            silent=True
        )
        or {}
    )

    raw_rating = data.get("rating")

    feedback = (
        data.get("feedback")
        or ""
    ).strip()

    try:
        rating = int(raw_rating)

    except (TypeError, ValueError):
        rating = None

    if (
        rating is None
        or rating < 1
        or rating > 5
    ):
        return jsonify({
            "ok": False,
            "reason": "invalid_rating",
            "message": (
                "Please select a rating "
                "between 1 and 5."
            )
        }), 400

    # Get the newest chat session for this ticket.
    chat_session = (
        ChatSession.query
        .filter_by(
            ticket_id=ticket.id,
            user_id=current_user.id
        )
        .order_by(
            ChatSession.updated_at.desc(),
            ChatSession.id.desc()
        )
        .first()
    )

    # First check for a rating linked directly to this ticket.
    existing_rating = (
        CustomerSatisfaction.query
        .filter_by(
            ticket_id=ticket.id,
            customer_id=current_user.id
        )
        .first()
    )

    # Also check through the linked chat session.
    if (
        not existing_rating
        and chat_session
    ):
        existing_rating = (
            CustomerSatisfaction.query
            .filter_by(
                session_id=chat_session.id,
                customer_id=current_user.id
            )
            .first()
        )

    # Do not show an editable rating form again.
    if existing_rating:
        return jsonify({
            "ok": True,
            "already_rated": True,
            "ticket_id": ticket.id,
            "rating": existing_rating.rating,
            "feedback": (
                existing_rating.feedback
                or ""
            ),
            "message": (
                "Your feedback has already been saved."
            )
        }), 200

    new_rating = CustomerSatisfaction(
        ticket_id=ticket.id,
        session_id=(
            chat_session.id
            if chat_session
            else None
        ),
        customer_id=current_user.id,
        rating=rating,
        feedback=feedback
    )

    db.session.add(
        new_rating
    )

    if chat_session:
        chat_session.status = "Solved"
        chat_session.current_stage = "solved"
        chat_session.updated_at = (
            datetime.datetime.utcnow()
        )

    try:
        save_or_update_rating_message(
            customer_id=current_user.id,
            rating=rating,
            feedback=feedback,
            ticket_id=ticket.id,
            session_id=(
                chat_session.id
                if chat_session
                else None
            )
        )

        db.session.commit()

    except Exception:
        db.session.rollback()

        current_app.logger.exception(
            "Ticket rating save failed "
            "for ticket_id=%s customer_id=%s",
            ticket.id,
            current_user.id
        )

        return jsonify({
            "ok": False,
            "reason": "database_error",
            "message": (
                "Your feedback could not be saved. "
                "Please try again."
            )
        }), 500

    payload = {
        "user_id": current_user.id,
        "ticket_id": ticket.id,
        "ticket_number": ticket.number,
        "rating": rating,
        "feedback": feedback,
        "message": (
            "Thank you. Your rating has been saved."
        )
    }

    socketio.emit(
        "ticket_rating_saved",
        payload,
        room=f"user_{current_user.id}"
    )

    socketio.emit(
        "global_ticket_updated",
        payload
    )

    socketio.emit(
        "analytics_updated",
        payload
    )

    # Keep all chat history visible.
    # Do not set customer_visible=False.
    # Do not delete ChatMessage records.
    # Do not emit customer_chat_cleared.

    return jsonify({
        "ok": True,
        "already_rated": False,
        "ticket_id": ticket.id,
        "rating": rating,
        "feedback": feedback,
        "message": (
            "Thank you. Your rating has been saved."
        )
    }), 200


@customer_blueprint.route("/chat/rate/<int:session_id>", methods=["POST"])
@login_required(role="Customer")
def rate_chat(session_id):
    chat_session = ChatSession.query.filter_by(
        id=session_id,
        user_id=current_user.id
    ).first()

    if not chat_session:
        flash("Chat session not found.", "warning")
        return redirect(url_for("customer.my_tickets"))

    rating = request.form.get("rating", type=int)
    feedback = (request.form.get("feedback") or "").strip()

    if not rating or rating < 1 or rating > 5:
        flash("Please select a rating between 1 and 5.", "warning")
        return redirect(url_for("customer.view_chat", session_id=chat_session.id))

    existing_rating = CustomerSatisfaction.query.filter_by(
        session_id=chat_session.id,
        customer_id=current_user.id
    ).first()

    if not existing_rating and chat_session.ticket_id:
        existing_rating = CustomerSatisfaction.query.filter_by(
            ticket_id=chat_session.ticket_id,
            customer_id=current_user.id
        ).first()

    if existing_rating:
        existing_rating.session_id = chat_session.id
        existing_rating.ticket_id = chat_session.ticket_id
        existing_rating.rating = rating
        existing_rating.feedback = feedback
        existing_rating.updated_at = datetime.datetime.utcnow()
    else:
        existing_rating = CustomerSatisfaction(
            ticket_id=chat_session.ticket_id,
            session_id=chat_session.id,
            customer_id=current_user.id,
            rating=rating,
            feedback=feedback
        )
        db.session.add(existing_rating)

    chat_session.status = "Solved"
    chat_session.updated_at = datetime.datetime.utcnow()

    save_or_update_rating_message(
        customer_id=current_user.id,
        rating=rating,
        feedback=feedback,
        ticket_id=chat_session.ticket_id,
        session_id=chat_session.id
    )

    db.session.commit()

    flash("Thank you. Your chat rating has been saved.", "success")
    return redirect(url_for("customer.view_chat", session_id=chat_session.id))


@csrf.exempt
@customer_blueprint.route(
    "/api/chat/session/<int:session_id>/rate",
    methods=["POST"]
)
@login_required(role="Customer")
def api_rate_chat_session(session_id):
    chat_session = ChatSession.query.filter_by(
        id=session_id,
        user_id=current_user.id
    ).first()

    if not chat_session:
        return jsonify({
            "ok": False,
            "reason": "session_not_found",
            "message": "Chat session not found."
        }), 404

    data = request.get_json(
        silent=True
    ) or {}

    raw_rating = data.get("rating")

    feedback = (
        data.get("feedback")
        or ""
    ).strip()

    try:
        rating = int(raw_rating)

    except (TypeError, ValueError):
        rating = None

    if (
        rating is None
        or rating < 1
        or rating > 5
    ):
        return jsonify({
            "ok": False,
            "reason": "invalid_rating",
            "message": (
                "Please select a rating "
                "between 1 and 5."
            )
        }), 400

    existing_rating = (
        CustomerSatisfaction.query
        .filter(
            CustomerSatisfaction.customer_id
            == current_user.id,
            or_(
                CustomerSatisfaction.session_id
                == chat_session.id,
                CustomerSatisfaction.ticket_id
                == chat_session.ticket_id
            )
        )
        .first()
    )

    if existing_rating:
        existing_rating.session_id = (
            chat_session.id
        )
        existing_rating.ticket_id = (
            chat_session.ticket_id
        )
        existing_rating.rating = rating
        existing_rating.feedback = feedback
        existing_rating.updated_at = (
            datetime.datetime.utcnow()
        )

    else:
        existing_rating = CustomerSatisfaction(
            ticket_id=chat_session.ticket_id,
            session_id=chat_session.id,
            customer_id=current_user.id,
            rating=rating,
            feedback=feedback
        )

        db.session.add(
            existing_rating
        )

    chat_session.status = "Solved"
    chat_session.current_stage = "solved"
    chat_session.updated_at = (
        datetime.datetime.utcnow()
    )

    ChatMessage.query.filter(
        ChatMessage.session_id
        == chat_session.id,
        ChatMessage.user_id
        == current_user.id,
        ChatMessage.resolution_status
        == "Pending"
    ).update({
        "resolution_status": "Solved"
    }, synchronize_session=False)

    save_or_update_rating_message(
        customer_id=current_user.id,
        rating=rating,
        feedback=feedback,
        ticket_id=chat_session.ticket_id,
        session_id=chat_session.id
    )

    db.session.commit()

    emit_customer_refresh(
        current_user.id,
        "chat_rated"
    )

    return jsonify({
        "ok": True,
        "message": (
            "Rating saved successfully. "
            "This chat is now complete."
        ),
        "rating": rating,
        "feedback": feedback,
        "session": serialize_chat_session(
            chat_session
        )
    }), 200


# ============================================================
# TRIAGE CLASSIFICATION
# ============================================================

def classify_it_issue(issue_text):
    """
    Automatically determine the ticket category and priority
    based on the customer's issue description.
    """

    text = (issue_text or "").lower()

    # -----------------------------
    # CATEGORY
    # -----------------------------

    category = "General"

    if any(word in text for word in [
        "password",
        "login",
        "signin",
        "account",
        "authentication"
    ]):
        category = "Account"

    elif any(word in text for word in [
        "wifi",
        "internet",
        "network",
        "vpn",
        "connection"
    ]):
        category = "Network"

    elif any(word in text for word in [
        "printer",
        "scanner",
        "keyboard",
        "mouse",
        "monitor",
        "hardware"
    ]):
        category = "Hardware"

    elif any(word in text for word in [
        "email",
        "outlook",
        "office",
        "excel",
        "word",
        "teams"
    ]):
        category = "Software"

    elif any(word in text for word in [
        "virus",
        "malware",
        "hack",
        "security",
        "phishing"
    ]):
        category = "Security"

    # -----------------------------
    # PRIORITY
    # -----------------------------

    priority = "Medium"

    if any(word in text for word in [
        "urgent",
        "critical",
        "emergency",
        "cannot work",
        "system down",
        "server down"
    ]):
        priority = "High"

    elif any(word in text for word in [
        "minor",
        "question",
        "how to",
        "information",
        "help"
    ]):
        priority = "Low"

    return category, priority

# ============================================================
# AI / FAQ HELPERS
# ============================================================

def calculate_match_score(text, issue_type, title, body="", tags="", category=""):
    text = (text or "").lower()
    issue_type = (issue_type or "").lower()
    title = (title or "").lower()
    body = (body or "").lower()
    tags = (tags or "").lower()
    category = (category or "").lower()

    words = [
        word.strip()
        for word in text.replace("?", " ").replace(",", " ").replace("/", " ").split()
        if len(word.strip()) >= 3
    ]

    score = 0

    if issue_type and issue_type in category:
        score += 15

    if issue_type and issue_type in title:
        score += 10

    if text and text in title:
        score += 12

    if text and text in tags:
        score += 10

    if text and text in category:
        score += 8

    for word in words:
        if word in title:
            score += 6

        if word in tags:
            score += 5

        if word in category:
            score += 4

        if word in body:
            score += 2

    return score

def find_related_faqs(user_text: str, issue_type="", limit=5):
    text = (user_text or "").strip()

    if not text:
        return []

    faqs = (
        FAQ.query
        .filter(FAQ.is_active == True)
        .order_by(FAQ.id.desc())
        .all()
    )

    scored = []

    for faq in faqs:
        category_name = faq.category.category if faq.category else ""

        score = calculate_match_score(
            text=text,
            issue_type=issue_type,
            title=faq.question,
            body=faq.answer,
            tags=faq.tags,
            category=category_name
        )

        if score > 0:
            scored.append((score, faq))

    scored.sort(key=lambda item: item[0], reverse=True)

    return [
        {
            "id": faq.id,
            "question": faq.question,
            "answer": faq.answer,
            "category": faq.category.category if faq.category else "",
            "tags": faq.tags or "",
            "score": score
        }
        for score, faq in scored[:limit]
    ]

def find_related_knowledge_articles(user_text: str, issue_type="", limit=5):
    text = (user_text or "").strip()

    if not text:
        return []

    articles = (
        KnowledgeArticle.query
        .filter(KnowledgeArticle.is_active == True)
        .order_by(KnowledgeArticle.id.desc())
        .all()
    )

    scored = []

    for article in articles:
        category_name = article.category.category if article.category else ""

        score = calculate_match_score(
            text=text,
            issue_type=issue_type,
            title=article.title,
            body=article.content,
            tags=article.tags,
            category=category_name
        )

        if score > 0:
            scored.append((score, article))

    scored.sort(key=lambda item: item[0], reverse=True)

    return [
        {
            "id": article.id,
            "title": article.title,
            "content": article.content[:1000] if article.content else "",
            "category": article.category.category if article.category else "",
            "tags": article.tags or "",
            "score": score
        }
        for score, article in scored[:limit]
    ]

def build_faq_context(faqs):
    if not faqs:
        return "No matching FAQs found."

    return "\n\n".join([
        f"""
FAQ Match Score: {faq.get("score", 0)}
FAQ Category: {faq.get("category", "")}
FAQ Question: {faq.get("question", "")}
FAQ Answer: {faq.get("answer", "")}
""".strip()
        for faq in faqs
    ])


def build_knowledge_context(articles):
    if not articles:
        return "No matching Knowledge Base articles found."

    return "\n\n".join([
        f"""
Knowledge Match Score: {article.get("score", 0)}
Knowledge Category: {article.get("category", "")}
Article Title: {article.get("title", "")}
Article Content: {article.get("content", "")}
""".strip()
        for article in articles
    ])

def ask_openai_it_triage(user_text, triage_summary="", faqs=None, articles=None, language="en"):
    faqs = faqs or []
    articles = articles or []

    faq_text = "\n\n".join([
        f"FAQ Question: {faq.get('question')}\nFAQ Answer: {faq.get('answer')}"
        for faq in faqs
    ])

    kb_text = "\n\n".join([
        f"Knowledge Base Title: {article.get('title')}\nContent: {article.get('content')}"
        for article in articles
    ])

    setting = ChatbotSetting.query.first()

    if not setting:
        setting = ChatbotSetting()
        db.session.add(setting)
        db.session.commit()

    context_prompt = f"""
You are an AI-powered IT Service Desk assistant.

Use the available FAQ and Knowledge Base content first.
If the FAQ or Knowledge Base content does not fully answer the issue, provide a safe troubleshooting answer using general IT support knowledge.

Triage Summary:
{triage_summary or "No triage summary provided."}

Relevant FAQs:
{faq_text or "No matching FAQs found."}

Relevant Knowledge Base Articles:
{kb_text or "No matching Knowledge Base articles found."}

Customer Issue:
{user_text}

Response rules:
- Give a clear answer.
- Use step-by-step troubleshooting.
- Keep it practical.
- Do not make up company-specific policies.
- If this requires account access, admin permission, security investigation, or hardware replacement, say that support staff may need to assist.
- End by asking the customer to confirm whether this solved the issue.
""".strip()

    return ask_openai_chat(
        context_prompt,
        setting=setting,
        language=language
    )

def normalise_chat_language(language):
    if language == "ne":
        return "ne"
    return "en"

def build_ai_system_prompt(setting, language="en"):
    language = normalise_chat_language(language)

    tone = getattr(setting, "chatbot_tone", "Professional") or "Professional"
    response_length = getattr(setting, "response_length", "Medium") or "Medium"
    confidence_threshold = getattr(setting, "confidence_threshold", 70) or 70
    custom_prompt = getattr(setting, "system_prompt", "") or ""

    length_rules = {
        "Short": "Keep answers brief. Use 2 to 4 short sentences.",
        "Medium": "Give a balanced answer with clear explanation and useful steps.",
        "Detailed": "Give a detailed step-by-step answer with helpful context."
    }

    tone_rules = {
        "Friendly": "Use a warm, friendly, supportive tone.",
        "Professional": "Use a clear, professional customer support tone.",
        "Formal": "Use a formal and respectful tone.",
        "Simple": "Use very simple words and short sentences."
    }

    language_rule = (
        "Reply in Nepali language. Use clear, natural Nepali. Keep support terms simple."
        if language == "ne"
        else "Reply in English."
    )

    return f"""
You are a customer support assistant.

Language instruction:
{language_rule}

Tone instruction:
{tone_rules.get(tone, tone_rules["Professional"])}

Response length instruction:
{length_rules.get(response_length, length_rules["Medium"])}

Confidence instruction:
Only answer confidently when the customer question is clear.
If you are unsure or the answer needs account-specific help, tell the customer to contact support.
Current confidence threshold setting: {confidence_threshold}%.

Custom admin instructions:
{custom_prompt}

Always be polite, clear, practical, and safe.
""".strip()


def ask_openai_chat(user_text: str, setting=None, language="en") -> str:
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")

    client = OpenAI(api_key=api_key)

    system_prompt = build_ai_system_prompt(setting, language)

    response_length = getattr(setting, "response_length", "Medium") if setting else "Medium"

    max_tokens = 180

    if response_length == "Short":
        max_tokens = 100
    elif response_length == "Detailed":
        max_tokens = 350

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": user_text
            }
        ],
        max_tokens=max_tokens,
        temperature=0.3
    )

    return (resp.choices[0].message.content or "").strip()


def save_chat_message(
    user_id,
    role,
    message,
    faq_matched=False,
    ai_used=False,
    escalated=False,
    customer_visible=True,
    ticket_id=None,
    session_id=None,
    resolution_status="Pending"
):
    if not user_id:
        return None

    try:
        chat = ChatMessage(
            user_id=user_id,
            session_id=session_id,
            ticket_id=ticket_id,
            role=role,
            message=message,
            faq_matched=faq_matched,
            ai_used=ai_used,
            escalated=escalated,
            guest_user=False,
            customer_visible=customer_visible,
            resolution_status=resolution_status
        )

        db.session.add(chat)

        if session_id:
            chat_session = ChatSession.query.filter_by(
                id=session_id,
                user_id=user_id
            ).first()

            if chat_session:
                chat_session.updated_at = datetime.datetime.utcnow()

        db.session.commit()
        return chat

    except Exception as e:
        db.session.rollback()
        print("CHAT MESSAGE SAVE ERROR:", e)
        return None

def needs_human_escalation(user_message: str, ai_reply: str) -> bool:
    msg = (user_message or "").lower()
    rep = (ai_reply or "").lower()

    human_words = [
        "human",
        "agent",
        "support",
        "representative",
        "staff",
        "person",
        "talk to someone",
        "talk to support",
        "not solved",
        "still not working",
        "complaint",
        "refund",
        "urgent"
    ]

    if any(word in msg for word in human_words):
        return True

    ai_uncertain = [
        "i am not sure",
        "not sure",
        "contact support",
        "talk to support",
        "can't help",
        "cannot help",
        "unable to"
    ]

    if any(word in rep for word in ai_uncertain):
        return True

    return False


# ============================================================
# CUSTOMER API
# ============================================================
@csrf.exempt
@customer_blueprint.route(
    "/api/chat/session/<int:session_id>/triage-progress",
    methods=["POST"]
)
@login_required(role="Customer")
def api_update_chat_triage_progress(session_id):
    chat_session = ChatSession.query.filter_by(
        id=session_id,
        user_id=current_user.id
    ).first()

    if not chat_session:
        return jsonify({
            "ok": False,
            "reason": "session_not_found",
            "message": "Chat session not found."
        }), 404

    if chat_session.current_stage in {
        "solved",
        "closed"
    }:
        return jsonify({
            "ok": False,
            "reason": "session_read_only",
            "message": "This chat is read-only."
        }), 400

    data = request.get_json(
        silent=True
    ) or {}

    raw_step = data.get(
        "triage_step",
        chat_session.triage_step or 0
    )

    try:
        triage_step = int(raw_step)

    except (TypeError, ValueError):
        return jsonify({
            "ok": False,
            "reason": "invalid_triage_step"
        }), 400

    triage_data = data.get(
        "triage_data"
    ) or {}

    if not isinstance(triage_data, dict):
        return jsonify({
            "ok": False,
            "reason": "invalid_triage_data"
        }), 400

    issue_type = (
        data.get("issue_type")
        or triage_data.get("issue_type")
        or chat_session.issue_type
        or ""
    ).strip()

    stage = (
        data.get("current_stage")
        or "triage"
    ).strip().lower()

    allowed_stages = {
        "triage",
        "processing_answer",
        "awaiting_resolution",
        "ai_chat",
        "awaiting_rating",
        "ticket_created",
        "solved",
        "closed"
    }

    if stage not in allowed_stages:
        stage = "triage"

    chat_session.issue_type = issue_type
    chat_session.triage_step = max(
        0,
        triage_step
    )
    chat_session.triage_data = json.dumps(
        triage_data
    )
    chat_session.current_stage = stage
    chat_session.updated_at = (
        datetime.datetime.utcnow()
    )

    if stage == "triage":
        chat_session.status = "Triage"

    elif stage == "processing_answer":
        chat_session.status = "Processing"

    elif stage == "awaiting_resolution":
        chat_session.status = "AI Answered"

    elif stage == "awaiting_rating":
        chat_session.status = "Awaiting Rating"

    elif stage == "ticket_created":
        chat_session.status = "Ticket Created"

    elif stage == "solved":
        chat_session.status = "Solved"

    elif stage == "closed":
        chat_session.status = "Closed"

    db.session.commit()

    return jsonify({
        "ok": True,
        "session": serialize_chat_session(
            chat_session
        )
    }), 200

@csrf.exempt
@customer_blueprint.route(
    "/api/chat/session/<int:session_id>/state",
    methods=["POST"]
)
@login_required(role="Customer")
def api_update_chat_session_state(session_id):
    chat_session = ChatSession.query.filter_by(
        id=session_id,
        user_id=current_user.id
    ).first()

    if not chat_session:
        return jsonify({
            "ok": False,
            "reason": "session_not_found"
        }), 404

    data = request.get_json(
        silent=True
    ) or {}

    current_stage = (
        data.get("current_stage")
        or ""
    ).strip().lower()

    allowed_stages = {
        "triage",
        "processing_answer",
        "awaiting_resolution",
        "ai_chat",
        "awaiting_rating",
        "ticket_created",
        "solved",
        "closed"
    }

    if current_stage not in allowed_stages:
        return jsonify({
            "ok": False,
            "reason": "invalid_stage"
        }), 400

    status_map = {
        "triage": "Triage",
        "processing_answer": "Processing",
        "awaiting_resolution": "AI Answered",
        "ai_chat": "AI Conversation",
        "awaiting_rating": "Awaiting Rating",
        "ticket_created": "Ticket Created",
        "solved": "Solved",
        "closed": "Closed"
    }

    chat_session.current_stage = current_stage
    chat_session.status = status_map[
        current_stage
    ]
    chat_session.updated_at = (
        datetime.datetime.utcnow()
    )

    db.session.commit()

    return jsonify({
        "ok": True,
        "session": serialize_chat_session(
            chat_session
        )
    }), 200



@csrf.exempt
@customer_blueprint.route(
    "/api/chat/session/<int:session_id>/triage-answer",
    methods=["POST"]
)
@login_required(role="Customer")
def api_chat_session_triage_answer(session_id):
    chat_session = ChatSession.query.filter_by(
        id=session_id,
        user_id=current_user.id
    ).first()

    if not chat_session:
        return jsonify({
            "ok": False,
            "reason": "session_not_found"
        }), 404

    if chat_session.current_stage in {
        "solved",
        "closed",
        "ticket_created"
    }:
        return jsonify({
            "ok": False,
            "reason": "invalid_session_stage",
            "message": (
                "This chat cannot generate another "
                "AI answer in its current state."
            )
        }), 400

    data = request.get_json(
        silent=True
    ) or {}

    triage_summary = (
        data.get("triage_summary")
        or ""
    ).strip()

    issue_type = (
        data.get("issue_type")
        or chat_session.issue_type
        or ""
    ).strip()

    if not triage_summary:
        return jsonify({
            "ok": False,
            "reason": "missing_triage_summary"
        }), 400

    chat_session.current_stage = (
        "processing_answer"
    )
    chat_session.status = "Processing"
    chat_session.triage_summary = (
        triage_summary
    )
    chat_session.updated_at = (
        datetime.datetime.utcnow()
    )

    db.session.commit()

    search_text = (
        f"{issue_type}\n"
        f"{triage_summary}"
    )

    related_faqs = find_related_faqs(
        search_text,
        issue_type=issue_type,
        limit=5
    )

    related_articles = (
        find_related_knowledge_articles(
            search_text,
            issue_type=issue_type,
            limit=5
        )
    )

    answer_source = "ai"
    ai_reply = ""

    strong_faq_match = bool(
        related_faqs
        and related_faqs[0].get(
            "score",
            0
        ) >= 25
    )

    strong_kb_match = bool(
        related_articles
        and related_articles[0].get(
            "score",
            0
        ) >= 25
    )

    try:
        if strong_faq_match:
            best_faq = related_faqs[0]

            ai_reply = f"""
<strong>FAQ Answer Found</strong><br><br>
<strong>{best_faq["question"]}</strong><br><br>
{best_faq["answer"]}
""".strip()

            answer_source = "faq"

        elif strong_kb_match:
            best_article = related_articles[0]

            ai_reply = f"""
<strong>Knowledge Base Answer Found</strong><br><br>
<strong>{best_article["title"]}</strong><br><br>
{best_article["content"]}
""".strip()

            answer_source = "knowledge_base"

        else:
            ai_result = ask_chatgpt(
                message=(
                    issue_type
                    or "IT Support"
                ),
                triage_context=triage_summary,
                faq_context=build_faq_context(
                    related_faqs
                ),
                knowledge_context=(
                    build_knowledge_context(
                        related_articles
                    )
                )
            )

            if ai_result.get("ok"):
                ai_reply = (
                    ai_result.get("answer")
                    or "No AI answer was generated."
                )

            else:
                ai_reply = (
                    "AI is temporarily unavailable. "
                    "Please create a support ticket."
                )

            answer_source = "ai"

    except Exception as error:
        current_app.logger.exception(
            "IT triage answer failed for "
            "session_id=%s: %s",
            chat_session.id,
            error
        )

        ai_reply = (
            "AI is temporarily unavailable. "
            "Please create a support ticket."
        )
        answer_source = "ai"

    assistant_message = ChatMessage(
        user_id=current_user.id,
        session_id=chat_session.id,
        ticket_id=chat_session.ticket_id,
        role="assistant",
        message=ai_reply,
        ai_used=(
            answer_source == "ai"
        ),
        faq_matched=(
            answer_source == "faq"
        ),
        escalated=False,
        guest_user=False,
        customer_visible=True,
        resolution_status="Pending"
    )

    db.session.add(
        assistant_message
    )

    chat_session.current_stage = (
        "awaiting_resolution"
    )
    chat_session.status = "AI Answered"
    chat_session.triage_summary = (
        triage_summary
    )
    chat_session.updated_at = (
        datetime.datetime.utcnow()
    )

    db.session.commit()

    emit_customer_refresh(
        current_user.id,
        "triage_answer_ready"
    )

    return jsonify({
        "ok": True,
        "reply": ai_reply,
        "source": answer_source,
        "faqs": related_faqs,
        "articles": related_articles,
        "ask_resolved": True,
        "session": serialize_chat_session(
            chat_session
        ),
        "chat": serialize_chat_message(
            assistant_message
        )
    }), 200

@csrf.exempt
@customer_blueprint.route(
    "/api/chat/session/<int:session_id>/ai-follow-up",
    methods=["POST"]
)
@login_required(role="Customer")
def api_chat_session_ai_follow_up(session_id):
    chat_session = ChatSession.query.filter_by(
        id=session_id,
        user_id=current_user.id
    ).first()

    if not chat_session:
        return jsonify({
            "ok": False,
            "reason": "session_not_found"
        }), 404

    if chat_session.ticket_id:
        return jsonify({
            "ok": False,
            "reason": "ticket_already_created",
            "message": (
                "This conversation is now connected to a support ticket."
            )
        }), 400

    if chat_session.current_stage not in {
        "ai_chat",
        "awaiting_resolution"
    }:
        return jsonify({
            "ok": False,
            "reason": "invalid_session_stage",
            "message": (
                "Choose 'No, continue with AI' before sending another message."
            )
        }), 400

    data = request.get_json(silent=True) or {}
    user_message = (data.get("message") or "").strip()

    if not user_message:
        return jsonify({
            "ok": False,
            "reason": "missing_message",
            "message": "Please type a message first."
        }), 400

    chat_session.current_stage = "processing_answer"
    chat_session.status = "Processing"
    chat_session.updated_at = datetime.datetime.utcnow()

    user_chat = ChatMessage(
        user_id=current_user.id,
        session_id=chat_session.id,
        ticket_id=None,
        role="user",
        message=user_message,
        ai_used=False,
        faq_matched=False,
        escalated=False,
        guest_user=False,
        customer_visible=True,
        resolution_status="Pending"
    )
    db.session.add(user_chat)
    db.session.commit()

    recent_messages = (
        ChatMessage.query
        .filter(ChatMessage.session_id == chat_session.id)
        .filter(ChatMessage.customer_visible == True)
        .order_by(ChatMessage.created_at.desc())
        .limit(12)
        .all()
    )
    recent_messages.reverse()

    conversation_context = "\n".join([
        f"{message.role.upper()}: {message.message}"
        for message in recent_messages
        if message.message
    ])

    search_text = (
        f"{chat_session.issue_type or ''}\n"
        f"{user_message}"
    )
    related_faqs = find_related_faqs(
        search_text,
        issue_type=chat_session.issue_type,
        limit=5
    )
    related_articles = find_related_knowledge_articles(
        search_text,
        issue_type=chat_session.issue_type,
        limit=5
    )

    try:
        ai_result = ask_chatgpt(
            message=user_message,
            triage_context=(
                f"Original triage summary:\n"
                f"{chat_session.triage_summary or ''}\n\n"
                f"Recent conversation:\n"
                f"{conversation_context}"
            ),
            faq_context=build_faq_context(related_faqs),
            knowledge_context=build_knowledge_context(
                related_articles
            )
        )

        if ai_result.get("ok"):
            ai_reply = (
                ai_result.get("answer")
                or "No AI answer was generated."
            )
        else:
            ai_reply = (
                "AI is temporarily unavailable. "
                "You can try again or create a support ticket."
            )

    except Exception as error:
        current_app.logger.exception(
            "AI follow-up failed for session_id=%s: %s",
            chat_session.id,
            error
        )
        ai_reply = (
            "AI is temporarily unavailable. "
            "You can try again or create a support ticket."
        )

    assistant_chat = ChatMessage(
        user_id=current_user.id,
        session_id=chat_session.id,
        ticket_id=None,
        role="assistant",
        message=ai_reply,
        ai_used=True,
        faq_matched=False,
        escalated=False,
        guest_user=False,
        customer_visible=True,
        resolution_status="Pending"
    )
    db.session.add(assistant_chat)

    # Remain in continuous AI-chat mode after every follow-up.
    # The full resolution question is shown only once, after the
    # initial triage answer. The customer can now keep chatting
    # until they choose Issue solved or Create support ticket.
    chat_session.current_stage = "ai_chat"
    chat_session.status = "AI Conversation"
    chat_session.updated_at = datetime.datetime.utcnow()
    db.session.commit()

    emit_customer_refresh(
        current_user.id,
        "ai_follow_up_ready"
    )

    return jsonify({
        "ok": True,
        "reply": ai_reply,
        "session": serialize_chat_session(chat_session),
        "user_chat": serialize_chat_message(user_chat),
        "chat": serialize_chat_message(assistant_chat)
    }), 200


@csrf.exempt
@customer_blueprint.route("/api/chat/session/<int:session_id>/message", methods=["POST"])
@login_required(role="Customer")
def api_save_chat_session_message(session_id):
    chat_session = ChatSession.query.filter_by(
        id=session_id,
        user_id=current_user.id
    ).first()

    if not chat_session:
        return jsonify({
            "ok": False,
            "reason": "session_not_found"
        }), 404

    data = request.get_json(silent=True) or {}

    role = (data.get("role") or "system").strip()
    message = (data.get("message") or "").strip()
    ticket_id = data.get("ticket_id")

    if not message:
        return jsonify({
            "ok": False,
            "reason": "empty_message"
        }), 400

    chat = save_chat_message(
        user_id=current_user.id,
        session_id=chat_session.id,
        ticket_id=ticket_id,
        role=role,
        message=message,
        resolution_status=data.get("resolution_status") or "Active",
        faq_matched=data.get("faq_matched") == True,
        ai_used=data.get("ai_used") == True,
        escalated=data.get("escalated") == True
    )

    return jsonify({
        "ok": True,
        "chat": serialize_chat_message(chat)
    }), 200

@csrf.exempt
@customer_blueprint.route(
    "/api/chat/session/new",
    methods=["POST"]
)
@login_required(role="Customer")
def api_create_chat_session():
    data = request.get_json(
        silent=True
    ) or {}

    title = (
        data.get("title")
        or "New IT Support Chat"
    ).strip()

    issue_type = (
        data.get("issue_type")
        or ""
    ).strip()

    initial_triage_data = {
        "issue_type": issue_type,
        "affected_users": "",
        "impact": "",
        "urgency": "",
        "device": "",
        "error_message": "",
        "tried_steps": "",
        "details": ""
    }

    chat_session = ChatSession(
        user_id=current_user.id,
        title=title,
        issue_type=issue_type,
        status="Triage",
        current_stage="triage",
        triage_step=0,
        triage_data=json.dumps(
            initial_triage_data
        ),
        triage_summary=None
    )

    db.session.add(
        chat_session
    )
    db.session.flush()

    start_message = ChatMessage(
        user_id=current_user.id,
        session_id=chat_session.id,
        ticket_id=None,
        role="system",
        message=(
            f"New IT support chat started. "
            f"Issue type: "
            f"{issue_type or 'Not selected'}"
        ),
        resolution_status="Active",
        customer_visible=True,
        faq_matched=False,
        ai_used=False,
        escalated=False,
        guest_user=False
    )

    db.session.add(
        start_message
    )
    db.session.commit()

    return jsonify({
        "ok": True,
        "session": serialize_chat_session(
            chat_session
        ),
        "start_message": serialize_chat_message(
            start_message
        )
    }), 200


@csrf.exempt
@customer_blueprint.route("/api/chat/sessions", methods=["GET"])
@login_required(role="Customer")
def api_chat_sessions():
    search = (request.args.get("search") or "").strip()

    query = ChatSession.query.filter_by(user_id=current_user.id)

    if search:
        query = query.filter(
            or_(
                ChatSession.title.ilike(f"%{search}%"),
                ChatSession.issue_type.ilike(f"%{search}%"),
                ChatSession.status.ilike(f"%{search}%"),
                ChatSession.triage_summary.ilike(f"%{search}%")
            )
        )

    sessions = (
        query
        .order_by(ChatSession.updated_at.desc(), ChatSession.created_at.desc())
        .all()
    )

    return jsonify({
        "ok": True,
        "sessions": [serialize_chat_session(s) for s in sessions]
    }), 200

@csrf.exempt
@customer_blueprint.route(
    "/api/chat/session/<int:session_id>",
    methods=["GET"]
)
@login_required(role="Customer")
def api_get_chat_session(session_id):
    chat_session = ChatSession.query.filter_by(
        id=session_id,
        user_id=current_user.id
    ).first()

    if not chat_session:
        return jsonify({
            "ok": False,
            "reason": "session_not_found",
            "message": "Chat session not found."
        }), 404

    ticket = None
    existing_rating = None

    if chat_session.ticket_id:
        ticket = Ticket.query.filter_by(
            id=chat_session.ticket_id,
            author_id=current_user.id
        ).first()

        existing_rating = (
            CustomerSatisfaction.query
            .filter(
                CustomerSatisfaction.customer_id
                == current_user.id,
                or_(
                    CustomerSatisfaction.session_id
                    == chat_session.id,
                    CustomerSatisfaction.ticket_id
                    == chat_session.ticket_id
                )
            )
            .first()
        )

        if (
            ticket
            and ticket.status
            and ticket.status.status.lower() == "closed"
        ):

            if existing_rating:
                chat_session.current_stage = "solved"
                chat_session.status = "Solved"
            else:
                chat_session.current_stage = "closed"
                chat_session.status = "Closed"

            db.session.commit()

    messages = (
        ChatMessage.query
        .filter(
            ChatMessage.session_id == chat_session.id,
            ChatMessage.user_id == current_user.id,
            ChatMessage.customer_visible == True
        )
        .order_by(
            ChatMessage.created_at.asc(),
            ChatMessage.id.asc()
        )
        .all()
    )

    comments = []

    if ticket:
        comments = (
            Comment.query
            .filter(
                Comment.ticket_id == ticket.id
            )
            .order_by(
                Comment.created_at.asc(),
                Comment.id.asc()
            )
            .all()
        )

    return jsonify({
        "ok": True,
        "session": serialize_chat_session(chat_session),

        "messages": [
            serialize_chat_message(message)
            for message in messages
        ],

        "comments": [
            serialize_comment(comment)
            for comment in comments
        ],

        "already_rated": existing_rating is not None,

        "ticket_rating": (
            {
                "id": existing_rating.id,
                "rating": existing_rating.rating,
                "feedback": existing_rating.feedback or "",
                "created_at":
                    existing_rating.created_at.strftime(
                        "%d %b %Y %H:%M"
                    )
                    if existing_rating.created_at
                    else ""
            }
            if existing_rating
            else None
        )
    }), 200


@csrf.exempt
@customer_blueprint.route("/api/chat/session/<int:session_id>/delete", methods=["POST", "DELETE"])
@login_required(role="Customer")
def api_delete_chat_session(session_id):
    chat_session = ChatSession.query.filter_by(
        id=session_id,
        user_id=current_user.id
    ).first()

    if not chat_session:
        return jsonify({
            "ok": False,
            "reason": "session_not_found"
        }), 404

    ChatMessage.query.filter_by(
        session_id=chat_session.id,
        user_id=current_user.id
    ).delete()

    db.session.delete(chat_session)
    db.session.commit()

    return jsonify({
        "ok": True,
        "deleted": True
    }), 200

@csrf.exempt
@customer_blueprint.route("/api/me", methods=["GET"])
def api_me():
    return jsonify({
        "ok": True,
        "is_authenticated": bool(current_user.is_authenticated),
        "user_id": current_user.id if current_user.is_authenticated else None,
        "name": current_user.name if current_user.is_authenticated else None,
        "role": current_user.role if current_user.is_authenticated else None
    }), 200

@csrf.exempt
@customer_blueprint.route("/api/guest-status", methods=["GET"])
def api_guest_status():

    if current_user.is_authenticated:
        return jsonify({
            "is_guest": False
        })

    used = session.get("guest_query_count", 0)

    return jsonify({
        "is_guest": True,
        "used": used,
        "remaining": max(
            0,
            GUEST_QUERY_LIMIT - used
        )
    })
@csrf.exempt
@customer_blueprint.route("/api/chat/history", methods=["GET"])
def api_chat_history():
    if not current_user.is_authenticated:
        return jsonify({"ok": True, "messages": []}), 200

    active_ticket = get_active_ticket_for_user(current_user.id)

    if active_ticket:
        return jsonify({
            "ok": True,
            "messages": [],
            "needs_resolution_prompt": False
        }), 200

    msgs = (
        ChatMessage.query
        .filter(ChatMessage.user_id == current_user.id)
        .filter(ChatMessage.customer_visible == True)
        .order_by(ChatMessage.created_at.asc())
        .limit(80)
        .all()
    )

    needs_resolution_prompt = False
    source_type = ""
    original_message = ""

    last_msg = msgs[-1] if msgs else None

    if (
        last_msg
        and last_msg.role == "assistant"
        and last_msg.resolution_status == "Pending"
        and (last_msg.ai_used == True or last_msg.faq_matched == True)
    ):
        needs_resolution_prompt = True
        source_type = "faq" if last_msg.faq_matched else "ai"

        previous_user_msg = (
            ChatMessage.query
            .filter(ChatMessage.user_id == current_user.id)
            .filter(ChatMessage.role == "user")
            .filter(ChatMessage.created_at <= last_msg.created_at)
            .order_by(ChatMessage.created_at.desc())
            .first()
        )

        original_message = previous_user_msg.message if previous_user_msg else ""

    return jsonify({
        "ok": True,
        "messages": [serialize_chat_message(m) for m in msgs],
        "needs_resolution_prompt": needs_resolution_prompt,
        "source_type": source_type,
        "original_message": original_message
    }), 200

@csrf.exempt
@customer_blueprint.route("/api/chat", methods=["POST"])

def api_chat():
    data = request.get_json(silent=True) or {}

    user_message = (data.get("message") or "").strip()
    skip_faq = data.get("skip_faq") == True
    language = normalise_chat_language(data.get("language", "en"))
    if not current_user.is_authenticated:
        return jsonify({
            "ok": False,
            "needs_login": True,
            "reply": "Please log in to use the IT support chatbot."
        }), 401

    user_id = current_user.id

    if not user_message:
        return jsonify({
            "ok": False,
            "reply": "Please type a message first."
        }), 400
    
    maintenance = get_active_maintenance()
    if maintenance:
        reply = maintenance.message or "The chatbot is currently under maintenance. Please try again later."

        return jsonify({
            "ok": True,
            "maintenance": True,
            "maintenance_title": maintenance.title or "System Maintenance",
            "reply": reply,
            "ask_resolved": False,
            "needs_human": maintenance.allow_ticket_creation,
            "original_message": user_message
        }), 200

    if not current_user.is_authenticated:
        guest_count = session.get("guest_query_count", 0)

        if guest_count >= GUEST_QUERY_LIMIT:
            return jsonify({
                "ok": False,
                "guest_limit_reached": True,
                "reply": (
                    "You have reached the guest chat limit. "
                    "Please log in or create an account to continue chatting."
                )
            }), 200

    setting = ChatbotSetting.query.first()

    if not setting:
        setting = ChatbotSetting()
        db.session.add(setting)
        db.session.commit()

    if not current_user.is_authenticated:
        session["guest_query_count"] = session.get("guest_query_count", 0) + 1

    user_chat = save_chat_message(
        user_id=user_id,
        role="user",
        message=user_message
    )

    if user_id and user_chat:
        emit_customer_chat_event(
            user_id,
            "customer_ai_message",
            {
                "chat": serialize_chat_message(user_chat),
                "event_type": "user_message"
            }
        )

    related_faqs = find_related_faqs(user_message) if not skip_faq else []

    if related_faqs:
        emit_customer_chat_event(
            user_id,
            "customer_faq_suggestions",
            {
                "original_message": user_message,
                "faqs": related_faqs
            }
        )

        return jsonify({
            "ok": True,
            "type": "faq_suggestions",
            "reply": "",
            "faqs": related_faqs,
            "original_message": user_message,
            "ask_resolved": False,
            "needs_human": False
        }), 200

    if not setting.ai_enabled:
        fallback_reply = (
            setting.fallback_message or
            "AI is currently unavailable. Please talk to support."
        )

        assistant_chat = save_chat_message(
            user_id=user_id,
            role="assistant",
            message=fallback_reply,
            ai_used=False,
            escalated=True
        )

        if user_id:
            emit_customer_chat_event(
                user_id,
                "customer_ai_message",
                {
                    "chat": serialize_chat_message(assistant_chat),
                    "event_type": "ai_unavailable",
                    "ask_resolved": False,
                    "needs_human": True,
                    "original_message": user_message
                }
            )

            emit_customer_chat_event(
                user_id,
                "customer_human_prompt",
                {
                    "original_message": user_message,
                    "message": "AI is unavailable. Would you like to talk to human support?"
                }
            )

        return jsonify({
            "ok": True,
            "reply": fallback_reply,
            "ai_disabled": True,
            "ask_resolved": False,
            "needs_human": True,
            "original_message": user_message
        }), 200

    try:
        ai_reply = ask_openai_chat(user_message, setting, language)

        if not ai_reply:
            ai_reply = "I could not generate a response right now. Please talk to support."

    except Exception as e:
        print("OPENAI ERROR:", e)
        ai_reply = "AI is temporarily unavailable. Please talk to support."

    needs_human = False

    if setting.auto_escalation_enabled:
        needs_human = needs_human_escalation(user_message, ai_reply)

    custom_keywords = [
        word.strip().lower()
        for word in (setting.escalation_keywords or "").split(",")
        if word.strip()
    ]

    message_lower = user_message.lower()

    if any(keyword in message_lower for keyword in custom_keywords):
        needs_human = True

    assistant_chat = save_chat_message(
        user_id=user_id,
        role="assistant",
        message=ai_reply,
        ai_used=True,
        escalated=needs_human
    )

    if user_id:
        emit_customer_chat_event(
            user_id,
            "customer_ai_message",
            {
                "chat": serialize_chat_message(assistant_chat),
                "event_type": "ai_answer",
                "ask_resolved": True,
                "needs_human": needs_human,
                "original_message": user_message
            }
        )

    return jsonify({
        "ok": True,
        "reply": ai_reply,
        "ask_resolved": True,
        "needs_human": needs_human,
        "original_message": user_message
    }), 200

@csrf.exempt
@customer_blueprint.route("/api/chat/faq-selected", methods=["POST"])
def api_chat_faq_selected():
    data = request.get_json(silent=True) or {}

    question = (data.get("question") or "").strip()
    answer = (data.get("answer") or "").strip()
    original_message = (data.get("original_message") or "").strip()

    user_id = current_user.id if current_user.is_authenticated else None

    if not question or not answer:
        return jsonify({"ok": False, "reason": "missing_faq"}), 400

    question_chat = None
    answer_chat = None

    if user_id:
        question_chat = save_chat_message(
            user_id=user_id,
            role="user",
            message=question,
            faq_matched=True
        )

        answer_chat = save_chat_message(
            user_id=user_id,
            role="assistant",
            message=answer,
            faq_matched=True
        )

        emit_customer_chat_event(
            user_id,
            "customer_faq_answer",
            {
                "question_chat": serialize_chat_message(question_chat),
                "answer_chat": serialize_chat_message(answer_chat),
                "question": question,
                "answer": answer,
                "original_message": original_message,
                "ask_resolved": True
            }
        )

    return jsonify({
        "ok": True,
        "question": question,
        "answer": answer,
        "original_message": original_message,
        "ask_resolved": True
    }), 200

@csrf.exempt
@customer_blueprint.route(
    "/api/chat/resolution",
    methods=["POST"]
)
@login_required(role="Customer")
def api_chat_resolution():
    data = request.get_json(
        silent=True
    ) or {}

    solved = (
        data.get("solved") is True
    )

    session_id = data.get(
        "session_id"
    )

    source_type = (
        data.get("source_type")
        or ""
    ).strip()

    original_message = (
        data.get("original_message")
        or ""
    ).strip()

    chat_session = None

    if session_id:
        chat_session = ChatSession.query.filter_by(
            id=session_id,
            user_id=current_user.id
        ).first()

        if not chat_session:
            return jsonify({
                "ok": False,
                "reason": "session_not_found"
            }), 404

    if solved:
        if chat_session:
            chat_session.current_stage = (
                "awaiting_rating"
            )
            chat_session.status = (
                "Awaiting Rating"
            )
            chat_session.updated_at = (
                datetime.datetime.utcnow()
            )

        ChatMessage.query.filter(
            ChatMessage.user_id
            == current_user.id,
            ChatMessage.session_id
            == (
                chat_session.id
                if chat_session
                else None
            ),
            ChatMessage.resolution_status
            == "Pending"
        ).update({
            "resolution_status": "Solved"
        }, synchronize_session=False)

        db.session.commit()

        return jsonify({
            "ok": True,
            "cleared": False,
            "next_step": "rating",
            "message": (
                "Please rate your support experience."
            ),
            "session": (
                serialize_chat_session(
                    chat_session
                )
                if chat_session
                else None
            )
        }), 200

    if chat_session:
        chat_session.current_stage = (
            "awaiting_resolution"
        )
        chat_session.status = "AI Answered"
        chat_session.updated_at = (
            datetime.datetime.utcnow()
        )

        ChatMessage.query.filter(
            ChatMessage.session_id
            == chat_session.id,
            ChatMessage.user_id
            == current_user.id,
            ChatMessage.resolution_status
            == "Pending"
        ).update({
            "resolution_status": "Not Solved"
        }, synchronize_session=False)

    db.session.commit()

    if source_type == "faq":
        return jsonify({
            "ok": True,
            "next_step": "ai",
            "message": (
                "Okay, I’ll try the AI assistant "
                "for you."
            ),
            "original_message": original_message
        }), 200

    return jsonify({
        "ok": True,
        "next_step": "human",
        "message": (
            "You can now create a support ticket "
            "for human assistance."
        ),
        "original_message": original_message
    }), 200


@csrf.exempt
@customer_blueprint.route("/api/chat/clear", methods=["POST"])
def api_chat_clear():
    if not current_user.is_authenticated:
        return jsonify({"ok": True, "cleared": True}), 200

    try:
        ChatMessage.query.filter(
            ChatMessage.user_id == current_user.id
        ).update({
            "customer_visible": False
        })
        db.session.commit()

        emit_customer_chat_event(
            current_user.id,
            "customer_chat_cleared",
            {
                "message": "Chat cleared."
            }
        )

        return jsonify({"ok": True, "cleared": True}), 200

    except Exception as e:
        db.session.rollback()
        print("CHAT CLEAR ERROR:", e)
        return jsonify({
            "ok": False,
            "reason": "server_error"
        }), 500


@csrf.exempt
@customer_blueprint.route("/api/ticket/active", methods=["GET"])
def api_active_ticket():
    auto_close_waiting_customer_tickets()
    if not current_user.is_authenticated:
        return jsonify({
            "ok": False,
            "reason": "not_authenticated",
            "has_active": False
        }), 401

    ticket = get_active_ticket_for_user(current_user.id)

    if not ticket:
        return jsonify({
            "ok": True,
            "has_active": False
        }), 200

    return jsonify({
        "ok": True,
        "has_active": True,
        **serialize_ticket(ticket)
    }), 200


@csrf.exempt
@customer_blueprint.route("/api/ticket/status/<int:ticket_id>", methods=["GET"])
def api_ticket_status(ticket_id):
    if not current_user.is_authenticated:
        return jsonify({"ok": False, "reason": "not_authenticated"}), 401

    ticket = Ticket.query.filter_by(id=ticket_id, author_id=current_user.id).first()

    if not ticket:
        return jsonify({"ok": False, "reason": "not_found"}), 404

    return jsonify({
        "ok": True,
        **serialize_ticket(ticket)
    }), 200


@csrf.exempt
@customer_blueprint.route(
    "/api/ticket/comments/<int:ticket_id>",
    methods=["GET"]
)
@login_required(role="Customer")
def api_ticket_comments(ticket_id):
    ticket = Ticket.query.filter_by(
        id=ticket_id,
        author_id=current_user.id
    ).first()

    if not ticket:
        return jsonify({
            "ok": False,
            "reason": "not_found",
            "message": "Ticket not found."
        }), 404

    comments = (
        Comment.query
        .filter(Comment.ticket_id == ticket.id)
        .order_by(Comment.created_at.asc())
        .all()
    )

    chat_session = ChatSession.query.filter_by(
        ticket_id=ticket.id,
        user_id=current_user.id
    ).first()

    existing_rating = CustomerSatisfaction.query.filter_by(
        ticket_id=ticket.id,
        customer_id=current_user.id
    ).first()

    if not existing_rating and chat_session:
        existing_rating = CustomerSatisfaction.query.filter_by(
            session_id=chat_session.id,
            customer_id=current_user.id
        ).first()

    rating_data = None

    if existing_rating:
        rating_data = {
            "id": existing_rating.id,
            "rating": existing_rating.rating,
            "feedback": existing_rating.feedback or "",
            "created_at": (
                existing_rating.created_at.strftime(
                    "%d %b %Y %H:%M"
                )
                if existing_rating.created_at
                else ""
            ),
            "updated_at": (
                existing_rating.updated_at.strftime(
                    "%d %b %Y %H:%M"
                )
                if existing_rating.updated_at
                else ""
                
            )
        }

    return jsonify({
        "ok": True,
        "ticket": serialize_ticket(ticket),
        "chat_session": (
            serialize_chat_session(chat_session)
            if chat_session
            else None
        ),
        "already_rated":
            existing_rating is not None,

        "ticket_rating":
            rating_data,
        "comments": [
            serialize_comment(comment)
            for comment in comments
        ]
    }), 200


@csrf.exempt
@customer_blueprint.route(
    "/api/escalate",
    methods=["POST"]
)
@login_required(role="Customer")
def api_escalate():
    """
    Create a support ticket from an IT triage chat session.

    This route:

    1. Validates the triage summary.
    2. Validates the optional ChatSession.
    3. Prevents duplicate ticket creation for one session.
    4. Determines the ticket category and priority.
    5. Creates the Ticket.
    6. Creates the initial triage Comment.
    7. Links the ChatSession to the Ticket.
    8. Links all ChatMessage rows to the Ticket.
    9. Updates the persistent chat stage to ticket_created.
    10. Sends ticket-created and ticket-escalated emails.
    11. Notifies agents and administrators.
    12. Emits ticket, sidebar, analytics and customer refresh events.
    """

    auto_close_waiting_customer_tickets()

    data = request.get_json(
        silent=True
    ) or {}

    # ========================================================
    # REQUEST VALUES
    # ========================================================

    summary = (
        data.get("message")
        or ""
    ).strip()

    subject = (
        data.get("subject")
        or "IT Support Request"
    ).strip()

    raw_session_id = data.get(
        "session_id"
    )

    frontend_category = (
        data.get("category")
        or ""
    ).strip()

    frontend_priority = (
        data.get("priority")
        or ""
    ).strip()

    # ========================================================
    # VALIDATE TRIAGE SUMMARY
    # ========================================================

    if not summary:
        return jsonify({
            "ok": False,
            "reason": "missing_summary",
            "reply": (
                "Please complete the IT triage questions "
                "before creating a support request."
            )
        }), 400

    if len(summary) > 50000:
        return jsonify({
            "ok": False,
            "reason": "summary_too_large",
            "reply": (
                "The triage summary is too large. "
                "Please shorten the support request."
            )
        }), 400

    if not subject:
        subject = "IT Support Request"

    if len(subject) > 255:
        subject = subject[:255]

    # ========================================================
    # VALIDATE OPTIONAL CHAT SESSION
    # ========================================================

    chat_session = None
    session_id = None

    if raw_session_id not in (
        None,
        "",
        0,
        "0"
    ):
        try:
            session_id = int(
                raw_session_id
            )

        except (TypeError, ValueError):
            return jsonify({
                "ok": False,
                "reason": "invalid_session_id",
                "reply": (
                    "The selected chat session is invalid."
                )
            }), 400

        if session_id <= 0:
            return jsonify({
                "ok": False,
                "reason": "invalid_session_id",
                "reply": (
                    "The selected chat session is invalid."
                )
            }), 400

        chat_session = ChatSession.query.filter_by(
            id=session_id,
            user_id=current_user.id
        ).first()

        if not chat_session:
            return jsonify({
                "ok": False,
                "reason": "session_not_found",
                "reply": (
                    "The selected chat session could not "
                    "be found."
                )
            }), 404

        # ----------------------------------------------------
        # PREVENT DUPLICATE ESCALATION
        # ----------------------------------------------------

        if chat_session.ticket_id:
            existing_ticket = Ticket.query.filter_by(
                id=chat_session.ticket_id,
                author_id=current_user.id
            ).first()

            if existing_ticket:
                return jsonify({
                    "ok": False,
                    "reason": "session_already_escalated",
                    "reply": (
                        f"This chat already has support ticket "
                        f"#{existing_ticket.number}."
                    ),
                    "session_id": chat_session.id,
                    **serialize_ticket(existing_ticket)
                }), 409

            # The session refers to a ticket that no longer exists.
            # Remove the stale reference before creating a new ticket.
            chat_session.ticket_id = None

    # ========================================================
    # AUTOMATIC CLASSIFICATION
    # ========================================================

    auto_category, auto_priority = classify_it_issue(
        f"{subject}\n{summary}"
    )

    category_name = (
        frontend_category
        or auto_category
        or "Help and support"
    ).strip()

    priority_name = (
        frontend_priority
        or auto_priority
        or "Medium"
    ).strip()

    # ========================================================
    # FIND CATEGORY
    # ========================================================

    category = Category.query.filter(
        Category.category.ilike(
            category_name
        )
    ).first()

    # Handle names produced by the JavaScript and classifier
    # that may not exactly match database values.
    if not category:
        category_aliases = {
            "account": [
                "Account",
                "Account Access",
                "Login / Account Access",
                "Help and support"
            ],
            "account access": [
                "Account Access",
                "Account",
                "Help and support"
            ],
            "password reset": [
                "Password Reset",
                "Account Access",
                "Account",
                "Help and support"
            ],
            "email": [
                "Email",
                "Software",
                "Help and support"
            ],
            "network": [
                "Network",
                "Help and support"
            ],
            "software": [
                "Software",
                "Help and support"
            ],
            "hardware": [
                "Hardware",
                "Help and support"
            ],
            "security": [
                "Security",
                "Help and support"
            ],
            "general": [
                "General",
                "Help and support"
            ],
            "help and support": [
                "Help and support",
                "General"
            ]
        }

        possible_names = category_aliases.get(
            category_name.lower(),
            [
                category_name,
                "Help and support",
                "General"
            ]
        )

        for possible_name in possible_names:
            category = Category.query.filter(
                Category.category.ilike(
                    possible_name
                )
            ).first()

            if category:
                break

    if not category:
        category = Category.query.order_by(
            Category.id.asc()
        ).first()

    # ========================================================
    # FIND PRIORITY
    # ========================================================

    priority = Priority.query.filter(
        Priority.priority.ilike(
            priority_name
        )
    ).first()

    if not priority:
        priority_aliases = {
            "critical": "Urgent",
            "urgent": "Urgent",
            "high": "High",
            "medium": "Medium",
            "normal": "Medium",
            "low": "Low"
        }

        fallback_priority_name = priority_aliases.get(
            priority_name.lower(),
            "Medium"
        )

        priority = Priority.query.filter(
            Priority.priority.ilike(
                fallback_priority_name
            )
        ).first()

    if not priority:
        priority = Priority.query.filter(
            Priority.priority.ilike(
                "Medium"
            )
        ).first()

    if not priority:
        priority = Priority.query.order_by(
            Priority.id.asc()
        ).first()

    # ========================================================
    # FIND OPEN STATUS
    # ========================================================

    open_status = Status.query.filter(
        Status.status.ilike(
            "Open"
        )
    ).first()

    if not open_status:
        open_status_id = get_open_status_id()

        if open_status_id:
            open_status = db.session.get(
                Status,
                open_status_id
            )

    # ========================================================
    # VALIDATE DATABASE CONFIGURATION
    # ========================================================

    if not category:
        return jsonify({
            "ok": False,
            "reason": "missing_category_configuration",
            "reply": (
                "No ticket categories are configured. "
                "Please contact the administrator."
            )
        }), 500

    if not priority:
        return jsonify({
            "ok": False,
            "reason": "missing_priority_configuration",
            "reply": (
                "No ticket priorities are configured. "
                "Please contact the administrator."
            )
        }), 500

    if not open_status:
        return jsonify({
            "ok": False,
            "reason": "missing_status_configuration",
            "reply": (
                "The Open ticket status is not configured. "
                "Please contact the administrator."
            )
        }), 500

    # ========================================================
    # CREATE DATABASE RECORDS
    # ========================================================

    ticket = None
    first_comment = None
    ticket_created_chat_message = None

    try:
        # ----------------------------------------------------
        # CREATE UNIQUE TICKET NUMBER
        # ----------------------------------------------------

        ticket_number = random_numbers()

        while Ticket.query.filter_by(
            number=ticket_number
        ).first():
            ticket_number = random_numbers()

        # ----------------------------------------------------
        # CREATE TICKET
        # ----------------------------------------------------

        ticket = Ticket(
            number=ticket_number,
            subject=subject,
            body=summary,
            author_id=current_user.id,
            owner_id=None,
            category_id=category.id,
            priority_id=priority.id,
            status_id=open_status.id,
            orig_file=None,
            file_link=None
        )

        db.session.add(
            ticket
        )

        # Generate ticket.id without committing yet.
        db.session.flush()

        # ----------------------------------------------------
        # CREATE FIRST TICKET COMMENT
        # ----------------------------------------------------

        first_comment = Comment(
            comment=summary,
            author_id=current_user.id,
            ticket_id=ticket.id
        )

        db.session.add(
            first_comment
        )

        # Generate first_comment.id before the final commit.
        db.session.flush()

        # ----------------------------------------------------
        # LINK CHAT SESSION TO TICKET
        # ----------------------------------------------------

        if chat_session:
            chat_session.ticket_id = ticket.id
            chat_session.title = subject
            chat_session.issue_type = (
                chat_session.issue_type
                or subject
            )
            chat_session.status = "Ticket Created"
            chat_session.current_stage = "ticket_created"
            chat_session.triage_summary = summary
            chat_session.updated_at = (
                datetime.datetime.utcnow()
            )

            # Keep every saved chat message visible and link it
            # to the newly created support ticket.
            ChatMessage.query.filter(
                ChatMessage.session_id == chat_session.id,
                ChatMessage.user_id == current_user.id
            ).update({
                "ticket_id": ticket.id,
                "escalated": True,
                "customer_visible": True
            }, synchronize_session=False)

            # ------------------------------------------------
            # SAVE TICKET-CREATED MESSAGE IN CHAT HISTORY
            # ------------------------------------------------

            ticket_created_chat_message = ChatMessage(
                user_id=current_user.id,
                session_id=chat_session.id,
                ticket_id=ticket.id,
                role="system",
                message=(
                    f"Support ticket #{ticket.number} was created "
                    f"and sent to the IT support team."
                ),
                faq_matched=False,
                ai_used=False,
                escalated=True,
                guest_user=False,
                customer_visible=True,
                resolution_status="Escalated"
            )

            db.session.add(
                ticket_created_chat_message
            )

        # ----------------------------------------------------
        # COMMIT EVERYTHING AS ONE TRANSACTION
        # ----------------------------------------------------

        db.session.commit()

        db.session.refresh(
            ticket
        )

        db.session.refresh(
            first_comment
        )

        if chat_session:
            db.session.refresh(
                chat_session
            )

        if ticket_created_chat_message:
            db.session.refresh(
                ticket_created_chat_message
            )

    except Exception as error:
        db.session.rollback()

        current_app.logger.exception(
            "Could not create escalated IT support ticket "
            "for customer_id=%s session_id=%s: %s",
            current_user.id,
            session_id,
            error
        )

        return jsonify({
            "ok": False,
            "reason": "ticket_creation_failed",
            "reply": (
                "The support ticket could not be created. "
                "Please try again."
            )
        }), 500

    # ========================================================
    # SEND CUSTOMER EMAILS
    # ========================================================

    created_email_sent = False
    escalated_email_sent = False

    try:
        created_email_sent = bool(
            send_ticket_created_email(
                current_user,
                ticket
            )
        )

    except Exception as error:
        current_app.logger.exception(
            "Ticket-created email raised an error "
            "for ticket_id=%s customer_id=%s: %s",
            ticket.id,
            current_user.id,
            error
        )

    try:
        escalated_email_sent = bool(
            send_ticket_escalated_email(
                current_user,
                ticket
            )
        )

    except Exception as error:
        current_app.logger.exception(
            "Ticket-escalated email raised an error "
            "for ticket_id=%s customer_id=%s: %s",
            ticket.id,
            current_user.id,
            error
        )

    # ========================================================
    # SYSTEM EVENT LOG
    # ========================================================

    log_system_event(
        event_type="Ticket Escalated",
        severity="Info",
        message=(
            f"Ticket #{ticket.number} was created from an "
            f"IT triage chat by customer {current_user.email}. "
            f"Chat session ID: "
            f"{chat_session.id if chat_session else 'None'}. "
            f"Category: "
            f"{ticket.category.category if ticket.category else category_name}. "
            f"Priority: "
            f"{ticket.priority.priority if ticket.priority else priority_name}. "
            f"Ticket-created email result: "
            f"{created_email_sent}. "
            f"Ticket-escalated email result: "
            f"{escalated_email_sent}."
        ),
        user_id=current_user.id,
        ticket_id=ticket.id
    )

    # ========================================================
    # NOTIFY AGENTS AND ADMINISTRATORS
    # ========================================================

    try:
        notify_staff(
            message=(
                f"created a new IT support request "
                f"#{ticket.number}"
            ),
            sender_id=current_user.id,
            ticket_id=ticket.id,
            include_agents=True,
            include_admins=True
        )

    except Exception as error:
        current_app.logger.exception(
            "Staff notification failed for "
            "ticket_id=%s: %s",
            ticket.id,
            error
        )

    # ========================================================
    # BUILD REAL-TIME PAYLOAD
    # ========================================================

    payload = {
        **serialize_ticket(ticket),
        "user_id": current_user.id,
        "session_id": (
            chat_session.id
            if chat_session
            else None
        ),
        "current_stage": (
            chat_session.current_stage
            if chat_session
            else "ticket_created"
        ),
        "reply": (
            f"Ticket #{ticket.number} was created. "
            f"Your IT triage summary has been sent to "
            f"the support team."
        ),
        "created_email_sent": created_email_sent,
        "escalated_email_sent": escalated_email_sent
    }

    # ========================================================
    # SOCKET.IO EVENTS
    # ========================================================

    try:
        emit_ticket_comment(
            ticket,
            first_comment,
            is_attachment=False
        )

        socketio.emit(
            "support_ticket_started",
            payload,
            room=f"user_{current_user.id}"
        )

        socketio.emit(
            "chat_session_updated",
            payload,
            room=f"user_{current_user.id}"
        )

        emit_global_event(
            "ticket_created",
            ticket,
            "Customer created a new IT support request."
        )

        emit_customer_refresh(
            current_user.id,
            "support_ticket_started"
        )

    except Exception as error:
        current_app.logger.exception(
            "Socket event emission failed for "
            "ticket_id=%s session_id=%s: %s",
            ticket.id,
            chat_session.id if chat_session else None,
            error
        )

    # ========================================================
    # RESPONSE
    # ========================================================

    return jsonify({
        "ok": True,
        "reply": payload["reply"],
        "session_id": payload["session_id"],
        "current_stage": payload["current_stage"],
        "created_email_sent": created_email_sent,
        "escalated_email_sent": escalated_email_sent,
        "email_message": (
            "Ticket confirmation and escalation emails "
            "were processed successfully."
            if (
                created_email_sent
                and escalated_email_sent
            )
            else (
                "The support ticket was created, but one "
                "or more email notifications could not "
                "be sent or were disabled by email "
                "preference settings."
            )
        ),
        **serialize_ticket(ticket)
    }), 200

@csrf.exempt
@customer_blueprint.route("/api/support-requests", methods=["GET"])
@login_required(role="Customer")
def api_support_requests():

    tickets = (
        Ticket.query
        .filter(Ticket.author_id == current_user.id)
        .order_by(Ticket.updated_at.desc(), Ticket.created_at.desc())
        .all()
    )

    return jsonify({
        "ok": True,
        "tickets": [
            {
                "id": ticket.id,
                "ticket_number": ticket.number,
                "subject": ticket.subject,
                "status": ticket.status.status if ticket.status else "",
                "priority": ticket.priority.priority if ticket.priority else "",
                "category": ticket.category.category if ticket.category else "",
                "updated_at": ticket.updated_at.strftime("%d %b %Y %H:%M") if ticket.updated_at else "",
                "created_at": ticket.created_at.strftime("%d %b %Y %H:%M") if ticket.created_at else ""
            }
            for ticket in tickets
        ]
    }), 200


@csrf.exempt
@customer_blueprint.route("/api/support-request/<int:ticket_id>", methods=["GET"])
@login_required(role="Customer")
def api_support_request(ticket_id):

    ticket = Ticket.query.filter_by(
        id=ticket_id,
        author_id=current_user.id
    ).first()

    if not ticket:
        return jsonify({
            "ok": False,
            "reason": "not_found"
        }), 404

    comments = (
        Comment.query
        .filter(Comment.ticket_id == ticket.id)
        .order_by(Comment.created_at.asc())
        .all()
    )

    return jsonify({
        "ok": True,
        "ticket": {
            "id": ticket.id,
            "ticket_number": ticket.number,
            "subject": ticket.subject,
            "status": ticket.status.status if ticket.status else "",
            "priority": ticket.priority.priority if ticket.priority else "",
            "category": ticket.category.category if ticket.category else ""
        },
        "comments": [
            serialize_comment(comment)
            for comment in comments
        ]
    }), 200

@csrf.exempt
@customer_blueprint.route("/api/ticket/comment/<int:ticket_id>", methods=["POST"])
def api_ticket_comment(ticket_id):
    if not current_user.is_authenticated:
        return jsonify({"ok": False, "reason": "not_authenticated"}), 401

    ticket = Ticket.query.filter_by(id=ticket_id, author_id=current_user.id).first()

    if not ticket:
        return jsonify({"ok": False, "reason": "not_found"}), 404

    if ticket.status_id == get_closed_status_id():
        return jsonify({"ok": False, "reason": "ticket_closed"}), 400

    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()

    if not message:
        return jsonify({"ok": False, "reason": "empty_message"}), 400

    comment = Comment(
        comment=message,
        author_id=current_user.id,
        ticket_id=ticket.id
    )

    db.session.add(comment)

    open_status = Status.query.filter_by(status="Open").first()

    if open_status:
        ticket.status_id = open_status.id

    ticket.waiting_customer_since = None
    ticket.inactive_reminder_sent = False

    db.session.commit()

    if ticket.owner_id:
        notify_user(
            message="commented on ticket",
            receiver_id=ticket.owner_id,
            sender_id=current_user.id,
            ticket_id=ticket.id
        )
    else:
        notify_staff(
            message="commented on unassigned ticket",
            sender_id=current_user.id,
            ticket_id=ticket.id
        )

    emit_ticket_comment(ticket, comment, is_attachment=False)

    return jsonify({
        "ok": True,
        "comment": serialize_comment(comment)
    }), 200


@csrf.exempt
@customer_blueprint.route("/api/ticket/upload/<int:ticket_id>", methods=["POST"])
def api_ticket_upload(ticket_id):
    if not current_user.is_authenticated:
        return jsonify({"ok": False, "reason": "not_authenticated"}), 401

    ticket = Ticket.query.filter_by(id=ticket_id, author_id=current_user.id).first()

    if not ticket:
        return jsonify({"ok": False, "reason": "not_found"}), 404

    if ticket.status_id == get_closed_status_id():
        return jsonify({"ok": False, "reason": "ticket_closed"}), 400

    file = request.files.get("attachment")

    if not file or not file.filename:
        return jsonify({"ok": False, "reason": "no_file"}), 400

    allowed_exts = {"png", "jpg", "jpeg", "gif", "pdf", "docx", "doc"}

    if "." not in file.filename or file.filename.rsplit(".", 1)[1].lower() not in allowed_exts:
        return jsonify({"ok": False, "reason": "invalid_file_type"}), 400

    if request.content_length and request.content_length > 5 * 1024 * 1024:
        return jsonify({"ok": False, "reason": "file_too_large"}), 400

    original_filename = secure_filename(file.filename)
    _, ext = os.path.splitext(original_filename)
    saved_filename = secure_filename(uuid.uuid4().hex + ext.lower())

    folder = os.path.join(
        path,
        "app",
        "static",
        "uploads",
        "attachments",
        str(current_user.id)
    )

    os.makedirs(folder, exist_ok=True)

    file.save(os.path.join(folder, saved_filename))

    file_url = url_for(
        "customer.download_attachment",
        id=current_user.id,
        filename=saved_filename
    )

    comment_text = (
        "Attachment uploaded: "
        f"<a href='{file_url}' target='_blank'>{original_filename}</a>"
    )

    comment = Comment(
        comment=comment_text,
        author_id=current_user.id,
        ticket_id=ticket.id
    )

    db.session.add(comment)
    db.session.commit()

    if ticket.owner_id:
        notify_user(
            message="uploaded an attachment",
            receiver_id=ticket.owner_id,
            sender_id=current_user.id,
            ticket_id=ticket.id
        )
    else:
        notify_staff(
            message="uploaded an attachment",
            sender_id=current_user.id,
            ticket_id=ticket.id
        )

    emit_ticket_comment(ticket, comment, is_attachment=True)
    

    return jsonify({
        "ok": True,
        "comment": serialize_comment(comment),
        "message": comment_text,
        "file_url": file_url,
        "file_name": original_filename
    }), 200

@csrf.exempt
@customer_blueprint.route("/api/notifications/mark-navbar-read", methods=["POST"])
@login_required(role="Customer")
def mark_navbar_notifications_read():
    Notification.query.filter(
        Notification.receiver_id == current_user.id,
        Notification.seen == False
    ).update({"seen": True})

    db.session.commit()

    socketio.emit(
        "notification_read",
        {
            "receiver_id": current_user.id,
            "notification_id": None
        },
        room=f"user_{current_user.id}"
    )

    socketio.emit("notification_updated", {
        "receiver_id": current_user.id
    })

    socketio.emit("sidebar_counts_updated", {
        "receiver_id": current_user.id
    })

    return jsonify({"ok": True}), 200

@csrf.exempt
@customer_blueprint.route(
    "/api/ticket/reopen/<int:ticket_id>",
    methods=["POST"]
)
@login_required(role="Customer")
def api_ticket_reopen(ticket_id):
    """
    Reopen a closed customer ticket.

    The customer can reopen a ticket only when:

        - the ticket belongs to the logged-in customer;
        - its current status is Closed; and
        - it was closed no more than 30 days ago.

    A successful reopening sends the ticket-reopened email and
    records the attempt through EmailLog.
    """

    ticket = Ticket.query.filter_by(
        id=ticket_id,
        author_id=current_user.id
    ).first()

    if not ticket:
        return jsonify({
            "ok": False,
            "reason": "not_found",
            "message": "Ticket not found."
        }), 404

    if ticket.status_id != get_closed_status_id():
        return jsonify({
            "ok": False,
            "reason": "not_closed",
            "message": "Only closed tickets can be reopened."
        }), 400

    closed_date = (
        ticket.updated_at
        or ticket.created_at
    )

    if closed_date:
        if closed_date.tzinfo is not None:
            closed_date = closed_date.replace(
                tzinfo=None
            )

        days_since_closed = (
            datetime.datetime.utcnow() - closed_date
        ).days

        if days_since_closed > 30:
            return jsonify({
                "ok": False,
                "reason": "reopen_period_expired",
                "message": (
                    "This ticket has been closed for more "
                    "than 30 days. Please create a new "
                    "support request."
                )
            }), 400

    # --------------------------------------------------------
    # REOPEN TICKET
    # --------------------------------------------------------

    ticket.status_id = get_pending_status_id()
    ticket.waiting_customer_since = None
    ticket.inactive_reminder_sent = False

    reopen_message = (
        f"Ticket reopened by customer {current_user.name}."
    )

    comment = Comment(
        comment=reopen_message,
        author_id=current_user.id,
        ticket_id=ticket.id
    )

    db.session.add(comment)
    db.session.commit()

    db.session.refresh(ticket)

    # --------------------------------------------------------
    # SEND TICKET-REOPENED EMAIL
    # --------------------------------------------------------

    email_sent = send_ticket_reopened_email(
        current_user,
        ticket
    )

    if not email_sent:
        current_app.logger.error(
            "Customer ticket-reopened email failed "
            "for ticket_id=%s customer_id=%s",
            ticket.id,
            current_user.id
        )

    # --------------------------------------------------------
    # SYSTEM EVENT
    # --------------------------------------------------------

    log_system_event(
        event_type="Ticket Reopened",
        severity="Info",
        message=(
            f"Ticket #{ticket.number} was reopened "
            f"by customer {current_user.email}. "
            f"Email result: {email_sent}."
        ),
        user_id=current_user.id,
        ticket_id=ticket.id
    )

    # --------------------------------------------------------
    # NOTIFICATIONS
    # --------------------------------------------------------

    if ticket.owner_id:
        notify_user(
            message="reopened ticket",
            receiver_id=ticket.owner_id,
            sender_id=current_user.id,
            ticket_id=ticket.id
        )

    notify_staff(
        message="reopened ticket",
        sender_id=current_user.id,
        ticket_id=ticket.id,
        include_agents=True,
        include_admins=True
    )

    # --------------------------------------------------------
    # REAL-TIME EVENTS
    # --------------------------------------------------------

    emit_ticket_comment(
        ticket,
        comment,
        is_attachment=False
    )

    emit_ticket_system(
        ticket,
        "ticket_reopened",
        reopen_message
    )

    emit_customer_refresh(
        current_user.id,
        "ticket_reopened"
    )

    return jsonify({
        "ok": True,
        "message": reopen_message,
        "email_sent": email_sent,
        "email_message": (
            "A ticket-reopened confirmation email was sent."
            if email_sent
            else (
                "The ticket was reopened, but the confirmation "
                "email could not be sent."
            )
        ),
        **serialize_ticket(ticket)
    }), 200

@csrf.exempt
@customer_blueprint.route(
    "/api/ticket/confirm-solved/<int:ticket_id>",
    methods=["POST"]
)
@login_required(role="Customer")
def api_ticket_confirm_solved(ticket_id):
    ticket = (
        Ticket.query
        .filter_by(
            id=ticket_id,
            author_id=current_user.id
        )
        .first()
    )

    if not ticket:
        return jsonify({
            "ok": False,
            "reason": "not_found",
            "message": "Ticket not found."
        }), 404

    if (
        ticket.status_id
        != get_closed_status_id()
    ):
        return jsonify({
            "ok": False,
            "reason": "not_closed",
            "message": (
                "Only a closed ticket can be "
                "confirmed as solved."
            )
        }), 400

    chat_session = (
        ChatSession.query
        .filter_by(
            ticket_id=ticket.id,
            user_id=current_user.id
        )
        .order_by(
            ChatSession.updated_at.desc()
        )
        .first()
    )

    if chat_session:
        # The customer has pressed Yes, but the process
        # is not complete until feedback is submitted.
        chat_session.status = "Awaiting Feedback"
        chat_session.current_stage = "awaiting_feedback"
        chat_session.updated_at = (
            datetime.datetime.utcnow()
        )

    confirmation_message = (
        "Customer confirmed that the issue was solved. "
        "Waiting for customer feedback."
    )

    existing_confirmation = (
        Comment.query
        .filter(
            Comment.ticket_id == ticket.id,
            Comment.comment
            == confirmation_message
        )
        .first()
    )

    if not existing_confirmation:
        confirmation_comment = Comment(
            comment=confirmation_message,
            author_id=current_user.id,
            ticket_id=ticket.id
        )

        db.session.add(
            confirmation_comment
        )

    try:
        db.session.commit()

    except Exception:
        db.session.rollback()

        current_app.logger.exception(
            "Could not confirm solved ticket_id=%s",
            ticket.id
        )

        return jsonify({
            "ok": False,
            "reason": "database_error",
            "message": (
                "The ticket could not be confirmed. "
                "Please try again."
            )
        }), 500

    # Do not hide ChatMessage records.
    # Do not clear the customer chat.
    # Do not emit ticket_confirmed_solved yet.
    # The customer must first submit a rating.

    return jsonify({
        "ok": True,
        "ticket_id": ticket.id,
        "ticket_number": ticket.number,
        "awaiting_feedback": True,
        "message": (
            "Thank you. Please rate your "
            "support experience."
        )
    }), 200


@csrf.exempt
@customer_blueprint.route("/api/chat/talk-to-support", methods=["POST"])
def api_talk_to_support():
    return api_escalate()


# ============================================================
# LEGACY FORM ROUTES STILL SUPPORTED
# ============================================================

@customer_blueprint.route(
    "/ticket/reopen/<int:id>",
    methods=["POST"]
)
@login_required(role="Customer")
def reopen_ticket(id):
    response = api_ticket_reopen(id)

    if isinstance(response, tuple):
        response_object = response[0]
        status_code = response[1]
    else:
        response_object = response
        status_code = response.status_code

    data = response_object.get_json() or {}

    if data.get("ok"):
        if data.get("email_sent"):
            flash(
                "Ticket reopened successfully. "
                "A confirmation email was sent.",
                "success"
            )
        else:
            flash(
                "Ticket reopened successfully, but the "
                "confirmation email could not be sent.",
                "warning"
            )

    else:
        flash(
            data.get("message")
            or "Ticket could not be reopened.",
            "warning"
        )

    if status_code >= 400:
        return redirect(
            url_for(
                "customer.view_ticket",
                id=id
            )
        )

    return redirect(
        url_for("customer.chat")
    )

@customer_blueprint.route("/ticket/confirm-solved/<int:id>", methods=["POST"])
@login_required(role="Customer")
def confirm_ticket_solved(id):
    api_ticket_confirm_solved(id)

    flash("Thank you for confirming your issue was resolved.", "primary")
    return redirect(url_for("customer.my_tickets"))


@customer_blueprint.route("/notification/open/<int:nid>", methods=["GET"])
@login_required(role="Customer")
def open_notification(nid):
    notification = Notification.query.get_or_404(nid)

    if notification.receiver_id != current_user.id:
        flash("Unauthorized notification.", "danger")
        return redirect(url_for("customer.notifications"))

    notification.seen = True
    notification.opened = True
    db.session.commit()

    socketio.emit(
        "notification_read",
        {
            "receiver_id": current_user.id,
            "notification_id": notification.id
        },
        room=f"user_{current_user.id}"
    )

    socketio.emit("notification_updated", {"receiver_id": current_user.id})
    socketio.emit("sidebar_counts_updated", {"receiver_id": current_user.id})

    if notification.ticket_id:
        return redirect(url_for("customer.view_ticket", id=notification.ticket_id))

    if notification.url and notification.url != "#":
        return redirect(notification.url)

    return redirect(url_for("customer.notifications"))

@customer_blueprint.route("/knowledge-base", methods=["GET"])
@login_required(role="Customer")
def knowledge_base():
    category_id = request.args.get("category_id", type=int)
    search = (request.args.get("search") or "").strip()

    query = KnowledgeArticle.query.filter_by(is_active=True)

    if category_id:
        query = query.filter(KnowledgeArticle.category_id == category_id)

    if search:
        query = query.filter(
            or_(
                KnowledgeArticle.title.ilike(f"%{search}%"),
                KnowledgeArticle.content.ilike(f"%{search}%"),
                KnowledgeArticle.tags.ilike(f"%{search}%")
            )
        )

    articles = (
        query
        .order_by(KnowledgeArticle.created_at.desc())
        .all()
    )

    return render_template(
        "customer/knowledge_base.html",
        articles=articles,
        categories=Category.query.order_by(Category.category.asc()).all(),
        selected_category_id=category_id,
        search=search
    )


@customer_blueprint.route("/knowledge-base/<int:id>", methods=["GET"])
@login_required(role="Customer")
def view_knowledge_article(id):
    article = KnowledgeArticle.query.get_or_404(id)

    if not article.is_active:
        flash("This article is not available.", "warning")
        return redirect(url_for("customer.knowledge_base"))

    article.view_count = (article.view_count or 0) + 1
    db.session.commit()

    return render_template(
        "customer/view_knowledge_article.html",
        article=article
    )


def get_or_create_email_preference(user_id):
    """
    Return the email preference record belonging to one customer.

    A default preference row is created for existing customers who
    registered before email preferences were introduced.
    """

    preference = EmailPreference.query.filter_by(
        user_id=user_id
    ).first()

    if preference:
        return preference

    try:
        preference = EmailPreference(
            user_id=user_id,
            ticket_updates=True,
            security_emails=True,
            marketing_emails=False,
            satisfaction_emails=True,
            created_at=datetime.datetime.utcnow(),
            updated_at=datetime.datetime.utcnow()
        )

        db.session.add(preference)
        db.session.commit()

        return preference

    except Exception as error:
        db.session.rollback()

        current_app.logger.exception(
            "EMAIL PREFERENCE CREATE ERROR: "
            "user_id=%s error=%s",
            user_id,
            error
        )

        # Another request may have created the row at the same time.
        preference = EmailPreference.query.filter_by(
            user_id=user_id
        ).first()

        if preference:
            return preference

        raise


@customer_blueprint.route(
    "/email-preferences",
    methods=["GET", "POST"]
)
@login_required(role="Customer")
def email_preferences():
    """
    Display and update optional customer email preferences.

    Mandatory authentication and security messages remain enabled:
        - email verification
        - login OTP
        - password reset
        - password changed confirmation
    """

    try:
        preference = get_or_create_email_preference(
            current_user.id
        )

    except Exception:
        flash(
            "Your email preference settings could not be loaded.",
            "danger"
        )

        return redirect(
            url_for("customer.dashboard")
        )

    if request.method == "POST":
        try:
            # A checkbox is present in request.form only when checked.
            preference.ticket_updates = (
                request.form.get("ticket_updates") == "on"
            )

            preference.satisfaction_emails = (
                request.form.get("satisfaction_emails") == "on"
            )

            preference.marketing_emails = (
                request.form.get("marketing_emails") == "on"
            )

            # Security emails are mandatory.
            preference.security_emails = True

            preference.updated_at = (
                datetime.datetime.utcnow()
            )

            db.session.commit()

            log_system_event(
                event_type="Email Preferences Updated",
                severity="Info",
                message=(
                    f"Email preferences updated by "
                    f"{current_user.email}. "
                    f"Ticket updates: "
                    f"{preference.ticket_updates}. "
                    f"Security emails: "
                    f"{preference.security_emails}. "
                    f"Satisfaction emails: "
                    f"{preference.satisfaction_emails}. "
                    f"Marketing emails: "
                    f"{preference.marketing_emails}."
                ),
                user_id=current_user.id
            )

            flash(
                "Your email preferences have been saved.",
                "success"
            )

            return redirect(
                url_for(
                    "customer.email_preferences"
                )
            )

        except Exception as error:
            db.session.rollback()

            current_app.logger.exception(
                "EMAIL PREFERENCE UPDATE ERROR: "
                "user_id=%s error=%s",
                current_user.id,
                error
            )

            flash(
                "Your email preferences could not be saved. "
                "Please try again.",
                "danger"
            )

    return render_template(
        "customer/email_preferences.html",
        preference=preference
    )
