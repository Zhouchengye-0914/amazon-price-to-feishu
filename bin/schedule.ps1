param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('--install', '--remove')]
    [string]$Action
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$runner = Join-Path $projectRoot 'bin\scheduled_run.bat'

if ($Action -eq '--remove') {
    & schtasks.exe /Delete /TN AmazonDaily_0730 /F
    & schtasks.exe /Delete /TN AmazonDaily_1530 /F
    exit 0
}

# HTML service and firewall are managed separately; price install/remove must
# not start, stop, or grant network access for that optional service.
# Current production schedule: weekdays at 07:30 and 15:30, no expiration.
& schtasks.exe /Create /TN AmazonDaily_0730 /TR $runner /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 07:30 /F
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& schtasks.exe /Create /TN AmazonDaily_1530 /TR $runner /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 15:30 /F
exit $LASTEXITCODE
