from datetime import datetime
from typing import Any, Optional

from flask import current_app, render_template
from flask_mail import Message

from app.exts import db, mail
from app.models import EmailLog, EmailPreference


# ============================================================
# EMAIL PREFERENCE CHECKING
# ============================================================

def can_send_preference_email(
    user_id: Optional[int],
    preference_type: str
) -> bool:
    """
    Check whether a user allows an optional email category.

    Supported optional preference types:
        ticket_updates
        satisfaction_emails
        marketing_emails

    Mandatory security emails must not call this helper:
        email verification
        login OTP
        password-reset link
        password-changed confirmation

    Returns True when:
        - user_id is unavailable;
        - no EmailPreference row exists yet;
        - the requested preference name is unknown;
        - the preference is enabled.

    Returns False only when the user explicitly disabled the
    requested optional email category.
    """

    if not user_id:
        return True

    preference_type = (
        preference_type or ""
    ).strip().lower()

    allowed_preferences = {
        "ticket_updates",
        "satisfaction_emails",
        "marketing_emails"
    }

    if preference_type not in allowed_preferences:
        current_app.logger.warning(
            "UNKNOWN EMAIL PREFERENCE TYPE: "
            "user_id=%s preference_type=%s",
            user_id,
            preference_type
        )

        # Unknown categories default to enabled so an incorrect
        # preference name does not silently block system emails.
        return True

    try:
        preference = EmailPreference.query.filter_by(
            user_id=user_id
        ).first()

    except Exception as error:
        current_app.logger.exception(
            "EMAIL PREFERENCE CHECK ERROR: "
            "user_id=%s preference_type=%s error=%s",
            user_id,
            preference_type,
            error
        )

        # A preference-table failure must not break the main
        # application action.
        return True

    if not preference:
        # Existing accounts may not yet have an EmailPreference row.
        # The default behaviour is therefore to allow emails.
        return True

    preference_value = getattr(
        preference,
        preference_type,
        True
    )

    return bool(preference_value)


def _optional_email_allowed(
    user: Any,
    preference_type: str,
    email_type: str,
    ticket: Optional[Any] = None
) -> bool:
    """
    Shared internal helper for optional emails.

    This avoids repeating the same preference logging code in
    every ticket email function.
    """

    user_id = getattr(
        user,
        "id",
        None
    )

    allowed = can_send_preference_email(
        user_id=user_id,
        preference_type=preference_type
    )

    if not allowed:
        current_app.logger.info(
            "EMAIL SKIPPED BY USER PREFERENCE: "
            "email_type=%s preference_type=%s "
            "user_id=%s ticket_id=%s",
            email_type,
            preference_type,
            user_id,
            getattr(ticket, "id", None)
        )

    return allowed


# ============================================================
# EMAIL LOGGING
# ============================================================

def _save_email_log(log: EmailLog) -> bool:
    """
    Save or update an EmailLog record.

    Email-log database failures are caught so that a logging
    problem does not crash the main ticket or authentication
    operation.
    """

    try:
        db.session.add(log)
        db.session.commit()

        return True

    except Exception as error:
        db.session.rollback()

        current_app.logger.exception(
            "EMAIL LOG DATABASE ERROR: %s",
            error
        )

        return False


# ============================================================
# CENTRAL EMAIL SENDER
# ============================================================

def send_email(
    recipient: str,
    subject: str,
    email_type: str,
    *,
    text_body: Optional[str] = None,
    text_template: Optional[str] = None,
    html_template: Optional[str] = None,
    template_context: Optional[dict[str, Any]] = None,
    user_id: Optional[int] = None,
    ticket_id: Optional[int] = None
) -> bool:
    """
    Render, send and log one application email.

    Parameters
    ----------
    recipient:
        Destination email address.

    subject:
        Email subject line.

    email_type:
        Internal identifier stored in email_logs.

    text_body:
        Optional already-generated plain-text body.

    text_template:
        Optional Jinja plain-text template path.

    html_template:
        Optional Jinja HTML template path.

    template_context:
        Values passed into the text and HTML templates.

    user_id:
        Related user ID stored in email_logs.

    ticket_id:
        Related ticket ID stored in email_logs.

    Returns
    -------
    bool:
        True when SMTP sends successfully.
        False when validation, rendering or SMTP fails.
    """

    recipient = (
        recipient or ""
    ).strip()

    subject = (
        subject or ""
    ).strip()

    email_type = (
        email_type or "general"
    ).strip()

    # Create a pending log before validation/rendering/SMTP.
    log = EmailLog(
        recipient=recipient or "missing-recipient",
        subject=subject or "Missing subject",
        email_type=email_type,
        status="Pending",
        user_id=user_id,
        ticket_id=ticket_id,
        error_message=None,
        created_at=datetime.utcnow(),
        sent_at=None
    )

    _save_email_log(log)

    # --------------------------------------------------------
    # VALIDATE RECIPIENT
    # --------------------------------------------------------

    if not recipient:
        log.status = "Failed"
        log.error_message = (
            "Recipient email address is missing."
        )

        _save_email_log(log)

        current_app.logger.error(
            "EMAIL SEND FAILED: "
            "email_type=%s recipient is missing",
            email_type
        )

        return False

    # --------------------------------------------------------
    # VALIDATE SUBJECT
    # --------------------------------------------------------

    if not subject:
        log.status = "Failed"
        log.error_message = (
            "Email subject is missing."
        )

        _save_email_log(log)

        current_app.logger.error(
            "EMAIL SEND FAILED: "
            "email_type=%s subject is missing",
            email_type
        )

        return False

    context = template_context or {}

    try:
        # ----------------------------------------------------
        # RENDER PLAIN-TEXT BODY
        # ----------------------------------------------------

        rendered_text = text_body

        if text_template:
            rendered_text = render_template(
                text_template,
                **context
            )

        if not rendered_text:
            rendered_text = (
                "This email requires an HTML-compatible "
                "email client."
            )

        # ----------------------------------------------------
        # RENDER HTML BODY
        # ----------------------------------------------------

        rendered_html = None

        if html_template:
            rendered_html = render_template(
                html_template,
                **context
            )

        # ----------------------------------------------------
        # CREATE FLASK-MAIL MESSAGE
        # ----------------------------------------------------

        message = Message(
            subject=subject,
            recipients=[recipient]
        )

        message.body = rendered_text

        if rendered_html:
            message.html = rendered_html

        # ----------------------------------------------------
        # SEND THROUGH SMTP
        # ----------------------------------------------------

        mail.send(message)

        # ----------------------------------------------------
        # MARK EMAIL LOG AS SENT
        # ----------------------------------------------------

        log.status = "Sent"
        log.sent_at = datetime.utcnow()
        log.error_message = None

        _save_email_log(log)

        current_app.logger.info(
            "EMAIL SENT: "
            "email_type=%s recipient=%s "
            "user_id=%s ticket_id=%s",
            email_type,
            recipient,
            user_id,
            ticket_id
        )

        return True

    except Exception as error:
        db.session.rollback()

        log.status = "Failed"
        log.sent_at = None
        log.error_message = str(error)[:2000]

        _save_email_log(log)

        current_app.logger.exception(
            "EMAIL SEND ERROR: "
            "email_type=%s recipient=%s "
            "user_id=%s ticket_id=%s error=%s",
            email_type,
            recipient,
            user_id,
            ticket_id,
            error
        )

        return False


# ============================================================
# AUTHENTICATION AND SECURITY EMAILS
# ============================================================
#
# These emails intentionally do not check optional preferences.
# They are required for account security and authentication.
# ============================================================

def send_verification_email(
    user: Any,
    code: str
) -> bool:
    """
    Send the registration email-verification OTP.
    """

    return send_email(
        recipient=user.email,
        subject="Verify Your Email Address",
        email_type="email_verification",
        text_template="email/verify_email.txt",
        html_template="email/verify_email.html",
        template_context={
            "user": user,
            "code": code
        },
        user_id=user.id
    )


def send_login_otp_email(
    user: Any,
    code: str
) -> bool:
    """
    Send the six-digit login OTP.
    """

    return send_email(
        recipient=user.email,
        subject="Your Login Verification Code",
        email_type="login_otp",
        text_template="email/login_otp.txt",
        html_template="email/login_otp.html",
        template_context={
            "user": user,
            "code": code
        },
        user_id=user.id
    )


def send_password_reset_email(
    user: Any,
    token: str
) -> bool:
    """
    Send a password-reset link.

    The reset templates receive:
        name
        token
    """

    return send_email(
        recipient=user.email,
        subject="Password Reset Request",
        email_type="password_reset",
        text_template="email/reset_password.txt",
        html_template="email/reset_password.html",
        template_context={
            "name": user.name,
            "token": token
        },
        user_id=user.id
    )


def send_password_changed_email(
    user: Any
) -> bool:
    """
    Notify the account owner after the password changes.
    """

    return send_email(
        recipient=user.email,
        subject="Your Password Was Changed",
        email_type="password_changed",
        text_template="email/password_changed.txt",
        html_template="email/password_changed.html",
        template_context={
            "user": user,
            "current_time": datetime.utcnow().strftime(
                "%d %b %Y, %H:%M UTC"
            )
        },
        user_id=user.id
    )


# ============================================================
# TICKET-CREATED EMAIL
# ============================================================

def send_ticket_created_email(
    user: Any,
    ticket: Any
) -> bool:
    """
    Notify the customer that a ticket has been created.
    """

    if not _optional_email_allowed(
        user=user,
        preference_type="ticket_updates",
        email_type="ticket_created",
        ticket=ticket
    ):
        # True means the calling ticket action may continue.
        # The email was intentionally skipped, not technically failed.
        return True

    return send_email(
        recipient=user.email,
        subject=(
            f"Support Ticket #{ticket.number} Created"
        ),
        email_type="ticket_created",
        text_template="email/ticket_created.txt",
        html_template="email/ticket_created.html",
        template_context={
            "user": user,
            "ticket": ticket
        },
        user_id=user.id,
        ticket_id=ticket.id
    )


# ============================================================
# TICKET-ASSIGNED EMAIL
# ============================================================

def send_ticket_assigned_email(
    user: Any,
    ticket: Any
) -> bool:
    """
    Notify the customer that support staff were assigned.
    """

    if not _optional_email_allowed(
        user=user,
        preference_type="ticket_updates",
        email_type="ticket_assigned",
        ticket=ticket
    ):
        return True

    return send_email(
        recipient=user.email,
        subject=(
            f"Ticket #{ticket.number} Assigned"
        ),
        email_type="ticket_assigned",
        text_template="email/ticket_assigned.txt",
        html_template="email/ticket_assigned.html",
        template_context={
            "user": user,
            "ticket": ticket
        },
        user_id=user.id,
        ticket_id=ticket.id
    )


# ============================================================
# TICKET-REASSIGNED EMAIL
# ============================================================

def send_ticket_reassigned_email(
    user: Any,
    ticket: Any
) -> bool:
    """
    Notify the customer that the assigned staff member changed.
    """

    if not _optional_email_allowed(
        user=user,
        preference_type="ticket_updates",
        email_type="ticket_reassigned",
        ticket=ticket
    ):
        return True

    return send_email(
        recipient=user.email,
        subject=(
            f"Ticket #{ticket.number} Reassigned"
        ),
        email_type="ticket_reassigned",
        text_template="email/ticket_reassigned.txt",
        html_template="email/ticket_reassigned.html",
        template_context={
            "user": user,
            "ticket": ticket
        },
        user_id=user.id,
        ticket_id=ticket.id
    )


# ============================================================
# TICKET-REPLY EMAIL
# ============================================================

def send_ticket_reply_email(
    user: Any,
    ticket: Any,
    reply_message: str
) -> bool:
    """
    Notify the customer about a new agent/admin ticket reply.
    """

    if not _optional_email_allowed(
        user=user,
        preference_type="ticket_updates",
        email_type="ticket_reply",
        ticket=ticket
    ):
        return True

    return send_email(
        recipient=user.email,
        subject=(
            f"New Reply on Ticket #{ticket.number}"
        ),
        email_type="ticket_reply",
        text_template="email/ticket_reply.txt",
        html_template="email/ticket_reply.html",
        template_context={
            "user": user,
            "ticket": ticket,
            "message": reply_message
        },
        user_id=user.id,
        ticket_id=ticket.id
    )


# ============================================================
# TICKET-CLOSED EMAIL
# ============================================================

def send_ticket_closed_email(
    user: Any,
    ticket: Any
) -> bool:
    """
    Notify the customer that the ticket was closed.
    """

    if not _optional_email_allowed(
        user=user,
        preference_type="ticket_updates",
        email_type="ticket_closed",
        ticket=ticket
    ):
        return True

    return send_email(
        recipient=user.email,
        subject=(
            f"Ticket #{ticket.number} Closed"
        ),
        email_type="ticket_closed",
        text_template="email/ticket_closed.txt",
        html_template="email/ticket_closed.html",
        template_context={
            "user": user,
            "ticket": ticket
        },
        user_id=user.id,
        ticket_id=ticket.id
    )


# ============================================================
# TICKET-REOPENED EMAIL
# ============================================================

def send_ticket_reopened_email(
    user: Any,
    ticket: Any
) -> bool:
    """
    Notify the customer that the ticket was reopened.
    """

    if not _optional_email_allowed(
        user=user,
        preference_type="ticket_updates",
        email_type="ticket_reopened",
        ticket=ticket
    ):
        return True

    return send_email(
        recipient=user.email,
        subject=(
            f"Ticket #{ticket.number} Reopened"
        ),
        email_type="ticket_reopened",
        text_template="email/ticket_reopened.txt",
        html_template="email/ticket_reopened.html",
        template_context={
            "user": user,
            "ticket": ticket
        },
        user_id=user.id,
        ticket_id=ticket.id
    )


# ============================================================
# TICKET-ESCALATED EMAIL
# ============================================================

def send_ticket_escalated_email(
    user: Any,
    ticket: Any
) -> bool:
    """
    Notify the customer that the issue was escalated.
    """

    if not _optional_email_allowed(
        user=user,
        preference_type="ticket_updates",
        email_type="ticket_escalated",
        ticket=ticket
    ):
        return True

    return send_email(
        recipient=user.email,
        subject=(
            f"Ticket #{ticket.number} Escalated "
            "to Human Support"
        ),
        email_type="ticket_escalated",
        text_template="email/ticket_escalated.txt",
        html_template="email/ticket_escalated.html",
        template_context={
            "user": user,
            "ticket": ticket
        },
        user_id=user.id,
        ticket_id=ticket.id
    )


# ============================================================
# SATISFACTION EMAIL
# ============================================================

def send_satisfaction_email(
    user: Any,
    ticket: Any
) -> bool:
    """
    Ask the customer to rate the completed support ticket.

    This uses satisfaction_emails instead of ticket_updates,
    allowing the customer to control rating invitations
    independently.
    """

    if not _optional_email_allowed(
        user=user,
        preference_type="satisfaction_emails",
        email_type="satisfaction_request",
        ticket=ticket
    ):
        return True

    return send_email(
        recipient=user.email,
        subject=(
            "Rate Your Support Experience - "
            f"Ticket #{ticket.number}"
        ),
        email_type="satisfaction_request",
        text_template="email/satisfaction_email.txt",
        html_template="email/satisfaction_email.html",
        template_context={
            "user": user,
            "ticket": ticket
        },
        user_id=user.id,
        ticket_id=ticket.id
    )


# ============================================================
# DELETED-TICKET EMAIL
# ============================================================

def send_ticket_deleted_email(
    user: Any,
    *,
    ticket_number: str,
    ticket_subject: str,
    deleted_by: Optional[str] = None,
    deleted_ticket_id: Optional[int] = None
) -> bool:
    """
    Notify the customer that a ticket was deleted.

    Important:
        Save the ticket values before deleting the Ticket row.

    The deleted Ticket object is not passed to the template because
    it may no longer exist after the database deletion.

    deleted_ticket_id is accepted for compatibility with existing
    route calls, but it is intentionally not saved to EmailLog.
    Saving a foreign key to a ticket that is about to be deleted can
    block deletion or create a foreign-key error.
    """

    if not _optional_email_allowed(
        user=user,
        preference_type="ticket_updates",
        email_type="ticket_deleted",
        ticket=None
    ):
        return True

    return send_email(
        recipient=user.email,
        subject=(
            f"Ticket #{ticket_number} Deleted"
        ),
        email_type="ticket_deleted",
        text_template="email/ticket_deleted.txt",
        html_template="email/ticket_deleted.html",
        template_context={
            "user": user,
            "ticket_number": ticket_number,
            "ticket_subject": ticket_subject,
            "deleted_by": deleted_by
        },
        user_id=user.id,

        # Deliberately do not store the deleted ticket FK.
        ticket_id=None
    )