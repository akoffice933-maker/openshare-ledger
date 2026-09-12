#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Конфигурация реестра и правила эмиссии."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime

DEFAULT_CONFIG = "config.json"


class Config:
    def __init__(self, raw: dict, root: str):
        self.raw = raw
        self.root = root

    # --- доступ ---

    @property
    def project(self) -> str:
        return self.raw.get("project", "OpenShare AI")

    @property
    def project_start(self) -> str:
        return self.raw.get("project_start", "2026-01")

    def w(self, key: str, default: float = 0.0) -> float:
        return float(self.raw.get("weights", {}).get(key, default))

    @property
    def subjective_share(self) -> float:
        return float(self.raw.get("subjective_share", 0.15))

    def em(self, key: str, default=0.0):
        return self.raw.get("emission", {}).get(key, default)

    def val(self, key: str, default=None):
        return self.raw.get("validation", {}).get(key, default)

    def path(self, key: str) -> str:
        return os.path.join(self.root, self.raw["paths"][key])

    def rel(self, *parts: str) -> str:
        return os.path.join(self.root, *parts)

    # --- хеш конфига: попадает в снимок, чтобы правила были проверяемы ---

    @property
    def hash(self) -> str:
        blob = json.dumps(self.raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def load_config(root: str) -> Config:
    with open(os.path.join(root, DEFAULT_CONFIG), encoding="utf-8") as fh:
        raw = json.load(fh)
    return Config(raw, root)


def cycle_index(cycle: str, project_start: str) -> int:
    """Номер цикла от старта проекта: 2026-09 при старте 2026-09 → 0."""
    def to_months(c: str) -> int:
        y, m = c.split("-")
        return int(y) * 12 + int(m)
    return max(0, to_months(cycle) - to_months(project_start))


def cycle_budget(cfg: Config, cycle: str) -> float:
    idx = cycle_index(cycle, cfg.project_start)
    step = idx // int(cfg.em("decay_every", 6))
    base = float(cfg.em("cycle_budget_base", 100000))
    decay = float(cfg.em("decay", 0.85))
    return base * (decay ** step)


def cycles_between(start: str, end: str) -> list[str]:
    def to_months(c: str) -> int:
        y, m = c.split("-")
        return int(y) * 12 + int(m)
    a, b = to_months(start), to_months(end)
    out = []
    for v in range(a, b + 1):
        y, m = divmod(v, 12)
        if m == 0:
            y -= 1
            m = 12
        out.append(f"{y:04d}-{m:02d}")
    return out


def cycle_of(ts: str) -> str:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%Y-%m")
