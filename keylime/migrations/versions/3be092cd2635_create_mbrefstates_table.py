"""add mb refstate id

Revision ID: 3be092cd2635
Revises: 21b5cb88fcdb
Create Date: 2023-10-11 17:25:15.737956

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "3be092cd2635"
down_revision = "21b5cb88fcdb"
branch_labels = None
depends_on = None


def upgrade(engine_name):
    globals()[f"upgrade_{engine_name}"]()


def downgrade(engine_name):
    globals()[f"downgrade_{engine_name}"]()


def upgrade_registrar():
    pass


def downgrade_registrar():
    pass


def upgrade_cloud_verifier():
    op.create_table(
        "mbrefstates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("checksum", sa.String(128), nullable=True),
        sa.Column("mb_refstate", sa.Text().with_variant(sa.Text(length=429400000), "mysql"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uniq_mbrefstates0name"),
        mysql_engine="InnoDB",
        mysql_charset="UTF8",
    )


def downgrade_cloud_verifier():
    op.drop_table("mbrefstates")
