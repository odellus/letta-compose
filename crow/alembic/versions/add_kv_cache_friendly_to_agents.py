"""add kv_cache_friendly to agents table

Revision ID: add_kv_cache_friendly
Revises: d0880aae6cee
Create Date: 2025-12-25

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_kv_cache_friendly"
down_revision: Union[str, None] = "39577145c45d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("agents", sa.Column("kv_cache_friendly", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("agents", "kv_cache_friendly")
