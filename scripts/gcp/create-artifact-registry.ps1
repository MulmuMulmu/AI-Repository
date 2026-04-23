Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectId,
    [string]$Region = "asia-northeast3",
    [string]$Repository = "mulmumu-ai",
    [string]$Description = "Mulmumu AI container images"
)

$describeArgs = @(
    "artifacts", "repositories", "describe", $Repository,
    "--project", $ProjectId,
    "--location", $Region
)

& gcloud @describeArgs *> $null
if ($LASTEXITCODE -eq 0) {
    Write-Host "Artifact Registry repository already exists: $Repository"
    exit 0
}

$createArgs = @(
    "artifacts", "repositories", "create", $Repository,
    "--project", $ProjectId,
    "--repository-format", "docker",
    "--location", $Region,
    "--description", $Description
)

& gcloud @createArgs
