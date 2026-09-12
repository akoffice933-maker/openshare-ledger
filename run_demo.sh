#!/usr/bin/env bash
# Полный прогон демо-сценария с чистого листа.
set -euo pipefail
cd "$(dirname "$0")"

rm -rf state demo/repo report.html

echo "=== init ==="
python3 -m ledger init

echo
echo "=== held-out сет (приватный) ==="
python3 -m ledger heldout --file private/golden.jsonl

echo
echo "=== демо-репозиторий ==="
python3 tools/make_demo_repo.py

echo
echo "=== collect ==="
python3 -m ledger collect --repo demo/repo

echo
echo "=== score ==="
python3 -m ledger score --repo demo/repo --cycle 2026-09

echo
echo "=== status ==="
python3 -m ledger status

echo
echo "=== verify + recompute ==="
python3 -m ledger verify --repo demo/repo --recompute --cycle 2026-09

echo
echo "=== selftest ==="
python3 -m ledger selftest

echo
echo "Готово: report.html, state/entries.jsonl, state/snapshots/, state/anchors.log"
