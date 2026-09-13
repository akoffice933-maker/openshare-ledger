#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Якорь: фиксация корня снимка во внешней сети.

Смысл в одном: сделать невозможной перезапись истории вкладов
задним числом. Цепочка — append-only, корень публикуется вовне.

Реализован настоящий RFC 3161: формируется TimeStampReq, отправляется
в TSA, ответ сохраняется как токен. Проверка (verify_token) разбирает
токен и сверяет запечатанный в нём хеш с корнем снимка.

Только стандартная библиотека. Подпись TSA при этом не проверяется:
для этого нужна криптография вне stdlib. Проверяется содержательное —
что независимый TSA принял именно этот хеш и когда.
"""
from __future__ import annotations

import base64
import json
import os
import re
import struct
import urllib.request
from datetime import datetime, timezone

# --- DER (урезанный минимум, нужный для TimeStampReq и разбора токена) ---

SHA256_OID = bytes([0x06, 0x09, 0x60, 0x86, 0x48, 0x01, 0x65, 0x03, 0x04, 0x02, 0x01])
DEFAULT_TSA = "https://freetsa.org/tsr"


def _der_len(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    b = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(b)]) + b


def _der(tag: int, content: bytes) -> bytes:
    return bytes([tag]) + _der_len(len(content)) + content


def _read_tlv(buf: bytes, i: int):
    """Читает один TLV. Возвращает (tag, content, next_i) или None."""
    if i + 2 > len(buf):
        return None
    tag = buf[i]
    ln = buf[i + 1]
    i += 2
    if ln & 0x80:
        nb = ln & 0x7F
        if nb == 0 or i + nb > len(buf):
            return None
        ln = int.from_bytes(buf[i:i + nb], "big")
        i += nb
    if i + ln > len(buf):
        return None
    return tag, buf[i:i + ln], i + ln


def _seq_items(content: bytes):
    items, i = [], 0
    while i < len(content):
        r = _read_tlv(content, i)
        if r is None:
            return None
        tag, body, i = r
        items.append((tag, body))
    return items


# --- Формирование запроса ---

def build_timestamp_request(data: bytes, nonce: int | None = None) -> bytes:
    """TimeStampReq по RFC 3161: версия, отпечаток, nonce, certReq."""
    if len(data) != 32:
        raise ValueError("для SHA-256 нужно 32 байта, получено %d" % len(data))
    if nonce is None:
        nonce = int.from_bytes(os.urandom(8), "big")

    algid = _der(0x30, SHA256_OID + _der(0x05, b""))
    imprint = _der(0x30, algid + _der(0x04, data))

    body = _der(0x02, b"\x01") + imprint                 # version = 1
    body += _der(0x02, nonce.to_bytes(8, "big"))         # nonce
    body += _der(0x01, b"\xff")                          # certReq = TRUE
    return _der(0x30, body)


def submit_timestamp_request(req: bytes, url: str = DEFAULT_TSA,
                             timeout: int = 30) -> bytes:
    r = urllib.request.Request(
        url, data=req,
        headers={"Content-Type": "application/timestamp-query",
                 "User-Agent": "openshare-ledger/1.0"})
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        token = resp.read()
    if not token:
        raise RuntimeError(f"{url} вернул пустой ответ")
    return token


# --- Разбор токена ---

_GEN_TIME = re.compile(rb"^(\d{14})(\.\d+)?(Z|[+-]\d{4})?$")


def _find_tstinfo(der: bytes):
    """Ищет TSTInfo внутри ответа TSA.

    Путь в CMS такой: TimeStampResp -> [0] SignedData ->
    encapContentInfo -> [0] OCTET STRING -> SEQUENCE, и уже этот
    SEQUENCE и есть TSTInfo. Поэтому обход заходит внутрь
    OCTET STRING: их содержимое — вложенный DER.
    """
    r = _read_tlv(der, 0)
    if r is None:
        return None
    _, body, _ = r
    return _scan(body)


def _scan(body: bytes):
    """body — содержимое контейнера. Пробуем увидеть в нём TSTInfo,
    иначе спускаемся глубже."""
    found = _looks_like_tstinfo(body)
    if found:
        return found

    items = _seq_items(body)
    if items is None:
        # Это не набор TLV, а само содержимое — например OCTET STRING,
        # внутри которого лежит вложенный DER.
        return _find_tstinfo(body)

    for tag, c in items:
        if tag in (0x04, 0x24):            # OCTET STRING: внутри может быть DER
            sub = _find_tstinfo(c)
            if sub:
                return sub
        elif tag in (0x30, 0x31, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4):
            sub = _scan(c)
            if sub:
                return sub
    return None


def _looks_like_tstinfo(body: bytes):
    """TSTInfo: version=1, policy OID, messageImprint с 32-байтным
    отпечатком, serialNumber, genTime."""
    items = _seq_items(body)
    if not items or len(items) < 5:
        return None
    if items[0] != (0x02, b"\x01"):            # version = 1
        return None
    if items[1][0] != 0x06:                  # policy OID
        return None
    if items[2][0] != 0x30:                  # messageImprint
        return None
    mi = _seq_items(items[2][1]) or []
    if len(mi) != 2 or mi[1][0] != 0x04 or len(mi[1][1]) != 32:
        return None
    if items[3][0] != 0x02:                  # serialNumber
        return None
    if items[4][0] != 0x18:                  # genTime GeneralizedTime
        return None
    return {"hash": mi[1][1].hex(), "gen_time": items[4][1]}


def parse_gen_time(raw: bytes) -> str:
    m = _GEN_TIME.match(raw)
    if not m:
        return raw.decode("ascii", "replace")
    s = m.group(1).decode()
    dt = datetime.strptime(s, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def _openssl_verify(token: bytes, expected_hash: str, ca_file: str):
    """Проверка подписи TSA через openssl. Возвращает (ok, сообщение)."""
    import shutil, subprocess, tempfile
    with tempfile.TemporaryDirectory() as td:
        tp = os.path.join(td, "token.tsr")
        with open(tp, "wb") as fh:
            fh.write(token)
        try:
            r = subprocess.run(
                ["openssl", "ts", "-verify", "-digest", expected_hash.lower(),
                 "-in", tp, "-CAfile", ca_file],
                capture_output=True, text=True, timeout=60)
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            return False, f"openssl недоступен: {exc}"
        out = (r.stdout or "") + (r.stderr or "")
        ok = "Verification: OK" in out
        line = next((l.strip() for l in out.splitlines() if l.strip()), "")
        return ok, line or f"код {r.returncode}"


def verify_token(token: bytes, expected_hash: str,
                 ca_file: str | None = None) -> dict:
    """Сверяет токен TSA с корнем снимка.

    Два уровня. Структурный всегда: разбираем токен и сравниваем
    запечатанный хеш с корнем. Этого недостаточно — подмена байтов
    вне TSTInfo так не ловится, поэтому при наличии openssl и
    CA-сертификата выполняется криптографическая проверка подписи.

    Поле method в ответе говорит, чем подтверждён результат:
    "openssl" — подпись проверена; "structure" — только структура,
    и это обязательно показывать пользователю.
    """
    out = {"ok": False, "expected": expected_hash.lower()}
    try:
        info = _find_tstinfo(token)
    except Exception as exc:
        out.update(method="structure",
                   error=f"не удалось разобрать токен: {exc}")
        return out
    if not info:
        out.update(method="structure", error="TSTInfo в токене не найден")
        return out

    out["hash_in_token"] = info["hash"]
    out["gen_time"] = parse_gen_time(info["gen_time"])
    if info["hash"].lower() != expected_hash.lower():
        out.update(method="structure",
                   error="хеш в токене не совпадает с корнем снимка")
        return out

    # Структура сошлась. Пробуем проверить подпись по-настоящему.
    if not ca_file:
        ca_file = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "tsa", "freetsa-cacert.pem")

    if not os.path.exists(ca_file):
        out.update(ok=True, method="structure",
                   warning="подпись не проверена: нет CA-сертификата TSA")
        return out
    if not _has_openssl():
        out.update(ok=True, method="structure",
                   warning="подпись не проверена: openssl недоступен")
        return out

    ok, msg = _openssl_verify(token, expected_hash, ca_file)
    out["method"] = "openssl"
    out["openssl"] = msg
    out["ok"] = ok
    if not ok:
        out["error"] = f"подпись TSA не прошла проверку: {msg}"
    return out


def _has_openssl() -> bool:
    import shutil
    return shutil.which("openssl") is not None


# --- Запись якоря ---

def anchor_path(cfg) -> str:
    p = os.path.join(cfg.path("state_dir"), "anchors.log")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return p


def token_path(cfg, cycle: str, root: str) -> str:
    """Имя токена уникально для каждого корня.

    Один цикл можно якорить несколько раз — леджер растёт, корень
    меняется. Если имя зависит только от цикла, второй якорь молча
    перезапишет токен первого, и тот начнёт не проходить проверку.
    """
    d = os.path.join(cfg.path("state_dir"), "anchors")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{cycle}.{root[:12]}.tsr")


def build_payload(cfg, snap: dict) -> dict:
    return {
        "project": cfg.project,
        "cycle": snap["cycle"],
        "root": snap["root"],
        "snapshot_hash": snap["snapshot_hash"],
        "entries": snap["entries"],
        "awarded": snap["total_points"],
        "config_hash": cfg.hash,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


def write_anchor(cfg, snap: dict, target: str | None = None,
                 dry: bool | None = None) -> dict:
    payload = build_payload(cfg, snap)
    acfg = cfg.raw.get("anchor", {})
    tgt = target or acfg.get("target", "rfc3161")
    if dry is None:
        dry = bool(acfg.get("dry_run", True))

    record = {"ts": payload["ts"], "cycle": snap["cycle"],
              "target": tgt, "payload": payload}

    if dry:
        record["status"] = "dry-run"
        record["tx_hint"] = "<не отправлено, dry-run>"
        _append(anchor_path(cfg), record)
        return record

    if tgt != "rfc3161":
        raise RuntimeError(f"неизвестная цель якоря: {tgt}")

    url = acfg.get("url") or DEFAULT_TSA
    root = bytes.fromhex(snap["root"])
    req = build_timestamp_request(root)
    token = submit_timestamp_request(req, url)

    # Проверяем сразу: бесполезно хранить токен, который не подтверждающий наш хеш.
    check = verify_token(token, snap["root"])
    if not check.get("ok"):
        raise RuntimeError(
            f"TSA {url} вернул токен, не подтверждающий корень снимка: "
            f"{check.get('error')}")

    tp = token_path(cfg, snap["cycle"], snap["root"])
    with open(tp, "wb") as fh:
        fh.write(token)

    record["status"] = "submitted"
    record["tsa"] = url
    record["token"] = os.path.relpath(tp, cfg.root)
    record["token_sha256"] = _sha256(token)
    record["gen_time"] = check.get("gen_time")
    record["tx_hint"] = f"rfc3161:{url}"
    _append(anchor_path(cfg), record)
    return record


def _sha256(b: bytes) -> str:
    import hashlib
    return hashlib.sha256(b).hexdigest()


def _append(path: str, record: dict) -> None:
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True,
                            separators=(",", ":")) + "\n")
