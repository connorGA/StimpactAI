#!/usr/bin/env bash

set -euo pipefail

CONFIG_PATH="${1:-infra/eks/cluster.yaml}"

eksctl create cluster -f "${CONFIG_PATH}"
kubectl get nodes
kubectl apply -f infra/kubernetes/namespaces.yaml
