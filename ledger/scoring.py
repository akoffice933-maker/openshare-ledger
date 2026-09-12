#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Начисление points: формулы, бюджет цикла, кап проекта.

Экономика защищает ранних контрибьюторов: бюджет цикла затухает,
общий кап зафиксирован заранее, субъективные вклады ограничены долей.
"""
from __future__ import annotations



def raw_points(kind: str, v: Verdict, w: dict) -> float:
    """Базовые points до масштабирования под бюджет цикла."""
    m = v.metrics
    if kind == "data":
        return float(m.get("accepted", 0)) * w["k_data"] * float(m.get("novelty", 0))
    if kind == "model":
        return max(0.0, float(m.get("delta", 0))) * w["k_model"]
    if kind == "eval":
        return float(m.get("confirmed", 0)) * w["k_eval"]
    if kind == "compute":
        return float(m.get("gpu_hours", 0)) * w["k_compute"] * float(m.get("utilization", 0))
    if kind == "code":
        return float(m.get("added", 0)) * w["k_code"]
    if kind == "docs":
        return float(m.get("added", 0)) * w["k_docs"]
    return 0.0


def score_cycle(contribs, cfg, accepted: set[str], heldout: set[str],
                budget: float, cap_remaining: float):
    """Возвращает (entries, новые_хеши_данных).

    entries — список словарей, готовых к записи в леджер.
    """
    from .validators import validate, rhash

    w = {k: cfg.w(k) for k in ("k_data", "k_model", "k_eval", "k_compute", "k_code", "k_docs")}
    subjective_kinds = {"code", "docs"}

    scored: list[dict] = []
    new_hashes: list[str] = []
    hashes_by_id: dict[str, list[str]] = {}

    for c in contribs:
        v = validate(c, cfg, accepted, heldout)
        pts = raw_points(c.kind, v, w) if v.ok else 0.0
        # принятые данные пополняют множество известных хешей
        if v.ok and c.kind == "data":
            taken: list[str] = []
            for rec in c.payload.get("records", []):
                h = rhash(rec)
                if h not in accepted:
                    new_hashes.append(h)
                    accepted.add(h)
                    taken.append(h)
            hashes_by_id[c.id] = taken
        scored.append({
            "id": c.id,
            "type": "contribution",
            "kind": c.kind,
            "contributor": c.contributor,
            "email": c.email,
            "ts": c.ts,
            "commit": c.commit,
            "path": c.path,
            "subject": c.subject,
            "ok": v.ok,
            "reasons": v.reasons,
            "metrics": v.metrics,
            "raw_points": round(pts, 4),
            "points": 0.0,
        })

    # --- разделение бюджета: измеримое против субъективного ---
    meas = [e for e in scored if e["kind"] not in subjective_kinds]
    subj = [e for e in scored if e["kind"] in subjective_kinds]
    share = cfg.subjective_share

    total_budget = min(budget, max(0.0, cap_remaining))
    subj_budget = total_budget * share
    meas_budget = total_budget - subj_budget

    def distribute(entries, pool):
        s = sum(e["raw_points"] for e in entries)
        if s <= 0:
            return
        scale = 1.0 if s <= pool else pool / s
        for e in entries:
            e["scale"] = round(scale, 6)
            e["points"] = round(e["raw_points"] * scale, 2)

    distribute(meas, meas_budget)
    distribute(subj, subj_budget)

    for e in scored:
        if e["kind"] == "data":
            e["record_hashes"] = hashes_by_id.get(e["id"], [])
        e.setdefault("scale", 0.0)
        e["budget"] = round(total_budget, 2)

    return scored, new_hashes
