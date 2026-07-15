from app.utils.system_events import (
    log_system_event
)
from flask import Blueprint, current_app, render_template as _render, send_file, redirect, request, url_for, flash, jsonify, abort
from flask_login import current_user
from flask_socketio import join_room
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
from app.agent.forms import (
    ChangeEmailForm,
    TicketForm,
    UpdateTicketForm,
    CommentForm,
    CategoryForm,
    PriorityForm,
    ChangeProfileForm,
    ChangePasswordForm
)
from app.models import User, Ticket, Category, Priority, Status, Comment, Notification, AgentReport, ChatMessage, AgentSolution, KnowledgeArticle, FAQ, CustomerSatisfaction, MaintenanceSetting
from app.utils.generate_digits import random_numbers
from app.utils.authorized_role import login_required
from app.exts import db, csrf
from app.socketio_ext import socketio

from werkzeug.utils import secure_filename
from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from sqlalchemy import desc, or_, func

import datetime
import uuid
import os


agent_blueprint = Blueprint("agent", __name__)
path = os.getcwd()

REPORT_UPLOAD_FOLDER = os.path.join(
    path,
    "app/static/uploads/reports"
)


# ============================================================
# TEMPLATE HELPER
# ============================================================

def get_agent_ticket_or_404(
    ticket_id,
    allow_unassigned=False
):
    query = Ticket.query.filter(
        Ticket.id == ticket_id
    )

    if allow_unassigned:
        query = query.filter(
            or_(
                Ticket.owner_id == current_user.id,
                Ticket.owner_id.is_(None),
                Ticket.author_id == current_user.id
            )
        )

    else:
        query = query.filter(
            or_(
                Ticket.owner_id == current_user.id,
                Ticket.author_id == current_user.id
            )
        )

    return query.first_or_404()

def render_template(*args, **kwargs):
    notifications = (
        Notification.query
        .filter(Notification.receiver_id == current_user.id)
        .filter(Notification.seen == False)
        .order_by(desc(Notification.created_at))
        .all()
    )

    year = datetime.date.today().year

    # ============================================================
    # DEFAULT COUNTS
    # ============================================================

    agent_new_ticket_count = 0
    agent_assigned_ticket_count = 0
    agent_support_desk_total_count = 0

    agent_knowledge_center_total_count = 0

    agent_faq_library_count = 0
    agent_knowledge_base_count = 0
    agent_my_pending_solution_count = 0
    agent_suggested_article_count = 0

    agent_reports_total_count = 0
    agent_incident_report_count = 0
    agent_issue_report_count = 0
    agent_internal_report_count = 0

    agent_performance_total_count = 0

    # ============================================================
    # AGENT COUNTS
    # ============================================================

    if current_user.is_authenticated and current_user.role == "Agent":

        closed_id = get_closed_status_id()
        solved_id = get_solved_status_id()

        inactive_status_ids = [
            status_id
            for status_id in [
                closed_id,
                solved_id
            ]
            if status_id is not None
        ]
        # --------------------------------------------------------
        # SUPPORT DESK
        # --------------------------------------------------------

        new_ticket_query = (
            Ticket.query
            .filter(Ticket.owner_id.is_(None))
        )

        if inactive_status_ids:
            new_ticket_query = (
                new_ticket_query
                .filter(
                    ~Ticket.status_id.in_(
                        inactive_status_ids
                    )
                )
            )

        agent_new_ticket_count = (
            new_ticket_query.count()
        )

        assigned_ticket_query = (
            Ticket.query
            .filter(
                Ticket.owner_id
                == current_user.id
            )
        )

        if inactive_status_ids:
            assigned_ticket_query = (
                assigned_ticket_query
                .filter(
                    ~Ticket.status_id.in_(
                        inactive_status_ids
                    )
                )
            )

        agent_assigned_ticket_count = (
            assigned_ticket_query.count()
        )

        agent_support_desk_total_count = (
            agent_new_ticket_count
            + agent_assigned_ticket_count
        )

        # --------------------------------------------------------
        # KNOWLEDGE CENTER
        # --------------------------------------------------------

        agent_faq_library_count = 0

        agent_knowledge_base_count = 0

        agent_my_pending_solution_count = (
            AgentSolution.query
            .filter(
                AgentSolution.submitted_by_id == current_user.id
            )
            .filter(
                AgentSolution.status == "Pending"
            )
            .count()
        )

        agent_suggested_article_count = 0

        agent_knowledge_center_total_count = (
            agent_my_pending_solution_count
        )

        # --------------------------------------------------------
        # REPORTS
        # --------------------------------------------------------

        agent_incident_report_count = (
            AgentReport.query
            .filter(
                AgentReport.reported_by_id == current_user.id
            )
            .filter(
                AgentReport.report_type == "Incident"
            )
            .filter(
                AgentReport.status != "Closed"
            )
            .count()
        )

        agent_issue_report_count = (
            AgentReport.query
            .filter(
                AgentReport.reported_by_id == current_user.id
            )
            .filter(
                AgentReport.report_type == "Issue"
            )
            .filter(
                AgentReport.status != "Closed"
            )
            .count()
        )

        agent_internal_report_count = (
            AgentReport.query
            .filter(
                AgentReport.reported_by_id == current_user.id
            )
            .filter(
                AgentReport.report_type == "Internal"
            )
            .filter(
                AgentReport.status != "Closed"
            )
            .count()
        )

        agent_reports_total_count = (
            agent_incident_report_count
            + agent_issue_report_count
            + agent_internal_report_count
        )

        # --------------------------------------------------------
        # PERFORMANCE
        # --------------------------------------------------------

        agent_performance_total_count = (
            CustomerSatisfaction.query
            .join(
                Ticket,
                CustomerSatisfaction.ticket_id == Ticket.id
            )
            .filter(
                Ticket.owner_id == current_user.id
            )
            .filter(
                CustomerSatisfaction.rating <= 2
            )
            .count()
        )

    # ============================================================
    # TEMPLATE VARIABLES
    # ============================================================

    kwargs.setdefault("notifications", notifications)
    kwargs.setdefault("year", year)

    kwargs.setdefault(
        "agent_new_ticket_count",
        agent_new_ticket_count
    )

    kwargs.setdefault(
        "agent_assigned_ticket_count",
        agent_assigned_ticket_count
    )

    kwargs.setdefault(
        "agent_support_desk_total_count",
        agent_support_desk_total_count
    )

    kwargs.setdefault(
        "agent_knowledge_center_total_count",
        agent_knowledge_center_total_count
    )

    kwargs.setdefault(
        "agent_faq_library_count",
        agent_faq_library_count
    )

    kwargs.setdefault(
        "agent_knowledge_base_count",
        agent_knowledge_base_count
    )

    kwargs.setdefault(
        "agent_my_pending_solution_count",
        agent_my_pending_solution_count
    )

    kwargs.setdefault(
        "agent_suggested_article_count",
        agent_suggested_article_count
    )

    kwargs.setdefault(
        "agent_reports_total_count",
        agent_reports_total_count
    )

    kwargs.setdefault(
        "agent_incident_report_count",
        agent_incident_report_count
    )

    kwargs.setdefault(
        "agent_issue_report_count",
        agent_issue_report_count
    )

    kwargs.setdefault(
        "agent_internal_report_count",
        agent_internal_report_count
    )

    kwargs.setdefault(
        "agent_performance_total_count",
        agent_performance_total_count
    )

    return _render(*args, **kwargs)


# ============================================================
# SMALL HELPERS
# ============================================================

def get_status_id(status_name, fallback=None):
    if not status_name:
        return fallback

    status = (
        Status.query
        .filter(
            func.lower(Status.status)
            == status_name.strip().lower()
        )
        .first()
    )

    return status.id if status else fallback


def get_open_status_id():
    return get_status_id("Open", 1)


def get_solved_status_id():
    return get_status_id("Solved", 2)


def get_pending_status_id():
    return get_status_id("Pending", 3)


def get_closed_status_id():
    return get_status_id("Closed", 4)


def get_escalated_status_id():
    return get_status_id("Escalated")


def get_waiting_customer_status_id():
    return get_status_id("Waiting for Customer")

def safe_send_email(email_function, *args, **kwargs):
    try:
        return bool(
            email_function(
                *args,
                **kwargs
            )
        )

    except Exception:
        current_app.logger.exception(
            "Email function failed: %s",
            getattr(
                email_function,
                "__name__",
                "unknown_email_function"
            )
        )

        return False


def safe_commit(error_message="Database operation failed."):
    try:
        db.session.commit()
        return True

    except Exception:
        db.session.rollback()

        current_app.logger.exception(
            error_message
        )

        return False

def auto_close_waiting_customer_tickets():
    waiting_id = (
        get_waiting_customer_status_id()
    )

    closed_id = (
        get_closed_status_id()
    )

    if not waiting_id or not closed_id:
        return

    now = datetime.datetime.utcnow()

    tickets = (
        Ticket.query
        .filter(
            Ticket.status_id == waiting_id
        )
        .all()
    )

    changed = False

    for ticket in tickets:
        waiting_since = (
            ticket.waiting_customer_since
        )

        if not waiting_since:
            waiting_since = (
                ticket.updated_at
                or ticket.created_at
                or now
            )

            ticket.waiting_customer_since = (
                waiting_since
            )

            changed = True

        waiting_since = (
            waiting_since.replace(
                tzinfo=None
            )
        )

        waiting_hours = (
            now - waiting_since
        ).total_seconds() / 3600

        if (
            waiting_hours >= 24
            and not ticket.inactive_reminder_sent
        ):
            notify_user(
                message=(
                    "Reminder: your support ticket is waiting "
                    "for your reply and may close after 48 hours "
                    "of no response."
                ),
                receiver_id=ticket.author_id,
                sender_id=(
                    ticket.owner_id
                    or current_user.id
                ),
                ticket_id=ticket.id
            )

            reminder_comment = Comment(
                comment=(
                    "Reminder sent to customer: ticket is "
                    "waiting for customer response."
                ),
                author_id=(
                    ticket.owner_id
                    or current_user.id
                ),
                ticket_id=ticket.id
            )

            db.session.add(
                reminder_comment
            )

            ticket.inactive_reminder_sent = True
            changed = True

        if waiting_hours >= 48:
            ticket.status_id = closed_id
            ticket.updated_at = now

            close_comment = Comment(
                comment=(
                    "Ticket automatically closed because the "
                    "customer did not respond within 48 hours."
                ),
                author_id=(
                    ticket.owner_id
                    or current_user.id
                ),
                ticket_id=ticket.id
            )

            db.session.add(
                close_comment
            )

            changed = True

            if ticket.author:
                safe_send_email(
                    send_ticket_closed_email,
                    ticket.author,
                    ticket
                )

                safe_send_email(
                    send_satisfaction_email,
                    ticket.author,
                    ticket
                )

            socketio.emit(
                "customer_ticket_closed",
                {
                    "ticket_id": ticket.id,
                    "message": (
                        "Ticket automatically closed."
                    )
                },
                room=f"user_{ticket.author_id}"
            )

            emit_ticket_event(
                ticket,
                "ticket_closed",
                close_comment.comment
            )

    if changed:
        safe_commit(
            "Automatic ticket closure failed."
        )
    

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

        # The unassigned waiting period starts from updated_at.
        # When a ticket becomes unassigned, updated_at is reset.
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
        # 15-MINUTE CUSTOMER NOTIFICATION
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
        safe_commit(
            "Unassigned ticket notification update failed."
        )


def emit_global_refresh(reason="updated", ticket=None):
    payload = {
        "reason": reason
    }

    if ticket:
        payload.update({
            "ticket_id": ticket.id,
            "ticket_number": ticket.number,
            "status": ticket.status.status if ticket.status else "",
            "status_id": ticket.status_id,
            "owner_id": ticket.owner_id,
            "author_id": ticket.author_id
        })

    socketio.emit("global_ticket_updated", payload)
    socketio.emit("sidebar_counts_updated", payload)
    socketio.emit("notification_updated", payload)
    socketio.emit("analytics_updated", payload)


def notify_user(
    message,
    receiver_id,
    sender_id=None,
    ticket_id=None
):
    if not receiver_id:
        return None

    try:
        return Notification.send_notification(
            message=message,
            receiver_id=receiver_id,
            sender_id=sender_id,
            ticket_id=ticket_id,
            notification_type="ticket",
            seen=False
        )

    except Exception:
        current_app.logger.exception(
            "Notification failed for receiver_id=%s "
            "ticket_id=%s",
            receiver_id,
            ticket_id
        )

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





# ============================================================
# AGENT REPORT ROUTES
# ============================================================





@agent_blueprint.route("/faq-library", methods=["GET"])
@login_required(role="Agent")
def faq_library():
    from app.models import FAQ

    faqs = (
        FAQ.query
        .filter(FAQ.is_active == True)
        .order_by(desc(FAQ.created_at))
        .all()
    )

    categories = Category.query.order_by(Category.category.asc()).all()

    return render_template(
        "agent/faq_library.html",
        faqs=faqs,
        categories=categories
    )


def emit_agent_report_created(report):
    admins = User.query.filter_by(role="Administrator").all()

    for admin in admins:
        Notification.send_notification(
            message=f"new {report.report_type.lower()} report submitted",
            receiver_id=admin.id,
            sender_id=current_user.id,
            ticket_id=None,
            agent_report_id=report.id,
            notification_type="agent_report",
            title=report.title,
            url=url_for("admin.agent_reports"),
            seen=False
        )

    payload = {
        "report_id": report.id,
        "report_type": report.report_type,
        "title": report.title,
        "severity": report.severity,
        "category": report.category,
        "reported_by": report.reported_by.name if report.reported_by else "Agent",
        "message": f"New {report.report_type} report submitted",
        "url": url_for("admin.agent_reports")
    }

    socketio.emit("agent_report_created_global", payload)
    socketio.emit("agent_report_updated", payload)
    socketio.emit("notification_updated", payload)
    socketio.emit("sidebar_counts_updated", payload)
    socketio.emit("analytics_updated", payload)


def emit_comment(
    ticket,
    comment,
    is_attachment=False
):
    user = comment.user

    payload = {
        "ticket_id": ticket.id,
        "ticket_number": ticket.number,
        "comment_id": comment.id,
        "message": comment.comment or "",
        "sender_name": (
            user.name
            if user
            else "System"
        ),
        "sender_role": (
            user.role
            if user
            else "System"
        ),
        "author_id": comment.author_id,
        "is_attachment": is_attachment,
        "created_at": (
            comment.created_at.strftime(
                "%d %b %Y, %H:%M %p"
            )
            if comment.created_at
            else ""
        )
    }

    socketio.emit(
        "new_comment",
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


def serialize_comment(comment):
    user = comment.user

    return {
        "id": comment.id,
        "message": comment.comment or "",
        "author": (
            user.name
            if user
            else "System"
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


# ============================================================
# AGENT REPORT ROUTES
# ============================================================

@agent_blueprint.route("/incident-log", methods=["GET", "POST"])
@login_required(role="Agent")
def incident_log():
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        category = (request.form.get("category") or "").strip()
        severity = (request.form.get("severity") or "").strip()
        description = (request.form.get("description") or "").strip()

        if not title or not category or not severity or not description:
            flash("Please complete all required fields.", "warning")
            return redirect(url_for("agent.incident_log"))

        attachment = None
        original_file = None

        file = request.files.get("attachment")

        if file and file.filename:
            os.makedirs(REPORT_UPLOAD_FOLDER, exist_ok=True)

            original_file = secure_filename(file.filename)
            filename, ext = os.path.splitext(original_file)
            attachment = secure_filename(uuid.uuid4().hex + ext.lower())

            file.save(os.path.join(REPORT_UPLOAD_FOLDER, attachment))

        report = AgentReport(
            report_type="Incident",
            title=title,
            category=category,
            severity=severity,
            description=description,
            reported_by_id=current_user.id,
            status="Open",
            orig_file=original_file,
            file_link=attachment
        )

        db.session.add(report)
        db.session.commit()

        emit_agent_report_created(report)

        flash("Incident report submitted to admin.", "primary")
        return redirect(url_for("agent.incident_log"))

    reports = (
        AgentReport.query
        .filter_by(reported_by_id=current_user.id, report_type="Incident")
        .order_by(desc(AgentReport.created_at))
        .all()
    )

    return render_template(
        "agent/report_form.html",
        page_title="Incident Log",
        page_text="Report serious support incidents such as customer abuse, security concerns, or urgent failures.",
        report_type="Incident",
        categories=[
            "Customer Abuse",
            "Security Concern",
            "Urgent System Failure",
            "Privacy Concern",
            "Safety Concern",
            "Other"
        ],
        reports=reports
    )


@agent_blueprint.route("/issue-log", methods=["GET", "POST"])
@login_required(role="Agent")
def issue_log():
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        category = (request.form.get("category") or "").strip()
        severity = (request.form.get("severity") or "").strip()
        description = (request.form.get("description") or "").strip()

        if not title or not category or not severity or not description:
            flash("Please complete all required fields.", "warning")
            return redirect(url_for("agent.issue_log"))

        attachment = None
        original_file = None

        file = request.files.get("attachment")

        if file and file.filename:
            os.makedirs(REPORT_UPLOAD_FOLDER, exist_ok=True)

            original_file = secure_filename(file.filename)
            filename, ext = os.path.splitext(original_file)
            attachment = secure_filename(uuid.uuid4().hex + ext.lower())

            file.save(os.path.join(REPORT_UPLOAD_FOLDER, attachment))

        report = AgentReport(
            report_type="Issue",
            title=title,
            category=category,
            severity=severity,
            description=description,
            reported_by_id=current_user.id,
            status="Open",
            orig_file=original_file,
            file_link=attachment
        )

        db.session.add(report)
        db.session.commit()

        emit_agent_report_created(report)

        flash("Issue report submitted to admin.", "primary")
        return redirect(url_for("agent.issue_log"))

    reports = (
        AgentReport.query
        .filter_by(reported_by_id=current_user.id, report_type="Issue")
        .order_by(desc(AgentReport.created_at))
        .all()
    )

    return render_template(
        "agent/report_form.html",
        page_title="Issue Log",
        page_text="Report platform issues such as bugs, upload problems, login errors, or chatbot problems.",
        report_type="Issue",
        categories=[
            "System Bug",
            "Attachment Issue",
            "Login Issue",
            "Chatbot Issue",
            "Notification Issue",
            "Database Issue",
            "Performance Issue",
            "Other"
        ],
        reports=reports
    )

@csrf.exempt
@agent_blueprint.route("/api/notifications/mark-navbar-read", methods=["POST"])
@login_required(role="Agent")
def mark_navbar_notifications_read():
    Notification.query.filter(
        Notification.receiver_id == current_user.id,
        Notification.seen == False
    ).update({"seen": True})

    db.session.commit()

    socketio.emit("notification_read", {"receiver_id": current_user.id}, room=f"user_{current_user.id}")
    socketio.emit("notification_updated", {"receiver_id": current_user.id})
    socketio.emit("sidebar_counts_updated", {"receiver_id": current_user.id})

    return jsonify({"ok": True}), 200

@agent_blueprint.route("/internal-reports", methods=["GET", "POST"])
@login_required(role="Agent")
def internal_reports():
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        category = (request.form.get("category") or "").strip()
        severity = (request.form.get("severity") or "").strip()
        description = (request.form.get("description") or "").strip()

        if not title or not category or not severity or not description:
            flash("Please complete all required fields.", "warning")
            return redirect(url_for("agent.internal_reports"))

        attachment = None
        original_file = None

        file = request.files.get("attachment")

        if file and file.filename:
            os.makedirs(REPORT_UPLOAD_FOLDER, exist_ok=True)

            original_file = secure_filename(file.filename)
            filename, ext = os.path.splitext(original_file)
            attachment = secure_filename(uuid.uuid4().hex + ext.lower())

            file.save(os.path.join(REPORT_UPLOAD_FOLDER, attachment))

        report = AgentReport(
            report_type="Internal",
            title=title,
            category=category,
            severity=severity,
            description=description,
            reported_by_id=current_user.id,
            status="Open",
            orig_file=original_file,
            file_link=attachment
        )

        db.session.add(report)
        db.session.commit()

        emit_agent_report_created(report)

        flash("Internal report submitted to admin.", "primary")
        return redirect(url_for("agent.internal_reports"))

    reports = (
        AgentReport.query
        .filter_by(reported_by_id=current_user.id, report_type="Internal")
        .order_by(desc(AgentReport.created_at))
        .all()
    )

    return render_template(
        "agent/report_form.html",
        page_title="Internal Reports",
        page_text="Submit shift notes, repeated customer issues, improvement ideas, or internal support observations.",
        report_type="Internal",
        categories=[
            "Shift Note",
            "Repeated Customer Issue",
            "Process Improvement",
            "Training Need",
            "Policy Question",
            "Other"
        ],
        reports=reports
    )



# ============================================================
# DASHBOARD / LIST ROUTES
# ============================================================

@agent_blueprint.route(
    "/dashboard",
    methods=["GET"]
)
@login_required(role="Agent")
def dashboard():
    auto_close_waiting_customer_tickets()
    notify_unassigned_tickets()

    user_id = current_user.id

    open_status_id = get_open_status_id()
    pending_status_id = get_pending_status_id()
    solved_status_id = get_solved_status_id()
    closed_status_id = get_closed_status_id()
    escalated_status_id = get_escalated_status_id()

    inactive_status_ids = [
        status_id
        for status_id in [
            closed_status_id,
            solved_status_id
        ]
        if status_id is not None
    ]

    # ========================================================
    # STATUS-SPECIFIC TICKETS
    # ========================================================

    open_tickets = (
        Ticket.query
        .filter(
            Ticket.owner_id == user_id,
            Ticket.status_id == open_status_id
        )
        .order_by(
            desc(Ticket.updated_at),
            desc(Ticket.created_at)
        )
        .all()
    )

    pending = (
        Ticket.query
        .filter(
            Ticket.owner_id == user_id,
            Ticket.status_id == pending_status_id
        )
        .order_by(
            desc(Ticket.updated_at),
            desc(Ticket.created_at)
        )
        .all()
    )

    solved = (
        Ticket.query
        .filter(
            Ticket.owner_id == user_id,
            Ticket.status_id == solved_status_id
        )
        .order_by(
            desc(Ticket.updated_at),
            desc(Ticket.created_at)
        )
        .all()
    )

    closed = (
        Ticket.query
        .filter(
            Ticket.owner_id == user_id,
            Ticket.status_id == closed_status_id
        )
        .order_by(
            desc(Ticket.updated_at),
            desc(Ticket.created_at)
        )
        .all()
    )

    # ========================================================
    # ACTIVE ASSIGNED TICKETS
    # ========================================================

    assigned_query = (
        Ticket.query
        .filter(
            Ticket.owner_id == user_id
        )
    )

    if inactive_status_ids:
        assigned_query = (
            assigned_query
            .filter(
                ~Ticket.status_id.in_(
                    inactive_status_ids
                )
            )
        )

    assigned_tickets = (
        assigned_query
        .order_by(
            desc(Ticket.updated_at),
            desc(Ticket.created_at)
        )
        .limit(10)
        .all()
    )

    # Use a fresh query for active chats.
    active_chat_query = (
        Ticket.query
        .filter(
            Ticket.owner_id == user_id
        )
    )

    if inactive_status_ids:
        active_chat_query = (
            active_chat_query
            .filter(
                ~Ticket.status_id.in_(
                    inactive_status_ids
                )
            )
        )

    active_chats = (
        active_chat_query
        .order_by(
            desc(Ticket.updated_at),
            desc(Ticket.created_at)
        )
        .limit(5)
        .all()
    )

    # ========================================================
    # UNASSIGNED ACTIVE TICKETS
    # ========================================================

    unassigned_query = (
        Ticket.query
        .filter(
            Ticket.owner_id.is_(None)
        )
    )

    if inactive_status_ids:
        unassigned_query = (
            unassigned_query
            .filter(
                ~Ticket.status_id.in_(
                    inactive_status_ids
                )
            )
        )

    unassigned_count = (
        unassigned_query.count()
    )

    # ========================================================
    # TOTAL ASSIGNED
    # Includes historical closed and solved tickets.
    # ========================================================

    total_assigned = (
        Ticket.query
        .filter(
            Ticket.owner_id == user_id
        )
        .count()
    )

    # ========================================================
    # ESCALATED
    # ========================================================

    escalated_count = 0

    if escalated_status_id:
        escalated_count = (
            Ticket.query
            .filter(
                Ticket.owner_id == user_id,
                Ticket.status_id
                == escalated_status_id
            )
            .count()
        )

    return render_template(
        "agent/dashboard.html",
        open=open_tickets,
        pending=pending,
        solved=solved,
        closed=closed,
        assigned_tickets=assigned_tickets,
        active_chats=active_chats,
        unassigned_count=unassigned_count,
        total_assigned=total_assigned,
        escalated_count=escalated_count
    )



@agent_blueprint.route(
    "/new-tickets",
    methods=["GET"]
)
@login_required(role="Agent")
def new_tickets():
    auto_close_waiting_customer_tickets()
    notify_unassigned_tickets()

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

    tickets = (
        query
        .order_by(
            desc(Ticket.created_at)
        )
        .all()
    )

    form = TicketForm()

    return render_template(
        "agent/new_tickets.html",
        form=form,
        tickets=tickets
    )



# ============================================================
# TICKET ACTIONS
# ============================================================

@agent_blueprint.route(
    "/ticket/claim/<int:id>",
    methods=["POST"]
)
@login_required(role="Agent")
def claim_ticket(id):
    ticket = Ticket.query.get_or_404(id)

    if (
        ticket.status_id
        == get_closed_status_id()
    ):
        flash(
            "Closed tickets cannot be claimed.",
            "warning"
        )

        return redirect(
            url_for("agent.new_tickets")
        )

    if (
        ticket.status_id
        == get_solved_status_id()
    ):
        flash(
            "Solved tickets cannot be claimed.",
            "warning"
        )

        return redirect(
            url_for("agent.new_tickets")
        )

    if ticket.owner_id:
        flash(
            "This ticket has already been claimed.",
            "warning"
        )

        return redirect(
            url_for("agent.new_tickets")
        )

    ticket.owner_id = current_user.id

    if (
        ticket.status_id
        == get_open_status_id()
    ):
        ticket.status_id = (
            get_pending_status_id()
        )

    ticket.updated_at = (
        datetime.datetime.utcnow()
    )

    ticket.unassigned_15min_sent = False
    ticket.unassigned_30min_sent = False

    comment = Comment(
        comment=(
            f"✅ Support agent "
            f"{current_user.name} joined the chat."
        ),
        author_id=current_user.id,
        ticket_id=ticket.id
    )

    db.session.add(comment)

    if not safe_commit(
        "Ticket claim failed."
    ):
        flash(
            "The ticket could not be claimed.",
            "danger"
        )

        return redirect(
            url_for("agent.new_tickets")
        )

    if ticket.author:
        safe_send_email(
            send_ticket_assigned_email,
            ticket.author,
            ticket,
            current_user
        )

    emit_comment(
        ticket,
        comment
    )

    emit_ticket_event(
        ticket,
        "agent_joined",
        comment.comment
    )

    emit_global_refresh(
        "ticket_claimed",
        ticket
    )

    flash(
        "Ticket claimed successfully.",
        "success"
    )

    return redirect(
        url_for(
            "agent.view_ticket",
            id=ticket.id
        )
    )

@agent_blueprint.route(
    "/create-ticket",
    methods=["GET", "POST"]
)
@login_required(role="Agent")
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
        # SEND TICKET-CREATED EMAIL
        # ----------------------------------------------------

        email_sent = send_ticket_created_email(
            current_user,
            ticket
        )

        if not email_sent:
            current_app.logger.error(
                "Agent ticket-created email failed "
                "for ticket_id=%s agent_id=%s",
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
                f"by agent {current_user.email}."
            ),
            user_id=current_user.id,
            ticket_id=ticket.id
        )

        # ----------------------------------------------------
        # REAL-TIME UPDATE
        # ----------------------------------------------------

        payload = {
            "ticket_id": ticket.id,
            "ticket_number": ticket.number,
            "message": "Ticket created by agent."
        }

        socketio.emit(
            "ticket_created",
            payload
        )

        emit_global_refresh(
            "ticket_created",
            ticket
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
            url_for("agent.new_tickets")
        )

    return render_template(
        "agent/new_tickets.html",
        form=form,
        tickets=[]
    )
@agent_blueprint.route(
    "/view-ticket/<int:id>",
    methods=["GET", "POST"]
)
@login_required(role="Agent")
def view_ticket(id):
    ticket = get_agent_ticket_or_404(
        id,
        allow_unassigned=True
    )

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
    # LOAD CURRENT VALUES INTO FORM
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
                    "agent.view_ticket",
                    id=ticket.id
                )
            )

        old_owner_id = ticket.owner_id
        old_status_id = ticket.status_id
        old_priority_id = ticket.priority_id

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
                    "agent.view_ticket",
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
                        "agent.view_ticket",
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
                    "agent.view_ticket",
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
                    "agent.view_ticket",
                    id=ticket.id
                )
            )

        assignment_comment = None
        close_comment = None

        now = datetime.datetime.utcnow()

        # ====================================================
        # OWNER CHANGE
        # ====================================================

        if old_owner_id != new_owner_id:
            ticket.owner_id = new_owner_id

            if new_owner:
                assignment_message = (
                    f"🔄 Ticket assigned to "
                    f"{new_owner.name} by "
                    f"{current_user.name}."
                )

                # Ticket is no longer unassigned.
                ticket.unassigned_15min_sent = False
                ticket.unassigned_30min_sent = False

            else:
                assignment_message = (
                    f"Ticket became unassigned by "
                    f"{current_user.name}."
                )

                # Start the unassigned timer now.
                ticket.updated_at = now

                # Allow the 15-minute and 30-minute alerts
                # to run for this new unassigned period.
                ticket.unassigned_15min_sent = False
                ticket.unassigned_30min_sent = False

            assignment_comment = Comment(
                comment=assignment_message,
                author_id=current_user.id,
                ticket_id=ticket.id
            )

            db.session.add(
                assignment_comment
            )

        # ====================================================
        # PRIORITY UPDATE
        # ====================================================

        ticket.priority_id = (
            new_priority_id
        )

        # ====================================================
        # STATUS UPDATE
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
            close_comment = Comment(
                comment=(
                    f"🔒 Ticket closed by "
                    f"{current_user.name}."
                ),
                author_id=current_user.id,
                ticket_id=ticket.id
            )

            db.session.add(
                close_comment
            )

        # Only overwrite updated_at here if the ticket did not
        # just become unassigned. In both cases the value is now,
        # but this condition makes the timer purpose clear.
        if not (
            old_owner_id != new_owner_id
            and new_owner_id is None
        ):
            ticket.updated_at = now

        # ====================================================
        # DATABASE COMMIT
        # ====================================================

        if not safe_commit(
            "Agent ticket update failed "
            f"for ticket_id={ticket.id}."
        ):
            flash(
                "The ticket could not be updated.",
                "danger"
            )

            return redirect(
                url_for(
                    "agent.view_ticket",
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
            if old_owner_id:
                safe_send_email(
                    send_ticket_reassigned_email,
                    ticket.author,
                    ticket
                )

            else:
                safe_send_email(
                    send_ticket_assigned_email,
                    ticket.author,
                    ticket,
                    new_owner
                )

        # ====================================================
        # CLOSED EMAILS AND CUSTOMER EVENT
        # ====================================================

        if (
            status_changed_to_closed
            and ticket.author
        ):
            safe_send_email(
                send_ticket_closed_email,
                ticket.author,
                ticket
            )

            safe_send_email(
                send_satisfaction_email,
                ticket.author,
                ticket
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
        # REAL-TIME EVENTS
        # ====================================================

        if assignment_comment:
            emit_comment(
                ticket,
                assignment_comment
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
                close_comment
            )

            emit_ticket_event(
                ticket,
                "ticket_closed",
                close_comment.comment
            )

        emit_global_refresh(
            "ticket_updated",
            ticket
        )

        flash(
            "Ticket updated successfully.",
            "success"
        )

        return redirect(
            url_for(
                "agent.view_ticket",
                id=ticket.id
            )
        )

    return render_template(
        "agent/view_ticket.html",
        ticket=ticket,
        comments=comments,
        form=form,
        comment_form=comment_form,
        is_closed=is_closed
    )

@agent_blueprint.route(
    "/ticket/reopen/<int:id>",
    methods=["POST"]
)
@login_required(role="Agent")
def reopen_ticket(id):
    ticket = get_agent_ticket_or_404(id)

    closed_status_id = (
        get_closed_status_id()
    )

    if (
        ticket.status_id
        != closed_status_id
    ):
        flash(
            "Only closed tickets can be reopened.",
            "warning"
        )

        return redirect(
            url_for(
                "agent.view_ticket",
                id=ticket.id
            )
        )

    ticket.status_id = (
        get_pending_status_id()
    )

    ticket.waiting_customer_since = None
    ticket.inactive_reminder_sent = False
    ticket.updated_at = (
        datetime.datetime.utcnow()
    )

    comment = Comment(
        comment=(
            f"🔓 Ticket reopened by "
            f"{current_user.name}."
        ),
        author_id=current_user.id,
        ticket_id=ticket.id
    )

    db.session.add(comment)

    if not safe_commit(
        "Ticket reopening failed."
    ):
        flash(
            "The ticket could not be reopened.",
            "danger"
        )

        return redirect(
            url_for(
                "agent.view_ticket",
                id=ticket.id
            )
        )

    if ticket.author:
        safe_send_email(
            send_ticket_reopened_email,
            ticket.author,
            ticket
        )

        socketio.emit(
            "customer_ticket_reopened",
            {
                "ticket_id": ticket.id,
                "message": (
                    "Ticket reopened."
                )
            },
            room=f"user_{ticket.author_id}"
        )

    emit_comment(
        ticket,
        comment
    )

    emit_ticket_event(
        ticket,
        "ticket_reopened",
        comment.comment
    )

    emit_global_refresh(
        "ticket_reopened",
        ticket
    )

    flash(
        "Ticket reopened successfully.",
        "success"
    )

    return redirect(
        url_for(
            "agent.view_ticket",
            id=ticket.id
        )
    )

@agent_blueprint.route(
    "/ticket/escalate/<int:id>",
    methods=["POST"]
)
@login_required(role="Agent")
def escalate_ticket(id):
    ticket = get_agent_ticket_or_404(id)

    if (
        ticket.status_id
        == get_closed_status_id()
    ):
        flash(
            "Closed tickets cannot be escalated. "
            "Reopen the ticket first.",
            "warning"
        )

        return redirect(
            url_for(
                "agent.view_ticket",
                id=ticket.id
            )
        )

    escalated_status_id = (
        get_escalated_status_id()
    )

    if not escalated_status_id:
        flash(
            "The Escalated status does not exist.",
            "danger"
        )

        return redirect(
            url_for(
                "agent.view_ticket",
                id=ticket.id
            )
        )

    if (
        ticket.status_id
        == escalated_status_id
    ):
        flash(
            "This ticket is already escalated.",
            "warning"
        )

        return redirect(
            url_for(
                "agent.view_ticket",
                id=ticket.id
            )
        )

    ticket.status_id = escalated_status_id
    ticket.owner_id = None
    ticket.updated_at = (
        datetime.datetime.utcnow()
    )

    escalate_message = (
        f"🚨 Ticket escalated to admin by "
        f"support agent {current_user.name}."
    )

    comment = Comment(
        comment=escalate_message,
        author_id=current_user.id,
        ticket_id=ticket.id
    )

    db.session.add(comment)

    if not safe_commit(
        "Ticket escalation failed."
    ):
        flash(
            "The ticket could not be escalated.",
            "danger"
        )

        return redirect(
            url_for(
                "agent.view_ticket",
                id=ticket.id
            )
        )

    if ticket.author:
        safe_send_email(
            send_ticket_escalated_email,
            ticket.author,
            ticket,
            current_user
        )

    notify_customer(
        ticket,
        "Your ticket was escalated to an administrator."
    )

    notify_admins(
        ticket,
        f"Ticket #{ticket.number} was escalated."
    )

    emit_comment(
        ticket,
        comment
    )

    emit_ticket_event(
        ticket,
        "ticket_escalated",
        escalate_message
    )

    emit_global_refresh(
        "ticket_escalated",
        ticket
    )

    flash(
        "Ticket escalated successfully.",
        "success"
    )

    return redirect(
        url_for(
            "agent.view_ticket",
            id=ticket.id
        )
    )

@agent_blueprint.route(
    "/comment-ticket/<int:id>",
    methods=["POST"]
)
@login_required(role="Agent")
def comment_ticket(id):
    ticket = get_agent_ticket_or_404(id)

    if (
        ticket.status_id
        == get_closed_status_id()
    ):
        return jsonify(
            success=False,
            message=(
                "This ticket is closed. "
                "Reopen it before replying."
            )
        ), 400

    form = CommentForm()

    if not form.validate_on_submit():
        return jsonify(
            success=False,
            message="Invalid message submission.",
            errors=form.errors
        ), 400

    message = (
        form.comment.data or ""
    ).strip()

    if not message:
        return jsonify(
            success=False,
            message="Message cannot be empty."
        ), 400

    comment = Comment(
        comment=message,
        author_id=current_user.id,
        ticket_id=ticket.id
    )

    db.session.add(comment)

    if (
        ticket.status_id
        == get_waiting_customer_status_id()
    ):
        ticket.status_id = (
            get_pending_status_id()
        )

        ticket.waiting_customer_since = None
        ticket.inactive_reminder_sent = False

    ticket.updated_at = (
        datetime.datetime.utcnow()
    )

    if not safe_commit(
        "Agent reply could not be saved."
    ):
        return jsonify(
            success=False,
            message="Message could not be saved."
        ), 500

    email_sent = False

    if ticket.author:
        email_sent = safe_send_email(
            send_ticket_reply_email,
            ticket.author,
            ticket,
            message
        )

    emit_comment(
        ticket,
        comment
    )

    emit_global_refresh(
        "ticket_message",
        ticket
    )

    return jsonify(
        success=True,
        email_sent=email_sent,
        comment=serialize_comment(
            comment
        )
    ), 200

@agent_blueprint.route(
    "/ticket/delete/<int:uid>/<int:tid>",
    methods=["POST"]
)
@login_required(role="Agent")
def delete_ticket(uid, tid):
    ticket = get_agent_ticket_or_404(tid)

    ticket_id = ticket.id
    ticket_number = ticket.number
    ticket_subject = (
        ticket.subject or "No subject"
    )

    customer = ticket.author
    customer_id = ticket.author_id

    email_sent = False

    if customer and customer.email:
        email_sent = safe_send_email(
            send_ticket_deleted_email,
            customer,
            ticket_number=str(
                ticket_number
            ),
            ticket_subject=(
                ticket_subject
            ),
            deleted_by=(
                f"support agent "
                f"{current_user.name}"
            ),
            deleted_ticket_id=(
                ticket.id
            )
        )

    if ticket.file_link and customer_id:
        folder_id = os.path.join(
            path,
            "app",
            "static",
            "uploads",
            "attachments",
            str(customer_id)
        )

        file_path = os.path.join(
            folder_id,
            secure_filename(
                ticket.file_link
            )
        )

        if os.path.isfile(file_path):
            try:
                os.remove(file_path)

            except OSError:
                current_app.logger.exception(
                    "Ticket attachment deletion "
                    "failed for ticket_id=%s",
                    ticket.id
                )

    try:
        db.session.delete(ticket)
        db.session.commit()

    except Exception:
        db.session.rollback()

        current_app.logger.exception(
            "Ticket deletion failed for "
            "ticket_id=%s",
            ticket_id
        )

        flash(
            "The ticket could not be deleted.",
            "danger"
        )

        return redirect(
            url_for(
                "agent.view_ticket",
                id=ticket_id
            )
        )

    log_system_event(
        event_type="Ticket Deleted",
        severity="Warning",
        message=(
            f"Ticket #{ticket_number} was deleted "
            f"by agent {current_user.email}."
        ),
        user_id=current_user.id,
        ticket_id=None
    )

    payload = {
        "ticket_id": ticket_id,
        "ticket_number": ticket_number,
        "message": (
            "Ticket deleted by agent."
        )
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
            "Ticket deleted and the customer "
            "was notified.",
            "success"
        )
    else:
        flash(
            "Ticket deleted. The customer email "
            "could not be sent.",
            "warning"
        )

    return redirect(
        url_for("agent.my_tickets")
    )

@agent_blueprint.route(
    "/download/attachment/<int:id>/<filename>",
    methods=["GET"]
)
@login_required(role="Agent")
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
            Ticket.file_link
            == safe_filename
        )
        .filter(
            or_(
                Ticket.owner_id
                == current_user.id,
                Ticket.author_id
                == current_user.id
            )
        )
        .first_or_404()
    )

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
        safe_filename
    )

    if not os.path.isfile(file_path):
        abort(404)

    return send_from_directory(
        folder_id,
        safe_filename,
        as_attachment=True,
        download_name=(
            ticket.orig_file
            or safe_filename
        )
    )


# ============================================================
# CATEGORY / PRIORITY / STATUS
# ============================================================

@agent_blueprint.route("/categories", methods=["GET", "POST"])
@login_required(role="Agent")
def category():
    categories = Category.query.all()
    form = CategoryForm()

    if form.validate_on_submit():
        category_obj = Category(category=form.category.data)
        db.session.add(category_obj)
        db.session.commit()

        socketio.emit("category_updated", {"message": "Category created by agent."})
        emit_global_refresh("category_updated")

        flash("Category has been created.", "primary")
        return redirect(url_for("agent.category"))

    return render_template("agent/category.html", form=form, categories=categories)


@agent_blueprint.route(
    "/category/update/<int:id>",
    methods=["GET", "POST"]
)
@login_required(role="Agent")
def update_category(id):
    category_obj = (
        Category.query.get_or_404(id)
    )

    form = CategoryForm()

    if request.method == "GET":
        form.category.data = (
            category_obj.category
        )

    if form.validate_on_submit():
        category_name = (
            form.category.data or ""
        ).strip()

        if not category_name:
            flash(
                "Category name is required.",
                "warning"
            )

            return redirect(
                url_for(
                    "agent.update_category",
                    id=id
                )
            )

        duplicate = (
            Category.query
            .filter(
                func.lower(
                    Category.category
                )
                == category_name.lower(),
                Category.id != category_obj.id
            )
            .first()
        )

        if duplicate:
            flash(
                "A category with this name "
                "already exists.",
                "warning"
            )

            return redirect(
                url_for(
                    "agent.update_category",
                    id=id
                )
            )

        category_obj.category = (
            category_name
        )

        if not safe_commit(
            "Category update failed."
        ):
            flash(
                "Category could not be updated.",
                "danger"
            )

            return redirect(
                url_for(
                    "agent.category"
                )
            )

        emit_global_refresh(
            "category_updated"
        )

        flash(
            "Category updated successfully.",
            "success"
        )

        return redirect(
            url_for("agent.category")
        )

    return render_template(
        "agent/category.html",
        form=form,
        categories=Category.query.all(),
        editing_category=category_obj
    )


@agent_blueprint.route(
    "/category/delete/<int:id>",
    methods=["POST"]
)
@login_required(role="Agent")
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
            "This category cannot be deleted "
            "because it is currently in use.",
            "warning"
        )

        return redirect(
            url_for("agent.category")
        )

    db.session.delete(
        category_obj
    )

    if not safe_commit(
        "Category deletion failed."
    ):
        flash(
            "Category could not be deleted.",
            "danger"
        )

        return redirect(
            url_for("agent.category")
        )

    emit_global_refresh(
        "category_updated"
    )

    flash(
        "Category deleted successfully.",
        "success"
    )

    return redirect(
        url_for("agent.category")
    )


@agent_blueprint.route("/priorities", methods=["GET", "POST"])
@login_required(role="Agent")
def priority():
    priorities = Priority.query.all()
    form = PriorityForm()

    if form.validate_on_submit():
        priority_obj = Priority(priority=form.priority.data)
        db.session.add(priority_obj)
        db.session.commit()

        socketio.emit("priority_updated", {"message": "Priority created by agent."})
        emit_global_refresh("priority_updated")

        flash("Priority has been created.", "primary")
        return redirect(url_for("agent.priority"))

    return render_template("agent/priority.html", form=form, priorities=priorities)


@agent_blueprint.route(
    "/priority/update/<int:id>",
    methods=["GET", "POST"]
)
@login_required(role="Agent")
def update_priority(id):
    priority_obj = (
        Priority.query.get_or_404(id)
    )

    form = PriorityForm()

    if request.method == "GET":
        form.priority.data = (
            priority_obj.priority
        )

    if form.validate_on_submit():
        priority_name = (
            form.priority.data or ""
        ).strip()

        if not priority_name:
            flash(
                "Priority name is required.",
                "warning"
            )

            return redirect(
                url_for(
                    "agent.update_priority",
                    id=id
                )
            )

        duplicate = (
            Priority.query
            .filter(
                func.lower(
                    Priority.priority
                )
                == priority_name.lower(),
                Priority.id != priority_obj.id
            )
            .first()
        )

        if duplicate:
            flash(
                "A priority with this name "
                "already exists.",
                "warning"
            )

            return redirect(
                url_for(
                    "agent.update_priority",
                    id=id
                )
            )

        priority_obj.priority = (
            priority_name
        )

        if not safe_commit(
            "Priority update failed."
        ):
            flash(
                "Priority could not be updated.",
                "danger"
            )

            return redirect(
                url_for("agent.priority")
            )

        emit_global_refresh(
            "priority_updated"
        )

        flash(
            "Priority updated successfully.",
            "success"
        )

        return redirect(
            url_for("agent.priority")
        )

    return render_template(
        "agent/priority.html",
        form=form,
        priorities=Priority.query.all(),
        editing_priority=priority_obj
    )


@agent_blueprint.route(
    "/priority/delete/<int:id>",
    methods=["POST"]
)
@login_required(role="Agent")
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
            "This priority cannot be deleted "
            "because it is assigned to tickets.",
            "warning"
        )

        return redirect(
            url_for("agent.priority")
        )

    db.session.delete(
        priority_obj
    )

    if not safe_commit(
        "Priority deletion failed."
    ):
        flash(
            "Priority could not be deleted.",
            "danger"
        )

        return redirect(
            url_for("agent.priority")
        )

    emit_global_refresh(
        "priority_updated"
    )

    flash(
        "Priority deleted successfully.",
        "success"
    )

    return redirect(
        url_for("agent.priority")
    )


@agent_blueprint.route("/statuses", methods=["GET"])
@login_required(role="Agent")
def status():
    statuses = Status.query.all()
    return render_template("agent/status.html", statuses=statuses)


@agent_blueprint.route("/my-tickets", methods=["GET"])
@login_required(role="Agent")
def my_tickets():
    auto_close_waiting_customer_tickets()
    notify_unassigned_tickets()

    tickets = (
        Ticket.query
        .filter(or_(Ticket.author_id == current_user.id, Ticket.owner_id == current_user.id))
        .order_by(desc(Ticket.created_at))
        .all()
    )

    form = TicketForm()

    return render_template(
        "agent/my_tickets.html",
        form=form,
        tickets=tickets
    )


# ============================================================
# PROFILE / PASSWORD
# ============================================================

@agent_blueprint.route(
    "/my-profile",
    methods=["GET", "POST"]
)
@login_required(role="Agent")
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
                url_for("agent.my_profile")
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

            file.save(
                os.path.join(
                    current_app.config["PROFILE_DIR"],
                    profile_filename
                )
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
                        os.remove(old_image_path)

                    except OSError:
                        current_app.logger.exception(
                            "Could not remove old agent "
                            "profile image for user_id=%s",
                            user.id
                        )

        try:
            db.session.commit()

        except Exception:
            db.session.rollback()

            current_app.logger.exception(
                "Agent profile update failed "
                "for user_id=%s",
                user.id
            )

            flash(
                "Your profile could not be updated.",
                "danger"
            )

            return redirect(
                url_for("agent.my_profile")
            )

        socketio.emit(
            "profile_updated",
            {
                "user_id": user.id,
                "name": user.name,
                "image": user.image,
                "message": "Agent profile updated."
            }
        )

        emit_global_refresh(
            "profile_updated"
        )

        flash(
            "Your profile has been updated.",
            "success"
        )

        return redirect(
            url_for("agent.my_profile")
        )

    return render_template(
        "agent/my_profile.html",
        form=form,
        user=user
    )

@agent_blueprint.route(
    "/change-password",
    methods=["GET", "POST"]
)
@login_required(role="Agent")
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
        if not check_password_hash(
            user.password,
            form.current_password.data
        ):
            flash(
                "Current password is incorrect.",
                "danger"
            )

            return redirect(
                url_for("agent.change_password")
            )

        user.password = generate_password_hash(
            form.password.data
        )

        user.failed_login_attempts = 0
        user.locked_until = None

        try:
            db.session.commit()

        except Exception:
            db.session.rollback()

            current_app.logger.exception(
                "Agent password update failed "
                "for user_id=%s",
                user.id
            )

            flash(
                "The password could not be updated.",
                "danger"
            )

            return redirect(
                url_for("agent.change_password")
            )

        flash(
            "Password updated successfully.",
            "success"
        )

        return redirect(
            url_for("agent.change_password")
        )

    return render_template(
        "agent/change_password.html",
        form=form
    )

@agent_blueprint.route(
    "/change-email",
    methods=["GET", "POST"]
)
@login_required(role="Agent")
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
                    "agent.change_email"
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
                    "agent.change_email"
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
                "Agent email update failed "
                "for user_id=%s",
                current_user.id
            )

            flash(
                "Your email could not be updated.",
                "danger"
            )

            return redirect(
                url_for(
                    "agent.change_email"
                )
            )

        flash(
            "Email updated.",
            "success"
        )

        return redirect(
            url_for(
                "agent.my_profile"
            )
        )

    return render_template(
        "agent/change_email.html",
        form=form
    )


# ============================================================
# NOTIFICATIONS
# ============================================================

@agent_blueprint.route("/notifications", methods=["GET"])
@login_required(role="Agent")
def notifications():
    my_notifications = (
        Notification.query
        .filter(Notification.receiver_id == current_user.id)
        .order_by(desc(Notification.created_at))
        .all()
    )

    return render_template("agent/notifications.html", my_notifications=my_notifications)


@agent_blueprint.route("/read-notification/<int:tid>/<int:nid>", methods=["GET"])
@login_required(role="Agent")
def read_notification(tid, nid):
    return redirect(url_for("agent.open_notification", nid=nid))


@agent_blueprint.route("/notifications/mark-all-read", methods=["POST"])
@login_required(role="Agent")
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
    return redirect(url_for("agent.notifications"))

@agent_blueprint.route("/agent-solutions", methods=["GET", "POST"])
@login_required(role="Agent")
def agent_solutions():

    if request.method == "POST":

        title = (
            request.form.get("title") or ""
        ).strip()

        solution = (
            request.form.get("solution") or ""
        ).strip()

        category_id = request.form.get(
            "category_id",
            type=int
        )

        tags = (
            request.form.get("tags") or ""
        ).strip()

        if not title:
            flash(
                "Solution title is required.",
                "warning"
            )
            return redirect(
                url_for("agent.agent_solutions")
            )

        if not solution:
            flash(
                "Solution details are required.",
                "warning"
            )
            return redirect(
                url_for("agent.agent_solutions")
            )

        new_solution = AgentSolution(
            title=title,
            solution=solution,
            category_id=category_id,
            tags=tags,
            submitted_by_id=current_user.id,
            status="Pending"
        )

        db.session.add(new_solution)
        db.session.commit()

        admins = User.query.filter_by(role="Administrator").all()

        for admin in admins:
            Notification.send_notification(
                message="new agent solution submitted for approval",
                receiver_id=admin.id,
                sender_id=current_user.id,
                ticket_id=None,
                notification_type="agent_knowledge_updated",
                title="New agent solution submitted",
                url=url_for("admin.agent_solution_library"),
                seen=False
            )

        socketio.emit("sidebar_counts_updated", {"message": "Agent solution submitted"})
        socketio.emit("notification_updated", {"message": "Agent solution submitted"})

        flash(
            "Solution submitted successfully and is awaiting admin approval.",
            "success"
        )

        return redirect(
            url_for("agent.agent_solutions")
        )

    solutions = (
        AgentSolution.query
        .filter_by(
            submitted_by_id=current_user.id
        )
        .order_by(
            AgentSolution.created_at.desc()
        )
        .all()
    )

    return render_template(
        "agent/agent_solutions.html",
        solutions=solutions,
        categories=Category.query.order_by(
            Category.category.asc()
        ).all()
    )

@agent_blueprint.route("/notification/open/<int:nid>", methods=["GET"])
@login_required(role="Agent")
def open_notification(nid):
    notification = Notification.query.get_or_404(nid)

    if notification.receiver_id != current_user.id:
        flash("Unauthorized notification.", "danger")
        return redirect(url_for("agent.notifications"))

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
        return redirect(url_for("agent.view_ticket", id=notification.ticket_id))

    if notification.agent_report_id:
        report = notification.agent_report_notification

        if report and report.report_type == "Incident":
            return redirect(url_for("agent.incident_log"))

        if report and report.report_type == "Issue":
            return redirect(url_for("agent.issue_log"))

        if report and report.report_type == "Internal":
            return redirect(url_for("agent.internal_reports"))

        return redirect(url_for("agent.internal_reports"))

    if notification.notification_type == "knowledge_updated":
        return redirect(url_for("agent.knowledge_base"))

    if notification.notification_type == "agent_knowledge_updated":
        return redirect(url_for("agent.agent_solutions"))

    if notification.notification_type == "system_settings_updated":
        return redirect(url_for("agent.faq_library"))

    if (
        notification.url
        and notification.url != "#"
    ):
        safe_url = str(
            notification.url
        ).strip()

        if safe_url.startswith("/"):
            return redirect(
                safe_url
            )

    return redirect(url_for("agent.notifications"))



@agent_blueprint.route("/contribution-statistics")
@login_required(role="Agent")
def contribution_statistics():

    my_solutions_query = AgentSolution.query.filter_by(
        submitted_by_id=current_user.id
    )

    total_solutions = my_solutions_query.count()

    approved_solutions = my_solutions_query.filter_by(
        status="Approved"
    ).count()

    pending_solutions = my_solutions_query.filter_by(
        status="Pending"
    ).count()

    rejected_solutions = my_solutions_query.filter_by(
        status="Rejected"
    ).count()

    total_views = (
        db.session.query(func.coalesce(func.sum(AgentSolution.view_count), 0))
        .filter(AgentSolution.submitted_by_id == current_user.id)
        .scalar()
    )

    total_reuse = (
        db.session.query(func.coalesce(func.sum(AgentSolution.reuse_count), 0))
        .filter(AgentSolution.submitted_by_id == current_user.id)
        .scalar()
    )

    contribution_score = (
        approved_solutions * 10
        + total_views
        + total_reuse
    )

    average_reuse = 0

    if approved_solutions > 0:
        average_reuse = round(total_reuse / approved_solutions, 1)

    most_viewed_solution = (
        AgentSolution.query
        .filter_by(submitted_by_id=current_user.id)
        .order_by(AgentSolution.view_count.desc())
        .first()
    )

    most_reused_solution = (
        AgentSolution.query
        .filter_by(submitted_by_id=current_user.id)
        .order_by(AgentSolution.reuse_count.desc())
        .first()
    )

    recent_solutions = (
        AgentSolution.query
        .filter_by(submitted_by_id=current_user.id)
        .order_by(AgentSolution.created_at.desc())
        .limit(5)
        .all()
    )
    
    agent_ticket_ids = [
        ticket.id for ticket in Ticket.query.filter_by(
            owner_id=current_user.id
        ).all()
    ]

    total_ratings = 0
    average_rating = 0
    five_star_ratings = 0
    low_ratings = 0
    recent_feedback = []

    if agent_ticket_ids:
        total_ratings = (
            CustomerSatisfaction.query
            .filter(CustomerSatisfaction.ticket_id.in_(agent_ticket_ids))
            .count()
        )

        average_rating = (
            db.session.query(func.avg(CustomerSatisfaction.rating))
            .filter(CustomerSatisfaction.ticket_id.in_(agent_ticket_ids))
            .scalar()
        )

        average_rating = round(average_rating or 0, 1)

        five_star_ratings = (
            CustomerSatisfaction.query
            .filter(CustomerSatisfaction.ticket_id.in_(agent_ticket_ids))
            .filter(CustomerSatisfaction.rating == 5)
            .count()
        )

        low_ratings = (
            CustomerSatisfaction.query
            .filter(CustomerSatisfaction.ticket_id.in_(agent_ticket_ids))
            .filter(CustomerSatisfaction.rating <= 2)
            .count()
        )

        recent_feedback = (
            CustomerSatisfaction.query
            .filter(CustomerSatisfaction.ticket_id.in_(agent_ticket_ids))
            .order_by(CustomerSatisfaction.created_at.desc())
            .limit(5)
            .all()
        )

    return render_template(
        "agent/contribution_statistics.html",
        total_solutions=total_solutions,
        approved_solutions=approved_solutions,
        pending_solutions=pending_solutions,
        rejected_solutions=rejected_solutions,
        total_views=total_views,
        total_reuse=total_reuse,
        average_reuse=average_reuse,
        contribution_score=contribution_score,
        most_viewed_solution=most_viewed_solution,
        most_reused_solution=most_reused_solution,
        recent_solutions=recent_solutions,
        total_ratings=total_ratings,
        average_rating=average_rating,
        five_star_ratings=five_star_ratings,
        low_ratings=low_ratings,
        recent_feedback=recent_feedback
    )



@agent_blueprint.route("/solution-effectiveness")
@login_required(role="Agent")
def solution_effectiveness():

    my_solutions = (
        AgentSolution.query
        .filter_by(submitted_by_id=current_user.id)
        .all()
    )

    approved_solutions = [
        solution for solution in my_solutions
        if solution.status == "Approved"
    ]

    total_solutions = len(my_solutions)
    approved_count = len(approved_solutions)

    total_views = sum(
        solution.view_count or 0
        for solution in my_solutions
    )

    total_reuse = sum(
        solution.reuse_count or 0
        for solution in my_solutions
    )

    effectiveness_score = 0

    if total_solutions > 0:
        effectiveness_score = min(
            100,
            round(
                (
                    (approved_count * 20)
                    + total_views
                    + (total_reuse * 2)
                ) / total_solutions
            )
        )

    most_viewed = (
        AgentSolution.query
        .filter_by(submitted_by_id=current_user.id)
        .order_by(AgentSolution.view_count.desc())
        .limit(5)
        .all()
    )

    most_reused = (
        AgentSolution.query
        .filter_by(submitted_by_id=current_user.id)
        .order_by(AgentSolution.reuse_count.desc())
        .limit(5)
        .all()
    )

    return render_template(
        "agent/solution_effectiveness.html",
        total_solutions=total_solutions,
        approved_count=approved_count,
        total_views=total_views,
        total_reuse=total_reuse,
        effectiveness_score=effectiveness_score,
        most_viewed=most_viewed,
        most_reused=most_reused
    )

@agent_blueprint.route("/knowledge-contributions")
@login_required(role="Agent")
def knowledge_contributions():

    solutions = (
        AgentSolution.query
        .filter_by(submitted_by_id=current_user.id)
        .order_by(AgentSolution.created_at.desc())
        .all()
    )

    approved_count = AgentSolution.query.filter_by(
        submitted_by_id=current_user.id,
        status="Approved"
    ).count()

    pending_count = AgentSolution.query.filter_by(
        submitted_by_id=current_user.id,
        status="Pending"
    ).count()

    rejected_count = AgentSolution.query.filter_by(
        submitted_by_id=current_user.id,
        status="Rejected"
    ).count()

    return render_template(
        "agent/knowledge_contributions.html",
        solutions=solutions,
        approved_count=approved_count,
        pending_count=pending_count,
        rejected_count=rejected_count
    )

@agent_blueprint.route("/knowledge-base", methods=["GET"])
@login_required(role="Agent")
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

    articles = query.order_by(KnowledgeArticle.created_at.desc()).all()

    return render_template(
        "agent/knowledge_base.html",
        articles=articles,
        categories=Category.query.order_by(Category.category.asc()).all(),
        selected_category_id=category_id,
        search=search
    )
@agent_blueprint.route("/support-help", methods=["GET"])
@login_required(role="Agent")
def support_help():
    return render_template("agent/support_help.html")

@agent_blueprint.route("/suggested-articles")
@login_required(role="Agent")
def suggested_articles():

    repeated_questions = (
        db.session.query(
            ChatMessage.message,
            func.count(ChatMessage.id).label("total")
        )
        .filter(ChatMessage.role == "user")
        .group_by(ChatMessage.message)
        .having(func.count(ChatMessage.id) >= 2)
        .order_by(func.count(ChatMessage.id).desc())
        .limit(10)
        .all()
    )

    recent_articles = (
        KnowledgeArticle.query
        .filter_by(is_active=True)
        .order_by(KnowledgeArticle.created_at.desc())
        .limit(8)
        .all()
    )

    recent_faqs = (
        FAQ.query
        .filter_by(is_active=True)
        .order_by(FAQ.created_at.desc())
        .limit(8)
        .all()
    )

    return render_template(
        "agent/suggested_articles.html",
        repeated_questions=repeated_questions,
        recent_articles=recent_articles,
        recent_faqs=recent_faqs
    )
