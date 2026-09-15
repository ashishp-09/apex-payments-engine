"""Initial ledger and payments schema with double-entry trigger

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-09-15 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Accounts
    op.create_table(
        "accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_type", sa.String(length=50), nullable=False),
        sa.Column("owner_id", sa.String(length=255), nullable=False),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("owner_type", "owner_id", "type", "currency", name="uq_accounts_owner_type_currency"),
    )

    # 2. Materialized Account Balances
    op.create_table(
        "account_balances",
        sa.Column("account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("balance", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("version", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("balance >= 0", name="non_negative_balance"),
    )

    # 3. Ledger Transactions
    op.create_table(
        "ledger_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("reference_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # 4. Ledger Entries (Postings)
    op.create_table(
        "ledger_entries",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("transaction_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ledger_transactions.id"), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("direction", sa.String(length=20), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("amount > 0", name="positive_amount"),
    )
    op.create_index("idx_entries_account_created", "ledger_entries", ["account_id", "created_at"])
    op.create_index("idx_entries_txn", "ledger_entries", ["transaction_id"])

    # 5. Payments
    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("merchant_id", sa.String(length=255), nullable=False),
        sa.Column("payer_account", postgresql.UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("payee_account", postgresql.UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("psp_reference", sa.String(length=255), nullable=True),
        sa.Column("refunded_amount", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("version", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_payments_status_created", "payments", ["status", "created_at"])
    op.create_index("idx_payments_merchant", "payments", ["merchant_id"])

    # 6. Idempotency Keys
    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("merchant_id", sa.String(length=255), nullable=False),
        sa.Column("idem_key", sa.String(length=255), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("response_code", sa.Integer(), nullable=True),
        sa.Column("response_body", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("merchant_id", "idem_key", name="uq_idempotency_merchant_key"),
    )

    # 7. Transactional Outbox
    op.create_table(
        "outbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("aggregate_type", sa.String(length=100), nullable=False),
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_outbox_unpublished", "outbox", ["created_at"], postgresql_where=sa.text("published_at IS NULL"))

    # 8. Webhook Events
    op.create_table(
        "webhook_events",
        sa.Column("psp_event_id", sa.String(length=255), primary_key=True),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # 9. Deferred Constraint Trigger: Enforce sum(amounts) = 0 on COMMIT
    op.execute("""
    CREATE OR REPLACE FUNCTION assert_ledger_balanced() RETURNS trigger AS $$
    DECLARE
      net BIGINT;
    BEGIN
      SELECT COALESCE(SUM(CASE direction WHEN 'DEBIT' THEN amount ELSE -amount END), 0)
        INTO net
        FROM ledger_entries
       WHERE transaction_id = NEW.transaction_id;

      IF net <> 0 THEN
        RAISE EXCEPTION 'Ledger transaction % is unbalanced (net = %)', NEW.transaction_id, net;
      END IF;

      RETURN NULL;
    END;
    $$ LANGUAGE plpgsql;
    """)

    op.execute("""
    CREATE CONSTRAINT TRIGGER trg_ledger_balanced
      AFTER INSERT ON ledger_entries
      DEFERRABLE INITIALLY DEFERRED
      FOR EACH ROW EXECUTE FUNCTION assert_ledger_balanced();
    """)

    # 10. Seed System Accounts
    op.execute("""
    INSERT INTO accounts (id, owner_type, owner_id, type, currency) VALUES
      ('00000000-0000-0000-0000-000000000001', 'SYSTEM', 'psp',  'PSP_SUSPENSE', 'INR'),
      ('00000000-0000-0000-0000-000000000002', 'SYSTEM', 'fees', 'FEE_INCOME',   'INR')
    ON CONFLICT DO NOTHING;
    """)

    op.execute("""
    INSERT INTO account_balances (account_id, balance, version) VALUES
      ('00000000-0000-0000-0000-000000000001', 0, 0),
      ('00000000-0000-0000-0000-000000000002', 0, 0)
    ON CONFLICT DO NOTHING;
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_ledger_balanced ON ledger_entries;")
    op.execute("DROP FUNCTION IF EXISTS assert_ledger_balanced;")
    op.drop_table("webhook_events")
    op.drop_table("outbox")
    op.drop_table("idempotency_keys")
    op.drop_table("payments")
    op.drop_table("ledger_entries")
    op.drop_table("ledger_transactions")
    op.drop_table("account_balances")
    op.drop_table("accounts")
