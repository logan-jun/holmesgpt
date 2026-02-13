#!/usr/bin/env bash
#
# HolmesGPT Air-Gapped Build Script
# Builds Docker image, runs Trivy vulnerability scan, auto-patches, and exports tar.
#
# Usage:
#   ./build.sh                    # Build + scan + export tar
#   ./build.sh --push             # Build + scan + push to registry
#   ./build.sh --skip-scan        # Build only, skip Trivy scan
#
# Environment Variables:
#   REGISTRY        - Container registry (default: holmesgpt)
#   IMAGE_NAME      - Image name (default: holmesgpt-airgap)
#   IMAGE_TAG       - Image tag (default: latest)
#   TRIVY_SEVERITY  - Trivy severity levels (default: HIGH,CRITICAL)
#   TARGETPLATFORM  - Build platform (default: linux/amd64)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Configurable variables
REGISTRY="${REGISTRY:-holmesgpt}"
IMAGE_NAME="${IMAGE_NAME:-holmesgpt-airgap}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
TRIVY_SEVERITY="${TRIVY_SEVERITY:-HIGH,CRITICAL}"
TARGETPLATFORM="${TARGETPLATFORM:-linux/amd64}"
DOCKERFILE="${SCRIPT_DIR}/Dockerfile.airgap"

FULL_IMAGE="${REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}"
REPORT_DIR="${SCRIPT_DIR}"
TRIVY_JSON="${REPORT_DIR}/trivy-report.json"
TRIVY_TABLE="${REPORT_DIR}/trivy-report.txt"

# Parse arguments
PUSH=false
SKIP_SCAN=false
for arg in "$@"; do
  case "$arg" in
    --push) PUSH=true ;;
    --skip-scan) SKIP_SCAN=true ;;
    --help|-h)
      echo "Usage: $0 [--push] [--skip-scan]"
      echo ""
      echo "Options:"
      echo "  --push        Push image to registry after build"
      echo "  --skip-scan   Skip Trivy vulnerability scan"
      echo ""
      echo "Environment Variables:"
      echo "  REGISTRY        Container registry (default: holmesgpt)"
      echo "  IMAGE_NAME      Image name (default: holmesgpt-airgap)"
      echo "  IMAGE_TAG       Image tag (default: latest)"
      echo "  TRIVY_SEVERITY  Severity levels (default: HIGH,CRITICAL)"
      echo "  TARGETPLATFORM  Build platform (default: linux/amd64)"
      exit 0
      ;;
  esac
done

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
err() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $*" >&2; }

check_prerequisites() {
  local missing=()
  command -v docker >/dev/null 2>&1 || missing+=("docker")

  if [ "$SKIP_SCAN" = false ]; then
    command -v trivy >/dev/null 2>&1 || missing+=("trivy")
  fi

  if [ ${#missing[@]} -gt 0 ]; then
    err "Missing required tools: ${missing[*]}"
    err "Install them before running this script."
    exit 1
  fi
}

build_image() {
  local dockerfile="$1"
  log "Building image: ${FULL_IMAGE}"
  log "Dockerfile: ${dockerfile}"
  log "Context: ${PROJECT_ROOT}"
  log "Platform: ${TARGETPLATFORM}"

  docker build \
    -t "${FULL_IMAGE}" \
    -f "${dockerfile}" \
    --build-arg TARGETPLATFORM="${TARGETPLATFORM}" \
    "${PROJECT_ROOT}"

  log "Build complete: ${FULL_IMAGE}"
}

run_trivy_scan() {
  local scan_label="$1"
  log "Running Trivy scan (${scan_label})..."

  # JSON report
  trivy image \
    --severity "${TRIVY_SEVERITY}" \
    --format json \
    --output "${TRIVY_JSON}" \
    "${FULL_IMAGE}" 2>/dev/null || true

  # Table report
  trivy image \
    --severity "${TRIVY_SEVERITY}" \
    --format table \
    --output "${TRIVY_TABLE}" \
    "${FULL_IMAGE}" 2>/dev/null || true

  # Count vulnerabilities
  local vuln_count=0
  if [ -f "${TRIVY_JSON}" ]; then
    vuln_count=$(python3 -c "
import json, sys
try:
    data = json.load(open('${TRIVY_JSON}'))
    results = data.get('Results', [])
    total = sum(len(r.get('Vulnerabilities', [])) for r in results)
    print(total)
except:
    print(0)
" 2>/dev/null || echo "0")
  fi

  # Print report to stderr so stdout only contains the count
  log "Trivy scan complete (${scan_label}): ${vuln_count} vulnerabilities found"

  if [ -f "${TRIVY_TABLE}" ]; then
    {
      echo ""
      echo "=== Trivy Scan Report (${scan_label}) ==="
      cat "${TRIVY_TABLE}"
      echo "=== End Report ==="
      echo ""
    } >&2
  fi

  # Return only the count via stdout (captured by caller)
  echo "${vuln_count}"
}

extract_patches() {
  # Extract vulnerable OS and Python packages from Trivy JSON report
  log "Analyzing vulnerabilities for auto-patch..."

  python3 - "${TRIVY_JSON}" <<'PYEOF'
import json, sys

report_path = sys.argv[1]
with open(report_path) as f:
    data = json.load(f)

os_packages = set()
pip_packages = set()

for result in data.get("Results", []):
    target_type = result.get("Type", "")
    for vuln in result.get("Vulnerabilities", []):
        pkg = vuln.get("PkgName", "")
        fixed = vuln.get("FixedVersion", "")
        if not pkg or not fixed:
            continue
        if target_type in ("debian", "ubuntu", "alpine", "redhat", "amazon"):
            os_packages.add(pkg)
        elif target_type == "pip" or "python" in target_type.lower():
            pip_packages.add(f"{pkg}>={fixed}")

if os_packages:
    with open("/tmp/airgap_os_patches.txt", "w") as f:
        f.write(" ".join(sorted(os_packages)))
    print(f"OS packages to patch: {', '.join(sorted(os_packages))}")

if pip_packages:
    with open("/tmp/airgap_pip_patches.txt", "w") as f:
        f.write(" ".join(sorted(pip_packages)))
    print(f"Python packages to patch: {', '.join(sorted(pip_packages))}")

if not os_packages and not pip_packages:
    print("No auto-patchable vulnerabilities found.")
PYEOF
}

apply_patches_and_rebuild() {
  log "Applying patches and rebuilding..."

  local patch_commands=""

  if [ -f /tmp/airgap_os_patches.txt ]; then
    local os_pkgs
    os_pkgs=$(cat /tmp/airgap_os_patches.txt)
    patch_commands="${patch_commands}RUN apt-get update && apt-get install -y --only-upgrade ${os_pkgs} && rm -rf /var/lib/apt/lists/*\n"
  fi

  if [ -f /tmp/airgap_pip_patches.txt ]; then
    local pip_pkgs
    pip_pkgs=$(cat /tmp/airgap_pip_patches.txt)
    patch_commands="${patch_commands}RUN pip install --no-cache-dir ${pip_pkgs}\n"
  fi

  if [ -z "${patch_commands}" ]; then
    log "No patches to apply."
    return 0
  fi

  # Create patched Dockerfile by appending patch layers before ENTRYPOINT
  local patched_dockerfile="${SCRIPT_DIR}/Dockerfile.airgap.patched"
  sed '/^ENTRYPOINT/i\
# === Auto-applied security patches ===' "${DOCKERFILE}" > "${patched_dockerfile}"

  # Insert patch commands before ENTRYPOINT
  local escaped_patches
  escaped_patches=$(echo -e "${patch_commands}" | sed 's/[&/\]/\\&/g')
  sed -i.bak "s|# === Auto-applied security patches ===|# === Auto-applied security patches ===\n${escaped_patches}|" "${patched_dockerfile}"
  rm -f "${patched_dockerfile}.bak"

  log "Patched Dockerfile created: ${patched_dockerfile}"
  build_image "${patched_dockerfile}"

  # Cleanup
  rm -f "${patched_dockerfile}"
  rm -f /tmp/airgap_os_patches.txt /tmp/airgap_pip_patches.txt
}

export_tar() {
  local tar_file="${REPORT_DIR}/${IMAGE_NAME}-${IMAGE_TAG}.tar"
  log "Exporting image to: ${tar_file}"
  docker save -o "${tar_file}" "${FULL_IMAGE}"
  log "Export complete: ${tar_file} ($(du -h "${tar_file}" | cut -f1))"
}

push_image() {
  log "Pushing image: ${FULL_IMAGE}"
  docker push "${FULL_IMAGE}"
  log "Push complete: ${FULL_IMAGE}"
}

main() {
  log "=== HolmesGPT Air-Gapped Build ==="
  log "Image: ${FULL_IMAGE}"

  check_prerequisites

  # 1st build
  build_image "${DOCKERFILE}"

  if [ "$SKIP_SCAN" = true ]; then
    log "Trivy scan skipped (--skip-scan)"
  else
    # 1st scan
    vuln_count=$(run_trivy_scan "initial")

    if [ "${vuln_count}" -gt 0 ] 2>/dev/null; then
      log "Found ${vuln_count} vulnerabilities. Attempting auto-patch..."
      extract_patches
      apply_patches_and_rebuild

      # 2nd scan
      vuln_count_after=$(run_trivy_scan "post-patch")
      if [ "${vuln_count_after}" -gt 0 ] 2>/dev/null; then
        log "WARNING: ${vuln_count_after} vulnerabilities remain after patching."
        log "Review ${TRIVY_TABLE} for details."
      else
        log "All vulnerabilities resolved."
      fi
    else
      log "No vulnerabilities found. Image is clean."
    fi
  fi

  # Export or push
  if [ "$PUSH" = true ]; then
    push_image
  else
    export_tar
  fi

  log "=== Build Complete ==="
}

main
