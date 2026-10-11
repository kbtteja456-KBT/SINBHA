from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from app.models import Base

revision: str = '2b19858baeff'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    """Upgrade schema: safely create all tables if not already existing."""
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)

def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
