"""add persistent chat session state

Revision ID: 3ed5d0056ee6
Revises: 7059fd291ec8
Create Date: 2026-07-12 19:26:31.481671
"""

from alembic import op
import sqlalchemy as sa


# ============================================================
# ALEMBIC REVISION IDENTIFIERS
# ============================================================

revision = "3ed5d0056ee6"
down_revision = "7059fd291ec8"
branch_labels = None
depends_on = None


# ============================================================
# DATABASE INSPECTION HELPERS
# ============================================================

def get_column_names(table_name):
    """
    Return all existing column names for the specified table.
    """

    connection = op.get_bind()
    inspector = sa.inspect(connection)

    return {
        column["name"]
        for column in inspector.get_columns(table_name)
    }


def get_index_names(table_name):
    """
    Return all existing index names for the specified table.
    """

    connection = op.get_bind()
    inspector = sa.inspect(connection)

    return {
        index["name"]
        for index in inspector.get_indexes(table_name)
        if index.get("name")
    }


# ============================================================
# UPGRADE
# ============================================================

def upgrade():
    """
    Recover from a partially completed MySQL migration and add
    persistent workflow state to chat_sessions.

    This migration safely handles these situations:

    - current_stage was already added;
    - triage_step was already added;
    - triage_data was not added because MySQL rejected its
      TEXT default value;
    - some indexes already exist;
    - the migration is being rerun after partial failure.
    """

    # --------------------------------------------------------
    # READ CURRENT CHAT_SESSION COLUMNS
    # --------------------------------------------------------

    columns = get_column_names("chat_sessions")

    # --------------------------------------------------------
    # ADD CURRENT_STAGE ONLY WHEN MISSING
    # --------------------------------------------------------

    if "current_stage" not in columns:
        op.add_column(
            "chat_sessions",
            sa.Column(
                "current_stage",
                sa.String(length=50),
                nullable=False,
                server_default=sa.text("'triage'")
            )
        )

    # Refresh existing columns after schema change.
    columns = get_column_names("chat_sessions")

    # --------------------------------------------------------
    # ADD TRIAGE_STEP ONLY WHEN MISSING
    # --------------------------------------------------------

    if "triage_step" not in columns:
        op.add_column(
            "chat_sessions",
            sa.Column(
                "triage_step",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0")
            )
        )

    # Refresh existing columns after schema change.
    columns = get_column_names("chat_sessions")

    # --------------------------------------------------------
    # ADD TRIAGE_DATA ONLY WHEN MISSING
    # --------------------------------------------------------
    #
    # Important:
    #
    # MySQL must not receive:
    #
    #     TEXT NOT NULL DEFAULT '{}'
    #
    # Therefore it is first added as nullable.
    # --------------------------------------------------------

    if "triage_data" not in columns:
        op.add_column(
            "chat_sessions",
            sa.Column(
                "triage_data",
                sa.Text(),
                nullable=True
            )
        )

    # --------------------------------------------------------
    # BACKFILL EXISTING ROWS
    # --------------------------------------------------------

    op.execute(
        sa.text(
            """
            UPDATE chat_sessions
            SET current_stage = 'triage'
            WHERE current_stage IS NULL
               OR TRIM(current_stage) = ''
            """
        )
    )

    op.execute(
        sa.text(
            """
            UPDATE chat_sessions
            SET triage_step = 0
            WHERE triage_step IS NULL
            """
        )
    )

    op.execute(
        sa.text(
            """
            UPDATE chat_sessions
            SET triage_data = '{}'
            WHERE triage_data IS NULL
               OR TRIM(triage_data) = ''
            """
        )
    )

    # --------------------------------------------------------
    # ENSURE FINAL COLUMN DEFINITIONS
    # --------------------------------------------------------

    op.alter_column(
        "chat_sessions",
        "current_stage",
        existing_type=sa.String(length=50),
        nullable=False,
        server_default=None
    )

    op.alter_column(
        "chat_sessions",
        "triage_step",
        existing_type=sa.Integer(),
        nullable=False,
        server_default=None
    )

    op.alter_column(
        "chat_sessions",
        "triage_data",
        existing_type=sa.Text(),
        nullable=False
    )

    # --------------------------------------------------------
    # CREATE INDEXES ONLY WHEN MISSING
    # --------------------------------------------------------

    indexes = get_index_names("chat_sessions")

    if "idx_chat_session_user_stage" not in indexes:
        op.create_index(
            "idx_chat_session_user_stage",
            "chat_sessions",
            [
                "user_id",
                "current_stage"
            ],
            unique=False
        )

    indexes = get_index_names("chat_sessions")

    if "idx_chat_session_user_updated" not in indexes:
        op.create_index(
            "idx_chat_session_user_updated",
            "chat_sessions",
            [
                "user_id",
                "updated_at"
            ],
            unique=False
        )

    indexes = get_index_names("chat_sessions")

    if "ix_chat_sessions_ticket_id" not in indexes:
        op.create_index(
            "ix_chat_sessions_ticket_id",
            "chat_sessions",
            [
                "ticket_id"
            ],
            unique=False
        )

    indexes = get_index_names("chat_sessions")

    if "ix_chat_sessions_user_id" not in indexes:
        op.create_index(
            "ix_chat_sessions_user_id",
            "chat_sessions",
            [
                "user_id"
            ],
            unique=False
        )


# ============================================================
# DOWNGRADE
# ============================================================

def downgrade():
    """
    Remove persistent chat-session state safely.

    The downgrade also checks whether indexes and columns exist
    before attempting to remove them.
    """

    # --------------------------------------------------------
    # DROP INDEXES WHEN PRESENT
    # --------------------------------------------------------

    indexes = get_index_names("chat_sessions")

    if "ix_chat_sessions_user_id" in indexes:
        op.drop_index(
            "ix_chat_sessions_user_id",
            table_name="chat_sessions"
        )

    indexes = get_index_names("chat_sessions")

    if "ix_chat_sessions_ticket_id" in indexes:
        op.drop_index(
            "ix_chat_sessions_ticket_id",
            table_name="chat_sessions"
        )

    indexes = get_index_names("chat_sessions")

    if "idx_chat_session_user_updated" in indexes:
        op.drop_index(
            "idx_chat_session_user_updated",
            table_name="chat_sessions"
        )

    indexes = get_index_names("chat_sessions")

    if "idx_chat_session_user_stage" in indexes:
        op.drop_index(
            "idx_chat_session_user_stage",
            table_name="chat_sessions"
        )

    # --------------------------------------------------------
    # DROP COLUMNS WHEN PRESENT
    # --------------------------------------------------------

    columns = get_column_names("chat_sessions")

    if "triage_data" in columns:
        op.drop_column(
            "chat_sessions",
            "triage_data"
        )

    columns = get_column_names("chat_sessions")

    if "triage_step" in columns:
        op.drop_column(
            "chat_sessions",
            "triage_step"
        )

    columns = get_column_names("chat_sessions")

    if "current_stage" in columns:
        op.drop_column(
            "chat_sessions",
            "current_stage"
        )