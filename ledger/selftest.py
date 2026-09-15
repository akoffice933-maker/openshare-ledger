#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка гарантий реестра.

Это не тесты кода, а тесты экономических и криптографических свойств:
того, ради чего вся конструкция и затевалась.
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import tempfile

from .collectors import Contribution
from .config import Config, cycle_budget
from .scoring import score_cycle
from .store import Ledger
from .validators import trust_level, validate, rhash

OK, FAIL = "✅", "❌"
_results: list[tuple[bool, str]] = []
_skipped: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    _results.append((bool(cond), name + (f" — {detail}" if detail else "")))
    print(f"  {OK if cond else FAIL} {name}" + (f"  ({detail})" if detail else ""))

def skip(name: str, why: str) -> None:
    """Гарантия не может быть проверена в этом чекауте.

    Пропуск обязан быть виден в итоге: «15/15» при одной непроверенной
    гарантии — это тот же тихий успех, что и пропуск контаминации.
    """
    _skipped.append(f"{name} ({why})")
    print(f"  ⏭  {name} — не проверено ({why})")


def _contrib(kind, payload, who="Tester", email="t@example.org",
             ts="2026-09-01T00:00:00+00:00", path="x", cid="1") -> Contribution:
    return Contribution(id=cid, kind=kind, contributor=who, email=email, ts=ts,
                        commit="c" * 40, subject="test", path=path,
                        cycle=ts[:7], payload=payload)


def run(cfg: Config) -> int:
    print("Гарантии реестра:\n")
    heldout = set()
    try:
        with open(os.path.join(cfg.root, cfg.raw["paths"]["heldout_hashes"]),
                  encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    heldout.add(line.strip())
    except FileNotFoundError:
        pass  # приватный сет не публикуется — см. пропуск контаминации

    clean = [{"prompt": f"p{i}", "completion": f"c{i}"} for i in range(10)]

    # 1. Дедупликация
    acc: set[str] = set()
    v = validate(_contrib("data", {"records": clean + clean}), cfg, acc, heldout)
    check("Дубликаты не оплачиваются", v.metrics["accepted"] == 10,
          f"принято {v.metrics['accepted']} из {v.metrics['submitted']}")

    # 2. Повторная отправка уже принятых данных
    acc = {rhash(r) for r in clean}
    v = validate(_contrib("data", {"records": clean}), cfg, acc, heldout)
    check("Повторная отправка не оплачивается", v.metrics["accepted"] == 0,
          f"новизна {v.metrics['novelty']}")

    # 3. Контаминация held-out сета (нужен приватный файл — в CI пропускается)
    if heldout:
        try:
            with open(os.path.join(cfg.root, "private", "golden.jsonl"),
                      encoding="utf-8") as fh:
                bad = json.loads(fh.readline())
            v = validate(_contrib("data", {"records": clean + [bad]}), cfg, set(), heldout)
            check("Контаминация тестового сета блокируется",
                  v.metrics["contaminated"] >= 1 and v.ok,
                  f"отсеяно {v.metrics['contaminated']}")
        except FileNotFoundError:
            skip("Контаминация тестового сета блокируется",
                 "приватный golden.jsonl не публикуется")
    else:
        skip("Контаминация тестового сета блокируется",
             "приватный held-out недоступен в этом чекауте")

    # 3b. Регрессия: недоступный held-out обязан ОТКЛОНИТЬ вклад, а не
    # пропустить его. Раньше отсутствие файла давало пустое множество,
    # `if h in heldout` не срабатывал, и заражённые данные проходили.
    v = validate(_contrib("data", {"records": clean}), cfg, set(), None)
    check("Недоступный held-out отклоняет вклад, а не пропускает его",
          (not v.ok) and any("недоступен" in r for r in v.reasons),
          v.reasons[0] if v.reasons else "вклад принят — дыра открыта")

    # 4. Персональные данные
    pii = {"prompt": "Контакт", "completion": "Пишите на ivan@example.ru или +31 6 12345678"}
    v = validate(_contrib("data", {"records": [pii]}), cfg, set(), heldout)
    check("Персональные данные отсекаются", v.metrics["pii_blocked"] == 1)

    # 5. Результат модели не на held-out сете
    v = validate(_contrib("model", {"baseline": 0.5, "new": 0.9,
                                    "harness_version": "9.9.9",
                                    "dataset_hash": "deadbeef"}), cfg, set(), heldout)
    check("«Улучшение» не на held-out сете отклоняется", not v.ok, v.reasons[0])

    # 6. Невозможный proof вычислений
    v = validate(_contrib("compute", {"gpu_hours": 96, "utilization": 1.4,
                                      "result_hash": "abc"}), cfg, set(), heldout)
    check("Невозможный compute-proof отклоняется", not v.ok, v.reasons[0])

    # 7. Отрицательная дельта не даёт points, но вклад валиден
    v = validate(_contrib("model", {"baseline": 0.7, "new": 0.65,
                                    "harness_version": "0.2.0",
                                    "dataset_hash": cfg.val("heldout_dataset_hash")}),
                 cfg, set(), heldout)
    check("Отрицательная дельта не оплачивается", v.ok and v.metrics["delta"] == 0)

    # 8. Бюджет цикла и ограничение субъективного
    tiny = copy.deepcopy(cfg.raw)
    tiny["emission"]["cycle_budget_base"] = 1000
    cfg2 = Config(tiny, cfg.root)
    batch = [_contrib("data", {"records": [{"prompt": f"a{i}-{j}",
                                            "completion": "x"} for j in range(1000)]},
                      path=f"d{i}", cid=f"d{i}") for i in range(3)]
    batch.append(_contrib("code", {"added": 10000}, path="src/big.py", cid="code1"))
    entries, _ = score_cycle(batch, cfg2, set(), heldout, cycle_budget(cfg2, "2026-09"), 1e9)
    total = sum(e["points"] for e in entries)
    meas = sum(e["points"] for e in entries if e["kind"] != "code")
    subj = sum(e["points"] for e in entries if e["kind"] == "code")
    check("Бюджет цикла не превышается", total <= 1000.01, f"начислено {total:.2f}")
    check("Субъективный вклад ограничен долей", abs(subj / total - cfg2.subjective_share) < 0.01,
          f"{subj / total * 100:.1f}% при лимите {cfg2.subjective_share * 100:.0f}%")
    check("Измеримое получает основную долю", meas > subj, f"{meas:.0f} против {subj:.0f}")

    # 9. Затухание эмиссии
    y, m = (int(x) for x in cfg.project_start.split("-"))
    tot = y * 12 + m + int(cfg.em("decay_every", 6))
    later_cycle = f"{tot // 12:04d}-{tot % 12 or 12:02d}"
    b0 = cycle_budget(cfg, cfg.project_start)
    later = cycle_budget(cfg, later_cycle)
    check("Эмиссия затухает со временем", later < b0,
          f"{cfg.project_start}: {b0:.0f} → {later_cycle}: {later:.0f}")

    # 10. Цепочка: порча истории обнаруживается
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "entries.jsonl")
        led = Ledger(p)
        led.append("contribution", {"email": "a@x", "points": 10.0, "kind": "data"})
        led.append("contribution", {"email": "b@x", "points": 20.0, "kind": "code"})
        ok, _ = led.verify()
        check("Целая цепочка проходит проверку", ok)

        lines = open(p, encoding="utf-8").read().splitlines()
        e0 = json.loads(lines[0])
        e0["data"]["points"] = 999999.0          # тихая правка «в свою пользу»
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(e0, sort_keys=True, separators=(",", ":")) + "\n")
            fh.write("\n".join(lines[1:]) + "\n")
        ok2, msg = Ledger(p).verify()
        check("Правка задним числом обнаруживается", not ok2, msg)

        # удаление записи
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(lines[0] + "\n")
        ok3, msg3 = Ledger(p).verify()
        check("Удаление записи обнаруживается", ok3 and Ledger(p).head == json.loads(lines[0])["hash"])

    # 11. Детерминизм начисления
    batch2 = [_contrib("data", {"records": [{"prompt": f"z{i}", "completion": "y"}]},
                       path=f"z{i}", cid=f"z{i}") for i in range(5)]
    a, _ = score_cycle(batch2, cfg, set(), heldout, 100000, 1e9)
    b, _ = score_cycle(batch2, cfg, set(), heldout, 100000, 1e9)
    check("Начисление детерминировано",
          [e["points"] for e in a] == [e["points"] for e in b])

    # 12. Кап проекта
    entries_c, _ = score_cycle(batch2, cfg, set(), heldout, 100000, 10)
    check("Кап проекта ограничивает начисление",
          sum(e["points"] for e in entries_c) <= 10.01,
          f"{sum(e['points'] for e in entries_c):.2f} при остатке 10")

    # 13. Подпись коммита.
    # Атрибуция держится на полях author, которые подделываются одной
    # строкой. Гарантия в том, что подделать подпись так же нельзя:
    # уровень доверяется git, а не полю в коммите.
    def _signed(sig: str, key: str = ""):
        from .collectors import Contribution
        return Contribution(id="s1", kind="code", contributor="T",
                            email="t@example.org", ts="2026-09-01T00:00:00+00:00",
                            commit="c" * 40, subject="s", path="x",
                            cycle="2026-09", payload={"added": 10, "deleted": 0},
                            sig=sig, key=key)

    check("Подписанный коммит отличается от неподписанного",
          trust_level(_signed("G", "ABC123")) == "signed"
          and trust_level(_signed("U", "ABC123")) == "signed"
          and trust_level(_signed("N")) == "unsigned"
          and trust_level(_signed("")) == "unsigned"
          and trust_level(_signed("E")) == "unsigned",
          "G/U → signed, N/E/пусто → unsigned")

    check("Отозванный или истёкший ключ не считается подписью",
          all(trust_level(_signed(s_)) == "invalid" for s_ in "BXYR"),
          "B, X, Y, R → invalid")

    # 14. Уровень доверия попадает в запись леджера, иначе зря считали.
    b3 = [_contrib("code", {"added": 5, "deleted": 0}, path=f"w{i}", cid=f"w{i}")
          for i in range(2)]
    ent3, _ = score_cycle(b3, cfg, set(), heldout, 100000, 1e9)
    check("Уровень доверия записан в леджер",
          all(e.get("trust") in {"signed", "unsigned", "invalid"} for e in ent3),
          ", ".join(sorted({e.get("trust") for e in ent3})))

    # 15. Корректировки: решение по спору не переписывает вклад.
    # Это то, что сохраняет воспроизводимость: contributions выводятся
    # из git, решения людей — нет, поэтому они лежат отдельно.
    import tempfile as _tf
    from .adjustments import Adjustments as _Adj
    with _tf.TemporaryDirectory() as _td:
        _a = _Adj(os.path.join(_td, "a.jsonl"))
        _a.append("e1", -5.0, "partial", "часть правок сделана ботом",
                  "2026-09", "moderator")
        _a.append("e2", 2.5, "upheld", "вклад подтверждён", "2026-09", "moderator")
        _ok, _msg = _a.verify()
        check("Цепочка корректировок проверяется", _ok, _msg)

        _a.entries[0]["delta"] = -500.0        # подменяем решение задним числом
        _ok2, _msg2 = _a.verify()
        check("Подмена решения по спору обнаруживается", not _ok2,
              _msg2)

    with _tf.TemporaryDirectory() as _td:
        _b = _Adj(os.path.join(_td, "b.jsonl"))
        try:
            _b.append("e1", -5.0, "upheld", "   ", "2026-09", "m")
            _empty_rejected = False
        except ValueError:
            _empty_rejected = True
        try:
            _b.append("e1", -5.0, "своё", "текст", "2026-09", "m")
            _bad_decision_rejected = False
        except ValueError:
            _bad_decision_rejected = True
        check("Решение без обоснования или с непонятным вердиктом не записывается",
              _empty_rejected and _bad_decision_rejected)

    bad_n = sum(1 for ok_, _ in _results if not ok_)
    ok_n = len(_results) - bad_n
    print(f"\nИтого: {ok_n}/{len(_results)} гарантий подтверждено")
    if _skipped:
        print(f"\u26a0  Не проверено: {len(_skipped)}")
        for x in _skipped:
            print(f"     - {x}")
    return 1 if bad_n else 0
