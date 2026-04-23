Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectId,
    [ValidateSet("cpu", "gpu")]
    [string]$Profile = "cpu",
    [string]$Region = "asia-northeast3",
    [string]$Repository = "mulmumu-ai",
    [string]$ImageName = "ai-api",
    [string]$Tag = "latest"
)

$configFile = if ($Profile -eq "gpu") { "cloudbuild.gpu.yaml" } else { "cloudbuild.cpu.yaml" }
$resolvedImageName = if ($Profile -eq "gpu" -and $ImageName -eq "ai-api") { "ai-api-gpu" } else { $ImageName }

$submitArgs = @(
    "builds", "submit", ".",
    "--project", $ProjectId,
    "--config", $configFile,
    "--substitutions", "_REGION=$Region,_REPOSITORY=$Repository,_IMAGE_NAME=$resolvedImageName,_TAG=$Tag"
)

& gcloud @submitArgs

$imageUri = "$Region-docker.pkg.dev/$ProjectId/$Repository/$resolvedImageName`:$Tag"
Write-Host "Built and pushed image: $imageUri"
