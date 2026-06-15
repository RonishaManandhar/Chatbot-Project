
from flask import Blueprint, current_app, render_template as _render, send_file, redirect, request, url_for, flash, jsonify, session
from flask_login import current_user
from flask_socketio import join_room
from app.socketio_ext import socketio
from openai import OpenAI
import os
import datetime
import uuid

from sqlalchemy import desc, or_
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash

from app.exts import db, csrf
from app.customer.forms import TicketForm, UpdateTicketForm, CommentForm, ChangeProfileForm, ChangePasswordForm
from app.models import User, Ticket, Comment, Notification, FAQ, ChatMessage, Category, Status, ChatbotSetting, KnowledgeArticle, CustomerSatisfaction, MaintenanceSetting, SystemEvent
from app.utils.generate_digits import random_numbers
from app.utils.authorized_role import login_required


customer_blueprint = Blueprint("customer", __name__)
path = os.getcwd()
GUEST_QUERY_LIMIT = 3
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


def get_active_ticket_for_user(user_id):
    open_id = get_open_status_id()
    pending_id = get_pending_status_id()
    waiting_id = get_waiting_customer_status_id()
    escalated_id = get_escalated_status_id()

    active_status_ids = [open_id, pending_id]

    if waiting_id:
        active_status_ids.append(waiting_id)

    if escalated_id:
        active_status_ids.append(escalated_id)

    return (
        Ticket.query
        .filter(Ticket.author_id == user_id)
        .filter(Ticket.status_id.in_(active_status_ids))
        .order_by(desc(Ticket.updated_at), desc(Ticket.created_at))
        .first()
    )

def auto_close_waiting_customer_tickets():
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
                ticket.waiting_customer_since = ticket.updated_at.replace(tzinfo=None)
            elif ticket.created_at:
                ticket.waiting_customer_since = ticket.created_at.replace(tzinfo=None)
            else:
                ticket.waiting_customer_since = now

        waiting_hours = (
            now - ticket.waiting_customer_since.replace(tzinfo=None)
        ).total_seconds() / 3600

        if waiting_hours >= 48:
            ticket.status_id = closed_id

            close_comment = Comment(
                comment="Ticket automatically closed because the customer did not respond within 48 hours.",
                author_id=ticket.owner_id or ticket.author_id,
                ticket_id=ticket.id
            )

            db.session.add(close_comment)

            ChatMessage.query.filter(
                ChatMessage.user_id == ticket.author_id
            ).update({
                "customer_visible": False
            })

            socketio.emit(
                "ticket_closed",
                {
                    **serialize_ticket(ticket),
                    "message": "Ticket automatically closed due to customer inactivity."
                },
                room=f"ticket_{ticket.id}"
            )

            socketio.emit("global_ticket_updated", serialize_ticket(ticket))
            socketio.emit("sidebar_counts_updated", serialize_ticket(ticket))
            socketio.emit("notification_updated", serialize_ticket(ticket))

            emit_customer_refresh(ticket.author_id, "ticket_auto_closed")

    db.session.commit()


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

    socketio.emit(event_name, payload, room=f"ticket_{ticket.id}")
    socketio.emit(event_name, payload)
    socketio.emit("global_ticket_updated", payload)
    socketio.emit("sidebar_counts_updated", payload)
    socketio.emit("notification_updated", payload)
    socketio.emit("analytics_updated", payload)

    if ticket.author_id:
        emit_customer_refresh(ticket.author_id, event_name)


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
    tickets = (
        Ticket.query
        .filter(Ticket.author_id == current_user.id)
        .order_by(desc(Ticket.created_at))
        .all()
    )

    form = TicketForm()
    active_ticket = get_active_ticket_for_user(current_user.id)

    return render_template(
        "customer/my_tickets.html",
        form=form,
        tickets=tickets,
        active_ticket=active_ticket
    )


@customer_blueprint.route("/create-ticket", methods=["GET", "POST"])
@login_required(role="Customer")
def create_ticket():
    auto_close_waiting_customer_tickets()
    active_ticket = get_active_ticket_for_user(current_user.id)

    if active_ticket:
        flash(
            f"You already have an active support ticket #{active_ticket.number}. Please continue that chat first.",
            "warning"
        )
        return redirect(url_for("customer.chat_page"))

    form = TicketForm()

    if form.validate_on_submit():
        file = form.attachment.data
        attachment = None
        original_f = None

        if file and file.filename:
            folder_id = os.path.join(path, "app/static/uploads/attachments", str(current_user.id))
            os.makedirs(folder_id, exist_ok=True)

            original_f = secure_filename(file.filename)
            _, ext = os.path.splitext(original_f)
            attachment = secure_filename(uuid.uuid4().hex + ext.lower())

            file.save(os.path.join(folder_id, attachment))

        ticket = Ticket(
            number=random_numbers(),
            subject=form.subject.data,
            body=form.body.data,
            author_id=current_user.id,
            owner_id=None,
            category_id=int(form.category.data),
            priority_id=1,
            status_id=get_open_status_id(),
            orig_file=original_f,
            file_link=attachment
        )

        db.session.add(ticket)
        db.session.commit()

        notify_staff(
            message="created a new support ticket",
            sender_id=current_user.id,
            ticket_id=ticket.id
        )

        emit_global_event(
            "ticket_created",
            ticket,
            "Customer created a new support ticket."
        )

        flash("Ticket has been created. You can continue in chat.", "primary")
        return redirect(url_for("customer.chat_page"))

    return render_template("customer/my_tickets.html", form=form, tickets=[], active_ticket=None)


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

    if form.validate_on_submit():
        if ticket.status_id == get_closed_status_id():
            flash("Closed tickets cannot be edited.", "warning")
            return redirect(url_for("customer.view_ticket", id=id))

        if ticket.category_id != int(form.category.data) and ticket.owner_id is not None:
            notify_user(
                message="updated category on ticket",
                receiver_id=ticket.owner_id,
                sender_id=current_user.id,
                ticket_id=ticket.id
            )

        ticket.category_id = int(form.category.data)
        db.session.commit()

        emit_global_event(
            "ticket_updated",
            ticket,
            "Customer updated ticket category."
        )

        flash("Ticket has been updated.", "primary")
        return redirect(url_for("customer.view_ticket", id=id))
    
    existing_rating = CustomerSatisfaction.query.filter_by(
        ticket_id=ticket.id,
        customer_id=current_user.id
    ).first()

    return render_template(
    "customer/view_ticket.html",
    form=form,
    comment_form=comment_form,
    ticket=ticket,
    comments=comments,
    existing_rating=existing_rating
)


@customer_blueprint.route("/comment-ticket/<int:id>", methods=["GET", "POST"])
@login_required(role="Customer")
def comment_ticket(id):
    return redirect(url_for("customer.chat_page"))


@customer_blueprint.route("/faqs", methods=["GET"])
@login_required(role="Customer")
def faqs():
    categories = Category.query.order_by(Category.category.asc()).all()
    return render_template("customer/faqs.html", categories=categories)


@customer_blueprint.route("/widget-demo", methods=["GET"])
def widget_demo():
    return render_template("widget/demo.html")


@customer_blueprint.route("/chat", methods=["GET"])
@login_required(role="Customer")
def chat_page():
    auto_close_waiting_customer_tickets()
    return render_template("customer/chat.html")


# ============================================================
# PROFILE / ACCOUNT
# ============================================================

@customer_blueprint.route("/my-profile", methods=["GET", "POST"])
@login_required(role="Customer")
def my_profile():
    user = User.query.filter(User.id == current_user.id).first()
    form = ChangeProfileForm()

    if form.validate_on_submit():
        file = form.profile.data

        if file and file.filename:
            filename, ext = os.path.splitext(file.filename)
            profile = secure_filename(str(user.id) + ext)

            file.save(os.path.join(current_app.config["PROFILE_DIR"], profile))

            user.image = profile
            db.session.commit()

            emit_global_event(
                "profile_updated",
                message="Customer profile updated"
            )

            flash("Your profile has been changed.", "primary")
            return redirect(url_for("customer.my_profile"))

    return render_template("customer/my_profile.html", form=form, user=user)


@customer_blueprint.route("/change-password", methods=["GET", "POST"])
@login_required(role="Customer")
def change_password():
    user = User.query.filter(User.id == current_user.id).first()
    form = ChangePasswordForm()

    if form.validate_on_submit():
        user.password = generate_password_hash(form.password.data)
        db.session.commit()
        log_system_event(
            event_type="Password Changed",
            severity="Info",
            message=f"Password changed for {user.email}.",
            user_id=user.id
        )

        emit_global_event(
            "password_updated",
            message="Customer password updated"
        )

        flash("Your password has been changed.", "primary")
        return redirect(url_for("customer.change_password"))

    return render_template("customer/change_password.html", form=form)


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


@customer_blueprint.route("/ticket/delete/<int:uid>/<int:tid>", methods=["GET", "POST"])
@login_required(role="Customer")
def delete_ticket(uid, tid):
    ticket = Ticket.query.get_or_404(tid)

    if ticket.author_id != current_user.id:
        flash("Unauthorized access.", "danger")
        return redirect(url_for("customer.my_tickets"))

    if request.method == "POST":
        ticket_id = ticket.id
        ticket_number = ticket.number

        if ticket.file_link:
            folder_id = os.path.join(path, "app/static/uploads/attachments", str(uid))
            file_path = os.path.join(folder_id, ticket.file_link)

            if os.path.exists(file_path):
                os.remove(file_path)

        db.session.delete(ticket)
        db.session.commit()

        payload = {
            "ticket_id": ticket_id,
            "ticket_number": ticket_number,
            "message": "Ticket deleted by customer."
        }

        socketio.emit("ticket_deleted", payload)
        socketio.emit("global_ticket_updated", payload)
        socketio.emit("sidebar_counts_updated", payload)
        socketio.emit("notification_updated", payload)
        socketio.emit("analytics_updated", payload)

        emit_customer_refresh(current_user.id, "ticket_deleted")

        flash("Ticket has been deleted.", "primary")
        return redirect(url_for("customer.my_tickets"))

    return redirect(url_for("customer.view_ticket", id=tid))

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

    existing_rating = CustomerSatisfaction.query.filter_by(
        ticket_id=ticket.id,
        customer_id=current_user.id
    ).first()

    if existing_rating:
        existing_rating.rating = rating
        existing_rating.feedback = feedback
    else:
        satisfaction = CustomerSatisfaction(
            ticket_id=ticket.id,
            customer_id=current_user.id,
            rating=rating,
            feedback=feedback
        )

        db.session.add(satisfaction)

    db.session.commit()

    flash("Thank you for your feedback.", "success")
    return redirect(url_for("customer.view_ticket", id=ticket.id))
# ============================================================
# AI / FAQ HELPERS
# ============================================================

def find_related_faqs(user_text: str, limit=5):
    text = (user_text or "").strip().lower()

    if not text:
        return []

    words = [
        word.strip()
        for word in text.replace("?", " ").replace(",", " ").split()
        if len(word.strip()) >= 3
    ]

    faqs = (
        FAQ.query
        .filter(FAQ.is_active == True)
        .order_by(FAQ.id.desc())
        .all()
    )

    scored = []

    for faq in faqs:
        question = (faq.question or "").lower()
        answer = (faq.answer or "").lower()
        tags = (faq.tags or "").lower()
        category = faq.category.category.lower() if faq.category else ""

        score = 0

        if text in question:
            score += 10

        if text in tags:
            score += 8

        if text in category:
            score += 6

        for word in words:
            if word in question:
                score += 4
            if word in tags:
                score += 3
            if word in category:
                score += 2
            if word in answer:
                score += 1

        if score > 0:
            scored.append((score, faq))

    scored.sort(key=lambda item: item[0], reverse=True)

    return [
        {
            "id": faq.id,
            "question": faq.question,
            "answer": faq.answer,
            "category": faq.category.category if faq.category else "",
            "tags": faq.tags or ""
        }
        for score, faq in scored[:limit]
    ]

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
    ticket_id=None
):
    if not user_id:
        return None

    try:
        chat = ChatMessage(
            user_id=user_id,
            ticket_id=ticket_id,
            role=role,
            message=message,
            faq_matched=faq_matched,
            ai_used=ai_used,
            escalated=escalated,
            guest_user=False,
            customer_visible=customer_visible
        )

        db.session.add(chat)
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
    user_id = current_user.id if current_user.is_authenticated else None

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
@customer_blueprint.route("/api/chat/resolution", methods=["POST"])
def api_chat_resolution():
    data = request.get_json(silent=True) or {}

    solved = data.get("solved") == True
    source_type = (data.get("source_type") or "").strip()
    original_message = (data.get("original_message") or "").strip()

    user_id = current_user.id if current_user.is_authenticated else None

    if solved:
        if user_id:
            ChatMessage.query.filter(
                ChatMessage.user_id == user_id,
                ChatMessage.customer_visible == True,
                ChatMessage.resolution_status == "Pending"
            ).update({
                "resolution_status": "Solved",
                "customer_visible": False
            })

            db.session.commit()

            emit_customer_chat_event(
                user_id,
                "customer_chat_cleared",
                {
                    "message": "✅ Thank you. I’m glad your issue was solved. You can start a new chat anytime."
                }
            )

        return jsonify({
            "ok": True,
            "cleared": True,
            "message": "✅ Thank you. I’m glad your issue was solved. You can start a new chat anytime."
        }), 200

    if user_id:
        ChatMessage.query.filter(
            ChatMessage.user_id == user_id,
            ChatMessage.customer_visible == True,
            ChatMessage.resolution_status == "Pending"
        ).update({
            "resolution_status": "Not Solved"
        })

        db.session.commit()

    if source_type == "faq":
        progress_message = "Okay, I’ll try the AI assistant for you."

        if user_id:
            progress_chat = save_chat_message(
                user_id=user_id,
                role="system",
                message=progress_message
            )

            emit_customer_chat_event(
                user_id,
                "customer_resolution_progress",
                {
                    "source_type": "faq",
                    "original_message": original_message,
                    "message": progress_message,
                    "chat": serialize_chat_message(progress_chat)
                }
            )

        return jsonify({
            "ok": True,
            "next_step": "ai",
            "message": progress_message,
            "original_message": original_message
        }), 200

    if user_id:
        emit_customer_chat_event(
            user_id,
            "customer_human_prompt",
            {
                "original_message": original_message,
                "message": "Would you like to talk to human support?"
            }
        )

    return jsonify({
        "ok": True,
        "next_step": "human",
        "message": "Would you like to talk to human support?",
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
@customer_blueprint.route("/api/ticket/comments/<int:ticket_id>", methods=["GET"])
def api_ticket_comments(ticket_id):
    if not current_user.is_authenticated:
        return jsonify({"ok": False, "reason": "not_authenticated"}), 401

    ticket = Ticket.query.filter_by(id=ticket_id, author_id=current_user.id).first()

    if not ticket:
        return jsonify({"ok": False, "reason": "not_found"}), 404

    comments = (
        Comment.query
        .filter(Comment.ticket_id == ticket.id)
        .order_by(Comment.created_at.asc())
        .all()
    )

    return jsonify({
        "ok": True,
        "ticket": serialize_ticket(ticket),
        "comments": [serialize_comment(c) for c in comments]
    }), 200


@csrf.exempt
@customer_blueprint.route("/api/escalate", methods=["POST"])
def api_escalate():
    auto_close_waiting_customer_tickets()
    if not current_user.is_authenticated:
        return jsonify({
            "ok": False,
            "needs_login": True,
            "reply": "Please login or sign up to talk to a support agent."
        }), 200

    data = request.get_json(silent=True) or {}

    last_message = (
        data.get("message") or ""
    ).strip() or "Customer requested live support."

    existing_ticket = get_active_ticket_for_user(current_user.id)

    if existing_ticket:
        emit_customer_chat_event(
            current_user.id,
            "support_ticket_started",
            {
                **serialize_ticket(existing_ticket),
                "reply": (
                    f"You already have an active support ticket "
                    f"#{existing_ticket.number}. Reconnecting you now..."
                )
            }
        )

        return jsonify({
            "ok": True,
            "already_exists": True,
            "reply": (
                f"You already have an active support ticket "
                f"#{existing_ticket.number}. Reconnecting you now..."
            ),
            **serialize_ticket(existing_ticket)
        }), 200

    ticket = Ticket(
        number=random_numbers(),
        subject="Live Support Request",
        body=last_message,
        author_id=current_user.id,
        owner_id=None,
        category_id=1,
        priority_id=2,
        status_id=get_open_status_id(),
        orig_file=None,
        file_link=None
    )

    db.session.add(ticket)
    db.session.commit()

    previous_ai_messages = (
        ChatMessage.query
        .filter(ChatMessage.user_id == current_user.id)
        .filter(ChatMessage.customer_visible == True)
        .filter(ChatMessage.resolution_status == "Not Solved")
        .order_by(ChatMessage.created_at.asc())
        .all()
    )

    context_lines = []

    for msg in previous_ai_messages:
        role_name = "Customer" if msg.role == "user" else "AI Assistant"
        context_lines.append(
            f"<strong>{role_name}:</strong> {msg.message}"
        )

    first_comment_text = last_message

    if context_lines:
        first_comment_text = (
            "<strong>Current AI / FAQ Conversation</strong><br><br>" +
            "<br>".join(context_lines) +
            "<br><br><strong>Support request:</strong> " +
            last_message
        )

    first_comment = Comment(
        comment=first_comment_text,
        author_id=current_user.id,
        ticket_id=ticket.id
    )

    db.session.add(first_comment)
    db.session.commit()
    
    ChatMessage.query.filter(
        ChatMessage.user_id == current_user.id,
        ChatMessage.customer_visible == True
    ).update({
        "customer_visible": False
    })

    db.session.commit()

    notify_staff(
        message="created a new support ticket",
        sender_id=current_user.id,
        ticket_id=ticket.id
    )

    emit_ticket_comment(ticket, first_comment, is_attachment=True)

    payload = {
        **serialize_ticket(ticket),
        "user_id": current_user.id,
        "reply": (
            f"Ticket #{ticket.number} created. "
            f"Waiting for a support agent to join..."
        )
    }

    socketio.emit(
        "support_ticket_started",
        payload,
        room=f"user_{current_user.id}"
    )

    socketio.emit(
        "global_ticket_updated",
        {
            **serialize_ticket(ticket),
            "message": "Customer started a support ticket."
        }
    )

    socketio.emit(
        "sidebar_counts_updated",
        {
            **serialize_ticket(ticket),
            "message": "Customer started a support ticket."
        }
    )

    socketio.emit(
        "notification_updated",
        {
            **serialize_ticket(ticket),
            "message": "Customer started a support ticket."
        }
    )

    socketio.emit(
        "analytics_updated",
        {
            **serialize_ticket(ticket),
            "message": "Customer started a support ticket."
        }
    )

    emit_customer_refresh(current_user.id, "support_ticket_started")

    return jsonify({
        "ok": True,
        "reply": payload["reply"],
        **serialize_ticket(ticket)
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
@customer_blueprint.route("/api/ticket/reopen/<int:ticket_id>", methods=["POST"])
def api_ticket_reopen(ticket_id):
    if not current_user.is_authenticated:
        return jsonify({"ok": False, "reason": "not_authenticated"}), 401

    ticket = Ticket.query.filter_by(
        id=ticket_id,
        author_id=current_user.id
    ).first()

    if not ticket:
        return jsonify({"ok": False, "reason": "not_found"}), 404

    if ticket.status_id != get_closed_status_id():
        return jsonify({"ok": False, "reason": "not_closed"}), 400

    closed_date = ticket.updated_at or ticket.created_at

    if closed_date:
        closed_date = closed_date.replace(tzinfo=None)

        days_since_closed = (
            datetime.datetime.utcnow() - closed_date
        ).days

        if days_since_closed > 30:
            return jsonify({
                "ok": False,
                "reason": "reopen_period_expired",
                "message": "This ticket has been closed for more than 30 days. Please create a new support request."
            }), 400

    ticket.status_id = get_pending_status_id()

    message = f"Ticket reopened by customer {current_user.name}."

    comment = Comment(
        comment=message,
        author_id=current_user.id,
        ticket_id=ticket.id
    )

    db.session.add(comment)
    db.session.commit()

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

    emit_ticket_comment(ticket, comment, is_attachment=False)
    emit_ticket_system(ticket, "ticket_reopened", message)
    emit_customer_refresh(current_user.id, "ticket_reopened")

    return jsonify({
        "ok": True,
        "message": message,
        **serialize_ticket(ticket)
    }), 200

@csrf.exempt
@customer_blueprint.route("/api/ticket/confirm-solved/<int:ticket_id>", methods=["POST"])
def api_ticket_confirm_solved(ticket_id):
    if not current_user.is_authenticated:
        return jsonify({"ok": False, "reason": "not_authenticated"}), 401

    ticket = Ticket.query.filter_by(
        id=ticket_id,
        author_id=current_user.id
    ).first()

    if not ticket:
        return jsonify({"ok": False, "reason": "not_found"}), 404

    if ticket.status_id != get_closed_status_id():
        return jsonify({"ok": False, "reason": "not_closed"}), 400

    ChatMessage.query.filter(
        ChatMessage.user_id == current_user.id
    ).update({
        "customer_visible": False
    })

    db.session.commit()

    clear_payload = {
        "user_id": current_user.id,
        "ticket_id": ticket.id,
        "ticket_number": ticket.number,
        "message": "✅ Thank you. Your issue has been marked as solved. You can start a new chat anytime."
    }

    socketio.emit(
        "customer_chat_cleared",
        clear_payload,
        room=f"user_{current_user.id}"
    )

    socketio.emit(
        "ticket_confirmed_solved",
        clear_payload,
        room=f"ticket_{ticket.id}"
    )

    socketio.emit(
        "global_ticket_updated",
        clear_payload
    )

    socketio.emit(
        "sidebar_counts_updated",
        clear_payload
    )

    socketio.emit(
        "analytics_updated",
        clear_payload
    )

    emit_customer_refresh(current_user.id, "ticket_confirmed_solved")

    return jsonify({
        "ok": True,
        "message": clear_payload["message"]
    }), 200


@csrf.exempt
@customer_blueprint.route("/api/chat/talk-to-support", methods=["POST"])
def api_talk_to_support():
    return api_escalate()


# ============================================================
# LEGACY FORM ROUTES STILL SUPPORTED
# ============================================================

@customer_blueprint.route("/ticket/reopen/<int:id>", methods=["POST"])
@login_required(role="Customer")
def reopen_ticket(id):
    response = api_ticket_reopen(id)

    if isinstance(response, tuple):
        data = response[0].get_json()
    else:
        data = response.get_json()

    if data.get("ok"):
        flash("Ticket reopened successfully.", "primary")
    else:
        flash(
            data.get("message") or "Ticket could not be reopened.",
            "warning"
        )

    return redirect(url_for("customer.chat_page"))

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
# ============================================================
# SOCKET ROOMS
# ============================================================
@socketio.on("join_ticket_room")
def join_ticket_room(data):
    try:
        if not current_user.is_authenticated:
            return

        ticket_id = data.get("ticket_id")

        if not ticket_id:
            return

        ticket = Ticket.query.filter_by(
            id=int(ticket_id),
            author_id=current_user.id
        ).first()

        if not ticket:
            return

        room = f"ticket_{ticket.id}"
        join_room(room)

        print(f"✅ Customer joined ticket room: {room}")

    except Exception as e:
        print("SOCKET ROOM ERROR:", e)


@socketio.on("join_notification_room")
def join_notification_room(data):
    try:
        if not current_user.is_authenticated:
            return

        user_id = str(data.get("user_id"))

        if user_id != str(current_user.id):
            return

        room = f"user_{current_user.id}"
        join_room(room)

        print(f"✅ Customer joined user room: {room}")

    except Exception as e:
        print("USER ROOM ERROR:", e)