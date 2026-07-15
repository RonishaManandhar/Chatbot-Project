from flask import (
    Blueprint,
    current_app,
    render_template as _render,
    send_file,
    send_from_directory,
    redirect,
    request,
    url_for,
    flash,
    jsonify,
    Response,
    abort
)
from app.utils.system_events import (
    log_system_event
)
from flask_login import current_user
from datetime import datetime
from flask_socketio import join_room
from sqlalchemy import or_, desc, text, func
from app.admin.forms import (
    ChangeEmailForm, TicketForm, UpdateTicketForm, CommentForm, CategoryForm, PriorityForm,
    UserForm, UpdateRoleForm, ChangeProfileForm, ChangePasswordForm, FAQForm, KnowledgeArticleForm
)

from app.models import User, Ticket, Category, Priority, Status, Comment, Notification, FAQ, ChatMessage, AgentReport, ChatbotSetting, KnowledgeArticle, AgentSolution, CustomerSatisfaction, SystemEvent, MaintenanceSetting
from app.utils.generate_digits import random_numbers
from app.utils.authorized_role import login_required
from app.exts import db, csrf
from app.socketio_ext import socketio
from app.models import EmailLog

from werkzeug.utils import secure_filename
from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)
from app.services.email_service import (
    send_ticket_reply_email,
    send_ticket_created_email,
    send_ticket_closed_email,
    send_satisfaction_email,
    send_ticket_assigned_email,
    send_ticket_reassigned_email,
    send_ticket_escalated_email,
    send_ticket_reopened_email,
    send_ticket_deleted_email
)

from sqlalchemy import desc, or_, func

import datetime
import shutil
import uuid
import os
import csv
import html
import io



admin_blueprint = Blueprint("admin", __name__)
path = os.getcwd()


# ============================================================
# TEMPLATE HELPER
# ============================================================

def render_template(*args, **kwargs):
    notifications = (
        Notification.query
        .filter(Notification.receiver_id == current_user.id)
        .filter(Notification.seen == False)
        .order_by(desc(Notification.created_at))
        .all()
    )

    year = datetime.date.today().year

    escalated_status = Status.query.filter_by(status="Escalated").first()
    escalated_count = 0

    if escalated_status:
        escalated_count = (
            Ticket.query
            .filter(Ticket.status_id == escalated_status.id)
            .count()
        )

    excluded_status_ids = [
        status_id
        for status_id in [
            get_closed_status_id(),
            get_solved_status_id()
        ]
        if status_id is not None
    ]

    active_chat_query = Ticket.query

    if excluded_status_ids:
        active_chat_query = active_chat_query.filter(
            ~Ticket.status_id.in_(
                excluded_status_ids
            )
        )

    active_chat_count = active_chat_query.count()

    agent_report_count = (
        AgentReport.query
        .filter(AgentReport.status != "Closed")
        .count()
    )

    ai_review_count = (
        ChatMessage.query
        .filter(ChatMessage.role == "assistant")
        .filter(ChatMessage.review_status == "Pending")
        .count()
    )

    ai_training_case_count = (
        ChatMessage.query
        .filter(ChatMessage.role == "assistant")
        .filter(
            or_(
                ChatMessage.resolution_status == "Not Solved",
                ChatMessage.escalated == True,
                ChatMessage.review_status == "Rejected"
            )
        )
        .count()
    )

    ai_repeated_question_count = (
        db.session.query(ChatMessage.message)
        .filter(ChatMessage.role == "user")
        .group_by(ChatMessage.message)
        .having(func.count(ChatMessage.id) > 1)
        .count()
    )

    ai_training_total_count = (
        ai_review_count
        + ai_training_case_count
        + ai_repeated_question_count
    )

    faq_suggestion_count = (
        ChatMessage.query
        .filter(ChatMessage.role == "assistant")
        .filter(ChatMessage.resolution_status == "Not Solved")
        .count()
    )

    inactive_article_count = (
        KnowledgeArticle.query
        .filter(KnowledgeArticle.is_active == False)
        .count()
    )

    knowledge_management_total_count = (
        faq_suggestion_count
        + inactive_article_count
    )

    pending_agent_solution_count = (
        AgentSolution.query
        .filter(AgentSolution.status == "Pending")
        .count()
    )

    agent_knowledge_total_count = pending_agent_solution_count

    warning_security_event_count = (
        SystemEvent.query
        .filter(SystemEvent.severity.in_(["Warning", "Critical"]))
        .count()
    )

    maintenance_active_count = 1 if is_maintenance_active() else 0

    system_operations_total_count = (
        warning_security_event_count
        + maintenance_active_count
    )

    support_operations_total_count = (
        active_chat_count
        + escalated_count
        + agent_report_count
    )

    kwargs.setdefault("notifications", notifications)
    kwargs.setdefault("year", year)

    kwargs.setdefault("active_chat_count", active_chat_count)
    kwargs.setdefault("escalated_count", escalated_count)
    kwargs.setdefault("agent_report_count", agent_report_count)
    kwargs.setdefault("support_operations_total_count", support_operations_total_count)

    kwargs.setdefault("ai_review_count", ai_review_count)
    kwargs.setdefault("ai_training_case_count", ai_training_case_count)
    kwargs.setdefault("ai_repeated_question_count", ai_repeated_question_count)
    kwargs.setdefault("ai_training_total_count", ai_training_total_count)

    kwargs.setdefault("faq_suggestion_count", faq_suggestion_count)
    kwargs.setdefault("inactive_article_count", inactive_article_count)
    kwargs.setdefault("knowledge_management_total_count", knowledge_management_total_count)

    kwargs.setdefault("pending_agent_solution_count", pending_agent_solution_count)
    kwargs.setdefault("agent_knowledge_total_count", agent_knowledge_total_count)

    kwargs.setdefault("warning_security_event_count", warning_security_event_count)
    kwargs.setdefault("maintenance_active_count", maintenance_active_count)
    kwargs.setdefault("system_operations_total_count", system_operations_total_count)

    return _render(*args, **kwargs)


# ============================================================
# SMALL HELPERS
# ============================================================

def get_status_id(status_name, fallback=None):
    status = Status.query.filter_by(status=status_name).first()
    return status.id if status else fallback


def get_open_status_id():
    return get_status_id("Open", 1)


def get_pending_status_id():
    return get_status_id("Pending", 3)


def get_closed_status_id():
    return get_status_id("Closed", 4)

def get_solved_status_id():
    return get_status_id("Solved", 2)

def get_waiting_customer_status_id():
    status = (
        Status.query
        .filter(
            func.lower(Status.status)
            == "waiting for customer"
        )
        .first()
    )

    return status.id if status else None


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
            ticket.waiting_customer_since = (
                ticket.updated_at.replace(tzinfo=None)
                if ticket.updated_at else now
            )

        waiting_hours = (
            now - ticket.waiting_customer_since.replace(tzinfo=None)
        ).total_seconds() / 3600

        if waiting_hours >= 24 and not ticket.inactive_reminder_sent:
            notify_user(
                message="Reminder: your support ticket is waiting for your reply and may close after 48 hours of no response.",
                receiver_id=ticket.author_id,
                sender_id=ticket.owner_id,
                ticket_id=ticket.id
            )

            reminder_comment = Comment(
                comment="Reminder sent to customer: ticket is waiting for customer response.",
                author_id=ticket.owner_id or ticket.author_id,
                ticket_id=ticket.id
            )

            db.session.add(reminder_comment)
            ticket.inactive_reminder_sent = True

        if waiting_hours >= 48:
            ticket.status_id = closed_id
            ticket.updated_at = datetime.datetime.utcnow()
            


            close_comment = Comment(
                comment="Ticket automatically closed because the customer did not respond within 48 hours.",
                author_id=ticket.owner_id or ticket.author_id,
                ticket_id=ticket.id
            )

            db.session.add(close_comment)

            db.session.flush()

            emit_comment(ticket, close_comment, is_attachment=False)
            emit_ticket_event(
                ticket,
                "ticket_closed",
                "Ticket automatically closed due to customer inactivity."
            )

            socketio.emit(
                "customer_ticket_closed",
                {
                    "ticket_id": ticket.id
                },
                room=f"user_{ticket.author_id}"
            )

    db.session.commit()
    

def get_maintenance_setting():
    setting = MaintenanceSetting.query.first()

    if not setting:
        setting = MaintenanceSetting()
        db.session.add(setting)
        db.session.commit()

    return setting


def is_maintenance_active():
    setting = MaintenanceSetting.query.first()

    if not setting or not setting.enabled:
        return None

    now = datetime.datetime.utcnow()

    if setting.start_time and now < setting.start_time:
        return None

    if setting.end_time and now > setting.end_time:
        return None

    return setting

def notify_unassigned_tickets():
    now = datetime.datetime.utcnow()

    inactive_status_ids = [
        status_id
        for status_id in [
            get_closed_status_id(),
            get_solved_status_id()
        ]
        if status_id is not None
    ]

    query = Ticket.query.filter(
        Ticket.owner_id.is_(None)
    )

    if inactive_status_ids:
        query = query.filter(
            ~Ticket.status_id.in_(
                inactive_status_ids
            )
        )

    unassigned_tickets = query.all()

    changed = False

    for ticket in unassigned_tickets:

        # Use updated_at as the start of the current
        # unassigned period.
        unassigned_since = (
            ticket.updated_at
            or ticket.created_at
        )

        if not unassigned_since:
            continue

        unassigned_since = (
            unassigned_since.replace(
                tzinfo=None
            )
        )

        waiting_minutes = (
            now - unassigned_since
        ).total_seconds() / 60

        # =====================================================
        # 15-MINUTE CUSTOMER REMINDER
        # =====================================================

        if (
            waiting_minutes >= 15
            and not ticket.unassigned_15min_sent
        ):
            notify_user(
                message=(
                    "Your ticket is still waiting for an "
                    "available support agent. Thank you for "
                    "your patience."
                ),
                receiver_id=ticket.author_id,
                sender_id=ticket.author_id,
                ticket_id=ticket.id
            )

            reminder_comment = Comment(
                comment=(
                    "Customer wait-time reminder sent: ticket "
                    "is still waiting for an available support "
                    "agent."
                ),
                author_id=ticket.author_id,
                ticket_id=ticket.id
            )

            db.session.add(
                reminder_comment
            )

            ticket.unassigned_15min_sent = True
            changed = True

        # =====================================================
        # 30-MINUTE STAFF ALERT
        # =====================================================

        if (
            waiting_minutes >= 30
            and not ticket.unassigned_30min_sent
        ):
            staff_users = (
                User.query
                .filter(
                    User.role.in_(
                        [
                            "Agent",
                            "Administrator"
                        ]
                    )
                )
                .all()
            )

            for staff in staff_users:
                notify_user(
                    message=(
                        f"Unassigned ticket "
                        f"#{ticket.number} has been "
                        f"waiting over 30 minutes."
                    ),
                    receiver_id=staff.id,
                    sender_id=ticket.author_id,
                    ticket_id=ticket.id
                )

            staff_comment = Comment(
                comment=(
                    "Staff alert sent: ticket has been "
                    "unassigned for more than 30 minutes."
                ),
                author_id=ticket.author_id,
                ticket_id=ticket.id
            )

            db.session.add(
                staff_comment
            )

            ticket.unassigned_30min_sent = True
            changed = True

    if changed:
        try:
            db.session.commit()

        except Exception:
            db.session.rollback()

            current_app.logger.exception(
                "Admin unassigned-ticket notification "
                "update failed."
            )

def serialize_ticket(ticket):
    return {
        "ticket_id": ticket.id,
        "ticket_number": ticket.number,
        "subject": ticket.subject,
        "status": ticket.status.status if ticket.status else "",
        "status_id": ticket.status_id,
        "owner": ticket.owner.name if ticket.owner else None,
        "owner_id": ticket.owner_id,
        "author_id": ticket.author_id,
        "author": ticket.author.name if ticket.author else "",
        "priority": ticket.priority.priority if ticket.priority else "",
        "category": ticket.category.category if ticket.category else "",
    }


def serialize_comment(comment):
    user = comment.user

    return {
        "id": comment.id,
        "message": comment.comment or "",
        "author": (
            user.name
            if user
            else "Deleted user"
        ),
        "author_id": comment.author_id,
        "role": (
            user.role
            if user
            else "System"
        ),
        "created_at": (
            comment.created_at.strftime(
                "%d %b %Y, %H:%M"
            )
            if comment.created_at
            else ""
        )
    }

def get_feature_url(event_name, role="Administrator"):
    admin_urls = {
        "knowledge_updated": url_for("admin.knowledge_base"),
        "ai_training_updated": url_for( "admin.ai_review_center", tab="pending"),
        "ai_settings_updated": url_for("admin.chatbot_settings"),
        "agent_knowledge_updated": url_for("admin.agent_solution_library"),
        "users_staff_updated": url_for("admin.create_account"),
        "system_settings_updated": url_for("admin.category"),
        "system_operations_updated": url_for("admin.maintenance_mode"),
        "agent_report_updated": url_for("admin.agent_reports"),
    }

    agent_urls = {
        "knowledge_updated": url_for("agent.knowledge_base"),
        "ai_settings_updated": url_for("agent.support_help"),
        "agent_knowledge_updated": url_for("agent.agent_solutions"),
        "system_settings_updated": url_for("agent.support_help"),
        "agent_report_updated": url_for("agent.internal_reports"),
    }

    if role == "Agent":
        return agent_urls.get(event_name, url_for("agent.dashboard"))

    return admin_urls.get(event_name, url_for("admin.dashboard"))


def emit_feature_update(
    event_name,
    message="",
    receiver_roles=None,
    receiver_ids=None,
    payload=None,
    save_notification=True
):
    payload = payload or {}
    

    data = {
        "event": event_name,
        "message": message,
        
        **payload
    }

    socketio.emit(event_name, data)
    socketio.emit("feature_updated", data)
    socketio.emit("sidebar_counts_updated", data)
    socketio.emit("notification_updated", data)
    socketio.emit("analytics_updated", data)

    receiver_ids = receiver_ids or []

    if receiver_roles:
        users = User.query.filter(User.role.in_(receiver_roles)).all()
        receiver_ids.extend([user.id for user in users])

    receiver_ids = list(set(receiver_ids))

    for receiver_id in receiver_ids:
        receiver = User.query.get(receiver_id)
        receiver_role = receiver.role if receiver else "Administrator"
        feature_url = get_feature_url(event_name, receiver_role)
        if current_user.is_authenticated and receiver_id == current_user.id:
            continue

        notification = None

        if save_notification:
            try:
                notification = Notification.send_notification(
                    message=message,
                    receiver_id=receiver_id,
                    sender_id=current_user.id,
                    ticket_id=None,
                    notification_type=event_name,
                    receiver_role=receiver_role,
                    title=message,
                    url=feature_url,
                    seen=False
                )
            except Exception as e:
                print("FEATURE NOTIFICATION ERROR:", e)

        socketio.emit(
            "new_notification",
            {
                "notification_id": notification.id if notification else None,
                "receiver_id": receiver_id,
                "sender_id": current_user.id,
                "message": message,
                "item_type": event_name,
                "notification_type": event_name,
                "url": feature_url
            },
            room=f"user_{receiver_id}"
        )


def notify_feature_change(feature, message, admin=True, agent=False):
    roles = []

    if admin:
        roles.append("Administrator")

    if agent:
        roles.append("Agent")

    emit_feature_update(
        event_name=feature,
        message=message,
        receiver_roles=roles,
        save_notification=True
    )
    


def notify_knowledge_updated(message):
    notify_feature_change(
        feature="knowledge_updated",
        message=message,
        admin=True,
        agent=True
    )


def notify_ai_updated(message):
    notify_feature_change(
        feature="ai_settings_updated",
        message=message,
        admin=True,
        agent=False
    )


def notify_agent_knowledge_updated(message):
    notify_feature_change(
        feature="agent_knowledge_updated",
        message=message,
        admin=True,
        agent=True
    )


def notify_users_staff_updated(message):
    notify_feature_change(
        feature="users_staff_updated",
        message=message,
        admin=True,
        agent=False
    )


def notify_system_settings_updated(message):
    notify_feature_change(
        feature="system_settings_updated",
        message=message,
        admin=True,
        agent=False
    )


def notify_system_operations_updated(message):
    notify_feature_change(
        feature="system_operations_updated",
        message=message,
        admin=True,
        agent=False
    )

def emit_global_refresh(reason="updated", ticket=None):
    payload = {
        "reason": reason
    }

    if ticket:
        payload.update(serialize_ticket(ticket))

    socketio.emit("global_ticket_updated", payload)
    socketio.emit("sidebar_counts_updated", payload)
    socketio.emit("notification_updated", payload)
    socketio.emit("analytics_updated", payload)


def notify_user(message, receiver_id, sender_id=None, ticket_id=None):
    try:
        return Notification.send_notification(
            message=message,
            receiver_id=receiver_id,
            sender_id=sender_id if sender_id else None,
            ticket_id=ticket_id,
            seen=False
        )

    except Exception as e:
        print("ADMIN NOTIFICATION ERROR:", e)
        return None

def notify_customer(ticket, message):
    if ticket.author_id != current_user.id:
        notify_user(
            message=message,
            receiver_id=ticket.author_id,
            sender_id=current_user.id,
            ticket_id=ticket.id
        )


def notify_owner(ticket, message):
    if ticket.owner_id and ticket.owner_id != current_user.id:
        notify_user(
            message=message,
            receiver_id=ticket.owner_id,
            sender_id=current_user.id,
            ticket_id=ticket.id
        )


def notify_admins(ticket, message):
    admins = User.query.filter_by(role="Administrator").all()

    for admin in admins:
        if admin.id != current_user.id:
            notify_user(
                message=message,
                receiver_id=admin.id,
                sender_id=current_user.id,
                ticket_id=ticket.id
            )


def notify_agents(ticket, message):
    agents = User.query.filter_by(role="Agent").all()

    for agent in agents:
        if agent.id != current_user.id:
            notify_user(
                message=message,
                receiver_id=agent.id,
                sender_id=current_user.id,
                ticket_id=ticket.id
            )


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


def emit_ticket_event(ticket, event_name, message):
    payload = {
        "ticket_id": ticket.id,
        "ticket_number": ticket.number,
        "message": message,
        "status": ticket.status.status if ticket.status else "",
        "status_id": ticket.status_id,
        "owner_id": ticket.owner_id,
        "author_id": ticket.author_id
    }

    # Send the actual ticket event only once to users viewing this ticket.
    socketio.emit(
        event_name,
        payload,
        room=f"ticket_{ticket.id}"
    )

    # These update other pages, badges, and analytics silently.
    socketio.emit("global_ticket_updated", payload)
    socketio.emit("sidebar_counts_updated", payload)
    socketio.emit("notification_updated", payload)
    socketio.emit("analytics_updated", payload)


def emit_comment(ticket, comment, is_attachment=False):
    payload = {
        **serialize_ticket(ticket),
        "comment_id": comment.id,
        "message": comment.comment,
        "sender_name": comment.user.name,
        "sender_role": comment.user.role,
        "author_id": comment.author_id,
        "is_attachment": is_attachment,
        "created_at": comment.created_at.strftime("%d %b %Y, %H:%M %p") if comment.created_at else ""
    }

    socketio.emit("new_comment", payload, room=f"ticket_{ticket.id}")
    socketio.emit("global_ticket_updated", payload)
    socketio.emit("sidebar_counts_updated", payload)
    socketio.emit("notification_updated", payload)
    socketio.emit("analytics_updated", payload)


# ============================================================    
# DASHBOARD
# ============================================================

@admin_blueprint.route("/dashboard")
@login_required(role="Administrator")
def dashboard():
    auto_close_waiting_customer_tickets()
    notify_unassigned_tickets()

    open_tickets = Ticket.query.filter_by(status_id=get_open_status_id()).all()
    solved_tickets = Ticket.query.filter_by(status_id=get_status_id("Solved", 2)).all()
    pending_tickets = Ticket.query.filter_by(status_id=get_pending_status_id()).all()
    closed_tickets = Ticket.query.filter_by(status_id=get_closed_status_id()).all()

    total_tickets = Ticket.query.count()
    total_users = User.query.count()
    total_customers = User.query.filter_by(role="Customer").count()
    total_agents = User.query.filter_by(role="Agent").count()
    total_admins = User.query.filter_by(role="Administrator").count()
    total_categories = Category.query.count()

    unassigned_tickets = Ticket.query.filter(
        Ticket.owner_id == None,
        Ticket.status_id != get_closed_status_id()
    ).count()

    recent_tickets = Ticket.query.order_by(desc(Ticket.created_at)).limit(8).all()

    priority_labels = []
    priority_counts = []

    for p in Priority.query.all():
        priority_labels.append(p.priority)
        priority_counts.append(Ticket.query.filter_by(priority_id=p.id).count())

    category_labels = []
    category_counts = []

    for c in Category.query.all():
        category_labels.append(c.category)
        category_counts.append(Ticket.query.filter_by(category_id=c.id).count())

    agent_labels = []
    agent_counts = []

    for agent in User.query.filter_by(role="Agent").all():
        agent_labels.append(agent.name)
        agent_counts.append(Ticket.query.filter_by(owner_id=agent.id).count())

    return render_template(
        "admin/dashboard.html",
        open_tickets=open_tickets,
        solved_tickets=solved_tickets,
        pending_tickets=pending_tickets,
        closed_tickets=closed_tickets,
        total_tickets=total_tickets,
        total_users=total_users,
        total_customers=total_customers,
        total_agents=total_agents,
        total_admins=total_admins,
        total_categories=total_categories,
        unassigned_tickets=unassigned_tickets,
        recent_tickets=recent_tickets,
        priority_labels=priority_labels,
        priority_counts=priority_counts,
        category_labels=category_labels,
        category_counts=category_counts,
        agent_labels=agent_labels,
        agent_counts=agent_counts
    )


# ============================================================
# TICKET LISTS
# ============================================================



@csrf.exempt
@admin_blueprint.route("/api/notifications/mark-navbar-read", methods=["POST"])
@login_required(role="Administrator")
def mark_navbar_notifications_read():
    Notification.query.filter(
        Notification.receiver_id == current_user.id,
        Notification.seen == False
    ).update({"seen": True})

    db.session.commit()

    socketio.emit(
        "notification_read",
        {
            "receiver_id": current_user.id
        },
        room=f"user_{current_user.id}"
    )

    socketio.emit("notification_updated", {"receiver_id": current_user.id})
    socketio.emit("sidebar_counts_updated", {"receiver_id": current_user.id})

    return jsonify({"ok": True}), 200

@admin_blueprint.route("/my-tickets", methods=["GET"])
@login_required(role="Administrator")
def my_tickets():
    tickets = (
        Ticket.query
        .filter(or_(Ticket.author_id == current_user.id, Ticket.owner_id == current_user.id))
        .order_by(desc(Ticket.created_at))
        .all()
    )

    form = TicketForm()
    return render_template("admin/my_tickets.html", form=form, tickets=tickets)


@admin_blueprint.route(
    "/new-tickets",
    methods=["GET"]
)
@login_required(role="Administrator")
def new_tickets():
    auto_close_waiting_customer_tickets()
    notify_unassigned_tickets()

    closed_status_id = get_closed_status_id()

    solved_status_id = get_status_id(
        "Solved",
        fallback=None
    )

    excluded_status_ids = [
        status_id
        for status_id in [
            closed_status_id,
            solved_status_id
        ]
        if status_id is not None
    ]

    query = Ticket.query.filter(
        Ticket.owner_id.is_(None)
    )

    if excluded_status_ids:
        query = query.filter(
            ~Ticket.status_id.in_(
                excluded_status_ids
            )
        )

    tickets = (
        query
        .order_by(
            desc(Ticket.created_at)
        )
        .all()
    )

    form = TicketForm()

    return render_template(
        "admin/new_tickets.html",
        form=form,
        tickets=tickets
    )

@admin_blueprint.route(
    "/all-tickets",
    methods=["GET"]
)
@login_required(role="Administrator")
def all_tickets():
    auto_close_waiting_customer_tickets()
    notify_unassigned_tickets()

    tickets = (
        Ticket.query
        .order_by(
            desc(Ticket.updated_at),
            desc(Ticket.created_at)
        )
        .all()
    )

    return render_template(
        "admin/all_tickets.html",
        tickets=tickets
    )


@admin_blueprint.route("/notification/open/<int:nid>", methods=["GET"])
@login_required(role="Administrator")
def open_notification(nid):
    notification = Notification.query.get_or_404(nid)

    if notification.receiver_id != current_user.id:
        flash("Unauthorized notification.", "danger")
        return redirect(url_for("admin.notifications"))

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

    emit_global_refresh("notification_read")

    if notification.ticket_id:
        return redirect(url_for("admin.view_ticket", id=notification.ticket_id))

    if notification.agent_report_id:
        return redirect(url_for("admin.agent_reports"))

    if (
        notification.url
        and notification.url != "#"
        and f"/admin/notification/open/{notification.id}" not in notification.url
    ):
        if (
            notification.url
            and notification.url != "#"
        ):
            notification_url = str(
                notification.url
            ).strip()

            if notification_url.startswith("/"):
                return redirect(
                    notification_url
                )

    if notification.notification_type:
        return redirect(get_feature_url(notification.notification_type, "Administrator"))
    message = (notification.message or "").lower()

    if "agent solution" in message:
        return redirect(url_for("admin.agent_solution_library", status="Pending"))

    if "agent report" in message:
        return redirect(url_for("admin.agent_reports"))

    if "knowledge" in message or "faq" in message:
        return redirect(url_for("admin.knowledge_base"))

    if "ai" in message or "training" in message:
        return redirect(
            url_for(
                "admin.ai_review_center",
                tab="pending"
            )
        )

    if "system" in message:
        return redirect(url_for("admin.system_health"))

    return redirect(url_for("admin.dashboard"))

@admin_blueprint.route(
    "/active-chats",
    methods=["GET"]
)
@login_required(role="Administrator")
def active_chats():
    auto_close_waiting_customer_tickets()
    notify_unassigned_tickets()

    closed_status_id = get_closed_status_id()

    solved_status_id = get_status_id(
        "Solved",
        fallback=None
    )

    excluded_status_ids = [
        status_id
        for status_id in [
            closed_status_id,
            solved_status_id
        ]
        if status_id is not None
    ]

    query = Ticket.query

    if excluded_status_ids:
        query = query.filter(
            ~Ticket.status_id.in_(
                excluded_status_ids
            )
        )

    active_tickets = (
        query
        .order_by(
            desc(Ticket.updated_at),
            desc(Ticket.created_at)
        )
        .all()
    )

    return render_template(
        "admin/active_chats.html",
        active_tickets=active_tickets
    )

# ============================================================
# TICKET ACTIONS
# ============================================================

@admin_blueprint.route("/ticket/claim/<int:id>", methods=["POST"])
@login_required(role="Administrator")
def claim_ticket(id):
    ticket = Ticket.query.get_or_404(id)

    if ticket.owner_id is not None:
        flash("This ticket has already been claimed by another support staff.", "warning")
        return redirect(url_for("admin.view_ticket", id=id))

    ticket.owner_id = current_user.id
    ticket.unassigned_15min_sent = False
    ticket.unassigned_30min_sent = False

    if ticket.status_id == get_open_status_id():
        ticket.status_id = get_pending_status_id()

    join_message = f"Support admin {current_user.name} has joined the chat."

    comment = Comment(
        comment=join_message,
        author_id=current_user.id,
        ticket_id=ticket.id
    )

    db.session.add(comment)
    db.session.commit()
    if ticket.author:

        send_ticket_assigned_email(
            ticket.author,
            ticket,
            current_user
        )

    notify_customer(ticket, "joined your support ticket")

    emit_comment(ticket, comment, is_attachment=False)
    emit_ticket_event(ticket, "agent_joined", join_message)

    flash("You have joined this ticket.", "primary")
    return redirect(url_for("admin.view_ticket", id=id))


@admin_blueprint.route(
    "/create-ticket",
    methods=["GET", "POST"]
)
@login_required(role="Administrator")
def create_ticket():
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
            priority_id=1,
            status_id=get_open_status_id(),
            orig_file=original_f,
            file_link=attachment
        )

        db.session.add(ticket)
        db.session.commit()

        # ----------------------------------------------------
        # SEND TICKET-CREATED EMAIL TO THE AUTHOR
        # ----------------------------------------------------

        email_sent = send_ticket_created_email(
            current_user,
            ticket
        )

        if not email_sent:
            current_app.logger.error(
                "Administrator ticket-created email failed "
                "for ticket_id=%s administrator_id=%s",
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
                f"by administrator {current_user.email}."
            ),
            user_id=current_user.id,
            ticket_id=ticket.id
        )

        # ----------------------------------------------------
        # REAL-TIME UPDATE
        # ----------------------------------------------------

        emit_global_event(
            "ticket_created",
            ticket,
            "Ticket created by administrator."
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
            url_for("admin.new_tickets")
        )

    return render_template(
        "admin/new_tickets.html",
        form=form,
        tickets=[]
    )


@admin_blueprint.route(
    "/view-ticket/<int:id>",
    methods=["GET", "POST"]
)
@login_required(role="Administrator")
def view_ticket(id):
    ticket = Ticket.query.get_or_404(id)

    comments = (
        Comment.query
        .filter(
            Comment.ticket_id == ticket.id
        )
        .order_by(
            Comment.created_at.asc()
        )
        .all()
    )

    form = UpdateTicketForm()
    comment_form = CommentForm()

    closed_status_id = (
        get_closed_status_id()
    )

    is_closed = (
        ticket.status_id
        == closed_status_id
    )

    # ========================================================
    # LOAD CURRENT VALUES INTO THE FORM
    # ========================================================

    if request.method == "GET":
        form.owner.data = (
            str(ticket.owner_id)
            if ticket.owner_id
            else ""
        )

        form.priority.data = (
            str(ticket.priority_id)
            if ticket.priority_id
            else ""
        )

        form.status.data = (
            str(ticket.status_id)
            if ticket.status_id
            else ""
        )

    # ========================================================
    # UPDATE TICKET
    # ========================================================

    if form.validate_on_submit():

        if is_closed:
            flash(
                "Closed tickets cannot be changed. "
                "Reopen the ticket first.",
                "warning"
            )

            return redirect(
                url_for(
                    "admin.view_ticket",
                    id=ticket.id
                )
            )

        old_owner_id = ticket.owner_id
        old_priority_id = ticket.priority_id
        old_status_id = ticket.status_id

        now = datetime.datetime.utcnow()

        # ====================================================
        # CONVERT FORM VALUES
        # ====================================================

        try:
            new_owner_id = (
                int(form.owner.data)
                if form.owner.data
                else None
            )

            new_priority_id = (
                int(form.priority.data)
                if form.priority.data
                else old_priority_id
            )

            new_status_id = (
                int(form.status.data)
                if form.status.data
                else old_status_id
            )

        except (TypeError, ValueError):
            flash(
                "One or more selected values are invalid.",
                "danger"
            )

            return redirect(
                url_for(
                    "admin.view_ticket",
                    id=ticket.id
                )
            )

        # ====================================================
        # VALIDATE OWNER
        # ====================================================

        new_owner = None

        if new_owner_id:
            new_owner = User.query.get(
                new_owner_id
            )

            if (
                not new_owner
                or new_owner.role
                not in [
                    "Agent",
                    "Administrator"
                ]
            ):
                flash(
                    "The selected assignee is invalid.",
                    "danger"
                )

                return redirect(
                    url_for(
                        "admin.view_ticket",
                        id=ticket.id
                    )
                )

        # ====================================================
        # VALIDATE PRIORITY
        # ====================================================

        if (
            new_priority_id
            and not Priority.query.get(
                new_priority_id
            )
        ):
            flash(
                "The selected priority is invalid.",
                "danger"
            )

            return redirect(
                url_for(
                    "admin.view_ticket",
                    id=ticket.id
                )
            )

        # ====================================================
        # VALIDATE STATUS
        # ====================================================

        if (
            new_status_id
            and not Status.query.get(
                new_status_id
            )
        ):
            flash(
                "The selected status is invalid.",
                "danger"
            )

            return redirect(
                url_for(
                    "admin.view_ticket",
                    id=ticket.id
                )
            )

        assignment_comment = None
        close_comment = None

        # Used to prevent the unassigned timer from being reset
        # whenever an already-unassigned ticket is edited.
        became_unassigned = (
            old_owner_id is not None
            and new_owner_id is None
        )

        became_assigned = (
            old_owner_id is None
            and new_owner_id is not None
        )

        was_reassigned = (
            old_owner_id is not None
            and new_owner_id is not None
            and old_owner_id != new_owner_id
        )

        # ====================================================
        # OWNER CHANGE
        # ====================================================

        if old_owner_id != new_owner_id:
            ticket.owner_id = new_owner_id

            if new_owner:
                assignment_message = (
                    f"🔄 Ticket assigned to "
                    f"{new_owner.name} by administrator "
                    f"{current_user.name}."
                )

            else:
                assignment_message = (
                    f"🔄 Ticket was unassigned by administrator "
                    f"{current_user.name}."
                )

            assignment_comment = Comment(
                comment=assignment_message,
                author_id=current_user.id,
                ticket_id=ticket.id
            )

            db.session.add(
                assignment_comment
            )

            # Reset reminder flags whenever assignment changes.
            ticket.unassigned_15min_sent = False
            ticket.unassigned_30min_sent = False

            # Start the unassigned waiting timer exactly now.
            if became_unassigned:
                ticket.updated_at = now

        # ====================================================
        # PRIORITY
        # ====================================================

        ticket.priority_id = (
            new_priority_id
        )

        # ====================================================
        # STATUS
        # ====================================================

        ticket.status_id = (
            new_status_id
        )

        waiting_status_id = (
            get_waiting_customer_status_id()
        )

        if (
            waiting_status_id
            and new_status_id
            == waiting_status_id
        ):
            # Only start the 48-hour customer-response timer
            # when the ticket first enters this status.
            if (
                old_status_id
                != waiting_status_id
                or not ticket.waiting_customer_since
            ):
                ticket.waiting_customer_since = now

            ticket.inactive_reminder_sent = False

        else:
            ticket.waiting_customer_since = None
            ticket.inactive_reminder_sent = False

        # ====================================================
        # CLOSED STATUS
        # ====================================================

        status_changed_to_closed = (
            old_status_id != new_status_id
            and new_status_id
            == closed_status_id
        )

        if status_changed_to_closed:
            close_message = (
                f"🔒 Ticket closed by administrator "
                f"{current_user.name}."
            )

            close_comment = Comment(
                comment=close_message,
                author_id=current_user.id,
                ticket_id=ticket.id
            )

            db.session.add(
                close_comment
            )

        # ====================================================
        # UPDATED TIME
        # ====================================================

        if became_unassigned:
            # updated_at was already set above and now acts as
            # the start time for the unassigned waiting period.
            pass

        elif new_owner_id is None:
            # The ticket was already unassigned before this edit.
            # Do not overwrite updated_at, because doing so would
            # restart the 15-minute and 30-minute timers.
            pass

        else:
            ticket.updated_at = now

        # ====================================================
        # SAVE DATABASE CHANGES
        # ====================================================

        try:
            db.session.commit()

        except Exception:
            db.session.rollback()

            current_app.logger.exception(
                "Admin ticket update failed "
                "for ticket_id=%s",
                ticket.id
            )

            flash(
                "The ticket could not be updated.",
                "danger"
            )

            return redirect(
                url_for(
                    "admin.view_ticket",
                    id=ticket.id
                )
            )

        # ====================================================
        # ASSIGNMENT EMAIL
        # ====================================================

        if (
            old_owner_id != new_owner_id
            and new_owner
            and ticket.author
        ):
            try:
                if was_reassigned:
                    # This service accepts only:
                    # customer and ticket.
                    send_ticket_reassigned_email(
                        ticket.author,
                        ticket
                    )

                elif became_assigned:
                    send_ticket_assigned_email(
                        ticket.author,
                        ticket,
                        new_owner
                    )

            except Exception:
                current_app.logger.exception(
                    "Assignment email failed "
                    "for ticket_id=%s",
                    ticket.id
                )

        # ====================================================
        # CLOSED EMAILS
        # ====================================================

        if (
            status_changed_to_closed
            and ticket.author
        ):
            try:
                send_ticket_closed_email(
                    ticket.author,
                    ticket
                )

            except Exception:
                current_app.logger.exception(
                    "Closed-ticket email failed "
                    "for ticket_id=%s",
                    ticket.id
                )

            try:
                send_satisfaction_email(
                    ticket.author,
                    ticket
                )

            except Exception:
                current_app.logger.exception(
                    "Satisfaction email failed "
                    "for ticket_id=%s",
                    ticket.id
                )

            socketio.emit(
                "customer_ticket_closed",
                {
                    "ticket_id": ticket.id,
                    "message": "Ticket closed."
                },
                room=f"user_{ticket.author_id}"
            )

        # ====================================================
        # SOCKET EVENTS
        # ====================================================

        if assignment_comment:
            emit_comment(
                ticket,
                assignment_comment,
                is_attachment=False
            )

            if new_owner:
                emit_ticket_event(
                    ticket,
                    "agent_joined",
                    assignment_comment.comment
                )

            else:
                emit_ticket_event(
                    ticket,
                    "ticket_unassigned",
                    assignment_comment.comment
                )

        if close_comment:
            emit_comment(
                ticket,
                close_comment,
                is_attachment=False
            )

            emit_ticket_event(
                ticket,
                "ticket_closed",
                close_comment.comment
            )

        emit_global_event(
            "ticket_updated",
            ticket,
            "Ticket updated."
        )

        flash(
            "Ticket updated successfully.",
            "success"
        )

        return redirect(
            url_for(
                "admin.view_ticket",
                id=ticket.id
            )
        )

    return render_template(
        "admin/view_ticket.html",
        ticket=ticket,
        comments=comments,
        form=form,
        comment_form=comment_form,
        is_closed=is_closed
    )


@admin_blueprint.route(
    "/comment-ticket/<int:id>",
    methods=[ "POST"]
)
@login_required(role="Administrator")
def comment_ticket(id):
    ticket = Ticket.query.get_or_404(id)
    comment_form = CommentForm()

    if ticket.status_id == get_closed_status_id():
        return jsonify({
            "success": False,
            "message": "Closed tickets cannot receive new messages."
        }), 400

    if comment_form.validate_on_submit():
        comment_text = (
            comment_form.comment.data or ""
        ).strip()

        if not comment_text:
            return jsonify({
                "success": False,
                "message": "Message is empty."
            }), 400

        new_comment = Comment(
            comment=comment_text,
            author_id=current_user.id,
            ticket_id=ticket.id
        )

        db.session.add(new_comment)
        db.session.commit()

        # Send email to the customer after the reply is saved.
        email_sent = False

        if ticket.author:
            email_sent = send_ticket_reply_email(
                ticket.author,
                ticket,
                comment_text
            )

            if not email_sent:
                current_app.logger.error(
                    "Admin ticket-reply email failed "
                    "for ticket_id=%s customer_id=%s",
                    ticket.id,
                    ticket.author_id
                )

        notify_customer(
            ticket,
            "commented on ticket"
        )

        notify_owner(
            ticket,
            "commented on ticket"
        )

        emit_comment(
            ticket,
            new_comment,
            is_attachment=False
        )

        return jsonify({
            "success": True,
            "comment": serialize_comment(
                new_comment
            ),
            "email_sent": email_sent
        }), 200

    return jsonify({
        "success": False,
        "message": "Invalid message."
    }), 400


@admin_blueprint.route("/ticket/reopen/<int:id>", methods=["POST"])
@login_required(role="Administrator")
def reopen_ticket(id):
    ticket = Ticket.query.get_or_404(id)
    if ticket.status_id != get_closed_status_id():
        flash(
            "Only closed tickets can be reopened.",
            "warning"
        )

        return redirect(
            url_for(
                "admin.view_ticket",
                id=ticket.id
            )
        )

    old_status = ticket.status_id

    ticket.status_id = get_pending_status_id()

    ticket.waiting_customer_since = None
    ticket.inactive_reminder_sent = False

    ChatMessage.query.filter(
        ChatMessage.ticket_id == ticket.id
    ).update(
        {
            "customer_visible": True
        }
    )

    reopen_message = (
        f"Ticket reopened by admin "
        f"{current_user.name}."
    )

    comment = Comment(
        comment=reopen_message,
        author_id=current_user.id,
        ticket_id=ticket.id
    )

    db.session.add(comment)
    db.session.commit()

    if ticket.author:
        send_ticket_reopened_email(
            ticket.author,
            ticket
        )

    notify_customer(
        ticket,
        "reopened ticket"
    )

    notify_owner(
        ticket,
        "reopened ticket"
    )

    notify_agents(
        ticket,
        "reopened ticket"
    )

    emit_comment(
        ticket,
        comment,
        is_attachment=False
    )

    emit_ticket_event(
        ticket,
        "ticket_reopened",
        reopen_message
    )

    socketio.emit(
        "customer_ticket_reopened",
        {
            "ticket_id": ticket.id,
            "status_id": ticket.status_id
        },
        room=f"user_{ticket.author_id}"
    )

    emit_global_refresh(
        "ticket_reopened",
        ticket
    )

    flash(
        "Ticket reopened successfully.",
        "primary"
    )

    return redirect(
        url_for(
            "admin.view_ticket",
            id=ticket.id
        )
    )


@admin_blueprint.route(
    "/ticket/delete/<int:uid>/<int:tid>",
    methods=["POST"]
)
@login_required(role="Administrator")
def delete_ticket(uid, tid):
    ticket = Ticket.query.get_or_404(tid)
        # Save required ticket information before deletion.
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
            deleted_by=(
                f"administrator {current_user.name}"
            ),
            deleted_ticket_id=ticket.id
        )

        if not email_sent:
            current_app.logger.error(
                "Admin ticket-deleted email failed "
                "for ticket_id=%s customer_id=%s",
                ticket.id,
                ticket.author_id
            )

    # ----------------------------------------------------
    # DELETE ATTACHMENT
    # ----------------------------------------------------

    if ticket.file_link:
        folder_id = os.path.join(
            path,
            "app",
            "static",
            "uploads",
            "attachments",
            str(ticket.author_id)
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

    # Log the action before deletion, but do not keep a
    # foreign key to a record that is about to disappear.
    log_system_event(
        event_type="Ticket Deleted",
        severity="Warning",
        message=(
            f"Ticket #{ticket_number} was deleted "
            f"by administrator {current_user.email}."
        ),
        user_id=current_user.id,
        ticket_id=None
    )

    # ----------------------------------------------------
    # DELETE DATABASE TICKET
    # ----------------------------------------------------

    db.session.delete(ticket)
    db.session.commit()

    payload = {
        "ticket_id": ticket_id,
        "ticket_number": ticket_number,
        "message": "Ticket deleted by administrator."
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

    if email_sent:
        flash(
            "Ticket has been deleted. "
            "A confirmation email was sent to the customer.",
            "success"
        )
    else:
        flash(
            "Ticket has been deleted, but the confirmation "
            "email could not be sent.",
            "warning"
        )

    return redirect(
        url_for("admin.all_tickets")
    )


@admin_blueprint.route(
    "/download/attachment/<int:id>/<filename>",
    methods=["GET"]
)
@login_required(role="Administrator")
def download_attachment(id, filename):
    safe_filename = secure_filename(
        filename
    )

    if (
        not safe_filename
        or safe_filename != filename
    ):
        abort(400)

    ticket = (
        Ticket.query
        .filter(
            Ticket.author_id == id,
            Ticket.file_link == safe_filename
        )
        .first()
    )

    if not ticket:
        abort(404)

    folder_id = os.path.join(
        path,
        "app",
        "static",
        "uploads",
        "attachments",
        str(ticket.author_id)
    )

    return send_from_directory(
        folder_id,
        safe_filename,
        as_attachment=True
    )


# ============================================================
# CATEGORY / PRIORITY / STATUS
# ============================================================

@admin_blueprint.route("/categories", methods=["GET", "POST"])
@login_required(role="Administrator")
def category():
    categories = Category.query.all()
    form = CategoryForm()

    if form.validate_on_submit():
        category_obj = Category(category=form.category.data)
        db.session.add(category_obj)
        db.session.commit()
        notify_feature_change(
            "system_settings_updated",
            "System Settings were updated.",
            admin=True,
            agent=True
        )


        flash("Category has been created.", "primary")
        return redirect(url_for("admin.category"))

    return render_template("admin/category.html", form=form, categories=categories)


@admin_blueprint.route(
    "/category/update/<int:id>",
    methods=["GET", "POST"]
)
@login_required(role="Administrator")
def update_category(id):
    category_obj = (
        Category.query.get_or_404(id)
    )

    form = CategoryForm(
        obj=category_obj
    )

    if request.method == "GET":
        form.category.data = (
            category_obj.category
        )

    if form.validate_on_submit():
        category_obj.category = (
            form.category.data.strip()
        )

        db.session.commit()

        notify_feature_change(
            "system_settings_updated",
            "System Settings were updated.",
            admin=True,
            agent=True
        )

        flash(
            "Category has been updated.",
            "success"
        )

        return redirect(
            url_for("admin.category")
        )

    return render_template(
        "admin/category.html",
        form=form,
        categories=Category.query.all(),
        editing_category=category_obj
    )


@admin_blueprint.route(
    "/category/delete/<int:id>",
    methods=["POST"]
)
@login_required(role="Administrator")
def delete_category(id):
    category_obj = (
        Category.query.get_or_404(id)
    )

    linked_ticket = (
        Ticket.query
        .filter(
            Ticket.category_id
            == category_obj.id
        )
        .first()
    )

    linked_faq = (
        FAQ.query
        .filter(
            FAQ.category_id
            == category_obj.id
        )
        .first()
    )

    linked_article = (
        KnowledgeArticle.query
        .filter(
            KnowledgeArticle.category_id
            == category_obj.id
        )
        .first()
    )

    if (
        linked_ticket
        or linked_faq
        or linked_article
    ):
        flash(
            "This category cannot be deleted because "
            "it is currently in use.",
            "warning"
        )

        return redirect(
            url_for("admin.category")
        )

    db.session.delete(category_obj)
    db.session.commit()

    notify_feature_change(
        "system_settings_updated",
        "System Settings were updated.",
        admin=True,
        agent=True
    )

    flash(
        "Category has been deleted.",
        "success"
    )

    return redirect(
        url_for("admin.category")
    )


@admin_blueprint.route("/priorities", methods=["GET", "POST"])
@login_required(role="Administrator")
def priority():
    priorities = Priority.query.all()
    form = PriorityForm()

    if form.validate_on_submit():
        priority_obj = Priority(priority=form.priority.data)
        db.session.add(priority_obj)
        db.session.commit()
        notify_feature_change(
            "system_settings_updated",
            "System Settings were updated.",
            admin=True,
            agent=True
        )


        flash("Priority has been created.", "primary")
        return redirect(url_for("admin.priority"))

    return render_template("admin/priority.html", form=form, priorities=priorities)


@admin_blueprint.route(
    "/priority/update/<int:id>",
    methods=["GET", "POST"]
)
@login_required(role="Administrator")
def update_priority(id):
    priority_obj = (
        Priority.query.get_or_404(id)
    )

    form = PriorityForm(
        obj=priority_obj
    )

    if request.method == "GET":
        form.priority.data = (
            priority_obj.priority
        )

    if form.validate_on_submit():
        priority_obj.priority = (
            form.priority.data.strip()
        )

        db.session.commit()

        notify_feature_change(
            "system_settings_updated",
            "System Settings were updated.",
            admin=True,
            agent=True
        )

        flash(
            "Priority has been updated.",
            "success"
        )

        return redirect(
            url_for("admin.priority")
        )

    return render_template(
        "admin/priority.html",
        form=form,
        priorities=Priority.query.all(),
        editing_priority=priority_obj
    )


@admin_blueprint.route(
    "/priority/delete/<int:id>",
    methods=["POST"]
)
@login_required(role="Administrator")
def delete_priority(id):
    priority_obj = (
        Priority.query.get_or_404(id)
    )

    linked_ticket = (
        Ticket.query
        .filter(
            Ticket.priority_id
            == priority_obj.id
        )
        .first()
    )

    if linked_ticket:
        flash(
            "This priority cannot be deleted because "
            "it is currently assigned to tickets.",
            "warning"
        )

        return redirect(
            url_for("admin.priority")
        )

    db.session.delete(priority_obj)
    db.session.commit()

    notify_feature_change(
        "system_settings_updated",
        "System Settings were updated.",
        admin=True,
        agent=True
    )

    flash(
        "Priority has been deleted.",
        "success"
    )

    return redirect(
        url_for("admin.priority")
    )


@admin_blueprint.route("/statuses", methods=["GET"])
@login_required(role="Administrator")
def status():
    statuses = Status.query.all()
    return render_template("admin/status.html", statuses=statuses)


# ============================================================
# USERS / ACCOUNT
# ============================================================

@admin_blueprint.route("/create-account", methods=["GET", "POST"])
@login_required(role="Administrator")
def create_account():
    users = User.query.order_by(desc(User.created_at)).all()
    form = UserForm()
    role_form = UpdateRoleForm()

    if form.validate_on_submit():
        user = User(
            name=form.name.data,
            email=form.email.data,
            password=generate_password_hash(form.password.data),
            role=form.role.data,
            image="default-profile.png"
        )

        db.session.add(user)
        db.session.commit()
        notify_feature_change(
            "users_staff_updated",
            "New user/staff account was created.",
            admin=True,
            agent=False
        )

        flash(f"{form.email.data} has been created.", "primary")
        return redirect(url_for("admin.create_account"))

    return render_template("admin/create_account.html", form=form, role_form=role_form, users=users)


@admin_blueprint.route("/user/delete/<int:id>", methods=["POST"])
@login_required(role="Administrator")
def delete_account(id):
    user = User.query.get_or_404(id)
    if user.id == current_user.id:
        flash(
            "You cannot delete your own account.",
            "warning"
        )

        return redirect(
            url_for("admin.create_account")
        )

    if request.method == "POST":
        folder_id = os.path.join(path, "app/static/uploads/attachments", str(id))

        if os.path.exists(folder_id):
            shutil.rmtree(folder_id)

        if user.image != "default-profile.png":
            profile_path = os.path.join(current_app.config["PROFILE_DIR"], user.image)

            if os.path.exists(profile_path):
                os.remove(profile_path)

        db.session.delete(user)
        db.session.commit()
        notify_feature_change(
            "users_staff_updated",
            "User/staff account was deleted.",
            admin=True,
            agent=False
        )

        flash("User has been deleted.", "primary")

    return redirect(url_for("admin.create_account"))


@admin_blueprint.route(
    "/user/update/<int:id>",
    methods=["POST"]
)
@login_required(role="Administrator")
def update_role(id):
    user = User.query.get_or_404(id)
    role_form = UpdateRoleForm()

    if not role_form.validate_on_submit():
        flash(
            "The selected role is invalid.",
            "danger"
        )

        return redirect(
            url_for("admin.create_account")
        )

    old_role = user.role
    new_role = role_form.role.data

    if user.id == current_user.id:
        if new_role != "Administrator":
            flash(
                "You cannot remove your own administrator role.",
                "warning"
            )

            return redirect(
                url_for("admin.create_account")
            )

    user.role = new_role
    db.session.commit()

    notify_feature_change(
        "users_staff_updated",
        "User/staff role was updated.",
        admin=True,
        agent=False
    )

    log_system_event(
        event_type="Role Changed",
        severity="Warning",
        message=(
            f"User {user.email} role changed "
            f"from {old_role} to {user.role} "
            f"by {current_user.email}."
        ),
        user_id=current_user.id
    )

    flash(
        "User role has been updated.",
        "success"
    )

    return redirect(
        url_for("admin.create_account")
    )


@admin_blueprint.route(
    "/my-profile",
    methods=["GET", "POST"]
)
@login_required(role="Administrator")
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
                url_for("admin.my_profile")
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
                            "Could not remove old administrator "
                            "profile image for user_id=%s",
                            user.id
                        )

        try:
            db.session.commit()

        except Exception:
            db.session.rollback()

            current_app.logger.exception(
                "Administrator profile update failed "
                "for user_id=%s",
                user.id
            )

            flash(
                "Your profile could not be updated.",
                "danger"
            )

            return redirect(
                url_for("admin.my_profile")
            )

        socketio.emit(
            "profile_updated",
            {
                "user_id": user.id,
                "name": user.name,
                "image": user.image,
                "message": (
                    "Administrator profile updated."
                )
            }
        )

        flash(
            "Your profile has been updated.",
            "success"
        )

        return redirect(
            url_for("admin.my_profile")
        )

    return render_template(
        "admin/my_profile.html",
        form=form,
        user=user
    )

@admin_blueprint.route(
    "/change-password",
    methods=["GET", "POST"]
)
@login_required(role="Administrator")
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
                url_for("admin.change_password")
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
                "Administrator password update failed "
                "for user_id=%s",
                user.id
            )

            flash(
                "The password could not be updated.",
                "danger"
            )

            return redirect(
                url_for("admin.change_password")
            )

        socketio.emit(
            "password_updated",
            {
                "user_id": user.id,
                "message": (
                    "Administrator password updated."
                )
            }
        )

        flash(
            "Password updated successfully.",
            "success"
        )

        return redirect(
            url_for("admin.change_password")
        )

    return render_template(
        "admin/change_password.html",
        form=form
    )

@admin_blueprint.route(
    "/change-email",
    methods=["GET", "POST"]
)
@login_required(role="Administrator")
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
                url_for(
                    "admin.change_email"
                )
            )

        new_email = (
            form.email.data or ""
        ).strip().lower()

        existing = (
            User.query
            .filter(
                func.lower(User.email)
                == new_email,
                User.id
                != current_user.id
            )
            .first()
        )

        if existing:
            flash(
                "Email already exists.",
                "danger"
            )

            return redirect(
                url_for(
                    "admin.change_email"
                )
            )

        current_user.email = (
            new_email
        )

        try:
            db.session.commit()

        except Exception:
            db.session.rollback()

            current_app.logger.exception(
                "Administrator email update "
                "failed for user_id=%s",
                current_user.id
            )

            flash(
                "Your email could not be updated.",
                "danger"
            )

            return redirect(
                url_for(
                    "admin.change_email"
                )
            )

        flash(
            "Email updated.",
            "success"
        )

        return redirect(
            url_for(
                "admin.my_profile"
            )
        )

    return render_template(
        "admin/change_email.html",
        form=form
    )



# ============================================================
# NOTIFICATIONS
# ============================================================

@admin_blueprint.route("/notifications", methods=["GET"])
@login_required(role="Administrator")
def notifications():
    my_notifications = (
        Notification.query
        .filter(Notification.receiver_id == current_user.id)
        .order_by(desc(Notification.created_at))
        .all()
    )

    return render_template("admin/notifications.html", my_notifications=my_notifications)


@admin_blueprint.route("/read-notification/<int:tid>/<int:nid>", methods=["GET"])
@login_required(role="Administrator")
def read_notification(tid, nid):
    return redirect(url_for("admin.open_notification", nid=nid))

@admin_blueprint.route("/notifications/mark-all-read", methods=["POST"])
@login_required(role="Administrator")
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

    emit_global_refresh("notifications_read")

    flash("All notifications marked as read.", "primary")
    return redirect(url_for("admin.notifications"))


def find_previous_customer_message(ai_log):
    """
    Find the customer message that belongs to an AI response.

    Matching order:
    1. Same chat session
    2. Same ticket
    3. Same customer
    """

    if not ai_log or not ai_log.user_id:
        return ""

    query = ChatMessage.query.filter(
        ChatMessage.user_id == ai_log.user_id,
        ChatMessage.role == "user",
        ChatMessage.created_at <= ai_log.created_at
    )

    # Prefer a message from the same chat session.
    if ai_log.session_id:
        session_message = (
            query
            .filter(ChatMessage.session_id == ai_log.session_id)
            .order_by(ChatMessage.created_at.desc())
            .first()
        )

        if session_message:
            return session_message.message or ""

    # Otherwise, try the same support ticket.
    if ai_log.ticket_id:
        ticket_message = (
            query
            .filter(ChatMessage.ticket_id == ai_log.ticket_id)
            .order_by(ChatMessage.created_at.desc())
            .first()
        )

        if ticket_message:
            return ticket_message.message or ""

    # Final fallback: latest earlier message from the same customer.
    previous_message = (
        query
        .order_by(ChatMessage.created_at.desc())
        .first()
    )

    return previous_message.message if previous_message else ""

def clean_ai_message(message):
    """
    Decode HTML entities stored in ChatMessage.message.

    Example:
    &lt;strong&gt;Answer&lt;/strong&gt;
    becomes:
    <strong>Answer</strong>
    """

    if not message:
        return ""

    cleaned = str(message)

    # Some records may have been encoded more than once.
    for _ in range(3):
        decoded = html.unescape(cleaned)

        if decoded == cleaned:
            break

        cleaned = decoded

    return cleaned

# ============================================================
# CHATBOT REVIEW / HISTORY
# ============================================================

@admin_blueprint.route("/ai/review-queue", methods=["GET"])
@login_required(role="Administrator")
def review_queue():
    return redirect(
        url_for(
            "admin.ai_review_center",
            tab="pending"
        )
    )

@admin_blueprint.route("/chat-history", methods=["GET"])
@login_required(role="Administrator")
def chat_history():
    review_status = request.args.get("review_status", "")
    role = request.args.get("role", "")

    query = ChatMessage.query

    if review_status:
        query = query.filter(ChatMessage.review_status == review_status)

    if role:
        query = query.filter(ChatMessage.role == role)

    logs = query.order_by(desc(ChatMessage.created_at)).all()

    return render_template(
        "admin/chat_history.html",
        logs=logs,
        selected_review_status=review_status,
        selected_role=role
    )

# ============================================================
# KNOWLEDGE BASE / LOGS
# ============================================================
@admin_blueprint.route("/knowledge-base", methods=["GET", "POST"])
@login_required(role="Administrator")
def knowledge_base():

    faqs = FAQ.query.order_by(desc(FAQ.created_at)).all()

    form = FAQForm()

    if form.validate_on_submit():

        existing_faq = FAQ.query.filter(
            FAQ.question.ilike(form.question.data.strip())
        ).first()

        if existing_faq:

            flash(
                "A FAQ with the same question already exists.",
                "warning"
            )

            return render_template(
                "admin/knowledge_base.html",
                form=form,
                faqs=faqs
            )

        faq = FAQ(
            question=form.question.data,
            answer=form.answer.data,
            category_id=int(form.category.data),
            tags=form.tags.data,
            is_active=True
        )

        db.session.add(faq)
        db.session.commit()
        
        
        
        notify_feature_change(
            "knowledge_updated",
            "FAQ was created in Knowledge Management.",
            admin=True,
            agent=True
        )

        socketio.emit(
            "faq_library_updated",
            {
                "message": "FAQ library updated"
            }
        )

        flash(
            "FAQ created successfully.",
            "primary"
        )

        return redirect(
            url_for("admin.knowledge_base")
        )

    return render_template(
        "admin/knowledge_base.html",
        form=form,
        faqs=faqs
    )

@admin_blueprint.route("/chatbot-settings", methods=["GET", "POST"])
@login_required(role="Administrator")
def chatbot_settings():
    setting = ChatbotSetting.query.first()

    if not setting:
        setting = ChatbotSetting()
        db.session.add(setting)
        db.session.commit()

    if request.method == "POST":
        setting.ai_enabled = True if request.form.get("ai_enabled") == "on" else False

        setting.auto_escalation_enabled = (
            True if request.form.get("auto_escalation_enabled") == "on" else False
        )

        setting.fallback_message = (
            request.form.get("fallback_message") or ""
        ).strip() or "Our support team is currently unavailable. Please create a support ticket."

        setting.escalation_keywords = (
            request.form.get("escalation_keywords") or ""
        ).strip() or "angry,refund,complaint,manager,lawyer,cancel"

        setting.chatbot_tone = (
            request.form.get("chatbot_tone") or "Professional"
        ).strip()

        setting.response_length = (
            request.form.get("response_length") or "Medium"
        ).strip()

        setting.confidence_threshold = request.form.get(
            "confidence_threshold",
            type=int
        ) or 70

        if setting.confidence_threshold < 0:
            setting.confidence_threshold = 0

        if setting.confidence_threshold > 100:
            setting.confidence_threshold = 100

        setting.system_prompt = (
            request.form.get("system_prompt") or ""
        ).strip()

        db.session.commit()
       

        notify_feature_change(
            "ai_settings_updated",
            "AI Settings were updated.",
            admin=True,
            agent=True
        )

        socketio.emit(
            "chatbot_settings_updated",
            {
                "message": "AI settings updated"
            }
        )

        flash("AI settings updated successfully.", "primary")
        return redirect(url_for("admin.chatbot_settings"))

    return render_template(
        "admin/chatbot_settings.html",
        setting=setting
    )

@admin_blueprint.route("/agent-reports", methods=["GET", "POST"])
@login_required(role="Administrator")
def agent_reports():
    if request.method == "POST":
        report_id = request.form.get("report_id", type=int)
        new_status = (request.form.get("status") or "").strip()

        report = AgentReport.query.get_or_404(report_id)

        allowed_statuses = [
            "Open",
            "In Progress",
            "Resolved",
            "Closed"
        ]

        if new_status not in allowed_statuses:
            flash("Invalid report status.", "warning")
            return redirect(url_for("admin.agent_reports"))

        old_status = report.status

        report.status = new_status
        db.session.commit()
        notify_feature_change(
            "agent_report_updated",
            "Agent Report status was updated.",
            admin=True,
            agent=True
        )

        if old_status != new_status:
            Notification.send_notification(
                message=f"your {report.report_type.lower()} report was updated to {new_status}",
                receiver_id=report.reported_by_id,
                sender_id=current_user.id,
                ticket_id=None,
                agent_report_id=report.id,
                seen=False
            )

        socketio.emit(
            "agent_report_updated",
            {
                "report_id": report.id,
                "status": report.status,
                "message": f"Agent report #{report.id} updated to {report.status}"
            }
        )

        flash("Agent report status updated.", "primary")
        return redirect(url_for("admin.agent_reports"))

    report_type = request.args.get("type", "")
    severity = request.args.get("severity", "")
    status = request.args.get("status", "")

    query = AgentReport.query

    if report_type:
        query = query.filter(AgentReport.report_type == report_type)

    if severity:
        query = query.filter(AgentReport.severity == severity)

    if status:
        query = query.filter(AgentReport.status == status)

    reports = (
        query
        .order_by(desc(AgentReport.created_at))
        .all()
    )

    open_report_count = (
        AgentReport.query
        .filter(AgentReport.status != "Closed")
        .count()
    )

    return render_template(
        "admin/agent_reports.html",
        reports=reports,
        selected_type=report_type,
        selected_severity=severity,
        selected_status=status,
        open_report_count=open_report_count
    )

@admin_blueprint.route("/agent-reports/delete/<int:id>", methods=["POST"])
@login_required(role="Administrator")
def delete_agent_report(id):
    report = AgentReport.query.get_or_404(id)

    agent_id = report.reported_by_id
    report_type = report.report_type
    report_title = report.title

    Notification.query.filter(
        Notification.agent_report_id == report.id
    ).delete()

    Notification.send_notification(
        message=f"your {report_type.lower()} report '{report_title}' was deleted by admin",
        receiver_id=agent_id,
        sender_id=current_user.id,
        ticket_id=None,
        agent_report_id=None,
        seen=False
    )

    if report.file_link:
        report_upload_folder = os.path.join(
            path,
            "app/static/uploads/reports"
        )

        file_path = os.path.join(
            report_upload_folder,
            report.file_link
        )

        if os.path.exists(file_path):
            os.remove(file_path)

    db.session.delete(report)
    db.session.commit()
    notify_feature_change(
        "agent_report_updated",
        "Agent Report was deleted.",
        admin=True,
        agent=True
    )

    socketio.emit(
        "agent_report_updated",
        {
            "report_id": id,
            "message": "Agent report deleted"
        }
    )

    flash("Agent report deleted successfully.", "primary")
    return redirect(url_for("admin.agent_reports"))

@admin_blueprint.route("/agent-reports/download/<filename>")
@login_required(role="Administrator")
def download_agent_report_attachment(filename):
    report_upload_folder = os.path.join(
        path,
        "app/static/uploads/reports"
    )

    return send_file(
        os.path.join(report_upload_folder, filename),
        as_attachment=True
    )

@admin_blueprint.route(
    "/faq/toggle/<int:id>",
    methods=["POST"]
)
@login_required(role="Administrator")
def toggle_faq(id):
    faq = FAQ.query.get_or_404(id)
    faq.is_active = not faq.is_active

    db.session.commit()

    notify_feature_change(
        "knowledge_updated",
        "FAQ status was updated.",
        admin=True,
        agent=True
    )

    socketio.emit("faq_library_updated", {
        "message": "FAQ library updated"
    })

    flash("FAQ status updated.", "primary")
    return redirect(url_for("admin.knowledge_base"))


@admin_blueprint.route("/faq/delete/<int:id>", methods=["POST"])
@login_required(role="Administrator")
def delete_faq(id):
    faq = FAQ.query.get_or_404(id)


    log_system_event(
        event_type="FAQ Deleted",
        severity="Warning",
        message=f"FAQ deleted by {current_user.email}: {faq.question}",
        user_id=current_user.id
    )
    db.session.delete(faq)
    db.session.commit()
    notify_feature_change(
        "knowledge_updated",
        "FAQ was deleted from Knowledge Management.",
        admin=True,
        agent=True
    )

    socketio.emit("faq_library_updated", {
        "message": "FAQ library updated"
    })

    flash("FAQ deleted successfully.", "primary")
    return redirect(url_for("admin.knowledge_base"))


@admin_blueprint.route("/chat-logs", methods=["GET"])
@login_required(role="Administrator")
def chat_logs():
    """
    Legacy route retained for old links and notifications.

    Instead of loading the old chat-log page, it now opens the
    Pending Reviews tab in the unified AI Review Center.
    """

    return redirect(
        url_for(
            "admin.ai_review_center",
            tab="pending"
        )
    )

@admin_blueprint.route(
    "/chat-logs/review/<int:id>",
    methods=["POST"]
)
@login_required(role="Administrator")
def review_chat_log(id):
    log = ChatMessage.query.get_or_404(id)

    log.review_status = "Reviewed"
    log.reviewed_by_id = current_user.id
    log.reviewed_at = datetime.datetime.utcnow()

    db.session.commit()

    emit_feature_update(
        "ai_training_updated",
        "AI training and review data was updated.",
        receiver_roles=["Administrator"]
    )

    flash(
        "Chat message reviewed successfully.",
        "success"
    )

    return redirect(
        url_for(
            "admin.ai_review_center",
            tab="pending"
        )
    )


@admin_blueprint.route(
    "/chat-logs/approve/<int:id>",
    methods=["POST"]
)
@login_required(role="Administrator")
def approve_chat_log(id):
    log = ChatMessage.query.get_or_404(id)

    log.review_status = "Approved"
    log.reviewed_by_id = current_user.id
    log.reviewed_at = datetime.datetime.utcnow()

    db.session.commit()

    emit_feature_update(
        "ai_training_updated",
        "AI training and review data was updated.",
        receiver_roles=["Administrator"]
    )

    flash(
        "AI support response approved.",
        "success"
    )

    return redirect(
        url_for(
            "admin.ai_review_center",
            tab="pending"
        )
    )


@admin_blueprint.route(
    "/chat-logs/reject/<int:id>",
    methods=["POST"]
)
@login_required(role="Administrator")
def reject_chat_log(id):
    log = ChatMessage.query.get_or_404(id)

    log.review_status = "Rejected"
    log.reviewed_by_id = current_user.id
    log.reviewed_at = datetime.datetime.utcnow()

    db.session.commit()

    emit_feature_update(
        "ai_training_updated",
        "AI training and review data was updated.",
        receiver_roles=["Administrator"]
    )

    flash(
        "AI support response rejected and moved to training cases.",
        "warning"
    )

    return redirect(
        url_for(
            "admin.ai_review_center",
            tab="training",
            type="rejected"
        )
    )


@admin_blueprint.route(
    "/chat-logs/save-as-faq/<int:id>",
    methods=["POST"]
)
@login_required(role="Administrator")
def save_chat_log_as_faq(id):
    log = ChatMessage.query.get_or_404(id)

    if log.role != "assistant":
        flash(
            "Only AI assistant responses can be saved as FAQ answers.",
            "warning"
        )

        return redirect(
            url_for(
                "admin.ai_review_center",
                tab="pending"
            )
        )

    question = (
        request.form.get("question")
        or find_previous_customer_message(log)
        or "Customer question"
    ).strip()

    answer = (
        request.form.get("answer")
        or log.message
        or ""
    ).strip()

    category_id = request.form.get(
        "category_id",
        type=int
    )

    tags = (
        request.form.get("tags")
        or "ai-reviewed,it-support"
    ).strip()

    if not question or not answer:
        flash(
            "Question and answer are required to create an FAQ.",
            "warning"
        )

        return redirect(
            url_for(
                "admin.ai_review_center",
                tab="pending"
            )
        )

    existing_faq = FAQ.query.filter(
        FAQ.question.ilike(question)
    ).first()

    if existing_faq:
        flash(
            "An FAQ with the same question already exists.",
            "warning"
        )

        return redirect(
            url_for(
                "admin.ai_review_center",
                tab="pending"
            )
        )

    if not category_id:
        default_category = Category.query.first()

        if not default_category:
            default_category = Category(
                category="Help and support"
            )

            db.session.add(default_category)
            db.session.flush()

        category_id = default_category.id

    faq = FAQ(
        question=question,
        answer=answer,
        category_id=category_id,
        tags=tags,
        is_active=True
    )

    db.session.add(faq)

    log.review_status = "Saved as FAQ"
    log.reviewed_by_id = current_user.id
    log.reviewed_at = datetime.datetime.utcnow()

    db.session.commit()

    emit_feature_update(
        "ai_training_updated",
        "AI training and review data was updated.",
        receiver_roles=["Administrator"]
    )

    socketio.emit(
        "faq_library_updated",
        {
            "message": (
                "IT support FAQ library updated "
                "from an AI review."
            )
        }
    )

    flash(
        "AI response saved as an IT support FAQ successfully.",
        "success"
    )

    return redirect(
        url_for(
            "admin.ai_review_center",
            tab="pending"
        )
    )


# ============================================================
# REPORTS / ANALYTICS
# ============================================================

@admin_blueprint.route("/reports", methods=["GET"])
@login_required(role="Administrator")
def reports():
    status_id = request.args.get("status_id", type=int)
    priority_id = request.args.get("priority_id", type=int)
    category_id = request.args.get("category_id", type=int)
    agent_id = request.args.get("agent_id", type=int)

    query = Ticket.query

    if status_id:
        query = query.filter(Ticket.status_id == status_id)

    if priority_id:
        query = query.filter(Ticket.priority_id == priority_id)

    if category_id:
        query = query.filter(Ticket.category_id == category_id)

    if agent_id:
        query = query.filter(Ticket.owner_id == agent_id)

    tickets = query.order_by(desc(Ticket.created_at)).all()

    return render_template(
        "admin/reports.html",
        tickets=tickets,
        statuses=Status.query.all(),
        priorities=Priority.query.all(),
        categories=Category.query.all(),
        agents=User.query.filter_by(role="Agent").all()
    )


@admin_blueprint.route("/escalated-tickets", methods=["GET"])
@login_required(role="Administrator")
def escalated_tickets():
    escalated_status = Status.query.filter_by(status="Escalated").first()

    if not escalated_status:
        tickets = []
    else:
        tickets = (
            Ticket.query
            .filter(Ticket.status_id == escalated_status.id)
            .order_by(desc(Ticket.created_at))
            .all()
        )

    return render_template("admin/escalated_tickets.html", tickets=tickets)


@admin_blueprint.route("/analytics", methods=["GET"])
@login_required(role="Administrator")
def analytics():
    from datetime import datetime, timedelta

    total_tickets = Ticket.query.count()

    solved_count = (
        Ticket.query
        .join(Status)
        .filter(Status.status == "Solved")
        .count()
    )

    escalated_count = (
        Ticket.query
        .join(Status)
        .filter(Status.status == "Escalated")
        .count()
    )

    active_count = (
        Ticket.query
        .join(Status)
        .filter(
            func.lower(Status.status).notin_(
                ["closed", "solved"]
            )
        )
        .count()
    )

    today = datetime.utcnow().date()
    start_date = today - timedelta(days=6)

    dates = []
    tickets_per_day = []
    solved_per_day = []
    escalations_per_day = []

    solved_status = Status.query.filter_by(status="Solved").first()
    escalated_status = Status.query.filter_by(status="Escalated").first()

    for i in range(7):
        day = start_date + timedelta(days=i)
        next_day = day + timedelta(days=1)

        dates.append(day.strftime("%d %b"))

        tickets_per_day.append(
            Ticket.query.filter(
                Ticket.created_at >= day,
                Ticket.created_at < next_day
            ).count()
        )

        solved_per_day.append(
            Ticket.query.filter(
                Ticket.status_id == solved_status.id,
                Ticket.updated_at >= day,
                Ticket.updated_at < next_day
            ).count() if solved_status else 0
        )

        escalations_per_day.append(
            Ticket.query.filter(
                Ticket.status_id == escalated_status.id,
                Ticket.updated_at >= day,
                Ticket.updated_at < next_day
            ).count() if escalated_status else 0
        )

    status_labels = [s.status for s in Status.query.all()]
    status_counts = [Ticket.query.filter_by(status_id=s.id).count() for s in Status.query.all()]

    category_labels = [c.category for c in Category.query.all()]
    category_counts = [Ticket.query.filter_by(category_id=c.id).count() for c in Category.query.all()]

    priority_labels = [p.priority for p in Priority.query.all()]
    priority_counts = [Ticket.query.filter_by(priority_id=p.id).count() for p in Priority.query.all()]

    agent_labels = []
    agent_counts = []

    for agent in User.query.filter_by(role="Agent").all():
        agent_labels.append(agent.name)
        agent_counts.append(Ticket.query.filter_by(owner_id=agent.id).count())

    customer_labels = []
    customer_counts = []

    top_customers = (
        db.session.query(User.name, func.count(Ticket.id))
        .join(Ticket, Ticket.author_id == User.id)
        .filter(User.role == "Customer")
        .group_by(User.id)
        .order_by(func.count(Ticket.id).desc())
        .limit(5)
        .all()
    )

    for name, count in top_customers:
        customer_labels.append(name)
        customer_counts.append(count)
        
    # ============================================================
    # AI / FAQ ANALYTICS
    # ============================================================

    ai_total = ChatMessage.query.filter(
        ChatMessage.role == "assistant",
        ChatMessage.ai_used == True
    ).count()

    ai_solved = ChatMessage.query.filter(
        ChatMessage.role == "assistant",
        ChatMessage.ai_used == True,
        ChatMessage.resolution_status == "Solved"
    ).count()

    ai_not_solved = ChatMessage.query.filter(
        ChatMessage.role == "assistant",
        ChatMessage.ai_used == True,
        ChatMessage.resolution_status == "Not Solved"
    ).count()

    ai_pending = ChatMessage.query.filter(
        ChatMessage.role == "assistant",
        ChatMessage.ai_used == True,
        ChatMessage.resolution_status == "Pending"
    ).count()

    ai_accuracy = 0

    if ai_solved + ai_not_solved > 0:
        ai_accuracy = round(
            (ai_solved / (ai_solved + ai_not_solved)) * 100,
            1
        )

    faq_total = ChatMessage.query.filter(
        ChatMessage.faq_matched == True,
        ChatMessage.role == "assistant"
    ).count()

    faq_solved = ChatMessage.query.filter(
        ChatMessage.faq_matched == True,
        ChatMessage.role == "assistant",
        ChatMessage.resolution_status == "Solved"
    ).count()

    faq_not_solved = ChatMessage.query.filter(
        ChatMessage.faq_matched == True,
        ChatMessage.role == "assistant",
        ChatMessage.resolution_status == "Not Solved"
    ).count()

    faq_accuracy = 0

    if faq_solved + faq_not_solved > 0:
        faq_accuracy = round(
            (faq_solved / (faq_solved + faq_not_solved)) * 100,
            1
        )

    chatbot_escalated = ChatMessage.query.filter(
        ChatMessage.escalated == True
    ).count()

    return render_template(
        "admin/analytics.html",
        total_tickets=total_tickets,
        solved_count=solved_count,
        escalated_count=escalated_count,
        active_count=active_count,
        dates=dates,
        tickets_per_day=tickets_per_day,
        solved_per_day=solved_per_day,
        escalations_per_day=escalations_per_day,
        status_labels=status_labels,
        status_counts=status_counts,
        category_labels=category_labels,
        category_counts=category_counts,
        priority_labels=priority_labels,
        priority_counts=priority_counts,
        agent_labels=agent_labels,
        agent_counts=agent_counts,
        customer_labels=customer_labels,
        customer_counts=customer_counts,
        ai_total=ai_total,
        ai_solved=ai_solved,
        ai_not_solved=ai_not_solved,
        ai_pending=ai_pending,
        ai_accuracy=ai_accuracy,
        faq_total=faq_total,
        faq_solved=faq_solved,
        faq_not_solved=faq_not_solved,
        faq_accuracy=faq_accuracy,
        chatbot_escalated=chatbot_escalated
    
    )


@admin_blueprint.route(
    "/agent-performance",
    methods=["GET"]
)
@login_required(role="Administrator")
def agent_performance():
    agents = (
        User.query
        .filter_by(role="Agent")
        .order_by(User.name.asc())
        .all()
    )

    open_id = get_open_status_id()
    pending_id = get_pending_status_id()
    solved_id = get_solved_status_id()
    closed_id = get_closed_status_id()
    escalated_id = get_status_id(
        "Escalated",
        None
    )

    performance = []

    for agent in agents:
        base_query = Ticket.query.filter(
            Ticket.owner_id == agent.id
        )

        assigned = base_query.count()

        open_count = (
            base_query.filter(
                Ticket.status_id == open_id
            ).count()
            if open_id
            else 0
        )

        pending_count = (
            base_query.filter(
                Ticket.status_id == pending_id
            ).count()
            if pending_id
            else 0
        )

        solved_count = (
            base_query.filter(
                Ticket.status_id == solved_id
            ).count()
            if solved_id
            else 0
        )

        closed_count = (
            base_query.filter(
                Ticket.status_id == closed_id
            ).count()
            if closed_id
            else 0
        )

        escalated_count = (
            base_query.filter(
                Ticket.status_id
                == escalated_id
            ).count()
            if escalated_id
            else 0
        )

        closed_tickets = (
            base_query.filter(
                Ticket.status_id == closed_id
            ).all()
            if closed_id
            else []
        )

        resolution_seconds = []

        for ticket in closed_tickets:
            if (
                ticket.created_at
                and ticket.updated_at
            ):
                resolution_seconds.append(
                    (
                        ticket.updated_at
                        - ticket.created_at
                    ).total_seconds()
                )

        avg_hours = 0

        if resolution_seconds:
            avg_hours = round(
                (
                    sum(resolution_seconds)
                    / len(resolution_seconds)
                )
                / 3600,
                1
            )

        performance.append({
            "agent": agent,
            "assigned": assigned,
            "open": open_count,
            "pending": pending_count,
            "solved": solved_count,
            "closed": closed_count,
            "escalated": escalated_count,
            "avg_hours": avg_hours
        })

    return render_template(
        "admin/agent_performance.html",
        performance=performance
    )

@admin_blueprint.route("/security-events", methods=["GET"])
@login_required(role="Administrator")
def security_events():
    event_type = request.args.get("event_type", "")
    severity = request.args.get("severity", "")

    query = SystemEvent.query

    if event_type:
        query = query.filter(SystemEvent.event_type == event_type)

    if severity:
        query = query.filter(SystemEvent.severity == severity)

    events = (
        query
        .order_by(SystemEvent.created_at.desc())
        .all()
    )

    event_types = [
        item[0]
        for item in db.session.query(SystemEvent.event_type)
        .distinct()
        .order_by(SystemEvent.event_type.asc())
        .all()
    ]

    total_events = SystemEvent.query.count()
    warning_events = SystemEvent.query.filter_by(severity="Warning").count()
    critical_events = SystemEvent.query.filter_by(severity="Critical").count()
    info_events = SystemEvent.query.filter_by(severity="Info").count()

    return render_template(
        "admin/security_events.html",
        events=events,
        event_types=event_types,
        selected_event_type=event_type,
        selected_severity=severity,
        total_events=total_events,
        warning_events=warning_events,
        critical_events=critical_events,
        info_events=info_events
    )

@admin_blueprint.route("/system-health", methods=["GET"])
@login_required(role="Administrator")
def system_health():
    health_checks = []

    try:
        db.session.execute(text("SELECT 1"))
        health_checks.append({
            "name": "Database Connection",
            "status": "Online",
            "details": "Database connection is working.",
            "healthy": True
        })
    except Exception as e:
        health_checks.append({
            "name": "Database Connection",
            "status": "Error",
            "details": str(e),
            "healthy": False
        })

    openai_key = os.getenv("OPENAI_API_KEY")

    health_checks.append({
        "name": "OpenAI API Key",
        "status": "Available" if openai_key else "Missing",
        "details": "OpenAI API key is configured." if openai_key else "OPENAI_API_KEY is missing.",
        "healthy": True if openai_key else False
    })

    try:
        ticket_count = Ticket.query.count()
        health_checks.append({
            "name": "Tickets Table",
            "status": "Working",
            "details": f"{ticket_count} tickets found.",
            "healthy": True
        })
    except Exception as e:
        health_checks.append({
            "name": "Tickets Table",
            "status": "Error",
            "details": str(e),
            "healthy": False
        })

    try:
        notification_count = Notification.query.count()
        health_checks.append({
            "name": "Notifications Table",
            "status": "Working",
            "details": f"{notification_count} notifications found.",
            "healthy": True
        })
    except Exception as e:
        health_checks.append({
            "name": "Notifications Table",
            "status": "Error",
            "details": str(e),
            "healthy": False
        })

    try:
        chat_count = ChatMessage.query.count()
        health_checks.append({
            "name": "Chat Logs",
            "status": "Working",
            "details": f"{chat_count} chat messages found.",
            "healthy": True
        })
    except Exception as e:
        health_checks.append({
            "name": "Chat Logs",
            "status": "Error",
            "details": str(e),
            "healthy": False
        })

    try:
        event_count = SystemEvent.query.count()
        health_checks.append({
            "name": "Security Event Logs",
            "status": "Working",
            "details": f"{event_count} security events found.",
            "healthy": True
        })
    except Exception as e:
        health_checks.append({
            "name": "Security Event Logs",
            "status": "Error",
            "details": str(e),
            "healthy": False
        })

    upload_path = os.path.join(path, "app/static/uploads")

    health_checks.append({
        "name": "Upload Storage",
        "status": "Available" if os.path.exists(upload_path) else "Missing",
        "details": upload_path,
        "healthy": os.path.exists(upload_path)
    })

    maintenance = MaintenanceSetting.query.first()

    if maintenance and maintenance.enabled:
        maintenance_status = "Active"
        maintenance_details = maintenance.message
        maintenance_healthy = False
    else:
        maintenance_status = "Inactive"
        maintenance_details = "Maintenance mode is currently off."
        maintenance_healthy = True

    health_checks.append({
        "name": "Maintenance Mode",
        "status": maintenance_status,
        "details": maintenance_details,
        "healthy": maintenance_healthy
    })

    total_checks = len(health_checks)
    healthy_checks = len([check for check in health_checks if check["healthy"]])
    issue_checks = total_checks - healthy_checks

    return render_template(
        "admin/system_health.html",
        health_checks=health_checks,
        total_checks=total_checks,
        healthy_checks=healthy_checks,
        issue_checks=issue_checks
    )


@admin_blueprint.route("/maintenance-mode", methods=["GET", "POST"])
@login_required(role="Administrator")
def maintenance_mode():
    setting = MaintenanceSetting.query.first()

    if not setting:
        setting = MaintenanceSetting()
        db.session.add(setting)
        db.session.commit()
        notify_feature_change(
            "system_operations_updated",
            "Maintenance Mode settings were updated.",
            admin=True,
            agent=False
        )

    if request.method == "POST":
        old_status = setting.enabled

        setting.enabled = True if request.form.get("enabled") == "on" else False

        setting.title = (
            request.form.get("title") or "System Maintenance"
        ).strip()

        setting.message = (
            request.form.get("message") or
            "The chatbot is currently under maintenance. Please try again later or create a support ticket."
        ).strip()

        setting.allow_ticket_creation = (
            True if request.form.get("allow_ticket_creation") == "on" else False
        )

        start_time_raw = request.form.get("start_time")
        end_time_raw = request.form.get("end_time")

        setting.start_time = None
        setting.end_time = None

        if start_time_raw:
            setting.start_time = datetime.datetime.strptime(
                start_time_raw,
                "%Y-%m-%dT%H:%M"
            )

        if end_time_raw:
            setting.end_time = datetime.datetime.strptime(
                end_time_raw,
                "%Y-%m-%dT%H:%M"
            )

        if setting.start_time and setting.end_time:
            if setting.end_time <= setting.start_time:
                flash("End time must be after start time.", "warning")
                return redirect(url_for("admin.maintenance_mode"))

        setting.updated_by_id = current_user.id
        setting.updated_at = datetime.datetime.utcnow()

        db.session.commit()
        notify_feature_change(
            "system_operations_updated",
            "Maintenance Mode settings were updated.",
            admin=True,
            agent=False
        )

        if old_status != setting.enabled:
            if setting.enabled:
                log_system_event(
                    event_type="Maintenance Enabled",
                    severity="Warning",
                    message=f"Maintenance mode enabled by {current_user.email}.",
                    user_id=current_user.id
                )
            else:
                log_system_event(
                    event_type="Maintenance Disabled",
                    severity="Info",
                    message=f"Maintenance mode disabled by {current_user.email}.",
                    user_id=current_user.id
                )
        else:
            log_system_event(
                event_type="Maintenance Updated",
                severity="Info",
                message=f"Maintenance settings updated by {current_user.email}.",
                user_id=current_user.id
            )

        flash("Maintenance settings updated successfully.", "primary")
        return redirect(url_for("admin.maintenance_mode"))

    now = datetime.datetime.utcnow()

    is_currently_active = False

    if setting.enabled:
        is_currently_active = True

        if setting.start_time and now < setting.start_time:
            is_currently_active = False

        if setting.end_time and now > setting.end_time:
            is_currently_active = False

    return render_template(
        "admin/maintenance_mode.html",
        setting=setting,
        is_currently_active=is_currently_active
    )
# ============================================================
# ADMIN PLACEHOLDER / FUTURE MODULE ROUTES
# ============================================================

def admin_placeholder_page(title, message):
    return render_template(
        "admin/placeholder.html",
        page_title=title,
        page_message=message
    )


# ============================================================
# AI TRAINING & REVIEW PAGES
# ============================================================
# ============================================================
# AI TRAINING CASES
# ============================================================

# ============================================================
# UNIFIED AI REVIEW CENTER
# ============================================================

@admin_blueprint.route("/ai/review-center", methods=["GET"])
@login_required(role="Administrator")
def ai_review_center():
    """
    Unified AI review page.

    Tabs:
    - Pending reviews
    - Training cases
    - Recurring issues
    - Learning summary
    """

    active_tab = (
        request.args.get("tab")
        or "pending"
    ).strip().lower()

    allowed_tabs = {
        "pending",
        "training",
        "recurring",
        "summary"
    }

    if active_tab not in allowed_tabs:
        active_tab = "pending"

    training_type = (
        request.args.get("type")
        or "all"
    ).strip().lower()

    allowed_training_types = {
        "all",
        "failed",
        "escalated",
        "rejected"
    }

    if training_type not in allowed_training_types:
        training_type = "all"

    # ========================================================
    # PENDING REVIEWS
    # ========================================================

    pending_logs = (
        ChatMessage.query
        .filter(
            ChatMessage.role == "assistant",
            ChatMessage.review_status == "Pending"
        )
        .order_by(ChatMessage.created_at.desc())
        .all()
    )

    # ========================================================
    # TRAINING CASES
    # ========================================================

    training_query = ChatMessage.query.filter(
        ChatMessage.role == "assistant"
    )

    if training_type == "failed":
        training_query = training_query.filter(
            ChatMessage.resolution_status == "Not Solved"
        )

    elif training_type == "escalated":
        training_query = training_query.filter(
            ChatMessage.escalated == True
        )

    elif training_type == "rejected":
        training_query = training_query.filter(
            ChatMessage.review_status == "Rejected"
        )

    else:
        training_query = training_query.filter(
            or_(
                ChatMessage.resolution_status == "Not Solved",
                ChatMessage.escalated == True,
                ChatMessage.review_status == "Rejected"
            )
        )

    training_logs = (
        training_query
        .order_by(ChatMessage.created_at.desc())
        .all()
    )

    # ========================================================
    # RECURRING CUSTOMER ISSUES
    # ========================================================

    recurring_issues = (
        db.session.query(
            ChatMessage.message,
            func.count(ChatMessage.id).label("total")
        )
        .filter(
            ChatMessage.role == "user",
            ChatMessage.message.isnot(None),
            ChatMessage.message != ""
        )
        .group_by(ChatMessage.message)
        .having(func.count(ChatMessage.id) > 1)
        .order_by(
            func.count(ChatMessage.id).desc()
        )
        .all()
    )

    # ========================================================
    # SUMMARY COUNTS
    # ========================================================

    pending_count = (
        ChatMessage.query
        .filter(
            ChatMessage.role == "assistant",
            ChatMessage.review_status == "Pending"
        )
        .count()
    )

    approved_count = (
        ChatMessage.query
        .filter(
            ChatMessage.role == "assistant",
            ChatMessage.review_status == "Approved"
        )
        .count()
    )

    rejected_count = (
        ChatMessage.query
        .filter(
            ChatMessage.role == "assistant",
            ChatMessage.review_status == "Rejected"
        )
        .count()
    )

    failed_count = (
        ChatMessage.query
        .filter(
            ChatMessage.role == "assistant",
            ChatMessage.resolution_status == "Not Solved"
        )
        .count()
    )

    solved_count = (
        ChatMessage.query
        .filter(
            ChatMessage.role == "assistant",
            ChatMessage.resolution_status == "Solved"
        )
        .count()
    )

    escalated_count = (
        ChatMessage.query
        .filter(
            ChatMessage.role == "assistant",
            ChatMessage.escalated == True
        )
        .count()
    )

    saved_faq_count = (
        ChatMessage.query
        .filter(
            ChatMessage.role == "assistant",
            ChatMessage.review_status == "Saved as FAQ"
        )
        .count()
    )

    training_case_count = (
        ChatMessage.query
        .filter(ChatMessage.role == "assistant")
        .filter(
            or_(
                ChatMessage.resolution_status == "Not Solved",
                ChatMessage.escalated == True,
                ChatMessage.review_status == "Rejected"
            )
        )
        .count()
    )

    total_resolved_outcomes = solved_count + failed_count

    success_rate = 0

    if total_resolved_outcomes > 0:
        success_rate = round(
            (solved_count / total_resolved_outcomes) * 100,
            1
        )

    categories = (
        Category.query
        .order_by(Category.category.asc())
        .all()
    )

    return render_template(
        "admin/ai_review_center.html",

        active_tab=active_tab,
        training_type=training_type,

        pending_logs=pending_logs,
        training_logs=training_logs,
        recurring_issues=recurring_issues,

        pending_count=pending_count,
        approved_count=approved_count,
        rejected_count=rejected_count,
        failed_count=failed_count,
        solved_count=solved_count,
        escalated_count=escalated_count,
        saved_faq_count=saved_faq_count,
        training_case_count=training_case_count,
        success_rate=success_rate,

        categories=categories,

        find_previous_customer_message=find_previous_customer_message,
        clean_ai_message=clean_ai_message
    )


@admin_blueprint.route("/ai/training-cases", methods=["GET"])
@login_required(role="Administrator")
def training_cases():
    """
    Legacy route retained for old sidebar links, bookmarks,
    notifications, and previously generated URLs.

    The old type filter is preserved and passed to the unified
    AI Review Center.
    """

    case_type = (
        request.args.get("type")
        or "all"
    ).strip().lower()

    allowed_types = {
        "all",
        "failed",
        "escalated",
        "rejected"
    }

    if case_type not in allowed_types:
        case_type = "all"

    return redirect(
        url_for(
            "admin.ai_review_center",
            tab="training",
            type=case_type
        )
    )

@admin_blueprint.route("/ai/repeated-questions", methods=["GET"])
@login_required(role="Administrator")
def repeated_questions():
    """
    Legacy route for the old Recurring IT Issues page.

    Recurring issues now appear as a tab inside the unified
    AI Review Center.
    """

    return redirect(
        url_for(
            "admin.ai_review_center",
            tab="recurring"
        )
    )


@admin_blueprint.route("/ai/learning-dashboard", methods=["GET"])
@login_required(role="Administrator")
def ai_learning_dashboard():
    """
    Legacy route for the old standalone AI learning dashboard.

    Learning statistics are now displayed under the Learning
    Summary tab of the unified AI Review Center.
    """

    return redirect(
        url_for(
            "admin.ai_review_center",
            tab="summary"
        )
    )

# ---------------- KNOWLEDGE MANAGEMENT ----------------

@admin_blueprint.route("/knowledge/articles", methods=["GET", "POST"])
@login_required(role="Administrator")
def knowledge_articles():
    from app.admin.forms import KnowledgeArticleForm
    from app.models import KnowledgeArticle

    form = KnowledgeArticleForm()

    form.category.choices = [
        (c.id, c.category)
        for c in Category.query.order_by(Category.category.asc()).all()
    ]

    if form.validate_on_submit():
        article = KnowledgeArticle(
            title=form.title.data,
            content=form.content.data,
            category_id=form.category.data,
            tags=form.tags.data,
            created_by_id=current_user.id,
            is_active=True
        )

        db.session.add(article)
        db.session.commit()

        notify_feature_change(
            "knowledge_updated",
            "Knowledge Base Article was created.",
            admin=True,
            agent=True
        )

        flash("Knowledge article created successfully.", "primary")
        return redirect(url_for("admin.knowledge_articles"))

    articles = (
        KnowledgeArticle.query
        .order_by(desc(KnowledgeArticle.created_at))
        .all()
    )

    return render_template(
        "admin/knowledge_articles.html",
        form=form,
        articles=articles
    )

@admin_blueprint.route("/knowledge/articles/edit/<int:id>", methods=["GET", "POST"])
@login_required(role="Administrator")
def edit_knowledge_article(id):
    article = KnowledgeArticle.query.get_or_404(id)

    form = KnowledgeArticleForm(obj=article)

    form.category.choices = [
        (c.id, c.category)
        for c in Category.query.order_by(Category.category.asc()).all()
    ]

    if request.method == "GET":
        form.category.data = article.category_id

    if form.validate_on_submit():
        article.title = form.title.data
        article.content = form.content.data
        article.category_id = form.category.data
        article.tags = form.tags.data
        article.updated_at = datetime.datetime.utcnow()

        db.session.commit()

        notify_feature_change(
            "knowledge_updated",
            "Knowledge Base Article was updated.",
            admin=True,
            agent=True
        )

        flash("Knowledge article updated successfully.", "success")
        return redirect(url_for("admin.knowledge_articles"))

    return render_template(
        "admin/edit_knowledge_article.html",
        form=form,
        article=article
    )

@admin_blueprint.route("/knowledge/articles/toggle/<int:id>", methods=["POST"])
@login_required(role="Administrator")
def toggle_knowledge_article(id):
    article = KnowledgeArticle.query.get_or_404(id)

    article.is_active = not article.is_active

    db.session.commit()
    
    notify_feature_change(
        "knowledge_updated",
        "Knowledge Base Article status was updated.",
        admin=True,
        agent=True
    )


    if article.is_active:
        flash("Knowledge article enabled successfully.", "primary")
    else:
        flash("Knowledge article disabled successfully.", "warning")

    return redirect(url_for("admin.knowledge_articles"))

@admin_blueprint.route("/knowledge/articles/delete/<int:id>", methods=["POST"])
@login_required(role="Administrator")
def delete_knowledge_article(id):
    article = KnowledgeArticle.query.get_or_404(id)


    log_system_event(
        event_type="Knowledge Article Deleted",
        severity="Warning",
        message=f"Knowledge article deleted by {current_user.email}: {article.title}",
        user_id=current_user.id
    )
    db.session.delete(article)
    db.session.commit()
    
    notify_feature_change(
        "knowledge_updated",
        "Knowledge Base Article was deleted.",
        admin=True,
        agent=True
    )

    flash(
        "Knowledge article deleted successfully.",
        "primary"
    )

    return redirect(url_for("admin.knowledge_articles"))




@admin_blueprint.route("/knowledge/faq-suggestions")
@login_required(role="Administrator")
def faq_suggestions():

    failed_questions = (
        ChatMessage.query
        .filter(
            ChatMessage.role == "assistant",
            ChatMessage.resolution_status == "Not Solved"
        )
        .order_by(desc(ChatMessage.created_at))
        .all()
    )

    repeated_questions = (
        db.session.query(
            ChatMessage.message,
            func.count(ChatMessage.id).label("count")
        )
        .filter(ChatMessage.role == "user")
        .group_by(ChatMessage.message)
        .having(func.count(ChatMessage.id) > 1)
        .order_by(func.count(ChatMessage.id).desc())
        .all()
    )

    categories = (
        Category.query
        .order_by(Category.category.asc())
        .all()
    )

    return render_template(
        "admin/faq_suggestions.html",
        failed_questions=failed_questions,
        repeated_questions=repeated_questions,
        categories=categories,
        find_previous_customer_message=find_previous_customer_message
    )
@admin_blueprint.route("/knowledge/faq-suggestions/create", methods=["POST"])
@login_required(role="Administrator")
def create_faq_from_suggestion():
    question = (request.form.get("question") or "").strip()
    answer = (request.form.get("answer") or "").strip()
    category_id = request.form.get("category_id", type=int)
    tags = (request.form.get("tags") or "faq-suggestion").strip()

    if not question or not answer:
        flash(
            "Question and answer are required.",
            "warning"
        )

        return redirect(
            url_for(
                "admin.ai_review_center",
                tab="training"
            )
        )

    existing_faq = FAQ.query.filter(
        FAQ.question.ilike(question)
    ).first()

    if existing_faq:
        flash(
            "An FAQ with the same question already exists.",
            "warning"
        )

        return redirect(
            url_for(
                "admin.ai_review_center",
                tab="training"
            )
        )

    faq = FAQ(
        question=question,
        answer=answer,
        category_id=category_id,
        tags=tags,
        is_active=True
    )

    db.session.add(faq)
    db.session.commit()

    notify_feature_change(
        "knowledge_updated",
        "FAQ was created from a suggestion.",
        admin=True,
        agent=True
    )

    socketio.emit("faq_library_updated", {
        "message": "FAQ created from suggestion"
    })

    flash("FAQ created from suggestion successfully.", "primary")
    return redirect(url_for("admin.faq_suggestions"))



@admin_blueprint.route("/knowledge/analytics")
@login_required(role="Administrator")
def knowledge_analytics():

    faq_count = FAQ.query.count()

    article_count = KnowledgeArticle.query.count()

    active_count = (
        KnowledgeArticle.query
        .filter_by(is_active=True)
        .count()
    )

    inactive_count = (
        KnowledgeArticle.query
        .filter_by(is_active=False)
        .count()
    )

    recent_articles = (
        KnowledgeArticle.query
        .order_by(KnowledgeArticle.created_at.desc())
        .limit(5)
        .all()
    )

    recent_faqs = (
        FAQ.query
        .order_by(FAQ.created_at.desc())
        .limit(5)
        .all()
    )

    if hasattr(FAQ, "view_count"):
        top_faqs = (
            FAQ.query
            .order_by(
                FAQ.view_count.desc()
            )
            .limit(10)
            .all()
        )
    else:
        top_faqs = (
            FAQ.query
            .order_by(
                FAQ.created_at.desc()
            )
            .limit(10)
            .all()
        )
       
    if hasattr(
        KnowledgeArticle,
        "view_count"
    ):
        top_articles = (
            KnowledgeArticle.query
            .order_by(
                KnowledgeArticle.view_count.desc()
            )
            .limit(10)
            .all()
        )
    else:
        top_articles = (
            KnowledgeArticle.query
            .order_by(
                KnowledgeArticle.created_at.desc()
            )
            .limit(10)
            .all()
        )

    


    return render_template(
        "admin/knowledge_analytics.html",
        faq_count=faq_count,
        article_count=article_count,
        active_count=active_count,
        inactive_count=inactive_count,
        recent_articles=recent_articles,
        recent_faqs=recent_faqs,
        top_faqs=top_faqs,
        top_articles=top_articles
    )

# ---------------- AGENT KNOWLEDGE ----------------


@admin_blueprint.route("/agent-knowledge/solutions")
@login_required(role="Administrator")
def agent_solution_library():

    status = request.args.get("status")
    category_id = request.args.get("category_id")

    query = AgentSolution.query

    if status:
        query = query.filter(
            AgentSolution.status == status
        )

    if category_id:
        query = query.filter(
            AgentSolution.category_id == int(category_id)
        )

    solutions = (
        query.order_by(
            AgentSolution.created_at.desc()
        )
        .all()
    )

    return render_template(
        "admin/agent_solution_library.html",
        solutions=solutions,
        categories=Category.query.order_by(
            Category.category.asc()
        ).all(),
        selected_status=status,
        selected_category_id=int(category_id)
        if category_id else None,
        total_solutions=AgentSolution.query.count(),
        pending_count=AgentSolution.query.filter_by(
            status="Pending"
        ).count(),
        approved_count=AgentSolution.query.filter_by(
            status="Approved"
        ).count(),
        rejected_count=AgentSolution.query.filter_by(
            status="Rejected"
        ).count()
    )
@admin_blueprint.route(
    "/agent-knowledge/solutions/<int:id>/approve",
    methods=["POST"]
)
@login_required(role="Administrator")
def approve_agent_solution(id):

    solution = AgentSolution.query.get_or_404(id)

    solution.status = "Approved"

    db.session.commit()
    notify_feature_change(
        "agent_knowledge_updated",
        "Agent Solution was approved.",
        admin=True,
        agent=True
    )

    flash(
        "Solution approved successfully.",
        "success"
    )

    return redirect(
        url_for("admin.agent_solution_library")
    )
@admin_blueprint.route(
    "/agent-knowledge/solutions/<int:id>/reject",
    methods=["POST"]
)
@login_required(role="Administrator")
def reject_agent_solution(id):

    solution = AgentSolution.query.get_or_404(id)

    solution.status = "Rejected"

    db.session.commit()
    
    notify_feature_change(
        "agent_knowledge_updated",
        "Agent Solution was rejected.",
        admin=True,
        agent=True
    )
    flash(
        "Solution rejected successfully.",
        "warning"
    )

    return redirect(
        url_for("admin.agent_solution_library")
    )
@admin_blueprint.route(
    "/agent-knowledge/solutions/<int:id>/delete",
    methods=["POST"]
)
@login_required(role="Administrator")
def delete_agent_solution(id):

    solution = AgentSolution.query.get_or_404(id)

    db.session.delete(solution)

    db.session.commit()
    
    notify_feature_change(
        "agent_knowledge_updated",
        "Agent Solution was deleted.",
        admin=True,
        agent=True
    )
    flash(
        "Solution deleted successfully.",
        "success"
    )

    return redirect(
        url_for("admin.agent_solution_library")
    )

@admin_blueprint.route("/agent-knowledge/closed-tickets", methods=["GET"])
@login_required(role="Administrator")
def closed_ticket_knowledge():
    closed_status = Status.query.filter_by(status="Closed").first()
    solved_status = Status.query.filter_by(status="Solved").first()

    status_ids = []

    if closed_status:
        status_ids.append(closed_status.id)

    if solved_status:
        status_ids.append(solved_status.id)

    tickets = []

    if status_ids:
        tickets = (
            Ticket.query
            .filter(Ticket.status_id.in_(status_ids))
            .order_by(desc(Ticket.updated_at), desc(Ticket.created_at))
            .all()
        )

    return render_template(
        "admin/closed_ticket_knowledge.html",
        tickets=tickets,
        categories=Category.query.order_by(Category.category.asc()).all()
    )


@admin_blueprint.route("/agent-knowledge/closed-tickets/<int:id>/convert", methods=["POST"])
@login_required(role="Administrator")
def convert_closed_ticket_to_solution(id):
    ticket = Ticket.query.get_or_404(id)

    title = (request.form.get("title") or ticket.subject or "").strip()
    solution_text = (request.form.get("solution") or "").strip()
    category_id = request.form.get("category_id", type=int)
    tags = (request.form.get("tags") or "closed-ticket, agent-solution").strip()

    if not title or not solution_text:
        flash("Title and solution are required.", "warning")
        return redirect(url_for("admin.closed_ticket_knowledge"))

    existing_solution = AgentSolution.query.filter_by(ticket_id=ticket.id).first()

    if existing_solution:
        flash("This ticket has already been converted into an agent solution.", "warning")
        return redirect(url_for("admin.closed_ticket_knowledge"))

    solution = AgentSolution(
        title=title,
        solution=solution_text,
        category_id=category_id or ticket.category_id,
        tags=tags,
        submitted_by_id=ticket.owner_id or current_user.id,
        ticket_id=ticket.id,
        status="Approved"
    )

    db.session.add(solution)
    db.session.commit()
    notify_feature_change(
        "agent_knowledge_updated",
        "Closed ticket was converted into an Agent Solution.",
        admin=True,
        agent=True
    )

    flash("Closed ticket converted into agent solution successfully.", "success")
    return redirect(url_for("admin.agent_solution_library"))

@admin_blueprint.route("/agent-knowledge/contributions", methods=["GET"])
@login_required(role="Administrator")
def agent_contributions():
    agents = User.query.filter_by(role="Agent").order_by(User.name.asc()).all()

    contributions = []

    for agent in agents:
        total_solutions = AgentSolution.query.filter_by(
            submitted_by_id=agent.id
        ).count()

        pending_solutions = AgentSolution.query.filter_by(
            submitted_by_id=agent.id,
            status="Pending"
        ).count()

        approved_solutions = AgentSolution.query.filter_by(
            submitted_by_id=agent.id,
            status="Approved"
        ).count()

        rejected_solutions = AgentSolution.query.filter_by(
            submitted_by_id=agent.id,
            status="Rejected"
        ).count()

        total_reuse = (
            db.session.query(func.coalesce(func.sum(AgentSolution.reuse_count), 0))
            .filter(AgentSolution.submitted_by_id == agent.id)
            .scalar()
        )

        total_views = (
            db.session.query(func.coalesce(func.sum(AgentSolution.view_count), 0))
            .filter(AgentSolution.submitted_by_id == agent.id)
            .scalar()
        )

        contributions.append({
            "agent": agent,
            "total_solutions": total_solutions,
            "pending_solutions": pending_solutions,
            "approved_solutions": approved_solutions,
            "rejected_solutions": rejected_solutions,
            "total_reuse": total_reuse,
            "total_views": total_views
        })

    return render_template(
        "admin/agent_contributions.html",
        contributions=contributions
    )

# ============================================================
# ADVANCED ANALYTICS & EXPORT REPORTS
# ============================================================

@admin_blueprint.route("/analytics/chatbot-performance", methods=["GET"])
@login_required(role="Administrator")
def chatbot_performance():
    total_messages = ChatMessage.query.count()

    total_ai_messages = ChatMessage.query.filter(
        ChatMessage.role == "assistant",
        ChatMessage.ai_used == True
    ).count()

    faq_matches = ChatMessage.query.filter(
        ChatMessage.role == "assistant",
        ChatMessage.faq_matched == True
    ).count()

    solved_count = ChatMessage.query.filter(
        ChatMessage.role == "assistant",
        ChatMessage.resolution_status == "Solved"
    ).count()

    not_solved_count = ChatMessage.query.filter(
        ChatMessage.role == "assistant",
        ChatMessage.resolution_status == "Not Solved"
    ).count()

    pending_count = ChatMessage.query.filter(
        ChatMessage.role == "assistant",
        ChatMessage.resolution_status == "Pending"
    ).count()

    escalated_count = ChatMessage.query.filter(
        ChatMessage.escalated == True
    ).count()

    approved_count = ChatMessage.query.filter_by(
        review_status="Approved"
    ).count()

    rejected_count = ChatMessage.query.filter_by(
        review_status="Rejected"
    ).count()

    saved_faq_count = ChatMessage.query.filter_by(
        review_status="Saved as FAQ"
    ).count()

    success_rate = 0
    if solved_count + not_solved_count > 0:
        success_rate = round(
            (solved_count / (solved_count + not_solved_count)) * 100,
            1
        )

    escalation_rate = 0
    if total_ai_messages > 0:
        escalation_rate = round(
            (escalated_count / total_ai_messages) * 100,
            1
        )

    return render_template(
        "admin/chatbot_performance.html",
        total_messages=total_messages,
        total_ai_messages=total_ai_messages,
        faq_matches=faq_matches,
        solved_count=solved_count,
        not_solved_count=not_solved_count,
        pending_count=pending_count,
        escalated_count=escalated_count,
        approved_count=approved_count,
        rejected_count=rejected_count,
        saved_faq_count=saved_faq_count,
        success_rate=success_rate,
        escalation_rate=escalation_rate
    )


@admin_blueprint.route("/analytics/resolution-comparison", methods=["GET"])
@login_required(role="Administrator")
def resolution_comparison():
    faq_solved = ChatMessage.query.filter(
        ChatMessage.role == "assistant",
        ChatMessage.faq_matched == True,
        ChatMessage.resolution_status == "Solved"
    ).count()

    faq_failed = ChatMessage.query.filter(
        ChatMessage.role == "assistant",
        ChatMessage.faq_matched == True,
        ChatMessage.resolution_status == "Not Solved"
    ).count()

    ai_solved = ChatMessage.query.filter(
        ChatMessage.role == "assistant",
        ChatMessage.ai_used == True,
        ChatMessage.resolution_status == "Solved"
    ).count()

    ai_failed = ChatMessage.query.filter(
        ChatMessage.role == "assistant",
        ChatMessage.ai_used == True,
        ChatMessage.resolution_status == "Not Solved"
    ).count()

    human_solved = Ticket.query.join(Status).filter(
        Status.status.in_(["Solved", "Closed"])
    ).count()

    escalated = ChatMessage.query.filter(
        ChatMessage.escalated == True
    ).count()

    return render_template(
        "admin/resolution_comparison.html",
        faq_solved=faq_solved,
        faq_failed=faq_failed,
        ai_solved=ai_solved,
        ai_failed=ai_failed,
        human_solved=human_solved,
        escalated=escalated
    )


@admin_blueprint.route("/analytics/export-reports", methods=["GET"])
@login_required(role="Administrator")
def export_reports():
    return render_template("admin/export_reports.html")


def generate_csv_response(filename, headers, rows):
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(headers)

    for row in rows:
        writer.writerow(row)

    response = Response(
        output.getvalue(),
        mimetype="text/csv"
    )

    response.headers["Content-Disposition"] = f"attachment; filename={filename}"

    return response


@admin_blueprint.route("/analytics/export/tickets", methods=["GET"])
@login_required(role="Administrator")
def export_tickets_csv():
    tickets = Ticket.query.order_by(desc(Ticket.created_at)).all()

    rows = []

    for ticket in tickets:
        rows.append([
            ticket.number,
            ticket.subject,
            ticket.author.name if ticket.author else "",
            ticket.owner.name if ticket.owner else "",
            ticket.category.category if ticket.category else "",
            ticket.priority.priority if ticket.priority else "",
            ticket.status.status if ticket.status else "",
            ticket.created_at.strftime("%Y-%m-%d %H:%M") if ticket.created_at else ""
        ])

    return generate_csv_response(
        "ticket_report.csv",
        [
            "Ticket Number",
            "Subject",
            "Customer",
            "Assigned Agent",
            "Category",
            "Priority",
            "Status",
            "Created At"
        ],
        rows
    )

@admin_blueprint.route("/analytics/export/chatbot", methods=["GET"])
@login_required(role="Administrator")
def export_chatbot_csv():
    logs = ChatMessage.query.order_by(desc(ChatMessage.created_at)).all()

    rows = []

    for log in logs:
        rows.append([
            log.user.name if log.user else "Guest",
            log.role,
            log.message,
            "Yes" if log.faq_matched else "No",
            "Yes" if log.ai_used else "No",
            "Yes" if log.escalated else "No",
            log.resolution_status,
            log.review_status,
            log.created_at.strftime("%Y-%m-%d %H:%M") if log.created_at else ""
        ])

    return generate_csv_response(
        "chatbot_report.csv",
        [
            "User",
            "Role",
            "Message",
            "FAQ Matched",
            "AI Used",
            "Escalated",
            "Resolution Status",
            "Review Status",
            "Created At"
        ],
        rows
    )


@admin_blueprint.route("/analytics/export/faqs", methods=["GET"])
@login_required(role="Administrator")
def export_faqs_csv():
    faqs = FAQ.query.order_by(desc(FAQ.created_at)).all()

    rows = []

    for faq in faqs:
        rows.append([
            faq.question,
            faq.answer,
            faq.category.category if faq.category else "",
            faq.tags or "",
            "Active" if faq.is_active else "Inactive",
            faq.view_count if hasattr(faq, "view_count") else 0,
            faq.created_at.strftime("%Y-%m-%d %H:%M") if faq.created_at else ""
        ])

    return generate_csv_response(
        "faq_report.csv",
        [
            "Question",
            "Answer",
            "Category",
            "Tags",
            "Status",
            "Views",
            "Created At"
        ],
        rows
    )


@admin_blueprint.route("/analytics/export/articles", methods=["GET"])
@login_required(role="Administrator")
def export_articles_csv():
    articles = KnowledgeArticle.query.order_by(desc(KnowledgeArticle.created_at)).all()

    rows = []

    for article in articles:
        rows.append([
            article.title,
            article.category.category if article.category else "",
            article.tags or "",
            "Active" if article.is_active else "Inactive",
            article.view_count if hasattr(article, "view_count") else 0,
            article.created_by.name if article.created_by else "",
            article.created_at.strftime("%Y-%m-%d %H:%M") if article.created_at else ""
        ])

    return generate_csv_response(
        "knowledge_article_report.csv",
        [
            "Title",
            "Category",
            "Tags",
            "Status",
            "Views",
            "Created By",
            "Created At"
        ],
        rows
    )

@admin_blueprint.route("/training-cases/convert/<int:id>", methods=["POST"])
@login_required(role="Administrator")
def convert_training_case_to_faq(id):
    chat = ChatMessage.query.get_or_404(id)

    question = (
        request.form.get("question") or
        find_previous_customer_message(chat) or
        ""
    ).strip()

    answer = (
        request.form.get("answer") or
        chat.message or
        ""
    ).strip()

    category_id = request.form.get("category_id", type=int)

    tags = (
        request.form.get("tags") or
        "training-case, chatbot-learning"
    ).strip()

    if not question or not answer:
        flash("Question and answer are required.", "warning")
        return redirect(url_for("admin.training_cases"))

    existing = FAQ.query.filter(
        FAQ.question.ilike(question)
    ).first()

    if existing:
        flash("A FAQ with the same question already exists.", "warning")
        return redirect(url_for("admin.training_cases"))

    if not category_id:
        default_category = Category.query.first()

        if not default_category:
            default_category = Category(category="Help and support")
            db.session.add(default_category)
            db.session.commit()

        category_id = default_category.id

    faq = FAQ(
        question=question,
        answer=answer,
        category_id=category_id,
        tags=tags,
        is_active=True
    )

    db.session.add(faq)

    chat.review_status = "Saved as FAQ"
    chat.reviewed_by_id = current_user.id
    chat.reviewed_at = datetime.datetime.utcnow()

    db.session.commit()
    emit_feature_update(
        "ai_training_updated",
        "AI training and review data was updated.",
        receiver_roles=["Administrator"]
    )

    socketio.emit(
        "faq_library_updated",
        {
            "message": "FAQ created from training case"
        }
    )

    flash("Training case converted to FAQ successfully.", "success")
    return redirect(url_for("admin.knowledge_base"))

@admin_blueprint.route("/analytics/customer-satisfaction")
@login_required(role="Administrator")
def customer_satisfaction():
    total_reviews = CustomerSatisfaction.query.count()

    average_rating = (
        db.session.query(func.avg(CustomerSatisfaction.rating))
        .scalar()
    )

    average_rating = round(average_rating or 0, 1)

    satisfied_reviews = (
        CustomerSatisfaction.query
        .filter(CustomerSatisfaction.rating >= 4)
        .count()
    )

    unsatisfied_reviews = (
        CustomerSatisfaction.query
        .filter(CustomerSatisfaction.rating <= 2)
        .count()
    )

    satisfaction_percent = 0
    unsatisfied_percent = 0

    if total_reviews > 0:
        satisfaction_percent = round((satisfied_reviews / total_reviews) * 100, 1)
        unsatisfied_percent = round((unsatisfied_reviews / total_reviews) * 100, 1)

    recent_reviews = (
        CustomerSatisfaction.query
        .order_by(CustomerSatisfaction.created_at.desc())
        .limit(10)
        .all()
    )

    top_rated_agents = (
        db.session.query(
            User,
            func.avg(CustomerSatisfaction.rating).label("avg_rating"),
            func.count(CustomerSatisfaction.id).label("review_count")
        )
        .join(Ticket, Ticket.owner_id == User.id)
        .join(CustomerSatisfaction, CustomerSatisfaction.ticket_id == Ticket.id)
        .filter(User.role == "Agent")
        .group_by(User.id)
        .order_by(func.avg(CustomerSatisfaction.rating).desc())
        .limit(10)
        .all()
    )

    return render_template(
        "admin/customer_satisfaction.html",
        total_reviews=total_reviews,
        average_rating=average_rating,
        satisfied_reviews=satisfied_reviews,
        unsatisfied_reviews=unsatisfied_reviews,
        satisfaction_percent=satisfaction_percent,
        unsatisfied_percent=unsatisfied_percent,
        recent_reviews=recent_reviews,
        top_rated_agents=top_rated_agents
    )


@admin_blueprint.route(
    "/email-logs",
    methods=["GET"]
)
@login_required(role="Administrator")
def email_logs():
    search = (
        request.args.get("search")
        or ""
    ).strip()

    selected_status = (
        request.args.get("status")
        or ""
    ).strip()

    selected_type = (
        request.args.get("email_type")
        or ""
    ).strip()

    date_from = (
        request.args.get("date_from")
        or ""
    ).strip()

    date_to = (
        request.args.get("date_to")
        or ""
    ).strip()

    page = request.args.get(
        "page",
        default=1,
        type=int
    )

    per_page = request.args.get(
        "per_page",
        default=20,
        type=int
    )

    allowed_page_sizes = [
        10,
        20,
        50,
        100
    ]

    if per_page not in allowed_page_sizes:
        per_page = 20

    query = EmailLog.query

    # ========================================================
    # SEARCH
    # ========================================================

    if search:
        search_pattern = (
            f"%{search}%"
        )

        query = query.filter(
            or_(
                EmailLog.recipient.ilike(
                    search_pattern
                ),
                EmailLog.subject.ilike(
                    search_pattern
                ),
                EmailLog.email_type.ilike(
                    search_pattern
                ),
                EmailLog.error_message.ilike(
                    search_pattern
                )
            )
        )

    # ========================================================
    # STATUS FILTER
    # ========================================================

    if selected_status in [
        "Pending",
        "Sent",
        "Failed"
    ]:
        query = query.filter(
            EmailLog.status
            == selected_status
        )

    # ========================================================
    # EMAIL-TYPE FILTER
    # ========================================================

    if selected_type:
        query = query.filter(
            EmailLog.email_type
            == selected_type
        )

    # ========================================================
    # DATE FILTERS
    # ========================================================

    if date_from:
        try:
            start_date = (
                datetime.datetime.strptime(
                    date_from,
                    "%Y-%m-%d"
                )
            )

            query = query.filter(
                EmailLog.created_at
                >= start_date
            )

        except ValueError:
            flash(
                "The From date is invalid.",
                "warning"
            )

    if date_to:
        try:
            end_date = (
                datetime.datetime.strptime(
                    date_to,
                    "%Y-%m-%d"
                )
                + datetime.timedelta(
                    days=1
                )
            )

            query = query.filter(
                EmailLog.created_at
                < end_date
            )

        except ValueError:
            flash(
                "The To date is invalid.",
                "warning"
            )

    # ========================================================
    # PAGINATION
    # ========================================================

    pagination = (
        query
        .order_by(
            EmailLog.created_at.desc(),
            EmailLog.id.desc()
        )
        .paginate(
            page=page,
            per_page=per_page,
            error_out=False
        )
    )

    logs = pagination.items

    # ========================================================
    # OVERALL STATISTICS
    # These counts are not affected by filters.
    # ========================================================

    total = (
        EmailLog.query.count()
    )

    sent = (
        EmailLog.query
        .filter(
            EmailLog.status == "Sent"
        )
        .count()
    )

    failed = (
        EmailLog.query
        .filter(
            EmailLog.status == "Failed"
        )
        .count()
    )

    pending = (
        EmailLog.query
        .filter(
            EmailLog.status == "Pending"
        )
        .count()
    )

    email_types = [
        row[0]
        for row in (
            db.session.query(
                EmailLog.email_type
            )
            .filter(
                EmailLog.email_type.isnot(
                    None
                )
            )
            .distinct()
            .order_by(
                EmailLog.email_type.asc()
            )
            .all()
        )
        if row[0]
    ]

    return render_template(
        "admin/email_logs.html",
        logs=logs,
        pagination=pagination,
        total=total,
        sent=sent,
        failed=failed,
        pending=pending,
        email_types=email_types,
        search=search,
        selected_status=selected_status,
        selected_type=selected_type,
        date_from=date_from,
        date_to=date_to,
        per_page=per_page
    )


@admin_blueprint.route(
    "/email-logs/delete/<int:log_id>",
    methods=["POST"]
)
@login_required(role="Administrator")
def delete_email_log(log_id):
    email_log = (
        EmailLog.query.get_or_404(
            log_id
        )
    )

    try:
        db.session.delete(
            email_log
        )

        db.session.commit()

    except Exception:
        db.session.rollback()

        current_app.logger.exception(
            "Email log deletion failed "
            "for log_id=%s",
            log_id
        )

        flash(
            "The email log could not be deleted.",
            "danger"
        )

        return redirect(
            url_for(
                "admin.email_logs"
            )
        )

    flash(
        "Email log deleted successfully.",
        "success"
    )

    return redirect(
        request.referrer
        or url_for(
            "admin.email_logs"
        )
    )

@admin_blueprint.route(
    "/email-logs/delete-failed",
    methods=["POST"]
)
@login_required(role="Administrator")
def delete_failed_email_logs():
    try:
        deleted_count = (
            EmailLog.query
            .filter(
                EmailLog.status
                == "Failed"
            )
            .delete(
                synchronize_session=False
            )
        )

        db.session.commit()

    except Exception:
        db.session.rollback()

        current_app.logger.exception(
            "Failed email-log cleanup failed."
        )

        flash(
            "Failed email logs could not be deleted.",
            "danger"
        )

        return redirect(
            url_for(
                "admin.email_logs"
            )
        )

    if deleted_count:
        flash(
            f"{deleted_count} failed email "
            "log(s) deleted successfully.",
            "success"
        )
    else:
        flash(
            "There were no failed email logs to delete.",
            "info"
        )

    return redirect(
        url_for(
            "admin.email_logs"
        )
    )

@admin_blueprint.route(
    "/email-logs/delete-all",
    methods=["POST"]
)
@login_required(role="Administrator")
def delete_all_email_logs():
    confirmation = (
        request.form.get(
            "confirmation"
        )
        or ""
    ).strip()

    if confirmation != "DELETE":
        flash(
            "Type DELETE to confirm clearing all email logs.",
            "warning"
        )

        return redirect(
            url_for(
                "admin.email_logs"
            )
        )

    try:
        deleted_count = (
            EmailLog.query.delete(
                synchronize_session=False
            )
        )

        db.session.commit()

    except Exception:
        db.session.rollback()

        current_app.logger.exception(
            "Complete email-log cleanup failed."
        )

        flash(
            "Email logs could not be cleared.",
            "danger"
        )

        return redirect(
            url_for(
                "admin.email_logs"
            )
        )

    flash(
        f"{deleted_count} email log(s) cleared.",
        "success"
    )

    return redirect(
        url_for(
            "admin.email_logs"
        )
    )
    


@admin_blueprint.route("/test-email", methods=["GET"])
@login_required(role="Administrator")
def test_email():
    from app.services.email_service import send_email

    email_sent = send_email(
        recipient=current_user.email,
        subject="SMTP Service Test",
        email_type="smtp_test",
        text_body=(
            f"Hello {current_user.name},\n\n"
            "The chatbot SMTP email service is working correctly.\n\n"
            "This message was sent from the administrator test route."
        ),
        user_id=current_user.id
    )

    if email_sent:
        return "Email sent successfully.", 200

    return (
        "Email could not be sent. Check the terminal and email_logs table.",
        500
    )