$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$schedulerLogRoot = Join-Path $projectRoot 'outputs\scheduler_logs'
New-Item -ItemType Directory -Force -Path $schedulerLogRoot | Out-Null
$startedAt = Get-Date
$logPath = Join-Path $schedulerLogRoot ($startedAt.ToString('yyyy-MM-dd_HHmmss') + '.log')
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    "[$($startedAt.ToString('o'))] ERROR: Python not found: $python" | Set-Content -LiteralPath $logPath -Encoding UTF8
    exit 2
}
Set-Location -LiteralPath $projectRoot
# Python owns outputs/weekly_scheduler.lock for ALL CLI entrypoints.
# Do not acquire the same lock twice (parent PowerShell + child Python).
"[$($startedAt.ToString('o'))] START weekly-run --confirm" | Set-Content -LiteralPath $logPath -Encoding UTF8
& $python 'app\main.py' '--weekly-run' '--confirm' *>> $logPath
$exitCode = $LASTEXITCODE
$finishedAt = Get-Date
"[$($finishedAt.ToString('o'))] END exit=$exitCode elapsed_seconds=$([math]::Round(($finishedAt - $startedAt).TotalSeconds, 3))" | Add-Content -LiteralPath $logPath -Encoding UTF8
exit $exitCode
