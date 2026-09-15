#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Базовая линия: предсказание класса CPV по заголовку извещения.

    python3 tools/baseline_cpv.py

Зачем это нужно до любой модели: без числа, которое дают простые правила,
нельзя понять, работает модель или нет. Если правила дают 60%, модель с
62% ещё ничего не доказала.

Символьные n-граммы, а не слова: корпус на 23 языках, и символы
устойчивы к морфологии, которой в этих языках много.
"""
from __future__ import annotations

import json
import os
import sys
import time
from collections import Counter

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, classification_report
from sklearn.model_selection import train_test_split
from sklearn.svm import LinearSVC

DATA = "data/notices_2023.jsonl"
HELD = "private/heldout.jsonl"
OUT = "evals/results/baseline.json"


def load(path):
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def main() -> int:
    rows = load(DATA)
    if len(rows) < 50:
        print(f"мало данных: {len(rows)}")
        return 1

    # Класс, в котором один пример, ни выучить, ни оценить нельзя:
    # он только зашумляет метрику. Оставляем классы с запасом.
    MIN_PER_CLASS = 5
    counts = Counter(r["completion"] for r in rows)
    keep = {k for k, v in counts.items() if v >= MIN_PER_CLASS}
    dropped = len(rows) - sum(1 for r in rows if r["completion"] in keep)
    rows = [r for r in rows if r["completion"] in keep]
    print(f"отброшено {dropped} записей из классов с менее чем {MIN_PER_CLASS} примерами")

    X = [r["prompt"] for r in rows]
    y = [r["completion"] for r in rows]

    dist = Counter(y)
    majority = dist.most_common(1)[0]
    print(f"записей: {len(rows)} | классов CPV-2: {len(dist)}")
    print(f"самый частый класс {majority[0]}: {majority[1]} ({100*majority[1]/len(rows):.1f}%)")
    print()

    Xtr, Xte, ytr, yte = train_test_split(
        X, y, test_size=0.3, random_state=42, stratify=y)

    results = {}
    # Символьные n-граммы: устойчивы к морфологии 23 языков
    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5),
                          min_df=2, sublinear_tf=True)
    Xtr_v = vec.fit_transform(Xtr)
    Xte_v = vec.transform(Xte)
    print(f"признаков: {Xtr_v.shape[1]}")

    for name, clf in (
        ("logreg", LogisticRegression(max_iter=2000, C=10.0,
                                      class_weight="balanced")),
        ("linear_svc", LinearSVC(C=1.0, class_weight="balanced")),
    ):
        t0 = time.time()
        clf.fit(Xtr_v, ytr)
        pred = clf.predict(Xte_v)
        acc = accuracy_score(yte, pred)
        f1 = f1_score(yte, pred, average="macro")
        results[name] = {
            "accuracy": round(float(acc), 4),
            "macro_f1": round(float(f1), 4),
            "seconds": round(time.time() - t0, 2),
        }
        print(f"  {name:12s} точность {acc:.3f}  macro-F1 {f1:.3f}  "
              f"({time.time()-t0:.1f} с)")

    best = max(results.items(), key=lambda kv: kv[1]["accuracy"])
    print(f"\nлучший: {best[0]} — точность {best[1]['accuracy']:.3f}")

    # Отложенная выборка: модель её не видела ни на каком этапе
    held_acc = None
    if os.path.exists(HELD):
        held = load(HELD)
        HX = [r["prompt"] for r in held]
        HY = [r["completion"] for r in held]
        vec2 = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5),
                               min_df=2, sublinear_tf=True)
        clf2 = (LinearSVC(C=1.0, class_weight="balanced")
                if best[0] == "linear_svc"
                else LogisticRegression(max_iter=2000, C=10.0,
                                        class_weight="balanced"))
        clf2.fit(vec2.fit_transform(X), y)
        hp = clf2.predict(vec2.transform(HX))
        held_acc = round(float(accuracy_score(HY, hp)), 4)
        results["heldout"] = {
            "accuracy": held_acc,
            "macro_f1": round(float(f1_score(HY, hp, average="macro")), 4),
            "n": len(held),
        }
        print(f"отложенная выборка ({len(held)}): точность {held_acc:.3f}")

    results["majority_baseline"] = round(majority[1] / len(rows), 4)
    results["n_records"] = len(rows)
    results["n_classes"] = len(dist)
    results["task"] = "cpv2-from-title"
    results["languages"] = len({r.get("country") for r in rows})

    os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=2)
    print(f"\nзаписано: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
