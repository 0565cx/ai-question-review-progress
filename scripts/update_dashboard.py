#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自动生成「进度看板.md」（按轮次打勾版）。

每个岗位下有 5 个类型文件夹：
  1_待审核题目 / 2_保留题目 / 3_需重新出题 / 4_需重新出答案 / 5_审核结果看板

进度判定：根据文件名里的「轮次」前缀归集到各轮，逐轮检查 5 类是否就绪：
  - 待审核题表：1_待审核题目 里有「待N轮审核」文件
  - 保留题目：  2_保留题目 里有「N轮_…可保留」文件
  - 需重新出题：3_需重新出题 里有「N轮_…需要重新出题」文件
  - 需重新出答案：4_需重新出答案 里有「N轮_…重新出答案」文件
  - 审核看板：  5_审核结果看板 里有「N轮 / 第N轮」看板文件
每轮 5 类齐全打 ✅，部分打 🔄，无打 ⬜（仅展示已开始到的最大轮次 + 1）。

由 GitHub Actions 每次 push 后自动运行并提交。
"""
import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FOLDERS = {
    "待审题": "1_待审核题目",
    "保留": "2_保留题目",
    "重出题": "3_需重新出题",
    "重出答案": "4_需重新出答案",
    "看板": "5_审核结果看板",
    "汇总": "6_汇总",
}
# 语言问题审核的 4 个子文件夹（顺序即流程）
LANG_SUB = ["待语言问题审核", "一审结果", "待重出", "重出结果"]
LANG_DIRS = {
    "待语言问题审核": "7_语言问题审核/1_待语言问题审核",
    "一审结果": "7_语言问题审核/2_一审结果",
    "待重出": "7_语言问题审核/3_待重出",
    "重出结果": "7_语言问题审核/4_重出结果",
}
# 看板每轮展示的 5 个勾列
COLS = ["待审题表", "保留题目", "需重出题", "需重出答案", "审核看板"]
CN = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7,
      "八": 8, "九": 9, "十": 10}
MAX_ROUND = 7
DONE, DOING, TODO = "✅", "⬜", "⬜"  # 单元格只用 ✅/⬜（打勾或空）


def round_of(name: str):
    """从文件名解析轮次号。"""
    m = re.search(r"待([0-9一二三四五六七八九十])轮审核", name)
    if m:
        r = m.group(1)
        return int(r) if r.isdigit() else CN.get(r, 1)
    m = re.match(r"^([0-9]+)轮[_-]", name)
    if m:
        return int(m.group(1))
    m = re.search(r"第([0-9一二三四五六七八九十])轮", name)
    if m:
        r = m.group(1)
        return int(r) if r.isdigit() else CN.get(r, 1)
    m = re.search(r"([0-9])轮", name)
    if m:
        return int(m.group(1))
    return None


def list_files(d: Path):
    if not d.is_dir():
        return []
    return [p.name for p in d.rglob("*") if p.is_file() and p.name != ".gitkeep"]


def load_positions():
    rows = list(csv.DictReader(open(ROOT / "data" / "positions.csv", encoding="utf-8")))
    known = {r["path"] for r in rows}
    for d in ROOT.rglob("1_待审核题目"):
        pos = d.parent
        rel = pos.relative_to(ROOT).as_posix()
        if rel in known:
            continue
        parts = rel.split("/")
        rows.append({"path": rel, "招聘场景": parts[0], "行业": parts[1] if len(parts) > 1 else "",
                     "子行业": parts[2] if len(parts) > 2 else "",
                     "岗位类型": parts[-2], "岗位名称": parts[-1],
                     "分工": "", "知识审核时间": "", "语言审核时间": "", "基线完成阶段": "-1"})
        known.add(rel)
    return rows


def analyze(pos_dir: Path):
    """返回 (got, files, max_r, extra)。
    got:   {round: set(已就绪的列)}
    files: {round: {列: [文件名,...]}}
    extra: {"汇总": [文件], "语言": {子项: [文件]}}
    """
    got = {}
    files = {}

    def add(col, names):
        for n in names:
            r = round_of(n) or 1
            got.setdefault(r, set()).add(col)
            files.setdefault(r, {}).setdefault(col, []).append(n)

    add("待审题表", list_files(pos_dir / FOLDERS["待审题"]))
    add("保留题目", list_files(pos_dir / FOLDERS["保留"]))
    add("需重出题", list_files(pos_dir / FOLDERS["重出题"]))
    add("需重出答案", list_files(pos_dir / FOLDERS["重出答案"]))
    add("审核看板", list_files(pos_dir / FOLDERS["看板"]))

    extra = {"汇总": list_files(pos_dir / FOLDERS["汇总"]),
             "语言": {k: list_files(pos_dir / v) for k, v in LANG_DIRS.items()}}

    max_r = max(got.keys(), default=0)
    return got, files, max_r, extra


def status_badge(max_r, got):
    if max_r == 0:
        return "🟥 待出题"
    if max_r <= 2:
        return "🟨 进行至一二轮"
    return f"🟨 进行至第{max_r}轮"


def display_slots(got, files, grp_max):
    """把内部轮次合并成展示槽位：第1、2轮 → 「一二轮」，第3轮起单列。
    返回 [(label, got_set, files_map), ...]
    """
    slots = []
    # 一二轮：合并 round 1 与 2
    g12 = set(got.get(1, set())) | set(got.get(2, set()))
    f12 = {}
    for rd in (1, 2):
        for col, names in files.get(rd, {}).items():
            f12.setdefault(col, []).extend(names)
    slots.append(("一二轮", g12, f12))
    # 第3轮及以后
    for rd in range(3, max(grp_max, 2) + 1):
        slots.append((f"第{rd}轮", set(got.get(rd, set())), files.get(rd, {})))
    return slots


HTML_HEAD = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>8月迭代 · 各岗位审题进度看板</title>
<style>
:root{--g:#2ea043;--gray:#e6e8eb;--txt:#1f2328;--mut:#656d76;--bd:#d0d7de;--bg:#f6f8fa}
*{box-sizing:border-box}
body{margin:0;font-family:-apple-system,"PingFang SC","Microsoft YaHei",Segoe UI,sans-serif;color:var(--txt);background:#fff;padding:20px}
h1{font-size:22px;margin:0 0 4px}
.sub{color:var(--mut);font-size:13px;margin-bottom:16px}
.stats{display:flex;gap:18px;flex-wrap:wrap;margin:14px 0 20px;font-size:14px}
.stats b{font-size:20px}
.legend{background:var(--bg);border:1px solid var(--bd);border-radius:8px;padding:10px 14px;font-size:13px;margin-bottom:22px;line-height:1.9}
.legend .cell{display:inline-flex;vertical-align:middle;margin:0 6px}
h2{font-size:16px;margin:26px 0 10px;padding-bottom:6px;border-bottom:2px solid var(--bg)}
table{border-collapse:collapse;width:100%;margin-bottom:8px;font-size:13px}
th,td{border:1px solid var(--bd);padding:7px 9px;text-align:center;white-space:nowrap}
th{background:var(--bg);font-weight:600;position:sticky;top:0}
td.pos{text-align:left;font-weight:600}
td.who{color:var(--mut)}
td.grp{text-align:left;vertical-align:middle;background:#fbfcfd;font-weight:600;color:#444}
.badge{display:inline-block;padding:2px 9px;border-radius:20px;font-size:12px;white-space:nowrap}
.b-todo{background:#ffeef0;color:#cf222e}
.b-doing{background:#fff8c5;color:#9a6700}
.cell{display:inline-flex;gap:3px}
.dot{width:13px;height:13px;border-radius:3px;background:var(--gray);cursor:default;display:inline-block}
.dot.on{background:var(--g)}
.empty{color:#afb8c1}
.tip{position:relative}
.tip:hover::after{content:attr(data-tip);position:absolute;left:50%;bottom:130%;transform:translateX(-50%);
 background:#1f2328;color:#fff;padding:7px 10px;border-radius:6px;font-size:12px;white-space:pre-line;
 z-index:9;min-width:160px;max-width:320px;text-align:left;box-shadow:0 4px 14px rgba(0,0,0,.18)}
.foot{color:var(--mut);font-size:12px;margin-top:24px;border-top:1px solid var(--bg);padding-top:12px}
</style>
</head>
<body>
"""


def build_html(rows, order, total, n_todo, n_doing):
    import html as _html
    COLS_ABBR = ["待审题表", "保留题目", "需重出题", "需重出答案", "审核看板"]
    P = []
    P.append(HTML_HEAD)
    P.append('<h1>8月迭代 · 各岗位审题进度看板</h1>')
    P.append('<div class="sub">🤖 由 GitHub Actions 自动生成 · 把文件传到岗位对应文件夹后自动刷新</div>')

    P.append('<div class="stats">'
             f'<span>岗位总数 <b>{total}</b></span>'
             f'<span>🟥 未开始 <b>{n_todo}</b></span>'
             f'<span>🟨 进行中 <b>{n_doing}</b></span>'
             '</div>')

    # 图例
    P.append('<div class="legend">'
             '<b>每一轮的格子由 5 个小方块组成，从左到右依次是：</b><br>'
             '① 待审题表　② 保留题目　③ 需重出题　④ 需重出答案　⑤ 审核看板<br>'
             '<span class="cell">'
             '<span class="dot on"></span><span class="dot"></span>'
             '<span class="dot on"></span><span class="dot"></span>'
             '<span class="dot on"></span></span>'
             '　绿色 = 已上传，灰色 = 待上传　·　鼠标悬停格子可看具体文件名<br>'
             '<b>汇总</b>：全部轮次完成后最终保留的题目　·　'
             '<b>语言审核</b>（4格）：① 待语言问题审核　② 一审结果　③ 待重出　④ 重出结果'
             '</div>')

    def render_cell(got_set, files_map):
        """一轮 → 5个方块的 HTML，带悬停文件名。"""
        if not got_set:
            return '<span class="empty">—</span>'
        blocks = ""
        tips = []
        for c in COLS_ABBR:
            on = c in got_set
            blocks += f'<span class="dot{" on" if on else ""}"></span>'
            if on:
                fs = files_map.get(c, [])
                tips.append(f"✅ {c}：\n" + "\n".join("· " + _html.escape(x) for x in fs))
            else:
                tips.append(f"○ {c}：待上传")
        tip = _html.escape("\n".join(tips)).replace("&#x27;", "'")
        return f'<span class="cell tip" data-tip="{tip}">{blocks}</span>'

    def render_single(names, label):
        """单文件夹（如汇总）→ 1个方块。"""
        on = bool(names)
        tip = (f"✅ {label}：\n" + "\n".join("· " + _html.escape(x) for x in names)) if on \
            else f"○ {label}：待上传"
        tip = _html.escape(tip).replace("&#x27;", "'")
        return (f'<span class="cell tip" data-tip="{tip}">'
                f'<span class="dot{" on" if on else ""}"></span></span>')

    def render_lang(lang_map):
        """语言审核 → 4个方块（待审/一审结果/待重出/重出结果）。"""
        if not any(lang_map.values()):
            return '<span class="empty">—</span>'
        blocks = ""
        tips = []
        for k in LANG_SUB:
            fs = lang_map.get(k, [])
            on = bool(fs)
            blocks += f'<span class="dot{" on" if on else ""}"></span>'
            if on:
                tips.append(f"✅ {k}：\n" + "\n".join("· " + _html.escape(x) for x in fs))
            else:
                tips.append(f"○ {k}：待上传")
        tip = _html.escape("\n".join(tips)).replace("&#x27;", "'")
        return f'<span class="cell tip" data-tip="{tip}">{blocks}</span>'

    # 单张大表：全局最大轮次对齐，行业/子行业作为左侧列
    global_max = max((r["_max"] for r in rows), default=2)
    slot_labels = [s[0] for s in display_slots({}, {}, global_max)]
    head = ('<table><tr><th style="text-align:left">行业</th>'
            '<th style="text-align:left">子行业</th>'
            '<th style="text-align:left">岗位</th><th>分工</th><th>状态</th>')
    for lab in slot_labels:
        head += f'<th>{lab}</th>'
    head += '<th>汇总</th><th>语言审核</th></tr>'
    P.append(head)

    # 计算每个 (行业,子行业) 的行数，用于 rowspan 合并
    for ind, sub in order:
        rs = [r for r in rows if r.get("行业", "") == ind and
              (r.get("子行业", "") or "（无子行业）") == sub]
        for i, r in enumerate(rs):
            if r["_max"] == 0:
                badge = '<span class="badge b-todo">待出题</span>'
            elif r["_max"] <= 2:
                badge = '<span class="badge b-doing">进行至一二轮</span>'
            else:
                badge = f'<span class="badge b-doing">进行至第{r["_max"]}轮</span>'
            row = "<tr>"
            if i == 0:
                row += f'<td class="grp" rowspan="{len(rs)}">{_html.escape(ind)}</td>'
                row += f'<td class="grp" rowspan="{len(rs)}">{_html.escape(sub)}</td>'
            row += (f'<td class="pos">{_html.escape(r.get("岗位名称",""))}</td>'
                    f'<td class="who">{_html.escape(r.get("分工","") or "—")}</td>'
                    f'<td>{badge}</td>')
            for lab, gset, fmap in display_slots(r["_got"], r["_files"], global_max):
                row += '<td>' + render_cell(gset, fmap) + '</td>'
            row += '<td>' + render_single(r["_extra"]["汇总"], "汇总题目") + '</td>'
            row += '<td>' + render_lang(r["_extra"]["语言"]) + '</td>'
            row += '</tr>'
            P.append(row)
    P.append('</table>')

    import datetime as _dt
    ts = _dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    P.append(f'<div class="foot">最后更新：{ts}　·　数据来源：仓库各岗位文件夹</div>')
    P.append('</body></html>')
    (ROOT / "index.html").write_text("\n".join(P), encoding="utf-8")


def main():
    rows = load_positions()
    for r in rows:
        got, files, max_r, extra = analyze(ROOT / r["path"])
        r["_got"] = got
        r["_files"] = files
        r["_max"] = max_r
        r["_extra"] = extra

    total = len(rows)
    n_todo = sum(1 for r in rows if r["_max"] == 0)
    n_doing = total - n_todo

    L = []
    L.append("# 8月迭代 · 各岗位审题进度看板")
    L.append("")
    L.append("> 🤖 本看板由 GitHub Actions **自动生成**：把文件传到岗位对应的类型文件夹后，进度自动刷新，无需手动改。")
    L.append("")
    L.append("**每个圆点格代表一轮审核应交的 5 份文件，顺序固定：**")
    L.append("")
    L.append("> ① 待审题表　② 保留题目　③ 需重出题　④ 需重出答案　⑤ 审核看板　——　● = 已上传，○ = 待上传")
    L.append("")
    L.append("> **汇总**：全部轮次完成后最终保留的题目（● = 已传）。**语言审核**：4 个环节顺序为 ① 待语言问题审核　② 一审结果　③ 待重出　④ 重出结果。")
    L.append("")
    L.append("## 总览")
    L.append("")
    L.append(f"- 岗位总数：**{total}**　🟥 未开始：**{n_todo}**　🟨 进行中：**{n_doing}**")
    L.append("- 每个岗位下固定 5 个文件夹：`1_待审核题目`/`2_保留题目`/`3_需重新出题`/`4_需重新出答案`/`5_审核结果看板`")
    L.append("")

    order = []
    for r in rows:
        k = (r.get("行业", ""), r.get("子行业", "") or "（无子行业）")
        if k not in order:
            order.append(k)

    def dots(got_set):
        return "".join("●" if c in got_set else "○" for c in COLS)

    def lang_dots(lang_map):
        if not any(lang_map.values()):
            return "—"
        return "".join("●" if lang_map.get(k) else "○" for k in LANG_SUB)

    L.append("## 进度明细")
    L.append("")
    global_max = max((r["_max"] for r in rows), default=2)
    slot_labels = [s[0] for s in display_slots({}, {}, global_max)]
    head = "| 行业 | 子行业 | 岗位 | 分工 | 状态 |"
    sep = "|---|---|---|---|---|"
    for lab in slot_labels:
        head += f" {lab} |"
        sep += ":-:|"
    head += " 汇总 | 语言审核 |"
    sep += ":-:|:-:|"
    L.append(head)
    L.append(sep)
    for ind, sub in order:
        rs = [r for r in rows if r.get("行业", "") == ind and
              (r.get("子行业", "") or "（无子行业）") == sub]
        for i, r in enumerate(rs):
            # 同组只在首行显示行业/子行业，其余留空，视觉上对齐成块
            c_ind = ind if i == 0 else ""
            c_sub = sub if i == 0 else ""
            line = (f"| {c_ind} | {c_sub} | {r.get('岗位名称','')} | "
                    f"{r.get('分工','') or '—'} | {status_badge(r['_max'], r['_got'])} |")
            for lab, gset, fmap in display_slots(r["_got"], r["_files"], global_max):
                line += f" {dots(gset) if gset else '—'} |"
            line += f" {'●' if r['_extra']['汇总'] else '○'} | {lang_dots(r['_extra']['语言'])} |"
            L.append(line)
    L.append("")

    L.append("---")
    L.append("## 文件夹说明")
    L.append("")
    L.append("| 文件夹 | 放什么 |")
    L.append("|---|---|")
    L.append("| `1_待审核题目` | 各轮「待N轮审核」的题目表 |")
    L.append("| `2_保留题目` | 各轮审核后可保留的题目（统一放，不分轮） |")
    L.append("| `3_需重新出题` | 各轮审核后需要重新出题的清单 |")
    L.append("| `4_需重新出答案` | 各轮审核后需要重新出答案的清单 |")
    L.append("| `5_审核结果看板` | 各轮审核后生成的看板 |")
    L.append("| `6_汇总` | 全部轮次审核完成后最终保留的所有题目 |")
    L.append("| `7_语言问题审核/1_待语言问题审核` | 待语言问题审核的题目 |")
    L.append("| `7_语言问题审核/2_一审结果` | 语言问题一审结果 |")
    L.append("| `7_语言问题审核/3_待重出` | 语言问题待重出清单 |")
    L.append("| `7_语言问题审核/4_重出结果` | 语言问题重出结果 |")
    L.append("")

    (ROOT / "进度看板.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"已生成进度看板.md（{total} 个岗位）")

    build_html(rows, order, total, n_todo, n_doing)
    print("已生成 index.html")


if __name__ == "__main__":
    main()
