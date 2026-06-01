#!/usr/bin/env bash
# Coleta os dados e sobe o dashboard localmente em http://localhost:8000
set -e
echo ">> Coletando dados (recalculando metricas)..."
python3 collector/collect.py
echo ">> Subindo servidor local em http://localhost:8000 (Ctrl+C para parar)"
cd site && python3 -m http.server 8000
