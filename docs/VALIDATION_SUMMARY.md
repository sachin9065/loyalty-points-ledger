# Validation summary

Build `2026.1-20261022` · seed `20261022` · snapshot 2026-11-01T09:00:00Z

**19 passed**, **0 expected warnings**,
**0 failures** across 19 checks.

| Check | Result | Detail |
|---|---|---|
| customers.customer_id uniqueness | pass | 0 duplicate keys |
| loyalty_accounts.account_id uniqueness | pass | 0 duplicate keys |
| orders.order_id uniqueness | pass | 0 duplicate keys |
| order_lines.order_line_id uniqueness | pass | 0 duplicate keys |
| points_transactions.points_txn_id uniqueness | pass | 0 duplicate keys |
| redemptions.redemption_id uniqueness | pass | 0 duplicate keys |
| expiry_batches.expiry_batch_id uniqueness | pass | 0 duplicate keys |
| Foreign-key integrity | pass | 0 broken references |
| Allowed enum values | pass | 0 invalid enum values |
| Date and lifecycle ordering | pass | 0 ordering failures |
| Balance equals ledger | pass | 12 mismatches, 12 labelled |
| Redemption never exceeds available balance | pass | 0 bad approvals |
| Reversals reference original accrual | pass | 0 invalid reversal links |
| Returned order points are reversed | pass | 0 unlabelled missing reversals; 24 labelled cases |
| Expiry batch idempotency | pass | 8 duplicate idempotency keys, all 8 labelled |
| Tier follows qualifying-spend rules | pass | 0 unlabelled tier mismatches; 10 labelled exceptions |
| Expiry batch totals reconcile | pass | 0 batch totals disagree with linked ledger rows |
| Concurrent attempt guard | pass | 0 groups without exactly one approval |
| Ledger volume target | pass | 300,000 vs 300,000 target |

## Exception register

| Issue type | Count | Severity | Expected handling |
|---|---:|---|---|
| `balance_differs_from_ledger` | 12 | high | Rebuild materialised balance from ledger |
| `concurrent_redemption_attempt` | 20 | medium | Approve one; reject the second with concurrent_lock |
| `points_expire_twice` | 8 | high | Void duplicate batch; restore points |
| `redemption_exceeds_available_points` | 16 | medium | Reject; do not post a ledger row |
| `returned_order_keeps_all_points` | 24 | high | Post missing reversals to the original accruals |
| `tier_uses_gross_spend` | 10 | medium | Reapply trailing qualifying-spend rule |

Warnings are expected labelled exceptions, not silent corruption. The original
history is retained; anomalies exist only in the documented fields and are
available separately in `ground_truth.csv` / `ground_truth.json`.
