#!/bin/bash
rsync -avz --delete \
  --exclude '.git' \
  --exclude '.venv' \
  --exclude '.vscode' \
  --exclude '__pycache__' \
  --exclude 'push.sh' \
  --exclude 'pull.sh' \
  --exclude 'docker-compose.yml' \
  --exclude 'results' \
  --exclude 'demo/demo-tpc-c/data/' \
  st1:/home/derhan/styx/ ./

# 2) Aggregate results/ from remote → local (NO delete)
rsync -avz \
  st1:/home/derhan/styx/results/ ./results/