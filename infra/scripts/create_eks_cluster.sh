#!/usr/bin/env bash

set -euo pipefail

CONFIG_PATH="${1:-infra/eks/cluster.yaml}"
ACKNOWLEDGED="${STIMPACT_ACK_EKS_COSTS:-0}"
AUTO_APPROVE="${2:-}"

readarray -t CONFIG_VALUES < <(
  python3 - "${CONFIG_PATH}" <<'PY'
import re
import sys
from pathlib import Path

config_path = Path(sys.argv[1])
name = ""
region = ""
version = ""
for raw_line in config_path.read_text().splitlines():
    line = raw_line.strip()
    if not name and re.match(r"name:\s*", line):
        name = line.split(":", 1)[1].strip().strip('"')
    elif not region and re.match(r"region:\s*", line):
        region = line.split(":", 1)[1].strip().strip('"')
    elif not version and re.match(r"version:\s*", line):
        version = line.split(":", 1)[1].strip().strip('"')
print(name)
print(region)
print(version)
PY
)

CLUSTER_NAME="${CONFIG_VALUES[0]:-unknown}"
AWS_REGION="${CONFIG_VALUES[1]:-unknown}"
KUBERNETES_VERSION="${CONFIG_VALUES[2]:-unknown}"

cat <<EOF
About to create an EKS cluster with ongoing hourly charges:
  cluster: ${CLUSTER_NAME}
  region: ${AWS_REGION}
  kubernetes version: ${KUBERNETES_VERSION}

This will incur EKS cluster-hours even with no traffic. EC2, EBS, load balancer, and CloudWatch
costs continue until the cluster and its dependencies are deleted.
EOF

if [[ "${ACKNOWLEDGED}" != "1" && "${AUTO_APPROVE}" != "--yes" ]]; then
  cat <<'EOF'
Refusing to create the cluster without explicit acknowledgement.

Re-run with one of:
  STIMPACT_ACK_EKS_COSTS=1 ./infra/scripts/create_eks_cluster.sh
  ./infra/scripts/create_eks_cluster.sh infra/eks/cluster.yaml --yes
EOF
  exit 1
fi

eksctl create cluster -f "${CONFIG_PATH}"
kubectl get nodes
kubectl apply -f infra/kubernetes/namespaces.yaml
