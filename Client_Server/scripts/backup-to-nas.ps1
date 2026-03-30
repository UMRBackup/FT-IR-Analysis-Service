param(
    [string]$ConfigFile = "",
    [string]$NasBackupRoot = "",
    [string]$ComposeFile = "",
    [string]$EnvFile = "",
    [string[]]$BackupSourcePaths = @(),
    [Nullable[int]]$RetentionDays = $null,
    [string]$MysqlServiceName = "",
    [string]$BackupPrefix = ""
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

function Read-SimpleEnvFile {
    param([string]$FilePath)

    $result = @{}
    if (-not (Test-Path -LiteralPath $FilePath)) {
        return $result
    }

    $lines = Get-Content -LiteralPath $FilePath
    foreach ($line in $lines) {
        $trimmed = $line.Trim()
        if ([string]::IsNullOrWhiteSpace($trimmed)) {
            continue
        }
        if ($trimmed.StartsWith("#")) {
            continue
        }

        $separatorIndex = $trimmed.IndexOf("=")
        if ($separatorIndex -le 0) {
            continue
        }

        $key = $trimmed.Substring(0, $separatorIndex).Trim()
        $value = $trimmed.Substring($separatorIndex + 1).Trim()
        $result[$key] = $value
    }

    return $result
}

function Merge-Config {
    param(
        [hashtable]$Target,
        [pscustomobject]$Source
    )

    if ($null -eq $Source) {
        return
    }

    foreach ($property in $Source.PSObject.Properties) {
        $name = $property.Name
        $value = $property.Value
        if ($null -eq $value) {
            continue
        }

        if ($value -is [string] -and [string]::IsNullOrWhiteSpace($value)) {
            continue
        }

        if ($value -is [System.Collections.IEnumerable] -and -not ($value -is [string])) {
            $arr = @($value)
            if ($arr.Count -eq 0) {
                continue
            }
            $Target[$name] = $arr
            continue
        }

        $Target[$name] = $value
    }
}

function Ensure-NativeCommand {
    param([string]$Name)

    if (-not (Get-Command -Name $Name -ErrorAction SilentlyContinue)) {
        throw "Required command not found: $Name"
    }
}

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$clientServerRoot = Split-Path -Parent $scriptRoot

$config = @{
    NasBackupRoot = ""
    ComposeFile = (Join-Path $clientServerRoot "docker-compose.yml")
    EnvFile = (Join-Path $clientServerRoot ".env")
    BackupSourcePaths = @((Join-Path $clientServerRoot "shared_storage"))
    RetentionDays = 14
    MysqlServiceName = "mysql"
    BackupPrefix = "ftir"
}

if (-not [string]::IsNullOrWhiteSpace($ConfigFile)) {
    $resolvedConfigFile = Resolve-AbsolutePath -PathText $ConfigFile
    if (-not (Test-Path -LiteralPath $resolvedConfigFile)) {
        throw "Config file not found: $resolvedConfigFile"
    }

    $configJson = Get-Content -LiteralPath $resolvedConfigFile -Raw | ConvertFrom-Json
    Merge-Config -Target $config -Source $configJson
}

$cliConfig = [pscustomobject]@{
    NasBackupRoot = $NasBackupRoot
    ComposeFile = $ComposeFile
    EnvFile = $EnvFile
    BackupSourcePaths = $BackupSourcePaths
    RetentionDays = if ($null -ne $RetentionDays) { [int]$RetentionDays } else { $null }
    MysqlServiceName = $MysqlServiceName
    BackupPrefix = $BackupPrefix
}
Merge-Config -Target $config -Source $cliConfig

$config.NasBackupRoot = Resolve-AbsolutePath -PathText ([string]$config.NasBackupRoot)
$config.ComposeFile = Resolve-AbsolutePath -PathText ([string]$config.ComposeFile)
$config.EnvFile = Resolve-AbsolutePath -PathText ([string]$config.EnvFile)
$config.BackupSourcePaths = @($config.BackupSourcePaths | ForEach-Object { Resolve-AbsolutePath -PathText ([string]$_) })
$config.RetentionDays = [int]$config.RetentionDays

if ([string]::IsNullOrWhiteSpace($config.NasBackupRoot)) {
    throw "NasBackupRoot is required. Provide -NasBackupRoot or set it in config json."
}

if (-not (Test-Path -LiteralPath $config.ComposeFile)) {
    throw "Compose file not found: $($config.ComposeFile)"
}

if ($config.BackupSourcePaths.Count -eq 0) {
    throw "BackupSourcePaths is empty."
}

Ensure-NativeCommand -Name "docker"
Ensure-NativeCommand -Name "robocopy"

if (-not (Test-Path -LiteralPath $config.NasBackupRoot)) {
    New-Item -ItemType Directory -Path $config.NasBackupRoot -Force | Out-Null
}

$envMap = Read-SimpleEnvFile -FilePath $config.EnvFile
$mysqlDatabase = if ($envMap.ContainsKey("MYSQL_DATABASE")) { $envMap["MYSQL_DATABASE"] } else { "ftir" }
$mysqlRootPassword = if ($envMap.ContainsKey("MYSQL_ROOT_PASSWORD")) { $envMap["MYSQL_ROOT_PASSWORD"] } else { "" }

if ([string]::IsNullOrWhiteSpace($mysqlRootPassword)) {
    throw "MYSQL_ROOT_PASSWORD is required in env file: $($config.EnvFile)"
}

$composeArgs = @("compose", "-f", $config.ComposeFile)
if (Test-Path -LiteralPath $config.EnvFile) {
    $composeArgs += @("--env-file", $config.EnvFile)
}

$runningServices = & docker @composeArgs ps --status running --services
if ($LASTEXITCODE -ne 0) {
    throw "Failed to query docker compose services."
}

if (-not ($runningServices -contains $config.MysqlServiceName)) {
    throw "MySQL service '$($config.MysqlServiceName)' is not running."
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$runRoot = Join-Path $config.NasBackupRoot ("{0}-{1}" -f $config.BackupPrefix, $timestamp)
$dbDir = Join-Path $runRoot "db"
$dataDir = Join-Path $runRoot "data"

New-Item -ItemType Directory -Path $dbDir -Force | Out-Null
New-Item -ItemType Directory -Path $dataDir -Force | Out-Null

$dbDumpPath = Join-Path $dbDir ("{0}.sql" -f $mysqlDatabase)

Write-Host "[backup] dumping mysql database to $dbDumpPath"
$dumpOutput = & docker @composeArgs exec -T $config.MysqlServiceName mysqldump -uroot ("-p{0}" -f $mysqlRootPassword) --single-transaction --routines --triggers --events --databases $mysqlDatabase 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "mysqldump failed: $($dumpOutput -join [Environment]::NewLine)"
}
$dumpOutput | Set-Content -LiteralPath $dbDumpPath -Encoding utf8

$copiedTargets = @()
foreach ($sourcePath in $config.BackupSourcePaths) {
    if (-not (Test-Path -LiteralPath $sourcePath)) {
        throw "Backup source path not found: $sourcePath"
    }

    $leaf = Split-Path -Path $sourcePath -Leaf
    if ([string]::IsNullOrWhiteSpace($leaf)) {
        $leaf = "root"
    }

    $targetPath = Join-Path $dataDir $leaf
    New-Item -ItemType Directory -Path $targetPath -Force | Out-Null

    Write-Host "[backup] copying $sourcePath -> $targetPath"
    & robocopy $sourcePath $targetPath /MIR /R:2 /W:2 /NFL /NDL /NP /NJH /NJS | Out-Null
    $robocopyCode = $LASTEXITCODE
    if ($robocopyCode -ge 8) {
        throw "robocopy failed for '$sourcePath' with exit code $robocopyCode"
    }

    $copiedTargets += [pscustomobject]@{
        source = $sourcePath
        target = $targetPath
        robocopyExitCode = $robocopyCode
    }
}

$manifest = [pscustomobject]@{
    backupTimestamp = (Get-Date).ToString("o")
    host = $env:COMPUTERNAME
    mysqlService = $config.MysqlServiceName
    mysqlDatabase = $mysqlDatabase
    runRoot = $runRoot
    dbDumpPath = $dbDumpPath
    copiedData = $copiedTargets
    retentionDays = $config.RetentionDays
}

$manifestPath = Join-Path $runRoot "manifest.json"
$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $manifestPath -Encoding utf8

$cutoff = (Get-Date).AddDays(-1 * $config.RetentionDays)
$expired = Get-ChildItem -LiteralPath $config.NasBackupRoot -Directory |
    Where-Object {
        $_.Name -like ("{0}-*" -f $config.BackupPrefix) -and $_.LastWriteTime -lt $cutoff
    }

foreach ($dir in $expired) {
    Write-Host "[backup] removing expired backup: $($dir.FullName)"
    Remove-Item -LiteralPath $dir.FullName -Recurse -Force
}

Write-Host "[backup] completed successfully: $runRoot"
