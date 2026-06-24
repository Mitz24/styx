#!/bin/bash
set -uo pipefail

echo "Resetting Styx cluster..."
docker compose --profile autoscale down --remove-orphans
docker compose -f docker-compose-kafka.yml down --remove-orphans
docker compose -f docker-compose-s3.yml down --remove-orphans
docker network prune -f
echo "Reset complete."
