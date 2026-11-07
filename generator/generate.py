#!/usr/bin/env python3
"""
Ledgerline synthetic loyalty data generator.

Generates a deterministic, referentially complete loyalty ledger for the
Morrow & Finch demo. The generator is stdlib-only and uses a fixed seed.

Examples
--------
Full build (20,000 customers / 100,000 orders / 300,000 ledger rows):
    python generator/generate.py --seed 20261022 --out data

Starter build (1/100th scale, useful for tests):
    python generator/generate.py --seed 20261022 --customers 200 --orders 1000 \
        --transactions 3000 --out data/starter
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import random
import shutil
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

UTC = timezone.utc
AS_OF = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)
DATA_START = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
DATA_END = datetime(2026, 10, 31, 21, 0, tzinfo=UTC)
DEFAULT_SEED = 20261022

FIRST_NAMES = [
    "Aisha", "Alfie", "Amara", "Ana", "Arjun", "Bea", "Ben", "Callum", "Camille",
    "Chloe", "Clara", "Daniel", "Dara", "Dev", "Elena", "Eli", "Emeka", "Esme",
    "Farah", "Felix", "Freya", "Gemma", "Grace", "Hana", "Hari", "Harriet",
    "Iris", "Isaac", "Ivy", "Jade", "Jamie", "Jana", "Joel", "Jonah", "Juno",
    "Kai", "Kara", "Kieran", "Lara", "Leah", "Leo", "Lila", "Lina", "Luca",
    "Mae", "Maya", "Miles", "Mina", "Nadia", "Nell", "Nia", "Noah", "Nora",
    "Obi", "Olive", "Omar", "Orla", "Owen", "Pia", "Rafi", "Raya", "Remi",
    "Rhea", "Rosa", "Ruben", "Ruth", "Sami", "Sana", "Sara", "Sean", "Seth",
    "Shay", "Sofia", "Sona", "Tara", "Theo", "Tilly", "Tom", "Una", "Veda",
    "Willa", "Yara", "Yusuf", "Zara", "Zoe",
]
LAST_NAMES = [
    "Abbott", "Achebe", "Ahmed", "Ali", "Allen", "Anand", "Andrews", "Armstrong",
    "Bailey", "Baines", "Barker", "Bennett", "Bhat", "Black", "Bolan", "Brennan",
    "Brown", "Bryant", "Byrne", "Campbell", "Carter", "Chan", "Clarke", "Cole",
    "Collins", "Cook", "Cooper", "Costa", "Cox", "Dalton", "Davies", "Dawson",
    "Diaz", "Dillon", "Doyle", "Duncan", "Edwards", "Ellis", "Evans", "Farrell",
    "Ferguson", "Fernandez", "Fischer", "Fitzgerald", "Fleming", "Foster", "Fox",
    "Fraser", "Gallagher", "Garcia", "Gibson", "Gill", "Grant", "Gray", "Green",
    "Hall", "Hamilton", "Hansen", "Harris", "Hart", "Hayes", "Henderson", "Hill",
    "Holmes", "Howard", "Hughes", "Hussain", "Ibrahim", "Jackson", "James", "Jensen",
    "Johnson", "Jones", "Kapoor", "Kelly", "Kennedy", "Khan", "Kumar", "Lane",
    "Lawson", "Lee", "Lewis", "Lloyd", "Lopez", "Lynch", "MacDonald", "Marsh",
    "Martin", "Mason", "Matthews", "McCarthy", "Mehta", "Miller", "Mitchell",
    "Moore", "Morgan", "Morris", "Murphy", "Nair", "Nelson", "Newman", "Nguyen",
    "Nichols", "O'Brien", "Okafor", "Owen", "Palmer", "Parker", "Patel", "Pearson",
    "Peters", "Phillips", "Poole", "Powell", "Price", "Quinn", "Rahman", "Reed",
    "Reid", "Reynolds", "Richardson", "Roberts", "Robertson", "Robinson", "Rogers",
    "Rose", "Ross", "Russell", "Said", "Sanders", "Scott", "Shah", "Sharma",
    "Shaw", "Simpson", "Singh", "Smith", "Spencer", "Stewart", "Stone", "Sullivan",
    "Taylor", "Thomas", "Thompson", "Turner", "Walker", "Wallace", "Walsh", "Ward",
    "Watson", "Webb", "Wells", "West", "White", "Williams", "Wilson", "Wood",
    "Wright", "Young",
]
REGIONS = [
    ("Greater London", "London", 0.25),
    ("South East", "Brighton", 0.15),
    ("South West", "Bristol", 0.11),
    ("North West", "Manchester", 0.13),
    ("Yorkshire", "Leeds", 0.09),
    ("West Midlands", "Birmingham", 0.09),
    ("Scotland", "Edinburgh", 0.08),
    ("East of England", "Cambridge", 0.06),
    ("Wales", "Cardiff", 0.04),
]
CHANNELS = [("online", 0.62), ("store", 0.31), ("app", 0.07)]
STORES = {
    "S-04": "Morrow & Finch, Marylebone",
    "S-07": "Morrow & Finch, Bath",
    "S-11": "Morrow & Finch, Manchester",
    "S-15": "Morrow & Finch, Edinburgh",
    "S-18": "Morrow & Finch, Leeds",
    "S-22": "Morrow & Finch, Brighton",
}
CATEGORY_WEIGHTS = [
    ("apparel", 0.38, (3500, 12500), [
        "Ribbed merino crew", "Washed cotton overshirt", "Pleated wool trouser",
        "Linen camp collar shirt", "Heavyweight jersey tee", "Quilted patch jacket",
    ]),
    ("footwear", 0.22, (4500, 15500), [
        "Suede field shoe", "Leather derby, oak", "Canvas low trainer",
        "Chelsea boot, waxed", "Walking sandal, moss",
    ]),
    ("home", 0.16, (1800, 8500), [
        "Stoneware serving bowl", "Brushed cotton throw", "Oak desk tray",
        "Beeswax pillar candle", "Ribbed glass tumbler, set of two",
    ]),
    ("beauty", 0.12, (900, 4800), [
        "Cedar hand wash", "Botanical face oil", "Mineral bath soak",
        "Vetiver travel candle", "Rosehip body balm",
    ]),
    ("accessories", 0.08, (1200, 6500), [
        "Waxed canvas pouch", "Woven leather belt", "Merino beanie",
        "Brass key ring", "Linen pocket square",
    ]),
    ("gift_card", 0.04, (2500, 10000), [
        "Morrow & Finch gift card", "E-gift card",
    ]),
]
CATEGORY_MAP = {c[0]: c for c in CATEGORY_WEIGHTS}
CHANNEL_MAP = dict(CHANNELS)
RETURNS_BY_CHANNEL = {
    "online": (0.055, 0.145),
    "app": (0.06, 0.16),
    "store": (0.02, 0.075),
}

TIERS = [
    {"tier_id": "TIER-01", "tier_name": "Member", "rank": 1, "qualify_spend_cents": 0,
     "valid_from": "2024-01-01", "valid_to": "", "status": "active"},
    {"tier_id": "TIER-02", "tier_name": "Silver", "rank": 2, "qualify_spend_cents": 10000,
     "valid_from": "2024-01-01", "valid_to": "", "status": "active"},
    {"tier_id": "TIER-03", "tier_name": "Gold", "rank": 3, "qualify_spend_cents": 35000,
     "valid_from": "2024-01-01", "valid_to": "", "status": "active"},
    {"tier_id": "TIER-04", "tier_name": "Platinum", "rank": 4, "qualify_spend_cents": 80000,
     "valid_from": "2024-01-01", "valid_to": "", "status": "active"},
]

EARN_RULES = [
    {
        "rule_id": "RULE-EARN-2024-V1",
        "rule_code": "EARN_RATE",
        "version": 1,
        "name": "Earn rate, 2024 schedule",
        "effective_from": "2024-01-01T00:00:00Z",
        "effective_to": "2025-12-31T23:59:59Z",
        "parameters": {"points_per_gbp": 10, "rounding": "floor", "basis": "net_eligible_line_spend"},
        "status": "superseded",
    },
    {
        "rule_id": "RULE-EARN-2026-V2",
        "rule_code": "EARN_RATE",
        "version": 2,
        "name": "Earn rate, 2026 schedule",
        "effective_from": "2026-01-01T00:00:00Z",
        "effective_to": "",
        "parameters": {"points_per_gbp": 10, "rounding": "floor", "basis": "net_eligible_line_spend"},
        "status": "active",
    },
    {
        "rule_id": "RULE-REDEEM-V2",
        "rule_code": "REDEMPTION",
        "version": 2,
        "name": "Reward redemption",
        "effective_from": "2024-01-01T00:00:00Z",
        "effective_to": "",
        "parameters": {"points_per_gbp": 100, "minimum_points": 300,
                       "max_share_of_basket": 0.5, "one_open_attempt_per_account": True},
        "status": "active",
    },
    {
        "rule_id": "RULE-EXPIRY-V1",
        "rule_code": "EXPIRY",
        "version": 1,
        "name": "Points expiry by lot",
        "effective_from": "2024-01-01T00:00:00Z",
        "effective_to": "",
        "parameters": {"accrual_months": 24, "bonus_months": 12, "allocation": "expiry_first"},
        "status": "active",
    },
    {
        "rule_id": "RULE-TIER-V1",
        "rule_code": "TIER_REVIEW",
        "version": 1,
        "name": "Trailing twelve-month tier review",
        "effective_from": "2024-01-01T00:00:00Z",
        "effective_to": "",
        "parameters": {"lookback_days": 365, "review_cadence": "on activity + annual_review",
                       "basis": "net_eligible_spend_after_returns"},
        "status": "active",
    },
    {
        "rule_id": "RULE-BONUS-V1",
        "rule_code": "BONUS",
        "version": 1,
        "name": "Campaign and welcome bonus",
        "effective_from": "2024-01-01T00:00:00Z",
        "effective_to": "",
        "parameters": {"expiry_months": 12, "max_points": 500},
        "status": "active",
    },
]

TIER_RATES = {
    "RULE-EARN-2024-V1": {"TIER-01": 1.0, "TIER-02": 1.2, "TIER-03": 1.4, "TIER-04": 1.8},
    "RULE-EARN-2026-V2": {"TIER-01": 1.0, "TIER-02": 1.25, "TIER-03": 1.5, "TIER-04": 2.0},
}
TIER_BY_RANK = {t["rank"]: t for t in TIERS}
TIER_BY_ID = {t["tier_id"]: t for t in TIERS}

REWARDS = [
    {"reward_id": "RWD-01", "reward_name": "Free standard delivery", "category": "delivery",
     "points_cost": 300, "cash_value_cents": 499, "min_tier_rank": 1, "status": "active",
     "effective_from": "2024-01-01", "effective_to": ""},
    {"reward_id": "RWD-02", "reward_name": "£5 reward voucher", "category": "voucher",
     "points_cost": 500, "cash_value_cents": 500, "min_tier_rank": 1, "status": "active",
     "effective_from": "2024-01-01", "effective_to": ""},
    {"reward_id": "RWD-03", "reward_name": "£10 reward voucher", "category": "voucher",
     "points_cost": 1000, "cash_value_cents": 1000, "min_tier_rank": 1, "status": "active",
     "effective_from": "2024-01-01", "effective_to": ""},
    {"reward_id": "RWD-04", "reward_name": "Morrow canvas tote", "category": "merchandise",
     "points_cost": 1200, "cash_value_cents": 1800, "min_tier_rank": 2, "status": "active",
     "effective_from": "2024-03-01", "effective_to": ""},
    {"reward_id": "RWD-05", "reward_name": "£25 reward voucher", "category": "voucher",
     "points_cost": 2500, "cash_value_cents": 2500, "min_tier_rank": 2, "status": "active",
     "effective_from": "2024-01-01", "effective_to": ""},
    {"reward_id": "RWD-06", "reward_name": "Priority alterations", "category": "service",
     "points_cost": 1800, "cash_value_cents": 2200, "min_tier_rank": 3, "status": "active",
     "effective_from": "2024-06-01", "effective_to": ""},
    {"reward_id": "RWD-07", "reward_name": "£50 reward voucher", "category": "voucher",
     "points_cost": 5000, "cash_value_cents": 5000, "min_tier_rank": 3, "status": "active",
     "effective_from": "2024-01-01", "effective_to": ""},
    {"reward_id": "RWD-08", "reward_name": "Archive print, limited", "category": "merchandise",
     "points_cost": 3200, "cash_value_cents": 4000, "min_tier_rank": 4, "status": "retired",
     "effective_from": "2024-02-01", "effective_to": "2025-12-31"},
]
REWARD_BY_ID = {r["reward_id"]: r for r in REWARDS}

REWARD_RATES = {
    "RWD-01": [1, 2, 3, 4],
    "RWD-02": [1, 2, 3, 4],
    "RWD-03": [1, 2, 3, 4],
    "RWD-04": [2, 3, 4],
    "RWD-05": [2, 3, 4],
    "RWD-06": [3, 4],
    "RWD-07": [3, 4],
    "RWD-08": [4],
}

DATA_DICTIONARY = [
    {
        "entity": "Customer", "table": "customers", "primary_key": "customer_id",
        "description": "A person enrolled in the Morrow & Finch loyalty programme. No real personal data is used.",
        "fields": [
            ["customer_id", "string", "yes", "C-000001", "unique", "Regex ^C-\\d{6}$; immutable"],
            ["first_name", "string", "yes", "Aisha", "-", "2–40 chars; synthetic name"],
            ["last_name", "string", "yes", "Patel", "-", "2–40 chars; synthetic name"],
            ["email", "string", "yes", "aisha.patel.00001@example.test", "unique", "RFC 5322 basic pattern; .test domain only"],
            ["region", "enum", "yes", "Greater London", "-", "One of the nine configured regions"],
            ["city", "string", "yes", "London", "-", "Must match region lookup"],
            ["acquisition_channel", "enum", "yes", "online", "-", "online | store | app | referral"],
            ["marketing_consent", "boolean", "yes", "true", "-", "True or false; independent of programme state"],
            ["status", "enum", "yes", "active", "-", "active | inactive | deactivated"],
            ["joined_at", "datetime", "yes", "2023-04-18T10:22:00Z", "-", "Before first account activity"],
            ["updated_at", "datetime", "yes", "2026-10-31T18:00:00Z", "-", "At or after joined_at"],
        ],
    },
    {
        "entity": "LoyaltyAccount", "table": "loyalty_accounts", "primary_key": "account_id",
        "description": "One programme account per customer; the materialised balance is derived from the ledger.",
        "fields": [
            ["account_id", "string", "yes", "LOY-C-000001", "unique", "Regex ^LOY-C-\\d{6}$; 1:1 with customer_id"],
            ["customer_id", "string FK", "yes", "C-000001", "unique", "References customers.customer_id"],
            ["tier_id", "string FK", "yes", "TIER-02", "-", "References tiers.tier_id"],
            ["opened_at", "datetime", "yes", "2023-04-18T10:22:00Z", "-", "Must equal or follow customer.joined_at"],
            ["status", "enum", "yes", "active", "-", "active | suspended | closed"],
            ["available_points", "integer", "yes", "1840", "-", ">= 0 in valid rows; equals ledger sum unless labelled mismatch"],
            ["pending_points", "integer", "yes", "0", "-", ">= 0; pending earns are excluded from available balance"],
            ["lifetime_earned_points", "integer", "yes", "12680", "-", "Sum of positive accrual, bonus and adjustment rows"],
            ["qualifying_spend_cents", "integer", "yes", "54820", "GBP cents", "Trailing 365-day net eligible spend after returns"],
            ["tier_reviewed_at", "datetime", "yes", "2026-10-01T00:00:00Z", "-", "Effective date of current tier"],
            ["last_activity_at", "datetime", "no", "2026-10-30T14:16:00Z", "-", "Maximum posted_at across ledger rows"],
            ["updated_at", "datetime", "yes", "2026-11-01T09:00:00Z", "-", "Snapshot materialisation time"],
        ],
    },
    {
        "entity": "Tier", "table": "tiers", "primary_key": "tier_id",
        "description": "Configured membership tier and its qualifying-spend threshold.",
        "fields": [
            ["tier_id", "string", "yes", "TIER-02", "unique", "Regex ^TIER-\\d{2}$"],
            ["tier_name", "string", "yes", "Silver", "unique", "Member | Silver | Gold | Platinum"],
            ["rank", "integer", "yes", "2", "ordinal", "1–4; strictly increasing"],
            ["qualify_spend_cents", "integer", "yes", "10000", "GBP cents", ">= 0; monotonic by rank"],
            ["valid_from", "date", "yes", "2024-01-01", "-", "Effective date"],
            ["valid_to", "date", "no", "", "-", "Null means open-ended; >= valid_from"],
            ["status", "enum", "yes", "active", "-", "active | retired"],
        ],
    },
    {
        "entity": "Rule", "table": "rules", "primary_key": "rule_id",
        "description": "Versioned earning, redemption, expiry, tier and bonus policy with effective dates.",
        "fields": [
            ["rule_id", "string", "yes", "RULE-EARN-2024-V1", "unique", "Immutable; version suffix required"],
            ["rule_code", "enum", "yes", "EARN_RATE", "-", "EARN_RATE | REDEMPTION | EXPIRY | TIER_REVIEW | BONUS"],
            ["version", "integer", "yes", "1", "-", ">= 1; unique per rule_code"],
            ["name", "string", "yes", "Earn rate, 2024 schedule", "-", "Human-readable policy name"],
            ["effective_from", "datetime", "yes", "2024-01-01T00:00:00Z", "-", "Start of validity"],
            ["effective_to", "datetime", "no", "2025-12-31T23:59:59Z", "-", "Null means current; later than effective_from"],
            ["parameters", "json", "yes", "{\"points_per_gbp\":10}", "-", "Validated key/value policy object"],
            ["status", "enum", "yes", "active", "-", "draft | active | superseded"],
        ],
    },
    {
        "entity": "Order", "table": "orders", "primary_key": "order_id",
        "description": "A completed purchase used as the source for accrual and return events.",
        "fields": [
            ["order_id", "string", "yes", "ORD-2026-000001", "unique", "Regex ^ORD-\\d{4}-\\d{6}$; year matches order_ts"],
            ["customer_id", "string FK", "yes", "C-000001", "-", "References customers.customer_id"],
            ["account_id", "string FK", "yes", "LOY-C-000001", "-", "References loyalty_accounts.account_id"],
            ["order_ts", "datetime", "yes", "2026-10-17T14:32:00Z", "-", "Within dataset window; after account open"],
            ["channel", "enum", "yes", "online", "-", "online | store | app"],
            ["store_id", "string FK", "no", "S-11", "-", "Required for store orders; null otherwise"],
            ["gross_cents", "integer", "yes", "12800", "GBP cents", ">= 0; equals sum of line gross"],
            ["discount_cents", "integer", "yes", "1280", "GBP cents", ">= 0; <= gross"],
            ["tax_cents", "integer", "yes", "2304", "GBP cents", "= floor((gross-discount) × 20%)"],
            ["shipping_cents", "integer", "yes", "0", "GBP cents", "0 | 499 | 699"],
            ["net_eligible_cents", "integer", "yes", "11520", "GBP cents", "Sum of eligible line net; excludes gift cards, tax and shipping"],
            ["refund_cents", "integer", "yes", "0", "GBP cents", "0–(gross-discount); ties to returned_qty"],
            ["status", "enum", "yes", "completed", "-", "completed | partially_returned | returned | voided"],
            ["returned_at", "datetime", "no", "", "-", "Required iff status is partially_returned or returned; after order_ts"],
        ],
    },
    {
        "entity": "OrderLine", "table": "order_lines", "primary_key": "order_line_id",
        "description": "Product-level purchase line. Points accrue per eligible line, giving source-level traceability.",
        "fields": [
            ["order_line_id", "string", "yes", "OL-2026-000001", "unique", "Regex ^OL-\\d{4}-\\d{6}$"],
            ["order_id", "string FK", "yes", "ORD-2026-000001", "-", "References orders.order_id"],
            ["sku", "string", "yes", "APP-1042", "unique per category", "Synthetic SKU; no real catalogue data"],
            ["product_name", "string", "yes", "Ribbed merino crew", "-", "Synthetic product label"],
            ["category", "enum", "yes", "apparel", "-", "apparel | footwear | home | beauty | accessories | gift_card"],
            ["quantity", "integer", "yes", "1", "units", "1–4"],
            ["unit_price_cents", "integer", "yes", "6500", "GBP cents", "> 0"],
            ["discount_cents", "integer", "yes", "650", "GBP cents", "0 <= discount <= quantity × unit_price"],
            ["line_net_cents", "integer", "yes", "5850", "GBP cents", "quantity × unit_price - discount"],
            ["eligible_for_points", "boolean", "yes", "true", "-", "False for gift_card category"],
            ["returned_qty", "integer", "yes", "0", "units", "0–quantity; zero if not returned"],
            ["returned_amount_cents", "integer", "yes", "0", "GBP cents", "0 <= returned_amount <= line_net"],
        ],
    },
    {
        "entity": "PointsTransaction", "table": "points_transactions", "primary_key": "points_txn_id",
        "description": "Immutable, signed points ledger. Positive rows create lots; negative rows consume or remove them.",
        "fields": [
            ["points_txn_id", "string", "yes", "PTS-2026-00000001", "unique", "Regex ^PTS-\\d{4}-\\d{8}$; immutable"],
            ["account_id", "string FK", "yes", "LOY-C-000001", "-", "References loyalty_accounts.account_id"],
            ["txn_type", "enum", "yes", "ACCRUAL", "-", "ACCRUAL | REVERSAL | REDEMPTION | EXPIRATION | BONUS | ADJUSTMENT"],
            ["points_delta", "integer", "yes", "248", "points", "Non-zero; positive for ACCRUAL/BONUS/ADJUSTMENT, negative otherwise"],
            ["posted_at", "datetime", "yes", "2026-10-17T14:34:00Z", "-", "Chronological ledger time; no updates"],
            ["status", "enum", "yes", "posted", "-", "posted | reversed | partially_reversed"],
            ["source_order_id", "string FK", "no", "ORD-2026-000001", "-", "Required for ACCRUAL and order-linked REVERSAL"],
            ["source_order_line_id", "string FK", "no", "OL-2026-000001", "-", "Required for line-level ACCRUAL and REVERSAL"],
            ["reversal_of_pts_id", "string FK", "no", "", "-", "Required for REVERSAL; references an ACCRUAL row"],
            ["redemption_id", "string FK", "no", "", "-", "Required for REDEMPTION; references redemptions.redemption_id"],
            ["expiry_batch_id", "string FK", "no", "", "-", "Required for EXPIRATION; references expiry_batches.expiry_batch_id"],
            ["expiry_source_pts_id", "string FK", "no", "", "-", "For EXPIRATION, the accrual/bonus lot that expired"],
            ["rule_id", "string FK", "yes", "RULE-EARN-2026-V2", "-", "Policy applied at posting time"],
            ["tier_id_at_post", "string FK", "no", "TIER-02", "-", "Tier used for earning; null for non-accrual rows"],
            ["earn_multiplier", "decimal", "no", "1.25", "multiplier", "Present for ACCRUAL rows; matches rule-tier bridge"],
            ["expires_at", "datetime", "no", "2028-10-17T14:34:00Z", "-", "Required for positive earning rows; later than posted_at"],
            ["description", "string", "yes", "Line accrual · ORD-2026-000001", "-", "Non-empty audit narrative"],
        ],
    },
    {
        "entity": "Reward", "table": "rewards", "primary_key": "reward_id",
        "description": "Catalogue item that can be redeemed for points. Tier eligibility is many-to-many.",
        "fields": [
            ["reward_id", "string", "yes", "RWD-02", "unique", "Regex ^RWD-\\d{2}$"],
            ["reward_name", "string", "yes", "£5 reward voucher", "-", "Human-readable label"],
            ["category", "enum", "yes", "voucher", "-", "voucher | delivery | merchandise | service"],
            ["points_cost", "integer", "yes", "500", "points", "> 0; multiple of 100"],
            ["cash_value_cents", "integer", "yes", "500", "GBP cents", ">= 0; liability reference only"],
            ["min_tier_rank", "integer", "yes", "1", "ordinal", "1–4; mirrored by reward_tier_eligibility"],
            ["status", "enum", "yes", "active", "-", "active | retired"],
            ["effective_from", "date", "yes", "2024-01-01", "-", "Start of catalogue period"],
            ["effective_to", "date", "no", "", "-", "Null means open-ended"],
        ],
    },
    {
        "entity": "Redemption", "table": "redemptions", "primary_key": "redemption_id",
        "description": "One redemption attempt and its evaluated decision. Rejected attempts are retained and never posted.",
        "fields": [
            ["redemption_id", "string", "yes", "RDM-2026-000001", "unique", "Regex ^RDM-\\d{4}-\\d{6}$; immutable"],
            ["account_id", "string FK", "yes", "LOY-C-000001", "-", "References loyalty_accounts.account_id"],
            ["reward_id", "string FK", "yes", "RWD-02", "-", "References rewards.reward_id"],
            ["requested_at", "datetime", "yes", "2026-06-18T11:03:00Z", "-", "After account open"],
            ["points_requested", "integer", "yes", "500", "points", "> 0; equals reward points_cost"],
            ["status", "enum", "yes", "approved", "-", "approved | rejected"],
            ["decision_reason", "enum", "yes", "approved", "-", "approved | insufficient_balance | concurrent_lock | reward_inactive | below_minimum | account_suspended"],
            ["balance_before", "integer", "yes", "1820", "points", "Account ledger balance immediately before decision"],
            ["balance_after", "integer", "yes", "1320", "points", "Equals balance_before less approved points"],
            ["points_txn_id", "string FK", "no", "PTS-2026-00000218", "-", "Required iff approved; references points_transactions.points_txn_id"],
            ["request_group_id", "string", "no", "", "-", "Set for concurrent attempts; at most one approval per group"],
        ],
    },
    {
        "entity": "ExpiryBatch", "table": "expiry_batches", "primary_key": "expiry_batch_id",
        "description": "Idempotent expiry run. Each batch removes remaining points from one or more due lots for one account.",
        "fields": [
            ["expiry_batch_id", "string", "yes", "EXP-2026-000001", "unique", "Regex ^EXP-\\d{4}-\\d{6}$"],
            ["account_id", "string FK", "yes", "LOY-C-000001", "-", "References loyalty_accounts.account_id"],
            ["run_at", "datetime", "yes", "2026-09-01T00:00:00Z", "-", "Batch cut-off; >= each expired lot's expires_at"],
            ["points_expired", "integer", "yes", "420", "points", "> 0; equals sum of linked EXPIRATION rows"],
            ["lot_count", "integer", "yes", "2", "lots", ">= 1; count of distinct expiry_source_pts_id rows"],
            ["idempotency_key", "string", "yes", "exp:LOY-C-000001:2026-09", "unique", "Unique in valid rows; duplicate intentionally labelled"],
            ["status", "enum", "yes", "posted", "-", "posted | void"],
            ["rule_id", "string FK", "yes", "RULE-EXPIRY-V1", "-", "References rules.rule_id"],
            ["created_at", "datetime", "yes", "2026-09-01T00:00:04Z", "-", "Posting timestamp"],
        ],
    },
    {
        "entity": "TierHistory", "table": "tier_history", "primary_key": "history_id",
        "description": "Append-only account tier changes, with the qualifying spend and rule that caused the change.",
        "fields": [
            ["history_id", "string", "yes", "TH-2026-000001", "unique", "Regex ^TH-\\d{4}-\\d{6}$"],
            ["account_id", "string FK", "yes", "LOY-C-000001", "-", "References loyalty_accounts.account_id"],
            ["from_tier_id", "string FK", "no", "", "-", "Null on opening tier; otherwise references tiers"],
            ["to_tier_id", "string FK", "yes", "TIER-02", "-", "References tiers.tier_id"],
            ["changed_at", "datetime", "yes", "2026-04-02T12:00:00Z", "-", "After account open; append-only"],
            ["reason", "enum", "yes", "rolling_spend_upgrade", "-", "opening | rolling_spend_upgrade | annual_review_downgrade | correction"],
            ["qualifying_spend_cents", "integer", "yes", "41200", "GBP cents", "Trailing 365-day net eligible spend at decision"],
            ["rule_id", "string FK", "yes", "RULE-TIER-V1", "-", "References rules.rule_id"],
        ],
    },
]

TABLES = [
    "customers", "loyalty_accounts", "tiers", "rules", "rewards",
    "reward_tier_eligibility", "rule_tier_rate", "tier_history",
    "orders", "order_lines", "points_transactions", "redemptions",
    "expiry_batches", "ground_truth",
]


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def uid_number(value: str) -> str:
    return value.split("-")[-1]


def weighted_choice(rng: random.Random, pairs):
    values = [p[0] for p in pairs]
    weights = [p[1] for p in pairs]
    return rng.choices(values, weights=weights, k=1)[0]


def random_dt(rng: random.Random, start: datetime, end: datetime) -> datetime:
    span = int((end - start).total_seconds())
    return start + timedelta(seconds=rng.randrange(span))


def business_ts(rng: random.Random, start: datetime, end: datetime) -> datetime:
    """Timestamp with a plausible weekday, hour and seasonal weighting."""
    dt = random_dt(rng, start, end)
    # Pull a small share of orders back from the exact midnight boundary.
    if dt.hour < 7:
        dt = dt.replace(hour=rng.randint(8, 11))
    elif dt.hour > 21:
        dt = dt.replace(hour=rng.randint(17, 20))
    return dt.replace(minute=rng.randint(0, 59), second=rng.randint(0, 59), microsecond=0)


def pct(n: int, d: int) -> float:
    return round((n / d * 100.0), 2) if d else 0.0


def money(cents: int) -> str:
    return f"£{cents / 100:,.2f}"


def new_rng(seed: int) -> random.Random:
    return random.Random(seed)


def build_master_tables(rng: random.Random):
    """Rules, tiers, reward catalogue and bridge tables."""
    tiers = [dict(t) for t in TIERS]
    rules = []
    for r in EARN_RULES:
        row = dict(r)
        row["parameters"] = json.dumps(r["parameters"], sort_keys=True, separators=(",", ":"))
        rules.append(row)

    rules_tier_rate = []
    for rule_id, rates in TIER_RATES.items():
        for tier_id, multiplier in rates.items():
            rules_tier_rate.append({
                "rule_id": rule_id,
                "tier_id": tier_id,
                "earn_multiplier": f"{multiplier:.2f}",
                "effective_from": "2024-01-01" if "2024" in rule_id else "2026-01-01",
            })

    reward_eligibility = []
    for reward in REWARDS:
        for tier in TIERS:
            if tier["rank"] >= reward["min_tier_rank"]:
                reward_eligibility.append({
                    "reward_id": reward["reward_id"],
                    "tier_id": tier["tier_id"],
                    "eligible": "true",
                })

    return {
        "tiers": tiers,
        "rules": rules,
        "rewards": [dict(r) for r in REWARDS],
        "rule_tier_rate": rules_tier_rate,
        "reward_tier_eligibility": reward_eligibility,
    }


def build_customers(rng: random.Random, n_customers: int):
    customers = []
    accounts = []
    region_values = [(r[0], r[2]) for r in REGIONS]
    channel_values = [
        ("online", 0.44), ("store", 0.23), ("app", 0.21), ("referral", 0.12)
    ]

    for i in range(1, n_customers + 1):
        first = FIRST_NAMES[(i - 1) % len(FIRST_NAMES)]
        last = LAST_NAMES[((i - 1) * 17 + (i - 1) // len(FIRST_NAMES)) % len(LAST_NAMES)]
        region = weighted_choice(rng, region_values)
        city = next(r[1] for r in REGIONS if r[0] == region)
        customer_id = f"C-{i:06d}"
        account_id = f"LOY-{customer_id}"
        joined = business_ts(
            rng,
            datetime(2022, 1, 4, 8, 0, tzinfo=UTC),
            datetime(2023, 12, 20, 20, 0, tzinfo=UTC),
        )
        # Customer statuses are mostly healthy, with the long tail every
        # programme carries after several years.
        status_roll = rng.random()
        if status_roll < 0.011:
            customer_status = "deactivated"
            account_status = "closed"
        elif status_roll < 0.028:
            customer_status = "inactive"
            account_status = "suspended"
        else:
            customer_status = "active"
            account_status = "active"

        marketing = rng.random() > 0.29
        acquisition = weighted_choice(rng, channel_values)
        last_slug = last.lower().replace("'", "")
        email = f"{first.lower()}.{last_slug}.{i:05d}@example.test"
        customers.append({
            "customer_id": customer_id,
            "first_name": first,
            "last_name": last,
            "email": email,
            "region": region,
            "city": city,
            "acquisition_channel": acquisition,
            "marketing_consent": "true" if marketing else "false",
            "status": customer_status,
            "joined_at": iso(joined),
            "updated_at": iso(AS_OF),
            "_joined_dt": joined,
        })
        accounts.append({
            "account_id": account_id,
            "customer_id": customer_id,
            "tier_id": "TIER-01",
            "opened_at": iso(joined),
            "status": account_status,
            "available_points": 0,
            "pending_points": 0,
            "lifetime_earned_points": 0,
            "qualifying_spend_cents": 0,
            "tier_reviewed_at": iso(joined),
            "last_activity_at": "",
            "updated_at": iso(AS_OF),
            "_opened_dt": joined,
            "_joined_dt": joined,
            "_current_rank": 1,
            "_balance": 0,
            "_activity_weight": 0.0,
        })

    return customers, accounts


def build_reward_catalogue():
    return [dict(r) for r in REWARDS]


def tier_rank_for_spend(cents: int) -> int:
    rank = 1
    for tier in sorted(TIERS, key=lambda t: t["rank"]):
        if cents >= tier["qualify_spend_cents"]:
            rank = tier["rank"]
    return rank


def _category_choice(rng: random.Random):
    return weighted_choice(rng, [(c[0], c[1]) for c in CATEGORY_WEIGHTS])


def build_orders(rng: random.Random, customers, accounts, n_orders: int):
    """Build orders and order lines. Accruals and reversals are derived later."""
    customer_by_id = {c["customer_id"]: c for c in customers}
    active_accounts = [a for a in accounts if a["status"] == "active"]
    if not active_accounts:
        active_accounts = accounts

    # A realistic long tail: most members order occasionally; a small cohort
    # carries a disproportionate share of orders.
    activity = []
    for account in active_accounts:
        weight = rng.lognormvariate(0.15, 0.72)
        if rng.random() < 0.16:
            weight *= 0.14
        account["_activity_weight"] = weight
        activity.append((account, weight))
    acct_values = [a[0] for a in activity]
    acct_weights = [a[1] for a in activity]

    orders = []
    for i in range(n_orders):
        account = rng.choices(acct_values, weights=acct_weights, k=1)[0]
        customer = customer_by_id[account["customer_id"]]
        ts = business_ts(rng, DATA_START, DATA_END)
        opened = account["_opened_dt"]
        if ts <= opened:
            ts = opened + timedelta(days=rng.randint(5, 240), hours=rng.randint(1, 8))
            if ts > DATA_END:
                ts = DATA_END - timedelta(days=rng.randint(1, 20))

        channel = weighted_choice(rng, CHANNELS)
        store_id = rng.choice(list(STORES.keys())) if channel == "store" else ""
        line_count = weighted_choice(rng, [(1, 0.30), (2, 0.46), (3, 0.19), (4, 0.05)])

        lines = []
        gross = 0
        discount_total = 0
        eligible_net = 0
        for j in range(line_count):
            category = _category_choice(rng)
            category_name, _, price_range, product_names = CATEGORY_MAP[category]
            if category_name == "gift_card" and j > 0 and rng.random() < 0.7:
                category_name = "apparel"
                _, _, price_range, product_names = CATEGORY_MAP[category_name]

            quantity = 1
            if category_name == "beauty" and rng.random() < 0.18:
                quantity = 2
            elif category_name == "home" and rng.random() < 0.05:
                quantity = 2

            unit_price = rng.randrange(price_range[0], price_range[1] + 1)
            # Round to a credible shelf price ending in 00, 50 or 95.
            unit_price = int(round(unit_price / 50.0)) * 50 + rng.choice([0, 0, 0, 0, 50, 95])
            unit_price = max(unit_price, 250)
            discount_pct = weighted_choice(
                rng, [(0, 0.54), (5, 0.14), (10, 0.18), (15, 0.10), (20, 0.03), (25, 0.01)]
            )
            line_gross = unit_price * quantity
            line_discount = int(round(line_gross * discount_pct / 100.0))
            line_net = line_gross - line_discount
            eligible = category_name != "gift_card"
            sku_prefix = {
                "apparel": "APP", "footwear": "FTW", "home": "HME",
                "beauty": "BTY", "accessories": "ACC", "gift_card": "GFT",
            }[category_name]
            lines.append({
                "order_line_id": "",
                "order_id": "",
                "sku": f"{sku_prefix}-{rng.randint(1000, 9999)}",
                "product_name": rng.choice(product_names),
                "category": category_name,
                "quantity": quantity,
                "unit_price_cents": unit_price,
                "discount_cents": line_discount,
                "line_net_cents": line_net,
                "eligible_for_points": "true" if eligible else "false",
                "returned_qty": 0,
                "returned_amount_cents": 0,
                "_line_gross": line_gross,
                "_eligible": eligible,
                "_returned_points": 0,
                "_points": 0,
                "_accrual_key": "",
            })
            gross += line_gross
            discount_total += line_discount
            if eligible:
                eligible_net += line_net

        shipping = 0 if gross >= 7500 else rng.choice([0, 499, 699])
        taxable = gross - discount_total
        tax = int(math.floor(taxable * 0.2))
        return_possible = ts + timedelta(days=4) <= AS_OF - timedelta(hours=12)
        full_rate, partial_rate = RETURNS_BY_CHANNEL[channel]
        return_roll = rng.random() if return_possible else 1.0
        status = "completed"
        returned_at = None
        refund = 0
        if return_roll < full_rate:
            status = "returned"
            returned_at = ts + timedelta(days=rng.randint(4, 36), hours=rng.randint(0, 12))
            if returned_at > AS_OF:
                returned_at = AS_OF - timedelta(hours=6)
            refund = sum(l["line_net_cents"] for l in lines if l["_eligible"])
            for line in lines:
                if line["_eligible"]:
                    line["returned_qty"] = line["quantity"]
                    line["returned_amount_cents"] = line["line_net_cents"]
        elif return_roll < full_rate + partial_rate:
            status = "partially_returned"
            returned_at = ts + timedelta(days=rng.randint(4, 44), hours=rng.randint(0, 12))
            if returned_at > AS_OF:
                returned_at = AS_OF - timedelta(hours=6)
            eligible_lines = [l for l in lines if l["_eligible"] and l["quantity"] > 0]
            if eligible_lines:
                line = rng.choice(eligible_lines)
                qty = line["quantity"] if rng.random() < 0.56 else 1
                qty = max(1, min(qty, line["quantity"]))
                line["returned_qty"] = qty
                line["returned_amount_cents"] = int(round(line["line_net_cents"] * qty / line["quantity"]))
                refund = line["returned_amount_cents"]
        if rng.random() < 0.0015:
            status = "voided"
            returned_at = None
            refund = 0
            for line in lines:
                line["returned_qty"] = 0
                line["returned_amount_cents"] = 0

        orders.append({
            "order_id": "",
            "customer_id": customer["customer_id"],
            "account_id": account["account_id"],
            "order_ts": iso(ts),
            "channel": channel,
            "store_id": store_id,
            "gross_cents": gross,
            "discount_cents": discount_total,
            "tax_cents": tax,
            "shipping_cents": shipping,
            "net_eligible_cents": eligible_net,
            "refund_cents": refund,
            "status": status,
            "returned_at": iso(returned_at) if returned_at else "",
            "_order_dt": ts,
            "_returned_dt": returned_at,
            "_lines": lines,
            "_accruals": [],
            "_reversals": [],
            "_missing_reversal": False,
        })

    # Assign immutable IDs after ordering by time.
    orders.sort(key=lambda o: (o["_order_dt"], o["customer_id"]))
    year_counters = defaultdict(int)
    line_year_counters = defaultdict(int)
    for order in orders:
        year = order["_order_dt"].year
        year_counters[year] += 1
        order["order_id"] = f"ORD-{year}-{year_counters[year]:06d}"
        for line in order["_lines"]:
            line_year_counters[year] += 1
            line["order_id"] = order["order_id"]
            line["order_line_id"] = f"OL-{year}-{line_year_counters[year]:06d}"

    # Identify the deliberate "returned order keeps all points" cases.
    fully_returned = [
        o for o in orders
        if o["status"] == "returned" and o["refund_cents"] > 0
    ]
    missing_reversal_orders = set()
    rng.shuffle(fully_returned)
    for order in fully_returned:
        if len(missing_reversal_orders) >= 24:
            break
        if any(l["_eligible"] for l in order["_lines"]):
            order["_missing_reversal"] = True
            missing_reversal_orders.add(order["order_id"])

    by_account = defaultdict(list)
    for order in orders:
        by_account[order["account_id"]].append(order)
    return orders, by_account, missing_reversal_orders


def apply_tiers_and_accruals(rng: random.Random, accounts, by_account, orders):
    """Derive tier history and line-level accruals from eligible net spend."""
    from collections import deque

    accruals = []
    reversals = []
    tier_history = []
    account_by_id = {a["account_id"]: a for a in accounts}
    rule_v1 = "RULE-EARN-2024-V1"
    rule_v2 = "RULE-EARN-2026-V2"

    for account in accounts:
        acct_orders = sorted(by_account.get(account["account_id"], []), key=lambda o: o["_order_dt"])
        current_rank = 1
        tier_history.append({
            "history_id": "",
            "account_id": account["account_id"],
            "from_tier_id": "",
            "to_tier_id": "TIER-01",
            "changed_at": account["opened_at"],
            "reason": "opening",
            "qualifying_spend_cents": 0,
            "rule_id": "RULE-TIER-V1",
            "_changed_dt": account["_opened_dt"],
        })
        rolling = deque()
        for order in acct_orders:
            if order["status"] == "voided":
                continue
            earn_rule = rule_v2 if order["_order_dt"] >= datetime(2026, 1, 1, tzinfo=UTC) else rule_v1
            rate = TIER_RATES[earn_rule][TIER_BY_RANK[current_rank]["tier_id"]]
            for line in order["_lines"]:
                if not line["_eligible"]:
                    continue
                points = int(math.floor(line["line_net_cents"] * 10 / 100.0 * rate))
                if points <= 0:
                    continue
                line["_points"] = points
                accrual_key = f"A-{line['order_line_id']}"
                line["_accrual_key"] = accrual_key
                posted = order["_order_dt"] + timedelta(seconds=90)
                accrual = {
                    "points_txn_id": "",
                    "account_id": account["account_id"],
                    "txn_type": "ACCRUAL",
                    "points_delta": points,
                    "posted_at": iso(posted),
                    "status": "posted",
                    "source_order_id": order["order_id"],
                    "source_order_line_id": line["order_line_id"],
                    "reversal_of_pts_id": "",
                    "redemption_id": "",
                    "expiry_batch_id": "",
                    "expiry_source_pts_id": "",
                    "rule_id": earn_rule,
                    "tier_id_at_post": TIER_BY_RANK[current_rank]["tier_id"],
                    "earn_multiplier": f"{rate:.2f}",
                    "expires_at": iso(order["_order_dt"] + timedelta(days=730)),
                    "description": f"Line accrual · {order['order_id']}",
                    "_key": accrual_key,
                    "_posted_dt": posted,
                    "_expires_dt": order["_order_dt"] + timedelta(days=730),
                    "_source_account": account["account_id"],
                }
                order["_accruals"].append(accrual)
                accruals.append(accrual)

            # Tier progression uses trailing, net-eligible spend. Upgrades are
            # effective immediately; downgrades are recognised at review.
            rolling.append((order["_order_dt"], max(0, order["net_eligible_cents"])))
            while rolling and (order["_order_dt"] - rolling[0][0]).days > 365:
                rolling.popleft()
            spend = sum(v for _, v in rolling)
            new_rank = tier_rank_for_spend(spend)
            if new_rank > current_rank:
                changed = order["_order_dt"] + timedelta(seconds=4)
                tier_history.append({
                    "history_id": "",
                    "account_id": account["account_id"],
                    "from_tier_id": TIER_BY_RANK[current_rank]["tier_id"],
                    "to_tier_id": TIER_BY_RANK[new_rank]["tier_id"],
                    "changed_at": iso(changed),
                    "reason": "rolling_spend_upgrade",
                    "qualifying_spend_cents": spend,
                    "rule_id": "RULE-TIER-V1",
                    "_changed_dt": changed,
                })
                current_rank = new_rank
                account["_current_rank"] = current_rank

        # Snapshot tier is derived from trailing qualifying spend after returns.
        window_start = AS_OF - timedelta(days=365)
        final_spend = 0
        for order in acct_orders:
            if order["status"] == "voided":
                continue
            if order["_order_dt"] < window_start:
                continue
            final_spend += order["net_eligible_cents"] - order["refund_cents"]
        final_spend = max(0, final_spend)
        final_rank = tier_rank_for_spend(final_spend)
        if final_rank != current_rank:
            reason = "annual_review_downgrade" if final_rank < current_rank else "rolling_spend_upgrade"
            changed = AS_OF - timedelta(days=30, hours=4)
            tier_history.append({
                "history_id": "",
                "account_id": account["account_id"],
                "from_tier_id": TIER_BY_RANK[current_rank]["tier_id"],
                "to_tier_id": TIER_BY_RANK[final_rank]["tier_id"],
                "changed_at": iso(changed),
                "reason": reason,
                "qualifying_spend_cents": final_spend,
                "rule_id": "RULE-TIER-V1",
                "_changed_dt": changed,
            })
        account["tier_id"] = TIER_BY_RANK[final_rank]["tier_id"]
        account["qualifying_spend_cents"] = final_spend
        account["tier_reviewed_at"] = iso(AS_OF - timedelta(days=30, hours=4))
        account["_current_rank"] = final_rank

        # Build return reversals from the original line-level accruals.
        for order in acct_orders:
            if order["status"] == "voided" or not order["_returned_dt"]:
                continue
            if order["_missing_reversal"]:
                continue
            returned_ts = order["_returned_dt"] + timedelta(minutes=8)
            for line in order["_lines"]:
                if line["returned_qty"] <= 0 or line["_points"] <= 0:
                    continue
                reversed_points = int(math.floor(line["_points"] * line["returned_qty"] / line["quantity"]))
                if reversed_points <= 0:
                    continue
                rev_key = f"R-{line['order_line_id']}"
                reversal = {
                    "points_txn_id": "",
                    "account_id": account["account_id"],
                    "txn_type": "REVERSAL",
                    "points_delta": -reversed_points,
                    "posted_at": iso(returned_ts),
                    "status": "posted",
                    "source_order_id": order["order_id"],
                    "source_order_line_id": line["order_line_id"],
                    "reversal_of_pts_id": "",
                    "redemption_id": "",
                    "expiry_batch_id": "",
                    "expiry_source_pts_id": "",
                    "rule_id": "RULE-REDEEM-V2",
                    "tier_id_at_post": account["tier_id"],
                    "earn_multiplier": "",
                    "expires_at": "",
                    "description": f"Return reversal · {order['order_id']}",
                    "_key": rev_key,
                    "_posted_dt": returned_ts,
                    "_source_accrual_key": line["_accrual_key"],
                    "_reversed_points": reversed_points,
                }
                order["_reversals"].append(reversal)
                reversals.append(reversal)
                line["_returned_points"] = reversed_points

    return accruals, reversals, tier_history


def build_bonus_events(rng: random.Random, accounts, n_bonus: int):
    """A small number of campaign and welcome bonuses, each a dated point lot."""
    eligible = [a for a in accounts if a["status"] == "active"]
    if not eligible:
        return []
    events = []
    for i in range(n_bonus):
        account = rng.choice(eligible)
        if i % 4 == 0:
            # Welcome / reactivation bonus, close to account opening.
            ts = account["_opened_dt"] + timedelta(days=rng.randint(1, 25), hours=rng.randint(2, 18))
            description = "Welcome bonus · programme launch"
            points = rng.choice([100, 150, 200, 250])
        else:
            ts = business_ts(
                rng,
                max(DATA_START, account["_opened_dt"] + timedelta(days=3)),
                datetime(2026, 8, 31, 20, 0, tzinfo=UTC),
            )
            description = rng.choice([
                "Seasonal campaign bonus", "Tier appreciation bonus",
                "Profile completion bonus", "Reactivation campaign bonus",
            ])
            points = rng.choice([50, 75, 100, 150, 200, 250, 300, 500])
        if ts > AS_OF - timedelta(days=1):
            ts = AS_OF - timedelta(days=2, hours=3)
        events.append({
            "points_txn_id": "",
            "account_id": account["account_id"],
            "txn_type": "BONUS",
            "points_delta": points,
            "posted_at": iso(ts),
            "status": "posted",
            "source_order_id": "",
            "source_order_line_id": "",
            "reversal_of_pts_id": "",
            "redemption_id": "",
            "expiry_batch_id": "",
            "expiry_source_pts_id": "",
            "rule_id": "RULE-BONUS-V1",
            "tier_id_at_post": account["tier_id"],
            "earn_multiplier": "",
            "expires_at": iso(ts + timedelta(days=365)),
            "description": description,
            "_key": f"BON-{i + 1:08d}",
            "_posted_dt": ts,
            "_expires_dt": ts + timedelta(days=365),
            "_source_account": account["account_id"],
        })
    return events


def build_redemption_attempts(rng: random.Random, accounts, by_account, n_attempts: int):
    """Pre-schedule redemption attempts; decisions are made in the ledger simulation."""
    candidates = [a for a in accounts if by_account.get(a["account_id"])]
    if not candidates:
        return []
    order_times = {}
    for account in candidates:
        times = [o["_order_dt"] for o in by_account[account["account_id"]] if o["status"] != "voided"]
        if times:
            order_times[account["account_id"]] = times
    candidates = [a for a in candidates if order_times.get(a["account_id"])]
    if not candidates:
        return []

    reward_weights = [
        ("RWD-01", 0.22), ("RWD-02", 0.34), ("RWD-03", 0.24),
        ("RWD-04", 0.04), ("RWD-05", 0.11), ("RWD-06", 0.02),
        ("RWD-07", 0.02), ("RWD-08", 0.01),
    ]
    attempts = []
    for i in range(n_attempts):
        account = rng.choice(candidates)
        times = order_times[account["account_id"]]
        base = rng.choice(times)
        ts = base + timedelta(days=rng.randint(3, 150), minutes=rng.randint(1, 1100))
        if ts > AS_OF - timedelta(hours=2):
            ts = AS_OF - timedelta(hours=2, minutes=rng.randint(1, 55))
        if ts <= account["_opened_dt"]:
            ts = account["_opened_dt"] + timedelta(days=2)
        reward_id = weighted_choice(rng, reward_weights)
        reward = REWARD_BY_ID[reward_id]
        attempts.append({
            "redemption_id": "",
            "account_id": account["account_id"],
            "reward_id": reward_id,
            "requested_at": iso(ts),
            "points_requested": reward["points_cost"],
            "status": "",
            "decision_reason": "",
            "balance_before": 0,
            "balance_after": 0,
            "points_txn_id": "",
            "request_group_id": "",
            "_requested_dt": ts,
            "_key": f"RDMREQ-{i + 1:08d}",
            "_txn_key": "",
            "_approved": False,
        })
    return attempts


def simulate_ledger(rng: random.Random, accounts, accruals, reversals, bonuses, attempts):
    """Process ledger events, expiries and redemption decisions chronologically."""
    from collections import defaultdict

    account_by_id = {a["account_id"]: a for a in accounts}
    points_rows = []
    expiry_batches = {}
    redemption_rows = []
    accrual_by_key = {a["_key"]: a for a in accruals}
    reversed_by_accrual = defaultdict(int)
    row_seq = 0

    events_by_account = defaultdict(list)
    for row in accruals + bonuses:
        events_by_account[row["account_id"]].append({
            "kind": "earn", "ts": row["_posted_dt"], "row": row,
        })
    for row in reversals:
        events_by_account[row["account_id"]].append({
            "kind": "reversal", "ts": row["_posted_dt"], "row": row,
        })
    for attempt in attempts:
        events_by_account[attempt["account_id"]].append({
            "kind": "redemption", "ts": attempt["_requested_dt"], "attempt": attempt,
        })

    # Add a monthly expiry sweep. Points expire at the first month boundary
    # after their lot expiry date; batches are keyed by account and month.
    for account_id, events in events_by_account.items():
        positive_ts = [e["ts"] for e in events if e["kind"] == "earn"]
        if not positive_ts:
            continue
        cursor = min(positive_ts).replace(day=1, hour=0, minute=1, second=0, microsecond=0)
        if cursor < datetime(2024, 1, 1, tzinfo=UTC):
            cursor = datetime(2024, 1, 1, tzinfo=UTC)
        while cursor <= AS_OF:
            events.append({"kind": "expiry_sweep", "ts": cursor, "row": None})
            if cursor.month == 12:
                cursor = cursor.replace(year=cursor.year + 1, month=1)
            else:
                cursor = cursor.replace(month=cursor.month + 1)

    for account_id, events in events_by_account.items():
        account = account_by_id[account_id]
        events.sort(key=lambda e: (
            e["ts"],
            {"expiry_sweep": 0, "earn": 1, "reversal": 2, "redemption": 3}[e["kind"]],
        ))
        lots = []
        debt = 0
        batches_for_account = {}

        def balance_now():
            return sum(l["remaining"] for l in lots) - debt

        def consume_lots(amount: int):
            nonlocal debt
            left = amount
            lots.sort(key=lambda l: (l["_expires_dt"], l["_seq"]))
            for lot in lots:
                if left <= 0:
                    break
                take = min(lot["remaining"], left)
                lot["remaining"] -= take
                left -= take
            if left > 0:
                debt += left

        for event in events:
            kind = event["kind"]
            ts = event["ts"]
            if kind == "expiry_sweep":
                due = [l for l in lots if l["remaining"] > 0 and l["_expires_dt"] <= ts]
                if not due:
                    continue
                batch_key = f"exp:{account_id}:{ts.strftime('%Y-%m')}"
                batch = expiry_batches.get(batch_key)
                if batch is None:
                    batch = {
                        "expiry_batch_id": "",
                        "account_id": account_id,
                        "run_at": iso(ts),
                        "points_expired": 0,
                        "lot_count": 0,
                        "idempotency_key": batch_key,
                        "status": "posted",
                        "rule_id": "RULE-EXPIRY-V1",
                        "created_at": iso(ts + timedelta(seconds=13)),
                        "_key": batch_key,
                        "_run_dt": ts,
                        "_seq": len(expiry_batches),
                    }
                    expiry_batches[batch_key] = batch
                for lot in due:
                    expired = lot["remaining"]
                    if expired <= 0:
                        continue
                    lot["remaining"] = 0
                    batch["points_expired"] += expired
                    batch["lot_count"] += 1
                    row_seq += 1
                    expiry_row = {
                        "points_txn_id": "",
                        "account_id": account_id,
                        "txn_type": "EXPIRATION",
                        "points_delta": -expired,
                        "posted_at": iso(ts + timedelta(minutes=5, seconds=(row_seq % 23))),
                        "status": "posted",
                        "source_order_id": lot.get("_order_id", ""),
                        "source_order_line_id": lot.get("_line_id", ""),
                        "reversal_of_pts_id": "",
                        "redemption_id": "",
                        "expiry_batch_id": "",
                        "expiry_source_pts_id": "",
                        "rule_id": "RULE-EXPIRY-V1",
                        "tier_id_at_post": "",
                        "earn_multiplier": "",
                        "expires_at": "",
                        "description": f"Lot expiry · {lot['_source_key']}",
                        "_key": f"E-{account_id}-{lot['_source_key']}-{row_seq:08d}",
                        "_posted_dt": ts + timedelta(minutes=5, seconds=(row_seq % 23)),
                        "_expiry_source_key": lot["_source_key"],
                        "_batch_key": batch_key,
                        "_source_account": account_id,
                        "_seq": row_seq,
                        "_lot": lot,
                    }
                    points_rows.append(expiry_row)
                continue

            if kind == "earn":
                row = event["row"]
                points = row["points_delta"]
                if debt > 0:
                    paid = min(debt, points)
                    debt -= paid
                    points_for_lot = points - paid
                else:
                    points_for_lot = points
                row_seq += 1
                row["_seq"] = row_seq
                row["_posted_dt"] = datetime.fromisoformat(row["posted_at"].replace("Z", "+00:00"))
                row["_expires_dt"] = datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00"))
                points_rows.append(row)
                if points_for_lot > 0:
                    lots.append({
                        "remaining": points_for_lot,
                        "_expires_dt": row["_expires_dt"],
                        "_source_key": row["_key"],
                        "_order_id": row.get("source_order_id", ""),
                        "_line_id": row.get("source_order_line_id", ""),
                        "_seq": row_seq,
                        "account_id": account_id,
                    })
                continue

            if kind == "reversal":
                row = event["row"]
                row_seq += 1
                row["_seq"] = row_seq
                row["_posted_dt"] = datetime.fromisoformat(row["posted_at"].replace("Z", "+00:00"))
                points_rows.append(row)
                amount = abs(row["points_delta"])
                consume_lots(amount)
                reversed_by_accrual[row["_source_accrual_key"]] += amount
                continue

            if kind == "redemption":
                attempt = event["attempt"]
                reward = REWARD_BY_ID[attempt["reward_id"]]
                request_dt = attempt["_requested_dt"]
                before = balance_now()
                effective_to = reward.get("effective_to") or ""
                if effective_to and request_dt.date().isoformat() > effective_to:
                    reason = "reward_inactive"
                elif before < attempt["points_requested"]:
                    reason = "insufficient_balance"
                else:
                    reason = "approved"
                attempt["balance_before"] = before
                if reason == "approved":
                    row_seq += 1
                    points_requested = attempt["points_requested"]
                    consume_lots(points_requested)
                    txn_key = f"RED-{attempt['_key']}"
                    row = {
                        "points_txn_id": "",
                        "account_id": account_id,
                        "txn_type": "REDEMPTION",
                        "points_delta": -points_requested,
                        "posted_at": iso(request_dt + timedelta(seconds=1)),
                        "status": "posted",
                        "source_order_id": "",
                        "source_order_line_id": "",
                        "reversal_of_pts_id": "",
                        "redemption_id": "",
                        "expiry_batch_id": "",
                        "expiry_source_pts_id": "",
                        "rule_id": "RULE-REDEEM-V2",
                        "tier_id_at_post": account["tier_id"],
                        "earn_multiplier": "",
                        "expires_at": "",
                        "description": f"Reward redemption · {reward['reward_name']}",
                        "_key": txn_key,
                        "_posted_dt": request_dt + timedelta(seconds=1),
                        "_redemption_key": attempt["_key"],
                        "_source_account": account_id,
                        "_seq": row_seq,
                    }
                    points_rows.append(row)
                    attempt["_txn_key"] = txn_key
                    attempt["_approved"] = True
                    attempt["status"] = "approved"
                    attempt["decision_reason"] = "approved"
                    attempt["balance_after"] = before - points_requested
                else:
                    attempt["status"] = "rejected"
                    attempt["decision_reason"] = reason
                    attempt["balance_after"] = before
                redemption_rows.append(attempt)

    included = {a["_key"] for a in redemption_rows}
    for attempt in attempts:
        if attempt["_key"] not in included:
            attempt["status"] = "rejected"
            attempt["decision_reason"] = "insufficient_balance"
            attempt["balance_before"] = 0
            attempt["balance_after"] = 0
            redemption_rows.append(attempt)

    for accrual in accruals:
        rev = reversed_by_accrual.get(accrual["_key"], 0)
        if rev >= accrual["points_delta"]:
            accrual["status"] = "reversed"
        elif rev > 0:
            accrual["status"] = "partially_reversed"
        else:
            accrual["status"] = "posted"

    return points_rows, redemption_rows, list(expiry_batches.values()), reversed_by_accrual


def parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def public_row(row: dict) -> dict:
    return {k: v for k, v in row.items() if not k.startswith("_")}


def add_expiry_duplicates(rng: random.Random, points_rows, expiry_batches):
    """Deliberately duplicate a handful of expired lots and their batches."""
    expiry_rows = [r for r in points_rows if r["txn_type"] == "EXPIRATION"]
    if not expiry_rows:
        return [], []
    rng.shuffle(expiry_rows)
    chosen = expiry_rows[:8]
    new_batches = []
    new_rows = []
    for idx, original in enumerate(chosen):
        batch = next((b for b in expiry_batches if b["_key"] == original["_batch_key"]), None)
        if batch is None:
            continue
        duplicate_batch_key = f"{batch['_key']}:duplicate:{idx + 1:02d}"
        duplicate_batch = dict(batch)
        duplicate_batch["expiry_batch_id"] = ""
        duplicate_batch["points_expired"] = abs(original["points_delta"])
        duplicate_batch["lot_count"] = 1
        duplicate_batch["_key"] = duplicate_batch_key
        duplicate_batch["_run_dt"] = batch["_run_dt"] + timedelta(seconds=30 + idx)
        duplicate_batch["created_at"] = iso(duplicate_batch["_run_dt"])
        # duplicate idempotency key is deliberate; this is the observable defect
        duplicate_batch["_seq"] = len(expiry_batches) + idx
        new_batches.append(duplicate_batch)

        duplicate_row = dict(original)
        duplicate_row["points_txn_id"] = ""
        duplicate_row["posted_at"] = iso(original["_posted_dt"] + timedelta(seconds=30 + idx))
        duplicate_row["_posted_dt"] = original["_posted_dt"] + timedelta(seconds=30 + idx)
        duplicate_row["_key"] = f"DUP-{original['_key']}"
        duplicate_row["_batch_key"] = duplicate_batch_key
        duplicate_row["_seq"] = 10_000_000 + idx
        duplicate_row["description"] = f"Duplicate lot expiry · {original['_expiry_source_key']}"
        new_rows.append(duplicate_row)
    points_rows.extend(new_rows)
    expiry_batches.extend(new_batches)
    return new_rows, new_batches


def add_filler_bonus(rng: random.Random, accounts, points_rows, target_count: int, excluded_accounts=None):
    """Fill to the exact ledger volume with campaign bonuses dated before the snapshot."""
    excluded_accounts = set(excluded_accounts or [])
    active = [a for a in accounts if a["status"] == "active" and a["account_id"] not in excluded_accounts]
    if not active:
        active = [a for a in accounts if a["account_id"] not in excluded_accounts]
    remaining = target_count - len(points_rows)
    if remaining < 0:
        raise RuntimeError(
            f"Baseline generated {len(points_rows)} ledger rows, above the {target_count} target. "
            "Reduce attempts, bonuses, or line volume."
        )
    campaigns = [
        "Autumn member campaign", "Studio preview bonus", "Address book completion bonus",
        "Anniversary appreciation bonus", "Mending service promotion",
    ]
    filler_rows = []
    for i in range(remaining):
        account = rng.choice(active)
        ts = business_ts(
            rng,
            datetime(2026, 8, 20, 8, 0, tzinfo=UTC),
            datetime(2026, 10, 20, 19, 0, tzinfo=UTC),
        )
        points = rng.choice([25, 50, 50, 75, 100, 150, 200])
        exp = ts + timedelta(days=540)
        row = {
            "points_txn_id": "",
            "account_id": account["account_id"],
            "txn_type": "BONUS",
            "points_delta": points,
            "posted_at": iso(ts),
            "status": "posted",
            "source_order_id": "",
            "source_order_line_id": "",
            "reversal_of_pts_id": "",
            "redemption_id": "",
            "expiry_batch_id": "",
            "expiry_source_pts_id": "",
            "rule_id": "RULE-BONUS-V1",
            "tier_id_at_post": account["tier_id"],
            "earn_multiplier": "",
            "expires_at": iso(exp),
            "description": f"{rng.choice(campaigns)} · campaign points",
            "_key": f"FILL-{i + 1:08d}",
            "_posted_dt": ts,
            "_expires_dt": exp,
            "_source_account": account["account_id"],
            "_seq": 20_000_000 + i,
        }
        filler_rows.append(row)
    points_rows.extend(filler_rows)
    return filler_rows


def add_concurrent_attempts(rng: random.Random, accounts, points_rows, redemption_rows):
    """Post one approved and one locked-out attempt per concurrent request group."""
    account_balances = defaultdict(int)
    for row in points_rows:
        account_balances[row["account_id"]] += row["points_delta"]
    candidates = [
        a for a in accounts
        if a["status"] == "active" and account_balances[a["account_id"]] >= 700
    ]
    if not candidates:
        candidates = [a for a in accounts if a["status"] == "active"]
    rng.shuffle(candidates)
    candidates = candidates[:20]
    approved_rows = []
    decisions = []
    base_dt = AS_OF - timedelta(hours=3)
    for idx, account in enumerate(candidates):
        cost = 500
        if account_balances[account["account_id"]] < cost:
            continue
        group_id = f"RG-2026-{idx + 1:04d}"
        ts = base_dt + timedelta(minutes=idx * 2)
        before = account_balances[account["account_id"]]
        pending_key = f"CONC-{idx + 1:03d}-A"
        txn = {
            "points_txn_id": "",
            "account_id": account["account_id"],
            "txn_type": "REDEMPTION",
            "points_delta": -cost,
            "posted_at": iso(ts + timedelta(seconds=2)),
            "status": "posted",
            "source_order_id": "",
            "source_order_line_id": "",
            "reversal_of_pts_id": "",
            "redemption_id": "",
            "expiry_batch_id": "",
            "expiry_source_pts_id": "",
            "rule_id": "RULE-REDEEM-V2",
            "tier_id_at_post": account["tier_id"],
            "earn_multiplier": "",
            "expires_at": "",
            "description": "Reward redemption · £5 reward voucher",
            "_key": pending_key,
            "_posted_dt": ts + timedelta(seconds=2),
            "_redemption_key": f"CONC-RDM-{idx + 1:03d}-A",
            "_source_account": account["account_id"],
            "_seq": 30_000_000 + idx,
        }
        approved_rows.append(txn)
        account_balances[account["account_id"]] -= cost

        approved = {
            "redemption_id": "",
            "account_id": account["account_id"],
            "reward_id": "RWD-02",
            "requested_at": iso(ts),
            "points_requested": cost,
            "status": "approved",
            "decision_reason": "approved",
            "balance_before": before,
            "balance_after": before - cost,
            "points_txn_id": "",
            "request_group_id": group_id,
            "_requested_dt": ts,
            "_key": f"CONC-RDM-{idx + 1:03d}-A",
            "_txn_key": pending_key,
            "_approved": True,
        }
        rejected = {
            "redemption_id": "",
            "account_id": account["account_id"],
            "reward_id": "RWD-02",
            "requested_at": iso(ts),
            "points_requested": cost,
            "status": "rejected",
            "decision_reason": "concurrent_lock",
            "balance_before": before - cost,
            "balance_after": before - cost,
            "points_txn_id": "",
            "request_group_id": group_id,
            "_requested_dt": ts,
            "_key": f"CONC-RDM-{idx + 1:03d}-B",
            "_txn_key": "",
            "_approved": False,
        }
        redemption_rows.extend([approved, rejected])
        decisions.append({
            "group_id": group_id,
            "account_id": account["account_id"],
            "approved_key": approved["_key"],
            "rejected_key": rejected["_key"],
            "points_txn_key": pending_key,
            "before": before,
            "cost": cost,
            "ts": ts,
        })
    points_rows.extend(approved_rows)
    return approved_rows, decisions


def add_over_balance_attempts(rng: random.Random, accounts, points_rows, redemption_rows):
    """Retain rejected attempts that ask for more points than the account holds."""
    balances = defaultdict(int)
    for row in points_rows:
        balances[row["account_id"]] += row["points_delta"]
    low_balance = [
        a for a in accounts
        if a["status"] == "active" and 0 <= balances[a["account_id"]] < 5000
    ]
    rng.shuffle(low_balance)
    low_balance = low_balance[:16]
    decisions = []
    base_dt = AS_OF - timedelta(hours=2)
    for idx, account in enumerate(low_balance):
        before = balances[account["account_id"]]
        ts = base_dt + timedelta(minutes=idx)
        reward = REWARD_BY_ID["RWD-07"]
        row = {
            "redemption_id": "",
            "account_id": account["account_id"],
            "reward_id": "RWD-07",
            "requested_at": iso(ts),
            "points_requested": reward["points_cost"],
            "status": "rejected",
            "decision_reason": "insufficient_balance",
            "balance_before": before,
            "balance_after": before,
            "points_txn_id": "",
            "request_group_id": "",
            "_requested_dt": ts,
            "_key": f"OVER-RDM-{idx + 1:03d}",
            "_txn_key": "",
            "_approved": False,
        }
        redemption_rows.append(row)
        decisions.append({
            "redemption_key": row["_key"],
            "account_id": account["account_id"],
            "before": before,
            "requested": reward["points_cost"],
            "ts": ts,
        })
    return decisions


def assign_ids(points_rows, redemption_rows, expiry_batches, orders, accruals, reversed_by_accrual):
    """Assign deterministic public identifiers and resolve cross-references."""
    points_rows.sort(key=lambda r: (r["_posted_dt"], r.get("_seq", 0), r["_key"]))
    for i, row in enumerate(points_rows, start=1):
        row["points_txn_id"] = f"PTS-2026-{i:08d}"
    by_key = {row["_key"]: row for row in points_rows}
    accrual_by_key = {row["_key"]: row for row in accruals}

    for row in points_rows:
        if row["txn_type"] == "REVERSAL":
            source = accrual_by_key.get(row.get("_source_accrual_key", ""))
            row["reversal_of_pts_id"] = source["points_txn_id"] if source else ""
        if row["txn_type"] == "EXPIRATION":
            source = by_key.get(row.get("_expiry_source_key", ""))
            row["expiry_source_pts_id"] = source["points_txn_id"] if source else ""

    exposure_by_account = defaultdict(int)
    for row in points_rows:
        exposure_by_account[row["account_id"]] += row["points_delta"]

    batches_sorted = sorted(expiry_batches, key=lambda b: (b["_run_dt"], b["account_id"], b["_key"]))
    for i, batch in enumerate(batches_sorted, start=1):
        batch["expiry_batch_id"] = f"EXP-2026-{i:06d}"
    batch_by_key = {b["_key"]: b for b in batches_sorted}
    for row in points_rows:
        if row["txn_type"] == "EXPIRATION":
            batch = batch_by_key.get(row.get("_batch_key", ""))
            row["expiry_batch_id"] = batch["expiry_batch_id"] if batch else ""

    # Recalculate batch totals from linked ledger lines. This keeps the batch
    # header honest even after a duplicate-batch injection.
    batch_totals = defaultdict(lambda: {"points": 0, "sources": set()})
    for row in points_rows:
        if row["txn_type"] == "EXPIRATION" and row.get("_batch_key"):
            batch_totals[row["_batch_key"]]["points"] += abs(row["points_delta"])
            batch_totals[row["_batch_key"]]["sources"].add(row.get("_expiry_source_key", ""))
    for batch in batches_sorted:
        totals = batch_totals.get(batch["_key"])
        if totals:
            batch["points_expired"] = totals["points"]
            batch["lot_count"] = len(totals["sources"])

    redemption_rows.sort(key=lambda r: (r["_requested_dt"], r["_key"]))
    for i, row in enumerate(redemption_rows, start=1):
        row["redemption_id"] = f"RDM-2026-{i:06d}"
    redemption_by_key = {r["_key"]: r for r in redemption_rows}
    # Approved attempts own exactly one posted redemption row.
    for row in points_rows:
        if row["txn_type"] == "REDEMPTION":
            red = redemption_by_key.get(row.get("_redemption_key", ""))
            if red is not None:
                red["points_txn_id"] = row["points_txn_id"]
                row["redemption_id"] = red["redemption_id"]

    # Tier history IDs, ordered by effective change time.
    return by_key, redemption_by_key, batch_by_key, exposure_by_account, batches_sorted


def materialize_accounts(
    rng: random.Random, accounts, by_account, points_rows, tier_history,
    orders, concurrent_decisions, over_balance_decisions,
    expiry_duplicates
):
    """Derive account balances, exception labels and ground-truth records."""
    acc_by_id = {a["account_id"]: a for a in accounts}
    balances = defaultdict(int)
    lifetime = defaultdict(int)
    last_activity = {}
    for row in points_rows:
        acct = row["account_id"]
        balances[acct] += row["points_delta"]
        if row["points_delta"] > 0 and row["txn_type"] in ("ACCRUAL", "BONUS", "ADJUSTMENT"):
            lifetime[acct] += row["points_delta"]
        ts = row["_posted_dt"]
        if acct not in last_activity or ts > last_activity[acct]:
            last_activity[acct] = ts

    for account in accounts:
        account["available_points"] = balances.get(account["account_id"], 0)
        account["lifetime_earned_points"] = lifetime.get(account["account_id"], 0)
        account["pending_points"] = 0
        account["last_activity_at"] = iso(last_activity[account["account_id"]]) if account["account_id"] in last_activity else ""
        account["updated_at"] = iso(AS_OF)

    # ---- Ground truth: missing reversal ----
    gt = []
    for order in orders:
        if not order["_missing_reversal"]:
            continue
        total_points = sum(r["points_delta"] for r in order["_accruals"])
        related = ",".join(r["points_txn_id"] for r in order["_accruals"] if r["points_txn_id"])
        gt.append({
            "issue_type": "returned_order_keeps_all_points",
            "entity_type": "Order",
            "entity_id": order["order_id"],
            "related_entity_id": related,
            "expected_label": "missing_return_reversal",
            "expected_decision": f"Reverse {total_points:,} earned points and set the accrual to reversed",
            "severity": "high",
            "detection_rule": "returned order with eligible accruals but no REVERSAL linked to the original lines",
            "notes": f"Order status is returned; {len(order['_accruals'])} line accrual(s) remain posted.",
            "evidence": {
                "refund_cents": order["refund_cents"],
                "unreversed_points": total_points,
                "returned_at": order["returned_at"],
            },
        })

    # ---- Ground truth: duplicate expiry ----
    for duplicate in expiry_duplicates:
        gt.append({
            "issue_type": "points_expire_twice",
            "entity_type": "ExpiryBatch",
            "entity_id": duplicate["expiry_batch_id"],
            "related_entity_id": "",
            "expected_label": "duplicate_expiry",
            "expected_decision": "Void the duplicate batch and reverse its ledger entry; keep the original expiry",
            "severity": "high",
            "detection_rule": "duplicate expiry_batches.idempotency_key or a second EXPIRATION for the same source lot",
            "notes": f"Expiry source {duplicate.get('expiry_source_pts_id', '')} was expired a second time for {abs(duplicate['points_delta']):,} points.",
            "evidence": {
                "duplicate_batch": duplicate["expiry_batch_id"],
                "points_txn_id": duplicate["points_txn_id"],
                "points": abs(duplicate["points_delta"]),
            },
        })

    # ---- Ground truth: concurrent request groups ----
    for c in concurrent_decisions:
        gt.append({
            "issue_type": "concurrent_redemption_attempt",
            "entity_type": "Redemption",
            "entity_id": c.get("approved_id", c["approved_key"]),
            "related_entity_id": c.get("rejected_id", c["rejected_key"]),
            "expected_label": "concurrency_guard",
            "expected_decision": "Approve exactly one request; reject the second with concurrent_lock",
            "severity": "medium",
            "detection_rule": "two attempts share a request_group_id; count(approved)=1",
            "notes": f"Both requests for {c['cost']} points arrived at {iso(c['ts'])}.",
            "evidence": {"account_id": c["account_id"], "balance_before": c["before"]},
        })

    # ---- Ground truth: over-balance attempts ----
    for d in over_balance_decisions:
        gt.append({
            "issue_type": "redemption_exceeds_available_points",
            "entity_type": "Redemption",
            "entity_id": d.get("redemption_id", d["redemption_key"]),
            "related_entity_id": "",
            "expected_label": "insufficient_balance",
            "expected_decision": "Reject the attempt; do not post a redemption ledger row",
            "severity": "medium",
            "detection_rule": "points_requested > balance_before, or approved attempt above available balance",
            "notes": f"Requested {d['requested']:,} points with {d['before']:,} available.",
            "evidence": {"balance_before": d["before"], "points_requested": d["requested"]},
        })

    # ---- Ground truth: account materialisation mismatch ----
    eligible_mismatch = [
        a for a in accounts
        if a["status"] == "active" and a["available_points"] > 0
    ]
    rng.shuffle(eligible_mismatch)
    mismatch_accounts = eligible_mismatch[:12]
    mismatch_deltas = [37, -58, 120, -240, 15, 65, -90, 48, -21, 130, -46, 88]
    for idx, account in enumerate(mismatch_accounts):
        canonical = account["available_points"]
        delta = mismatch_deltas[idx % len(mismatch_deltas)]
        account["available_points"] = canonical + delta
        gt.append({
            "issue_type": "balance_differs_from_ledger",
            "entity_type": "LoyaltyAccount",
            "entity_id": account["account_id"],
            "related_entity_id": "",
            "expected_label": "balance_mismatch",
            "expected_decision": "Rebuild the materialised balance from the immutable ledger; do not alter ledger history",
            "severity": "high",
            "detection_rule": "loyalty_accounts.available_points != sum(points_transactions.points_delta)",
            "notes": f"Stored balance is {account['available_points']:,}; ledger sum is {canonical:,}.",
            "evidence": {"stored_balance": account["available_points"], "ledger_balance": canonical, "delta": delta},
        })

    # ---- Ground truth: tier calculated from gross spend ----
    cutoff = AS_OF - timedelta(days=365)
    candidates = []
    for account in accounts:
        orders = by_account.get(account["account_id"], [])
        if not orders:
            continue
        baseline_tier = account["tier_id"]
        baseline_rank = TIER_BY_ID[baseline_tier]["rank"]
        gross_window = 0
        for order in orders:
            if order["status"] == "voided" or order["_order_dt"] < cutoff:
                continue
            gross_window += order["gross_cents"] + order["tax_cents"] + order["shipping_cents"]
        gross_rank = tier_rank_for_spend(gross_window)
        if gross_rank > baseline_rank:
            candidates.append((account, baseline_rank, gross_rank, gross_window))
    rng.shuffle(candidates)
    for account, baseline_rank, gross_rank, gross_window in candidates[:10]:
        baseline_tier = TIER_BY_RANK[baseline_rank]["tier_id"]
        account["tier_id"] = TIER_BY_RANK[gross_rank]["tier_id"]
        gt.append({
            "issue_type": "tier_uses_gross_spend",
            "entity_type": "LoyaltyAccount",
            "entity_id": account["account_id"],
            "related_entity_id": "RULE-TIER-V1",
            "expected_label": "wrong_tier_basis",
            "expected_decision": "Recalculate tier from trailing net-eligible spend after returns",
            "severity": "medium",
            "detection_rule": "stored tier rank != rank(trailing net-eligible spend after returns)",
            "notes": f"Tier was set from {gross_window:,} gross cents instead of {account['qualifying_spend_cents']:,} qualifying cents.",
            "evidence": {
                "baseline_tier": baseline_tier,
                "stored_tier": account["tier_id"],
                "gross_spend_cents": gross_window,
                "qualifying_spend_cents": account["qualifying_spend_cents"],
            },
        })

    # Tier history IDs.
    year_counters = defaultdict(int)
    history_sorted = sorted(tier_history, key=lambda r: (r["_changed_dt"], r["account_id"]))
    for row in history_sorted:
        year = row["_changed_dt"].year
        year_counters[year] += 1
        row["history_id"] = f"TH-{year}-{year_counters[year]:06d}"

    # Ground-truth case IDs are assigned at the end in a stable order.
    gt.sort(key=lambda r: (r["issue_type"], r["entity_type"], r["entity_id"]))
    for idx, row in enumerate(gt, start=1):
        row["case_id"] = f"GT-2026-{idx:04d}"
        row["generated_at"] = iso(AS_OF)
    return gt, mismatch_accounts


def validate_dataset(tables, ground_truth, target_txn_count):
    """Run structural and domain checks over the in-memory result."""
    customers = tables["customers"]
    accounts = tables["loyalty_accounts"]
    orders = tables["orders"]
    lines = tables["order_lines"]
    pts = tables["points_transactions"]
    redemptions = tables["redemptions"]
    batches = tables["expiry_batches"]
    tiers = tables["tiers"]
    rewards = tables["rewards"]
    tier_history = tables["tier_history"]
    rules = tables["rules"]

    checks = []

    def add_check(check_id, label, result, detail):
        checks.append({
            "check_id": check_id,
            "label": label,
            "result": result,
            "detail": detail,
        })

    def unique(rows, field):
        ids = [r[field] for r in rows]
        return len(ids) == len(set(ids)), len(ids) - len(set(ids))

    helper_checks = [
        ("PK-customers", "customers.customer_id uniqueness", unique(customers, "customer_id")),
        ("PK-accounts", "loyalty_accounts.account_id uniqueness", unique(accounts, "account_id")),
        ("PK-orders", "orders.order_id uniqueness", unique(orders, "order_id")),
        ("PK-lines", "order_lines.order_line_id uniqueness", unique(lines, "order_line_id")),
        ("PK-points", "points_transactions.points_txn_id uniqueness", unique(pts, "points_txn_id")),
        ("PK-redemptions", "redemptions.redemption_id uniqueness", unique(redemptions, "redemption_id")),
        ("PK-expiry", "expiry_batches.expiry_batch_id uniqueness", unique(batches, "expiry_batch_id")),
    ]
    for check_id, label, (ok, dupes) in helper_checks:
        add_check(check_id, label, "pass" if ok else "fail", f"{dupes} duplicate keys")

    customer_ids = {c["customer_id"] for c in customers}
    account_ids = {a["account_id"] for a in accounts}
    order_ids = {o["order_id"] for o in orders}
    line_ids = {l["order_line_id"] for l in lines}
    tier_ids = {t["tier_id"] for t in tiers}
    rule_ids = {r["rule_id"] for r in rules}
    reward_ids = {r["reward_id"] for r in rewards}
    pts_ids = {p["points_txn_id"] for p in pts}
    redemption_ids = {r["redemption_id"] for r in redemptions}
    batch_ids = {b["expiry_batch_id"] for b in batches}
    fk_failures = []
    for a in accounts:
        if a["customer_id"] not in customer_ids: fk_failures.append((a["account_id"], "customer_id"))
        if a["tier_id"] not in tier_ids: fk_failures.append((a["account_id"], "tier_id"))
    for o in orders:
        if o["customer_id"] not in customer_ids: fk_failures.append((o["order_id"], "customer_id"))
        if o["account_id"] not in account_ids: fk_failures.append((o["order_id"], "account_id"))
    for l in lines:
        if l["order_id"] not in order_ids: fk_failures.append((l["order_line_id"], "order_id"))
    for p in pts:
        if p["account_id"] not in account_ids: fk_failures.append((p["points_txn_id"], "account_id"))
        if p["rule_id"] and p["rule_id"] not in rule_ids: fk_failures.append((p["points_txn_id"], "rule_id"))
        if p["source_order_id"] and p["source_order_id"] not in order_ids: fk_failures.append((p["points_txn_id"], "source_order_id"))
        if p["source_order_line_id"] and p["source_order_line_id"] not in line_ids: fk_failures.append((p["points_txn_id"], "source_order_line_id"))
        if p["reversal_of_pts_id"] and p["reversal_of_pts_id"] not in pts_ids: fk_failures.append((p["points_txn_id"], "reversal_of_pts_id"))
        if p["redemption_id"] and p["redemption_id"] not in redemption_ids: fk_failures.append((p["points_txn_id"], "redemption_id"))
        if p["expiry_batch_id"] and p["expiry_batch_id"] not in batch_ids: fk_failures.append((p["points_txn_id"], "expiry_batch_id"))
        if p["expiry_source_pts_id"] and p["expiry_source_pts_id"] not in pts_ids: fk_failures.append((p["points_txn_id"], "expiry_source_pts_id"))
    for r in redemptions:
        if r["account_id"] not in account_ids: fk_failures.append((r["redemption_id"], "account_id"))
        if r["reward_id"] not in reward_ids: fk_failures.append((r["redemption_id"], "reward_id"))
        if r["points_txn_id"] and r["points_txn_id"] not in pts_ids: fk_failures.append((r["redemption_id"], "points_txn_id"))
    for b in batches:
        if b["account_id"] not in account_ids: fk_failures.append((b["expiry_batch_id"], "account_id"))
        if b["rule_id"] not in rule_ids: fk_failures.append((b["expiry_batch_id"], "rule_id"))
    add_check("FK-001", "Foreign-key integrity", "pass" if not fk_failures else "fail",
              f"{len(fk_failures)} broken references")

    enums = {
        "orders.status": (orders, "status", {"completed", "partially_returned", "returned", "voided"}),
        "redemptions.status": (redemptions, "status", {"approved", "rejected"}),
        "redemptions.reason": (redemptions, "decision_reason", {"approved", "insufficient_balance", "concurrent_lock", "reward_inactive", "below_minimum", "account_suspended"}),
        "expiry.status": (batches, "status", {"posted", "void"}),
        "points.txn_type": (pts, "txn_type", {"ACCRUAL", "REVERSAL", "REDEMPTION", "EXPIRATION", "BONUS", "ADJUSTMENT"}),
        "points.status": (pts, "status", {"posted", "reversed", "partially_reversed"}),
    }
    enum_failures = 0
    for _, (rows, field, allowed) in enums.items():
        enum_failures += sum(1 for r in rows if r[field] not in allowed)
    add_check("ENUM-001", "Allowed enum values", "pass" if enum_failures == 0 else "fail",
              f"{enum_failures} invalid enum values")

    date_failures = 0
    for o in orders:
        if o["returned_at"] and parse_dt(o["returned_at"]) <= parse_dt(o["order_ts"]):
            date_failures += 1
    for p in pts:
        if p["expires_at"] and parse_dt(p["expires_at"]) <= parse_dt(p["posted_at"]):
            date_failures += 1
    for r in redemptions:
        if r["balance_after"] > r["balance_before"]:
            date_failures += 1
    add_check("DATE-001", "Date and lifecycle ordering", "pass" if date_failures == 0 else "fail",
              f"{date_failures} ordering failures")

    ledger = defaultdict(int)
    for p in pts:
        ledger[p["account_id"]] += p["points_delta"]
    mismatches = [a for a in accounts if ledger.get(a["account_id"], 0) != a["available_points"]]
    expected_mismatch = sum(1 for g in ground_truth if g["issue_type"] == "balance_differs_from_ledger")
    add_check("REC-001", "Balance equals ledger",
              "pass" if len(mismatches) == expected_mismatch else "fail",
              f"{len(mismatches)} mismatches, {expected_mismatch} labelled")

    bad_approved = []
    for r in redemptions:
        if r["status"] == "approved" and r["points_requested"] > r["balance_before"]:
            bad_approved.append(r["redemption_id"])
    add_check("RED-001", "Redemption never exceeds available balance", "pass" if not bad_approved else "fail",
              f"{len(bad_approved)} bad approvals")

    pts_by_id = {p["points_txn_id"]: p for p in pts}
    reversal_failures = []
    for p in pts:
        if p["txn_type"] == "REVERSAL":
            parent = pts_by_id.get(p["reversal_of_pts_id"])
            if parent is None or parent["txn_type"] != "ACCRUAL":
                reversal_failures.append(p["points_txn_id"])
            elif abs(p["points_delta"]) > parent["points_delta"]:
                reversal_failures.append(p["points_txn_id"])
    add_check("REV-001", "Reversals reference original accrual", "pass" if not reversal_failures else "fail",
              f"{len(reversal_failures)} invalid reversal links")

    full_returns = [o for o in orders if o["status"] == "returned"]
    missing_reversals = []
    expected_missing_orders = {
        g["entity_id"] for g in ground_truth if g["issue_type"] == "returned_order_keeps_all_points"
    }
    accrual_lines_by_order = defaultdict(set)
    reversed_lines_by_order = defaultdict(set)
    for p in pts:
        if p["txn_type"] == "ACCRUAL":
            accrual_lines_by_order[p["source_order_id"]].add(p["source_order_line_id"])
        elif p["txn_type"] == "REVERSAL":
            reversed_lines_by_order[p["source_order_id"]].add(p["source_order_line_id"])
    for o in full_returns:
        if o["order_id"] in expected_missing_orders:
            continue
        accrual_lines = accrual_lines_by_order.get(o["order_id"], set())
        reversed_lines = reversed_lines_by_order.get(o["order_id"], set())
        if accrual_lines - reversed_lines:
            missing_reversals.append(o["order_id"])
    add_check("RET-001", "Returned order points are reversed",
              "pass" if not missing_reversals else "warning",
              f"{len(missing_reversals)} unlabelled missing reversals; {len(expected_missing_orders)} labelled cases")

    idem = Counter(b["idempotency_key"] for b in batches)
    duplicate_keys = {k: v for k, v in idem.items() if v > 1}
    expected_expiry_dupes = sum(1 for g in ground_truth if g["issue_type"] == "points_expire_twice")
    add_check("EXP-001", "Expiry batch idempotency",
              "pass" if len(duplicate_keys) == expected_expiry_dupes else "warning",
              f"{len(duplicate_keys)} duplicate idempotency keys, all {expected_expiry_dupes} labelled")

    # Re-derive current tier from qualifying spend for every account.
    tier_mismatch = []
    expected_tier_anomalies = {
        g["entity_id"] for g in ground_truth if g["issue_type"] == "tier_uses_gross_spend"
    }
    for a in accounts:
        expected_rank = tier_rank_for_spend(a["qualifying_spend_cents"])
        actual_rank = TIER_BY_ID[a["tier_id"]]["rank"]
        if expected_rank != actual_rank and a["account_id"] not in expected_tier_anomalies:
            tier_mismatch.append(a["account_id"])
    add_check("TIER-001", "Tier follows qualifying-spend rules",
              "pass" if not tier_mismatch else "fail",
              f"{len(tier_mismatch)} unlabelled tier mismatches; {len(expected_tier_anomalies)} labelled exceptions")

    batch_links = defaultdict(int)
    for p in pts:
        if p["txn_type"] == "EXPIRATION":
            batch_links[p["expiry_batch_id"]] += abs(p["points_delta"])
    batch_failures = [b["expiry_batch_id"] for b in batches if batch_links.get(b["expiry_batch_id"], 0) != b["points_expired"]]
    add_check("EXP-002", "Expiry batch totals reconcile", "pass" if not batch_failures else "fail",
              f"{len(batch_failures)} batch totals disagree with linked ledger rows")

    approved_per_group = defaultdict(int)
    for r in redemptions:
        if r["request_group_id"] and r["status"] == "approved":
            approved_per_group[r["request_group_id"]] += 1
    concurrency_bad = [g for g, n in approved_per_group.items() if n != 1]
    add_check("CONC-001", "Concurrent attempt guard", "pass" if not concurrency_bad else "fail",
              f"{len(concurrency_bad)} groups without exactly one approval")

    count_ok = len(pts) == target_txn_count
    add_check("VOL-001", "Ledger volume target", "pass" if count_ok else "fail",
              f"{len(pts):,} vs {target_txn_count:,} target")

    passed = sum(1 for c in checks if c["result"] == "pass")
    warnings = sum(1 for c in checks if c["result"] == "warning")
    failed = sum(1 for c in checks if c["result"] == "fail")
    summary = {
        "generated_at": iso(AS_OF),
        "seed": None,
        "checks": checks,
        "passed": passed,
        "warnings": warnings,
        "failed": failed,
        "total_checks": len(checks),
        "counts": {
            "customers": len(customers),
            "loyalty_accounts": len(accounts),
            "orders": len(orders),
            "order_lines": len(lines),
            "points_transactions": len(pts),
            "redemptions": len(redemptions),
            "expiry_batches": len(batches),
            "ground_truth_cases": len(ground_truth),
        },
        "issue_counts": dict(Counter(g["issue_type"] for g in ground_truth)),
        "balance_mismatches": len(mismatches),
        "bad_redemptions": len(bad_approved),
        "unlabelled_missing_reversals": len(missing_reversals),
        "duplicate_expiry_keys": len(duplicate_keys),
        "tier_mismatches": len(tier_mismatch),
    }
    return summary


TABLE_COLUMNS = {
    "customers": [
        "customer_id", "first_name", "last_name", "email", "region", "city",
        "acquisition_channel", "marketing_consent", "status", "joined_at", "updated_at",
    ],
    "loyalty_accounts": [
        "account_id", "customer_id", "tier_id", "opened_at", "status",
        "available_points", "pending_points", "lifetime_earned_points",
        "qualifying_spend_cents", "tier_reviewed_at", "last_activity_at", "updated_at",
    ],
    "tiers": [
        "tier_id", "tier_name", "rank", "qualify_spend_cents", "valid_from", "valid_to", "status",
    ],
    "rules": [
        "rule_id", "rule_code", "version", "name", "effective_from", "effective_to",
        "parameters", "status",
    ],
    "rewards": [
        "reward_id", "reward_name", "category", "points_cost", "cash_value_cents",
        "min_tier_rank", "status", "effective_from", "effective_to",
    ],
    "reward_tier_eligibility": ["reward_id", "tier_id", "eligible"],
    "rule_tier_rate": ["rule_id", "tier_id", "earn_multiplier", "effective_from"],
    "tier_history": [
        "history_id", "account_id", "from_tier_id", "to_tier_id", "changed_at",
        "reason", "qualifying_spend_cents", "rule_id",
    ],
    "orders": [
        "order_id", "customer_id", "account_id", "order_ts", "channel", "store_id",
        "gross_cents", "discount_cents", "tax_cents", "shipping_cents",
        "net_eligible_cents", "refund_cents", "status", "returned_at",
    ],
    "order_lines": [
        "order_line_id", "order_id", "sku", "product_name", "category", "quantity",
        "unit_price_cents", "discount_cents", "line_net_cents", "eligible_for_points",
        "returned_qty", "returned_amount_cents",
    ],
    "points_transactions": [
        "points_txn_id", "account_id", "txn_type", "points_delta", "posted_at", "status",
        "source_order_id", "source_order_line_id", "reversal_of_pts_id", "redemption_id",
        "expiry_batch_id", "expiry_source_pts_id", "rule_id", "tier_id_at_post",
        "earn_multiplier", "expires_at", "description",
    ],
    "redemptions": [
        "redemption_id", "account_id", "reward_id", "requested_at", "points_requested",
        "status", "decision_reason", "balance_before", "balance_after", "points_txn_id",
        "request_group_id",
    ],
    "expiry_batches": [
        "expiry_batch_id", "account_id", "run_at", "points_expired", "lot_count",
        "idempotency_key", "status", "rule_id", "created_at",
    ],
    "ground_truth": [
        "case_id", "issue_type", "entity_type", "entity_id", "related_entity_id",
        "expected_label", "expected_decision", "severity", "detection_rule", "notes",
        "evidence", "generated_at",
    ],
}


def sort_and_public(rows, key_fn=None):
    result = [public_row(r) for r in rows]
    if key_fn:
        result.sort(key=key_fn)
    return result


def build_tables(master, customers, accounts, orders, accruals, bonuses, points_rows,
                 redemption_rows, expiry_batches, tier_history, ground_truth, fillers):
    tables = {}
    tables["customers"] = sort_and_public(customers, lambda r: r["customer_id"])
    tables["loyalty_accounts"] = sort_and_public(accounts, lambda r: r["account_id"])
    tables["tiers"] = sort_and_public(master["tiers"], lambda r: r["tier_id"])
    tables["rules"] = sort_and_public(master["rules"], lambda r: r["rule_id"])
    tables["rewards"] = sort_and_public(master["rewards"], lambda r: r["reward_id"])
    tables["reward_tier_eligibility"] = sort_and_public(
        master["reward_tier_eligibility"], lambda r: (r["reward_id"], r["tier_id"])
    )
    tables["rule_tier_rate"] = sort_and_public(
        master["rule_tier_rate"], lambda r: (r["rule_id"], r["tier_id"])
    )
    tables["tier_history"] = sort_and_public(tier_history, lambda r: r["history_id"])
    tables["orders"] = sort_and_public(orders, lambda r: (r["order_ts"], r["order_id"]))
    order_lines = []
    for order in orders:
        order_lines.extend(order["_lines"])
    tables["order_lines"] = sort_and_public(order_lines, lambda r: r["order_line_id"])
    tables["points_transactions"] = sort_and_public(points_rows, lambda r: r["points_txn_id"])
    tables["redemptions"] = sort_and_public(redemption_rows, lambda r: r["redemption_id"])
    tables["expiry_batches"] = sort_and_public(expiry_batches, lambda r: r["expiry_batch_id"])
    gt = []
    for row in ground_truth:
        row = dict(row)
        row["evidence"] = json.dumps(row["evidence"], sort_keys=True, separators=(",", ":"))
        gt.append(row)
    tables["ground_truth"] = sort_and_public(gt, lambda r: r["case_id"])
    return tables


def generate_dataset(args):
    seed = int(args.seed)
    rng = new_rng(seed)
    master = build_master_tables(rng)
    customers, accounts = build_customers(rng, args.customers)
    print(f"[1/8] master data: {len(customers):,} customers, {len(accounts):,} accounts", flush=True)

    orders, by_account, missing_reversal_ids = build_orders(rng, customers, accounts, args.orders)
    print(f"[2/8] transactions: {len(orders):,} orders", flush=True)

    accruals, reversals, tier_history = apply_tiers_and_accruals(rng, accounts, by_account, orders)
    print(
        f"[3/8] derived points: {len(accruals):,} accrual rows, "
        f"{len(reversals):,} reversals, {len(tier_history):,} tier changes",
        flush=True,
    )

    n_bonus = args.bonus if args.bonus is not None else max(30, round(args.orders * 0.06))
    n_attempts = args.attempts if args.attempts is not None else max(20, round(args.orders * 0.50))
    bonuses = build_bonus_events(rng, accounts, n_bonus)
    attempts = build_redemption_attempts(rng, accounts, by_account, n_attempts)
    print(f"[4/8] scheduled {len(bonuses):,} bonus lots and {len(attempts):,} redemption attempts", flush=True)

    points_rows, redemption_rows, expiry_batches, reversed_by_accrual = simulate_ledger(
        rng, accounts, accruals, reversals, bonuses, attempts
    )
    base_count = len(points_rows)
    print(f"[5/8] ledger simulation: {base_count:,} rows before injected edge cases", flush=True)

    duplicate_rows, duplicate_batches = add_expiry_duplicates(rng, points_rows, expiry_batches)
    concurrent_rows, concurrent_decisions = add_concurrent_attempts(
        rng, accounts, points_rows, redemption_rows
    )
    concurrent_account_ids = {d["account_id"] for d in concurrent_decisions}
    try:
        fillers = add_filler_bonus(
            rng, accounts, points_rows, args.transactions,
            excluded_accounts=concurrent_account_ids,
        )
    except RuntimeError as exc:
        raise RuntimeError(
            f"{exc}\nBase volume was {base_count:,}; reduce --attempts, --bonus, "
            "or the order-line distribution before rerunning."
        ) from exc
    over_balance_decisions = add_over_balance_attempts(rng, accounts, points_rows, redemption_rows)

    pts_by_key, redemption_by_key, batch_by_key, exposure, batches_sorted = assign_ids(
        points_rows, redemption_rows, expiry_batches, orders, accruals, reversed_by_accrual
    )
    for c in concurrent_decisions:
        approved = redemption_by_key.get(c["approved_key"])
        rejected = redemption_by_key.get(c["rejected_key"])
        c["approved_id"] = approved["redemption_id"] if approved else ""
        c["rejected_id"] = rejected["redemption_id"] if rejected else ""
    for d in over_balance_decisions:
        row = redemption_by_key.get(d["redemption_key"])
        d["redemption_id"] = row["redemption_id"] if row else ""

    ground_truth, mismatch_accounts = materialize_accounts(
        rng, accounts, by_account, points_rows, tier_history, orders,
        concurrent_decisions, over_balance_decisions, duplicate_rows,
    )
    print(
        f"[6/8] anomaly cases: {len(ground_truth):,} labelled, "
        f"{len(mismatch_accounts):,} balance mismatches, {len(fillers):,} campaign fill rows",
        flush=True,
    )

    tables = build_tables(
        master, customers, accounts, orders, accruals, bonuses, points_rows,
        redemption_rows, batches_sorted, tier_history, ground_truth, fillers,
    )

    validation = validate_dataset(tables, tables["ground_truth"], args.transactions)
    validation["seed"] = seed
    validation["generator"] = "ledgerline.generate/1.4.2"
    validation["generated_at"] = iso(AS_OF)
    failed = validation["failed"]
    print(
        f"[7/8] validation: {validation['passed']} pass, {validation['warnings']} warning, "
        f"{failed} fail", flush=True,
    )
    if failed:
        for check in validation["checks"]:
            if check["result"] == "fail":
                print(f"       FAIL {check['check_id']}: {check['detail']}", flush=True)

    metadata = {
        "seed": seed,
        "scale": {
            "customers": args.customers,
            "orders": args.orders,
            "transactions_target": args.transactions,
        },
        "as_of": iso(AS_OF),
        "generator_version": "1.4.2",
        "build_id": f"2026.1-{seed}",
        "edge_case_switches": {
            "returns_and_partial_returns": True,
            "concurrent_redemptions": True,
            "missing_return_reversals": True,
            "duplicate_expiry_batches": True,
            "balance_materialisation_drift": True,
            "tier_basis_drift": True,
        },
    }
    return tables, validation, metadata


def table_checksums(tables):
    """Canonical content hashes independent of filesystem line endings."""
    result = {}
    for table, rows in tables.items():
        digest = hashlib.sha256()
        columns = TABLE_COLUMNS[table]
        for row in rows:
            payload = {col: row.get(col, "") for col in columns}
            digest.update(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))
            digest.update(b"\n")
        result[table] = {
            "rows": len(rows),
            "sha256": digest.hexdigest(),
        }
    return result


def write_csvs(out_dir: Path, tables):
    csv_dir = out_dir / "csv"
    csv_dir.mkdir(parents=True, exist_ok=True)
    for table, rows in tables.items():
        columns = TABLE_COLUMNS[table]
        with (csv_dir / f"{table}.csv").open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
    return csv_dir


def write_jsonl(out_dir: Path, tables):
    json_dir = out_dir / "jsonl"
    json_dir.mkdir(parents=True, exist_ok=True)
    for table, rows in tables.items():
        with (json_dir / f"{table}.jsonl").open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
                fh.write("\n")
    # Ground truth is also offered as one readable JSON document.
    gt = tables["ground_truth"]
    (out_dir / "json").mkdir(parents=True, exist_ok=True)
    (out_dir / "json" / "ground_truth.json").write_text(
        json.dumps(gt, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    master = {
        "tiers": tables["tiers"],
        "rules": tables["rules"],
        "rewards": tables["rewards"],
        "reward_tier_eligibility": tables["reward_tier_eligibility"],
        "rule_tier_rate": tables["rule_tier_rate"],
        "data_dictionary": DATA_DICTIONARY,
    }
    (out_dir / "json" / "master_data.json").write_text(
        json.dumps(master, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return json_dir


SQL_TYPES = {
    "customers": "TEXT PRIMARY KEY",
    "loyalty_accounts": "TEXT PRIMARY KEY",
    "tiers": "TEXT PRIMARY KEY",
    "rules": "TEXT PRIMARY KEY",
    "rewards": "TEXT PRIMARY KEY",
    "reward_tier_eligibility": "TEXT",
    "rule_tier_rate": "TEXT",
    "tier_history": "TEXT PRIMARY KEY",
    "orders": "TEXT PRIMARY KEY",
    "order_lines": "TEXT PRIMARY KEY",
    "points_transactions": "TEXT PRIMARY KEY",
    "redemptions": "TEXT PRIMARY KEY",
    "expiry_batches": "TEXT PRIMARY KEY",
    "ground_truth": "TEXT PRIMARY KEY",
}

SQL_COL_TYPES = {
    "rank": "INTEGER", "qualify_spend_cents": "INTEGER", "version": "INTEGER",
    "points_cost": "INTEGER", "cash_value_cents": "INTEGER", "min_tier_rank": "INTEGER",
    "gross_cents": "INTEGER", "discount_cents": "INTEGER", "tax_cents": "INTEGER",
    "shipping_cents": "INTEGER", "net_eligible_cents": "INTEGER", "refund_cents": "INTEGER",
    "quantity": "INTEGER", "unit_price_cents": "INTEGER", "line_net_cents": "INTEGER",
    "returned_qty": "INTEGER", "returned_amount_cents": "INTEGER", "points_delta": "INTEGER",
    "earn_multiplier": "REAL", "points_requested": "INTEGER", "balance_before": "INTEGER",
    "balance_after": "INTEGER", "points_expired": "INTEGER", "lot_count": "INTEGER",
    "available_points": "INTEGER", "pending_points": "INTEGER",
    "lifetime_earned_points": "INTEGER", "qualifying_spend_cents": "INTEGER",
}


def sql_literal(value):
    if value is None or value == "":
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    s = str(value)
    # Numeric-looking fields are still quoted for portability; SQL engines
    # coerce them into the declared column types where needed.
    return "'" + s.replace("'", "''") + "'"


def write_sql(out_dir: Path, tables):
    sql_dir = out_dir / "sql"
    sql_dir.mkdir(parents=True, exist_ok=True)
    create_lines = [
        "-- Ledgerline demo schema (SQLite-compatible). Build 2026.1",
        "-- All identifiers and timestamps are synthetic. See README.md.",
        "PRAGMA foreign_keys = OFF;",
        "",
    ]
    for table in [
        "tiers", "rules", "rewards", "customers", "loyalty_accounts",
        "reward_tier_eligibility", "rule_tier_rate", "tier_history",
        "orders", "order_lines", "points_transactions", "redemptions",
        "expiry_batches", "ground_truth",
    ]:
        cols = TABLE_COLUMNS[table]
        if table in ("reward_tier_eligibility", "rule_tier_rate"):
            pk = ", ".join(cols[:2])
        else:
            pk = cols[0]
        col_defs = []
        for i, col in enumerate(cols):
            coltype = SQL_COL_TYPES.get(col, "TEXT")
            if i == 0:
                coltype = "TEXT PRIMARY KEY" if table not in ("reward_tier_eligibility", "rule_tier_rate") else "TEXT"
            elif col in ("rank", "version", "points_cost", "cash_value_cents", "min_tier_rank",
                         "gross_cents", "discount_cents", "tax_cents", "shipping_cents",
                         "net_eligible_cents", "refund_cents", "quantity", "unit_price_cents",
                         "line_net_cents", "returned_qty", "returned_amount_cents", "points_delta",
                         "points_requested", "balance_before", "balance_after", "points_expired",
                         "lot_count", "available_points", "pending_points", "lifetime_earned_points",
                         "qualifying_spend_cents", "qualify_spend_cents"):
                coltype = "INTEGER"
            elif col == "earn_multiplier":
                coltype = "REAL"
            else:
                coltype = "TEXT"
            col_defs.append(f"  {col} {coltype}")
        create_lines.append(f"CREATE TABLE {table} (")
        create_lines.append(",\n".join(col_defs))
        if table in ("reward_tier_eligibility", "rule_tier_rate"):
            create_lines[-1] += f",\n  PRIMARY KEY ({pk})"
        create_lines.append(");")
        create_lines.append("")
    create_lines += [
        "CREATE INDEX idx_pts_account_time ON points_transactions(account_id, posted_at);",
        "CREATE INDEX idx_pts_order ON points_transactions(source_order_id);",
        "CREATE INDEX idx_orders_customer ON orders(customer_id, order_ts);",
        "CREATE INDEX idx_redemptions_account ON redemptions(account_id, requested_at);",
        "CREATE INDEX idx_expiry_account ON expiry_batches(account_id, run_at);",
        "PRAGMA foreign_keys = ON;",
        "",
    ]
    (sql_dir / "schema.sql").write_text("\n".join(create_lines), encoding="utf-8")

    with (sql_dir / "seed.sql").open("w", encoding="utf-8") as fh:
        fh.write("-- Full deterministic seed generated by ledgerline.generate/1.4.2\n")
        fh.write("-- Synthetic data only. Do not join ground_truth into model features.\n")
        fh.write("PRAGMA foreign_keys = OFF;\nBEGIN TRANSACTION;\n")
        for table, rows in tables.items():
            if not rows:
                continue
            cols = TABLE_COLUMNS[table]
            col_sql = ", ".join(cols)
            batch = []
            for row in rows:
                vals = ", ".join(sql_literal(row.get(c, "")) for c in cols)
                batch.append(f"({vals})")
                if len(batch) >= 200:
                    fh.write(f"INSERT INTO {table} ({col_sql}) VALUES\n")
                    fh.write(",\n".join(batch) + ";\n")
                    batch = []
            if batch:
                fh.write(f"INSERT INTO {table} ({col_sql}) VALUES\n")
                fh.write(",\n".join(batch) + ";\n")
        fh.write("COMMIT;\n")
    return sql_dir


def build_site_payload(tables, validation, metadata, checksums, reproducibility=None):
    customers = {r["customer_id"]: r for r in tables["customers"]}
    accounts = tables["loyalty_accounts"]
    account_by_id = {r["account_id"]: r for r in accounts}
    tiers = {r["tier_id"]: r for r in tables["tiers"]}
    rewards = {r["reward_id"]: r for r in tables["rewards"]}
    pts = tables["points_transactions"]
    redemptions = tables["redemptions"]
    orders = tables["orders"]
    batches = tables["expiry_batches"]
    gt = tables["ground_truth"]

    def account_name(account_id):
        acc = account_by_id.get(account_id)
        if not acc:
            return "Unknown"
        cust = customers.get(acc["customer_id"], {})
        return f"{cust.get('first_name', '')} {cust.get('last_name', '')}".strip()

    balances = defaultdict(int)
    type_totals = defaultdict(int)
    type_counts = Counter()
    monthly = defaultdict(lambda: {"earned": 0, "redeemed": 0, "expired": 0, "reversed": 0, "count": 0})
    for row in pts:
        balances[row["account_id"]] += row["points_delta"]
        type_counts[row["txn_type"]] += 1
        value = row["points_delta"]
        if value > 0 and row["txn_type"] in ("ACCRUAL", "BONUS", "ADJUSTMENT"):
            type_totals["earned"] += value
        if row["txn_type"] == "REDEMPTION":
            type_totals["redeemed"] += abs(value)
        if row["txn_type"] == "EXPIRATION":
            type_totals["expired"] += abs(value)
        if row["txn_type"] == "REVERSAL":
            type_totals["reversed"] += abs(value)
        month = row["posted_at"][:7]
        if month >= "2025-05":
            if value > 0 and row["txn_type"] in ("ACCRUAL", "BONUS", "ADJUSTMENT"):
                monthly[month]["earned"] += value
            elif row["txn_type"] == "REDEMPTION":
                monthly[month]["redeemed"] += abs(value)
            elif row["txn_type"] == "EXPIRATION":
                monthly[month]["expired"] += abs(value)
            elif row["txn_type"] == "REVERSAL":
                monthly[month]["reversed"] += abs(value)
            monthly[month]["count"] += 1
    outstanding = sum(balances.values())
    tier_counts = Counter(a["tier_id"] for a in accounts)
    tier_mix = []
    for tier_id in sorted(tiers):
        tier = tiers[tier_id]
        tier_accounts = [a for a in accounts if a["tier_id"] == tier_id]
        tier_mix.append({
            "tier_id": tier_id,
            "tier_name": tier["tier_name"],
            "rank": tier["rank"],
            "qualify_spend_cents": tier["qualify_spend_cents"],
            "accounts": len(tier_accounts),
            "points": sum(balances[a["account_id"]] for a in tier_accounts),
            "share": pct(len(tier_accounts), len(accounts)),
        })
    approved = sum(1 for r in redemptions if r["status"] == "approved")
    rejected = len(redemptions) - approved
    returned_orders = sum(1 for o in orders if o["status"] == "returned")
    partial_orders = sum(1 for o in orders if o["status"] == "partially_returned")
    mismatch_count = sum(1 for g in gt if g["issue_type"] == "balance_differs_from_ledger")
    ledger_match_rate = round((1 - mismatch_count / max(1, len(accounts))) * 100, 2)
    active_accounts = sum(1 for a in accounts if a["status"] == "active")

    # A deterministic, useful sample rather than a random dump of 300k rows.
    by_type = defaultdict(list)
    for row in pts:
        by_type[row["txn_type"]].append(row)
    recent = sorted(pts, key=lambda r: r["posted_at"], reverse=True)[:140]
    sample = {r["points_txn_id"]: r for r in recent}
    per_type = 48
    for txn_type, rows in by_type.items():
        sorted_rows = sorted(rows, key=lambda r: r["posted_at"], reverse=True)
        step = max(1, len(sorted_rows) // per_type)
        for row in sorted_rows[::step][:per_type]:
            sample[row["points_txn_id"]] = row
    p = random.Random(20261022)
    extra = p.sample(pts, min(120, len(pts)))
    for row in extra:
        sample[row["points_txn_id"]] = row
    ledger = []
    for row in sample.values():
        acc = account_by_id.get(row["account_id"], {})
        cust = customers.get(acc.get("customer_id", ""), {})
        ledger.append({
            "points_txn_id": row["points_txn_id"],
            "account_id": row["account_id"],
            "customer_name": f"{cust.get('first_name', '')} {cust.get('last_name', '')}".strip(),
            "tier_name": tiers.get(acc.get("tier_id", ""), {}).get("tier_name", ""),
            "txn_type": row["txn_type"],
            "points_delta": row["points_delta"],
            "posted_at": row["posted_at"],
            "status": row["status"],
            "source_order_id": row["source_order_id"],
            "source_order_line_id": row["source_order_line_id"],
            "reversal_of_pts_id": row["reversal_of_pts_id"],
            "redemption_id": row["redemption_id"],
            "expiry_batch_id": row["expiry_batch_id"],
            "expiry_source_pts_id": row["expiry_source_pts_id"],
            "rule_id": row["rule_id"],
            "expires_at": row["expires_at"],
            "description": row["description"],
        })
    ledger.sort(key=lambda r: (r["posted_at"], r["points_txn_id"]), reverse=True)

    account_sample_ids = set()
    top_accounts = sorted(accounts, key=lambda a: balances[a["account_id"]], reverse=True)[:100]
    account_sample_ids.update(a["account_id"] for a in top_accounts)
    while len(account_sample_ids) < min(240, len(accounts)):
        account_sample_ids.add(p.choice(accounts)["account_id"])
    account_rows = []
    for account_id in account_sample_ids:
        acc = account_by_id[account_id]
        cust = customers[acc["customer_id"]]
        account_rows.append({
            "account_id": account_id,
            "customer_id": cust["customer_id"],
            "customer_name": f"{cust['first_name']} {cust['last_name']}",
            "email": cust["email"],
            "region": cust["region"],
            "city": cust["city"],
            "tier_id": acc["tier_id"],
            "tier_name": tiers.get(acc["tier_id"], {}).get("tier_name", ""),
            "status": acc["status"],
            "available_points": acc["available_points"],
            "lifetime_earned_points": acc["lifetime_earned_points"],
            "qualifying_spend_cents": acc["qualifying_spend_cents"],
            "opened_at": acc["opened_at"],
            "last_activity_at": acc["last_activity_at"],
        })
    account_rows.sort(key=lambda r: r["customer_name"])
    order_sample = []
    for order in sorted(orders, key=lambda o: o["order_ts"], reverse=True)[:120]:
        cust = customers[order["customer_id"]]
        order_sample.append({
            "order_id": order["order_id"],
            "customer_id": order["customer_id"],
            "customer_name": f"{cust['first_name']} {cust['last_name']}",
            "order_ts": order["order_ts"],
            "channel": order["channel"],
            "store_id": order["store_id"],
            "gross_cents": order["gross_cents"],
            "tax_cents": order["tax_cents"],
            "shipping_cents": order["shipping_cents"],
            "net_eligible_cents": order["net_eligible_cents"],
            "refund_cents": order["refund_cents"],
            "status": order["status"],
            "returned_at": order["returned_at"],
        })
    cases = []
    for row in gt:
        try:
            evidence = json.loads(row["evidence"]) if isinstance(row["evidence"], str) else row["evidence"]
        except Exception:
            evidence = {}
        cases.append({
            "case_id": row["case_id"],
            "issue_type": row["issue_type"],
            "entity_type": row["entity_type"],
            "entity_id": row["entity_id"],
            "related_entity_id": row["related_entity_id"],
            "expected_label": row["expected_label"],
            "expected_decision": row["expected_decision"],
            "severity": row["severity"],
            "detection_rule": row["detection_rule"],
            "notes": row["notes"],
            "evidence": evidence,
        })
    months = sorted(monthly.keys())[-18:]
    monthly_series = []
    for month in months:
        entry = dict(monthly[month])
        entry["month"] = month
        monthly_series.append(entry)

    # Table counts / sizes for the build inventory page.
    row_counts = {k: len(v) for k, v in tables.items()}
    summary = {
        "customers": len(accounts),
        "active_accounts": active_accounts,
        "orders": len(orders),
        "order_lines": row_counts["order_lines"],
        "points_transactions": len(pts),
        "redemptions": len(redemptions),
        "approved_redemptions": approved,
        "rejected_redemptions": rejected,
        "approval_rate": pct(approved, len(redemptions)),
        "expiry_batches": len(batches),
        "ground_truth_cases": len(gt),
        "returned_orders": returned_orders,
        "partial_returns": partial_orders,
        "return_rate": pct(returned_orders + partial_orders, len(orders)),
        "points_outstanding": outstanding,
        "outstanding_value_cents": outstanding,
        "points_earned": type_totals["earned"],
        "points_redeemed": type_totals["redeemed"],
        "points_expired": type_totals["expired"],
        "points_reversed": type_totals["reversed"],
        "ledger_match_rate": ledger_match_rate,
        "mismatch_accounts": mismatch_count,
        "type_counts": dict(type_counts),
        "tier_mix": tier_mix,
    }
    id_rules = [
        {"entity": "Customer", "pattern": "C-000001", "rule": "C- + six-digit sequence; immutable."},
        {"entity": "LoyaltyAccount", "pattern": "LOY-C-000001", "rule": "LOY- + customer_id. One account per customer."},
        {"entity": "Order", "pattern": "ORD-2026-000001", "rule": "ORD- + order year + six-digit year sequence."},
        {"entity": "OrderLine", "pattern": "OL-2026-000001", "rule": "OL- + order year + six-digit line sequence."},
        {"entity": "PointsTransaction", "pattern": "PTS-2026-00000001", "rule": "Snapshot year + eight-digit posting sequence."},
        {"entity": "Redemption", "pattern": "RDM-2026-000001", "rule": "Snapshot year + six-digit attempt sequence."},
        {"entity": "ExpiryBatch", "pattern": "EXP-2026-000001", "rule": "Snapshot year + six-digit batch sequence."},
        {"entity": "TierHistory", "pattern": "TH-2026-000001", "rule": "Change year + six-digit sequence."},
        {"entity": "Reward", "pattern": "RWD-02", "rule": "RWD- + two-digit catalogue sequence."},
        {"entity": "GroundTruth", "pattern": "GT-2026-0001", "rule": "GT- + snapshot year + case sequence."},
    ]
    payload = {
        "meta": {
            **metadata,
            "generated_at": iso(AS_OF),
            "customer_label": "Morrow & Finch",
            "source": "Synthetic only; no external or personal data",
            "license": "Generated data CC BY 4.0 · demonstration build",
        },
        "summary": summary,
        "monthly": monthly_series,
        "ledger": ledger,
        "accounts": account_rows,
        "orders": order_sample,
        "exceptions": cases,
        "validation": validation,
        "checksums": checksums,
        "reproducibility": reproducibility,
        "tiers": [
            {**t, "accounts": tier_counts.get(t["tier_id"], 0)} for t in tables["tiers"]
        ],
        "rules": tables["rules"],
        "rewards": [
            {**r, "eligible_tiers": [
                t["tier_id"] for t in tables["tiers"]
                if int(t["rank"]) >= int(r["min_tier_rank"])
            ]} for r in tables["rewards"]
        ],
        "dataDictionary": DATA_DICTIONARY,
        "idRules": id_rules,
        "tableCounts": row_counts,
        "links": {
            "csv": "data/csv/",
            "json": "data/json/ground_truth.json",
            "schema": "data/sql/schema.sql",
            "seed": "data/sql/seed.sql",
            "bundle": "data/ledgerline_bundle.zip",
            "readme": "docs/README.md",
            "dictionary": "docs/DATA_DICTIONARY.md",
            "validation": "docs/VALIDATION_SUMMARY.md",
        },
    }
    return payload


def write_site_assets(payload, out_dir: Path, project_root: Path):
    json_path = out_dir / "json" / "site-data.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    js_dir = project_root / "assets" / "js"
    js_dir.mkdir(parents=True, exist_ok=True)
    js_text = "window.LEDGER_DATA = " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";\n"
    (js_dir / "data.js").write_text(js_text, encoding="utf-8")
    return json_path, js_dir / "data.js"


ENTITY_RELATIONSHIPS = [
    ("Customer", "LoyaltyAccount", "1:1", "Every customer has exactly one account in this build; account is optional only for prospects."),
    ("Tier", "LoyaltyAccount", "1:N", "One current tier per account; tier changes retained in TierHistory."),
    ("Tier", "Rule", "M:N", "Mapped through rule_tier_rate with an earn multiplier."),
    ("Reward", "Tier", "M:N", "Mapped through reward_tier_eligibility."),
    ("Customer", "Order", "1:N", "Orders must reference a valid customer; account open must precede order."),
    ("Order", "OrderLine", "1:N", "One or more product lines per order; all line totals reconcile to the order."),
    ("Order", "PointsTransaction", "1:N", "Accrual rows optionally link to an order and a line; reversals reference the original accrual."),
    ("LoyaltyAccount", "PointsTransaction", "1:N", "Ledger is the source of truth for the materialised balance."),
    ("Reward", "Redemption", "1:N", "A rejected attempt still references a valid reward; only approved attempts post points."),
    ("LoyaltyAccount", "Redemption", "1:N", "Every attempt belongs to one account; request groups model concurrency."),
    ("LoyaltyAccount", "ExpiryBatch", "1:N", "One batch per account per monthly run; may contain several lots."),
    ("ExpiryBatch", "PointsTransaction", "1:N", "Each expiration row references its batch and the source lot."),
    ("LoyaltyAccount", "TierHistory", "1:N", "Append-only tier changes with effective time and rule."),
]


def write_docs(out_dir: Path, tables, validation, metadata, checksums, project_root: Path):
    docs_dir = project_root / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    counts = validation["counts"]
    issue_counts = validation["issue_counts"]
    seed = metadata["seed"]
    readme = f"""# Ledgerline: synthetic loyalty ledger

A working, deterministic synthetic-data build for the Morrow & Finch loyalty
ledger exercise. The same generator produces a starter sample and the full
build, so every demonstration row can be traced back to a documented rule.

## At a glance

| Item | Value |
|---|---|
| Build | {metadata['build_id']} |
| Seed | `{seed}` |
| Snapshot | {metadata['as_of']} |
| Customers / accounts | {counts['customers']:,} / {counts['loyalty_accounts']:,} |
| Orders / order lines | {counts['orders']:,} / {counts['order_lines']:,} |
| Points ledger rows | {counts['points_transactions']:,} |
| Redemption attempts | {counts['redemptions']:,} |
| Expiry batches | {counts['expiry_batches']:,} |
| Labelled ground-truth cases | {counts['ground_truth_cases']:,} |
| Validation | {validation['passed']} pass / {validation['warnings']} warnings / {validation['failed']} fail |

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
python generator/generate.py --seed {seed} --out data
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
python generator/generate.py --seed {seed} --customers 200 --orders 1000 \\
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
  families, {counts['ground_truth_cases']} cases in all, are labelled in
  `ground_truth.csv` / `ground_truth.json`.

## Deliberately injected edge cases

| `issue_type` | Cases | Intended handling |
|---|---:|---|
| balance_differs_from_ledger | {issue_counts.get('balance_differs_from_ledger', 0)} | Rebuild materialised balance from ledger |
| redemption_exceeds_available_points | {issue_counts.get('redemption_exceeds_available_points', 0)} | Reject, no posted ledger row |
| returned_order_keeps_all_points | {issue_counts.get('returned_order_keeps_all_points', 0)} | Reverse the missing line accruals |
| points_expire_twice | {issue_counts.get('points_expire_twice', 0)} | Void duplicate expiry batch and restore points |
| tier_uses_gross_spend | {issue_counts.get('tier_uses_gross_spend', 0)} | Recalculate from qualifying spend |
| concurrent_redemption_attempt | {issue_counts.get('concurrent_redemption_attempt', 0)} | Approve first, reject second with lock |

Ground truth is a separate table and file. It is not a feature in any input
table and must not be joined into model features.

## Entity relationships

| Parent | Child | Cardinality | Note |
|---|---|---|---|
""" + "\n".join(
        f"| {a} | {b} | {c} | {note} |" for a, b, c, note in ENTITY_RELATIONSHIPS
    ) + f"""

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

The generator is stdlib-only and seeded by `random.Random({seed})`. Re-running
the same command produces identical row counts and SHA-256 table checksums.
`--verify-repro` performs the second build automatically; the comparison is
written to `data/reproducibility.json`.

## Public data and provenance

No external data was used. The build contains only deterministic synthetic
records generated from this repository's rules. See
`docs/SOURCE_MANIFEST.json` for the explicit provenance record, licence and
transformation list.
"""
    (docs_dir / "README.md").write_text(readme, encoding="utf-8")
    (project_root / "README.md").write_text(readme, encoding="utf-8")

    dictionary_lines = [
        "# Ledgerline data dictionary",
        "",
        "Generated from the same source constants as the dataset. The field-level",
        "dictionary covers the ten core entities plus the tier history and bridge tables.",
        "",
    ]
    for entity in DATA_DICTIONARY:
        dictionary_lines.append(f"## {entity['entity']} (`{entity['table']}`)")
        dictionary_lines.append("")
        dictionary_lines.append(entity["description"])
        dictionary_lines.append("")
        dictionary_lines.append("Primary key: `" + entity["primary_key"] + "`")
        dictionary_lines.append("")
        dictionary_lines.append("| Field | Type | Required | Example | Units | Uniqueness / validation |")
        dictionary_lines.append("|---|---|---|---|---|---|")
        for field in entity["fields"]:
            dictionary_lines.append("| " + " | ".join(str(x).replace("|", "\\|") for x in field) + " |")
        dictionary_lines.append("")
    dictionary_lines += [
        "## Bridge tables",
        "",
        "### `rule_tier_rate`",
        "",
        "Composite key: (`rule_id`, `tier_id`). Effective earn multiplier per policy version.",
        "",
        "| Field | Type | Required | Validation |",
        "|---|---|---|---|",
        "| rule_id | string FK | yes | references rules.rule_id |",
        "| tier_id | string FK | yes | references tiers.tier_id |",
        "| earn_multiplier | decimal | yes | > 0; unique per rule/tier pair |",
        "| effective_from | date | yes | matches the policy effective date |",
        "",
        "### `reward_tier_eligibility`",
        "",
        "Composite key: (`reward_id`, `tier_id`). Controls which tiers may see a reward.",
        "",
        "| Field | Type | Required | Validation |",
        "|---|---|---|---|",
        "| reward_id | string FK | yes | references rewards.reward_id |",
        "| tier_id | string FK | yes | references tiers.tier_id |",
        "| eligible | boolean | yes | true only when tier rank >= reward.min_tier_rank |",
        "",
        "## Entity relationships",
        "",
        "| Parent | Child | Cardinality | Note |",
        "|---|---|---|---|",
    ]
    dictionary_lines += [
        f"| {a} | {b} | {c} | {note} |" for a, b, c, note in ENTITY_RELATIONSHIPS
    ]
    dictionary_lines += [
        "",
        "## Lifecycle states",
        "",
        "- **Customer:** active, inactive, deactivated.",
        "- **LoyaltyAccount:** active, suspended, closed.",
        "- **Order:** completed, partially_returned, returned, voided.",
        "- **PointsTransaction:** posted, partially_reversed (accrual), reversed (accrual).",
        "- **Redemption:** approved, rejected (with a decision reason).",
        "- **ExpiryBatch:** posted, void.",
        "- **Rule / Tier / Reward:** draft or active/superseded, retired, with effective dates.",
        "",
        "## ID grammar",
        "",
        "| Entity | Pattern | Rule |",
        "|---|---|---|",
    ]
    id_rules = [
        ("Customer", "C-000001", "six-digit immutable sequence"),
        ("LoyaltyAccount", "LOY-C-000001", "LOY- + customer_id"),
        ("Order", "ORD-2026-000001", "year of order + six-digit sequence"),
        ("OrderLine", "OL-2026-000001", "year of order + six-digit sequence"),
        ("PointsTransaction", "PTS-2026-00000001", "snapshot year + eight-digit posting sequence"),
        ("Redemption", "RDM-2026-000001", "snapshot year + six-digit attempt sequence"),
        ("ExpiryBatch", "EXP-2026-000001", "snapshot year + six-digit batch sequence"),
        ("TierHistory", "TH-2026-000001", "change year + six-digit sequence"),
        ("GroundTruth", "GT-2026-0001", "snapshot year + case sequence"),
    ]
    dictionary_lines += [f"| {e} | `{p}` | {r} |" for e, p, r in id_rules]
    (docs_dir / "DATA_DICTIONARY.md").write_text("\n".join(dictionary_lines) + "\n", encoding="utf-8")

    validation_lines = [
        "# Validation summary",
        "",
        f"Build `{metadata['build_id']}` · seed `{seed}` · snapshot {metadata['as_of']}",
        "",
        f"**{validation['passed']} passed**, **{validation['warnings']} expected warnings**,",
        f"**{validation['failed']} failures** across {validation['total_checks']} checks.",
        "",
        "| Check | Result | Detail |",
        "|---|---|---|",
    ]
    for check in validation["checks"]:
        validation_lines.append(f"| {check['label']} | {check['result']} | {check['detail']} |")
    validation_lines += [
        "",
        "## Exception register",
        "",
        "| Issue type | Count | Severity | Expected handling |",
        "|---|---:|---|---|",
    ]
    labels = {
        "balance_differs_from_ledger": ("high", "Rebuild materialised balance from ledger"),
        "redemption_exceeds_available_points": ("medium", "Reject; do not post a ledger row"),
        "returned_order_keeps_all_points": ("high", "Post missing reversals to the original accruals"),
        "points_expire_twice": ("high", "Void duplicate batch; restore points"),
        "tier_uses_gross_spend": ("medium", "Reapply trailing qualifying-spend rule"),
        "concurrent_redemption_attempt": ("medium", "Approve one; reject the second with concurrent_lock"),
    }
    for issue, count in sorted(issue_counts.items()):
        severity, handling = labels.get(issue, ("medium", "Review against ground truth"))
        validation_lines.append(f"| `{issue}` | {count} | {severity} | {handling} |")
    validation_lines += [
        "",
        "Warnings are expected labelled exceptions, not silent corruption. The original",
        "history is retained; anomalies exist only in the documented fields and are",
        "available separately in `ground_truth.csv` / `ground_truth.json`.",
    ]
    (docs_dir / "VALIDATION_SUMMARY.md").write_text("\n".join(validation_lines) + "\n", encoding="utf-8")

    source_manifest = {
        "dataset": "Ledgerline loyalty ledger — Morrow & Finch synthetic build",
        "build_id": metadata["build_id"],
        "version": metadata["generator_version"],
        "generated_at": metadata["as_of"],
        "seed": seed,
        "synthetic": True,
        "external_sources": [],
        "reference_data": "Schema and workflow patterns are original; no public dataset was copied.",
        "provenance": "All records generated locally by generator/generate.py using business rules and a fixed seed.",
        "license": {
            "generated_data": "CC BY 4.0",
            "code": "MIT",
            "attribution": "Ledgerline demonstration build",
        },
        "personal_data": {
            "used": False,
            "note": "Names, emails and addresses are synthetic. Emails use the reserved .test domain.",
        },
        "transformations": [
            "Tier rank derived from trailing 365-day net-eligible spend after returns.",
            "Earn points derived per eligible line from net line spend, policy version and tier multiplier.",
            "Return reversal amounts derived pro rata from the original line accrual.",
            "Redemption decisions evaluated sequentially against the running ledger balance.",
            "Expiry batches derived from lot expiry dates and remaining lot balance.",
            "Materialised account metrics derived from the immutable points ledger.",
        ],
        "fields_discarded": [],
        "volumes": validation["counts"],
        "checksums": "manifest.json",
        "ground_truth_separated": True,
    }
    (docs_dir / "SOURCE_MANIFEST.json").write_text(
        json.dumps(source_manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return docs_dir


def write_manifest(out_dir: Path, tables, validation, metadata, checksums, reproducibility=None):
    files = []
    for folder in ["csv", "jsonl", "json", "sql"]:
        p = out_dir / folder
        if p.exists():
            for f in sorted(p.glob("*")):
                if f.is_file():
                    files.append({
                        "path": f.relative_to(out_dir).as_posix(),
                        "bytes": f.stat().st_size,
                    })
    manifest = {
        "dataset": "Ledgerline loyalty ledger — Morrow & Finch synthetic build",
        "build_id": metadata["build_id"],
        "seed": metadata["seed"],
        "as_of": metadata["as_of"],
        "generator": metadata["generator_version"],
        "synthetic": True,
        "personal_data_used": False,
        "external_sources": [],
        "license": "Generated data CC BY 4.0; code MIT",
        "row_counts": {k: len(v) for k, v in tables.items()},
        "checksums": checksums,
        "validation": {
            "passed": validation["passed"],
            "warnings": validation["warnings"],
            "failed": validation["failed"],
            "checks": validation["checks"],
            "issue_counts": validation["issue_counts"],
        },
        "ground_truth_file": "json/ground_truth.json",
        "reproducibility": reproducibility,
        "files": files,
    }
    path = out_dir / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate the Ledgerline loyalty ledger dataset.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--customers", type=int, default=20000)
    parser.add_argument("--orders", type=int, default=100000)
    parser.add_argument("--transactions", type=int, default=300000)
    parser.add_argument("--bonus", type=int, default=None,
                        help="base bonus lots (default: 6%% of orders)")
    parser.add_argument("--attempts", type=int, default=None,
                        help="pre-scheduled redemption attempts (default: 50%% of orders)")
    parser.add_argument("--out", default="data")
    parser.add_argument("--skip-sql", action="store_true", help="skip the large seed.sql export")
    parser.add_argument("--verify-repro", action="store_true",
                        help="generate a second in-memory build and compare row counts/checksums")
    args = parser.parse_args(argv)

    project_root = Path(__file__).resolve().parent.parent
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = project_root / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    tables, validation, metadata = generate_dataset(args)
    checksums = table_checksums(tables)

    print("[8/8] writing exports", flush=True)
    write_csvs(out_dir, tables)
    write_jsonl(out_dir, tables)
    if not args.skip_sql:
        write_sql(out_dir, tables)
    write_docs(out_dir, tables, validation, metadata, checksums, project_root)

    reproducibility = None
    if args.verify_repro:
        print("       reproducibility: rebuilding in memory for run B", flush=True)
        tables_b, validation_b, metadata_b = generate_dataset(args)
        checksums_b = table_checksums(tables_b)
        table_matches = {
            table: checksums[table]["rows"] == checksums_b[table]["rows"]
            and checksums[table]["sha256"] == checksums_b[table]["sha256"]
            for table in checksums
        }
        counts_match = validation["counts"] == validation_b["counts"]
        identical = all(table_matches.values()) and counts_match
        reproducibility = {
            "seed": args.seed,
            "generated_at": iso(AS_OF),
            "run_a": {
                "row_counts": validation["counts"],
                "checksums": checksums,
            },
            "run_b": {
                "row_counts": validation_b["counts"],
                "checksums": checksums_b,
            },
            "tables_compared": len(table_matches),
            "tables_identical": sum(table_matches.values()),
            "identities": table_matches,
            "counts_identical": counts_match,
            "identical": identical,
        }
        (out_dir / "reproducibility.json").write_text(
            json.dumps(reproducibility, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(
            f"       reproducibility: {sum(table_matches.values())}/{len(table_matches)} tables identical; "
            f"seed {args.seed}", flush=True,
        )

    payload = build_site_payload(tables, validation, metadata, checksums, reproducibility)
    write_site_assets(payload, out_dir, project_root)
    write_manifest(out_dir, tables, validation, metadata, checksums, reproducibility)

    print("")
    print(f"Build complete: {metadata['build_id']}")
    print(f"  customers      {validation['counts']['customers']:,}")
    print(f"  orders         {validation['counts']['orders']:,}")
    print(f"  ledger rows    {validation['counts']['points_transactions']:,}")
    print(f"  ground truth   {validation['counts']['ground_truth_cases']:,} cases")
    print(f"  validation     {validation['passed']} pass / {validation['warnings']} warning / {validation['failed']} fail")
    print(f"  project        {project_root}")
    print(f"  output         {out_dir}")
    return 0 if validation["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
