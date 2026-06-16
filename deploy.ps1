# deploy.ps1 - PowerShell script to configure Coolify application FQDN and trigger restart

# Load env variables from .env if it exists
if (Test-Path .env) {
    Get-Content .env | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#")) {
            $key, $value = $line -split '=', 2
            if ($key -and $value) {
                [System.Environment]::SetEnvironmentVariable($key.Trim(), $value.Trim(), "Process")
            }
        }
    }
}

$DryRun = $args -contains "--dry-run"

# Configuration check
$errors = @()
$vpsIp = [System.Environment]::GetEnvironmentVariable("VPS_IP")
$appUuid = [System.Environment]::GetEnvironmentVariable("APP_UUID")
$coolifyToken = [System.Environment]::GetEnvironmentVariable("COOLIFY_API_TOKEN")
$domainUrl = [System.Environment]::GetEnvironmentVariable("DOMAIN_URL")

if ([string]::IsNullOrEmpty($vpsIp) -or $vpsIp.Contains("your_") -or $vpsIp.Contains("placeholder")) {
    $errors += "VPS_IP is missing or set to a placeholder."
}

if ([string]::IsNullOrEmpty($appUuid) -or $appUuid.Contains("your_") -or $appUuid.Contains("placeholder")) {
    $errors += "APP_UUID is missing or set to a placeholder."
}

if ([string]::IsNullOrEmpty($coolifyToken) -or $coolifyToken.Contains("your_") -or $coolifyToken.Contains("placeholder")) {
    $errors += "COOLIFY_API_TOKEN is missing or set to a placeholder."
}

if ([string]::IsNullOrEmpty($domainUrl)) {
    $domainUrl = "https://arbitragearena.io"
}

if ($errors.Length -gt 0) {
    Write-Host "Error: Configuration validation failed:" -ForegroundColor Red
    foreach ($err in $errors) {
        Write-Host "  - $err" -ForegroundColor Red
    }
    Exit 1
}

$coolifyUrl = "http://$($vpsIp):8000"
$cliPath = "$env:LOCALAPPDATA\Coolify\coolify.exe"

if (-not (Test-Path $cliPath)) {
    $cliPath = "coolify"
}

if ($DryRun) {
    Write-Host "=== COOLIFY DEPLOYMENT DRY RUN ==="
    Write-Host "URL: $coolifyUrl"
    Write-Host "APP UUID: $appUuid"
    Write-Host "DOMAIN URL: $domainUrl"
    Write-Host ""
    Write-Host "[Dry Run] Would configure Coolify context 'my-server' using URL: $coolifyUrl"
    Write-Host "[Dry Run] Would verify context connection."
    Write-Host "[Dry Run] Would run: coolify app env create $appUuid --key COOLIFY_FQDN --value `"$domainUrl`""
    Write-Host "[Dry Run] Would run: coolify app update $appUuid --domains `"$domainUrl`""
    Write-Host "[Dry Run] Would run: coolify app restart $appUuid"
    Write-Host "=================================="
    Exit 0
}

Write-Host "=== COOLIFY DEPLOYMENT ==="
Write-Host "Configuring context..."
& $cliPath context add my-server "$coolifyUrl" "$coolifyToken" --default --force

Write-Host "Verifying context..."
& $cliPath context verify

Write-Host "Setting COOLIFY_FQDN environment variable..."
& $cliPath app env create "$appUuid" --key COOLIFY_FQDN --value "$domainUrl"

Write-Host "Updating application domains configuration..."
& $cliPath app update "$appUuid" --domains "$domainUrl"

Write-Host "Restarting application to apply changes..."
& $cliPath app restart "$appUuid"
Write-Host "Deployment triggered successfully!"
