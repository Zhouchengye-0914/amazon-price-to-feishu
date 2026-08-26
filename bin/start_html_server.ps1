$ErrorActionPreference = 'Stop'

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$logRoot = Join-Path $projectRoot 'outputs\html_server_logs'
New-Item -ItemType Directory -Force -Path $logRoot | Out-Null

function Test-HtmlServer {
    $raw = & $python (Join-Path $projectRoot 'app\html_server.py') '--status' 2>$null
    if ($LASTEXITCODE -ne 0) { return $false }
    try { return [bool](($raw | ConvertFrom-Json).reachable) } catch { return $false }
}

if (Test-HtmlServer) { exit 0 }

$stamp = (Get-Date).ToString('yyyy-MM-dd_HHmmss')
$stdout = Join-Path $logRoot ($stamp + '.out.log')
$stderr = Join-Path $logRoot ($stamp + '.err.log')
Start-Process -FilePath $python `
    -ArgumentList @((Join-Path $projectRoot 'app\html_server.py'), '--serve') `
    -WorkingDirectory $projectRoot -WindowStyle Hidden `
    -RedirectStandardOutput $stdout -RedirectStandardError $stderr

for ($attempt = 0; $attempt -lt 20; $attempt++) {
    Start-Sleep -Milliseconds 500
    if (Test-HtmlServer) { exit 0 }
}
throw "HTML局域网服务启动后健康检查失败，日志: $stderr"
