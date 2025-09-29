# Chaos Testing Script - Pod/Container Killer (PowerShell version)
#
# Simulates infrastructure failures during load testing by killing pods/containers
# Supports both Kubernetes and Docker Compose environments on Windows
#
# Usage:
#   .\kill_pod.ps1 -Help
#   .\kill_pod.ps1 -Mode k8s -Namespace trading-platform -Service api
#   .\kill_pod.ps1 -Mode docker -ComposeFile docker-compose.yml -Service api

param(
    [Parameter(Mandatory=$false)]
    [ValidateSet("k8s", "docker")]
    [string]$Mode = "",
    
    [Parameter(Mandatory=$false)]
    [string]$Namespace = "default",
    
    [Parameter(Mandatory=$false)]
    [string]$Service = "",
    
    [Parameter(Mandatory=$false)]
    [string]$ComposeFile = "docker-compose.yml",
    
    [Parameter(Mandatory=$false)]
    [int]$Interval = 30,
    
    [Parameter(Mandatory=$false)]
    [int]$Count = 3,
    
    [Parameter(Mandatory=$false)]
    [switch]$DryRun = $false,
    
    [Parameter(Mandatory=$false)]
    [switch]$Help = $false
)

# Color functions for output
function Write-ColorOutput {
    param(
        [string]$Message,
        [string]$Color = "White"
    )
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "[$timestamp] " -NoNewline
    Write-Host $Message -ForegroundColor $Color
}

function Write-Info { param([string]$Message) Write-ColorOutput $Message "Cyan" }
function Write-Success { param([string]$Message) Write-ColorOutput "[SUCCESS] $Message" "Green" }
function Write-Warning { param([string]$Message) Write-ColorOutput "[WARNING] $Message" "Yellow" }
function Write-Error { param([string]$Message) Write-ColorOutput "[ERROR] $Message" "Red" }

# Help function
function Show-Help {
    Write-Host @"
Chaos Testing Script - Pod/Container Killer (PowerShell)

USAGE:
    .\kill_pod.ps1 [OPTIONS]

OPTIONS:
    -Mode <k8s|docker>      Use Kubernetes or Docker mode
    -Namespace <name>       Kubernetes namespace (default: default)
    -Service <name>         Service name to target
    -ComposeFile <file>     Docker compose file (default: docker-compose.yml)
    -Interval <seconds>     Interval between kills (default: 30)
    -Count <number>         Number of kill cycles (default: 3)
    -DryRun                Show what would be done without executing
    -Help                  Show this help

EXAMPLES:
    # Kill Kubernetes pods
    .\kill_pod.ps1 -Mode k8s -Namespace trading-platform -Service api-server -Interval 45 -Count 5
    
    # Kill Docker containers  
    .\kill_pod.ps1 -Mode docker -ComposeFile docker-compose.yml -Service api -Interval 60
    
    # Dry run to see what would happen
    .\kill_pod.ps1 -Mode k8s -Namespace staging -Service api -DryRun

ENVIRONMENT VARIABLES:
    `$env:CHAOS_INTERVAL          Override default interval
    `$env:CHAOS_COUNT            Override default count
    `$env:CHAOS_NAMESPACE        Override default namespace
    `$env:CHAOS_SERVICE          Override service name

"@
}

# Override from environment variables
if ($env:CHAOS_INTERVAL) { $Interval = [int]$env:CHAOS_INTERVAL }
if ($env:CHAOS_COUNT) { $Count = [int]$env:CHAOS_COUNT }
if ($env:CHAOS_NAMESPACE) { $Namespace = $env:CHAOS_NAMESPACE }
if ($env:CHAOS_SERVICE) { $Service = $env:CHAOS_SERVICE }

# Show help if requested
if ($Help) {
    Show-Help
    exit 0
}

# Validate required parameters
if (-not $Mode) {
    Write-Error "Must specify -Mode parameter (k8s or docker)"
    Show-Help
    exit 1
}

if (-not $Service) {
    Write-Error "Must specify -Service parameter"
    Show-Help
    exit 1
}

# Kubernetes functions
function Test-KubernetesTools {
    try {
        $null = Get-Command kubectl -ErrorAction Stop
        $null = kubectl cluster-info 2>$null
        Write-Success "Kubernetes cluster connectivity verified"
        return $true
    }
    catch {
        Write-Error "kubectl not found or cluster not accessible: $($_.Exception.Message)"
        return $false
    }
}

function Get-KubernetesPods {
    param([string]$Namespace, [string]$Service)
    
    try {
        # Try app label selector first
        $pods = kubectl get pods -n $Namespace -l "app=$Service" -o jsonpath='{.items[*].metadata.name}' 2>$null
        
        if (-not $pods) {
            # Try service label selector
            $pods = kubectl get pods -n $Namespace -l "service=$Service" -o jsonpath='{.items[*].metadata.name}' 2>$null
        }
        
        if (-not $pods) {
            # Try name pattern matching
            $allPods = kubectl get pods -n $Namespace --field-selector=status.phase=Running -o name 2>$null
            $pods = ($allPods | Where-Object { $_ -match $Service } | ForEach-Object { $_ -replace 'pod/', '' }) -join ' '
        }
        
        return $pods.Trim()
    }
    catch {
        Write-Warning "Failed to get pods: $($_.Exception.Message)"
        return ""
    }
}

function Invoke-KubernetesChaos {
    param([string]$Namespace, [string]$Service, [bool]$DryRun)
    
    $pods = Get-KubernetesPods -Namespace $Namespace -Service $Service
    
    if (-not $pods) {
        Write-Warning "No running pods found for service '$Service' in namespace '$Namespace'"
        return $false
    }
    
    # Select random pod if multiple exist
    $podArray = $pods -split '\s+'
    $targetPod = $podArray | Get-Random
    
    Write-Info "Targeting pod: $targetPod"
    
    if ($DryRun) {
        Write-Info "[DRY RUN] Would delete pod: $targetPod"
        return $true
    }
    
    try {
        # Kill the pod
        kubectl delete pod $targetPod -n $Namespace --grace-period=0 --force 2>$null
        Write-Success "Killed pod: $targetPod"
        
        # Wait for replacement pod to start
        Write-Info "Waiting for replacement pod to start..."
        $timeout = 60
        $elapsed = 0
        
        while ($elapsed -lt $timeout) {
            Start-Sleep 5
            $elapsed += 5
            
            $newPods = Get-KubernetesPods -Namespace $Namespace -Service $Service
            if ($newPods) {
                Write-Success "Replacement pod(s) detected: $newPods"
                return $true
            }
        }
        
        Write-Warning "Replacement pod not detected within ${timeout}s"
        return $true
    }
    catch {
        Write-Error "Failed to kill pod: $targetPod - $($_.Exception.Message)"
        return $false
    }
}

# Docker functions
function Test-DockerTools {
    param([string]$ComposeFile)
    
    try {
        $null = Get-Command docker -ErrorAction Stop
        
        # Check for docker-compose or docker compose
        $hasDockerCompose = $false
        try {
            $null = Get-Command docker-compose -ErrorAction Stop
            $hasDockerCompose = $true
        }
        catch {
            try {
                $null = docker compose version 2>$null
                $hasDockerCompose = $true
            }
            catch {
                # Neither available
            }
        }
        
        if (-not $hasDockerCompose) {
            Write-Error "docker-compose or docker compose is required for Docker mode"
            return $false
        }
        
        # Check if compose file exists
        if (-not (Test-Path $ComposeFile)) {
            Write-Error "Compose file not found: $ComposeFile"
            return $false
        }
        
        Write-Success "Docker and compose tools verified"
        return $true
    }
    catch {
        Write-Error "Docker is required for Docker mode: $($_.Exception.Message)"
        return $false
    }
}

function Get-DockerContainers {
    param([string]$ComposeFile, [string]$Service)
    
    try {
        # Try docker-compose first, then docker compose
        $containers = ""
        try {
            $null = Get-Command docker-compose -ErrorAction Stop
            $containers = docker-compose -f $ComposeFile ps -q $Service 2>$null
        }
        catch {
            $containers = docker compose -f $ComposeFile ps -q $Service 2>$null
        }
        
        return ($containers | Where-Object { $_.Trim() -ne "" }) -join ' '
    }
    catch {
        Write-Warning "Failed to get containers: $($_.Exception.Message)"
        return ""
    }
}

function Invoke-DockerChaos {
    param([string]$ComposeFile, [string]$Service, [bool]$DryRun)
    
    $containers = Get-DockerContainers -ComposeFile $ComposeFile -Service $Service
    
    if (-not $containers) {
        Write-Warning "No running containers found for service '$Service'"
        return $false
    }
    
    # Select random container if multiple exist
    $containerArray = $containers -split '\s+'
    $targetContainer = $containerArray | Get-Random
    
    # Get container name for logging
    try {
        $containerName = docker inspect --format='{{.Name}}' $targetContainer 2>$null
        $containerName = $containerName -replace '^/', ''
        if (-not $containerName) { $containerName = $targetContainer }
    }
    catch {
        $containerName = $targetContainer
    }
    
    Write-Info "Targeting container: $containerName ($targetContainer)"
    
    if ($DryRun) {
        Write-Info "[DRY RUN] Would restart container: $containerName"
        return $true
    }
    
    try {
        # Restart the container (kill + start)
        docker restart $targetContainer 2>$null | Out-Null
        Write-Success "Restarted container: $containerName"
        
        # Verify it's back up
        Start-Sleep 5
        $runningCheck = docker ps -q --filter "id=$targetContainer" --filter "status=running" 2>$null
        if ($runningCheck -match $targetContainer) {
            Write-Success "Container $containerName is running again"
        }
        else {
            Write-Warning "Container $containerName may not be running properly"
        }
        
        return $true
    }
    catch {
        Write-Error "Failed to restart container: $containerName - $($_.Exception.Message)"
        return $false
    }
}

# Main chaos loop
function Start-ChaosTest {
    param([string]$Mode, [string]$Namespace, [string]$Service, [string]$ComposeFile, [int]$Interval, [int]$Count, [bool]$DryRun)
    
    Write-Info "Starting chaos testing..."
    Write-Info "Mode: $Mode"
    Write-Info "Service: $Service"
    Write-Info "Interval: ${Interval}s"
    Write-Info "Count: $Count"
    
    if ($Mode -eq "k8s") {
        Write-Info "Namespace: $Namespace"
    }
    else {
        Write-Info "Compose file: $ComposeFile"
    }
    
    if ($DryRun) {
        Write-Warning "DRY RUN MODE - No actual changes will be made"
    }
    
    $successCount = 0
    $failureCount = 0
    
    for ($i = 1; $i -le $Count; $i++) {
        Write-Info "=== Chaos iteration $i/$Count ==="
        
        $result = $false
        if ($Mode -eq "k8s") {
            $result = Invoke-KubernetesChaos -Namespace $Namespace -Service $Service -DryRun $DryRun
        }
        else {
            $result = Invoke-DockerChaos -ComposeFile $ComposeFile -Service $Service -DryRun $DryRun
        }
        
        if ($result) {
            $successCount++
        }
        else {
            $failureCount++
        }
        
        # Wait before next iteration (unless it's the last one)
        if ($i -lt $Count) {
            Write-Info "Waiting ${Interval}s before next iteration..."
            Start-Sleep $Interval
        }
    }
    
    Write-Info "=== Chaos testing completed ==="
    Write-Success "Successful chaos actions: $successCount"
    if ($failureCount -gt 0) {
        Write-Warning "Failed chaos actions: $failureCount"
    }
    
    # Return true if no failures occurred
    return ($failureCount -eq 0)
}

# Main execution
function main {
    Write-Info "Chaos Testing Script Starting..."
    
    # Check dependencies based on mode
    if ($Mode -eq "k8s") {
        if (-not (Test-KubernetesTools)) {
            exit 1
        }
    }
    else {
        if (-not (Test-DockerTools -ComposeFile $ComposeFile)) {
            exit 1
        }
    }
    
    # Run the chaos test
    if (Start-ChaosTest -Mode $Mode -Namespace $Namespace -Service $Service -ComposeFile $ComposeFile -Interval $Interval -Count $Count -DryRun $DryRun) {
        Write-Success "Chaos testing completed successfully"
        exit 0
    }
    else {
        Write-Error "Chaos testing completed with failures"
        exit 1
    }
}

# Handle Ctrl+C gracefully
$null = Register-EngineEvent PowerShell.Exiting -Action {
    Write-Warning "Chaos testing interrupted"
}

# Run main function
main