Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectId,
    [ValidateSet("cpu", "gpu", "recommend")]
    [string]$Profile = "cpu",
    [string]$Region = "asia-northeast3",
    [string]$Repository = "mulmumu-ai",
    [string]$ImageName = "ai-api",
    [string]$Tag = "latest"
)

$configFile = switch ($Profile) {
    "gpu" { "cloudbuild.gpu.yaml" }
    "recommend" { "cloudbuild.recommend.yaml" }
    default { "cloudbuild.cpu.yaml" }
}

$resolvedImageName = switch ($Profile) {
    "gpu" {
        if ($ImageName -eq "ai-api") { "ocr-api-gpu" } else { $ImageName }
    }
    "recommend" {
        if ($ImageName -eq "ai-api") { "recommend-api" } else { $ImageName }
    }
    default {
        if ($ImageName -eq "ai-api") { "ocr-api" } else { $ImageName }
    }
}

$submitArgs = @(
    "builds", "submit", ".",
    "--project", $ProjectId,
    "--config", $configFile,
    "--substitutions", "_REGION=$Region,_REPOSITORY=$Repository,_IMAGE_NAME=$resolvedImageName,_TAG=$Tag"
)

& gcloud @submitArgs

$imageUri = "$Region-docker.pkg.dev/$ProjectId/$Repository/$resolvedImageName`:$Tag"
Write-Host "Built and pushed image: $imageUri"
