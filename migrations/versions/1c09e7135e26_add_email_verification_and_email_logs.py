"""add email verification and email logs

Revision ID: 1c09e7135e26
Revises: e1f4e6cbce06
Create Date: 2026-07-11 15:02:22.254374
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "1c09e7135e26"
down_revision = "e1f4e6cbce06"
branch_labels = None
depends_on = None


def upgrade():

    # -------------------------------------------------
    # EMAIL VERIFICATION TABLE
    # -------------------------------------------------
    op.create_table(
        "email_verification_codes",

        sa.Column("id", sa.Integer(), primary_key=True),

        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey(
                "users.id",
                ondelete="CASCADE"
            ),
            nullable=False
        ),

        sa.Column(
            "code_hash",
            sa.String(255),
            nullable=False
        ),

        sa.Column(
            "purpose",
            sa.String(50),
            nullable=False
        ),

        sa.Column(
            "expires_at",
            sa.DateTime(),
            nullable=False
        ),

        sa.Column(
            "used",
            sa.Boolean(),
            nullable=False,
            server_default="0"
        ),

        sa.Column(
            "attempts",
            sa.Integer(),
            nullable=False,
            server_default="0"
        ),

        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False
        ),

        sa.Column(
            "used_at",
            sa.DateTime(),
            nullable=True
        )
    )

    op.create_index(
        "idx_email_code_user_purpose",
        "email_verification_codes",
        ["user_id", "purpose"]
    )

    # -------------------------------------------------
    # EMAIL LOG TABLE
    # -------------------------------------------------
    op.create_table(
        "email_logs",

        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True
        ),

        sa.Column(
            "recipient",
            sa.String(255),
            nullable=False
        ),

        sa.Column(
            "subject",
            sa.String(255),
            nullable=False
        ),

        sa.Column(
            "email_type",
            sa.String(80),
            nullable=False
        ),

        sa.Column(
            "status",
            sa.String(30),
            nullable=False
        ),

        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey(
                "users.id",
                ondelete="SET NULL"
            ),
            nullable=True
        ),

        sa.Column(
            "ticket_id",
            sa.Integer(),
            sa.ForeignKey(
                "tickets.id",
                ondelete="SET NULL"
            ),
            nullable=True
        ),

        sa.Column(
            "error_message",
            sa.Text(),
            nullable=True
        ),

        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False
        ),

        sa.Column(
            "sent_at",
            sa.DateTime(),
            nullable=True
        )
    )

    op.create_index(
        "idx_email_log_created",
        "email_logs",
        ["created_at"]
    )

    op.create_index(
        "idx_email_log_status",
        "email_logs",
        ["status"]
    )

    op.create_index(
        "idx_email_log_ticket",
        "email_logs",
        ["ticket_id"]
    )

    # -------------------------------------------------
    # USERS TABLE
    # -------------------------------------------------

    with op.batch_alter_table("users") as batch_op:

        batch_op.add_column(
            sa.Column(
                "email_verified",
                sa.Boolean(),
                nullable=False,
                server_default="0"
            )
        )

        batch_op.add_column(
            sa.Column(
                "email_verified_at",
                sa.DateTime(),
                nullable=True
            )
        )

    # -------------------------------------------------
    # CUSTOMER SATISFACTION
    # -------------------------------------------------

    try:
        with op.batch_alter_table(
                "customer_satisfaction"
        ) as batch_op:

            batch_op.create_unique_constraint(
                "uq_session_customer_rating",
                [
                    "session_id",
                    "customer_id"
                ]
            )

    except:
        pass


def downgrade():

    # CUSTOMER SATISFACTION
    try:
        with op.batch_alter_table(
                "customer_satisfaction"
        ) as batch_op:

            batch_op.drop_constraint(
                "uq_session_customer_rating",
                type_="unique"
            )

    except:
        pass

    # USERS
    try:
        with op.batch_alter_table("users") as batch_op:

            batch_op.drop_column(
                "email_verified_at"
            )

            batch_op.drop_column(
                "email_verified"
            )

    except:
        pass

    # EMAIL LOG INDEXES
    try:
        op.drop_index(
            "idx_email_log_ticket",
            table_name="email_logs"
        )
    except:
        pass

    try:
        op.drop_index(
            "idx_email_log_status",
            table_name="email_logs"
        )
    except:
        pass

    try:
        op.drop_index(
            "idx_email_log_created",
            table_name="email_logs"
        )
    except:
        pass

    try:
        op.drop_table("email_logs")
    except:
        pass

    try:
        op.drop_index(
            "idx_email_code_user_purpose",
            table_name="email_verification_codes"
        )
    except:
        pass

    try:
        op.drop_table(
            "email_verification_codes"
        )
    except:
        pass