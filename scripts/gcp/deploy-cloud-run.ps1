Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectId,
    [string]$Region = "asia-northeast3",
    [string]$ServiceName = "mulmumu-ai-api",
    [string]$Repository = "mulmumu-ai",
    [string]$ImageName = "ai-api",
    [string]$Tag = "latest",
    [int]$Port = 8000,
    [string]$Memory = "2Gi",
    [int]$Cpu = 2,
    [int]$Concurrency = 1,
    [int]$TimeoutSeconds = 300,
    [switch]$AllowUnauthenticated,
    [string]$QwenBaseUrl = "",
    [string]$QwenApiKey = "",
    [string]$QwenModel = ""
)

$imageUri = "$Region-docker.pkg.dev/$ProjectId/$Repository/$ImageName`:$Tag"

$deployArgs = @(
    "run", "deploy", $ServiceName,
    "--project", $ProjectId,
    "--region", $Region,
    "--platform", "managed",
    "--image", $imageUri,
    "--port", $Port,
    "--memory", $Memory,
    "--cpu", $Cpu,
    "--concurrency", $Concurrency,
    "--timeout", $TimeoutSeconds
)

if ($AllowUnauthenticated.IsPresent) {
    $deployArgs += "--allow-unauthenticated"
} else {
    $deployArgs += "--no-allow-unauthenticated"
}

$envVars = @(
    "ENABLE_LOCAL_QWEN=0",
    "ALLOW_MODEL_DOWNLOAD=0"
)

if ($QwenBaseUrl) { $envVars += "QWEN_OPENAI_COMPATIBLE_BASE_URL=$QwenBaseUrl" }
if ($QwenApiKey) { $envVars += "QWEN_OPENAI_COMPATIBLE_API_KEY=$QwenApiKey" }
if ($QwenModel) { $envVars += "QWEN_OPENAI_COMPATIBLE_MODEL=$QwenModel" }

if ($envVars.Count -gt 0) {
    $deployArgs += @("--set-env-vars", ($envVars -join ","))
}

& gcloud @deployArgs
