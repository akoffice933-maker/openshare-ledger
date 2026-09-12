#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Append-only леджер с хеш-цепочкой.

Исправление записи невозможно — только новая запись со ссылкой на
предыдущую. Любое изменение задним числом ломает цепочку, и это
проверяется одной командой.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone

GENESIS = "0" * 64


def canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class Ledger:
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

    # --- запись ---

    def append(self, kind: str, data: dict, ts: str | None = None) -> dict:
        prev = self.entries[-1]["hash"] if self.entries else GENESIS
        body = {
            "seq": len(self.entries),
            "ts": ts or datetime.now(timezone.utc).isoformat(),
            "kind": kind,
            "data": data,
            "prev": prev,
        }
        body["hash"] = hashlib.sha256(canon(body).encode("utf-8")).hexdigest()
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(canon(body) + "\n")
        self.entries.append(body)
        return body

    # --- проверка ---

    def verify(self) -> tuple[bool, str]:
        prev = GENESIS
        for i, e in enumerate(self.entries):
            payload = {k: e[k] for k in ("seq", "ts", "kind", "data", "prev")}
            if e["seq"] != i:
                return False, f"нарушена нумерация: позиция {i}, seq={e['seq']}"
            if e["prev"] != prev:
                return False, f"разрыв цепочки на записи {i}"
            if hashlib.sha256(canon(payload).encode("utf-8")).hexdigest() != e["hash"]:
                return False, f"хеш записи {i} не совпадает с содержимым"
            prev = e["hash"]
        return True, f"цепочка цела: {len(self.entries)} записей"

    @property
    def head(self) -> str:
        return self.entries[-1]["hash"] if self.entries else GENESIS

    @property
    def root(self) -> str:
        """Корень всех записей — то, что уходит в якорь."""
        joined = "".join(e["hash"] for e in self.entries)
        return hashlib.sha256(joined.encode()).hexdigest()

    # --- выборки ---

    def contributions(self) -> list[dict]:
        return [e["data"] for e in self.entries if e["kind"] == "contribution"]

    def cycle_points(self, cycle: str) -> float:
        return round(sum(c["points"] for c in self.contributions()
                         if str(c["ts"])[:7] == cycle), 2)

    def totals(self) -> dict:
        out: dict[str, dict] = {}
        for c in self.contributions():
            acc = out.setdefault(c["email"], {
                "name": c["contributor"], "email": c["email"],
                "points": 0.0, "contributions": 0, "accepted": 0,
                "by_kind": {},
            })
            acc["points"] = round(acc["points"] + c["points"], 2)
            acc["contributions"] += 1
            if c["ok"]:
                acc["accepted"] += 1
            acc["by_kind"][c["kind"]] = round(
                acc["by_kind"].get(c["kind"], 0.0) + c["points"], 2)
        return out

    def accepted_hashes(self) -> set[str]:
        """Хеши всех принятых записей данных — база для дедупликации."""
        out: set[str] = set()
        for c in self.contributions():
            out.update(c.get("record_hashes", []))
        return out

    def total_points(self) -> float:
        return round(sum(c["points"] for c in self.contributions()), 2)

    def reset(self) -> None:
        if os.path.exists(self.path):
            os.remove(self.path)
        self.entries = []
