#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ежемесячный снимок реестра: публикуемая агрегированная картина."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone

from . import config as cfgmod
from .adjustments import Adjustments


def build(cfg, ledger, cycle: str,
          adjustments: Adjustments | None = None) -> dict:
    accounts = ledger.totals()
    ranked = sorted(accounts.values(), key=lambda a: -a["points"])

    # Корректировки не пересчитываются из git, поэтому лежат отдельно.
    # Но их корень попадает в снимок — иначе якорь подтверждал бы только
    # половину итога, а вторую половину можно было бы править незаметно.
    adj_sum = adjustments.sum_for_cycle(cycle) if adjustments else 0.0
    adj_head = adjustments.head if adjustments else "0" * 64
    adj_count = len(adjustments.for_cycle(cycle)) if adjustments else 0

    snap = {
        "project": cfg.project,
        "cycle": cycle,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config_hash": cfg.hash,
        "entries": len(ledger.entries),
        "contributions": len(ledger.contributions()),
        "head": ledger.head,
        "root": ledger.root,
        "total_points": ledger.total_points(),
        "adjustments_points": adj_sum,
        "adjustments_count": adj_count,
        "adjustments_head": adj_head,
        "net_points": round(ledger.total_points() + adj_sum, 2),
        "cycle_points": ledger.cycle_points(cycle),
        "cycle_budget": round(cfgmod.cycle_budget(cfg, cycle), 2),
        "accounts": ranked,
        "contributors": len(ranked),
    }
    snap["snapshot_hash"] = hashlib.sha256(
        json.dumps({k: v for k, v in snap.items() if k != "snapshot_hash"},
                   sort_keys=True, separators=(",", ":"),
                   ensure_ascii=False).encode("utf-8")).hexdigest()
    return snap


def write(cfg, snap: dict) -> tuple[str, str]:
    d = os.path.join(cfg.path("state_dir"), "snapshots")
    os.makedirs(d, exist_ok=True)
    jp = os.path.join(d, f"{snap['cycle']}.json")
    with open(jp, "w", encoding="utf-8") as fh:
        json.dump(snap, fh, ensure_ascii=False, indent=2)

    lines = [
        f"# Реестр вкладов — {snap['project']} · {snap['cycle']}",
        "",
        f"- Сформирован: {snap['generated_at']}",
        f"- Записей в леджере: {snap['entries']} (вкладов: {snap['contributions']})",
        f"- Начислено за цикл: **{snap['cycle_points']}** из бюджета {snap['cycle_budget']}",
        f"- Всего начислено: **{snap['total_points']}**",
        f"- Участников: {snap['contributors']}",
        f"- Корень цепочки: `{snap['root'][:16]}…`",
        f"- Хеш конфигурации: `{snap['config_hash'][:16]}…`",
        "",
        "| Участник | Points | Вкладов | Принято |",
        "|---|---:|---:|---:|",
    ]
    for a in snap["accounts"]:
        lines.append(f"| {a['name']} | {a['points']:.2f} | {a['contributions']} | {a['accepted']} |")
    lines += ["", "_Снимок append-only: изменение возможно только новой записью._", ""]
    mp = os.path.join(d, f"{snap['cycle']}.md")
    with open(mp, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return jp, mp
