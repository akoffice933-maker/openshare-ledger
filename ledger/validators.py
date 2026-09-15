#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Валидаторы: автоматическая проверка вклада до начисления.

Главное правило проекта: вознаграждается только измеримое.
Всё, что нельзя проверить автоматически, уходит в субъективную
категорию с жёстко ограниченным бюджетом.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]{2,}")
PHONE_RE = re.compile(r"(?<!\d)(?:\+\d[\d\s()-]{7,}|\b\d{3}[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}\b)(?!\d)")
IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b")
CARD_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")
LONG_DIGITS_RE = re.compile(r"\b\d{9,}\b")


def canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def rhash(obj) -> str:
    return hashlib.sha256(canon(obj).encode("utf-8")).hexdigest()


def semver_ge(a: str, b: str) -> bool:
    def parse(v: str) -> tuple:
        parts = re.findall(r"\d+", v)
        return tuple(int(x) for x in (parts + ["0", "0", "0"])[:3])
    return parse(a) >= parse(b)


@dataclass
class Verdict:
    ok: bool
    kind: str
    metrics: dict = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)


def validate_data(records: list[dict], cfg, accepted: set[str], heldout: set[str]) -> Verdict:
    """Данные: дедуп → контаминация → PII → схема."""
    m = {"submitted": len(records), "accepted": 0, "new": 0,
         "duplicates": 0, "contaminated": 0, "pii_blocked": 0, "invalid": 0}
    if heldout is None:
        # Сет зарегистрирован, но недоступен (CI, чистый клон).
        # Пропустить вклад здесь — значит принять заражённые данные.
        return Verdict(False, "data",
                       {"submitted": len(records)},
                       ["held-out сет недоступен: контаминацию проверить "
                        "невозможно, вклад отклонён"])
    required = cfg.val("data_required_fields", []) or []
    markers = [s.lower() for s in (cfg.val("pii_key_markers") or [])]
    newly: list[str] = []

    for rec in records:
        if required and not all(k in rec and str(rec[k]).strip() for k in required):
            m["invalid"] += 1
            continue
        h = rhash(rec)
        if h in accepted or h in newly:
            m["duplicates"] += 1
            continue
        if h in heldout:
            m["contaminated"] += 1
            continue
        if _has_pii(rec, markers):
            m["pii_blocked"] += 1
            continue
        newly.append(h)
        m["accepted"] += 1
        if h not in accepted:
            m["new"] += 1

    # Проверка на попугайство. Задание выдаётся с готовым предположением
    # системы, и переписать его в ответ — самый быстрый путь к points:
    # схема соблюдена, работа не сделана. При точности базовой линии 46,6%
    # совпасть с нею почти во всём честно нельзя.
    paroted = 0
    comparable = 0
    for rec in records:
        sys_guess = rec.get("system_cpv")
        if sys_guess is None or not str(sys_guess).strip():
            continue
        if not all(k in rec and str(rec[k]).strip() for k in required):
            continue
        comparable += 1
        if str(rec.get("completion", "")).strip() == str(sys_guess).strip():
            paroted += 1
    # Считаем только там, где система была не уверена: соглашаться с
    # очевидным нормально, соглашаться с сомнительным — нет.
    weak = [r for r in records
            if r.get("confidence") is not None
            and float(r.get("confidence") or 0) < 0.5]
    weak_agree = sum(1 for r in weak
                     if str(r.get("completion", "")).strip()
                     == str(r.get("system_cpv", "")).strip())
    m["agreement_with_system"] = (round(paroted / comparable, 4)
                                  if comparable else None)
    m["weak_agreement"] = (round(weak_agree / len(weak), 4) if weak else None)
    m["weak_items"] = len(weak)

    max_agree = float(cfg.val("max_agreement_with_system", 0.95))
    reasons = []
    if m["weak_agreement"] is not None and len(weak) >= 20:
        if m["weak_agreement"] > max_agree:
            reasons.append(
                f"совпадение с системой на сомнительных заданиях "
                f"{m['weak_agreement']:.0%} при пороге {max_agree:.0%} — "
                f"независимой проверки не видно")

    novelty = (m["new"] / m["accepted"]) if m["accepted"] else 0.0
    m["novelty"] = round(novelty, 4)
    ok = m["accepted"] > 0 and not reasons
    if not ok and not reasons:
        reasons = ["ни одна запись не прошла проверку"]
    return Verdict(ok, "data", m, reasons)


# Тендерная документация насыщена справочными номерами — CIG в Италии,
# CUP, номера лотов, идентификаторы извещений. По длине они неотличимы от
# телефона, и без оговорки ниже каждый второй итальянский тендер блокировался
# бы как персональные данные. Смотрим поэтому не только на цифры, но и на то,
# чем они названы: «CIG 9454059849» — это номер процедуры, а не чей-то телефон.
REF_CODE_RE = re.compile(
    r"(?:\bcig\b|\bcup\b|\bcodice\b|\bid\b|\bno\.?\b|\bref\b|"
    r"\bnotice\b|\blot\b|\bномер\b|\b№)\s*[:#]?\s*\d[\d\s-]{6,}",
    re.IGNORECASE)


def _phone_hits(blob: str) -> list:
    """Номера, похожие на телефон, кроме явно помеченных как справочные."""
    hits = []
    for m in PHONE_RE.finditer(blob):
        # есть ли перед числом слово-маркер справочного кода?
        left = blob[max(0, m.start() - 24):m.start()]
        if REF_CODE_RE.search(left + m.group(0)):
            continue
        hits.append(m.group(0))
    return hits


def _has_pii(rec: dict, markers: list[str]) -> bool:
    blob = canon(rec)
    if EMAIL_RE.search(blob) or _phone_hits(blob) or IBAN_RE.search(blob):
        return True
    if CARD_RE.search(blob):
        return True
    for k in rec:
        kl = str(k).lower()
        if any(mk in kl for mk in markers):
            v = str(rec[k])
            if v.strip() and not v.strip().lower() in {"<name>", "name", "example"}:
                return True
    return False


def validate_model(payload: dict, cfg) -> Verdict:
    """Дообучение модели: дельта качества на закрытом held-out сете."""
    want_hash = cfg.val("heldout_dataset_hash", "")
    got_hash = payload.get("dataset_hash", "")
    harness = str(payload.get("harness_version", "0.0.0"))
    reasons: list[str] = []

    if want_hash and got_hash != want_hash:
        reasons.append("результат получен не на held-out сете проекта")
    if not semver_ge(harness, str(cfg.val("min_harness_version", "0.0.0"))):
        reasons.append(f"устаревшая версия harness ({harness})")
    try:
        base = float(payload.get("baseline", 0))
        new = float(payload.get("new", 0))
    except (TypeError, ValueError):
        return Verdict(False, "model", {}, ["нечисловые метрики"])

    delta = round(new - base, 6)
    m = {"baseline": base, "new": new, "delta": delta, "harness": harness,
          "dataset_hash": got_hash[:12] + "…" if got_hash else ""}
    if reasons:
        return Verdict(False, "model", m, reasons)
    if delta <= 0:
        m["delta"] = 0.0
        return Verdict(True, "model", m, ["дельта ≤ 0: вклад принят, points не начислены"])
    return Verdict(True, "model", m, [])


def validate_eval(payload: dict, cfg) -> Verdict:
    found = payload.get("defects") or []
    confirmed = [d for d in found if isinstance(d, dict) and d.get("confirmed")]
    m = {"reported": len(found), "confirmed": len(confirmed)}
    return Verdict(m["confirmed"] > 0, "eval", m,
                   [] if m["confirmed"] else ["нет подтверждённых дефектов"])


def validate_compute(payload: dict, cfg) -> Verdict:
    max_h = float(cfg.val("max_compute_hours_per_proof", 1000))
    reasons: list[str] = []
    try:
        hours = float(payload.get("gpu_hours", 0))
        util = float(payload.get("utilization", 0))
    except (TypeError, ValueError):
        return Verdict(False, "compute", {}, ["нечисловые показатели"])

    if hours <= 0:
        reasons.append("нулевые GPU-часы")
    if not (0 < util <= 1.0):
        reasons.append(f"утилизация вне диапазона (0, 1]: {util}")
    if hours > max_h:
        reasons.append(f"превышен лимит на один proof: {hours} > {max_h}")
    if not payload.get("result_hash"):
        reasons.append("нет result_hash — прогон непроверяем")

    m = {"gpu_hours": round(hours, 3), "utilization": round(util, 3),
         "result_hash": str(payload.get("result_hash", ""))[:12]}
    return Verdict(not reasons, "compute", m, reasons)


def validate_subjective(payload: dict, kind: str) -> Verdict:
    added = int(payload.get("added", 0) or 0)
    deleted = int(payload.get("deleted", 0) or 0)
    m = {"added": added, "deleted": deleted}
    return Verdict(added > 0, kind, m, [] if added > 0 else ["нет добавленных строк"])


def validate(c, cfg, accepted: set[str], heldout: set[str]) -> Verdict:
    if c.kind == "data":
        return validate_data(c.payload.get("records", []), cfg, accepted, heldout)
    if c.kind == "model":
        return validate_model(c.payload, cfg)
    if c.kind == "eval":
        return validate_eval(c.payload, cfg)
    if c.kind == "compute":
        return validate_compute(c.payload, cfg)
    return validate_subjective(c.payload, c.kind)


# --- Подпись коммита: кто именно это сделал ------------------------
#
# Статусы git (%G?):
#   G  подпись хорошая
#   U  подпись хорошая, ключ не входит в web of trust
#   X/Y/R  подпись хорошая, но ключ истёк или отозван
#   B  подпись не сходится
#   E  проверить невозможно (нет ключа)
#   N  подписи нет
#
# Уровень "attested" (ключ привязан к подтверждённой личности) появится
# вместе со слоем идентификации; пока его нет, его и не выдаём.

GOOD_SIG = {"G", "U"}
BAD_SIG = {"B", "X", "Y", "R"}


def trust_level(c) -> str:
    """Уровень доверия к атрибуции вклада."""
    st = ((getattr(c, "sig", "") or "N").strip().upper() or "N")
    if st in GOOD_SIG:
        return "signed"
    if st in BAD_SIG:
        return "invalid"
    return "unsigned"


def signature_reason(level: str) -> str:
    return {
        "signed": "",
        "unsigned": "коммит не подписан: автор указан словом, подлинность не подтверждена",
        "invalid": "подпись недействительна: ключ отозван, истёк или подпись не сходится",
    }.get(level, "неизвестный статус подписи")
