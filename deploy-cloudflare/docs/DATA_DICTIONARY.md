# Ledgerline data dictionary

Generated from the same source constants as the dataset. The field-level
dictionary covers the ten core entities plus the tier history and bridge tables.

## Customer (`customers`)

A person enrolled in the Morrow & Finch loyalty programme. No real personal data is used.

Primary key: `customer_id`

| Field | Type | Required | Example | Units | Uniqueness / validation |
|---|---|---|---|---|---|
| customer_id | string | yes | C-000001 | unique | Regex ^C-\d{6}$; immutable |
| first_name | string | yes | Aisha | - | 2–40 chars; synthetic name |
| last_name | string | yes | Patel | - | 2–40 chars; synthetic name |
| email | string | yes | aisha.patel.00001@example.test | unique | RFC 5322 basic pattern; .test domain only |
| region | enum | yes | Greater London | - | One of the nine configured regions |
| city | string | yes | London | - | Must match region lookup |
| acquisition_channel | enum | yes | online | - | online \| store \| app \| referral |
| marketing_consent | boolean | yes | true | - | True or false; independent of programme state |
| status | enum | yes | active | - | active \| inactive \| deactivated |
| joined_at | datetime | yes | 2023-04-18T10:22:00Z | - | Before first account activity |
| updated_at | datetime | yes | 2026-10-31T18:00:00Z | - | At or after joined_at |

## LoyaltyAccount (`loyalty_accounts`)

One programme account per customer; the materialised balance is derived from the ledger.

Primary key: `account_id`

| Field | Type | Required | Example | Units | Uniqueness / validation |
|---|---|---|---|---|---|
| account_id | string | yes | LOY-C-000001 | unique | Regex ^LOY-C-\d{6}$; 1:1 with customer_id |
| customer_id | string FK | yes | C-000001 | unique | References customers.customer_id |
| tier_id | string FK | yes | TIER-02 | - | References tiers.tier_id |
| opened_at | datetime | yes | 2023-04-18T10:22:00Z | - | Must equal or follow customer.joined_at |
| status | enum | yes | active | - | active \| suspended \| closed |
| available_points | integer | yes | 1840 | - | >= 0 in valid rows; equals ledger sum unless labelled mismatch |
| pending_points | integer | yes | 0 | - | >= 0; pending earns are excluded from available balance |
| lifetime_earned_points | integer | yes | 12680 | - | Sum of positive accrual, bonus and adjustment rows |
| qualifying_spend_cents | integer | yes | 54820 | GBP cents | Trailing 365-day net eligible spend after returns |
| tier_reviewed_at | datetime | yes | 2026-10-01T00:00:00Z | - | Effective date of current tier |
| last_activity_at | datetime | no | 2026-10-30T14:16:00Z | - | Maximum posted_at across ledger rows |
| updated_at | datetime | yes | 2026-11-01T09:00:00Z | - | Snapshot materialisation time |

## Tier (`tiers`)

Configured membership tier and its qualifying-spend threshold.

Primary key: `tier_id`

| Field | Type | Required | Example | Units | Uniqueness / validation |
|---|---|---|---|---|---|
| tier_id | string | yes | TIER-02 | unique | Regex ^TIER-\d{2}$ |
| tier_name | string | yes | Silver | unique | Member \| Silver \| Gold \| Platinum |
| rank | integer | yes | 2 | ordinal | 1–4; strictly increasing |
| qualify_spend_cents | integer | yes | 10000 | GBP cents | >= 0; monotonic by rank |
| valid_from | date | yes | 2024-01-01 | - | Effective date |
| valid_to | date | no |  | - | Null means open-ended; >= valid_from |
| status | enum | yes | active | - | active \| retired |

## Rule (`rules`)

Versioned earning, redemption, expiry, tier and bonus policy with effective dates.

Primary key: `rule_id`

| Field | Type | Required | Example | Units | Uniqueness / validation |
|---|---|---|---|---|---|
| rule_id | string | yes | RULE-EARN-2024-V1 | unique | Immutable; version suffix required |
| rule_code | enum | yes | EARN_RATE | - | EARN_RATE \| REDEMPTION \| EXPIRY \| TIER_REVIEW \| BONUS |
| version | integer | yes | 1 | - | >= 1; unique per rule_code |
| name | string | yes | Earn rate, 2024 schedule | - | Human-readable policy name |
| effective_from | datetime | yes | 2024-01-01T00:00:00Z | - | Start of validity |
| effective_to | datetime | no | 2025-12-31T23:59:59Z | - | Null means current; later than effective_from |
| parameters | json | yes | {"points_per_gbp":10} | - | Validated key/value policy object |
| status | enum | yes | active | - | draft \| active \| superseded |

## Order (`orders`)

A completed purchase used as the source for accrual and return events.

Primary key: `order_id`

| Field | Type | Required | Example | Units | Uniqueness / validation |
|---|---|---|---|---|---|
| order_id | string | yes | ORD-2026-000001 | unique | Regex ^ORD-\d{4}-\d{6}$; year matches order_ts |
| customer_id | string FK | yes | C-000001 | - | References customers.customer_id |
| account_id | string FK | yes | LOY-C-000001 | - | References loyalty_accounts.account_id |
| order_ts | datetime | yes | 2026-10-17T14:32:00Z | - | Within dataset window; after account open |
| channel | enum | yes | online | - | online \| store \| app |
| store_id | string FK | no | S-11 | - | Required for store orders; null otherwise |
| gross_cents | integer | yes | 12800 | GBP cents | >= 0; equals sum of line gross |
| discount_cents | integer | yes | 1280 | GBP cents | >= 0; <= gross |
| tax_cents | integer | yes | 2304 | GBP cents | = floor((gross-discount) × 20%) |
| shipping_cents | integer | yes | 0 | GBP cents | 0 \| 499 \| 699 |
| net_eligible_cents | integer | yes | 11520 | GBP cents | Sum of eligible line net; excludes gift cards, tax and shipping |
| refund_cents | integer | yes | 0 | GBP cents | 0–(gross-discount); ties to returned_qty |
| status | enum | yes | completed | - | completed \| partially_returned \| returned \| voided |
| returned_at | datetime | no |  | - | Required iff status is partially_returned or returned; after order_ts |

## OrderLine (`order_lines`)

Product-level purchase line. Points accrue per eligible line, giving source-level traceability.

Primary key: `order_line_id`

| Field | Type | Required | Example | Units | Uniqueness / validation |
|---|---|---|---|---|---|
| order_line_id | string | yes | OL-2026-000001 | unique | Regex ^OL-\d{4}-\d{6}$ |
| order_id | string FK | yes | ORD-2026-000001 | - | References orders.order_id |
| sku | string | yes | APP-1042 | unique per category | Synthetic SKU; no real catalogue data |
| product_name | string | yes | Ribbed merino crew | - | Synthetic product label |
| category | enum | yes | apparel | - | apparel \| footwear \| home \| beauty \| accessories \| gift_card |
| quantity | integer | yes | 1 | units | 1–4 |
| unit_price_cents | integer | yes | 6500 | GBP cents | > 0 |
| discount_cents | integer | yes | 650 | GBP cents | 0 <= discount <= quantity × unit_price |
| line_net_cents | integer | yes | 5850 | GBP cents | quantity × unit_price - discount |
| eligible_for_points | boolean | yes | true | - | False for gift_card category |
| returned_qty | integer | yes | 0 | units | 0–quantity; zero if not returned |
| returned_amount_cents | integer | yes | 0 | GBP cents | 0 <= returned_amount <= line_net |

## PointsTransaction (`points_transactions`)

Immutable, signed points ledger. Positive rows create lots; negative rows consume or remove them.

Primary key: `points_txn_id`

| Field | Type | Required | Example | Units | Uniqueness / validation |
|---|---|---|---|---|---|
| points_txn_id | string | yes | PTS-2026-00000001 | unique | Regex ^PTS-\d{4}-\d{8}$; immutable |
| account_id | string FK | yes | LOY-C-000001 | - | References loyalty_accounts.account_id |
| txn_type | enum | yes | ACCRUAL | - | ACCRUAL \| REVERSAL \| REDEMPTION \| EXPIRATION \| BONUS \| ADJUSTMENT |
| points_delta | integer | yes | 248 | points | Non-zero; positive for ACCRUAL/BONUS/ADJUSTMENT, negative otherwise |
| posted_at | datetime | yes | 2026-10-17T14:34:00Z | - | Chronological ledger time; no updates |
| status | enum | yes | posted | - | posted \| reversed \| partially_reversed |
| source_order_id | string FK | no | ORD-2026-000001 | - | Required for ACCRUAL and order-linked REVERSAL |
| source_order_line_id | string FK | no | OL-2026-000001 | - | Required for line-level ACCRUAL and REVERSAL |
| reversal_of_pts_id | string FK | no |  | - | Required for REVERSAL; references an ACCRUAL row |
| redemption_id | string FK | no |  | - | Required for REDEMPTION; references redemptions.redemption_id |
| expiry_batch_id | string FK | no |  | - | Required for EXPIRATION; references expiry_batches.expiry_batch_id |
| expiry_source_pts_id | string FK | no |  | - | For EXPIRATION, the accrual/bonus lot that expired |
| rule_id | string FK | yes | RULE-EARN-2026-V2 | - | Policy applied at posting time |
| tier_id_at_post | string FK | no | TIER-02 | - | Tier used for earning; null for non-accrual rows |
| earn_multiplier | decimal | no | 1.25 | multiplier | Present for ACCRUAL rows; matches rule-tier bridge |
| expires_at | datetime | no | 2028-10-17T14:34:00Z | - | Required for positive earning rows; later than posted_at |
| description | string | yes | Line accrual · ORD-2026-000001 | - | Non-empty audit narrative |

## Reward (`rewards`)

Catalogue item that can be redeemed for points. Tier eligibility is many-to-many.

Primary key: `reward_id`

| Field | Type | Required | Example | Units | Uniqueness / validation |
|---|---|---|---|---|---|
| reward_id | string | yes | RWD-02 | unique | Regex ^RWD-\d{2}$ |
| reward_name | string | yes | £5 reward voucher | - | Human-readable label |
| category | enum | yes | voucher | - | voucher \| delivery \| merchandise \| service |
| points_cost | integer | yes | 500 | points | > 0; multiple of 100 |
| cash_value_cents | integer | yes | 500 | GBP cents | >= 0; liability reference only |
| min_tier_rank | integer | yes | 1 | ordinal | 1–4; mirrored by reward_tier_eligibility |
| status | enum | yes | active | - | active \| retired |
| effective_from | date | yes | 2024-01-01 | - | Start of catalogue period |
| effective_to | date | no |  | - | Null means open-ended |

## Redemption (`redemptions`)

One redemption attempt and its evaluated decision. Rejected attempts are retained and never posted.

Primary key: `redemption_id`

| Field | Type | Required | Example | Units | Uniqueness / validation |
|---|---|---|---|---|---|
| redemption_id | string | yes | RDM-2026-000001 | unique | Regex ^RDM-\d{4}-\d{6}$; immutable |
| account_id | string FK | yes | LOY-C-000001 | - | References loyalty_accounts.account_id |
| reward_id | string FK | yes | RWD-02 | - | References rewards.reward_id |
| requested_at | datetime | yes | 2026-06-18T11:03:00Z | - | After account open |
| points_requested | integer | yes | 500 | points | > 0; equals reward points_cost |
| status | enum | yes | approved | - | approved \| rejected |
| decision_reason | enum | yes | approved | - | approved \| insufficient_balance \| concurrent_lock \| reward_inactive \| below_minimum \| account_suspended |
| balance_before | integer | yes | 1820 | points | Account ledger balance immediately before decision |
| balance_after | integer | yes | 1320 | points | Equals balance_before less approved points |
| points_txn_id | string FK | no | PTS-2026-00000218 | - | Required iff approved; references points_transactions.points_txn_id |
| request_group_id | string | no |  | - | Set for concurrent attempts; at most one approval per group |

## ExpiryBatch (`expiry_batches`)

Idempotent expiry run. Each batch removes remaining points from one or more due lots for one account.

Primary key: `expiry_batch_id`

| Field | Type | Required | Example | Units | Uniqueness / validation |
|---|---|---|---|---|---|
| expiry_batch_id | string | yes | EXP-2026-000001 | unique | Regex ^EXP-\d{4}-\d{6}$ |
| account_id | string FK | yes | LOY-C-000001 | - | References loyalty_accounts.account_id |
| run_at | datetime | yes | 2026-09-01T00:00:00Z | - | Batch cut-off; >= each expired lot's expires_at |
| points_expired | integer | yes | 420 | points | > 0; equals sum of linked EXPIRATION rows |
| lot_count | integer | yes | 2 | lots | >= 1; count of distinct expiry_source_pts_id rows |
| idempotency_key | string | yes | exp:LOY-C-000001:2026-09 | unique | Unique in valid rows; duplicate intentionally labelled |
| status | enum | yes | posted | - | posted \| void |
| rule_id | string FK | yes | RULE-EXPIRY-V1 | - | References rules.rule_id |
| created_at | datetime | yes | 2026-09-01T00:00:04Z | - | Posting timestamp |

## TierHistory (`tier_history`)

Append-only account tier changes, with the qualifying spend and rule that caused the change.

Primary key: `history_id`

| Field | Type | Required | Example | Units | Uniqueness / validation |
|---|---|---|---|---|---|
| history_id | string | yes | TH-2026-000001 | unique | Regex ^TH-\d{4}-\d{6}$ |
| account_id | string FK | yes | LOY-C-000001 | - | References loyalty_accounts.account_id |
| from_tier_id | string FK | no |  | - | Null on opening tier; otherwise references tiers |
| to_tier_id | string FK | yes | TIER-02 | - | References tiers.tier_id |
| changed_at | datetime | yes | 2026-04-02T12:00:00Z | - | After account open; append-only |
| reason | enum | yes | rolling_spend_upgrade | - | opening \| rolling_spend_upgrade \| annual_review_downgrade \| correction |
| qualifying_spend_cents | integer | yes | 41200 | GBP cents | Trailing 365-day net eligible spend at decision |
| rule_id | string FK | yes | RULE-TIER-V1 | - | References rules.rule_id |

## Bridge tables

### `rule_tier_rate`

Composite key: (`rule_id`, `tier_id`). Effective earn multiplier per policy version.

| Field | Type | Required | Validation |
|---|---|---|---|
| rule_id | string FK | yes | references rules.rule_id |
| tier_id | string FK | yes | references tiers.tier_id |
| earn_multiplier | decimal | yes | > 0; unique per rule/tier pair |
| effective_from | date | yes | matches the policy effective date |

### `reward_tier_eligibility`

Composite key: (`reward_id`, `tier_id`). Controls which tiers may see a reward.

| Field | Type | Required | Validation |
|---|---|---|---|
| reward_id | string FK | yes | references rewards.reward_id |
| tier_id | string FK | yes | references tiers.tier_id |
| eligible | boolean | yes | true only when tier rank >= reward.min_tier_rank |

## Entity relationships

| Parent | Child | Cardinality | Note |
|---|---|---|---|
| Customer | LoyaltyAccount | 1:1 | Every customer has exactly one account in this build; account is optional only for prospects. |
| Tier | LoyaltyAccount | 1:N | One current tier per account; tier changes retained in TierHistory. |
| Tier | Rule | M:N | Mapped through rule_tier_rate with an earn multiplier. |
| Reward | Tier | M:N | Mapped through reward_tier_eligibility. |
| Customer | Order | 1:N | Orders must reference a valid customer; account open must precede order. |
| Order | OrderLine | 1:N | One or more product lines per order; all line totals reconcile to the order. |
| Order | PointsTransaction | 1:N | Accrual rows optionally link to an order and a line; reversals reference the original accrual. |
| LoyaltyAccount | PointsTransaction | 1:N | Ledger is the source of truth for the materialised balance. |
| Reward | Redemption | 1:N | A rejected attempt still references a valid reward; only approved attempts post points. |
| LoyaltyAccount | Redemption | 1:N | Every attempt belongs to one account; request groups model concurrency. |
| LoyaltyAccount | ExpiryBatch | 1:N | One batch per account per monthly run; may contain several lots. |
| ExpiryBatch | PointsTransaction | 1:N | Each expiration row references its batch and the source lot. |
| LoyaltyAccount | TierHistory | 1:N | Append-only tier changes with effective time and rule. |

## Lifecycle states

- **Customer:** active, inactive, deactivated.
- **LoyaltyAccount:** active, suspended, closed.
- **Order:** completed, partially_returned, returned, voided.
- **PointsTransaction:** posted, partially_reversed (accrual), reversed (accrual).
- **Redemption:** approved, rejected (with a decision reason).
- **ExpiryBatch:** posted, void.
- **Rule / Tier / Reward:** draft or active/superseded, retired, with effective dates.

## ID grammar

| Entity | Pattern | Rule |
|---|---|---|
| Customer | `C-000001` | six-digit immutable sequence |
| LoyaltyAccount | `LOY-C-000001` | LOY- + customer_id |
| Order | `ORD-2026-000001` | year of order + six-digit sequence |
| OrderLine | `OL-2026-000001` | year of order + six-digit sequence |
| PointsTransaction | `PTS-2026-00000001` | snapshot year + eight-digit posting sequence |
| Redemption | `RDM-2026-000001` | snapshot year + six-digit attempt sequence |
| ExpiryBatch | `EXP-2026-000001` | snapshot year + six-digit batch sequence |
| TierHistory | `TH-2026-000001` | change year + six-digit sequence |
| GroundTruth | `GT-2026-0001` | snapshot year + case sequence |
