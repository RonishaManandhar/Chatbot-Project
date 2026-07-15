from flask_login import current_user
from flask_socketio import emit, join_room

from app.models import Ticket
from app.socketio_ext import socketio


@socketio.on("join_ticket_room")
def join_ticket_room(data):
    """Allow an authenticated user to join a ticket-specific room."""
    try:
        if not current_user.is_authenticated:
            emit("ticket_room_joined", {"ok": False, "reason": "not_authenticated"})
            return

        data = data or {}
        raw_ticket_id = data.get("ticket_id")

        try:
            ticket_id = int(raw_ticket_id)
        except (TypeError, ValueError):
            emit("ticket_room_joined", {"ok": False, "reason": "invalid_ticket_id"})
            return

        ticket = db_ticket = Ticket.query.get(ticket_id)
        if not ticket:
            emit("ticket_room_joined", {"ok": False, "reason": "ticket_not_found"})
            return

        role = (current_user.role or "").strip().lower()

        if role == "customer":
            allowed = ticket.author_id == current_user.id
        elif role == "agent":
            allowed = ticket.owner_id in (None, current_user.id) or ticket.author_id == current_user.id
        elif role == "administrator":
            allowed = True
        else:
            allowed = False

        if not allowed:
            emit("ticket_room_joined", {
                "ok": False,
                "reason": "forbidden",
                "ticket_id": ticket.id
            })
            return

        room = f"ticket_{ticket.id}"
        join_room(room)

        emit("ticket_room_joined", {
            "ok": True,
            "ticket_id": ticket.id,
            "room": room
        })

        print(
            f"SOCKET JOINED: user={current_user.id}, "
            f"role={current_user.role}, room={room}"
        )

    except Exception as error:
        print("JOIN TICKET ROOM ERROR:", error)
        emit("ticket_room_joined", {"ok": False, "reason": "server_error"})


@socketio.on(
    "join_notification_room"
)
def join_notification_room(data):

    try:

        if not current_user.is_authenticated:
            return

        room = (
            f"user_{current_user.id}"
        )

        join_room(room)

        emit(
            "notification_room_joined",
            {
                "ok": True,
                "room": room,
                "user_id": current_user.id
            }
        )

        print(
            "NOTIFICATION ROOM JOINED:",
            room
        )

    except Exception as e:

        print(
            "JOIN NOTIFICATION ROOM ERROR:",
            e
        )
