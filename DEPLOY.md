# Deploy Ledgerline (Vercel or Cloudflare Pages)

Ledgerline is a zero-build static site: `index.html` + `assets/` (1.1 MB),
with its payload in `assets/js/data.js`. It works over `http(s)://`, over
`file://` (except downloads, which need HTTP), and offline (fonts are local).

## Which folder to deploy

| Folder | What it contains | Use it when |
|---|---|---|
| `deploy/` (`deploy-site.zip`, ~500 KB) | Site only (`index.html`, `assets/`, `docs/`) | You only need the interactive site on the host. |
| `deploy-cloudflare/` (`deploy-cloudflare.zip`, ~510 KB) | Site + `data/json/ground_truth.json`, `data/manifest.json`, `data/reproducibility.json`, `data/sql/schema.sql` | **Recommended for Cloudflare Pages** — everything under the 25 MB/file limit, deploys instantly. |
| project root (`index.html` + `data/`) | Site + all data (~520 MB) | Local preview via `python -m http.server 4173`, or a host that accepts large files. |

All three work with `assets/js/config.js` — see "Where the downloads live".

## Recommended: site on Pages, data on R2

Cloudflare Pages limits (free plan) reject files over 25 MB — `seed.sql`
(130 MB), `points_transactions.csv` (53 MB) and the bundle (52 MB) can never
live there. The clean split is:

1. **Site → Cloudflare Pages** (or Vercel, same steps).
2. **Data → Cloudflare R2 bucket**, then point the site at the bucket.

### 1. Deploy the site

From PowerShell, in the project root:

```powershell
npx wrangler pages deploy deploy-cloudflare --project-name ledgerline
```

or drag `deploy-cloudflare/` (or `deploy-cloudflare.zip`) onto
**Dashboard → Workers & Pages → Create → Pages → Upload assets**.

For Vercel instead:

```powershell
cd deploy-cloudflare
npx vercel --prod
# Framework preset: Other · Build command: none · Output directory: ./
```

### 2. Publish the data to R2

Prerequisite: `npx wrangler login` for the account that will own the data.

```powershell
npx wrangler r2 bucket create ledgerline-data
.\scripts\publish-data-r2.ps1 -Bucket ledgerline-data
```

### 3. Point the site at the bucket

Make the bucket publicly readable (R2 dashboard → your bucket → **Settings →
Public access → Enable**), then edit `assets/js/config.js` in the deploy
source (`assets/` at the root, then re-copy or build from there):

```js
window.LEDGER_DATA_BASE_URL = "https://<your-bucket>.<your-account>.r2.cloudflarestorage.com";
```

No trailing slash — paths are appended under `/data/` (`<base>/data/csv/customers.csv`,
`<base>/data/sql/seed.sql`, `<base>/data/ledgerline_bundle.zip`, …).

Redeploy the site. To test a bucket before editing the file, append
`?data=<bucket-origin>` to any page URL, e.g.
`https://ledgerline.pages.dev/?data=https://ledgerline-data.<acct>.r2.cloudflarestorage.com`.

## Smoke test after deploy

Visit these routes on the live URL (no 404s expected, and the chart must render):

```text
#overview  #ledger  #accounts  #verification  #studio  #reference?tab=dictionary
```

Then spot-check one download from each family: Full ledger CSV, Ground truth
JSON, schema.sql, seed.sql, Run bundle.

## Notes

- **Regenerating data:** run `python generator/generate.py --seed 20261022 --out data --verify-repro`
  locally, re-run `scripts\publish-data-r2.ps1`, then redeploy the site so
  `assets/js/data.js` matches the new exports.
- **Vercel single-host alternative:** if you want everything on one host, deploy
  from the project root with Vercel — it tolerates the large files the free
  Pages limits reject (still mind disk/egress costs for the 287 MB JSONL set).
- **Do not deploy `data/starter/`** — it is a small local sample, not part of the
  production payload.
