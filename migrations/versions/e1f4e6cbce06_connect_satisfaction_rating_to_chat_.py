"""connect satisfaction rating to chat sessions

Revision ID: e1f4e6cbce06
Revises: f4035c233107
Create Date: 2026-07-09 14:42:52.719980
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "e1f4e6cbce06"
down_revision = "f4035c233107"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    columns = [col["name"] for col in inspector.get_columns("customer_satisfaction")]

    with op.batch_alter_table("customer_satisfaction") as batch_op:

        if "session_id" not in columns:
            batch_op.add_column(sa.Column("session_id", sa.Integer(), nullable=True))

        if "updated_at" not in columns:
            batch_op.add_column(sa.Column("updated_at", sa.DateTime(), nullable=True))

        batch_op.alter_column(
            "ticket_id",
            existing_type=mysql.INTEGER(),
            nullable=True
        )

    # Add FK only if it does not already exist
    fks = inspector.get_foreign_keys("customer_satisfaction")
    fk_exists = any(
        fk.get("referred_table") == "chat_sessions"
        and fk.get("constrained_columns") == ["session_id"]
        for fk in fks
    )

    if not fk_exists:
        with op.batch_alter_table("customer_satisfaction") as batch_op:
            batch_op.create_foreign_key(
                "fk_customer_satisfaction_session_id",
                "chat_sessions",
                ["session_id"],
                ["id"],
                ondelete="CASCADE"
            )


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    columns = [col["name"] for col in inspector.get_columns("customer_satisfaction")]

    fks = inspector.get_foreign_keys("customer_satisfaction")
    fk_exists = any(
        fk.get("name") == "fk_customer_satisfaction_session_id"
        for fk in fks
    )

    if fk_exists:
        with op.batch_alter_table("customer_satisfaction") as batch_op:
            batch_op.drop_constraint(
                "fk_customer_satisfaction_session_id",
                type_="foreignkey"
            )

    with op.batch_alter_table("customer_satisfaction") as batch_op:
        batch_op.alter_column(
            "ticket_id",
            existing_type=mysql.INTEGER(),
            nullable=False
        )

        if "updated_at" in columns:
            batch_op.drop_column("updated_at")

        if "session_id" in columns:
            batch_op.drop_column("session_id")