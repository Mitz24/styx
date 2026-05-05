#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

COORDINATOR_IMAGE="styx-coordinator"
WORKER_IMAGE="styx-worker"
TAG="dev"

cd "$ROOT_DIR"

echo "Building coordinator and worker images in parallel..."
eval $(minikube docker-env) 

docker build -f coordinator/coordinator.dockerfile -t "${COORDINATOR_IMAGE}:${TAG}" . &
COORDINATOR_PID=$!

docker build -f worker/worker.dockerfile -t "${WORKER_IMAGE}:${TAG}" . &
WORKER_PID=$!

wait $COORDINATOR_PID || { echo "ERROR: coordinator image build failed" >&2; kill $WORKER_PID 2>/dev/null; exit 1; }
wait $WORKER_PID       || { echo "ERROR: worker image build failed" >&2; exit 1; }

echo "Done."
