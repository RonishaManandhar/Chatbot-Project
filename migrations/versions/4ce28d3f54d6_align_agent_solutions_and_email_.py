

from alembic import op
import sqlalchemy as sa


# ============================================================
# ALEMBIC REVISION IDENTIFIERS
# ============================================================

revision = "4ce28d3f54d6"
down_revision = "3ed5d0056ee6"
branch_labels = None
depends_on = None


# ============================================================
# INSPECTION HELPERS
# ============================================================

def get_column_names(table_name):
    connection = op.get_bind()
    inspector = sa.inspect(connection)

    return {
        column["name"]
        for column in inspector.get_columns(table_name)
    }


def get_index_names(table_name):
    connection = op.get_bind()
    inspector = sa.inspect(connection)

    return {
        index["name"]
        for index in inspector.get_indexes(table_name)
        if index.get("name")
    }


def get_unique_constraint_names(table_name):
    connection = op.get_bind()
    inspector = sa.inspect(connection)

    return {
        constraint["name"]
        for constraint in inspector.get_unique_constraints(
            table_name
        )
        if constraint.get("name")
    }


def get_unique_constraint_columns(table_name):
    connection = op.get_bind()
    inspector = sa.inspect(connection)

    return {
        tuple(constraint.get("column_names") or [])
        for constraint in inspector.get_unique_constraints(
            table_name
        )
    }


# ============================================================
# UPGRADE
# ============================================================

def upgrade():
    # ========================================================
    # AGENT_SOLUTIONS
    # ========================================================

    agent_solution_columns = get_column_names(
        "agent_solutions"
    )

    # --------------------------------------------------------
    # ADD UPDATED_AT
    # --------------------------------------------------------

    if "updated_at" not in agent_solution_columns:
        op.add_column(
            "agent_solutions",
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=True
            )
        )

        op.execute(
            sa.text(
                """
                UPDATE agent_solutions
                SET updated_at =
                    COALESCE(created_at, CURRENT_TIMESTAMP)
                WHERE updated_at IS NULL
                """
            )
        )

        op.alter_column(
            "agent_solutions",
            "updated_at",
            existing_type=sa.DateTime(),
            nullable=False
        )

    # --------------------------------------------------------
    # BACKFILL EXISTING NULL VALUES
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

    # --------------------------------------------------------
    # FINAL AGENT_SOLUTION COLUMN DEFINITIONS
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

    # --------------------------------------------------------
    # AGENT_SOLUTION INDEXES
    # --------------------------------------------------------

    agent_solution_indexes = get_index_names(
        "agent_solutions"
    )

    # Never drop this index. MySQL requires it for the ticket
    # foreign-key constraint.
    if "ticket_id" not in agent_solution_indexes:
        op.create_index(
            "ticket_id",
            "agent_solutions",
            ["ticket_id"],
            unique=False
        )

    agent_solution_indexes = get_index_names(
        "agent_solutions"
    )

    if (
        "ix_agent_solutions_category_id"
        not in agent_solution_indexes
    ):
        op.create_index(
            "ix_agent_solutions_category_id",
            "agent_solutions",
            ["category_id"],
            unique=False
        )

    agent_solution_indexes = get_index_names(
        "agent_solutions"
    )

    if (
        "ix_agent_solutions_submitted_by_id"
        not in agent_solution_indexes
    ):
        op.create_index(
            "ix_agent_solutions_submitted_by_id",
            "agent_solutions",
            ["submitted_by_id"],
            unique=False
        )

    agent_solution_indexes = get_index_names(
        "agent_solutions"
    )

    if (
        "ix_agent_solutions_status"
        not in agent_solution_indexes
    ):
        op.create_index(
            "ix_agent_solutions_status",
            "agent_solutions",
            ["status"],
            unique=False
        )

    # ========================================================
    # EMAIL_PREFERENCES
    # ========================================================

    email_preference_columns = get_column_names(
        "email_preferences"
    )

    # --------------------------------------------------------
    # ADD UPDATED_AT
    # --------------------------------------------------------

    if "updated_at" not in email_preference_columns:
        op.add_column(
            "email_preferences",
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=True
            )
        )

        op.execute(
            sa.text(
                """
                UPDATE email_preferences
                SET updated_at =
                    COALESCE(created_at, CURRENT_TIMESTAMP)
                WHERE updated_at IS NULL
                """
            )
        )

        op.alter_column(
            "email_preferences",
            "updated_at",
            existing_type=sa.DateTime(),
            nullable=False
        )

    # --------------------------------------------------------
    # REMOVE DUPLICATE USER PREFERENCE ROWS
    # --------------------------------------------------------
    #
    # Keep the oldest row for every user before adding the
    # unique user_id constraint.
    # --------------------------------------------------------

    op.execute(
        sa.text(
            """
            DELETE duplicate_preference
            FROM email_preferences AS duplicate_preference
            INNER JOIN email_preferences AS retained_preference
                ON duplicate_preference.user_id =
                   retained_preference.user_id
               AND duplicate_preference.id >
                   retained_preference.id
            WHERE duplicate_preference.user_id IS NOT NULL
            """
        )
    )

    # --------------------------------------------------------
    # REMOVE INVALID NULL USER ROWS
    # --------------------------------------------------------

    op.execute(
        sa.text(
            """
            DELETE FROM email_preferences
            WHERE user_id IS NULL
            """
        )
    )

    # --------------------------------------------------------
    # BACKFILL NULL PREFERENCE VALUES
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

    # --------------------------------------------------------
    # FINAL EMAIL_PREFERENCE DEFINITIONS
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
        nullable=False
    )

    op.alter_column(
        "email_preferences",
        "security_emails",
        existing_type=sa.Boolean(),
        nullable=False
    )

    op.alter_column(
        "email_preferences",
        "marketing_emails",
        existing_type=sa.Boolean(),
        nullable=False
    )

    op.alter_column(
        "email_preferences",
        "satisfaction_emails",
        existing_type=sa.Boolean(),
        nullable=False
    )

    op.alter_column(
        "email_preferences",
        "created_at",
        existing_type=sa.DateTime(),
        nullable=False
    )

    # --------------------------------------------------------
    # EMAIL_PREFERENCE LOOKUP INDEX
    # --------------------------------------------------------

    email_preference_indexes = get_index_names(
        "email_preferences"
    )

    if (
        "idx_email_preference_user"
        not in email_preference_indexes
    ):
        op.create_index(
            "idx_email_preference_user",
            "email_preferences",
            ["user_id"],
            unique=False
        )

    # --------------------------------------------------------
    # ONE EMAIL PREFERENCE ROW PER USER
    # --------------------------------------------------------

    unique_column_sets = get_unique_constraint_columns(
        "email_preferences"
    )

    if ("user_id",) not in unique_column_sets:
        op.create_unique_constraint(
            "uq_email_preferences_user_id",
            "email_preferences",
            ["user_id"]
        )


# ============================================================
# DOWNGRADE
# ============================================================

def downgrade():
    # ========================================================
    # EMAIL_PREFERENCES
    # ========================================================

    email_preference_unique_names = (
        get_unique_constraint_names(
            "email_preferences"
        )
    )

    if (
        "uq_email_preferences_user_id"
        in email_preference_unique_names
    ):
        op.drop_constraint(
            "uq_email_preferences_user_id",
            "email_preferences",
            type_="unique"
        )

    email_preference_indexes = get_index_names(
        "email_preferences"
    )

    if (
        "idx_email_preference_user"
        in email_preference_indexes
    ):
        op.drop_index(
            "idx_email_preference_user",
            table_name="email_preferences"
        )

    email_preference_columns = get_column_names(
        "email_preferences"
    )

    if "updated_at" in email_preference_columns:
        op.drop_column(
            "email_preferences",
            "updated_at"
        )

    # ========================================================
    # AGENT_SOLUTIONS
    # ========================================================

    agent_solution_indexes = get_index_names(
        "agent_solutions"
    )

    if (
        "ix_agent_solutions_status"
        in agent_solution_indexes
    ):
        op.drop_index(
            "ix_agent_solutions_status",
            table_name="agent_solutions"
        )

    agent_solution_indexes = get_index_names(
        "agent_solutions"
    )

    if (
        "ix_agent_solutions_submitted_by_id"
        in agent_solution_indexes
    ):
        op.drop_index(
            "ix_agent_solutions_submitted_by_id",
            table_name="agent_solutions"
        )

    agent_solution_indexes = get_index_names(
        "agent_solutions"
    )

    if (
        "ix_agent_solutions_category_id"
        in agent_solution_indexes
    ):
        op.drop_index(
            "ix_agent_solutions_category_id",
            table_name="agent_solutions"
        )

    # Deliberately do not drop agent_solutions.ticket_id.
    # MySQL requires it for the ticket_id foreign key.

    agent_solution_columns = get_column_names(
        "agent_solutions"
    )

    if "updated_at" in agent_solution_columns:
        op.drop_column(
            "agent_solutions",
            "updated_at"
        )