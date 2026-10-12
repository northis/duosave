<#
.SYNOPSIS
    Register (or remove) the "Duosave Updater" scheduled task.
.DESCRIPTION
    The task starts `pythonw -m duosave.updater run --repo <repo>` at logon of the current
    user, restarts it after a failure and has no execution time limit. No administrator
    rights are needed: the updater only runs git and the docker CLI inside the repository.
.PARAMETER Python
    Path to python.exe or pythonw.exe. Default: pythonw.exe next to `python` from PATH.
.PARAMETER Remove
    Stop and unregister the task. Files in data/control are left untouched.
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File deploy\windows\install-updater.ps1
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File deploy\windows\install-updater.ps1 -Remove
#>
param(
    [string]$Python,
    [switch]$Remove
)

$ErrorActionPreference = "Stop"
$TaskName = "Duosave Updater"
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path

if ($Remove) {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($null -ne $task) {
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Removed the scheduled task '$TaskName'."
    } else {
        Write-Host "The scheduled task '$TaskName' is not registered."
    }
    exit 0
}

if (-not $Python) {
    $pythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $pythonExe) {
        throw "python.exe was not found in PATH; pass -Python <path to pythonw.exe>."
    }
    $pythonw = Join-Path (Split-Path $pythonExe) "pythonw.exe"
    $Python = if (Test-Path $pythonw) { $pythonw } else { $pythonExe }
}
if (-not (Test-Path $Python)) {
    throw "Python was not found at '$Python'."
}

$action = New-ScheduledTaskAction -Execute $Python `
    -Argument "-m duosave.updater run --repo `"$Repo`"" `
    -WorkingDirectory $Repo
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName
Write-Host "Registered and started the scheduled task '$TaskName'."
Write-Host "Check the runner with: python -m duosave.updater status --repo `"$Repo`""
