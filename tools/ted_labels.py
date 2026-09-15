#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Разбор извещений TED: из XML — структурированные поля.

    python3 tools/ted_labels.py corpus/raw/ corpus/labels/labels.jsonl

Метки берутся из кодированных полей извещения (суммы, коды CPV, коды
процедур). Это и есть разметка: она уже существует в XML, поэтому ручную
разметку с нуля делать не нужно.

Входом для модели в этой задаче служит НЕ этот XML, а человекочитаемый
текст извещения. Если скормить модели сам XML, она выучит разбирать
разметку, а не понимать документ, — задача станет бессмысленной.
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
import xml.etree.ElementTree as ET


def tag(el) -> str:
    return re.sub(r"\{[^}]*\}", "", el.tag)


def walk(root):
    for el in root.iter():
        yield tag(el), el


def first_text(root, names) -> str:
    for t, el in walk(root):
        if t in names and el.text and el.text.strip():
            return " ".join(el.text.split())
    return ""


def all_text(root, name) -> list:
    out = []
    for t, el in walk(root):
        if t == name and el.text and el.text.strip():
            v = " ".join(el.text.split())
            if v not in out:
                out.append(v)
    return out


def amounts(root) -> list:
    """Суммы с валютой: (значение, валюта)."""
    out = []
    for t, el in walk(root):
        if t in ("PayableAmount", "TotalAmount", "TaxInclusiveAmount"):
            try:
                v = float((el.text or "").strip())
            except (TypeError, ValueError):
                continue
            cur = el.attrib.get("currencyID", "")
            pair = (v, cur)
            if pair not in out:
                out.append(pair)
    return out


def buyer(root) -> str:
    """Заказчик. Ищем внутри ContractingParty, иначе — первое имя стороны."""
    for t, el in walk(root):
        if t == "ContractingParty":
            for t2, el2 in walk(el):
                if t2 == "Name" and el2.text and el2.text.strip():
                    return " ".join(el2.text.split())
    return first_text(root, {"PartyName"}) or first_text(root, {"Name"})


def parse(path: str) -> dict:
    root = ET.parse(path).getroot()
    doc_type = tag(root)
    amts = amounts(root)
    return {
        "file": os.path.basename(path),
        "doc_type": doc_type,
        "notice_id": first_text(root, {"ContractFolderID", "ID"}),
        "buyer": buyer(root),
        "country": first_text(root, {"IdentificationCode"}),
        "company_id": first_text(root, {"CompanyID"}),
        "values": [{"amount": a, "currency": c} for a, c in amts],
        "cpv": all_text(root, "ItemClassificationCode"),
        "procurement_type": first_text(root, {"ProcurementTypeCode"}),
        "procedure_code": first_text(root, {"ProcedureCode"}),
        "titles": all_text(root, "Title"),
        "descriptions": all_text(root, "Description"),
        "deadline_date": first_text(root, {"EndDate"}),
        "deadline_time": first_text(root, {"EndTime"}),
    }


def main(argv) -> int:
    src = argv[1] if len(argv) > 1 else "corpus/raw"
    dst = argv[2] if len(argv) > 2 else "corpus/labels/labels.jsonl"

    files = sorted(glob.glob(os.path.join(src, "*.xml")))
    if not files:
        print(f"нет XML в {src}")
        return 1

    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    rows = []
    for f in files:
        try:
            rows.append(parse(f))
        except ET.ParseError as exc:
            print(f"  пропуск {f}: {exc}")
        except Exception as exc:  # не даём одному файлу уронить прогон
            print(f"  ошибка {f}: {exc}")

    with open(dst, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")

    filled = lambda k: sum(1 for r in rows if r.get(k))
    print(f"разобрано {len(rows)} извещений → {dst}")
    for k in ("buyer", "country", "values", "cpv", "procedure_code",
              "procurement_type"):
        print(f"  {k:18s} заполнено у {filled(k)}/{len(rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
