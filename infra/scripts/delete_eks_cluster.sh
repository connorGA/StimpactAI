#!/usr/bin/env bash

set -euo pipefail

CONFIG_PATH="${1:-infra/eks/cluster.yaml}"
ACKNOWLEDGED="${STIMPACT_ACK_EKS_DELETE:-0}"
AUTO_APPROVE="${2:-}"

readarray -t CONFIG_VALUES < <(
  python3 - "${CONFIG_PATH}" <<'PY'
import re
import sys
from pathlib import Path

config_path = Path(sys.argv[1])
name = ""
region = ""
for raw_line in config_path.read_text().splitlines():
    line = raw_line.strip()
    if not name and re.match(r"name:\s*", line):
        name = line.split(":", 1)[1].strip().strip('"')
    elif not region and re.match(r"region:\s*", line):
        region = line.split(":", 1)[1].strip().strip('"')
print(name)
print(region)
PY
)

CLUSTER_NAME="${CONFIG_VALUES[0]:-}"
AWS_REGION="${CONFIG_VALUES[1]:-}"

if [[ -z "${CLUSTER_NAME}" || -z "${AWS_REGION}" ]]; then
  echo "Unable to determine cluster name/region from ${CONFIG_PATH}."
  exit 1
fi

cat <<EOF
About to delete the EKS cluster and managed node groups:
  cluster: ${CLUSTER_NAME}
  region: ${AWS_REGION}

Review and manually clean up any leftover AWS resources that are not always deleted automatically,
including load balancers, EBS volumes, CloudWatch log groups, and NAT gateways.
EOF

if [[ "${ACKNOWLEDGED}" != "1" && "${AUTO_APPROVE}" != "--yes" ]]; then
  cat <<'EOF'
Refusing to delete the cluster without explicit acknowledgement.

Re-run with one of:
  STIMPACT_ACK_EKS_DELETE=1 ./infra/scripts/delete_eks_cluster.sh
  ./infra/scripts/delete_eks_cluster.sh infra/eks/cluster.yaml --yes
EOF
  exit 1
fi

eksctl delete cluster --name "${CLUSTER_NAME}" --region "${AWS_REGION}" --wait
