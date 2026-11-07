#Requires -Version 5.1
<#
.SYNOPSIS
  Uploads the Ledgerline data files (csv / jsonl / json / sql / manifest / bundle)
  to a Cloudflare R2 bucket so the deployed site can point at them.

.EXAMPLE
  .\scripts\publish-data-r2.ps1 -Bucket ledgerline-data

.NOTES
  Prerequisite: Wrangler authenticated for the account that owns the bucket.
  The site must not also deploy the same paths on Pages — one home for data.
  After upload, put the bucket origin in assets/js/config.js:
    window.LEDGER_DATA_BASE_URL = "https://your-bucket.your-account.r2.cloudflarestorage.com";
  (or enable the R2 public dev URL / a custom domain for the bucket first).
#>
param(
  [Parameter(Mandatory = $true)]
  [string]$Bucket,
  [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot)
)
$ErrorActionPreference = 'Stop'

$probe = Get-Command wrangler -ErrorAction SilentlyContinue
if (-not $probe) {
  Write-Host 'Wrangler not found. Run: npx wrangler login' -ForegroundColor Yellow
  exit 1
}

$targets = @(
  'csv', 'jsonl', 'json', 'sql'
)
foreach ($dir in $targets) {
  $src = Join-Path $ProjectRoot "data\$dir"
  if (-not (Test-Path $src)) { Write-Host "Skip missing $src"; continue }
  Write-Host "Uploading data/$dir/ ..."
  $files = Get-ChildItem -LiteralPath $src -Recurse -File
  foreach ($f in $files) {
    $key = "data/" + $dir + "/" + $f.Name
    & wrangler r2 object put "$Bucket/$key" --file $f.FullName
    if ($LASTEXITCODE -ne 0) { throw "Failed uploading $key" }
  }
}

$singles = @('manifest.json', 'reproducibility.json', 'ledgerline_bundle.zip')
foreach ($name in $singles) {
  $src = Join-Path $ProjectRoot "data\$name"
  if (-not (Test-Path $src)) { Write-Host "Skip missing $src"; continue }
  Write-Host "Uploading data/$name ..."
  & wrangler r2 object put "$Bucket/data/$name" --file $src
  if ($LASTEXITCODE -ne 0) { throw "Failed uploading data/$name" }
}

Write-Host ''
Write-Host 'Done. Set this in assets/js/config.js (and redeploy the site):'
Write-Host "  window.LEDGER_DATA_BASE_URL = `"https://<your-bucket>.<your-account>.r2.cloudflarestorage.com`";"
Write-Host 'Or test without editing:' 
Write-Host '  <site-url>/?data=https://<bucket-origin>'
