param(
    [string]$TaskName = "FTIR-NAS-Backup",
    [string]$BackupScriptPath = "",
    [string]$ConfigFile = "",
    [string]$DailyAt = "02:30"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-AbsolutePath {
    param([string]$PathText)

    if ([string]::IsNullOrWhiteSpace($PathText)) {
        return ""
    }

    if ([System.IO.Path]::IsPathRooted($PathText)) {
        return [System.IO.Path]::GetFullPath($PathText)
    }

    return [System.IO.Path]::GetFullPath((Join-Path (Get-Location).Path $PathText))
}

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($BackupScriptPath)) {
    $BackupScriptPath = Join-Path $scriptRoot "backup-to-nas.ps1"
}
if ([string]::IsNullOrWhiteSpace($ConfigFile)) {
    $ConfigFile = Join-Path $scriptRoot "backup-config.json"
}

$BackupScriptPath = Resolve-AbsolutePath -PathText $BackupScriptPath
$ConfigFile = Resolve-AbsolutePath -PathText $ConfigFile

if (-not (Test-Path -LiteralPath $BackupScriptPath)) {
    throw "Backup script not found: $BackupScriptPath"
}
if (-not (Test-Path -LiteralPath $ConfigFile)) {
    throw "Backup config file not found: $ConfigFile"
}

$time = [DateTime]::Today
if (-not [DateTime]::TryParseExact($DailyAt, "HH:mm", $null, [System.Globalization.DateTimeStyles]::None, [ref]$time)) {
    throw "DailyAt must be in HH:mm format, for example 02:30"
}

$actionArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$BackupScriptPath`" -ConfigFile `"$ConfigFile`""
$action = New-ScheduledTaskAction -Execute "pwsh.exe" -Argument $actionArgs
$trigger = New-ScheduledTaskTrigger -Daily -At $time
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null

Write-Host "Scheduled task installed."
Write-Host "TaskName: $TaskName"
Write-Host "Script: $BackupScriptPath"
Write-Host "Config: $ConfigFile"
Write-Host "DailyAt: $DailyAt"
Write-Host "You can test it now with: Start-ScheduledTask -TaskName `"$TaskName`""
