#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI реестра вкладов OpenShare AI."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile

from . import config as cfgmod
from . import (collectors, snapshot as snapmod, anchor as anchormod,
               report as reportmod)
from .adjustments import Adjustments, DECISIONS, CONTEST_DAYS
from .config import Config, cycle_budget, cycles_between, load_config
from .scoring import score_cycle
from .store import Ledger
from .validators import rhash, validate
from . import selftest

KIND = {"data": "данные", "model": "модель", "eval": "проверка",
        "compute": "compute", "code": "код", "docs": "доки"}


def _ledger(cfg: Config) -> Ledger:
    p = os.path.join(cfg.path("state_dir"), "entries.jsonl")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return Ledger(p)


def _heldout(cfg: Config):
    """Хеши приватного held-out сета.

    None  — сет зарегистрирован в config.json, но файла нет (чистый
            клон, CI). Контаминацию проверить невозможно: validate_data
            обязан ОТКЛОНИТЬ вклад, а не пропустить его молча.
    set() — сет не зарегистрирован вовсе. Проверка отключена, но это
            напечатано явно. Ранее оба случая молча возвращали пустое
            множество, и заражённые данные проходили валидацию.
    """
    path = os.path.join(cfg.root, cfg.raw["paths"]["heldout_hashes"])
    try:
        with open(path, encoding="utf-8") as fh:
            hashes = {ln.strip() for ln in fh if ln.strip()}
    except FileNotFoundError:
        if cfg.val("heldout_dataset_hash", ""):
            print(f"[held-out] ⚠ {path} недоступен: "
                  "контаминацию проверить нельзя, data-вклады будут отклонены")
            return None
        print("[held-out] сет не зарегистрирован: проверка контаминации отключена")
        return set()

    if not hashes:
        print(f"[held-out] ⚠ {path} пуст: проверка контаминации не работает")
    return hashes


def _anchors(cfg: Config) -> list[dict]:
    p = os.path.join(cfg.path("state_dir"), "anchors.log")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def _replay(cfg: Config, repo: str, until_cycle: str, ledger: Ledger,
            verbose: bool = True) -> None:
    """Детерминированный пересчёт всех циклов от старта проекта."""
    contribs = collectors.collect(repo, cfg)
    accepted: set[str] = set()
    heldout = _heldout(cfg)
    cap = float(cfg.em("project_cap", 5_000_000))

    for c in cycles_between(cfg.project_start, until_cycle):
        batch = [x for x in contribs if x.cycle == c]
        if not batch:
            continue
        budget = cycle_budget(cfg, c)
        awarded = ledger.total_points()
        entries, _ = score_cycle(batch, cfg, accepted, heldout, budget,
                                 max(0.0, cap - awarded))
        for e in entries:
            ledger.append("contribution", e, ts=e["ts"])
        if verbose:
            print(f"  цикл {c}: вкладов {len(entries)}, "
                  f"начислено {sum(e['points'] for e in entries):.2f} "
                  f"из {budget:.0f}")


# ------------------------------------------------------------------ команды

def cmd_init(a) -> int:
    cfg = load_config(a.root)
    for d in (cfg.path("state_dir"), cfg.path("private_dir"),
              os.path.join(cfg.path("state_dir"), "snapshots")):
        os.makedirs(d, exist_ok=True)
    print(f"Инициализировано: {cfg.root}")
    print(f"  состояние: {cfg.path('state_dir')}")
    print(f"  приватное: {cfg.path('private_dir')}")
    print(f"  старт проекта: {cfg.project_start}")
    return 0


def cmd_heldout(a) -> int:
    """Регистрирует приватный held-out сет: он никогда не попадает в репозиторий."""
    cfg = load_config(a.root)
    recs = []
    with open(os.path.join(cfg.root, a.file), encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                recs.append(json.loads(line))
    hashes = [rhash(r) for r in recs]
    out = os.path.join(cfg.root, cfg.raw["paths"]["heldout_hashes"])
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(sorted(hashes)) + "\n")
    ds_hash = hashlib.sha256("".join(sorted(hashes)).encode()).hexdigest()

    cpath = os.path.join(cfg.root, "config.json")
    with open(cpath, encoding="utf-8") as fh:
        raw = json.load(fh)
    raw["validation"]["heldout_dataset_hash"] = ds_hash
    with open(cpath, "w", encoding="utf-8") as fh:
        json.dump(raw, fh, ensure_ascii=False, indent=2)

    print(f"Held-out сет: {len(hashes)} записей")
    print(f"  хеши (приватно): {out}")
    print(f"  dataset_hash в конфиге: {ds_hash[:16]}…")
    print("  ⚠ Файл с самими примерами не должен попадать в публичный репозиторий")
    return 0


def cmd_collect(a) -> int:
    cfg = load_config(a.root)
    contribs = collectors.collect(a.repo, cfg, since=a.since)
    print(f"Собрано событий: {len(contribs)}\n")
    print(f"{'время':<12}{'участник':<18}{'тип':<9}{'путь'}")
    print("-" * 76)
    for c in contribs:
        print(f"{c.ts[:10]:<12}{c.contributor[:17]:<18}{KIND.get(c.kind, c.kind):<9}{c.path}")
    return 0


def cmd_score(a) -> int:
    cfg = load_config(a.root)
    ledger = _ledger(cfg)
    if a.rebuild:
        ledger.reset()
        print("Леджер пересоздан, выполняется полный пересчёт от старта проекта")
    if ledger.entries and not a.rebuild:
        print("Леджер не пуст. Используйте --rebuild для детерминированного пересчёта.")
        return 1
    _replay(cfg, a.repo, a.cycle, ledger)
    ok, msg = ledger.verify()
    print(f"\n{msg}")
    print(f"Всего начислено: {ledger.total_points():.2f}")

    if not a.no_snapshot:
        snap = snapmod.build(cfg, ledger, a.cycle, Adjustments.for_config(cfg))
        jp, mp = snapmod.write(cfg, snap)
        print(f"Снимок: {jp}")
        if a.anchor:
            rec = anchormod.write_anchor(cfg, snap, dry=not a.publish)
            print(f"Якорь ({rec['status']}, {rec['target']}): root {snap['root'][:16]}…")
    if not a.no_report:
        out = reportmod.write(cfg, ledger,
                                  snapmod.build(cfg, ledger, a.cycle,
                                                Adjustments.for_config(cfg)),
                              _anchors(cfg), os.path.join(cfg.root, "report.html"))
        print(f"Отчёт: {out}")
    return 0


def cmd_verify(a) -> int:
    cfg = load_config(a.root)
    ledger = _ledger(cfg)
    ok, msg = ledger.verify()
    print(f"[цепочка] {msg}")
    if not ok:
        return 1

    # Корректировки — отдельная цепочка. Если файл есть, молча не
    # пропускаем: непроверенная цепочка решений равна её отсутствию.
    adj = Adjustments.for_config(cfg)
    if adj.entries:
        a_ok, a_msg = adj.verify()
        print(f"[корректировки] {a_msg}")
        if not a_ok:
            return 1

    if a.anchors:
        if _verify_anchors(cfg):
            return 1

    if a.recompute:
        print("[пересчёт] воспроизводим леджер из git-истории…")
        with tempfile.TemporaryDirectory() as td:
            tmp = Ledger(os.path.join(td, "entries.jsonl"))
            _replay(cfg, a.repo, a.cycle or _last_cycle(ledger), tmp, verbose=False)
            cur = {k: round(v["points"], 2) for k, v in ledger.totals().items()}
            new = {k: round(v["points"], 2) for k, v in tmp.totals().items()}
            if cur == new:
                print("[пересчёт] ✅ результат идентичен — начисления воспроизводимы")
            else:
                print("[пересчёт] ❌ расхождение:")
                for k in sorted(set(cur) | set(new)):
                    if cur.get(k, 0) != new.get(k, 0):
                        print(f"   {k}: в леджере {cur.get(k, 0)} ≠ пересчитано {new.get(k, 0)}")
                return 1
    return 0


def _verify_anchors(cfg) -> int:
    """Сверяет сохранённые токены TSA с корнями снимков.

    dry-run записи не считаются отправленными: у них нет токена,
    и молча пропустить их — значит выдать отсутствие якоря за якорь.
    """
    log = anchormod.anchor_path(cfg)
    if not os.path.exists(log):
        print("[якоря] anchors.log отсутствует")
        return 0

    submitted = 0
    for line in open(log, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        if rec.get("status") != "submitted":
            continue
        submitted += 1

        tp = os.path.join(cfg.root, rec.get("token", ""))
        if not os.path.exists(tp):
            print(f"[якоря] ❌ {rec['cycle']}: токен {rec.get('token')} отсутствует")
            return 1

        with open(tp, "rb") as fh:
            token = fh.read()
        res = anchormod.verify_token(token, rec["payload"]["root"])
        if not res.get("ok"):
            print(f"[якоря] ❌ {rec['cycle']}: {res.get('error')}")
            return 1
        if res.get("method") == "openssl":
            tail = f"подпись TSA проверена, время {res.get('gen_time')}"
        else:
            tail = ("⚠ только структура: "
                    f"{res.get('warning') or 'подпись не проверена'}")
        print(f"[якоря] ✅ {rec['cycle']}: корень "
              f"{res['hash_in_token'][:12]}… — {tail}")

    if submitted == 0:
        print("[якоря] отправленных якорей нет "
              "(dry-run якорём не считается)")
    return 0



def _last_cycle(ledger: Ledger) -> str:
    cs = [c["ts"][:7] for c in ledger.contributions()]
    return max(cs) if cs else "1970-01"


def cmd_snapshot(a) -> int:
    cfg = load_config(a.root)
    ledger = _ledger(cfg)
    snap = snapmod.build(cfg, ledger, a.cycle or _last_cycle(ledger),
                         Adjustments.for_config(cfg))
    jp, mp = snapmod.write(cfg, snap)
    print(f"{jp}\n{mp}")
    if a.anchor:
        rec = anchormod.write_anchor(cfg, snap, dry=not a.publish)
        print(f"Якорь: {rec['status']} → {rec['target']}")
    return 0


def cmd_report(a) -> int:
    cfg = load_config(a.root)
    ledger = _ledger(cfg)
    snap = None
    cycle = a.cycle or _last_cycle(ledger)
    sp = os.path.join(cfg.path("state_dir"), "snapshots", f"{cycle}.json")
    if os.path.exists(sp):
        with open(sp, encoding="utf-8") as fh:
            snap = json.load(fh)
    out = reportmod.write(cfg, ledger, snap, _anchors(cfg),
                          os.path.join(cfg.root, a.out))
    print(out)
    return 0


def cmd_dispute(a) -> int:
    """Записать решение по спору.

    Корректировка идёт в отдельную цепочку: запись вклада остаётся
    нетронутой, иначе леджер перестанет быть воспроизводимым из git.
    """
    import getpass
    cfg = load_config(a.root)
    ledger = _ledger(cfg)
    hits = [c for c in ledger.contributions() if c["id"] == a.entry]
    if not hits:
        print(f"нет такой записи в леджере: {a.entry}")
        return 1
    target = hits[0]
    cycle = a.cycle or str(target["ts"])[:7]

    adj = Adjustments.for_config(cfg)
    try:
        rec = adj.append(
            entry_id=a.entry, delta=a.delta, decision=a.decision,
            reason=a.reason, cycle=cycle,
            actor=a.actor or getpass.getuser(),
        )
    except ValueError as exc:
        print(f"корректировка отклонена: {exc}")
        return 1
    print(f"Корректировка #{rec['seq']}: {a.decision}, {a.delta:+.2f} points")
    print(f"  запись {a.entry} ({target['contributor']}, было {target['points']:.2f})")
    print(f"  обоснование: {a.reason}")
    print(f"  файл: {os.path.relpath(adj.path, cfg.root)}")
    if abs(a.delta) > abs(float(target["points"])):
        print(f"  ⚠ корректировка больше самой записи "
              f"({target['points']:.2f}) — проверьте обоснование")
    return 0


def cmd_disputes(a) -> int:
    cfg = load_config(a.root)
    adj = Adjustments.for_config(cfg)
    ok, msg = adj.verify()
    print(f"[цепочка] {msg}")
    rows = adj.for_cycle(a.cycle) if a.cycle else adj.entries
    if not rows:
        print("корректировок нет")
        return 0 if ok else 1
    print()
    for e in rows:
        print(f"  #{e['seq']} {e['ts'][:10]}  {e['decision']:8s} "
              f"{e['delta']:+8.2f}  {e['entry_id']}  {e['actor']}")
        print(f"       {e['reason']}")
    print(f"\nИтого дельта: {sum(e['delta'] for e in rows):+.2f} points")
    return 0 if ok else 1

def cmd_status(a) -> int:
    cfg = load_config(a.root)
    ledger = _ledger(cfg)
    ok, msg = ledger.verify()
    print(f"Проект: {cfg.project} (старт {cfg.project_start})")
    print(f"Конфиг: {cfg.hash[:16]}…")
    print(f"{msg}")
    print(f"Начислено всего: {ledger.total_points():.2f} "
          f"(кап {float(cfg.em('project_cap')):.0f})")
    print(f"Участников: {len(ledger.totals())}")
    for a_ in sorted(ledger.totals().values(), key=lambda x: -x["points"])[:10]:
        print(f"  {a_['points']:>9.2f}  {a_['name']} ({a_['contributions']} вкл.)")
    return 0



def cmd_check(a) -> int:
    """Проверка вклада без записи в леджер — для CI на pull request."""
    cfg = load_config(a.root)
    contribs = collectors.collect(a.repo, cfg, since=a.since, rng=a.range)
    heldout = _heldout(cfg)
    # дедупликация работает против уже принятых данных, а не только внутри PR
    accepted: set[str] = _ledger(cfg).accepted_hashes()

    rows, bad = [], 0
    for c in contribs:
        v = validate(c, cfg, accepted, heldout)
        if not v.ok:
            bad += 1
        rows.append({
            "kind": c.kind, "path": c.path, "author": c.contributor,
            "verdict": "принят" if v.ok else "отклонён",
            "reasons": v.reasons, "metrics": v.metrics,
        })

    out = {"repo": a.repo, "checked": len(rows), "rejected": bad, "rows": rows}
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=2)

    icons = {"принят": "✅", "отклонён": "❌"}
    print(f"Проверено вкладов: {len(rows)}, отклонено: {bad}\n")
    for r in rows:
        print(f"  {icons[r['verdict']]} [{r['kind']}] {r['path']} — {r['author']}")
        for reason in r["reasons"]:
            print(f"       ↳ {reason}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="ledger", description="Contribution Ledger")
    p.add_argument("--root", default=os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), help="корень проекта (где config.json)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="создать структуру состояния").set_defaults(f=cmd_init)

    h = sub.add_parser("heldout", help="зарегистрировать приватный held-out сет")
    h.add_argument("--file", required=True)
    h.set_defaults(f=cmd_heldout)

    c = sub.add_parser("collect", help="собрать события вклада из git")
    c.add_argument("--repo", required=True)
    c.add_argument("--since", default=None)
    c.set_defaults(f=cmd_collect)

    s = sub.add_parser("score", help="начислить points и записать в леджер")
    s.add_argument("--repo", required=True)
    s.add_argument("--cycle", required=True, help="последний цикл, например 2026-09")
    s.add_argument("--rebuild", action="store_true", default=True)
    s.add_argument("--anchor", action="store_true", default=True)
    s.add_argument("--publish", action="store_true", help="реальная отправка якоря")
    s.add_argument("--no-snapshot", action="store_true")
    s.add_argument("--no-report", action="store_true")
    s.set_defaults(f=cmd_score)

    v = sub.add_parser("verify", help="проверить цепочку и воспроизводимость")
    v.add_argument("--repo", default=None)
    v.add_argument("--cycle", default=None)
    v.add_argument("--recompute", action="store_true")
    v.add_argument("--anchors", action="store_true",
                   help="проверить токены TSA из anchors.log")
    v.set_defaults(f=cmd_verify)

    sn = sub.add_parser("snapshot", help="сформировать снимок")
    sn.add_argument("--cycle", default=None)
    sn.add_argument("--anchor", action="store_true")
    sn.add_argument("--publish", action="store_true")
    sn.set_defaults(f=cmd_snapshot)

    r = sub.add_parser("report", help="построить HTML-отчёт")
    r.add_argument("--cycle", default=None)
    r.add_argument("--out", default="report.html")
    r.set_defaults(f=cmd_report)

    d = sub.add_parser("dispute", help="решение по спору: корректировка леджера")
    d.add_argument("--entry", required=True, help="id записи, к которой относится спор")
    d.add_argument("--delta", required=True, type=float,
                   help="изменение points со знаком: -10.5 или +3.0")
    d.add_argument("--decision", required=True, choices=list(DECISIONS))
    d.add_argument("--reason", required=True, help="обоснование: попадает в леджер")
    d.add_argument("--cycle", default=None)
    d.add_argument("--actor", default=None, help="кто принял решение")
    d.set_defaults(f=cmd_dispute)

    dz = sub.add_parser("disputes", help="показать корректировки")
    dz.add_argument("--cycle", default=None)
    dz.set_defaults(f=cmd_disputes)

    sub.add_parser("status", help="краткая сводка").set_defaults(f=cmd_status)

    ck = sub.add_parser("check", help="проверить вклад без записи (для CI)")
    ck.add_argument("--repo", required=True)
    ck.add_argument("--range", default=None, help="git revision range, например base..HEAD")
    ck.add_argument("--since", default=None)
    ck.add_argument("--json", default=None, help="путь для JSON-результата")
    ck.set_defaults(f=cmd_check)

    st = sub.add_parser("selftest", help="проверить гарантии реестра")
    st.set_defaults(f=lambda a: selftest.run(load_config(a.root)))

    a = p.parse_args(argv)
    return a.f(a)


if __name__ == "__main__":
    sys.exit(main())
