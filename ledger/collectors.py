#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Сбор событий вклада из git-истории.

Git — источник истины. Мы ничего не спрашиваем у контрибьютора:
всё, что можно узнать из истории коммитов, мы узнаём из неё.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass, field, asdict
from typing import Any

SEP = "\x1e"
TRAILER_RE = re.compile(r"^([A-Za-z][A-Za-z0-9-]*):\s*(.+)$")


@dataclass
class Contribution:
    """Сырое (ещё не проверенное) событие вклада."""
    id: str
    kind: str                 # data | model | eval | compute | code | docs
    contributor: str
    email: str
    ts: str
    commit: str
    subject: str
    path: str
    cycle: str
    payload: dict = field(default_factory=dict)
    trailers: dict = field(default_factory=dict)
    meta: dict = field(default_factory=dict)
    sig: str = "N"            # статус подписи git (%G?)
    key: str = ""             # отпечаток ключа (%GK), если подпись есть

    def to_dict(self) -> dict:
        return asdict(self)


def _git(repo: str, *args: str) -> str:
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"git {args} failed: {r.stderr.strip()}")
    return r.stdout


def _classify(path: str, cfg) -> str | None:
    g = cfg.raw["git"]
    for key, kind in (("data_paths", "data"), ("model_paths", "model"),
                      ("eval_paths", "eval"), ("compute_paths", "compute")):
        for pref in g.get(key, []):
            if path.startswith(pref):
                return kind
    for pref in g.get("subjective_paths", []):
        if path.startswith(pref):
            return "docs" if (pref.startswith("docs") or path.endswith(".md")) else "code"
    return None


def _trailers(body: str) -> dict:
    out: dict[str, str] = {}
    for line in body.splitlines():
        m = TRAILER_RE.match(line.strip())
        if m:
            out[m.group(1).lower().replace("-", "_")] = m.group(2).strip()
    return out


def _file_at(repo: str, commit: str, path: str) -> str | None:
    try:
        return _git(repo, "show", f"{commit}:{path}")
    except RuntimeError:
        return None


def _numstat(repo: str, commit: str) -> dict[str, tuple[int, int]]:
    """{path: (added, deleted)} для коммита."""
    out: dict[str, tuple[int, int]] = {}
    for line in _git(repo, "show", "--numstat", "--format=", commit).splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        a, d, p = parts
        try:
            out[p] = (int(a), int(d))
        except ValueError:
            out[p] = (0, 0)
    return out


# Поля, в которых разметчик пишет ответ. Человеку яснее «human_cpv»,
# чем «completion», поэтому схема задания называет вещи по-человечески,
# а к канону приводит их этот маппинг. Иначе вернувшийся файл не прошёл
# бы проверку схемы и работа пропала бы зря.
ANNOTATION_FIELDS = {"title": "prompt", "human_cpv": "completion"}


def _normalize_annotation(obj: dict) -> dict:
    out = dict(obj)
    for src, dst in ANNOTATION_FIELDS.items():
        if src in obj and dst not in out:
            v = obj[src]
            out[dst] = "" if v is None else str(v)
    return out


def _load_data(text: str) -> list[dict]:
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            rows.append(_normalize_annotation(obj))
    return rows


def collect(repo: str, cfg, since: str | None = None,
            rng: str | None = None) -> list[Contribution]:
    """Собирает все события вклада из истории репозитория (детерминированно)."""
    # %G? — статус подписи (G/B/U/X/Y/R/E/N), %GK — отпечаток ключа.
    # Без этого атрибуция держится на полях author, которые подделываются
    # одной строкой: git -c user.name="..." commit
    fmt = "%H%x1f%an%x1f%ae%x1f%aI%x1f%G?%x1f%GK%x1f%s%x1f%b%x1e"
    args = ["log", "--reverse", f"--pretty=format:{fmt}"]
    if since:
        args.append(f"--since={since}")
    if rng:
        args.append(rng)
    raw = _git(repo, *args)

    contribs: list[Contribution] = []
    for block in raw.split(SEP):
        block = block.strip("\n")
        if not block.strip():
            continue
        parts = block.split("\x1f")
        if len(parts) != 8:
            continue
        sha, name, email, ts, sig_status, sig_key, subject, body = parts
        trailers = _trailers(body)
        stat = _numstat(repo, sha)

        for path, (added, deleted) in sorted(stat.items()):
            forced = trailers.get("contribution_type")
            kind = (forced or _classify(path, cfg) or "").lower()
            if kind not in {"data", "model", "eval", "compute", "code", "docs"}:
                continue

            payload: dict[str, Any] = {}
            if kind == "data":
                text = _file_at(repo, sha, path)
                payload = {"records": _load_data(text or ""), "file": path}
            elif kind in {"model", "eval", "compute"}:
                text = _file_at(repo, sha, path)
                try:
                    payload = json.loads(text) if text else {}
                except json.JSONDecodeError:
                    payload = {}
                payload["file"] = path
            else:
                payload = {"added": added, "deleted": deleted, "file": path}

            cid = hashlib.sha256(f"{sha}|{path}".encode()).hexdigest()[:16]
            cycle = ts[:7]
            contribs.append(Contribution(
                id=cid, kind=kind, contributor=name, email=email.lower(),
                ts=ts, commit=sha, subject=subject, path=path, cycle=cycle,
                payload=payload, trailers=trailers,
                meta={"added": added, "deleted": deleted},
                sig=(sig_status or "N").strip() or "N",
                key=(sig_key or "").strip(),
            ))

    contribs.sort(key=lambda c: (c.ts, c.commit, c.path))
    return contribs
