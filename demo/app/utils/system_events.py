from flask import (
    current_app
)
from flask_login import (
    current_user
)

from app.exts import db
from app.models import SystemEvent


def log_system_event(
    event_type,
    message,
    severity="Info",
    user_id=None,
    ticket_id=None
):
    try:
        resolved_user_id = (
            user_id
        )

        if (
            resolved_user_id is None
            and current_user.is_authenticated
        ):
            resolved_user_id = (
                current_user.id
            )

        event = SystemEvent(
            event_type=event_type,
            severity=severity,
            message=message,
            user_id=resolved_user_id,
            related_ticket_id=ticket_id
        )

        db.session.add(
            event
        )

        db.session.commit()

        return event

    except Exception:
        db.session.rollback()

        current_app.logger.exception(
            "System event logging failed."
        )

        return None