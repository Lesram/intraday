"""Create risk management tables

Revision ID: 003_risk_management
Revises: 002_add_cost_basis_tracking
Create Date: 2025-10-15

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '003_risk_management'
down_revision = '002_add_cost_basis_tracking'
branch_labels = None
depends_on = None


def upgrade():
    """Create risk management tables."""
    
    # Create risk_metrics table
    op.create_table(
        'risk_metrics',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('metric_name', sa.String(100), nullable=False),
        sa.Column('current_value', sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column('threshold_value', sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column('status', sa.String(20), nullable=False),  # normal, warning, critical, breached
        sa.Column('last_calculated', sa.DateTime(timezone=True), nullable=False),
        sa.Column('metadata', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, onupdate=sa.text('now()')),
    )
    op.create_index('ix_risk_metrics_user_id', 'risk_metrics', ['user_id'])
    op.create_index('ix_risk_metrics_metric_name', 'risk_metrics', ['metric_name'])
    op.create_index('ix_risk_metrics_status', 'risk_metrics', ['status'])
    
    # Create risk_violations table
    op.create_table(
        'risk_violations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('metric_name', sa.String(100), nullable=False),
        sa.Column('violation_type', sa.String(20), nullable=False),  # warning, breach
        sa.Column('severity', sa.String(20), nullable=False),  # low, medium, high, critical
        sa.Column('current_value', sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column('threshold_value', sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column('message', sa.Text, nullable=False),
        sa.Column('resolved', sa.Boolean, default=False, nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('metadata', postgresql.JSONB, nullable=True),
    )
    op.create_index('ix_risk_violations_user_id', 'risk_violations', ['user_id'])
    op.create_index('ix_risk_violations_resolved', 'risk_violations', ['resolved'])
    op.create_index('ix_risk_violations_severity', 'risk_violations', ['severity'])
    
    # Create risk_limits table
    op.create_table(
        'risk_limits',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('metric_name', sa.String(100), nullable=False),
        sa.Column('warning_threshold', sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column('breach_threshold', sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column('enabled', sa.Boolean, default=True, nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, onupdate=sa.text('now()')),
        sa.Column('metadata', postgresql.JSONB, nullable=True),
    )
    op.create_index('ix_risk_limits_user_id', 'risk_limits', ['user_id'])
    op.create_index('ix_risk_limits_enabled', 'risk_limits', ['enabled'])
    op.create_unique_constraint('uq_risk_limits_user_metric', 'risk_limits', ['user_id', 'metric_name'])
    
    # Create risk_emergency_stops table
    op.create_table(
        'risk_emergency_stops',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('trigger_reason', sa.Text, nullable=False),
        sa.Column('status', sa.String(20), nullable=False),  # active, resolved
        sa.Column('triggered_by', sa.String(100), nullable=False),  # system, user, violation
        sa.Column('triggered_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolved_by', sa.String(100), nullable=True),
        sa.Column('resolution_notes', sa.Text, nullable=True),
        sa.Column('metadata', postgresql.JSONB, nullable=True),
    )
    op.create_index('ix_risk_emergency_stops_user_id', 'risk_emergency_stops', ['user_id'])
    op.create_index('ix_risk_emergency_stops_status', 'risk_emergency_stops', ['status'])
    op.create_index('ix_risk_emergency_stops_triggered_at', 'risk_emergency_stops', ['triggered_at'])


def downgrade():
    """Drop risk management tables."""
    op.drop_table('risk_emergency_stops')
    op.drop_table('risk_limits')
    op.drop_table('risk_violations')
    op.drop_table('risk_metrics')
