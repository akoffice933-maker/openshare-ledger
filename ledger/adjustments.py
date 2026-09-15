#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Корректировки: решения по спорам.

Отдельная append-only цепочка, а не правки в entries.jsonl. Причина
в одном: contributions целиком выводятся из git и потому воспроизводимы
пересчётом. Решение по спору — человеческое решение, его пересчитать
нельзя. Смешать их — значит потерять свойство «пересчёт даёт тот же
результат», ради которого всё и затевалось.

Поэтому:

    entries.jsonl      воспроизводимо из git, пересчитывается
    adjustments.jsonl  решения людей, не пересчитывается, но проверяется
    итог               contributions + adjustments

Корректировка не удаляет и не меняет запись. Она добавляет дельту.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone

from .store import GENESIS, canon

# Решение по спору: спор удовлетворён полностью, частично или отклонён.
DECISIONS = ("upheld", "partial", "rejected")
CONTEST_DAYS = 14

FILENAME = "adjustments.jsonl"


class Adjustments:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.entries: list[dict] = []
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        self.entries.append(json.loads(line))

    @classmethod
    def for_config(cls, cfg) -> "Adjustments":
        return cls(os.path.join(cfg.path("state_dir"), FILENAME))

    def append(self, entry_id: str, delta: float, decision: str,
               reason: str, cycle: str, actor: str,
               ts: str | None = None) -> dict:
        if decision not in DECISIONS:
            raise ValueError(
                f"неизвестное решение: {decision} (допустимо {', '.join(DECISIONS)})")
        if not reason.strip():
            raise ValueError("решение без обоснования: спор нельзя закрыть молча")
        if not entry_id:
            raise ValueError("не указана запись, к которой относится спор")

        prev = self.entries[-1]["hash"] if self.entries else GENESIS
        body = {
            "seq": len(self.entries),
            "ts": ts or datetime.now(timezone.utc).isoformat(),
            "cycle": cycle,
            "entry_id": entry_id,
            "delta": round(float(delta), 2),
            "decision": decision,
            "reason": reason.strip(),
            "actor": actor,
            "prev": prev,
        }
        body["hash"] = hashlib.sha256(canon(body).encode("utf-8")).hexdigest()
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(canon(body) + "\n")
        self.entries.append(body)
        return body

    def verify(self) -> tuple[bool, str]:
        prev = GENESIS
        for i, e in enumerate(self.entries):
            payload = {k: e[k] for k in ("seq", "ts", "cycle", "entry_id",
                                         "delta", "decision", "reason",
                                         "actor", "prev")}
            if e["seq"] != i:
                return False, f"нарушена нумерация: позиция {i}, seq={e['seq']}"
            if e["prev"] != prev:
                return False, f"разрыв цепочки корректировок на записи {i}"
            if hashlib.sha256(canon(payload).encode("utf-8")).hexdigest() != e["hash"]:
                return False, f"хеш корректировки {i} не совпадает с содержимым"
            prev = e["hash"]
        return True, f"цепочка корректировок цела: {len(self.entries)} записей"

    @property
    def head(self) -> str:
        return self.entries[-1]["hash"] if self.entries else GENESIS

    def for_cycle(self, cycle: str) -> list[dict]:
        return [e for e in self.entries if e["cycle"] == cycle]

    def sum_for_cycle(self, cycle: str) -> float:
        return round(sum(e["delta"] for e in self.for_cycle(cycle)), 2)

    def total(self) -> float:
        return round(sum(e["delta"] for e in self.entries), 2)

    def by_entry(self, entry_id: str) -> list[dict]:
        return [e for e in self.entries if e["entry_id"] == entry_id]
