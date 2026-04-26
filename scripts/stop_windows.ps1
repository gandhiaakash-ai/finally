# Stop and remove the FinAlly container.
# The Docker volume (finally-data) is preserved so portfolio data persists.
# Idempotent: safe to run when the container is already stopped or absent.

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$ContainerName = "finally"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "docker is not installed or not on PATH."
    exit 1
}

$existing = docker ps -a --format '{{.Names}}' | Select-String -Pattern "^$ContainerName$" -Quiet
if ($existing) {
    Write-Host "Stopping container: $ContainerName"
    docker rm -f $ContainerName | Out-Null
    Write-Host "Stopped. Volume 'finally-data' is preserved."
} else {
    Write-Host "Container '$ContainerName' is not running."
}
