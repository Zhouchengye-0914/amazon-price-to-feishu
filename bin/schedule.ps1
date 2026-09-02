param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('--install', '--remove')]
    [string]$Action
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$runner = Join-Path $projectRoot 'bin\scheduled_run.ps1'
$hiddenLauncher = Join-Path $projectRoot 'bin\hidden_ps1.vbs'

if ($Action -eq '--remove') {
    & schtasks.exe /Delete /TN AmazonDaily_0730 /F
    & schtasks.exe /Delete /TN AmazonDaily_1530 /F
    exit 0
}

# HTML service and firewall are managed separately; price install/remove must
# not start, stop, or grant network access for that optional service.
# Current production schedule: weekdays at 07:30 and 15:30, no expiration.
# Use the GUI-subsystem WScript launcher.  A task that calls a .bat/cmd wrapper
# can still flash a console before the inner PowerShell -WindowStyle Hidden is
# applied; wscript.exe avoids creating that console in the first place.
$taskAction = New-ScheduledTaskAction -Execute 'wscript.exe' -Argument (
    '//B //NoLogo "{0}" "{1}"' -f $hiddenLauncher, $runner)
$settings = New-ScheduledTaskSettingsSet -Hidden -StartWhenAvailable -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
foreach ($item in @(@('AmazonDaily_0730', 7, 30), @('AmazonDaily_1530', 15, 30))) {
    $trigger = New-ScheduledTaskTrigger -Weekly -WeeksInterval 1 -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At (
        Get-Date -Hour $item[1] -Minute $item[2] -Second 0)
    Register-ScheduledTask -TaskName $item[0] -Action $taskAction -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
}
