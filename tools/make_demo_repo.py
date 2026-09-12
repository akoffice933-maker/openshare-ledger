#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Создаёт демо-репозиторий с реалистичной историей вкладов.

В истории намеренно заложены атаки, с которыми сталкивается любой
реестр вкладов: сибил-дамп, контаминация тестового сета,
персональные данные, поддельный proof, «улучшение» не на том сете.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.join(ROOT, "demo", "repo")
PRIVATE = os.path.join(ROOT, "private")

PEOPLE = [
    ("Anna Kowalski", "anna@example.org"),
    ("Dmitri Volkov", "dmitri@example.net"),
    ("Sofia Marin", "sofia@example.com"),
    ("Ivan Petrov", "ivan@example.io"),
    ("Elena Novak", "elena@example.dev"),
    ("Spam Bot", "spam@example.ru"),
]


def run(cmd, cwd=None, env=None):
    e = dict(os.environ)
    if env:
        e.update(env)
    r = subprocess.run(cmd, cwd=cwd, env=e, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"FAILED {cmd}\n{r.stdout}\n{r.stderr}")
    return r.stdout


def rec(i, tag="clause"):
    return {
        "prompt": f"Клауза {tag} №{i}: определить порядок поставки и приёмки.",
        "completion": f"Поставка осуществляется партиями в течение {10 + i} рабочих дней. "
                      f"Приёмка оформляется актом по форме ТОРГ-12.",
    }


def write_jsonl(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def main() -> int:
    ds_hash = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8")
                        )["validation"]["heldout_dataset_hash"]
    golden = [json.loads(l) for l in open(
        os.path.join(PRIVATE, "golden.jsonl"), encoding="utf-8") if l.strip()]
    print(f"held-out: {len(golden)} записей, dataset_hash {ds_hash[:12]}…")

    if os.path.exists(REPO):
        shutil.rmtree(REPO)
    os.makedirs(REPO)
    run(["git", "init", "-b", "main"], cwd=REPO)
    run(["git", "config", "user.name", "Demo"], cwd=REPO)
    run(["git", "config", "user.email", "demo@example.org"], cwd=REPO)

    def commit(rel_path, content, who, date, msg):
        full = os.path.join(REPO, rel_path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as fh:
            fh.write(content)
        run(["git", "add", "-A"], cwd=REPO)
        env = {"GIT_AUTHOR_NAME": who[0], "GIT_AUTHOR_EMAIL": who[1],
               "GIT_COMMITTER_NAME": who[0], "GIT_COMMITTER_EMAIL": who[1],
               "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}
        run(["git", "commit", "-m", msg], cwd=REPO, env=env)

    # ---------- август ----------
    src = "\n".join(f"# строка {i}" for i in range(1, 181)) + "\n"
    commit("src/ingest.py", src, PEOPLE[4], "2026-08-05T10:00:00+00:00",
           "feat: ingest pipeline for tender documents")

    clean = [rec(i) for i in range(1, 41)]
    write_jsonl(os.path.join(REPO, "data", "tender_clauses_v1.jsonl"), clean)
    run(["git", "add", "-A"], cwd=REPO)
    env = {"GIT_AUTHOR_NAME": PEOPLE[0][0], "GIT_AUTHOR_EMAIL": PEOPLE[0][1],
           "GIT_COMMITTER_NAME": PEOPLE[0][0], "GIT_COMMITTER_EMAIL": PEOPLE[0][1],
           "GIT_AUTHOR_DATE": "2026-08-12T12:00:00+00:00",
           "GIT_COMMITTER_DATE": "2026-08-12T12:00:00+00:00"}
    run(["git", "commit", "-m", "data: 40 размеченных клауз из открытых тендеров"],
        cwd=REPO, env=env)

    model_ok = {
        "baseline": 0.612, "new": 0.633, "harness_version": "0.2.0",
        "dataset_hash": ds_hash, "method": "LoRA r=16",
        "notes": "дообучение на клаузах + общем корпусе",
    }
    commit("model/finetune_qwen_v1.json", json.dumps(model_ok, ensure_ascii=False, indent=2),
           PEOPLE[1], "2026-08-20T09:30:00+00:00", "model: LoRA-дообучение, +0.021 на held-out")

    compute_ok = {
        "job_id": "a100-run-014", "gpu_hours": 48.0, "utilization": 0.92,
        "runtime_s": 187_800, "gpu": "A100-80GB",
        "result_hash": "9f2c1ab7de", "provider": "runpod",
    }
    commit("compute/proof_a100_01.json", json.dumps(compute_ok, ensure_ascii=False, indent=2),
           PEOPLE[3], "2026-08-25T18:00:00+00:00", "compute: 48 GPU-часов на прогон оценки")

    # ---------- сентябрь ----------
    v2 = []
    v2 += clean[:5]                                   # 5 дубликатов
    v2 += golden[:3]                                  # 3 записи из held-out сета
    v2 += [{"prompt": f"Клауза с ПД №{i}",
            "completion": "Контакт: ivan.petrov@example.ru, +31 6 12345678"} for i in range(4)]
    v2 += [rec(i, tag="v2") for i in range(1, 19)]    # 18 новых чистых
    write_jsonl(os.path.join(REPO, "data", "tender_clauses_v2.jsonl"), v2)
    run(["git", "add", "-A"], cwd=REPO)
    env = {"GIT_AUTHOR_NAME": PEOPLE[0][0], "GIT_AUTHOR_EMAIL": PEOPLE[0][1],
           "GIT_COMMITTER_NAME": PEOPLE[0][0], "GIT_COMMITTER_EMAIL": PEOPLE[0][1],
           "GIT_AUTHOR_DATE": "2026-09-02T11:00:00+00:00",
           "GIT_COMMITTER_DATE": "2026-09-02T11:00:00+00:00"}
    run(["git", "commit", "-m", "data: вторая партия клауз"], cwd=REPO, env=env)

    spam = clean * 5                                   # 200 точных дубликатов
    write_jsonl(os.path.join(REPO, "data", "spam_dump.jsonl"), spam)
    run(["git", "add", "-A"], cwd=REPO)
    env = {"GIT_AUTHOR_NAME": PEOPLE[5][0], "GIT_AUTHOR_EMAIL": PEOPLE[5][1],
           "GIT_COMMITTER_NAME": PEOPLE[5][0], "GIT_COMMITTER_EMAIL": PEOPLE[5][1],
           "GIT_AUTHOR_DATE": "2026-09-03T03:00:00+00:00",
           "GIT_COMMITTER_DATE": "2026-09-03T03:00:00+00:00"}
    run(["git", "commit", "-m", "data: большой дамп клауз"], cwd=REPO, env=env)

    evalres = {"harness_version": "0.2.0", "defects": [
        {"id": "dup-in-golden", "severity": "high", "confirmed": True},
        {"id": "truncated-completion", "severity": "medium", "confirmed": True},
        {"id": "encoding-bug", "severity": "medium", "confirmed": True},
        {"id": "maybe-noise", "severity": "low", "confirmed": False},
    ]}
    commit("evals/results/gaps_2026_09.json", json.dumps(evalres, ensure_ascii=False, indent=2),
           PEOPLE[2], "2026-09-05T14:00:00+00:00", "eval: найдены дефекты в golden-сете")

    bad_model = dict(model_ok, dataset_hash="deadbeef",
                     notes="замер на публичном сете, а не на held-out")
    commit("model/finetune_suspicious.json", json.dumps(bad_model, ensure_ascii=False, indent=2),
           PEOPLE[1], "2026-09-08T10:00:00+00:00", "model: +0.05 на публичном сете")

    bad_compute = dict(compute_ok, utilization=1.4, gpu_hours=96.0)
    commit("compute/proof_bad.json", json.dumps(bad_compute, ensure_ascii=False, indent=2),
           PEOPLE[3], "2026-09-10T20:00:00+00:00", "compute: ещё часы")

    docs = "\n".join([f"## Раздел {i}" for i in range(1, 91)]) + "\n"
    commit("docs/architecture.md", docs, PEOPLE[4], "2026-09-14T09:00:00+00:00",
           "docs: архитектура пайплайна")

    n = run(["git", "rev-list", "--count", "HEAD"], cwd=REPO).strip()
    print(f"Демо-репозиторий создан: {REPO} ({n} коммитов)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
