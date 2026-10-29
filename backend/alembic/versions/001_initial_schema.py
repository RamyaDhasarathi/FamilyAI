"""Initial schema migration for Family OS

Revision ID: 001
Revises: 
Create Date: 2026-10-19 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. users
    op.create_table(
        'users',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('display_name', sa.String(255), nullable=False),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True)

    # 2. families
    op.create_table(
        'families',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )

    # 3. family_memberships
    op.create_table(
        'family_memberships',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('family_id', sa.String(36), sa.ForeignKey('families.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('family_role', sa.String(50), nullable=False),
        sa.Column('membership_status', sa.String(50), nullable=False, server_default='ACTIVE'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('family_id', 'user_id', name='uq_family_user_membership'),
    )
    op.create_index('ix_family_memberships_family_id', 'family_memberships', ['family_id'])
    op.create_index('ix_family_memberships_user_id', 'family_memberships', ['user_id'])

    # 4. permission_grants
    op.create_table(
        'permission_grants',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('family_id', sa.String(36), sa.ForeignKey('families.id', ondelete='CASCADE'), nullable=False),
        sa.Column('subject_membership_id', sa.String(36), sa.ForeignKey('family_memberships.id', ondelete='CASCADE'), nullable=False),
        sa.Column('resource', sa.String(100), nullable=False),
        sa.Column('action', sa.String(100), nullable=False),
        sa.Column('effect', sa.String(20), nullable=False),
        sa.Column('approval_required', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('constraints_json', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('created_by_membership_id', sa.String(36), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
    )
    op.create_index('ix_permission_grants_lookup', 'permission_grants', ['family_id', 'subject_membership_id', 'resource', 'action'])

    # 5. conversations
    op.create_table(
        'conversations',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('family_id', sa.String(36), sa.ForeignKey('families.id', ondelete='CASCADE'), nullable=False),
        sa.Column('owner_membership_id', sa.String(36), sa.ForeignKey('family_memberships.id', ondelete='CASCADE'), nullable=False),
        sa.Column('agent_type', sa.String(50), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )

    # 6. messages
    op.create_table(
        'messages',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('conversation_id', sa.String(36), sa.ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('sender_type', sa.String(50), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('content_type', sa.String(50), nullable=False, server_default='TEXT'),
        sa.Column('metadata_json', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_messages_conversation_id', 'messages', ['conversation_id'])

    # 7. purchase_tasks
    op.create_table(
        'purchase_tasks',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('family_id', sa.String(36), sa.ForeignKey('families.id', ondelete='CASCADE'), nullable=False),
        sa.Column('requester_membership_id', sa.String(36), sa.ForeignKey('family_memberships.id', ondelete='CASCADE'), nullable=False),
        sa.Column('beneficiary_membership_id', sa.String(36), nullable=True),
        sa.Column('conversation_id', sa.String(36), nullable=False),
        sa.Column('original_request', sa.Text(), nullable=False),
        sa.Column('parsed_intent_json', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('status', sa.String(50), nullable=False),
        sa.Column('budget_amount', sa.Numeric(10, 2), nullable=True),
        sa.Column('currency', sa.String(3), nullable=True),
        sa.Column('selected_product_id', sa.String(36), nullable=True),
        sa.Column('approval_state', sa.String(50), nullable=False, server_default='NOT_REQUIRED'),
        sa.Column('execution_state', sa.String(50), nullable=False, server_default='NOT_STARTED'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_purchase_tasks_family_id', 'purchase_tasks', ['family_id'])

    # 8. product_candidates
    op.create_table(
        'product_candidates',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('purchase_task_id', sa.String(36), sa.ForeignKey('purchase_tasks.id', ondelete='CASCADE'), nullable=False),
        sa.Column('provider', sa.String(100), nullable=False),
        sa.Column('provider_product_id', sa.String(255), nullable=True),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('brand', sa.String(255), nullable=True),
        sa.Column('price_amount', sa.Numeric(10, 2), nullable=True),
        sa.Column('currency', sa.String(3), nullable=True),
        sa.Column('merchant', sa.String(255), nullable=True),
        sa.Column('product_url', sa.Text(), nullable=True),
        sa.Column('image_url', sa.Text(), nullable=True),
        sa.Column('availability', sa.String(100), nullable=True),
        sa.Column('delivery_estimate', sa.String(255), nullable=True),
        sa.Column('warranty_details', sa.Text(), nullable=True),
        sa.Column('return_details', sa.Text(), nullable=True),
        sa.Column('specifications_json', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('source_type', sa.String(50), nullable=False),
        sa.Column('last_checked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_product_candidates_task_id', 'product_candidates', ['purchase_task_id'])

    # 9. approval_requests
    op.create_table(
        'approval_requests',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('family_id', sa.String(36), sa.ForeignKey('families.id', ondelete='CASCADE'), nullable=False),
        sa.Column('purchase_task_id', sa.String(36), sa.ForeignKey('purchase_tasks.id', ondelete='CASCADE'), nullable=False),
        sa.Column('requested_by_membership_id', sa.String(36), sa.ForeignKey('family_memberships.id', ondelete='CASCADE'), nullable=False),
        sa.Column('approver_membership_id', sa.String(36), nullable=True),
        sa.Column('approval_type', sa.String(50), nullable=False),
        sa.Column('status', sa.String(50), nullable=False, server_default='PENDING'),
        sa.Column('request_payload_json', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('decision_reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_approval_requests_family_status', 'approval_requests', ['family_id', 'status'])

    # 10. mobile_use_instructions
    op.create_table(
        'mobile_use_instructions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('family_id', sa.String(36), sa.ForeignKey('families.id', ondelete='CASCADE'), nullable=False),
        sa.Column('purchase_task_id', sa.String(36), sa.ForeignKey('purchase_tasks.id', ondelete='CASCADE'), nullable=False),
        sa.Column('created_by_agent', sa.String(100), nullable=False),
        sa.Column('action_type', sa.String(100), nullable=False),
        sa.Column('target_type', sa.String(100), nullable=False),
        sa.Column('target_reference', sa.Text(), nullable=True),
        sa.Column('payload_json', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('policy_decision_id', sa.String(36), nullable=True),
        sa.Column('approval_request_id', sa.String(36), sa.ForeignKey('approval_requests.id', ondelete='SET NULL'), nullable=True),
        sa.Column('status', sa.String(50), nullable=False, server_default='CREATED'),
        sa.Column('idempotency_key', sa.String(255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_mobile_use_instructions_idempotency', 'mobile_use_instructions', ['idempotency_key'], unique=True)

    # 11. audit_events
    op.create_table(
        'audit_events',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('family_id', sa.String(36), nullable=True),
        sa.Column('actor_type', sa.String(50), nullable=False),
        sa.Column('actor_id', sa.String(36), nullable=True),
        sa.Column('action', sa.String(100), nullable=False),
        sa.Column('resource_type', sa.String(100), nullable=False),
        sa.Column('resource_id', sa.String(36), nullable=True),
        sa.Column('decision', sa.String(20), nullable=True),
        sa.Column('reason_code', sa.String(100), nullable=True),
        sa.Column('correlation_id', sa.String(100), nullable=False),
        sa.Column('metadata_json', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_audit_events_family_id', 'audit_events', ['family_id'])
    op.create_index('ix_audit_events_action', 'audit_events', ['action'])
    op.create_index('ix_audit_events_correlation_id', 'audit_events', ['correlation_id'])


def downgrade() -> None:
    op.drop_table('audit_events')
    op.drop_table('mobile_use_instructions')
    op.drop_table('approval_requests')
    op.drop_table('product_candidates')
    op.drop_table('purchase_tasks')
    op.drop_table('messages')
    op.drop_table('conversations')
    op.drop_table('permission_grants')
    op.drop_table('family_memberships')
    op.drop_table('families')
    op.drop_table('users')
