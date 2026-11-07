-- Ledgerline demo schema (SQLite-compatible). Build 2026.1
-- All identifiers and timestamps are synthetic. See README.md.
PRAGMA foreign_keys = OFF;

CREATE TABLE tiers (
  tier_id TEXT PRIMARY KEY,
  tier_name TEXT,
  rank INTEGER,
  qualify_spend_cents INTEGER,
  valid_from TEXT,
  valid_to TEXT,
  status TEXT
);

CREATE TABLE rules (
  rule_id TEXT PRIMARY KEY,
  rule_code TEXT,
  version INTEGER,
  name TEXT,
  effective_from TEXT,
  effective_to TEXT,
  parameters TEXT,
  status TEXT
);

CREATE TABLE rewards (
  reward_id TEXT PRIMARY KEY,
  reward_name TEXT,
  category TEXT,
  points_cost INTEGER,
  cash_value_cents INTEGER,
  min_tier_rank INTEGER,
  status TEXT,
  effective_from TEXT,
  effective_to TEXT
);

CREATE TABLE customers (
  customer_id TEXT PRIMARY KEY,
  first_name TEXT,
  last_name TEXT,
  email TEXT,
  region TEXT,
  city TEXT,
  acquisition_channel TEXT,
  marketing_consent TEXT,
  status TEXT,
  joined_at TEXT,
  updated_at TEXT
);

CREATE TABLE loyalty_accounts (
  account_id TEXT PRIMARY KEY,
  customer_id TEXT,
  tier_id TEXT,
  opened_at TEXT,
  status TEXT,
  available_points INTEGER,
  pending_points INTEGER,
  lifetime_earned_points INTEGER,
  qualifying_spend_cents INTEGER,
  tier_reviewed_at TEXT,
  last_activity_at TEXT,
  updated_at TEXT
);

CREATE TABLE reward_tier_eligibility (
  reward_id TEXT,
  tier_id TEXT,
  eligible TEXT,
  PRIMARY KEY (reward_id, tier_id)
);

CREATE TABLE rule_tier_rate (
  rule_id TEXT,
  tier_id TEXT,
  earn_multiplier REAL,
  effective_from TEXT,
  PRIMARY KEY (rule_id, tier_id)
);

CREATE TABLE tier_history (
  history_id TEXT PRIMARY KEY,
  account_id TEXT,
  from_tier_id TEXT,
  to_tier_id TEXT,
  changed_at TEXT,
  reason TEXT,
  qualifying_spend_cents INTEGER,
  rule_id TEXT
);

CREATE TABLE orders (
  order_id TEXT PRIMARY KEY,
  customer_id TEXT,
  account_id TEXT,
  order_ts TEXT,
  channel TEXT,
  store_id TEXT,
  gross_cents INTEGER,
  discount_cents INTEGER,
  tax_cents INTEGER,
  shipping_cents INTEGER,
  net_eligible_cents INTEGER,
  refund_cents INTEGER,
  status TEXT,
  returned_at TEXT
);

CREATE TABLE order_lines (
  order_line_id TEXT PRIMARY KEY,
  order_id TEXT,
  sku TEXT,
  product_name TEXT,
  category TEXT,
  quantity INTEGER,
  unit_price_cents INTEGER,
  discount_cents INTEGER,
  line_net_cents INTEGER,
  eligible_for_points TEXT,
  returned_qty INTEGER,
  returned_amount_cents INTEGER
);

CREATE TABLE points_transactions (
  points_txn_id TEXT PRIMARY KEY,
  account_id TEXT,
  txn_type TEXT,
  points_delta INTEGER,
  posted_at TEXT,
  status TEXT,
  source_order_id TEXT,
  source_order_line_id TEXT,
  reversal_of_pts_id TEXT,
  redemption_id TEXT,
  expiry_batch_id TEXT,
  expiry_source_pts_id TEXT,
  rule_id TEXT,
  tier_id_at_post TEXT,
  earn_multiplier REAL,
  expires_at TEXT,
  description TEXT
);

CREATE TABLE redemptions (
  redemption_id TEXT PRIMARY KEY,
  account_id TEXT,
  reward_id TEXT,
  requested_at TEXT,
  points_requested INTEGER,
  status TEXT,
  decision_reason TEXT,
  balance_before INTEGER,
  balance_after INTEGER,
  points_txn_id TEXT,
  request_group_id TEXT
);

CREATE TABLE expiry_batches (
  expiry_batch_id TEXT PRIMARY KEY,
  account_id TEXT,
  run_at TEXT,
  points_expired INTEGER,
  lot_count INTEGER,
  idempotency_key TEXT,
  status TEXT,
  rule_id TEXT,
  created_at TEXT
);

CREATE TABLE ground_truth (
  case_id TEXT PRIMARY KEY,
  issue_type TEXT,
  entity_type TEXT,
  entity_id TEXT,
  related_entity_id TEXT,
  expected_label TEXT,
  expected_decision TEXT,
  severity TEXT,
  detection_rule TEXT,
  notes TEXT,
  evidence TEXT,
  generated_at TEXT
);

CREATE INDEX idx_pts_account_time ON points_transactions(account_id, posted_at);
CREATE INDEX idx_pts_order ON points_transactions(source_order_id);
CREATE INDEX idx_orders_customer ON orders(customer_id, order_ts);
CREATE INDEX idx_redemptions_account ON redemptions(account_id, requested_at);
CREATE INDEX idx_expiry_account ON expiry_batches(account_id, run_at);
PRAGMA foreign_keys = ON;
