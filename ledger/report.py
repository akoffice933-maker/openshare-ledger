#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HTML-отчёт по состоянию реестра (без внешних зависимостей)."""
from __future__ import annotations

import html
import json
import os
from datetime import datetime, timezone

KIND_LABEL = {
    "data": "Данные", "model": "Модель", "eval": "Проверка",
    "compute": "Compute", "code": "Код", "docs": "Документация",
}


def render(cfg, ledger, snap: dict | None, anchors: list[dict]) -> str:
    accounts = ledger.totals()
    ranked = sorted(accounts.values(), key=lambda a: -a["points"])
    total = ledger.total_points()
    contribs = ledger.contributions()
    ok, msg = ledger.verify()

    rows = []
    for i, a in enumerate(ranked, 1):
        share = (a["points"] / total * 100) if total else 0
        kinds = " · ".join(
            f"{KIND_LABEL.get(k, k)} {v:.0f}" for k, v in
            sorted(a["by_kind"].items(), key=lambda kv: -kv[1]) if v > 0)
        rows.append(f"""<tr>
<td class="rank">{i}</td>
<td><div class="name">{html.escape(a['name'])}</div>
<div class="mail">{html.escape(a['email'])}</div></td>
<td class="num">{a['points']:.2f}</td>
<td class="num">{share:.1f}%</td>
<td class="num">{a['contributions']}</td>
<td class="kinds">{html.escape(kinds or '—')}</td>
</tr>""")

    by_kind: dict[str, float] = {}
    for c in contribs:
        by_kind[c["kind"]] = by_kind.get(c["kind"], 0.0) + c["points"]
    kind_rows = "".join(
        f"""<tr><td>{html.escape(KIND_LABEL.get(k, k))}</td>
<td class="num">{v:.2f}</td>
<td class="num">{(v / total * 100) if total else 0:.1f}%</td></tr>"""
        for k, v in sorted(by_kind.items(), key=lambda kv: -kv[1]))

    rejected = [c for c in contribs if not c["ok"]]
    rej_rows = "".join(
        f"""<tr><td>{html.escape(c['contributor'])}</td>
<td>{html.escape(KIND_LABEL.get(c['kind'], c['kind']))}</td>
<td class="reason">{html.escape('; '.join(c['reasons']) or '—')}</td></tr>"""
        for c in rejected)

    anchor_rows = "".join(
        f"""<tr><td>{html.escape(a['cycle'])}</td>
<td><code>{a['payload']['root'][:16]}…</code></td>
<td>{html.escape(a['target'])}</td><td>{html.escape(a['status'])}</td></tr>"""
        for a in anchors[-6:])

    snap_block = ""
    if snap:
        snap_block = f"""
<div class="grid">
  <div class="card"><div class="k">Цикл</div><div class="v">{html.escape(snap['cycle'])}</div></div>
  <div class="card"><div class="k">Начислено за цикл</div><div class="v">{snap['cycle_points']:.2f}</div></div>
  <div class="card"><div class="k">Бюджет цикла</div><div class="v">{snap['cycle_budget']:.0f}</div></div>
  <div class="card"><div class="k">Участников</div><div class="v">{snap['contributors']}</div></div>
</div>"""

    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<title>Реестр вкладов — {html.escape(cfg.project)}</title>
<style>
:root{{--bg:#0b0e1a;--card:#131829;--line:#232a44;--txt:#e8ecf8;--mut:#93a2c4;--acc:#5ee0c8;--warn:#ffb86b}}
*{{box-sizing:border-box}}
body{{margin:0;padding:40px 32px;background:var(--bg);color:var(--txt);
font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}}
.wrap{{max-width:1040px;margin:0 auto}}
h1{{font-size:30px;margin:0 0 6px;letter-spacing:-.02em}}
h2{{font-size:17px;margin:38px 0 14px;color:var(--mut);text-transform:uppercase;letter-spacing:.08em}}
.sub{{color:var(--mut);margin-bottom:8px}}
.badge{{display:inline-block;padding:5px 12px;border-radius:999px;font-size:13px;
background:{'rgba(94,224,200,.12)' if ok else 'rgba(255,184,107,.14)'};
color:{'var(--acc)' if ok else 'var(--warn)'};border:1px solid {'rgba(94,224,200,.3)' if ok else 'rgba(255,184,107,.35)'}}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-top:22px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 18px}}
.k{{color:var(--mut);font-size:12px;text-transform:uppercase;letter-spacing:.07em}}
.v{{font-size:26px;font-weight:700;margin-top:6px}}
table{{width:100%;border-collapse:collapse;background:var(--card);
border:1px solid var(--line);border-radius:14px;overflow:hidden}}
th{{text-align:left;font-size:12px;text-transform:uppercase;letter-spacing:.06em;
color:var(--mut);padding:12px 14px;background:rgba(255,255,255,.02)}}
td{{padding:12px 14px;border-top:1px solid var(--line);vertical-align:top}}
.num{{text-align:right;font-variant-numeric:tabular-nums}}
.rank{{color:var(--mut);width:38px}}
.name{{font-weight:600}}
.mail{{color:var(--mut);font-size:12px}}
.kinds{{color:var(--mut);font-size:13px}}
.reason{{color:var(--warn);font-size:13px}}
code{{color:var(--acc);font-size:12px}}
.foot{{color:var(--mut);font-size:12px;margin-top:34px;border-top:1px solid var(--line);padding-top:16px}}
</style></head><body><div class="wrap">
<h1>Реестр вкладов · {html.escape(cfg.project)}</h1>
<div class="sub">Публичный снимок: кто, что и когда внёс в проект. Append-only.</div>
<div class="sub">Цепочка: <span class="badge">{html.escape(msg)}</span></div>
{snap_block}
<h2>Участники</h2>
<table><thead><tr><th>#</th><th>Участник</th><th class="num">Points</th>
<th class="num">Доля</th><th class="num">Вкладов</th><th>По типам</th></tr></thead>
<tbody>{''.join(rows) or '<tr><td colspan="6">Пока нет данных</td></tr>'}</tbody></table>
<h2>Распределение по типам вклада</h2>
<table><thead><tr><th>Тип</th><th class="num">Points</th><th class="num">Доля</th></tr></thead>
<tbody>{kind_rows or '<tr><td colspan="3">—</td></tr>'}</tbody></table>
<h2>Отклонённые вклады ({len(rejected)})</h2>
<table><thead><tr><th>Участник</th><th>Тип</th><th>Причина</th></tr></thead>
<tbody>{rej_rows or '<tr><td colspan="3">Отклонённых нет</td></tr>'}</tbody></table>
<h2>Якоря</h2>
<table><thead><tr><th>Цикл</th><th>Корень</th><th>Сеть</th><th>Статус</th></tr></thead>
<tbody>{anchor_rows or '<tr><td colspan="4">Якорей пока нет</td></tr>'}</tbody></table>
<div class="foot">Сформировано {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} ·
Points не имеют денежной стоимости, не передаются и не дают права на выплаты.</div>
</div></body></html>"""


def write(cfg, ledger, snap, anchors, out_path: str) -> str:
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    html_str = render(cfg, ledger, snap, anchors)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html_str)
    return out_path
