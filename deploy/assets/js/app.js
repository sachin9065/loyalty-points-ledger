/* Ledgerline — client application.
   Reads window.LEDGER_DATA (written by generator/generate.py) and renders
   the operator views. No build step, no external dependencies. */

(function () {
  "use strict";

  var D = window.LEDGER_DATA;
  var app = document.getElementById("app");
  if (!D || !app) {
    if (app) {
      app.innerHTML = '<p style="padding:48px 0;font-family:monospace">The data payload did not load. Run <code>python generator/generate.py</code> and reload.</p>';
    }
    return;
  }

  // ---- data host override (see assets/js/config.js) ----
  // When the downloads live on R2/S3 instead of next to the site, point
  // window.LEDGER_DATA_BASE_URL (or ?data=...) at the bucket root.
  // Re-applied on every route render so ?data= works even when appended
  // after the page has loaded (hash-only navigation).
  function resolveDataBase() {
    var base = (window.LEDGER_DATA_BASE_URL || "").replace(/\/+$/, "");
    try {
      var q = new URLSearchParams(location.search).get("data");
      if (!q) {
        var hashQuery = (location.hash || "").split("?", 2)[1] || "";
        q = new URLSearchParams(hashQuery).get("data");
      }
      if (q) base = q.replace(/\/+$/, "");
    } catch (e) { /* URLSearchParams unavailable */ }
    return base;
  }

  function applyDataLinks() {
    var base = resolveDataBase();
    if (!base) return;
    if (D.links.csv.indexOf(base) !== 0) D.links.csv = base + "/data/csv/";
    if (D.links.jsonl.indexOf(base) !== 0) D.links.jsonl = base + "/data/jsonl/";
    D.links.json = base + "/data/json/ground_truth.json";
    D.links.schema = base + "/data/sql/schema.sql";
    D.links.seed = base + "/data/sql/seed.sql";
    D.links.bundle = base + "/data/ledgerline_bundle.zip";
    D.links.manifest = base + "/data/manifest.json";
    D.links.repro = base + "/data/reproducibility.json";
    document.querySelectorAll('a[href^="data/"]').forEach(function (a) {
      a.setAttribute("href", base + "/" + a.getAttribute("href"));
    });
  }

  applyDataLinks();

  if (!D.links.jsonl) D.links.jsonl = "data/jsonl/";
  if (!D.links.manifest) D.links.manifest = "data/manifest.json";
  if (!D.links.repro) D.links.repro = "data/reproducibility.json";

  var S = D.summary;
  var M = D.meta;
  var V = D.validation;
  var K = D.checksums;

  var state = {
    route: "overview",
    chartRange: 18,
    ledger: { q: "", type: "all", sort: "mix", page: 1, size: 25 },
    accounts: { q: "", tier: "all", status: "all", sort: "name", page: 1, size: 20 },
    cases: { q: "", issue: "all", severity: "all", page: 1, size: 15 },
    refTab: "entities",
    refEntity: "Customer",
    pendingIssue: null,
    studio: { scale: "full", seed: String(M.seed) }
  };

  var ROUTE_LABELS = {
    overview: "Overview",
    ledger: "Points ledger",
    accounts: "Members",
    verification: "Verification",
    studio: "Data studio",
    reference: "Field guide"
  };

  var TYPE_LABELS = {
    ACCRUAL: "Accrual",
    BONUS: "Bonus",
    REDEMPTION: "Redemption",
    REVERSAL: "Reversal",
    EXPIRATION: "Expiration",
    ADJUSTMENT: "Adjustment"
  };

  var ISSUE_LABELS = {
    balance_differs_from_ledger: "Balance differs from ledger",
    redemption_exceeds_available_points: "Redemption exceeds available",
    returned_order_keeps_all_points: "Returned order keeps all points",
    concurrent_redemption_attempt: "Concurrent redemption attempt",
    tier_uses_gross_spend: "Tier set from gross spend",
    points_expire_twice: "Points expired twice"
  };

  var TIER_MULTIPLIERS = { 1: "1.00×", 2: "1.25×", 3: "1.50×", 4: "2.00×" };

  var ENTITY_DOMAINS = {
    Customer: "Programme",
    LoyaltyAccount: "Programme",
    Tier: "Programme",
    TierHistory: "Programme",
    Rule: "Governance",
    Order: "Commerce",
    OrderLine: "Commerce",
    PointsTransaction: "Ledger",
    Reward: "Catalogue",
    Redemption: "Ledger",
    ExpiryBatch: "Ledger"
  };

  var RELATIONSHIPS = [
    { parent: "Customer", child: "LoyaltyAccount", card: "1 : 1", note: "Every customer has exactly one account in this build." },
    { parent: "Tier", child: "LoyaltyAccount", card: "1 : N", note: "One current tier per account; changes are kept in TierHistory." },
    { parent: "Tier", child: "Rule", card: "M : N", note: "Mapped through rule_tier_rate with the earn multiplier." },
    { parent: "Reward", child: "Tier", card: "M : N", note: "Mapped through reward_tier_eligibility." },
    { parent: "Customer", child: "Order", card: "1 : N", note: "Orders reference a valid customer; account open precedes order." },
    { parent: "Order", child: "OrderLine", card: "1 : N", note: "Line totals reconcile to the order header." },
    { parent: "Order", child: "PointsTransaction", card: "1 : N", note: "Accruals may link to an order and a line; reversals link to the original accrual." },
    { parent: "LoyaltyAccount", child: "PointsTransaction", card: "1 : N", note: "The ledger is the source of truth for the materialised balance." },
    { parent: "Reward", child: "Redemption", card: "1 : N", note: "A rejected attempt still references a valid reward; only approvals post." },
    { parent: "LoyaltyAccount", child: "Redemption", card: "1 : N", note: "Every attempt belongs to one account; request groups model concurrency." },
    { parent: "LoyaltyAccount", child: "ExpiryBatch", card: "1 : N", note: "One batch per account per monthly run; may contain several lots." },
    { parent: "ExpiryBatch", child: "PointsTransaction", card: "1 : N", note: "Each expiration row references its batch and its source lot." },
    { parent: "LoyaltyAccount", child: "TierHistory", card: "1 : N", note: "Append-only tier changes with effective time and rule." },
    { parent: "GroundTruth", child: "Entity", card: "N : 1", note: "Polymorphic by entity_type and entity_id; never joined into features." }
  ];

  // ---------- formatting ----------

  var intFmt = new Intl.NumberFormat("en-GB");
  var moneyFmt = new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP" });
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  function esc(v) {
    return String(v == null ? "" : v)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function fmtInt(n) {
    return intFmt.format(Number(n) || 0);
  }

  function trimOne(n) {
    var s = (Math.round(n * 10) / 10).toFixed(1);
    return s.replace(/\.0$/, "");
  }

  function fmtCompact(n) {
    n = Number(n) || 0;
    var a = Math.abs(n);
    if (a >= 1e9) return trimOne(n / 1e9) + "B";
    if (a >= 1e6) return trimOne(n / 1e6) + "M";
    if (a >= 1e4) return trimOne(n / 1e3) + "k";
    return intFmt.format(n);
  }

  function fmtGBP(cents, compact) {
    var pounds = (Number(cents) || 0) / 100;
    if (!compact) return moneyFmt.format(pounds);
    var a = Math.abs(pounds);
    if (a >= 1e6) {
      var digits = a >= 1e7 ? 1 : 2;
      return "£" + (pounds / 1e6).toFixed(digits).replace(/\.?0+$/, "") + "M";
    }
    if (a >= 1e3) return "£" + Math.round(pounds / 1e3) + "k";
    return "£" + intFmt.format(Math.round(pounds));
  }

  function fmtDate(iso) {
    if (!iso) return "—";
    var d = new Date(iso);
    if (isNaN(d.getTime())) return esc(iso);
    return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" });
  }

  function fmtDateShort(iso) {
    if (!iso) return "—";
    var d = new Date(iso);
    if (isNaN(d.getTime())) return esc(iso);
    return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "2-digit", timeZone: "UTC" });
  }

  function fmtDateTime(iso) {
    if (!iso) return "—";
    var d = new Date(iso);
    if (isNaN(d.getTime())) return esc(iso);
    return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" }) +
      " · " + d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "UTC" }) + " UTC";
  }

  function fmtTime(iso) {
    if (!iso) return "—";
    var d = new Date(iso);
    if (isNaN(d.getTime())) return esc(iso);
    return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", timeZone: "UTC" }) +
      " · " + d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "UTC" });
  }

  function fmtMonth(month) {
    var parts = String(month).split("-");
    return (MONTHS[Number(parts[1]) - 1] || parts[1]) + " " + parts[0];
  }

  function fmtMonthShort(month, withYear) {
    var parts = String(month).split("-");
    var label = MONTHS[Number(parts[1]) - 1] || parts[1];
    return withYear ? label + " " + String(parts[0]).slice(2) : label;
  }

  function fmtParams(raw) {
    try {
      var obj = JSON.parse(raw);
      return Object.keys(obj).map(function (k) {
        var v = obj[k];
        if (Array.isArray(v)) v = v.join(" / ");
        return k.replace(/_/g, " ") + " " + v;
      }).join(" · ");
    } catch (e) {
      return String(raw || "");
    }
  }

  function titleCase(s) {
    return String(s || "").replace(/_/g, " ").replace(/\b\w/g, function (c) { return c.toUpperCase(); });
  }

  function signed(n) {
    n = Number(n) || 0;
    return (n > 0 ? "+" : n < 0 ? "−" : "") + fmtInt(Math.abs(n));
  }

  function hashShort(hash, n) {
    if (!hash) return "—";
    return String(hash).slice(0, n || 12) + "…";
  }

  function icon(name, cls) {
    return '<svg class="' + (cls || "icon") + '" aria-hidden="true"><use href="#i-' + name + '"></use></svg>';
  }

  function typePill(type) {
    var cls = String(type || "").toLowerCase();
    return '<span class="type-pill ' + cls + '">' + (TYPE_LABELS[type] || titleCase(type)) + "</span>";
  }

  function tierTag(name) {
    var cls = name === "Gold" ? " gold" : name === "Platinum" ? " platinum" : "";
    return '<span class="tier-tag' + cls + '">' + esc(name || "—") + "</span>";
  }

  function statusTag(status) {
    var cls = status === "active" || status === "posted" || status === "approved" ? "" : " high";
    return '<span class="severity' + cls + '">' + esc(String(status || "—").replace(/_/g, " ")) + "</span>";
  }

  function movementTag(status) {
    var cls = status === "posted" ? "" : " " + String(status || "").replace(/_/g, "_");
    return '<span class="movement-status' + cls + '">' + esc(String(status || "—").replace(/_/g, " ")) + "</span>";
  }

  function issueLabel(issue) {
    return ISSUE_LABELS[issue] || titleCase(issue);
  }

  function issueSeverity(issue) {
    var c = D.exceptions.find(function (x) { return x.issue_type === issue; });
    return c ? c.severity : "high";
  }

  function emptyRow(cols, message) {
    return '<tr class="empty-row"><td colspan="' + cols + '">' + esc(message) + "</td></tr>";
  }

  function pageNumbers(page, total) {
    var out = [];
    if (total <= 7) {
      for (var i = 1; i <= total; i++) out.push(i);
      return out;
    }
    out.push(1);
    if (page > 4) out.push("…");
    var start = Math.max(2, page - 1);
    var end = Math.min(total - 1, page + 1);
    for (var j = start; j <= end; j++) out.push(j);
    if (page < total - 3) out.push("…");
    out.push(total);
    return out;
  }

  function pagination(page, total, kind) {
    if (total <= 1) return "";
    var html = '<div class="pagination">';
    html += '<button class="page-btn" type="button" data-' + kind + '-page="' + (page - 1) + '" ' + (page <= 1 ? "disabled" : "") + ' aria-label="Previous page">' + icon("left") + "</button>";
    pageNumbers(page, total).forEach(function (p) {
      if (p === "…") {
        html += '<span class="page-btn" style="pointer-events:none">…</span>';
      } else {
        html += '<button class="page-btn' + (p === page ? " active" : "") + '" type="button" data-' + kind + '-page="' + p + '"' + (p === page ? ' aria-current="page"' : "") + ">" + p + "</button>";
      }
    });
    html += '<button class="page-btn" type="button" data-' + kind + '-page="' + (page + 1) + '" ' + (page >= total ? "disabled" : "") + ' aria-label="Next page">' + icon("right") + "</button>";
    html += "</div>";
    return html;
  }

  function sourceRef(row) {
    return row.source_order_id || row.redemption_id || row.expiry_batch_id || row.reversal_of_pts_id || "—";
  }

  // ---------- chrome / drawer / toast ----------

  var drawerLayer = document.getElementById("drawerLayer");
  var drawerBody = document.getElementById("drawerBody");
  var drawerKicker = document.getElementById("drawerKicker");
  var drawerClose = document.getElementById("drawerClose");
  var drawerScrim = document.getElementById("drawerScrim");
  var toastEl = document.getElementById("toast");
  var toastTimer = null;
  var lastFocus = null;

  function showToast(message) {
    if (!toastEl) return;
    toastEl.textContent = message;
    toastEl.classList.add("show");
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(function () { toastEl.classList.remove("show"); }, 2400);
  }

  function copyText(text, label) {
    var done = function () { showToast((label || "Value") + " copied"); };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done).catch(function () { legacyCopy(text, done); });
    } else {
      legacyCopy(text, done);
    }
  }

  function legacyCopy(text, done) {
    var ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.left = "-9999px";
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand("copy"); done(); } catch (e) { showToast("Copy failed"); }
    document.body.removeChild(ta);
  }

  function openDrawer(kicker, html) {
    if (!drawerLayer) return;
    lastFocus = document.activeElement;
    drawerKicker.textContent = kicker;
    drawerBody.innerHTML = html;
    drawerLayer.hidden = false;
    drawerLayer.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
    bindDrawerActions();
    window.setTimeout(function () { if (drawerClose) drawerClose.focus(); }, 20);
  }

  function closeDrawer() {
    if (!drawerLayer || drawerLayer.hidden) return;
    drawerLayer.hidden = true;
    drawerLayer.setAttribute("aria-hidden", "true");
    document.body.style.overflow = "";
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }

  function bindDrawerActions() {
    drawerBody.querySelectorAll("[data-copy]").forEach(function (btn) {
      btn.addEventListener("click", function () { copyText(btn.getAttribute("data-copy"), btn.getAttribute("data-copy-label") || "ID"); });
    });
    drawerBody.querySelectorAll("[data-open-account]").forEach(function (btn) {
      btn.addEventListener("click", function () { openAccountDrawer(btn.getAttribute("data-open-account")); });
    });
    drawerBody.querySelectorAll("[data-filter-account]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var id = btn.getAttribute("data-filter-account");
        closeDrawer();
        state.ledger.q = id;
        state.ledger.page = 1;
        if (state.route === "ledger") {
          renderRoute();
        } else {
          location.hash = "ledger";
        }
      });
    });
  }

  function detailRow(label, value, mono) {
    return '<div class="detail-row"><dt>' + esc(label) + "</dt><dd" + (mono ? ' class="mono"' : "") + ">" + value + "</dd></div>";
  }

  function auditStep(title, value) {
    return '<div class="audit-step"><strong>' + esc(title) + "</strong><span>" + esc(value || "—") + "</span></div>";
  }

  function openLedgerDrawer(txnId) {
    var r = D.ledger.find(function (x) { return x.points_txn_id === txnId; });
    if (!r) return;
    var steps = [];
    if (r.txn_type === "REVERSAL" && r.reversal_of_pts_id) {
      steps.push(["Original accrual", r.reversal_of_pts_id]);
      steps.push(["Reversal posted", r.points_txn_id + " · " + fmtDateTime(r.posted_at)]);
    } else if (r.txn_type === "REDEMPTION") {
      steps.push(["Redemption attempt", r.redemption_id || "Not linked"]);
      steps.push(["Points posted", r.points_txn_id + " · " + fmtDateTime(r.posted_at)]);
    } else if (r.txn_type === "EXPIRATION") {
      steps.push(["Expiry batch", r.expiry_batch_id || "Not linked"]);
      steps.push(["Source lot", r.expiry_source_pts_id || "Not linked"]);
    } else if (r.source_order_id) {
      steps.push(["Source order", r.source_order_id]);
      if (r.source_order_line_id) steps.push(["Order line", r.source_order_line_id]);
      steps.push(["Accrual posted", r.points_txn_id + " · " + fmtDateTime(r.posted_at)]);
    } else {
      steps.push(["Rule applied", r.rule_id || "—"]);
      steps.push(["Posting created", r.points_txn_id + " · " + fmtDateTime(r.posted_at)]);
    }
    steps.push(["Account", r.account_id]);

    var html = "";
    html += '<p class="kicker">' + TYPE_LABELS[r.txn_type] + " posting · " + esc(r.status) + "</p>";
    html += '<h2 class="drawer-title" id="drawerTitle">' + esc(r.points_txn_id) + "</h2>";
    html += '<p class="drawer-subtitle">' + esc(r.description) + "</p>";
    html += '<div class="drawer-amount">' + signed(r.points_delta) + ' <span class="unit">points</span></div>';
    html += '<div class="drawer-tags">' + typePill(r.txn_type) + movementTag(r.status) + tierTag(r.tier_name) + "</div>";
    html += '<div class="section-label">Posting record</div><dl class="detail-list">';
    html += detailRow("Member", esc(r.customer_name));
    html += detailRow("Account", esc(r.account_id), true);
    html += detailRow("Posted", esc(fmtDateTime(r.posted_at)));
    html += detailRow("Rule", esc(r.rule_id || "—"), true);
    if (r.source_order_id) html += detailRow("Source order", esc(r.source_order_id), true);
    if (r.source_order_line_id) html += detailRow("Order line", esc(r.source_order_line_id), true);
    if (r.redemption_id) html += detailRow("Redemption", esc(r.redemption_id), true);
    if (r.expiry_batch_id) html += detailRow("Expiry batch", esc(r.expiry_batch_id), true);
    if (r.expiry_source_pts_id) html += detailRow("Expiry source", esc(r.expiry_source_pts_id), true);
    if (r.reversal_of_pts_id) html += detailRow("Reverses", esc(r.reversal_of_pts_id), true);
    if (r.expires_at) html += detailRow("Lot expires", esc(fmtDate(r.expires_at)));
    html += "</dl>";
    html += '<div class="section-label">Trace</div><div class="audit-chain">';
    steps.forEach(function (s) { html += auditStep(s[0], s[1]); });
    html += "</div>";
    var accountInSample = D.accounts.some(function (a) { return a.account_id === r.account_id; });
    html += '<div class="drawer-actions">';
    html += '<button class="btn small" type="button" data-copy="' + esc(r.points_txn_id) + '" data-copy-label="Posting ID">' + icon("copy") + " Copy ID</button>";
    if (accountInSample) html += '<button class="btn small" type="button" data-open-account="' + esc(r.account_id) + '">' + icon("users") + " Open member</button>";
    else html += '<span class="drawer-action-note">Member detail is outside the 240-account browser sample.</span>';
    html += "</div>";
    openDrawer("Ledger detail", html);
  }

  function openAccountDrawer(accountId) {
    var a = D.accounts.find(function (x) { return x.account_id === accountId; });
    if (!a) {
      showToast("That account is outside the 240-member browser sample.");
      return;
    }
    var tier = D.tiers.find(function (t) { return t.tier_id === a.tier_id; });
    var mismatch = D.exceptions.find(function (c) {
      return c.issue_type === "balance_differs_from_ledger" && c.entity_id === accountId;
    });
    var rows = D.ledger.filter(function (r) { return r.account_id === accountId; }).slice(0, 6);

    var html = "";
    html += '<p class="kicker">Member account · ' + esc(a.status) + "</p>";
    html += '<h2 class="drawer-title" id="drawerTitle">' + esc(a.customer_name) + "</h2>";
    html += '<p class="drawer-subtitle">' + esc(a.email) + " · " + esc(a.city) + ", " + esc(a.region) + "</p>";
    html += '<div class="drawer-amount">' + fmtInt(a.available_points) + ' <span class="unit">available points</span></div>';
    html += '<div class="drawer-tags">' + tierTag(a.tier_name) + statusTag(a.status) + '<span class="severity">' + esc(a.account_id) + "</span></div>";
    if (mismatch) {
      html += '<div class="notice"><strong>Labelled mismatch.</strong> The stored balance is under ground-truth case ' + esc(mismatch.case_id) + ". Rebuild from the ledger; do not edit history.</div>";
    }
    html += '<div class="section-label">Account</div><dl class="detail-list">';
    html += detailRow("Customer", esc(a.customer_id), true);
    html += detailRow("Account", esc(a.account_id), true);
    html += detailRow("Tier", esc(a.tier_name) + (tier ? " · since threshold " + fmtGBP(tier.qualify_spend_cents) : ""));
    html += detailRow("Opened", esc(fmtDate(a.opened_at)));
    html += detailRow("Last activity", esc(a.last_activity_at ? fmtDate(a.last_activity_at) : "No activity"));
    html += detailRow("Lifetime earned", fmtInt(a.lifetime_earned_points) + " points");
    html += detailRow("Qualifying spend", fmtGBP(a.qualifying_spend_cents) + " <span class=\"muted\">trailing 365 days</span>");
    html += detailRow("Ledger status", mismatch ? "Stored balance differs from ledger sum" : "Reconciled to ledger at snapshot");
    html += "</dl>";
    html += '<div class="section-label">Recent postings in sample</div>';
    if (rows.length) {
      html += '<div class="mini-table-wrap"><table class="mini-table"><thead><tr><th>Posting</th><th>Type</th><th class="points-cell">Points</th></tr></thead><tbody>';
      rows.forEach(function (r) {
        html += '<tr data-txn-id="' + esc(r.points_txn_id) + '"><td class="id-cell">' + esc(r.points_txn_id) + '<div class="source-cell">' + esc(fmtDateShort(r.posted_at)) + "</div></td><td>" + typePill(r.txn_type) + '</td><td class="points-cell ' + (r.points_delta >= 0 ? "positive" : "negative") + '">' + signed(r.points_delta) + "</td></tr>";
      });
      html += "</tbody></table></div>";
    } else {
      html += '<p class="muted" style="font-size:10px">No postings from this account fall inside the 499-row browser sample. The full ledger is in the CSV export.</p>';
    }
    html += '<div class="drawer-actions">';
    html += '<button class="btn small" type="button" data-copy="' + esc(a.account_id) + '" data-copy-label="Account ID">' + icon("copy") + " Copy account</button>";
    if (rows.length) html += '<button class="btn small" type="button" data-filter-account="' + esc(a.account_id) + '">' + icon("ledger") + " Filter ledger</button>";
    else html += '<span class="drawer-action-note">No sampled postings to filter.</span>';
    html += "</div>";
    openDrawer("Member detail", html);
    drawerBody.querySelectorAll("tr[data-txn-id]").forEach(function (tr) {
      tr.addEventListener("click", function () { openLedgerDrawer(tr.getAttribute("data-txn-id")); });
    });
  }

  function openCaseDrawer(caseId) {
    var c = D.exceptions.find(function (x) { return x.case_id === caseId; });
    if (!c) return;
    var html = "";
    html += '<p class="kicker">Ground truth · ' + esc(c.severity) + " severity</p>";
    html += '<h2 class="drawer-title" id="drawerTitle">' + esc(c.case_id) + "</h2>";
    html += '<p class="drawer-subtitle">' + esc(issueLabel(c.issue_type)) + " · " + esc(c.entity_type) + " " + esc(c.entity_id) + "</p>";
    html += '<div class="drawer-tags"><span class="severity ' + esc(c.severity) + '">' + esc(c.severity) + "</span><span class=\"severity\">" + esc(c.expected_label) + "</span></div>";
    html += '<div class="notice"><strong>Expected handling.</strong> ' + esc(c.expected_decision) + "</div>";
    html += '<div class="section-label">Case record</div><dl class="detail-list">';
    html += detailRow("Issue", esc(issueLabel(c.issue_type)));
    html += detailRow("Entity", esc(c.entity_type) + " · " + esc(c.entity_id), true);
    if (c.related_entity_id) html += detailRow("Related", esc(c.related_entity_id), true);
    html += detailRow("Detection rule", esc(c.detection_rule), true);
    html += detailRow("Notes", esc(c.notes));
    html += "</dl>";
    html += '<div class="section-label">Evidence</div><pre class="evidence-block">' + esc(JSON.stringify(c.evidence, null, 2)) + "</pre>";
    html += '<div class="drawer-actions">';
    html += '<button class="btn small" type="button" data-copy="' + esc(c.case_id) + '" data-copy-label="Case ID">' + icon("copy") + " Copy case</button>";
    if (c.entity_type === "LoyaltyAccount") {
      var inSample = D.accounts.some(function (a) { return a.account_id === c.entity_id; });
      if (inSample) html += '<button class="btn small" type="button" data-open-account="' + esc(c.entity_id) + '">' + icon("users") + " Open member</button>";
    }
    html += '<a class="btn small" href="' + esc(D.links.json) + '" target="_blank" rel="noopener">' + icon("download") + " Ground truth</a>";
    html += "</div>";
    openDrawer("Exception detail", html);
  }

  // ---------- chart ----------

  function niceScale(maxRaw, ticks) {
    ticks = ticks || 4;
    var rawStep = Math.max(maxRaw, 1) / ticks;
    var magnitude = Math.pow(10, Math.floor(Math.log10(rawStep)));
    var residual = rawStep / magnitude;
    var factor = residual <= 1 ? 1 : residual <= 2 ? 2 : residual <= 5 ? 5 : 10;
    var step = factor * magnitude;
    return { max: step * ticks, step: step };
  }

  function chartMarkup() {
    var rows = D.monthly.slice(-state.chartRange);
    var W = 760, H = 252, L = 48, R = 12, T = 14, B = 27;
    var iw = W - L - R, ih = H - T - B;
    var maxRaw = 1;
    rows.forEach(function (r) {
      ["earned", "redeemed", "expired", "reversed"].forEach(function (k) { maxRaw = Math.max(maxRaw, r[k]); });
    });
    var scale = niceScale(maxRaw, 4);
    var max = scale.max;
    var x = function (i) { return rows.length === 1 ? L + iw / 2 : L + (i * iw) / (rows.length - 1); };
    var y = function (v) { return T + ih * (1 - v / max); };
    var base = T + ih;
    var svg = '<svg class="chart-svg" viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="Monthly points earned, redeemed, expired and reversed">';

    for (var g = 0; g <= 4; g++) {
      var gy = y(scale.step * g);
      svg += '<line class="axis-line" x1="' + L + '" y1="' + gy.toFixed(1) + '" x2="' + (W - R) + '" y2="' + gy.toFixed(1) + '"></line>';
      svg += '<text class="axis-label" x="' + (L - 8) + '" y="' + (gy + 3).toFixed(1) + '" text-anchor="end">' + fmtCompact(scale.step * g) + "</text>";
    }

    rows.forEach(function (r, i) {
      var isLast = i === rows.length - 1;
      var show = i === 0 || isLast || i % 3 === 0;
      if (!show) return;
      var label = fmtMonthShort(r.month, i === 0 || r.month.slice(5) === "01");
      svg += '<text class="axis-label" x="' + x(i).toFixed(1) + '" y="' + (H - 7) + '" text-anchor="middle">' + label + "</text>";
    });

    var pathFor = function (key) {
      return rows.map(function (r, i) { return (i ? "L" : "M") + x(i).toFixed(1) + " " + y(r[key]).toFixed(1); }).join(" ");
    };

    var area = "M" + x(0).toFixed(1) + " " + base.toFixed(1) + " " +
      rows.map(function (r, i) { return "L" + x(i).toFixed(1) + " " + y(r.earned).toFixed(1); }).join(" ") +
      " L" + x(rows.length - 1).toFixed(1) + " " + base.toFixed(1) + " Z";
    svg += '<path class="chart-earned-area" d="' + area + '"></path>';
    svg += '<path class="chart-line line-reversed" d="' + pathFor("reversed") + '"></path>';
    svg += '<path class="chart-line line-expired" d="' + pathFor("expired") + '"></path>';
    svg += '<path class="chart-line line-redeemed" d="' + pathFor("redeemed") + '"></path>';
    svg += '<path class="chart-line line-earned" d="' + pathFor("earned") + '"></path>';

    ["expired", "reversed", "redeemed", "earned"].forEach(function (key) {
      rows.forEach(function (r, i) {
        svg += '<circle class="chart-point ' + key + '" cx="' + x(i).toFixed(1) + '" cy="' + y(r[key]).toFixed(1) + '" r="2.4"><title>' + fmtMonth(r.month) + ": " + fmtInt(r[key]) + " " + key + "</title></circle>";
      });
    });
    svg += "</svg>";

    var totals = rows.reduce(function (acc, r) {
      acc.earned += r.earned; acc.redeemed += r.redeemed; acc.expired += r.expired; acc.reversed += r.reversed;
      return acc;
    }, { earned: 0, redeemed: 0, expired: 0, reversed: 0 });
    var net = totals.earned - totals.redeemed - totals.expired - totals.reversed;

    var foot = '<div class="chart-foot"><p>Earned <strong>' + fmtCompact(totals.earned) + "</strong> points over " + rows.length + " months. November covers the first day of the snapshot only.</p>" +
      '<p class="chart-total">Net movement <strong>' + (net >= 0 ? "+" : "−") + fmtCompact(Math.abs(net)) + "</strong></p></div>";

    return svg + foot;
  }

  function refreshChart() {
    var mount = document.getElementById("chartMount");
    if (!mount) return;
    mount.innerHTML = chartMarkup();
    document.querySelectorAll("[data-range]").forEach(function (b) {
      b.classList.toggle("active", Number(b.getAttribute("data-range")) === state.chartRange);
    });
  }

  // ---------- overview ----------

  function viewOverview() {
    var latest = [];
    ["ACCRUAL", "BONUS", "REDEMPTION", "REVERSAL", "EXPIRATION"].forEach(function (type) {
      var row = D.ledger.find(function (r) { return r.txn_type === type; });
      if (row) latest.push(row);
    });
    D.ledger.forEach(function (r) {
      if (latest.length >= 7) return;
      if (!latest.some(function (x) { return x.points_txn_id === r.points_txn_id; })) latest.push(r);
    });
    latest.sort(function (a, b) { return a.posted_at < b.posted_at ? 1 : a.posted_at > b.posted_at ? -1 : 0; });
    var issues = Object.keys(V.issue_counts).map(function (k) {
      return { key: k, count: V.issue_counts[k], severity: issueSeverity(k) };
    }).sort(function (a, b) { return b.count - a.count; });
    var trace = D.ledger.find(function (r) { return r.txn_type === "ACCRUAL" && r.source_order_id && r.source_order_line_id; }) ||
      D.ledger.find(function (r) { return r.source_order_id; }) || D.ledger[0];
    var rangeTotals = D.monthly.slice(-18).reduce(function (a, r) {
      a.earned += r.earned; a.redeemed += r.redeemed; a.expired += r.expired; a.reversed += r.reversed; return a;
    }, { earned: 0, redeemed: 0, expired: 0, reversed: 0 });

    var html = '<div class="view-animate">';
    html += '<header class="page-head"><div class="page-head-main">';
    html += '<p class="eyebrow"><span class="eyebrow-mark">Morrow &amp; Finch</span> / Loyalty operations</p>';
    html += '<h1 class="display">Every point,<br><em>accounted for.</em></h1>';
    html += '<p class="lede">The programme runs on one immutable points ledger. Balances are derived, returns reverse the original accrual, and expiry is idempotent. This is the operator view of build 2026.1.</p>';
    html += "</div>";
    html += '<aside class="page-head-side"><div class="snapshot-box">';
    html += '<div class="snapshot-status"><span class="status-dot"></span> Build reconciled</div>';
    html += '<p class="snapshot-details">';
    html += "<span>Build <strong>" + esc(M.build_id) + "</strong></span>";
    html += "<span>Snapshot <strong>01 Nov 2026 · 09:00 UTC</strong></span>";
    html += "<span>Generator <strong>" + esc(M.generator_version) + " · stdlib</strong></span>";
    html += "<span>Source <strong>" + fmtInt(totalRows()) + " rows / 14 tables</strong></span>";
    html += "</p>";
    html += '<div class="snapshot-actions"><a class="btn primary" href="' + esc(D.links.bundle) + '" download>' + icon("download") + " Download bundle</a>";
    html += '<span class="snapshot-hash"><span>Ledger SHA</span>' + hashShort(K.points_transactions.sha256, 10) + "</span></div>";
    html += "</div></aside></header>";

    html += '<div class="volume-strip">';
    html += volumeItem("Members on file", fmtInt(S.customers), "accounts", "<strong>" + fmtInt(S.active_accounts) + " active</strong> · four tiers");
    html += volumeItem("Orders in scope", fmtInt(S.orders), "orders", "<strong>" + fmtInt(S.order_lines) + " lines</strong> · " + S.return_rate + "% returned");
    html += volumeItem("Ledger rows", fmtInt(S.points_transactions), "postings", "<strong>Five types</strong> · append-only");
    html += volumeItem("Points outstanding", fmtCompact(S.points_outstanding), "points", "<strong>" + fmtGBP(S.outstanding_value_cents, true) + "</strong> at 100 points / £1");
    html += "</div>";

    html += '<div class="content-grid">';
    html += '<section class="panel chart-panel"><div class="panel-head"><div><p class="kicker">Movement</p><h3>Points posted, month by month</h3><p>Four flows on one scale. The final month stops at the snapshot.</p></div>';
    html += '<div class="panel-head-actions"><div class="chart-toolbar"><div class="chart-legend">';
    html += '<span class="legend-item"><i class="legend-swatch"></i>Earned</span><span class="legend-item"><i class="legend-swatch redeemed"></i>Redeemed</span><span class="legend-item"><i class="legend-swatch expired"></i>Expired</span><span class="legend-item"><i class="legend-swatch reversed"></i>Reversed</span>';
    html += '</div><div class="segmented" id="chartRange"><button type="button" data-range="6">6M</button><button type="button" data-range="12">12M</button><button type="button" class="active" data-range="18">18M</button></div></div></div></div>';
    html += '<div class="chart-wrap" id="chartMount">' + chartMarkup() + "</div></section>";

    html += '<aside class="panel control-panel"><div class="control-head"><p class="kicker"><span class="index">01</span> Liability</p><span class="stamp">At snapshot</span></div>';
    html += '<div class="control-balance"><p class="mini-label">Points outstanding</p>';
    html += '<p class="control-amount"><span class="currency">£</span>' + fmtCompact(S.outstanding_value_cents / 100) + "</p>";
    html += '<div class="control-points"><strong>' + fmtInt(S.points_outstanding) + "</strong> points · 100 points = £1</div></div>";
    html += '<div class="control-list">';
    html += controlRow("Earned", S.points_earned, S.points_earned, false);
    html += controlRow("Redeemed", S.points_redeemed, S.points_earned, false);
    html += controlRow("Expired", S.points_expired, S.points_earned, true);
    html += controlRow("Reversed", S.points_reversed, S.points_earned, false);
    html += "</div>";
    html += '<div class="control-foot"><a class="line-link" href="#ledger">Open the points ledger ' + icon("arrow") + "</a></div></aside>";
    html += "</div>";

    html += '<div class="content-grid lower">';
    html += '<section class="panel"><div class="panel-head with-rule"><div><p class="kicker">Live tail</p><h3>Recent postings</h3><p>Seven rows across the five posting types.</p></div><a class="line-link" href="#ledger">All postings ' + icon("arrow") + "</a></div>";
    html += '<div class="mini-table-wrap"><table class="mini-table"><thead><tr><th>Posting</th><th>Member</th><th>Type</th><th class="points-cell">Points</th><th>Source</th></tr></thead><tbody>';
    latest.forEach(function (r) {
      html += '<tr data-txn-id="' + esc(r.points_txn_id) + '"><td class="id-cell">' + esc(r.points_txn_id) + '<div class="source-cell">' + esc(fmtTime(r.posted_at)) + "</div></td><td>" + esc(r.customer_name) + "</td><td>" + typePill(r.txn_type) + '</td><td class="points-cell ' + (r.points_delta >= 0 ? "positive" : "negative") + '">' + signed(r.points_delta) + '</td><td class="source-cell">' + esc(sourceRef(r)) + "</td></tr>";
    });
    html += "</tbody></table></div></section>";

    html += '<section class="panel exception-panel"><div class="panel-head"><div><p class="kicker">Ground truth</p><h3>Anomalies, by family</h3><p>Injected on purpose, labelled separately.</p></div><div class="exception-total"><strong>' + fmtInt(S.ground_truth_cases) + "</strong><span>cases</span></div></div>";
    html += '<div class="exception-list">';
    issues.forEach(function (i) {
      html += '<div class="exception-row' + (i.severity === "medium" ? " warning" : "") + '" data-issue="' + esc(i.key) + '" role="button" tabindex="0"><span class="exception-marker"></span><span class="exception-name">' + esc(issueLabel(i.key)) + '</span><span class="exception-count">' + i.count + "</span></div>";
    });
    html += '</div><div class="panel-foot"><span>44 high · 46 medium</span><a class="line-link" href="#verification">Open register ' + icon("arrow") + "</a></div></section>";
    html += "</div>";

    html += traceBand(trace);
    html += "</div>";
    return html;
  }

  function volumeItem(label, value, unit, note) {
    return '<div class="volume-item"><div class="volume-label">' + esc(label) + '</div><div class="volume-value">' + value + ' <span class="unit">' + esc(unit) + '</span></div><p class="volume-note">' + note + "</p></div>";
  }

  function controlRow(label, value, total, warning) {
    var pct = Math.min(100, (value / Math.max(1, total)) * 100);
    return '<div class="control-row"><span class="control-row-label">' + esc(label) + '</span><span class="control-row-value">' + fmtCompact(value) + '</span><div class="control-bar' + (warning ? " warning" : "") + '"><span style="width:' + pct.toFixed(2) + '%"></span></div></div>';
  }

  function traceBand(row) {
    if (!row) return "";
    var html = '<section class="trace-band"><div><p class="kicker">Trace</p><h2>One row, four links.</h2><p>A single accrual traces back to the order that caused it and forward to the account that carries it.</p></div><div class="trace-chain">';
    html += traceNode("Source order", row.source_order_id || "—", "Purchase event");
    html += traceNode("Order line", row.source_order_line_id || row.rule_id || "—", row.source_order_line_id ? "Eligible line spend" : "Rule applied");
    html += traceNode("Accrual", row.points_txn_id, signed(row.points_delta) + " points");
    html += traceNode("Account", row.account_id, row.customer_name);
    html += "</div></section>";
    return html;
  }

  function traceNode(label, id, strong) {
    return '<div class="trace-node"><span class="trace-node-label">' + esc(label) + '</span><span class="trace-node-id">' + esc(id) + "</span><strong>" + esc(strong) + "</strong></div>";
  }

  function totalRows() {
    return Object.keys(D.tableCounts).reduce(function (a, k) { return a + Number(D.tableCounts[k] || 0); }, 0);
  }

  // ---------- ledger ----------

  function ledgerFiltered() {
    var q = state.ledger.q.trim().toLowerCase();
    var type = state.ledger.type;
    var rows = D.ledger.filter(function (r) {
      if (type !== "all" && r.txn_type !== type) return false;
      if (!q) return true;
      return [r.points_txn_id, r.account_id, r.customer_name, r.description, r.source_order_id, r.redemption_id, r.expiry_batch_id].join(" ").toLowerCase().indexOf(q) !== -1;
    });
    var sort = state.ledger.sort;
    if (sort === "mix") {
      var groups = {};
      rows.forEach(function (r) {
        if (!groups[r.txn_type]) groups[r.txn_type] = [];
        groups[r.txn_type].push(r);
      });
      var order = ["ACCRUAL", "BONUS", "REDEMPTION", "REVERSAL", "EXPIRATION", "ADJUSTMENT"];
      var mixed = [];
      var index = 0;
      while (mixed.length < rows.length && index < 10000) {
        order.forEach(function (type) {
          if (groups[type] && groups[type][index]) mixed.push(groups[type][index]);
        });
        index += 1;
      }
      return mixed;
    }
    rows.sort(function (a, b) {
      if (sort === "oldest") return a.posted_at < b.posted_at ? -1 : a.posted_at > b.posted_at ? 1 : 0;
      if (sort === "points-desc") return Math.abs(b.points_delta) - Math.abs(a.points_delta);
      if (sort === "points-asc") return Math.abs(a.points_delta) - Math.abs(b.points_delta);
      return a.posted_at > b.posted_at ? -1 : a.posted_at < b.posted_at ? 1 : 0;
    });
    return rows;
  }

  function ledgerResults() {
    var rows = ledgerFiltered();
    var totalPages = Math.max(1, Math.ceil(rows.length / state.ledger.size));
    if (state.ledger.page > totalPages) state.ledger.page = totalPages;
    var start = (state.ledger.page - 1) * state.ledger.size;
    var pageRows = rows.slice(start, start + state.ledger.size);
    var html = '<div class="table-wrap"><table class="data-table"><thead><tr><th>Posting</th><th>Member</th><th>Type</th><th class="num">Points</th><th>Posted</th><th>Source</th></tr></thead><tbody>';
    if (!pageRows.length) {
      html += emptyRow(6, "No postings match that filter.");
    } else {
      pageRows.forEach(function (r) {
        html += '<tr class="clickable" data-txn="' + esc(r.points_txn_id) + '" tabindex="0"><td class="primary-cell">' + esc(r.points_txn_id) + '</td><td><div class="member-name">' + esc(r.customer_name) + '</div><div class="member-mail">' + esc(r.account_id) + "</div></td><td>" + typePill(r.txn_type) + '</td><td class="num"><span class="points-num ' + (r.points_delta >= 0 ? "earned" : "spent") + '">' + signed(r.points_delta) + '</span></td><td><span class="secondary-cell">' + esc(fmtTime(r.posted_at)) + '</span></td><td><span class="secondary-cell">' + esc(sourceRef(r)) + "</span></td></tr>";
      });
    }
    html += "</tbody></table></div>";
    var label = rows.length ? "Showing " + (start + 1) + "–" + Math.min(start + pageRows.length, rows.length) + " of " + fmtInt(rows.length) + " sampled postings" : "0 matching postings";
    html += '<div class="table-footer"><span>' + label + "</span>" + pagination(state.ledger.page, totalPages, "ledger") + "</div>";
    return html;
  }

  function viewLedger() {
    var sampleTypes = {};
    D.ledger.forEach(function (r) { sampleTypes[r.txn_type] = (sampleTypes[r.txn_type] || 0) + 1; });
    var chips = '<button class="chip' + (state.ledger.type === "all" ? " active" : "") + '" type="button" data-type="all">All<span class="chip-count">' + D.ledger.length + "</span></button>";
    Object.keys(TYPE_LABELS).forEach(function (t) {
      if (!sampleTypes[t]) return;
      chips += '<button class="chip' + (state.ledger.type === t ? " active" : "") + '" type="button" data-type="' + t + '">' + TYPE_LABELS[t] + '<span class="chip-count">' + sampleTypes[t] + "</span></button>";
    });

    var html = '<div class="view-animate">';
    html += '<header class="subpage-head"><div><p class="eyebrow"><span class="eyebrow-mark">02</span> Points ledger</p><h1 class="display">Posted once.<br><em>Traceable always.</em></h1>';
    html += '<p class="lede">Five posting types, one running balance, and a source reference on every row that needs one. This browser view samples 499 postings from the full 300,000-row export.</p>';
    html += '<div class="subpage-stats"><span class="subpage-stat"><strong>' + fmtInt(S.points_transactions) + "</strong> ledger rows</span><span class=\"subpage-stat\"><strong>499</strong> in browser</span><span class=\"subpage-stat\"><strong>5</strong> posting types</span><span class=\"subpage-stat\"><strong>" + esc(fmtDate(M.as_of)) + "</strong> snapshot</span></div></div>";
    html += '<div class="subpage-actions"><a class="btn" href="' + esc(D.links.csv) + 'points_transactions.csv" download>' + icon("download") + " <span>Full ledger CSV</span></a><a class=\"btn\" href=\"#reference\">" + icon("book") + " <span>Field guide</span></a></div></header>";

    html += '<div class="filter-bar"><label class="filter-search">' + icon("search") + '<input id="ledgerSearch" type="search" value="' + esc(state.ledger.q) + '" placeholder="Search posting, member or order" autocomplete="off" aria-label="Search postings"><kbd>/</kbd></label>';
    html += '<div class="filter-group" id="ledgerTypes">' + chips + "</div>";
    html += '<div class="select-wrap"><select id="ledgerSort" aria-label="Sort postings"><option value="mix"' + (state.ledger.sort === "mix" ? " selected" : "") + '>Sample mix</option><option value="newest"' + (state.ledger.sort === "newest" ? " selected" : "") + '>Newest first</option><option value="oldest"' + (state.ledger.sort === "oldest" ? " selected" : "") + '>Oldest first</option><option value="points-desc"' + (state.ledger.sort === "points-desc" ? " selected" : "") + '>Largest points</option><option value="points-asc"' + (state.ledger.sort === "points-asc" ? " selected" : "") + ">Smallest points</option></select>" + icon("chevron") + "</div>";
    html += '<div class="filter-tail">' + icon("filter") + '<span class="js-ledger-count">' + ledgerFiltered().length + " of " + D.ledger.length + " sampled</span></div></div>";
    html += '<div class="sheet" id="ledgerSheet">' + ledgerResults() + "</div>";
    html += '<p class="sample-note">' + icon("info") + " The browser table is a deterministic sample. The full 300,000-row ledger ships as CSV, JSONL and SQL.</p>";
    html += "</div>";
    return html;
  }

  function refreshLedger() {
    var sheet = document.getElementById("ledgerSheet");
    if (!sheet) return;
    sheet.innerHTML = ledgerResults();
    var count = document.querySelector(".js-ledger-count");
    if (count) count.textContent = ledgerFiltered().length + " of " + D.ledger.length + " sampled";
    document.querySelectorAll("#ledgerTypes .chip").forEach(function (c) {
      c.classList.toggle("active", c.getAttribute("data-type") === state.ledger.type);
    });
  }

  // ---------- accounts ----------

  function accountsFiltered() {
    var q = state.accounts.q.trim().toLowerCase();
    var tier = state.accounts.tier;
    var status = state.accounts.status;
    var rows = D.accounts.filter(function (a) {
      if (tier !== "all" && a.tier_id !== tier) return false;
      if (status !== "all" && a.status !== status) return false;
      if (!q) return true;
      return [a.account_id, a.customer_id, a.customer_name, a.email, a.city, a.region].join(" ").toLowerCase().indexOf(q) !== -1;
    });
    var sort = state.accounts.sort;
    rows.sort(function (a, b) {
      if (sort === "name") return a.customer_name.localeCompare(b.customer_name);
      if (sort === "spend") return b.qualifying_spend_cents - a.qualifying_spend_cents;
      if (sort === "low") return a.available_points - b.available_points;
      return b.available_points - a.available_points;
    });
    return rows;
  }

  function accountResults() {
    var rows = accountsFiltered();
    var totalPages = Math.max(1, Math.ceil(rows.length / state.accounts.size));
    if (state.accounts.page > totalPages) state.accounts.page = totalPages;
    var start = (state.accounts.page - 1) * state.accounts.size;
    var pageRows = rows.slice(start, start + state.accounts.size);
    var html = '<div class="table-wrap"><table class="data-table"><thead><tr><th>Member</th><th>Account</th><th>Tier</th><th>Region</th><th class="num">Balance</th><th class="num">Lifetime</th><th class="num">Qualifying spend</th><th>Last active</th><th></th></tr></thead><tbody>';
    if (!pageRows.length) {
      html += emptyRow(9, "No members match that filter.");
    } else {
      pageRows.forEach(function (a) {
        html += '<tr class="clickable" data-account="' + esc(a.account_id) + '" tabindex="0"><td><div class="member-name">' + esc(a.customer_name) + '</div><div class="member-mail">' + esc(a.email) + '</div></td><td class="primary-cell">' + esc(a.account_id) + '</td><td>' + tierTag(a.tier_name) + '</td><td>' + esc(a.region) + '</td><td class="num"><span class="points-num">' + fmtInt(a.available_points) + '</span></td><td class="num"><span class="points-num earned">' + fmtInt(a.lifetime_earned_points) + '</span></td><td class="num">' + fmtGBP(a.qualifying_spend_cents) + '</td><td><span class="secondary-cell">' + esc(a.last_activity_at ? fmtDateShort(a.last_activity_at) : "—") + '</span></td><td class="table-actions">' + icon("arrow") + "</td></tr>";
      });
    }
    html += "</tbody></table></div>";
    var label = rows.length ? "Showing " + (start + 1) + "–" + Math.min(start + pageRows.length, rows.length) + " of " + fmtInt(rows.length) + " sampled members" : "0 matching members";
    html += '<div class="table-footer"><span>' + label + "</span>" + pagination(state.accounts.page, totalPages, "account") + "</div>";
    return html;
  }

  function viewAccounts() {
    var chips = '<button class="chip' + (state.accounts.tier === "all" ? " active" : "") + '" type="button" data-tier="all">All<span class="chip-count">' + S.customers + "</span></button>";
    S.tier_mix.forEach(function (t) {
      chips += '<button class="chip' + (state.accounts.tier === t.tier_id ? " active" : "") + '" type="button" data-tier="' + t.tier_id + '">' + esc(t.tier_name) + '<span class="chip-count">' + fmtInt(t.accounts) + "</span></button>";
    });
    var avg = Math.round(S.points_outstanding / Math.max(1, S.customers));

    var html = '<div class="view-animate">';
    html += '<header class="subpage-head"><div><p class="eyebrow"><span class="eyebrow-mark">03</span> Members</p><h1 class="display">The people<br><em>behind the points.</em></h1>';
    html += '<p class="lede">Twenty thousand members across four tiers. Balances are materialised from the ledger at the November snapshot; qualifying spend is trailing 365 days after returns.</p>';
    html += '<div class="subpage-stats"><span class="subpage-stat"><strong>' + fmtInt(S.customers) + "</strong> members</span><span class=\"subpage-stat\"><strong>" + fmtInt(S.active_accounts) + "</strong> active</span><span class=\"subpage-stat\"><strong>4</strong> tiers</span><span class=\"subpage-stat\"><strong>" + fmtCompact(S.points_outstanding) + "</strong> points outstanding</span></div></div>";
    html += '<div class="subpage-actions"><a class="btn" href="' + esc(D.links.csv) + 'loyalty_accounts.csv" download>' + icon("download") + " <span>Members CSV</span></a><a class=\"btn\" href=\"#reference\">" + icon("book") + " <span>Data dictionary</span></a></div></header>";

    html += '<div class="account-hero"><div class="tier-mix"><span class="tier-mix-label">Tier mix</span><div class="tier-bar">';
    S.tier_mix.forEach(function (t, i) { html += '<span class="tier-' + (i + 1) + '" style="width:' + t.share + '%" title="' + esc(t.tier_name) + ": " + t.share + '%"></span>'; });
    html += '</div><div class="tier-legend">';
    S.tier_mix.forEach(function (t) { html += '<span class="tier-legend-item"><i></i>' + esc(t.tier_name) + " " + t.share + "%</span>"; });
    html += '</div></div><div class="account-summary-aside"><div class="account-summary-stat"><span>Average balance</span><strong>' + fmtInt(avg) + '</strong></div><div class="account-summary-stat"><span>Outstanding</span><strong>' + fmtCompact(S.points_outstanding) + '</strong></div><div class="account-summary-stat"><span>Reconciled</span><strong>' + S.ledger_match_rate + "%</strong></div></div></div>";

    html += '<div class="filter-bar"><label class="filter-search">' + icon("search") + '<input id="accountSearch" type="search" value="' + esc(state.accounts.q) + '" placeholder="Search name, email, account or city" autocomplete="off" aria-label="Search members"><kbd>/</kbd></label>';
    html += '<div class="filter-group" id="accountTiers">' + chips + "</div>";
    html += '<div class="select-wrap"><select id="accountStatus" aria-label="Account status"><option value="all">All statuses</option><option value="active"' + (state.accounts.status === "active" ? " selected" : "") + '>Active</option><option value="suspended"' + (state.accounts.status === "suspended" ? " selected" : "") + '>Suspended</option><option value="closed"' + (state.accounts.status === "closed" ? " selected" : "") + ">Closed</option></select>" + icon("chevron") + "</div>";
    html += '<div class="select-wrap"><select id="accountSort" aria-label="Sort members"><option value="name"' + (state.accounts.sort === "name" ? " selected" : "") + '>Name, A–Z</option><option value="balance"' + (state.accounts.sort === "balance" ? " selected" : "") + '>Highest balance</option><option value="low"' + (state.accounts.sort === "low" ? " selected" : "") + '>Lowest balance</option><option value="spend"' + (state.accounts.sort === "spend" ? " selected" : "") + ">Qualifying spend</option></select>" + icon("chevron") + "</div>";
    html += '<div class="filter-tail">' + icon("filter") + '<span class="js-account-count">' + accountsFiltered().length + " of " + D.accounts.length + " sampled</span></div></div>";
    html += '<div class="sheet" id="accountSheet">' + accountResults() + "</div>";
    html += '<p class="sample-note">' + icon("info") + " The table samples 240 members, including the 100 largest balances. The full population is in the CSV export.</p>";
    html += "</div>";
    return html;
  }

  function refreshAccounts() {
    var sheet = document.getElementById("accountSheet");
    if (!sheet) return;
    sheet.innerHTML = accountResults();
    var count = document.querySelector(".js-account-count");
    if (count) count.textContent = accountsFiltered().length + " of " + D.accounts.length + " sampled";
    document.querySelectorAll("#accountTiers .chip").forEach(function (c) {
      c.classList.toggle("active", c.getAttribute("data-tier") === state.accounts.tier);
    });
  }

  // ---------- verification ----------

  function casesFiltered() {
    var q = state.cases.q.trim().toLowerCase();
    var issue = state.cases.issue;
    var severity = state.cases.severity;
    return D.exceptions.filter(function (c) {
      if (issue !== "all" && c.issue_type !== issue) return false;
      if (severity !== "all" && c.severity !== severity) return false;
      if (!q) return true;
      return [c.case_id, c.issue_type, c.entity_id, c.entity_type, c.related_entity_id, c.notes, c.expected_decision].join(" ").toLowerCase().indexOf(q) !== -1;
    });
  }

  function caseResults() {
    var rows = casesFiltered();
    var totalPages = Math.max(1, Math.ceil(rows.length / state.cases.size));
    if (state.cases.page > totalPages) state.cases.page = totalPages;
    var start = (state.cases.page - 1) * state.cases.size;
    var pageRows = rows.slice(start, start + state.cases.size);
    var html = '<div class="table-wrap"><table class="data-table"><thead><tr><th>Case</th><th>Issue</th><th>Entity</th><th>Expected decision</th><th>Severity</th></tr></thead><tbody>';
    if (!pageRows.length) {
      html += emptyRow(5, "No cases match that filter.");
    } else {
      pageRows.forEach(function (c) {
        html += '<tr class="clickable" data-case="' + esc(c.case_id) + '" tabindex="0"><td class="primary-cell">' + esc(c.case_id) + '</td><td><div class="issue-label"><span class="issue-square"></span>' + esc(issueLabel(c.issue_type)) + "</div></td><td><div class=\"primary-cell\">" + esc(c.entity_id) + '</div><div class="secondary-cell">' + esc(c.entity_type) + "</div></td><td>" + esc(c.expected_decision) + '</td><td><span class="severity ' + esc(c.severity) + '">' + esc(c.severity) + "</span></td></tr>";
      });
    }
    html += "</tbody></table></div>";
    var label = rows.length ? "Showing " + (start + 1) + "–" + Math.min(start + pageRows.length, rows.length) + " of " + fmtInt(rows.length) + " labelled cases" : "0 matching cases";
    html += '<div class="table-footer"><span>' + label + "</span>" + pagination(state.cases.page, totalPages, "case") + "</div>";
    return html;
  }

  function caseIssueOptions() {
    var counts = {};
    D.exceptions.forEach(function (c) { counts[c.issue_type] = (counts[c.issue_type] || 0) + 1; });
    return Object.keys(counts).sort().map(function (k) {
      return '<option value="' + esc(k) + '"' + (state.cases.issue === k ? " selected" : "") + ">" + esc(issueLabel(k)) + " (" + counts[k] + ")</option>";
    }).join("");
  }

  function viewVerification() {
    var html = '<div class="view-animate">';
    html += '<header class="subpage-head"><div><p class="eyebrow"><span class="eyebrow-mark">04</span> Verification</p><h1 class="display">Trust is a check,<br><em>not a claim.</em></h1>';
    html += '<p class="lede">Nineteen acceptance checks run against every build. Six anomaly families are injected on purpose, labelled in a separate ground-truth table, and kept out of the feature surface.</p>';
    html += '<div class="subpage-stats"><span class="subpage-stat"><strong>' + V.passed + "/" + V.total_checks + "</strong> checks passed</span><span class=\"subpage-stat\"><strong>" + fmtInt(S.ground_truth_cases) + "</strong> labelled cases</span><span class=\"subpage-stat\"><strong>0</strong> unlabelled anomalies</span><span class=\"subpage-stat\"><strong>" + S.ledger_match_rate + "%</strong> ledger match</span></div></div>";
    html += '<div class="subpage-actions"><a class="btn" href="' + esc(D.links.validation) + '" target="_blank" rel="noopener">' + icon("shield") + " <span>Validation notes</span></a><a class=\"btn\" href=\"" + esc(D.links.json) + "\" target=\"_blank\" rel=\"noopener\">" + icon("download") + " <span>Ground truth</span></a></div></header>";

    html += '<div class="verify-metrics">';
    html += verifyMetric("Acceptance checks", V.passed + '<span class="slash"> / </span>' + V.total_checks, "0 failures · 0 warnings");
    html += verifyMetric("Ground-truth cases", fmtInt(S.ground_truth_cases), "Six anomaly families");
    html += verifyMetric("Unlabelled anomalies", "0", "Every injected case has a label");
    html += verifyMetric("Ledger match", S.ledger_match_rate + "%", fmtInt(S.mismatch_accounts) + " labelled mismatches");
    html += "</div>";

    html += '<div class="verify-layout"><section class="panel"><div class="panel-head with-rule"><div><p class="kicker">Acceptance</p><h3>What every build must prove</h3><p>Keys, references, enums, dates, arithmetic and lifecycle.</p></div><span class="stamp">All pass</span></div>';
    html += '<div class="check-list">';
    V.checks.forEach(function (c) {
      var ok = c.result === "pass";
      html += '<div class="check-row"><span class="check-label" title="' + esc(c.check_id) + '">' + esc(c.label) + '</span><span class="check-status' + (ok ? "" : " warning") + '">' + icon(ok ? "check" : "alert") + (ok ? "Pass" : "Review") + '</span><span class="check-detail" title="' + esc(c.detail) + '">' + esc(c.detail) + "</span></div>";
    });
    html += "</div></section>";

    html += '<aside class="separation-panel"><p class="kicker">Separation</p><h2>Labels stay out of the features.</h2><p>Ground truth is written to its own table and JSON file. It is not a column on any feature table, so it cannot leak into an extract by accident. Evidence is rebuilt from the source rows at build time.</p>';
    html += '<div class="separation-flow"><div class="separation-box"><span>Source rows</span><strong>13 tables</strong></div><div class="flow-arrow">→</div><div class="separation-box"><span>Detection</span><strong>6 rules</strong></div><div class="flow-arrow">→</div><div class="separation-box"><span>Ground truth</span><strong>90 cases</strong></div></div>';
    html += '<div class="separation-families">';
    Object.keys(V.issue_counts).sort(function (a, b) { return V.issue_counts[b] - V.issue_counts[a]; }).forEach(function (k) {
      html += '<div class="separation-family"><span>' + esc(issueLabel(k)) + '</span><strong>' + V.issue_counts[k] + "</strong></div>";
    });
    html += "</div>";
    html += '<a class="line-link" href="' + esc(D.links.json) + '" target="_blank" rel="noopener">Open ground_truth.json ' + icon("arrow-up") + "</a></aside></div>";

    html += '<section class="panel issue-register"><div class="panel-head with-rule"><div><p class="kicker">Ground truth</p><h3>Exception register</h3><p>Each case carries its detection rule, evidence and expected decision. Labels are never joined into model features.</p></div><div class="panel-head-actions"><span class="stamp">' + S.ground_truth_cases + " cases</span></div></div>";
    html += '<div class="case-toolbar"><label class="filter-search">' + icon("search") + '<input id="caseSearch" type="search" value="' + esc(state.cases.q) + '" placeholder="Search case, entity or note" autocomplete="off" aria-label="Search exception cases"><kbd>/</kbd></label>';
    html += '<div class="filter-group"><div class="select-wrap"><select id="caseIssue" aria-label="Issue type"><option value="all">All issue types</option>' + caseIssueOptions() + '</select>' + icon("chevron") + '</div><div class="select-wrap"><select id="caseSeverity" aria-label="Severity"><option value="all">All severities</option><option value="high"' + (state.cases.severity === "high" ? " selected" : "") + '>High</option><option value="medium"' + (state.cases.severity === "medium" ? " selected" : "") + ">Medium</option></select>" + icon("chevron") + '</div></div><span class="case-toolbar-note js-case-count">' + casesFiltered().length + " of " + D.exceptions.length + "</span></div>";
    html += '<div class="sheet" id="caseSheet">' + caseResults() + "</div></section>";

    html += reproPanel();
    html += checksumPanel();
    html += "</div>";
    return html;
  }

  function verifyMetric(label, value, note) {
    return '<div class="verify-metric"><div class="verify-metric-label">' + esc(label) + '</div><div class="verify-metric-value">' + value + '</div><div class="verify-metric-note">' + esc(note) + "</div></div>";
  }

  function reproPanel() {
    var R = D.reproducibility;
    var html = '<section class="panel repro-panel"><div class="panel-head with-rule"><div><p class="kicker">Reproducibility</p><h3>Two runs, one checksum</h3><p>The same seed and parameters are built twice, then compared table by table.</p></div><div class="panel-head-actions"><span class="stamp">' + (R ? (R.identical ? "Identical" : "Review") : "Single run") + "</span></div></div>";
    if (!R) {
      html += '<div class="panel-body" style="padding-top:15px"><p class="lede" style="font-size:11px">This payload was exported without <code class="mono">--verify-repro</code>, so only one run is recorded. The table checksums below still fingerprint the build. Re-run with the flag to produce a second build and a comparison file.</p>';
      html += '<p class="sample-note">' + icon("info") + " Seed " + M.seed + " · canonical SHA-256 over table rows.</p></div></section>";
      return html;
    }
    var a = R.run_a.checksums.points_transactions;
    var b = R.run_b.checksums.points_transactions;
    html += '<div class="repro-grid">';
    html += '<div class="repro-col"><div class="repro-col-head"><span>Run A · seed ' + R.seed + '</span><span class="stamp">Reference</span></div><div class="repro-hash">' + icon("check") + "<span>" + esc(a.sha256) + "</span></div><p class=\"sample-note\">" + fmtInt(a.rows) + " points rows · canonical SHA-256</p></div>";
    html += '<div class="repro-col"><div class="repro-col-head"><span>Run B · seed ' + R.seed + '</span><span class="stamp">' + (R.identical ? "Identical" : "Differs") + '</span></div><div class="repro-hash">' + icon(R.identical ? "check" : "alert") + "<span>" + esc(b.sha256) + "</span></div><p class=\"sample-note\">" + fmtInt(b.rows) + " points rows · canonical SHA-256</p></div></div>";
    html += '<div class="repro-foot"><span>' + R.tables_identical + " of " + R.tables_compared + " tables byte-identical · counts " + (R.counts_identical ? "match" : "differ") + '</span><strong>seed ' + R.seed + "</strong></div></section>";
    return html;
  }

  function checksumPanel() {
    var html = '<section class="panel repro-panel"><div class="panel-head with-rule"><div><p class="kicker">Manifest</p><h3>Table checksums</h3><p>SHA-256 over canonical row serialisation. The same rows and seed produce the same digest.</p></div><div class="panel-head-actions"><a class="line-link" href="data/manifest.json" target="_blank" rel="noopener">manifest.json ' + icon("arrow-up") + "</a></div></div>";
    html += '<div class="table-wrap"><table class="data-table manifest-table"><thead><tr><th>Table</th><th class="num">Rows</th><th>SHA-256</th><th>Status</th></tr></thead><tbody>';
    Object.keys(K).forEach(function (table) {
      var row = K[table];
      var identity = D.reproducibility && D.reproducibility.identities ? D.reproducibility.identities[table] : null;
      html += '<tr><td class="primary-cell">' + esc(table) + '</td><td class="num">' + fmtInt(row.rows) + '</td><td><span class="secondary-cell" title="' + esc(row.sha256) + '">' + hashShort(row.sha256, 24) + '</span></td><td>' + (identity === true ? '<span class="stamp">match</span>' : identity === false ? '<span class="severity high">differs</span>' : '<span class="severity">sealed</span>') + "</td></tr>";
    });
    html += "</tbody></table></div></section>";
    return html;
  }

  function refreshCases() {
    var sheet = document.getElementById("caseSheet");
    if (!sheet) return;
    sheet.innerHTML = caseResults();
    var count = document.querySelector(".js-case-count");
    if (count) count.textContent = casesFiltered().length + " of " + D.exceptions.length;
  }

  function bindVerification() {
    var search = document.getElementById("caseSearch");
    if (search) {
      search.addEventListener("input", function () {
        state.cases.q = search.value;
        state.cases.page = 1;
        refreshCases();
      });
    }
    var issue = document.getElementById("caseIssue");
    if (issue) issue.addEventListener("change", function () { state.cases.issue = issue.value; state.cases.page = 1; refreshCases(); });
    var severity = document.getElementById("caseSeverity");
    if (severity) severity.addEventListener("change", function () { state.cases.severity = severity.value; state.cases.page = 1; refreshCases(); });
    var sheet = document.getElementById("caseSheet");
    if (sheet) {
      sheet.addEventListener("click", function (e) {
        var page = e.target.closest("[data-case-page]");
        if (page && !page.disabled) {
          state.cases.page = Number(page.getAttribute("data-case-page"));
          refreshCases();
          return;
        }
        var tr = e.target.closest("tr[data-case]");
        if (tr) openCaseDrawer(tr.getAttribute("data-case"));
      });
      sheet.addEventListener("keydown", function (e) {
        if (e.key !== "Enter" && e.key !== " ") return;
        var tr = e.target.closest("tr[data-case]");
        if (tr) { e.preventDefault(); openCaseDrawer(tr.getAttribute("data-case")); }
      });
    }
  }

  // ---------- data studio ----------

  var EDGE_COPY = {
    returns_and_partial_returns: ["Returns and partial returns", "Full and pro-rata reversals linked to the original accrual."],
    concurrent_redemptions: ["Concurrent redemptions", "Two attempts, one lock; the first approval wins."],
    missing_return_reversals: ["Missing return reversals", "A returned order keeps its points; labelled for correction."],
    duplicate_expiry_batches: ["Duplicate expiry batches", "Idempotency key collision; the second batch is voided."],
    balance_materialisation_drift: ["Balance drift", "Stored balance differs from the ledger sum by a small delta."],
    tier_basis_drift: ["Tier basis drift", "Tier read from gross spend instead of qualifying spend."]
  };

  var ISSUE_FOR_SWITCH = {
    returns_and_partial_returns: "returned_order_keeps_all_points",
    concurrent_redemptions: "concurrent_redemption_attempt",
    missing_return_reversals: "returned_order_keeps_all_points",
    duplicate_expiry_batches: "points_expire_twice",
    balance_materialisation_drift: "balance_differs_from_ledger",
    tier_basis_drift: "tier_uses_gross_spend"
  };

  function studioScale() {
    return state.studio.scale === "starter"
      ? { customers: 200, orders: 1000, transactions: 3000, out: "data/starter", label: "Starter" }
      : { customers: 20000, orders: 100000, transactions: 300000, out: "data", label: "Full" };
  }

  function studioCommand() {
    var sc = studioScale();
    return "python generator/generate.py --seed " + (state.studio.seed || M.seed) +
      " --customers " + sc.customers + " --orders " + sc.orders + " --transactions " + sc.transactions +
      " --out " + sc.out;
  }

  function viewStudio() {
    var sc = studioScale();
    var html = '<div class="view-animate">';
    html += '<header class="subpage-head"><div><p class="eyebrow"><span class="eyebrow-mark">05</span> Data studio</p><h1 class="display">One seed.<br><em>The same build.</em></h1>';
    html += '<p class="lede">The generator is stdlib-only Python, seeded once and parameterised by scale. The starter sample and the full build come from the same code path; only the row counts change.</p>';
    html += '<div class="subpage-stats"><span class="subpage-stat"><strong>' + esc(M.generator_version) + "</strong> generator</span><span class=\"subpage-stat\"><strong>0</strong> third-party packages</span><span class=\"subpage-stat\"><strong>" + M.seed + "</strong> seed</span><span class=\"subpage-stat\"><strong>" + fmtInt(totalRows()) + "</strong> rows across 14 tables</span></div></div>";
    html += '<div class="subpage-actions"><a class="btn" href="' + esc(D.links.bundle) + '" download>' + icon("download") + " <span>Run bundle</span></a><a class=\"btn\" href=\"" + esc(D.links.readme) + "\" target=\"_blank\" rel=\"noopener\">" + icon("book") + " <span>README</span></a></div></header>";

    html += '<div class="studio-status"><span class="stamp">Build sealed</span><span class="studio-status-item">Generator <strong>' + esc(M.generator_version) + '</strong></span><span class="studio-status-item">Seed <strong>' + M.seed + '</strong></span><span class="studio-status-item">Snapshot <strong>' + esc(fmtDate(M.as_of)) + '</strong></span><span class="studio-status-item">Checks <strong>' + V.passed + "/" + V.total_checks + '</strong></span><span class="studio-status-item">Rows <strong>' + fmtInt(totalRows()) + "</strong></span></div>";

    html += '<div class="studio-grid">';
    html += '<section class="panel config-panel"><div class="panel-head"><div><p class="kicker">01 / Parameters</p><h3>Run configuration</h3><p>Edit the parameters; the command updates.</p></div><button class="btn small" type="button" id="studioReset">Reset</button></div>';

    html += '<div class="config-section"><div class="config-label-row"><span class="config-label">Scale</span><span class="config-hint" id="scaleHint">' + fmtInt(sc.customers) + " customers · " + fmtInt(sc.orders) + " orders · " + fmtInt(sc.transactions) + ' postings</span></div>';
    html += '<div class="scale-toggle" id="scaleToggle"><button class="scale-option' + (state.studio.scale === "full" ? " active" : "") + '" type="button" data-scale="full"><strong>Full build</strong><span>20,000 · 100,000 · 300,000</span></button><button class="scale-option' + (state.studio.scale === "starter" ? " active" : "") + '" type="button" data-scale="starter"><strong>Starter</strong><span>200 · 1,000 · 3,000</span></button></div></div>';

    html += '<div class="config-section"><div class="config-label-row"><span class="config-label">Seed</span><span class="config-hint">Integer · fixed across runs</span></div><div class="seed-row"><input class="seed-input" id="seedInput" type="text" inputmode="numeric" value="' + esc(state.studio.seed) + '" aria-label="Random seed"><button class="btn small" type="button" id="seedReset">Use ' + M.seed + "</button></div></div>";

    html += '<div class="config-section"><div class="config-label-row"><span class="config-label">Anomaly coverage</span><span class="config-hint">Fixed in the generator</span></div><div class="toggle-list">';
    Object.keys(M.edge_case_switches).forEach(function (key) {
      if (!M.edge_case_switches[key]) return;
      var copy = EDGE_COPY[key] || [titleCase(key), "Included in this build."];
      var issue = ISSUE_FOR_SWITCH[key];
      var count = issue ? V.issue_counts[issue] : null;
      html += '<div class="toggle-row"><div class="toggle-copy"><strong>' + esc(copy[0]) + (count ? " · " + count + " cases" : "") + '</strong><span>' + esc(copy[1]) + '</span></div><label class="toggle" title="Injection is fixed at build time"><input type="checkbox" checked disabled aria-label="' + esc(copy[0]) + '"><span class="toggle-track"></span></label></div>';
    });
    html += "</div></div>";

    html += '<div class="config-section"><div class="config-label-row"><span class="config-label">Command</span><span class="config-hint">Run from the project root</span></div>';
    html += '<pre class="code-block"><button class="copy-btn" type="button" id="copyCommand" aria-label="Copy command">' + icon("copy") + '</button><code id="genCommand">' + esc(studioCommand()) + "</code></pre>";
    html += '<div class="config-actions" style="margin-top:9px"><button class="btn small primary" type="button" id="copyCommandBtn">' + icon("copy") + ' Copy command</button><span class="hint">Python 3.11+ · no install step · deterministic RNG</span></div></div>';
    html += "</section>";

    html += '<section class="panel run-panel"><div class="panel-head with-rule"><div><p class="kicker">02 / Run</p><h3>Run record</h3><p>What the build did, in order.</p></div><span class="stamp">Validated</span></div>';
    html += '<div class="pipeline">';
    html += pipelineRow("01", "Seed and profiles", "Customers, accounts, regions and communication consent.", true);
    html += pipelineRow("02", "Simulate commerce", "Orders, lines, channels, returns and partial returns.", true);
    html += pipelineRow("03", "Post the ledger", "Accruals, bonuses, redemptions, reversals and expiry lots.", true);
    html += pipelineRow("04", "Materialise balances", "Ledger sums drive available points; drift is labelled.", true);
    html += pipelineRow("05", "Inject edge cases", "Six anomaly families with evidence and expected decisions.", true);
    html += pipelineRow("06", "Validate", "Keys, references, enums, dates, arithmetic and lifecycle.", true);
    html += pipelineRow("07", "Export", "CSV, JSONL, SQL, site payload and documentation.", true);
    html += "</div>";
    html += '<div class="run-details">';
    html += runDetail("Build", M.build_id);
    html += runDetail("Seed", M.seed);
    html += runDetail("Snapshot", "01 Nov 2026 · 09:00 UTC");
    html += runDetail("Generator", M.generator_version);
    html += runDetail("Tables", "14");
    html += runDetail("Rows", fmtInt(totalRows()));
    html += runDetail("Checks", V.passed + " pass / " + V.failed + " fail");
    html += runDetail("Ledger SHA", hashShort(K.points_transactions.sha256, 14));
    html += "</div>";
    html += '<div class="artifact-actions"><a class="artifact-link" href="' + esc(D.links.bundle) + '" download>' + icon("download") + ' run bundle</a><a class="artifact-link" href="' + esc(D.links.csv) + '" target="_blank" rel="noopener">' + icon("database") + ' CSV</a><a class="artifact-link" href="' + esc(D.links.jsonl) + '" target="_blank" rel="noopener">' + icon("database") + ' JSONL</a><a class="artifact-link" href="' + esc(D.links.schema) + '" target="_blank" rel="noopener">' + icon("terminal") + ' schema.sql</a><a class="artifact-link" href="' + esc(D.links.seed) + '" target="_blank" rel="noopener">' + icon("terminal") + ' seed.sql</a></div></section>';
    html += "</div>";

    html += '<section class="panel inventory-panel"><div class="panel-head with-rule"><div><p class="kicker">Inventory</p><h3>Tables and artefacts</h3><p>Row counts from the build; checksums are canonical SHA-256.</p></div><div class="panel-head-actions"><span class="stamp">14 tables</span></div></div>';
    html += '<div class="table-wrap"><table class="data-table inventory-table"><thead><tr><th>Table</th><th class="num">Rows</th><th>Formats</th><th>SHA-256</th></tr></thead><tbody>';
    Object.keys(D.tableCounts).forEach(function (table) {
      var checksum = K[table];
      html += '<tr><td class="primary-cell">' + esc(table) + '</td><td class="num">' + fmtInt(D.tableCounts[table]) + '</td><td><div class="format-links"><a class="format-link" href="' + esc(D.links.csv) + esc(table) + '.csv" download>CSV</a><a class="format-link" href="' + esc(D.links.jsonl) + esc(table) + '.jsonl" target="_blank" rel="noopener">JSONL</a>' + (table === "ground_truth" ? '<a class="format-link" href="' + esc(D.links.json) + '" target="_blank" rel="noopener">JSON</a>' : "") + '</div></td><td><span class="secondary-cell" title="' + esc(checksum ? checksum.sha256 : "") + '">' + hashShort(checksum ? checksum.sha256 : "", 22) + "</span></td></tr>";
    });
    html += "</tbody></table></div></section>";

    html += '<div class="provenance-strip"><p><strong>Provenance.</strong> No external or personal data. Every row is generated locally from the fixed seed and the rules in the repository; the fonts and payload are served from this folder.</p><a class="line-link" href="docs/SOURCE_MANIFEST.json" target="_blank" rel="noopener">Source manifest ' + icon("arrow-up") + "</a></div>";
    html += "</div>";
    return html;
  }

  function pipelineRow(num, title, copy, done) {
    return '<div class="pipeline-row"><span class="pipeline-step">' + esc(num) + '</span><div class="pipeline-copy"><strong>' + esc(title) + '</strong><span>' + esc(copy) + '</span></div><span class="pipeline-state">' + icon(done ? "check" : "clock") + (done ? "Done" : "Queued") + "</span></div>";
  }

  function runDetail(label, value) {
    return '<div class="run-detail"><span>' + esc(label) + '</span><strong>' + esc(value) + "</strong></div>";
  }

  function updateStudioCommand() {
    var cmd = document.getElementById("genCommand");
    if (cmd) cmd.textContent = studioCommand();
    var hint = document.getElementById("scaleHint");
    if (hint) {
      var sc = studioScale();
      hint.textContent = fmtInt(sc.customers) + " customers · " + fmtInt(sc.orders) + " orders · " + fmtInt(sc.transactions) + " postings";
    }
    document.querySelectorAll("[data-scale]").forEach(function (b) {
      b.classList.toggle("active", b.getAttribute("data-scale") === state.studio.scale);
    });
  }

  function bindStudio() {
    document.querySelectorAll("[data-scale]").forEach(function (b) {
      b.addEventListener("click", function () {
        state.studio.scale = b.getAttribute("data-scale");
        updateStudioCommand();
      });
    });
    var seed = document.getElementById("seedInput");
    if (seed) {
      seed.addEventListener("input", function () {
        var clean = seed.value.replace(/[^0-9]/g, "").slice(0, 12);
        if (clean !== seed.value) seed.value = clean;
        state.studio.seed = clean || String(M.seed);
        updateStudioCommand();
      });
    }
    var seedReset = document.getElementById("seedReset");
    if (seedReset) {
      seedReset.addEventListener("click", function () {
        state.studio.seed = String(M.seed);
        if (seed) seed.value = state.studio.seed;
        updateStudioCommand();
      });
    }
    var reset = document.getElementById("studioReset");
    if (reset) {
      reset.addEventListener("click", function () {
        state.studio.scale = "full";
        state.studio.seed = String(M.seed);
        if (seed) seed.value = state.studio.seed;
        updateStudioCommand();
        showToast("Run configuration reset");
      });
    }
    [document.getElementById("copyCommand"), document.getElementById("copyCommandBtn")].forEach(function (b) {
      if (b) b.addEventListener("click", function () { copyText(studioCommand(), "Command"); });
    });
  }

  // ---------- reference ----------

  var REF_TABS = [
    { id: "entities", label: "Entities" },
    { id: "dictionary", label: "Field dictionary" },
    { id: "rules", label: "Rules & rewards" },
    { id: "ids", label: "ID grammar" },
    { id: "lifecycle", label: "Lifecycle" },
    { id: "method", label: "Method" }
  ];

  function viewReference() {
    var html = '<div class="view-animate">';
    html += '<header class="subpage-head"><div><p class="eyebrow"><span class="eyebrow-mark">06</span> Field guide</p><h1 class="display">The grammar<br><em>of the ledger.</em></h1>';
    html += '<p class="lede">Eleven entities, fourteen tables, ten ID grammars. The record is append-only where it matters, and every derived value points back to the rows that produced it.</p>';
    html += '<div class="subpage-stats"><span class="subpage-stat"><strong>11</strong> entities</span><span class=\"subpage-stat\"><strong>14</strong> tables</span><span class=\"subpage-stat\"><strong>19</strong> checks</span><span class=\"subpage-stat\"><strong>v2.1</strong> schema</span></div></div>';
    html += '<div class="subpage-actions"><a class="btn" href="' + esc(D.links.dictionary) + '" target="_blank" rel="noopener">' + icon("download") + " <span>Data dictionary</span></a><a class=\"btn\" href=\"" + esc(D.links.schema) + "\" target=\"_blank\" rel=\"noopener\"><span>DDL</span></a></div></header>";

    html += '<div class="reference-tabs" role="tablist">';
    REF_TABS.forEach(function (t) {
      html += '<button class="ref-tab' + (state.refTab === t.id ? " active" : "") + '" type="button" role="tab" aria-selected="' + (state.refTab === t.id) + '" data-ref-tab="' + t.id + '">' + esc(t.label) + "</button>";
    });
    html += '</div><div class="ref-pane">';

    if (state.refTab === "entities") html += referenceEntities();
    if (state.refTab === "dictionary") html += referenceDictionary();
    if (state.refTab === "rules") html += referenceRules();
    if (state.refTab === "ids") html += referenceIds();
    if (state.refTab === "lifecycle") html += referenceLifecycle();
    if (state.refTab === "method") html += referenceMethod();

    html += "</div></div>";
    return html;
  }

  function referenceEntities() {
    var html = '<div class="entity-atlas">';
    D.dataDictionary.forEach(function (e) {
      html += '<button class="entity-card' + (state.refEntity === e.entity ? " active" : "") + '" type="button" data-entity="' + esc(e.entity) + '"><span class="entity-domain">' + esc(ENTITY_DOMAINS[e.entity] || "Record") + '</span><strong>' + esc(e.entity) + '</strong><span class="entity-table">' + esc(e.table) + '</span><span class="entity-arrow">' + icon("arrow") + "</span></button>";
    });
    html += "</div>";
    html += '<section class="panel relationships"><div class="panel-head with-rule"><div><p class="kicker">Foreign keys</p><h3>How the record connects</h3><p>Parent and child tables, cardinality and the rule that holds them together.</p></div><span class="stamp">' + RELATIONSHIPS.length + " relations</span></div>";
    html += '<div class="table-wrap"><table class="data-table"><thead><tr><th>Parent</th><th>Child</th><th>Cardinality</th><th>Rule</th></tr></thead><tbody>';
    RELATIONSHIPS.forEach(function (r) {
      html += "<tr><td>" + esc(r.parent) + "</td><td>" + esc(r.child) + '</td><td><span class="cardinality">' + esc(r.card) + "</span></td><td>" + esc(r.note) + "</td></tr>";
    });
    html += "</tbody></table></div></section>";
    return html;
  }

  function referenceDictionary() {
    var selected = D.dataDictionary.find(function (e) { return e.entity === state.refEntity; }) || D.dataDictionary[0];
    var html = '<div class="dictionary-layout"><div class="entity-index">';
    D.dataDictionary.forEach(function (e) {
      html += '<button class="' + (e.entity === selected.entity ? "active" : "") + '" type="button" data-entity="' + esc(e.entity) + '">' + esc(e.entity) + "<span>" + e.fields.length + "</span></button>";
    });
    html += '</div><div class="dictionary-main"><div class="dictionary-head"><p class="kicker">' + esc(selected.table) + '</p><h3>' + esc(selected.entity) + '</h3><p>' + esc(selected.description) + " Primary key <code>" + esc(selected.primary_key) + "</code>.</p></div>";
    html += '<div class="dictionary-table-wrap"><table class="dictionary-table"><thead><tr><th>Field</th><th>Type</th><th>Required</th><th>Example</th><th>Key</th><th>Rule</th></tr></thead><tbody>';
    selected.fields.forEach(function (f) {
      html += "<tr><td>" + esc(f[0]) + "</td><td>" + esc(f[1]) + "</td><td>" + esc(f[2]) + "</td><td><code>" + esc(f[3]) + "</code></td><td>" + esc(f[4]) + "</td><td>" + esc(f[5]) + "</td></tr>";
    });
    html += "</tbody></table></div></div></div>";
    return html;
  }

  function referenceRules() {
    var html = '<div class="rules-grid"><section class="panel"><div class="panel-head with-rule"><div><p class="kicker">Earn schedule</p><h3>The 2026 tier ladder</h3><p>Qualifying spend is trailing 365 days, net of returns.</p></div></div>';
    html += '<div class="table-wrap"><table class="data-table tier-rate-table"><thead><tr><th>Tier</th><th class="num">Qualifying spend</th><th class="num">Members</th><th class="num">Share</th><th>Earn</th></tr></thead><tbody>';
    D.tiers.forEach(function (t) {
      var mix = S.tier_mix.find(function (m) { return m.tier_id === t.tier_id; });
      html += '<tr><td>' + tierTag(t.tier_name) + '</td><td class="num">' + fmtGBP(t.qualify_spend_cents) + '</td><td class="num">' + fmtInt(t.accounts) + '</td><td class="num">' + (mix ? mix.share + "%" : "—") + '</td><td><span class="multiplier">' + (TIER_MULTIPLIERS[t.rank] || "—") + "×</span></td></tr>";
    });
    html += "</tbody></table></div></section>";

    html += '<div class="method-aside"><div class="policy-card"><div class="policy-card-head"><p class="kicker">RULE-TIER-V1</p><h3>Tier review</h3></div><div class="policy-list">';
    html += policyRow("Basis", "net eligible spend", "after returns; tax and delivery excluded");
    html += policyRow("Lookback", "365 days", "rolling window");
    html += policyRow("Upgrades", "immediate", "on qualifying activity");
    html += policyRow("Downgrades", "at review", "annual and on activity");
    html += "</div></div>";
    html += '<div class="policy-card"><div class="policy-card-head"><p class="kicker">RULE-REDEEM-V2</p><h3>Redemption controls</h3></div><div class="policy-list">';
    html += policyRow("Minimum", "300 points", "per reward");
    html += policyRow("Rate", "100 points / £1", "cash-equivalent value");
    html += policyRow("Basket cap", "50%", "maximum share of basket");
    html += policyRow("Concurrency", "one open attempt", "serialised per account");
    html += "</div></div></div></div>";

    html += '<section class="panel catalog-panel"><div class="panel-head with-rule"><div><p class="kicker">Rule register</p><h3>Versioned rules</h3><p>Effective dates are explicit; superseded versions stay on file.</p></div><span class="stamp">6 rules</span></div>';
    html += '<div class="table-wrap"><table class="data-table"><thead><tr><th>Rule</th><th>Code</th><th>Version</th><th>Effective</th><th>Parameters</th><th>Status</th></tr></thead><tbody>';
    D.rules.forEach(function (r) {
      html += '<tr><td><div class="member-name">' + esc(r.name) + '</div><div class="member-mail">' + esc(r.rule_id) + '</div></td><td class="primary-cell">' + esc(r.rule_code) + '</td><td class="num">v' + r.version + '</td><td><span class="secondary-cell">' + esc(fmtDate(r.effective_from)) + (r.effective_to ? " → " + esc(fmtDate(r.effective_to)) : " → open") + '</span></td><td><span class="secondary-cell" title="' + esc(r.parameters) + '">' + esc(fmtParams(r.parameters)) + '</span></td><td>' + statusTag(r.status) + "</td></tr>";
    });
    html += "</tbody></table></div></section>";

    html += '<section class="panel catalog-panel"><div class="panel-head with-rule"><div><p class="kicker">Catalogue</p><h3>Rewards</h3><p>Points cost, cash value and the minimum tier that can redeem.</p></div><span class="stamp">8 rewards</span></div>';
    html += '<div class="table-wrap"><table class="data-table"><thead><tr><th>Reward</th><th>Category</th><th class="num">Points</th><th class="num">Cash value</th><th>Eligible from</th><th>Status</th></tr></thead><tbody>';
    D.rewards.forEach(function (r) {
      var tier = D.tiers.find(function (t) { return t.rank === r.min_tier_rank; });
      html += '<tr><td><div class="member-name">' + esc(r.reward_name) + '</div><div class="member-mail">' + esc(r.reward_id) + '</div></td><td>' + esc(titleCase(r.category)) + '</td><td class="num points-num">' + fmtInt(r.points_cost) + '</td><td class="num">' + fmtGBP(r.cash_value_cents) + '</td><td>' + tierTag(tier ? tier.tier_name : "—") + '</td><td>' + statusTag(r.status) + "</td></tr>";
    });
    html += "</tbody></table></div></section>";
    return html;
  }

  function policyRow(label, value, sub) {
    return '<div class="policy-row"><span class="policy-row-label">' + esc(label) + '</span><span class="policy-row-value">' + esc(value) + '</span><span class="policy-row-sub">' + esc(sub) + "</span></div>";
  }

  function referenceIds() {
    var html = '<div class="id-table-wrap"><div class="table-wrap"><table class="data-table id-table"><thead><tr><th>Entity</th><th>Pattern</th><th>Rule</th></tr></thead><tbody>';
    D.idRules.forEach(function (r) {
      html += "<tr><td>" + esc(r.entity) + '</td><td><span class="id-pattern">' + esc(r.pattern) + "</span></td><td>" + esc(r.rule) + "</td></tr>";
    });
    html += "</tbody></table></div></div>";
    html += '<div class="two-col-note"><div class="note-strip">' + icon("info") + "<div><strong>Immutable by construction</strong><p>Sequences are allocated once per build. A reversal or correction creates a new posting; it never edits the original row.</p></div></div>";
    html += '<div class="note-strip">' + icon("clock") + "<div><strong>Snapshot year, not event year</strong><p>Points, redemption, expiry and tier-history IDs use the snapshot year. Orders and lines use the order year.</p></div></div></div>";
    return html;
  }

  function referenceLifecycle() {
    var rows = [
      ["Order", "placed → completed"],
      ["Order return", "completed → partially_returned → returned"],
      ["Account", "active → suspended → closed"],
      ["Tier", "reviewed → effective"],
      ["Accrual", "posted → available → consumed or expired"],
      ["Reversal", "posted against original accrual"],
      ["Redemption", "attempted → approved or rejected"],
      ["Expiry batch", "scheduled → posted → voided"],
      ["Return", "returned_at ≥ order_ts"],
      ["Snapshot", "2026-11-01T09:00:00Z"]
    ];
    var html = '<div class="lifecycle-grid">';
    rows.forEach(function (r) { html += '<div class="lifecycle-row"><span>' + esc(r[0]) + "</span><code>" + esc(r[1]) + "</code></div>"; });
    html += "</div>";
    html += '<div class="note-strip" style="margin-top:17px">' + icon("shield") + "<div><strong>History is append-only</strong><p>Account balances are materialised; ledger rows are not edited. Tier changes, expiry batches and redemption attempts keep their own state. A correction is a new row with a link to the original.</p></div></div>";
    return html;
  }

  function referenceMethod() {
    var steps = [
      ["Seed the population", "A fixed Mersenne Twister seed drives names, regions, channels, consent and join dates. Nothing is sampled from outside the repository."],
      ["Simulate commerce", "Orders are generated with lines, tax, delivery and discounts. Returns and partial returns are decided per line, then reconciled to the order header."],
      ["Post the ledger", "Each eligible line creates an accrual at the tier rate. Bonuses, redemptions, reversals and expiry batches post as separate types with source references."],
      ["Materialise balances", "Available points are the sum of posted ledger deltas. Lifetime earned is the sum of positive accrual, bonus and adjustment rows. A controlled drift is applied to twelve accounts and labelled."],
      ["Inject labelled edge cases", "Six anomaly families are added after the clean build: balance drift, over-redemption, missing return reversals, duplicate expiry, gross-spend tiers and concurrent attempts. Each case gets a detection rule and an expected decision."],
      ["Validate and export", "Nineteen checks run over keys, foreign keys, enums, date ordering, arithmetic, lifecycle, duplicates and the volume target. Exports are written only after validation passes."]
    ];
    var html = '<div class="method-grid"><div class="method-steps">';
    steps.forEach(function (s, i) {
      html += '<div class="method-step"><span class="method-num">' + String(i + 1).padStart(2, "0") + '</span><div class="method-copy"><strong>' + esc(s[0]) + "</strong><p>" + esc(s[1]) + "</p></div></div>";
    });
    html += '</div><aside class="method-aside">';
    html += '<div class="note-card dark"><p class="kicker">Separation</p><h3>Ground truth is not a feature.</h3><p>Labels live in <code>ground_truth</code>, a separate table and file. No feature table carries an issue flag, expected decision or severity column.</p><ul class="note-list"><li>Evidence is rebuilt from source rows.</li><li>Expected decisions are text, not model targets.</li><li>History is never overwritten to hide a case.</li></ul></div>';
    html += '<div class="note-card"><p class="kicker">Determinism</p><h3>Same seed, same digest.</h3><ul class="note-list"><li>Stdlib-only Python; no network calls.</li><li>Canonical SHA-256 over every table.</li><li>Second build compared under --verify-repro.</li><li>Counts and IDs are stable across exports.</li></ul></div>';
    html += '<div class="note-card"><p class="kicker">Provenance</p><h3>No external data.</h3><p>The brand, catalogue, customers, orders and rewards are fictional. Fonts and the data payload are served from this folder, so the site works offline.</p><a class="line-link" href="docs/SOURCE_MANIFEST.json" target="_blank" rel="noopener">Source manifest ' + icon("arrow-up") + "</a></div>";
    html += "</aside></div>";
    return html;
  }

  function renderReferenceOnly() {
    app.innerHTML = viewReference();
    bindReference();
  }

  function bindReference() {
    document.querySelectorAll("[data-ref-tab]").forEach(function (b) {
      b.addEventListener("click", function () {
        state.refTab = b.getAttribute("data-ref-tab");
        history.replaceState(null, "", "#reference?tab=" + state.refTab);
        renderReferenceOnly();
      });
    });
    document.querySelectorAll(".entity-card[data-entity]").forEach(function (b) {
      b.addEventListener("click", function () {
        state.refEntity = b.getAttribute("data-entity");
        state.refTab = "dictionary";
        renderReferenceOnly();
      });
    });
    document.querySelectorAll(".entity-index [data-entity]").forEach(function (b) {
      b.addEventListener("click", function () {
        state.refEntity = b.getAttribute("data-entity");
        renderReferenceOnly();
      });
    });
  }

  // ---------- routing ----------

  var VIEWS = {
    overview: viewOverview,
    ledger: viewLedger,
    accounts: viewAccounts,
    verification: viewVerification,
    studio: viewStudio,
    reference: viewReference
  };

  function renderRoute() {
    applyDataLinks();
    var raw = (location.hash || "#overview").slice(1);
    var bits = raw.split("?");
    var id = bits[0] || "overview";
    var params = new URLSearchParams(bits[1] || "");
    state.route = VIEWS[id] ? id : "overview";
    if (state.route === "reference" && params.get("tab")) {
      var tab = params.get("tab");
      var known = REF_TABS.some(function (t) { return t.id === tab; });
      if (known) state.refTab = tab;
    }
    if (state.route === "verification" && params.get("issue")) {
      var issue = params.get("issue");
      var exists = D.exceptions.some(function (c) { return c.issue_type === issue; });
      if (exists) { state.cases.issue = issue; state.cases.page = 1; }
    }
    if (state.route === "ledger" && params.get("type")) {
      var type = params.get("type");
      if (TYPE_LABELS[type] || type === "all") { state.ledger.type = type; state.ledger.page = 1; }
    }
    document.querySelectorAll("[data-route-link]").forEach(function (a) {
      a.classList.toggle("active", a.getAttribute("data-route-link") === state.route);
    });
    var current = document.getElementById("topbarCurrent");
    if (current) current.textContent = ROUTE_LABELS[state.route];
    if (state.route === "verification" && state.pendingIssue) {
      state.cases.issue = state.pendingIssue;
      state.cases.page = 1;
      state.pendingIssue = null;
    }
    app.innerHTML = VIEWS[state.route]();
    bindView(state.route);
    window.scrollTo(0, 0);
    closeRail();
  }

  function bindView(route) {
    if (route === "overview") bindOverview();
    if (route === "ledger") bindLedger();
    if (route === "accounts") bindAccounts();
    if (route === "verification") bindVerification();
    if (route === "studio") bindStudio();
    if (route === "reference") bindReference();
  }

  function bindOverview() {
    document.querySelectorAll("[data-range]").forEach(function (b) {
      b.addEventListener("click", function () {
        state.chartRange = Number(b.getAttribute("data-range"));
        refreshChart();
      });
    });
    app.querySelectorAll("tr[data-txn-id]").forEach(function (tr) {
      tr.addEventListener("click", function () { openLedgerDrawer(tr.getAttribute("data-txn-id")); });
    });
    app.querySelectorAll(".exception-row").forEach(function (row) {
      var go = function () {
        state.pendingIssue = row.getAttribute("data-issue");
        state.cases.page = 1;
        if (state.route === "verification") renderRoute(); else location.hash = "verification";
      };
      row.addEventListener("click", go);
      row.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); }
      });
    });
  }

  function bindLedger() {
    var search = document.getElementById("ledgerSearch");
    if (search) {
      search.addEventListener("input", function () {
        state.ledger.q = search.value;
        state.ledger.page = 1;
        refreshLedger();
      });
    }
    var types = document.getElementById("ledgerTypes");
    if (types) {
      types.addEventListener("click", function (e) {
        var chip = e.target.closest("[data-type]");
        if (!chip) return;
        state.ledger.type = chip.getAttribute("data-type");
        state.ledger.page = 1;
        refreshLedger();
      });
    }
    var sort = document.getElementById("ledgerSort");
    if (sort) sort.addEventListener("change", function () { state.ledger.sort = sort.value; state.ledger.page = 1; refreshLedger(); });
    var sheet = document.getElementById("ledgerSheet");
    if (sheet) {
      sheet.addEventListener("click", function (e) {
        var page = e.target.closest("[data-ledger-page]");
        if (page && !page.disabled) {
          state.ledger.page = Number(page.getAttribute("data-ledger-page"));
          refreshLedger();
          return;
        }
        var tr = e.target.closest("tr[data-txn]");
        if (tr) openLedgerDrawer(tr.getAttribute("data-txn"));
      });
      sheet.addEventListener("keydown", function (e) {
        if (e.key !== "Enter" && e.key !== " ") return;
        var tr = e.target.closest("tr[data-txn]");
        if (tr) { e.preventDefault(); openLedgerDrawer(tr.getAttribute("data-txn")); }
      });
    }
  }

  function bindAccounts() {
    var search = document.getElementById("accountSearch");
    if (search) {
      search.addEventListener("input", function () {
        state.accounts.q = search.value;
        state.accounts.page = 1;
        refreshAccounts();
      });
    }
    var tiers = document.getElementById("accountTiers");
    if (tiers) {
      tiers.addEventListener("click", function (e) {
        var chip = e.target.closest("[data-tier]");
        if (!chip) return;
        state.accounts.tier = chip.getAttribute("data-tier");
        state.accounts.page = 1;
        refreshAccounts();
      });
    }
    var status = document.getElementById("accountStatus");
    if (status) status.addEventListener("change", function () { state.accounts.status = status.value; state.accounts.page = 1; refreshAccounts(); });
    var sort = document.getElementById("accountSort");
    if (sort) sort.addEventListener("change", function () { state.accounts.sort = sort.value; state.accounts.page = 1; refreshAccounts(); });
    var sheet = document.getElementById("accountSheet");
    if (sheet) {
      sheet.addEventListener("click", function (e) {
        var page = e.target.closest("[data-account-page]");
        if (page && !page.disabled) {
          state.accounts.page = Number(page.getAttribute("data-account-page"));
          refreshAccounts();
          return;
        }
        var tr = e.target.closest("tr[data-account]");
        if (tr) openAccountDrawer(tr.getAttribute("data-account"));
      });
      sheet.addEventListener("keydown", function (e) {
        if (e.key !== "Enter" && e.key !== " ") return;
        var tr = e.target.closest("tr[data-account]");
        if (tr) { e.preventDefault(); openAccountDrawer(tr.getAttribute("data-account")); }
      });
    }
  }

  // ---------- shell ----------

  function bindChrome() {
    document.querySelectorAll('[data-bind="seed"]').forEach(function (el) { el.textContent = M.seed; });
    document.querySelectorAll('[data-bind="buildId"]').forEach(function (el) { el.textContent = M.build_id; });
    document.querySelectorAll('[data-bind="asOfShort"]').forEach(function (el) { el.textContent = fmtDate(M.as_of); });
    document.querySelectorAll('[data-bind="seedLine"]').forEach(function (el) { el.textContent = "Seed " + M.seed; });
    var topDate = document.querySelector(".topbar-date");
    if (topDate) topDate.textContent = "As of " + fmtDate(M.as_of) + " · 09:00 UTC";
  }

  var rail = document.getElementById("sidebar");
  var railScrim = document.getElementById("railScrim");
  var menuButton = document.getElementById("menuButton");

  function openRail() {
    if (!rail) return;
    rail.classList.add("open");
    if (railScrim) railScrim.hidden = false;
    if (menuButton) menuButton.setAttribute("aria-expanded", "true");
  }

  function closeRail() {
    if (!rail) return;
    rail.classList.remove("open");
    if (railScrim) railScrim.hidden = true;
    if (menuButton) menuButton.setAttribute("aria-expanded", "false");
  }

  function init() {
    bindChrome();
    if (menuButton) menuButton.addEventListener("click", openRail);
    var railClose = document.getElementById("railClose");
    if (railClose) railClose.addEventListener("click", closeRail);
    if (railScrim) railScrim.addEventListener("click", closeRail);
    if (drawerClose) drawerClose.addEventListener("click", closeDrawer);
    if (drawerScrim) drawerScrim.addEventListener("click", closeDrawer);

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") {
        closeDrawer();
        closeRail();
      }
      if (e.key === "Tab" && drawerLayer && !drawerLayer.hidden) {
        var focusables = Array.prototype.filter.call(
          drawerLayer.querySelectorAll('a[href]:not([tabindex="-1"]), button:not([disabled]):not([tabindex="-1"]), input:not([disabled]):not([tabindex="-1"]), select:not([disabled]):not([tabindex="-1"]), textarea:not([disabled]):not([tabindex="-1"]), [tabindex]:not([tabindex="-1"])'),
          function (el) { return el.offsetParent !== null; }
        );
        if (focusables.length) {
          var first = focusables[0];
          var last = focusables[focusables.length - 1];
          if (!drawerLayer.contains(document.activeElement)) {
            e.preventDefault();
            first.focus();
          } else if (e.shiftKey && document.activeElement === first) {
            e.preventDefault();
            last.focus();
          } else if (!e.shiftKey && document.activeElement === last) {
            e.preventDefault();
            first.focus();
          }
        }
      }
      if (e.key === "/" && !/^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement.tagName)) {
        var input = document.querySelector(".filter-search input");
        if (input) { e.preventDefault(); input.focus(); }
      }
    });

    document.querySelectorAll(".nav-link").forEach(function (a) {
      a.addEventListener("click", closeRail);
    });

    window.addEventListener("hashchange", renderRoute);
    if (!location.hash) history.replaceState(null, "", "#overview");
    renderRoute();
    var year = document.querySelector("[data-bind='year']");
    if (year) year.textContent = new Date().getFullYear();
  }

  init();
})();
