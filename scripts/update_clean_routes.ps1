# Run from a downloaded copy of meisacore/Newnews. Keeps the local Hyperdrive ID.
$ErrorActionPreference = "Stop"
$norxRoot = Split-Path $PSScriptRoot -Parent
$norxBase = "https://raw.githubusercontent.com/meisacore/Newnews/main"
$norxFiles = @(
    "frontend/index.html",
    "frontend/market.html",
    "frontend/public/favicon.svg",
    "frontend/src/routing.js",
    "frontend/src/App.jsx",
    "frontend/src/main.jsx",
    "frontend/src/ExchangeChrome.jsx",
    "frontend/src/Terminal.jsx",
    "frontend/vite.config.js",
    "cloudflare/src/index.js",
    "server.py"
)
foreach ($norxFile in $norxFiles) {
    $norxTarget = Join-Path $norxRoot $norxFile
    Invoke-WebRequest -Uri "$norxBase/$norxFile" -OutFile $norxTarget -UseBasicParsing -ErrorAction Stop
}
$norxConfigPath = Join-Path $norxRoot "cloudflare/wrangler.jsonc"
$norxConfig = [IO.File]::ReadAllText($norxConfigPath)
$norxPattern = '"run_worker_first"\s*:\s*\[[^\]]*\]'
if (-not [regex]::IsMatch($norxConfig, $norxPattern)) {
    throw "Could not locate run_worker_first in wrangler.jsonc. Configuration was not overwritten."
}
$norxRoutes = '"run_worker_first": ["/api/*", "/", "/pulse", "/pulse/", "/discover", "/discover/", "/trade", "/trade/*", "/portfolio", "/portfolio/", "/agents", "/agents/", "/market"]'
$norxConfig = [regex]::Replace($norxConfig, $norxPattern, $norxRoutes)
[IO.File]::WriteAllText($norxConfigPath, $norxConfig, [System.Text.UTF8Encoding]::new($false))
Write-Host "Clean routes and favicon updated. Your Hyperdrive binding was retained."
Write-Host "Next: cd cloudflare; npm run deploy"
