"""Email Preferences

Revision ID: 7059fd291ec8
Revises: 1c09e7135e26
Create Date: 2026-07-12 17:18:52.406892
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "7059fd291ec8"
down_revision = "1c09e7135e26"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "email_preferences",

        sa.Column(
            "id",
            sa.Integer(),
            nullable=False
        ),

        sa.Column(
            "user_id",
            sa.Integer(),
            nullable=True
        ),

        sa.Column(
            "ticket_updates",
            sa.Boolean(),
            nullable=True
        ),

        sa.Column(
            "security_emails",
            sa.Boolean(),
            nullable=True
        ),

        sa.Column(
            "marketing_emails",
            sa.Boolean(),
            nullable=True
        ),

        sa.Column(
            "satisfaction_emails",
            sa.Boolean(),
            nullable=True
        ),

        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=True
        ),

        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"]
        ),

        sa.PrimaryKeyConstraint(
            "id"
        )
    )


def downgrade():
    op.drop_table(
        "email_preferences"
    )