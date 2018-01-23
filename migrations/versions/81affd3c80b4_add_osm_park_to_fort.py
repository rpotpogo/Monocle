"""add OSM park to fort

Revision ID: 81affd3c80b4
Revises: 95ff6d6dd804
Create Date: 2018-01-08 20:21:00.030238

"""
from alembic import op
import sqlalchemy as sa
import sys
from pathlib import Path
monocle_dir = str(Path(__file__).resolve().parents[2])
if monocle_dir not in sys.path:
    sys.path.append(monocle_dir)
from monocle import db as db

# revision identifiers, used by Alembic.
revision = '81affd3c80b4'
down_revision = '95ff6d6dd804'
branch_labels = None
depends_on = None


def upgrade():
	op.add_column('forts', sa.Column('park', sa.String(128), nullable=True))


def downgrade():
	op.drop_column('forts', 'park')
