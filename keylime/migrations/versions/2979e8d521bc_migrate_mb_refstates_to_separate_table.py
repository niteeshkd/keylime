"""migrate mb_refstates to separate table

Revision ID: 2979e8d521bc
Revises: 3be092cd2635
Create Date: 2023-10-24 03:25:54.500601

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "2979e8d521bc"
down_revision = "3be092cd2635"
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
    # Migrate existing agent info to the mbrefstates table.
    conn = op.get_bind()
    meta = sa.MetaData()
    meta.reflect(bind=conn, only=("verifiermain", "mbrefstates"))
    verifiermain = meta.tables["verifiermain"]
    mbrefstates = meta.tables["mbrefstates"]

    # Get agent_id and mb_refstate from verifiermain
    res = conn.execute(sa.text("SELECT agent_id, mb_refstate FROM verifiermain"))
    results = res.fetchall()
    old_policy = [{"name": r[0], "mb_refstate": r[1]} for r in results]

    # Add name and mb_refstate columns to mbrefstates
    op.bulk_insert(mbrefstates, old_policy)

    # Modify verifiermain table (i.e. add mb_refstate_id and remove mb_refstate)
    with op.batch_alter_table("verifiermain") as batch_op:
        batch_op.add_column(
            sa.Column(
                "mb_refstate_id", sa.Integer(), sa.ForeignKey("mbrefstates.id", name="fk_verifiermain_mbrefstates")
            )
        )
        batch_op.drop_column("mb_refstate")

    # Get id and name from mbrefstates
    res2 = conn.execute(sa.text("SELECT id, name FROM mbrefstates"))
    results2 = res.fetchall()

    # Update mb_refstate_id of verifiermain with the id of "mbrefstates"
    for mbrefstates_id, name in results2:
        conn.execute(
            verifiermain.update().where(verifiermain.c.agent_id == name).values(**{"mb_refstate_id": mbrefstates_id})
        )


def downgrade_cloud_verifier():
    # Migrate existing agent info back to the mb_refstate column in verifiermain.
    conn = op.get_bind()
    meta = sa.MetaData()
    meta.reflect(bind=conn, only=("verifiermain", "mbrefstates"))
    verifiermain = meta.tables["verifiermain"]
    mbrefstates = meta.tables["mbrefstates"]

    # Get name and mb_refstate from mbrefstates
    res = conn.execute(sa.text("SELECT name, mb_refstate FROM mbrefstates"))
    results = res.fetchall()

    # Add mb_refstate column back to verifierman
    with op.batch_alter_table("verifiermain") as batch_op:
        batch_op.add_column(
            sa.Column("mb_refstate", sa.Text().with_variant(sa.Text(length=429400000), "mysql"), nullable=True)
        )

    # Put mb_refstate back to "verifiermain" and delete it from the "mbrefstates" database
    for name, mb_refstate in results:
        conn.execute(
            verifiermain.update().where(verifiermain.c.agent_id == name).values(**{"mb_refstate": mb_refstate})
        )
        conn.execute(mbrefstates.delete().where(mbrefstates.c.name == name))

    # Drop mb_refstate_id column from "verifiermain"
    with op.batch_alter_table("verifiermain") as batch_op:
        batch_op.drop_column("mb_refstate_id")
