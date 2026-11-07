# Ledgerline: synthetic loyalty ledger

A working, deterministic synthetic-data build for the Morrow & Finch loyalty
ledger exercise. The same generator produces a starter sample and the full
build, so every demonstration row can be traced back to a documented rule.

## At a glance

| Item | Value |
|---|---|
| Build | 2026.1-20261022 |
| Seed | `20261022` |
| Snapshot | 2026-11-01T09:00:00Z |
| Customers / accounts | 20,000 / 20,000 |
| Orders / order lines | 100,000 / 198,804 |
| Points ledger rows | 300,000 |
| Redemption attempts | 50,056 |
| Expiry batches | 15,351 |
| Labelled ground-truth cases | 90 |
| Validation | 19 pass / 0 warnings / 0 fail |

The generated data is synthetic. There are no real customers, addresses,
orders, or scraped catalogue records. The Morrow & Finch brand and product
names are fictional.

## Run the site

```bash
cd loyalty-ledger
python -m http.server 4173
# open http://localhost:4173
```

Opening `index.html` directly also works because the demo data is shipped as
`assets/js/data.js`. A local server is recommended for the downloadable
bundle.

## Regenerate the data

```bash
python generator/generate.py --seed 20261022 --out data
```

Full options:

```text
--seed 20261022              fixed RNG seed
--customers 20000            master population
--orders 100000              order volume
--transactions 300000        exact points ledger volume
--bonus 6000                 base bonus lots
--attempts 50000             pre-scheduled redemption attempts
--skip-sql                   skip the large seed.sql export
--verify-repro               build twice and compare canonical checksums
```

Starter sample:

```bash
python generator/generate.py --seed 20261022 --customers 200 --orders 1000 \
  --transactions 3000 --out data/starter
```

## Business rules implemented

- Points earn on **net eligible spend** after line discounts; gift cards, tax
  and delivery are excluded.
- Earn schedule: **10 points per whole GBP**, rounded down, multiplied by the
  tier at posting time (1.00 / 1.25 / 1.50 / 2.00 for Member, Silver, Gold and
  Platinum from 2026; 1.00 / 1.20 / 1.40 / 1.80 for the 2024 schedule).
- Tiers are calculated from **trailing 365-day net eligible spend after
  returns**. Upgrades are immediate; downgrades are recognised at review.
- Returns post a reversal that references the original accrual. A fully
  returned order reverses its line accruals; partial returns reverse pro rata.
- Redemptions are approved only when the account has enough available points.
  Concurrent attempts are serialised, with at most one approval per request
  group.
- Accrual lots expire at the first monthly run after their lot expiry date
  (24 months for order accruals, 12 months for campaign bonuses). Expiry is
  idempotent: one batch per account per run, one ledger line per source lot.
- Account balance is derived from the immutable ledger. Six deliberate anomaly
  families, 90 cases in all, are labelled in `ground_truth.csv` /
  `ground_truth.json`.

## Deliberately injected edge cases

| `issue_type` | Cases | Intended handling |
|---|---:|---|
| balance_differs_from_ledger | 12 | Rebuild materialised balance from ledger |
| redemption_exceeds_available_points | 16 | Reject, no posted ledger row |
| returned_order_keeps_all_points | 24 | Reverse the missing line accruals |
| points_expire_twice | 8 | Void duplicate expiry batch and restore points |
| tier_uses_gross_spend | 10 | Recalculate from qualifying spend |
| concurrent_redemption_attempt | 20 | Approve first, reject second with lock |

Ground truth is a separate table and file. It is not a feature in any input
table and must not be joined into model features.

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

Effective dates are explicit on `Tier` and `Rule`; lifecycle state is explicit
on accounts, orders, redemptions, batches and tier history. Bridge tables are
`rule_tier_rate` and `reward_tier_eligibility`.

## Files

| Path | Contents |
|---|---|
| `index.html` | The operator-facing site |
| `assets/` | CSS, JS and data payload |
| `generator/generate.py` | Deterministic generator, validator and exporter |
| `data/csv/` | Full CSV export for every entity |
| `data/jsonl/` | Full JSON Lines export for every entity |
| `data/json/ground_truth.json` | Separated verification labels |
| `data/json/site-data.json` | Dashboard payload |
| `data/sql/schema.sql` | SQLite-compatible DDL |
| `data/sql/seed.sql` | Full SQL seed data |
| `docs/DATA_DICTIONARY.md` | Field-level dictionary and validation rules |
| `docs/VALIDATION_SUMMARY.md` | Acceptance checks and exception counts |
| `data/manifest.json` | Source manifest, counts and checksums |

## Reproducibility

The generator is stdlib-only and seeded by `random.Random(20261022)`. Re-running
the same command produces identical row counts and SHA-256 table checksums.
`--verify-repro` performs the second build automatically; the comparison is
written to `data/reproducibility.json`.

## Public data and provenance

No external data was used. The build contains only deterministic synthetic
records generated from this repository's rules. See
`docs/SOURCE_MANIFEST.json` for the explicit provenance record, licence and
transformation list.
