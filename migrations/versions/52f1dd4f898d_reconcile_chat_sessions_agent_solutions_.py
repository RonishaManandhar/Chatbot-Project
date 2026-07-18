"""
Reconcile chat sessions, agent solutions and email preferences.

This migration repairs differences between the existing MySQL
database and the current SQLAlchemy models.

It safely checks whether columns, indexes and foreign keys already
exist before attempting to create or replace them.

Revision ID: 52f1dd4f898d
Revises: 4ce28d3f54d6
"""

from alembic import op
import sqlalchemy as sa


# ============================================================
# ALEMBIC REVISION IDENTIFIERS
# ============================================================

revision = "52f1dd4f898d"
down_revision = "4ce28d3f54d6"
branch_labels = None
depends_on = None


# ============================================================
# DATABASE INSPECTION HELPERS
# ============================================================

def get_inspector():
    """
    Return a fresh SQLAlchemy database inspector.

    A fresh inspector is required after schema changes because
    SQLAlchemy inspectors can cache old database metadata.
    """

    return sa.inspect(op.get_bind())


def table_exists(table_name):
    inspector = get_inspector()

    return table_name in inspector.get_table_names()


def get_column_names(table_name):
    inspector = get_inspector()

    return {
        column["name"]
        for column in inspector.get_columns(table_name)
    }


def get_indexes(table_name):
    inspector = get_inspector()

    return inspector.get_indexes(table_name)


def get_unique_constraints(table_name):
    inspector = get_inspector()

    return inspector.get_unique_constraints(table_name)


def get_foreign_keys(table_name):
    inspector = get_inspector()

    return inspector.get_foreign_keys(table_name)


def index_name_exists(table_name, index_name):
    for index in get_indexes(table_name):
        if index.get("name") == index_name:
            return True

    return False


def index_columns_exist(
    table_name,
    column_names,
    unique=None
):
    """
    Check whether an index already exists for the supplied columns.

    The index name does not need to match.
    """

    expected_columns = tuple(column_names)

    for index in get_indexes(table_name):
        current_columns = tuple(
            index.get("column_names") or []
        )

        if current_columns != expected_columns:
            continue

        if unique is None:
            return True

        if bool(index.get("unique")) == bool(unique):
            return True

    return False


def unique_constraint_exists(
    table_name,
    constraint_name=None,
    column_names=None
):
    expected_columns = (
        tuple(column_names)
        if column_names
        else None
    )

    for constraint in get_unique_constraints(table_name):
        if (
            constraint_name
            and constraint.get("name") == constraint_name
        ):
            return True

        current_columns = tuple(
            constraint.get("column_names") or []
        )

        if (
            expected_columns
            and current_columns == expected_columns
        ):
            return True

    # MySQL often reports a UNIQUE constraint as an index.
    if expected_columns:
        return index_columns_exist(
            table_name,
            expected_columns,
            unique=True
        )

    return False


def foreign_key_matches(
    table_name,
    constrained_columns,
    referred_table,
    referred_columns,
    ondelete=None
):
    expected_constrained = tuple(constrained_columns)
    expected_referred = tuple(referred_columns)

    for foreign_key in get_foreign_keys(table_name):
        current_constrained = tuple(
            foreign_key.get("constrained_columns") or []
        )

        current_referred = tuple(
            foreign_key.get("referred_columns") or []
        )

        current_table = foreign_key.get("referred_table")

        if current_constrained != expected_constrained:
            continue

        if current_table != referred_table:
            continue

        if current_referred != expected_referred:
            continue

        if ondelete:
            options = foreign_key.get("options") or {}

            current_ondelete = str(
                options.get("ondelete") or ""
            ).upper()

            if current_ondelete != str(ondelete).upper():
                continue

        return True

    return False


def drop_foreign_keys_for_columns(
    table_name,
    constrained_columns
):
    """
    Drop every foreign key attached to the supplied local columns.

    This handles automatically generated MySQL names such as:
        agent_solutions_ibfk_2
        email_preferences_ibfk_1
    """

    expected_columns = tuple(constrained_columns)

    foreign_keys = get_foreign_keys(table_name)

    for foreign_key in foreign_keys:
        current_columns = tuple(
            foreign_key.get("constrained_columns") or []
        )

        constraint_name = foreign_key.get("name")

        if (
            current_columns == expected_columns
            and constraint_name
        ):
            op.drop_constraint(
                constraint_name,
                table_name,
                type_="foreignkey"
            )


def create_index_if_missing(
    index_name,
    table_name,
    column_names,
    unique=False
):
    """
    Create the required named index unless it already exists.
    """

    if index_name_exists(
        table_name,
        index_name
    ):
        return

    op.create_index(
        index_name,
        table_name,
        column_names,
        unique=unique
    )


def drop_index_if_exists(
    index_name,
    table_name
):
    if not index_name_exists(
        table_name,
        index_name
    ):
        return

    op.drop_index(
        index_name,
        table_name=table_name
    )


# ============================================================
# CHAT SESSION RECONCILIATION
# ============================================================

def reconcile_chat_sessions():
    if not table_exists("chat_sessions"):
        return

    columns = get_column_names(
        "chat_sessions"
    )

    # --------------------------------------------------------
    # ADD CURRENT_STAGE
    # --------------------------------------------------------

    if "current_stage" not in columns:
        op.add_column(
            "chat_sessions",
            sa.Column(
                "current_stage",
                sa.String(length=50),
                nullable=False,
                server_default="triage"
            )
        )

    # --------------------------------------------------------
    # ADD TRIAGE_STEP
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

    # --------------------------------------------------------
    # ADD TRIAGE_DATA
    # --------------------------------------------------------

    if "triage_data" not in columns:
        op.add_column(
            "chat_sessions",
            sa.Column(
                "triage_data",
                sa.Text(),
                nullable=False,
                server_default="{}"
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

    op.execute(
        sa.text(
            """
            UPDATE chat_sessions
            SET created_at = CURRENT_TIMESTAMP
            WHERE created_at IS NULL
            """
        )
    )

    op.execute(
        sa.text(
            """
            UPDATE chat_sessions
            SET updated_at = created_at
            WHERE updated_at IS NULL
            """
        )
    )

    # --------------------------------------------------------
    # ALIGN COLUMN NULLABILITY
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
        nullable=False,
        server_default=None
    )

    op.alter_column(
        "chat_sessions",
        "created_at",
        existing_type=sa.DateTime(),
        nullable=False
    )

    op.alter_column(
        "chat_sessions",
        "updated_at",
        existing_type=sa.DateTime(),
        nullable=False
    )

    # --------------------------------------------------------
    # CREATE REQUIRED INDEXES FIRST
    # --------------------------------------------------------

    create_index_if_missing(
        "idx_chat_sessions_user_id",
        "chat_sessions",
        ["user_id"]
    )

    create_index_if_missing(
        "idx_chat_sessions_ticket_id",
        "chat_sessions",
        ["ticket_id"]
    )

    create_index_if_missing(
        "idx_chat_sessions_user_stage",
        "chat_sessions",
        [
            "user_id",
            "current_stage"
        ]
    )

    create_index_if_missing(
        "idx_chat_sessions_user_updated",
        "chat_sessions",
        [
            "user_id",
            "updated_at"
        ]
    )

    # --------------------------------------------------------
    # ALIGN USER FOREIGN KEY
    # --------------------------------------------------------

    if not foreign_key_matches(
        "chat_sessions",
        ["user_id"],
        "users",
        ["id"],
        ondelete="CASCADE"
    ):
        drop_foreign_keys_for_columns(
            "chat_sessions",
            ["user_id"]
        )

        op.create_foreign_key(
            "fk_chat_sessions_user_id_users",
            "chat_sessions",
            "users",
            ["user_id"],
            ["id"],
            ondelete="CASCADE"
        )

    # --------------------------------------------------------
    # ALIGN TICKET FOREIGN KEY
    # --------------------------------------------------------

    if not foreign_key_matches(
        "chat_sessions",
        ["ticket_id"],
        "tickets",
        ["id"],
        ondelete="SET NULL"
    ):
        drop_foreign_keys_for_columns(
            "chat_sessions",
            ["ticket_id"]
        )

        op.create_foreign_key(
            "fk_chat_sessions_ticket_id_tickets",
            "chat_sessions",
            "tickets",
            ["ticket_id"],
            ["id"],
            ondelete="SET NULL"
        )

    # --------------------------------------------------------
    # REMOVE OLD AUTOMATIC INDEX NAMES
    # --------------------------------------------------------
    #
    # Required replacement indexes already exist, so removing
    # legacy indexes will not break MySQL foreign keys.
    # --------------------------------------------------------

    old_indexes = [
        "ix_chat_sessions_user_id",
        "ix_chat_sessions_ticket_id",
        "idx_chat_session_user_stage",
        "idx_chat_session_user_updated"
    ]

    for index_name in old_indexes:
        drop_index_if_exists(
            index_name,
            "chat_sessions"
        )


# ============================================================
# AGENT SOLUTION RECONCILIATION
# ============================================================

def reconcile_agent_solutions():
    if not table_exists("agent_solutions"):
        return

    columns = get_column_names(
        "agent_solutions"
    )

    # --------------------------------------------------------
    # ADD UPDATED_AT IF MISSING
    # --------------------------------------------------------

    if "updated_at" not in columns:
        op.add_column(
            "agent_solutions",
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text(
                    "CURRENT_TIMESTAMP"
                )
            )
        )

    # --------------------------------------------------------
    # BACKFILL REQUIRED COLUMNS
    # --------------------------------------------------------

    op.execute(
        sa.text(
            """
            UPDATE agent_solutions
            SET status = 'Pending'
            WHERE status IS NULL
               OR TRIM(status) = ''
            """
        )
    )

    op.execute(
        sa.text(
            """
            UPDATE agent_solutions
            SET view_count = 0
            WHERE view_count IS NULL
            """
        )
    )

    op.execute(
        sa.text(
            """
            UPDATE agent_solutions
            SET reuse_count = 0
            WHERE reuse_count IS NULL
            """
        )
    )

    op.execute(
        sa.text(
            """
            UPDATE agent_solutions
            SET created_at = CURRENT_TIMESTAMP
            WHERE created_at IS NULL
            """
        )
    )

    op.execute(
        sa.text(
            """
            UPDATE agent_solutions
            SET updated_at = created_at
            WHERE updated_at IS NULL
            """
        )
    )

    # --------------------------------------------------------
    # ALIGN REQUIRED COLUMN NULLABILITY
    # --------------------------------------------------------

    op.alter_column(
        "agent_solutions",
        "status",
        existing_type=sa.String(length=50),
        nullable=False
    )

    op.alter_column(
        "agent_solutions",
        "view_count",
        existing_type=sa.Integer(),
        nullable=False
    )

    op.alter_column(
        "agent_solutions",
        "reuse_count",
        existing_type=sa.Integer(),
        nullable=False
    )

    op.alter_column(
        "agent_solutions",
        "created_at",
        existing_type=sa.DateTime(),
        nullable=False
    )

    op.alter_column(
        "agent_solutions",
        "updated_at",
        existing_type=sa.DateTime(),
        nullable=False,
        server_default=None
    )

    # --------------------------------------------------------
    # CREATE REQUIRED INDEXES BEFORE REPLACING FOREIGN KEYS
    # --------------------------------------------------------

    create_index_if_missing(
        "idx_agent_solutions_ticket_id",
        "agent_solutions",
        ["ticket_id"]
    )

    create_index_if_missing(
        "idx_agent_solutions_category_id",
        "agent_solutions",
        ["category_id"]
    )

    create_index_if_missing(
        "idx_agent_solutions_submitted_by_id",
        "agent_solutions",
        ["submitted_by_id"]
    )

    create_index_if_missing(
        "idx_agent_solutions_status",
        "agent_solutions",
        ["status"]
    )

    # --------------------------------------------------------
    # ALIGN CATEGORY FOREIGN KEY
    # --------------------------------------------------------

    if not foreign_key_matches(
        "agent_solutions",
        ["category_id"],
        "categories",
        ["id"],
        ondelete="SET NULL"
    ):
        drop_foreign_keys_for_columns(
            "agent_solutions",
            ["category_id"]
        )

        op.create_foreign_key(
            "fk_agent_solutions_category_id_categories",
            "agent_solutions",
            "categories",
            ["category_id"],
            ["id"],
            ondelete="SET NULL"
        )

    # --------------------------------------------------------
    # ALIGN SUBMITTED-BY FOREIGN KEY
    # --------------------------------------------------------

    if not foreign_key_matches(
        "agent_solutions",
        ["submitted_by_id"],
        "users",
        ["id"],
        ondelete="SET NULL"
    ):
        drop_foreign_keys_for_columns(
            "agent_solutions",
            ["submitted_by_id"]
        )

        op.create_foreign_key(
            "fk_agent_solutions_submitted_by_id_users",
            "agent_solutions",
            "users",
            ["submitted_by_id"],
            ["id"],
            ondelete="SET NULL"
        )

    # --------------------------------------------------------
    # ALIGN TICKET FOREIGN KEY
    # --------------------------------------------------------

    if not foreign_key_matches(
        "agent_solutions",
        ["ticket_id"],
        "tickets",
        ["id"],
        ondelete="SET NULL"
    ):
        drop_foreign_keys_for_columns(
            "agent_solutions",
            ["ticket_id"]
        )

        op.create_foreign_key(
            "fk_agent_solutions_ticket_id_tickets",
            "agent_solutions",
            "tickets",
            ["ticket_id"],
            ["id"],
            ondelete="SET NULL"
        )

    # --------------------------------------------------------
    # REMOVE LEGACY INDEX NAMES
    # --------------------------------------------------------

    old_indexes = [
        "ticket_id",
        "ix_agent_solutions_ticket_id",
        "ix_agent_solutions_category_id",
        "ix_agent_solutions_submitted_by_id",
        "ix_agent_solutions_status"
    ]

    for index_name in old_indexes:
        drop_index_if_exists(
            index_name,
            "agent_solutions"
        )


# ============================================================
# EMAIL PREFERENCE RECONCILIATION
# ============================================================

def reconcile_email_preferences():
    if not table_exists("email_preferences"):
        op.create_table(
            "email_preferences",

            sa.Column(
                "id",
                sa.Integer(),
                primary_key=True
            ),

            sa.Column(
                "user_id",
                sa.Integer(),
                nullable=False
            ),

            sa.Column(
                "ticket_updates",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("1")
            ),

            sa.Column(
                "security_emails",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("1")
            ),

            sa.Column(
                "marketing_emails",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0")
            ),

            sa.Column(
                "satisfaction_emails",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("1")
            ),

            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text(
                    "CURRENT_TIMESTAMP"
                )
            ),

            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text(
                    "CURRENT_TIMESTAMP"
                )
            ),

            sa.ForeignKeyConstraint(
                ["user_id"],
                ["users.id"],
                name=(
                    "fk_email_preferences_"
                    "user_id_users"
                ),
                ondelete="CASCADE"
            ),

            sa.UniqueConstraint(
                "user_id",
                name=(
                    "uq_email_preferences_"
                    "user_id"
                )
            )
        )

        return

    columns = get_column_names(
        "email_preferences"
    )

    # --------------------------------------------------------
    # ADD UPDATED_AT IF MISSING
    # --------------------------------------------------------

    if "updated_at" not in columns:
        op.add_column(
            "email_preferences",
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text(
                    "CURRENT_TIMESTAMP"
                )
            )
        )

    # --------------------------------------------------------
    # ADD ANY OTHER MISSING COLUMNS
    # --------------------------------------------------------

    columns = get_column_names(
        "email_preferences"
    )

    if "ticket_updates" not in columns:
        op.add_column(
            "email_preferences",
            sa.Column(
                "ticket_updates",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("1")
            )
        )

    if "security_emails" not in columns:
        op.add_column(
            "email_preferences",
            sa.Column(
                "security_emails",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("1")
            )
        )

    if "marketing_emails" not in columns:
        op.add_column(
            "email_preferences",
            sa.Column(
                "marketing_emails",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0")
            )
        )

    if "satisfaction_emails" not in columns:
        op.add_column(
            "email_preferences",
            sa.Column(
                "satisfaction_emails",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("1")
            )
        )

    # --------------------------------------------------------
    # REMOVE DUPLICATE USER PREFERENCE ROWS
    # --------------------------------------------------------
    #
    # Keep the oldest row for each customer before creating the
    # one-row-per-user unique constraint.
    # --------------------------------------------------------

    op.execute(
        sa.text(
            """
            DELETE duplicate_preference
            FROM email_preferences duplicate_preference
            INNER JOIN email_preferences original_preference
                ON duplicate_preference.user_id =
                   original_preference.user_id
               AND duplicate_preference.id >
                   original_preference.id
            """
        )
    )

    # --------------------------------------------------------
    # BACKFILL NULL VALUES
    # --------------------------------------------------------

    op.execute(
        sa.text(
            """
            UPDATE email_preferences
            SET ticket_updates = 1
            WHERE ticket_updates IS NULL
            """
        )
    )

    op.execute(
        sa.text(
            """
            UPDATE email_preferences
            SET security_emails = 1
            WHERE security_emails IS NULL
            """
        )
    )

    op.execute(
        sa.text(
            """
            UPDATE email_preferences
            SET marketing_emails = 0
            WHERE marketing_emails IS NULL
            """
        )
    )

    op.execute(
        sa.text(
            """
            UPDATE email_preferences
            SET satisfaction_emails = 1
            WHERE satisfaction_emails IS NULL
            """
        )
    )

    op.execute(
        sa.text(
            """
            UPDATE email_preferences
            SET created_at = CURRENT_TIMESTAMP
            WHERE created_at IS NULL
            """
        )
    )

    op.execute(
        sa.text(
            """
            UPDATE email_preferences
            SET updated_at = created_at
            WHERE updated_at IS NULL
            """
        )
    )

    # --------------------------------------------------------
    # ALIGN NULLABILITY
    # --------------------------------------------------------

    op.alter_column(
        "email_preferences",
        "user_id",
        existing_type=sa.Integer(),
        nullable=False
    )

    op.alter_column(
        "email_preferences",
        "ticket_updates",
        existing_type=sa.Boolean(),
        nullable=False,
        server_default=None
    )

    op.alter_column(
        "email_preferences",
        "security_emails",
        existing_type=sa.Boolean(),
        nullable=False,
        server_default=None
    )

    op.alter_column(
        "email_preferences",
        "marketing_emails",
        existing_type=sa.Boolean(),
        nullable=False,
        server_default=None
    )

    op.alter_column(
        "email_preferences",
        "satisfaction_emails",
        existing_type=sa.Boolean(),
        nullable=False,
        server_default=None
    )

    op.alter_column(
        "email_preferences",
        "created_at",
        existing_type=sa.DateTime(),
        nullable=False
    )

    op.alter_column(
        "email_preferences",
        "updated_at",
        existing_type=sa.DateTime(),
        nullable=False,
        server_default=None
    )

    # --------------------------------------------------------
    # CREATE REQUIRED UNIQUE CONSTRAINT
    # --------------------------------------------------------

    if not unique_constraint_exists(
        "email_preferences",
        constraint_name=(
            "uq_email_preferences_user_id"
        ),
        column_names=["user_id"]
    ):
        op.create_unique_constraint(
            "uq_email_preferences_user_id",
            "email_preferences",
            ["user_id"]
        )

    # --------------------------------------------------------
    # ALIGN USER FOREIGN KEY
    # --------------------------------------------------------

    if not foreign_key_matches(
        "email_preferences",
        ["user_id"],
        "users",
        ["id"],
        ondelete="CASCADE"
    ):
        drop_foreign_keys_for_columns(
            "email_preferences",
            ["user_id"]
        )

        op.create_foreign_key(
            "fk_email_preferences_user_id_users",
            "email_preferences",
            "users",
            ["user_id"],
            ["id"],
            ondelete="CASCADE"
        )

    # --------------------------------------------------------
    # REMOVE LEGACY UNIQUE INDEX NAME
    # --------------------------------------------------------
    #
    # Only remove it when the new required unique constraint
    # exists under the correct model name.
    # --------------------------------------------------------

    if unique_constraint_exists(
        "email_preferences",
        constraint_name=(
            "uq_email_preferences_user_id"
        ),
        column_names=["user_id"]
    ):
        legacy_indexes = [
            "idx_email_preference_user",
            "ix_email_preferences_user_id"
        ]

        for index_name in legacy_indexes:
            drop_index_if_exists(
                index_name,
                "email_preferences"
            )


# ============================================================
# UPGRADE
# ============================================================

def upgrade():
    reconcile_chat_sessions()
    reconcile_agent_solutions()
    reconcile_email_preferences()


# ============================================================
# DOWNGRADE
# ============================================================

def downgrade():
    """
    This is a database-reconciliation migration.

    It intentionally does not destructively remove repaired
    columns, customer preference records or working foreign keys.
    """

    pass