# Build (if needed) and run the FinAlly Docker container.
# Idempotent: safe to run multiple times.
#
# Usage:
#   .\scripts\start_windows.ps1            # run with existing image
#   .\scripts\start_windows.ps1 -Build     # force rebuild before running
#   .\scripts\start_windows.ps1 -Open      # open http://localhost:8000 after start

[CmdletBinding()]
param(
    [switch]$Build,
    [switch]$Open
)

$ErrorActionPreference = "Stop"

$ImageName     = "finally"
$ContainerName = "finally"
$VolumeName    = "finally-data"
$Port          = 8000

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "docker is not installed or not on PATH."
    exit 1
}

if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Write-Host "No .env found. Copy .env.example to .env and fill in your keys:"
        Write-Host "  Copy-Item .env.example .env"
    } else {
        Write-Error ".env not found and no .env.example to copy."
    }
    exit 1
}

$imageExists = $true
docker image inspect $ImageName *> $null
if ($LASTEXITCODE -ne 0) { $imageExists = $false }

if ($Build -or -not $imageExists) {
    Write-Host "Building Docker image: $ImageName"
    docker build -t $ImageName .
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$existing = docker ps -a --format '{{.Names}}' | Select-String -Pattern "^$ContainerName$" -Quiet
if ($existing) {
    Write-Host "Removing existing container: $ContainerName"
    docker rm -f $ContainerName | Out-Null
}

Write-Host "Starting container: $ContainerName"
docker run -d `
    --name $ContainerName `
    -p "$($Port):8000" `
    -v "$($VolumeName):/app/db" `
    --env-file .env `
    $ImageName | Out-Null

$Url = "http://localhost:$Port"
Write-Host "FinAlly is starting at $Url"

if ($Open) {
    Start-Process $Url
}
