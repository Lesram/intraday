#!/bin/bash
#
# Chaos Testing Script - Pod/Container Killer
#
# Simulates infrastructure failures during load testing by killing pods/containers
# Supports both Kubernetes and Docker Compose environments
#
# Usage:
#   ./kill_pod.sh --help
#   ./kill_pod.sh --k8s --namespace trading-platform --service api
#   ./kill_pod.sh --docker --compose-file docker-compose.yml --service api
#

set -euo pipefail

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
MODE=""
NAMESPACE="default"
SERVICE=""
COMPOSE_FILE="docker-compose.yml"
INTERVAL=30
COUNT=3
DRY_RUN=false

# Logging function
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Help function
show_help() {
    cat << EOF
Chaos Testing Script - Pod/Container Killer

USAGE:
    $0 [OPTIONS]

OPTIONS:
    --k8s                    Use Kubernetes mode
    --docker                 Use Docker Compose mode
    --namespace NAMESPACE    Kubernetes namespace (default: default)
    --service SERVICE        Service name to target
    --compose-file FILE      Docker compose file (default: docker-compose.yml)
    --interval SECONDS       Interval between kills (default: 30)
    --count NUMBER           Number of kill cycles (default: 3)
    --dry-run               Show what would be done without executing
    --help                  Show this help

EXAMPLES:
    # Kill Kubernetes pods
    $0 --k8s --namespace trading-platform --service api-server --interval 45 --count 5
    
    # Kill Docker containers  
    $0 --docker --compose-file docker-compose.yml --service api --interval 60
    
    # Dry run to see what would happen
    $0 --k8s --namespace staging --service api --dry-run

ENVIRONMENT VARIABLES:
    CHAOS_INTERVAL          Override default interval
    CHAOS_COUNT            Override default count
    CHAOS_NAMESPACE        Override default namespace
    CHAOS_SERVICE          Override service name

EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --k8s)
            MODE="k8s"
            shift
            ;;
        --docker)
            MODE="docker"
            shift
            ;;
        --namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        --service)
            SERVICE="$2"
            shift 2
            ;;
        --compose-file)
            COMPOSE_FILE="$2"
            shift 2
            ;;
        --interval)
            INTERVAL="$2"
            shift 2
            ;;
        --count)
            COUNT="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --help)
            show_help
            exit 0
            ;;
        *)
            error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Override from environment variables
INTERVAL=${CHAOS_INTERVAL:-$INTERVAL}
COUNT=${CHAOS_COUNT:-$COUNT}
NAMESPACE=${CHAOS_NAMESPACE:-$NAMESPACE}
SERVICE=${CHAOS_SERVICE:-$SERVICE}

# Validate required parameters
if [[ -z "$MODE" ]]; then
    error "Must specify either --k8s or --docker mode"
    show_help
    exit 1
fi

if [[ -z "$SERVICE" ]]; then
    error "Must specify --service parameter"
    show_help
    exit 1
fi

# Kubernetes functions
k8s_check_dependencies() {
    if ! command -v kubectl &> /dev/null; then
        error "kubectl is required for Kubernetes mode"
        exit 1
    fi
    
    # Check cluster connectivity
    if ! kubectl cluster-info &> /dev/null; then
        error "Unable to connect to Kubernetes cluster"
        exit 1
    fi
    
    success "Kubernetes cluster connectivity verified"
}

k8s_get_pods() {
    local pods
    pods=$(kubectl get pods -n "$NAMESPACE" -l app="$SERVICE" -o jsonpath='{.items[*].metadata.name}' 2>/dev/null || echo "")
    
    if [[ -z "$pods" ]]; then
        # Try alternative label selectors
        pods=$(kubectl get pods -n "$NAMESPACE" -l service="$SERVICE" -o jsonpath='{.items[*].metadata.name}' 2>/dev/null || echo "")
    fi
    
    if [[ -z "$pods" ]]; then
        # Try name pattern matching
        pods=$(kubectl get pods -n "$NAMESPACE" --field-selector=status.phase=Running -o name | grep "$SERVICE" | sed 's/pod\///' || echo "")
    fi
    
    echo "$pods"
}

k8s_kill_pod() {
    local pods
    pods=$(k8s_get_pods)
    
    if [[ -z "$pods" ]]; then
        warning "No running pods found for service '$SERVICE' in namespace '$NAMESPACE'"
        return 1
    fi
    
    # Select random pod if multiple exist
    local pod_array=($pods)
    local target_pod="${pod_array[$RANDOM % ${#pod_array[@]}]}"
    
    log "Targeting pod: $target_pod"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log "[DRY RUN] Would delete pod: $target_pod"
        return 0
    fi
    
    # Kill the pod
    if kubectl delete pod "$target_pod" -n "$NAMESPACE" --grace-period=0 --force; then
        success "Killed pod: $target_pod"
        
        # Wait for replacement pod to start
        log "Waiting for replacement pod to start..."
        local timeout=60
        local elapsed=0
        
        while [[ $elapsed -lt $timeout ]]; do
            local new_pods
            new_pods=$(k8s_get_pods)
            local new_pod_count=$(echo "$new_pods" | wc -w)
            
            if [[ $new_pod_count -gt 0 ]]; then
                success "Replacement pod(s) detected: $new_pods"
                return 0
            fi
            
            sleep 5
            elapsed=$((elapsed + 5))
        done
        
        warning "Replacement pod not detected within ${timeout}s"
    else
        error "Failed to kill pod: $target_pod"
        return 1
    fi
}

# Docker functions  
docker_check_dependencies() {
    if ! command -v docker &> /dev/null; then
        error "Docker is required for Docker mode"
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        error "docker-compose or docker compose is required for Docker mode"
        exit 1
    fi
    
    # Check if compose file exists
    if [[ ! -f "$COMPOSE_FILE" ]]; then
        error "Compose file not found: $COMPOSE_FILE"
        exit 1
    fi
    
    success "Docker and compose tools verified"
}

docker_get_containers() {
    local containers
    
    # Try docker-compose first, then docker compose
    if command -v docker-compose &> /dev/null; then
        containers=$(docker-compose -f "$COMPOSE_FILE" ps -q "$SERVICE" 2>/dev/null || echo "")
    else
        containers=$(docker compose -f "$COMPOSE_FILE" ps -q "$SERVICE" 2>/dev/null || echo "")
    fi
    
    echo "$containers"
}

docker_kill_container() {
    local containers
    containers=$(docker_get_containers)
    
    if [[ -z "$containers" ]]; then
        warning "No running containers found for service '$SERVICE'"
        return 1
    fi
    
    # Select random container if multiple exist
    local container_array=($containers)
    local target_container="${container_array[$RANDOM % ${#container_array[@]}]}"
    
    # Get container name for logging
    local container_name
    container_name=$(docker inspect --format='{{.Name}}' "$target_container" 2>/dev/null | sed 's/^\//' || echo "$target_container")
    
    log "Targeting container: $container_name ($target_container)"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log "[DRY RUN] Would restart container: $container_name"
        return 0
    fi
    
    # Restart the container (kill + start)
    if docker restart "$target_container" &> /dev/null; then
        success "Restarted container: $container_name"
        
        # Verify it's back up
        sleep 5
        if docker ps -q --filter "id=$target_container" --filter "status=running" | grep -q "$target_container"; then
            success "Container $container_name is running again"
        else
            warning "Container $container_name may not be running properly"
        fi
    else
        error "Failed to restart container: $container_name"
        return 1
    fi
}

# Main chaos loop
run_chaos_test() {
    log "Starting chaos testing..."
    log "Mode: $MODE"
    log "Service: $SERVICE"
    log "Interval: ${INTERVAL}s"
    log "Count: $COUNT"
    
    if [[ "$MODE" == "k8s" ]]; then
        log "Namespace: $NAMESPACE"
    else
        log "Compose file: $COMPOSE_FILE"
    fi
    
    if [[ "$DRY_RUN" == "true" ]]; then
        warning "DRY RUN MODE - No actual changes will be made"
    fi
    
    local success_count=0
    local failure_count=0
    
    for ((i=1; i<=COUNT; i++)); do
        log "=== Chaos iteration $i/$COUNT ==="
        
        local result=0
        if [[ "$MODE" == "k8s" ]]; then
            k8s_kill_pod || result=$?
        else
            docker_kill_container || result=$?
        fi
        
        if [[ $result -eq 0 ]]; then
            ((success_count++))
        else
            ((failure_count++))
        fi
        
        # Wait before next iteration (unless it's the last one)
        if [[ $i -lt $COUNT ]]; then
            log "Waiting ${INTERVAL}s before next iteration..."
            sleep "$INTERVAL"
        fi
    done
    
    log "=== Chaos testing completed ==="
    success "Successful chaos actions: $success_count"
    if [[ $failure_count -gt 0 ]]; then
        warning "Failed chaos actions: $failure_count"
    fi
    
    # Return non-zero if any failures occurred
    [[ $failure_count -eq 0 ]]
}

# Main execution
main() {
    log "Chaos Testing Script Starting..."
    
    # Check dependencies based on mode
    if [[ "$MODE" == "k8s" ]]; then
        k8s_check_dependencies
    else
        docker_check_dependencies
    fi
    
    # Run the chaos test
    if run_chaos_test; then
        success "Chaos testing completed successfully"
        exit 0
    else
        error "Chaos testing completed with failures"
        exit 1
    fi
}

# Trap signals for cleanup
trap 'error "Chaos testing interrupted"; exit 130' INT TERM

# Run main function
main "$@"