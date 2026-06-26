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
    """返回 {round: set(已就绪的列)} 与最大轮次。"""
    got = {}  # round -> set(col)

    待 = list_files(pos_dir / FOLDERS["待审题"])
    保 = list_files(pos_dir / FOLDERS["保留"])
    题 = list_files(pos_dir / FOLDERS["重出题"])
    答 = list_files(pos_dir / FOLDERS["重出答案"])
    板 = list_files(pos_dir / FOLDERS["看板"])

    for n in 待:
        r = round_of(n) or 1
        got.setdefault(r, set()).add("待审题表")
    for n in 保:
        r = round_of(n) or 1
        got.setdefault(r, set()).add("保留题目")
    for n in 题:
        r = round_of(n) or 1
        got.setdefault(r, set()).add("需重出题")
    for n in 答:
        r = round_of(n) or 1
        got.setdefault(r, set()).add("需重出答案")
    for n in 板:
        r = round_of(n) or 1
        got.setdefault(r, set()).add("审核看板")

    max_r = max(got.keys(), default=0)
    return got, max_r


def status_badge(max_r, got):
    if max_r == 0:
        return "🟥 待出题"
    # 若最大轮的待审题表已传但还没出审核结果，视为进行中
    return f"🟨 进行至第{max_r}轮"


def main():
    rows = load_positions()
    for r in rows:
        got, max_r = analyze(ROOT / r["path"])
        r["_got"] = got
        r["_max"] = max_r

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

    L.append("## 进度明细（按子行业分组）")
    L.append("")
    for ind, sub in order:
        rs = [r for r in rows if r.get("行业", "") == ind and
              (r.get("子行业", "") or "（无子行业）") == sub]
        L.append(f"### {ind} / {sub}")
        L.append("")
        grp_max = max((r["_max"] for r in rs), default=0)
        show_rounds = max(grp_max, 1)
        head = "| 岗位 | 分工 | 状态 |"
        sep = "|---|---|---|"
        for rd in range(1, show_rounds + 1):
            head += f" 第{rd}轮 |"
            sep += ":-:|"
        L.append(head)
        L.append(sep)
        for r in rs:
            line = f"| {r.get('岗位名称','')} | {r.get('分工','') or '—'} | {status_badge(r['_max'], r['_got'])} |"
            for rd in range(1, show_rounds + 1):
                got = r["_got"].get(rd, set())
                line += f" {dots(got) if got else '—'} |"
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
    L.append("")

    (ROOT / "进度看板.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"已生成进度看板.md（{total} 个岗位）")


if __name__ == "__main__":
    main()
