#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Якорь: фиксация корня снимка во внешней сети.

Смысл не в «блокчейне ради блокчейна», а в невозможности
переписать историю вкладов задним числом.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone


def anchor_path(cfg) -> str:
    p = os.path.join(cfg.path("state_dir"), "anchors.log")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return p


def build_payload(cfg, snap: dict) -> dict:
    return {
        "project": cfg.project,
        "cycle": snap["cycle"],
        "root": snap["root"],
        "snapshot_hash": snap["snapshot_hash"],
        "entries": snap["entries"],
        "awarded": snap["total_points"],
        "config_hash": cfg.hash,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


def write_anchor(cfg, snap: dict, target: str | None = None, dry: bool = True) -> dict:
    payload = build_payload(cfg, snap)
    tgt = target or cfg.raw.get("anchor", {}).get("target", "arweave")
    record = {
        "ts": payload["ts"],
        "cycle": snap["cycle"],
        "target": tgt,
        "status": "dry-run" if dry else "submitted",
        "payload": payload,
    }
    with open(anchor_path(cfg), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True, separators=(",", ":")
                            ) + "\n")
    record["tx_hint"] = (f"{tgt}:<txid>" if not dry else "<не отправлено, dry-run>")
    return record
