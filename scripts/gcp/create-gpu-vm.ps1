Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectId,
    [string]$Zone = "asia-northeast3-b",
    [string]$InstanceName = "mulmumu-qwen-gpu",
    [string]$MachineType = "g2-standard-8",
    [string]$GpuType = "nvidia-l4",
    [int]$GpuCount = 1,
    [string]$BootDiskSize = "200GB",
    [string]$ImageFamily = "common-cu128-ubuntu-2204-nvidia-570",
    [string]$ImageProject = "deeplearning-platform-release"
)

$args = @(
    "compute", "instances", "create", $InstanceName,
    "--project", $ProjectId,
    "--zone", $Zone,
    "--machine-type", $MachineType,
    "--maintenance-policy", "TERMINATE",
    "--accelerator", "type=$GpuType,count=$GpuCount",
    "--boot-disk-size", $BootDiskSize,
    "--image-family", $ImageFamily,
    "--image-project", $ImageProject,
    "--metadata", "install-nvidia-driver=True"
)

& gcloud @args

Write-Host ""
Write-Host "VM created. Next recommended steps:"
Write-Host "1. gcloud compute ssh $InstanceName --project $ProjectId --zone $Zone"
Write-Host "2. Install or verify Docker on the VM."
Write-Host "3. Authenticate Artifact Registry and run the GPU container there."
