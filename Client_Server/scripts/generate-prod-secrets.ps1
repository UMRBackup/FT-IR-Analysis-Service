param(
    [int]$JwtBytes = 64,
    [int]$DbPasswordBytes = 24,
    [int]$AdminPasswordLength = 20,
    [string]$WriteEnvFile = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function New-RandomBytes {
    param([int]$Length)

    $bytes = New-Object byte[] $Length
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($bytes)
    }
    finally {
        $rng.Dispose()
    }
    return $bytes
}

function New-HexSecret {
    param([int]$Length)

    $bytes = New-RandomBytes -Length $Length
    return ([Convert]::ToHexString($bytes)).ToLowerInvariant()
}

function New-Password {
    param([int]$Length)

    if ($Length -lt 12) {
        throw "Password length must be at least 12."
    }

    $upper = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    $lower = "abcdefghijkmnopqrstuvwxyz"
    $digits = "23456789"
    $special = "!@#%^*_+-="
    $all = $upper + $lower + $digits + $special

    $chars = New-Object System.Collections.Generic.List[char]
    $chars.Add($upper[(Get-Random -Minimum 0 -Maximum $upper.Length)])
    $chars.Add($lower[(Get-Random -Minimum 0 -Maximum $lower.Length)])
    $chars.Add($digits[(Get-Random -Minimum 0 -Maximum $digits.Length)])
    $chars.Add($special[(Get-Random -Minimum 0 -Maximum $special.Length)])

    for ($index = $chars.Count; $index -lt $Length; $index++) {
        $chars.Add($all[(Get-Random -Minimum 0 -Maximum $all.Length)])
    }

    $shuffled = $chars | Sort-Object { Get-Random }
    return -join $shuffled
}

$jwtSecret = New-HexSecret -Length $JwtBytes
$dbRootPassword = New-HexSecret -Length $DbPasswordBytes
$dbAppPassword = New-HexSecret -Length $DbPasswordBytes
$adminPassword = New-Password -Length $AdminPasswordLength

Write-Output "JWT_SECRET_KEY=$jwtSecret"
Write-Output "MYSQL_ROOT_PASSWORD=$dbRootPassword"
Write-Output "MYSQL_PASSWORD=$dbAppPassword"
Write-Output "INITIAL_ADMIN_PASSWORD=$adminPassword"

if ($WriteEnvFile) {
    $scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
    $clientServerRoot = Split-Path -Parent $scriptRoot
    $templatePath = Join-Path $clientServerRoot ".env.production.example"
    if (-not (Test-Path $templatePath)) {
        throw "Template not found: $templatePath"
    }

    $targetPath = if ([System.IO.Path]::IsPathRooted($WriteEnvFile)) {
        $WriteEnvFile
    } else {
        Join-Path $clientServerRoot $WriteEnvFile
    }

    $content = Get-Content -Path $templatePath -Raw
    $content = $content.Replace("REPLACE_WITH_GENERATED_MYSQL_ROOT_PASSWORD", $dbRootPassword)
    $content = $content.Replace("REPLACE_WITH_GENERATED_MYSQL_APP_PASSWORD", $dbAppPassword)
    $content = $content.Replace("REPLACE_WITH_GENERATED_SECRET", $jwtSecret)
    $content = $content.Replace("REPLACE_WITH_GENERATED_ADMIN_PASSWORD", $adminPassword)

    Set-Content -Path $targetPath -Value $content -Encoding ascii
    Write-Output "Wrote env template to $targetPath"
    Write-Output "Remember to set any external API keys manually."
}