from app.admin.views import log_system_event
from flask import Blueprint, current_app, render_template as _render, send_file, redirect, request, url_for, flash, jsonify
from flask_login import current_user
from flask_socketio import join_room

from app.agent.forms import (
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
from werkzeug.security import generate_password_hash

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

def get_agent_ticket_or_404(ticket_id, allow_unassigned=False):
    query = Ticket.query.filter(Ticket.id == ticket_id)

    if allow_unassigned:
        query = query.filter(
            or_(
                Ticket.owner_id == current_user.id,
                Ticket.owner_id == None,
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

        # --------------------------------------------------------
        # SUPPORT DESK
        # --------------------------------------------------------

        agent_new_ticket_count = (
            Ticket.query
            .filter(Ticket.owner_id == None)
            .filter(Ticket.status_id != closed_id)
            .count()
        )

        agent_assigned_ticket_count = (
            Ticket.query
            .filter(Ticket.owner_id == current_user.id)
            .filter(Ticket.status_id != closed_id)
            .count()
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
    status = Status.query.filter_by(status=status_name).first()
    return status.id if status else fallback


def get_open_status_id():
    return get_status_id("Open", 1)


def get_pending_status_id():
    return get_status_id("Pending", 3)


def get_closed_status_id():
    return get_status_id("Closed", 4)


def get_escalated_status_id():
    return get_status_id("Escalated", None)

def get_waiting_customer_status_id():
    return get_status_id("Waiting For Customer", None)


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
                sender_id=ticket.owner_id or current_user.id,
                ticket_id=ticket.id
            )

            reminder_comment = Comment(
                comment="Reminder sent to customer: ticket is waiting for customer response.",
                author_id=ticket.owner_id or current_user.id,
                ticket_id=ticket.id
            )

            db.session.add(reminder_comment)
            ticket.inactive_reminder_sent = True

        if waiting_hours >= 48:
            ticket.status_id = closed_id

            close_comment = Comment(
                comment="Ticket automatically closed because the customer did not respond within 48 hours.",
                author_id=ticket.owner_id or current_user.id,
                ticket_id=ticket.id
            )

            db.session.add(close_comment)

    db.session.commit()
    

def notify_unassigned_tickets():
    now = datetime.datetime.utcnow()

    closed_id = get_closed_status_id()

    unassigned_tickets = (
        Ticket.query
        .filter(Ticket.owner_id == None)
        .filter(Ticket.status_id != closed_id)
        .all()
    )

    for ticket in unassigned_tickets:

        if not ticket.created_at:
            continue

        created_at = ticket.created_at.replace(tzinfo=None)

        waiting_minutes = (
            now - created_at
        ).total_seconds() / 60

        # =====================================================
        # 15 MINUTE CUSTOMER WAITING NOTIFICATION
        # =====================================================

        if waiting_minutes >= 15 and not ticket.unassigned_15min_sent:

            notify_user(
                message=(
                    "Your ticket is still waiting for an available support agent. "
                    "Thank you for your patience."
                ),
                receiver_id=ticket.author_id,
                sender_id=ticket.author_id,
                ticket_id=ticket.id
            )

            reminder_comment = Comment(
                comment=(
                    "Customer wait-time reminder sent: ticket is still waiting "
                    "for an available support agent."
                ),
                author_id=ticket.author_id,
                ticket_id=ticket.id
            )

            db.session.add(reminder_comment)

            ticket.unassigned_15min_sent = True

        # =====================================================
        # 30 MINUTE STAFF ALERT
        # =====================================================

        if waiting_minutes >= 30 and not ticket.unassigned_30min_sent:

            staff_users = (
                User.query
                .filter(User.role.in_(["Agent", "Administrator"]))
                .all()
            )

            for staff in staff_users:

                notify_user(
                    message=(
                        f"Unassigned ticket #{ticket.number} has been waiting "
                        "over 30 minutes."
                    ),
                    receiver_id=staff.id,
                    sender_id=ticket.author_id,
                    ticket_id=ticket.id
                )

            staff_comment = Comment(
                comment=(
                    "Staff alert sent: ticket has been unassigned for more "
                    "than 30 minutes."
                ),
                author_id=ticket.author_id,
                ticket_id=ticket.id
            )

            db.session.add(staff_comment)

            ticket.unassigned_30min_sent = True

    db.session.commit()


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


def emit_comment(ticket, comment, is_attachment=False):
    payload = {
        "ticket_id": ticket.id,
        "ticket_number": ticket.number,
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

    socketio.emit(event_name, payload, room=f"ticket_{ticket.id}")
    socketio.emit(event_name, payload)
    socketio.emit("global_ticket_updated", payload)
    socketio.emit("sidebar_counts_updated", payload)
    socketio.emit("notification_updated", payload)
    socketio.emit("analytics_updated", payload)


def serialize_comment(comment):
    return {
        "id": comment.id,
        "message": comment.comment,
        "author": comment.user.name,
        "author_id": comment.author_id,
        "role": comment.user.role,
        "created_at": comment.created_at.strftime("%d %b %Y, %H:%M") if comment.created_at else ""
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

@agent_blueprint.route("/dashboard")
@login_required(role="Agent")
def dashboard():
    auto_close_waiting_customer_tickets()
    notify_unassigned_tickets()

    user_id = current_user.id

    open_tickets = (
        Ticket.query
        .filter(Ticket.owner_id == user_id)
        .filter_by(status_id=get_open_status_id())
        .all()
    )

    pending = (
        Ticket.query
        .filter(Ticket.owner_id == user_id)
        .filter_by(status_id=get_pending_status_id())
        .all()
    )

    solved = (
        Ticket.query
        .filter(Ticket.owner_id == user_id)
        .filter_by(status_id=get_status_id("Solved", 2))
        .all()
    )

    closed = (
        Ticket.query
        .filter(Ticket.owner_id == user_id)
        .filter_by(status_id=get_closed_status_id())
        .all()
    )

    assigned_tickets = (
        Ticket.query
        .filter(Ticket.owner_id == user_id)
        .filter(Ticket.status_id != get_closed_status_id())
        .order_by(desc(Ticket.updated_at))
        .limit(10)
        .all()
    )

    active_chats = (
        Ticket.query
        .filter(Ticket.owner_id == user_id)
        .filter(Ticket.status_id != get_closed_status_id())
        .order_by(desc(Ticket.updated_at))
        .limit(5)
        .all()
    )

    unassigned_count = (
        Ticket.query
        .filter(Ticket.owner_id == None)
        .filter(Ticket.status_id != get_closed_status_id())
        .count()
    )

    total_assigned = (
        Ticket.query
        .filter(Ticket.owner_id == user_id)
        .count()
    )

    escalated_status = Status.query.filter_by(status="Escalated").first()
    escalated_count = 0

    if escalated_status:
        escalated_count = (
            Ticket.query
            .filter(
                Ticket.owner_id == user_id,
                Ticket.status_id == escalated_status.id
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




@agent_blueprint.route("/new-tickets", methods=["GET"])
@login_required(role="Agent")
def new_tickets():
    auto_close_waiting_customer_tickets()
    notify_unassigned_tickets()

    tickets = (
        Ticket.query
        .filter(Ticket.owner_id == None)
        .filter(Ticket.status_id != get_closed_status_id())
        .order_by(desc(Ticket.created_at))
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

@agent_blueprint.route("/ticket/claim/<int:id>", methods=["POST"])
@login_required(role="Agent")
def claim_ticket(id):

    # Atomic claim: only update if owner_id is NULL
    updated = (
        Ticket.query
        .filter(Ticket.id == id)
        .filter(Ticket.owner_id == None)
        .update({
            "owner_id": current_user.id,
            "unassigned_15min_sent": False,
            "unassigned_30min_sent": False
        })
    )

    db.session.commit()

    # If updated == 0, someone else claimed it first
    if updated == 0:
        flash("This ticket has already been claimed by another support staff.", "warning")
        return redirect(url_for("agent.new_tickets"))

    # Reload the ticket AFTER the atomic update
    ticket = Ticket.query.get_or_404(id)

    # Update status if needed
    if ticket.status_id == get_open_status_id():
        ticket.status_id = get_pending_status_id()

    # Add join message
    join_message = f"✅ Support agent {current_user.name} has joined the chat."

    comment = Comment(
        comment=join_message,
        author_id=current_user.id,
        ticket_id=ticket.id
    )

    db.session.add(comment)
    db.session.commit()

    notify_customer(ticket, "joined your support ticket")
    emit_comment(ticket, comment, is_attachment=False)
    emit_ticket_event(ticket, "agent_joined", join_message)

    flash("You have joined this ticket.", "primary")
    return redirect(url_for("agent.view_ticket", id=id))



@agent_blueprint.route("/create-ticket", methods=["GET", "POST"])
@login_required(role="Agent")
def create_ticket():
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

        socketio.emit("ticket_created", {
            "ticket_id": ticket.id,
            "ticket_number": ticket.number,
            "message": "Ticket created by agent."
        })

        emit_global_refresh("ticket_created", ticket)

        flash("Ticket has been created.", "primary")
        return redirect(url_for("agent.new_tickets"))

    return render_template(
        "agent/new_tickets.html",
        form=form,
        tickets=[]
    )


@agent_blueprint.route("/view-ticket/<int:id>", methods=["GET", "POST"])
@login_required(role="Agent")
def view_ticket(id):
    ticket = get_agent_ticket_or_404(id, allow_unassigned=True)

    if not ticket:
        flash("Ticket not found.", "warning")
        return redirect(url_for("agent.new_tickets"))

    comments = (
        Comment.query
        .filter(Comment.ticket_id == id)
        .order_by(Comment.created_at.asc())
        .all()
    )

    form = UpdateTicketForm(
        owner=ticket.owner_id,
        priority=ticket.priority_id,
        status=ticket.status_id
    )

    comment_form = CommentForm()

    if form.validate_on_submit():
        if ticket.status_id == get_closed_status_id():
            flash("Closed tickets cannot be updated. Please use Reopen Ticket first.", "warning")
            return redirect(url_for("agent.view_ticket", id=id))

        old_owner_id = ticket.owner_id
        old_status_id = ticket.status_id
        old_priority_id = ticket.priority_id

        new_status_id = int(form.status.data)
        new_priority_id = int(form.priority.data)

        if not form.owner.data:
            if ticket.owner_id:
                notify_customer(ticket, "unassigned ticket")
                notify_owner(ticket, "unassigned ticket")

            ticket.owner_id = None

        else:
            new_owner_id = int(form.owner.data)

            if old_owner_id != new_owner_id:
                notify_customer(ticket, "assigned ticket")

                if new_owner_id != current_user.id:
                    notify_user(
                        message="assigned ticket",
                        receiver_id=new_owner_id,
                        sender_id=current_user.id,
                        ticket_id=ticket.id
                    )

                join_message = f"✅ Support agent {current_user.name} joined the chat."

                join_comment = Comment(
                    comment=join_message,
                    author_id=current_user.id,
                    ticket_id=ticket.id
                )

                db.session.add(join_comment)

            ticket.owner_id = new_owner_id

        if old_priority_id != new_priority_id:
            notify_customer(ticket, "updated priority on ticket")

        ticket.priority_id = new_priority_id

        if old_status_id != new_status_id:
            notify_customer(ticket, "updated status on ticket")

        if old_status_id != new_status_id and new_status_id == get_closed_status_id():
            close_message = f"Ticket closed by support agent {current_user.name}."

            close_comment = Comment(
                comment=close_message,
                author_id=current_user.id,
                ticket_id=ticket.id
            )

            db.session.add(close_comment)

            ChatMessage.query.filter(
                ChatMessage.user_id == ticket.author_id
            ).update({
                "customer_visible": False
            })

        ticket.status_id = new_status_id
        if new_status_id == get_waiting_customer_status_id():
            ticket.waiting_customer_since = datetime.datetime.utcnow()
            ticket.inactive_reminder_sent = False
        else:
            ticket.waiting_customer_since = None
            ticket.inactive_reminder_sent = False
        db.session.commit()

        if old_owner_id != ticket.owner_id and ticket.owner_id is not None:
            latest_join = (
                Comment.query
                .filter(Comment.ticket_id == ticket.id)
                .filter(Comment.comment.like("✅ Support agent%joined the chat."))
                .order_by(desc(Comment.created_at))
                .first()
            )

            if latest_join:
                emit_comment(ticket, latest_join, is_attachment=False)
                emit_ticket_event(ticket, "agent_joined", latest_join.comment)

        if old_status_id != new_status_id and new_status_id == get_closed_status_id():
            latest_close = (
                Comment.query
                .filter(Comment.ticket_id == ticket.id)
                .filter(Comment.comment.like("Ticket closed by support agent%"))
                .order_by(desc(Comment.created_at))
                .first()
            )

            if latest_close:
                emit_comment(ticket, latest_close, is_attachment=False)
                emit_ticket_event(ticket, "ticket_closed", latest_close.comment)

        emit_global_refresh("ticket_updated", ticket)

        flash("Ticket has been updated.", "primary")
        return redirect(url_for("agent.view_ticket", id=id))

    return render_template(
        "agent/view_ticket.html",
        form=form,
        comment_form=comment_form,
        ticket=ticket,
        comments=comments
    )


@agent_blueprint.route("/ticket/reopen/<int:id>", methods=["GET", "POST"])
@login_required(role="Agent")
def reopen_ticket(id):
    ticket = get_agent_ticket_or_404(id)

    ticket.status_id = get_pending_status_id()

    reopen_message = f"Ticket reopened by agent {current_user.name}."

    comment = Comment(
        comment=reopen_message,
        author_id=current_user.id,
        ticket_id=ticket.id
    )

    db.session.add(comment)
    db.session.commit()

    notify_customer(ticket, "reopened ticket")
    notify_admins(ticket, "reopened ticket")

    emit_comment(ticket, comment, is_attachment=False)
    emit_ticket_event(ticket, "ticket_reopened", reopen_message)

    flash("Ticket has been reopened and changed to Pending.", "primary")
    return redirect(url_for("agent.view_ticket", id=ticket.id))


@agent_blueprint.route("/ticket/escalate/<int:id>", methods=["POST"])
@login_required(role="Agent")
def escalate_ticket(id):
    ticket = get_agent_ticket_or_404(id)

    if ticket.status and ticket.status.status == "Closed":
        flash("Closed tickets cannot be escalated. Reopen the ticket first.", "warning")
        return redirect(url_for("agent.view_ticket", id=ticket.id))

    escalated_status = Status.query.filter_by(status="Escalated").first()

    if not escalated_status:
        flash("Escalated status does not exist. Please add it first.", "danger")
        return redirect(url_for("agent.view_ticket", id=ticket.id))

    ticket.status_id = escalated_status.id
    ticket.owner_id = None

    escalate_message = f"🚨 Ticket escalated to admin by support agent {current_user.name}."

    comment = Comment(
        comment=escalate_message,
        author_id=current_user.id,
        ticket_id=ticket.id
    )

    db.session.add(comment)
    db.session.commit()

    notify_customer(ticket, "ticket escalated to admin")
    notify_admins(ticket, "escalated ticket to admin")

    emit_comment(ticket, comment, is_attachment=False)
    emit_ticket_event(ticket, "ticket_escalated", escalate_message)

    flash("Ticket has been escalated to admin.", "primary")
    return redirect(url_for("agent.view_ticket", id=ticket.id))


@agent_blueprint.route("/comment-ticket/<int:id>", methods=["GET", "POST"])
@login_required(role="Agent")
def comment_ticket(id):
    ticket = get_agent_ticket_or_404(id)
    comment_form = CommentForm()

    if ticket.status_id == get_closed_status_id():
        return jsonify({
            "success": False,
            "message": "Closed tickets cannot receive new messages."
        }), 400

    if comment_form.validate_on_submit():
        comment_text = (comment_form.comment.data or "").strip()

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

        notify_customer(ticket, "commented on ticket")
        notify_owner(ticket, "commented on ticket")

        emit_comment(ticket, new_comment, is_attachment=False)

        return jsonify({
            "success": True,
            "comment": serialize_comment(new_comment)
        }), 200

    return jsonify({
        "success": False,
        "message": "Invalid message."
    }), 400


@agent_blueprint.route("/ticket/delete/<int:uid>/<int:tid>", methods=["GET", "POST"])
@login_required(role="Agent")
def delete_ticket(uid, tid):
    ticket = get_agent_ticket_or_404(tid)

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
            "message": "Ticket deleted by agent."
        }

        socketio.emit("ticket_deleted", payload)
        socketio.emit("global_ticket_updated", payload)
        socketio.emit("sidebar_counts_updated", payload)
        socketio.emit("notification_updated", payload)
        socketio.emit("analytics_updated", payload)

        flash("Ticket has been deleted.", "primary")
        return redirect(url_for("agent.new_tickets"))

    return redirect(url_for("agent.my_tickets"))


@agent_blueprint.route("/download/attachment/<int:id>/<filename>")
def download_attachment(id, filename):
    folder_id = os.path.join(path, "app/static/uploads/attachments", str(id))
    location = os.path.join(folder_id, filename)
    return send_file(location, as_attachment=True)


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


@agent_blueprint.route("/category/update/<int:id>", methods=["GET", "POST"])
@login_required(role="Agent")
def update_category(id):
    category_obj = Category.query.get_or_404(id)
    form = CategoryForm()

    if form.validate_on_submit():
        category_obj.category = form.category.data
        db.session.commit()

        socketio.emit("category_updated", {"message": "Category updated by agent."})
        emit_global_refresh("category_updated")

        flash("Category has been updated.", "primary")
        return redirect(url_for("agent.category"))

    return render_template("agent/category.html", form=form)


@agent_blueprint.route("/category/delete/<int:id>", methods=["GET", "POST"])
@login_required(role="Agent")
def delete_category(id):
    category_obj = Category.query.get_or_404(id)

    if request.method == "POST":
        db.session.delete(category_obj)
        db.session.commit()

        socketio.emit("category_updated", {"message": "Category deleted by agent."})
        emit_global_refresh("category_updated")

        flash("Category has been deleted.", "primary")
        return redirect(url_for("agent.category"))

    return redirect(url_for("agent.category"))


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


@agent_blueprint.route("/priority/update/<int:id>", methods=["GET", "POST"])
@login_required(role="Agent")
def update_priority(id):
    priority_obj = Priority.query.get_or_404(id)
    form = PriorityForm()

    if form.validate_on_submit():
        priority_obj.priority = form.priority.data
        db.session.commit()

        socketio.emit("priority_updated", {"message": "Priority updated by agent."})
        emit_global_refresh("priority_updated")

        flash("Priority has been updated.", "primary")
        return redirect(url_for("agent.priority"))

    return render_template("agent/priority.html", form=form)


@agent_blueprint.route("/priority/delete/<int:id>", methods=["GET", "POST"])
@login_required(role="Agent")
def delete_priority(id):
    priority_obj = Priority.query.get_or_404(id)

    if request.method == "POST":
        db.session.delete(priority_obj)
        db.session.commit()

        socketio.emit("priority_updated", {"message": "Priority deleted by agent."})
        emit_global_refresh("priority_updated")

        flash("Priority has been deleted.", "primary")
        return redirect(url_for("agent.priority"))

    return redirect(url_for("agent.priority"))


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

@agent_blueprint.route("/my-profile", methods=["GET", "POST"])
@login_required(role="Agent")
def my_profile():
    user = User.query.filter(User.id == current_user.id).first()
    form = ChangeProfileForm()

    if form.validate_on_submit():
        file = form.profile.data

        if file and file.filename:
            _, ext = os.path.splitext(file.filename)
            profile = secure_filename(str(user.id) + ext)

            file.save(os.path.join(current_app.config["PROFILE_DIR"], profile))

            user.image = profile
            db.session.commit()

            socketio.emit("profile_updated", {
                "user_id": current_user.id,
                "message": "Agent profile updated."
            })

            emit_global_refresh("profile_updated")

            flash("Your profile has been changed.", "primary")
            return redirect(url_for("agent.my_profile"))

    return render_template("agent/my_profile.html", form=form, user=user)


@agent_blueprint.route("/change-password", methods=["GET", "POST"])
@login_required(role="Agent")
def change_password():
    user = User.query.filter(User.id == current_user.id).first()
    form = ChangePasswordForm()

    if form.validate_on_submit():
        user.password = generate_password_hash(form.password.data)
        log_system_event(
            event_type="Password Changed",
            severity="Info",
            message=f"Password changed for {user.email}.",
            user_id=user.id
        )
        db.session.commit()

        socketio.emit("password_updated", {
            "user_id": current_user.id,
            "message": "Agent password updated."
        })

        emit_global_refresh("password_updated")

        flash("Your password has been changed.", "primary")
        return redirect(url_for("agent.change_password"))

    return render_template("agent/change_password.html", form=form)


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

    if notification.url and notification.url != "#":
        return redirect(notification.url)

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

# ============================================================
# SOCKET ROOMS
# ============================================================

@socketio.on("join_ticket_room")
def join_ticket_room(data):
    try:
        ticket_id = str(data.get("ticket_id"))

        if not ticket_id:
            return

        room = f"ticket_{ticket_id}"
        join_room(room)

        print(f"✅ Agent joined ticket room: {room}")

    except Exception as e:
        print("AGENT SOCKET ROOM ERROR:", e)


@socketio.on("join_notification_room")
def join_notification_room(data):
    try:
        user_id = str(data.get("user_id"))

        if not user_id:
            return

        room = f"user_{user_id}"
        join_room(room)

        print(f"✅ Agent joined user room: {room}")

    except Exception as e:
        print("AGENT USER ROOM ERROR:", e)