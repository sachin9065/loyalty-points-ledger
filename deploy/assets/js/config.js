/* Ledgerline deployment config.
 *
 * Where the downloadable data lives.
 * - "" (default): same origin, relative paths (data/csv/, data/sql/, ...).
 *   Use this when the data folder is deployed together with the site
 *   (e.g. a local `python -m http.server` or a host that accepts large files).
 * - "https://your-bucket.example.com" (no trailing slash): the data is
 *   hosted on object storage (Cloudflare R2, S3, etc.). Paths are appended
 *   under /data/, e.g. BASE + "/data/csv/customers.csv" (matches the keys
 *   scripts/publish-data-r2.ps1 uploads). Use this when the site is on
 *   Cloudflare Pages / Vercel and the CSV / SQL / JSONL files are on R2.
 *
 * You can also override per-visit with ?data=<base-url> — handy for testing
 * a bucket before committing it here. No rebuild needed either way.
 */
window.LEDGER_DATA_BASE_URL = "";
