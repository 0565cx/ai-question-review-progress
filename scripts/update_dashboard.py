#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自动生成「进度看板.md」。

进度判定规则：
- 每个岗位目录下有 10 个审核阶段子文件夹（00~09）。
- 某个阶段「已有文件」= 该子文件夹里存在 .gitkeep 以外的文件。
- 岗位「已完成到的阶段」= 文件夹里有文件的最大阶段；并与 data/positions.csv
  里的「基线完成阶段」取较大值（基线来自原共享表格的已知进度）。
- 看板每格：已完成阶段 ✅，下一个阶段 🔄，其余 ⬜。

本脚本由 GitHub Actions 在每次 push 后自动运行并提交结果，无需手动维护。
"""
import csv
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 10 个审核阶段子文件夹（与目录一一对应，顺序即流程顺序）
STAGES = [
    "00_待审核题表",
    "01_一审二审（含二审结果·重新出题）",
    "02_三审（含三审结果·重新出题）",
    "03_四审（含四审结果·重新出题）",
    "04_五审（含五审结果·重新出题）",
    "05_六审（含六审结果·重新出题）",
    "06_七审（含七审结果·重新出题）",
    "07_最后一轮重出",
    "08_各轮审核结果看板与汇总",
    "09_题干语言问题审核",
]
# 看板里显示的列名（更短）
COL_NAMES = ["待审核题表", "一审二审", "三审", "四审", "五审",
             "六审", "七审", "最后重出", "看板汇总", "语言审核"]
# 下一个阶段对应的状态文字
NEXT_LABEL = ["待上传题表", "待一审/二审", "待三审", "待四审", "待五审",
              "待六审", "待七审", "待最后重出", "待看板汇总", "待语言审核"]

DONE, DOING, TODO = "✅", "🔄", "⬜"


def stage_has_files(stage_dir: Path) -> bool:
    if not stage_dir.is_dir():
        return False
    for p in stage_dir.rglob("*"):
        if p.is_file() and p.name != ".gitkeep":
            return True
    return False


def folder_completed_index(pos_dir: Path) -> int:
    """文件夹里有文件的最大阶段索引；都没有则 -1。"""
    last = -1
    for i, st in enumerate(STAGES):
        if stage_has_files(pos_dir / st):
            last = i
    return last


def load_positions():
    csv_path = ROOT / "data" / "positions.csv"
    rows = []
    if csv_path.exists():
        with open(csv_path, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    known = {r["path"] for r in rows}
    # 发现 CSV 里没有、但目录中新增的岗位（包含 00_ 子文件夹即视为岗位叶子）
    for d in ROOT.rglob(STAGES[0]):
        pos_dir = d.parent
        rel = pos_dir.relative_to(ROOT).as_posix()
        if rel in known:
            continue
        parts = rel.split("/")
        rows.append({
            "path": rel,
            "招聘场景": parts[0] if len(parts) > 0 else "",
            "行业": parts[1] if len(parts) > 1 else "",
            "子行业": parts[2] if len(parts) > 2 else "",
            "岗位类型": parts[-2] if len(parts) >= 2 else "",
            "岗位名称": parts[-1],
            "分工": "", "知识审核时间": "", "语言审核时间": "",
            "基线完成阶段": "-1",
        })
        known.add(rel)
    return rows


def uploaded_files(pos_dir: Path):
    names = []
    for st in STAGES:
        d = pos_dir / st
        if d.is_dir():
            for p in sorted(d.rglob("*")):
                if p.is_file() and p.name != ".gitkeep":
                    names.append(p.name)
    return names


def cells(completed: int):
    out = []
    for i in range(len(STAGES)):
        if i <= completed:
            out.append(DONE)
        elif i == completed + 1 and completed >= 0:
            out.append(DOING)
        else:
            out.append(TODO)
    return out


def badge(completed: int):
    if completed < 0:
        return "🟥 待出题"
    if completed >= len(STAGES) - 1:
        return "🟩 已完成"
    return "🟨 " + NEXT_LABEL[completed + 1]


def main():
    rows = load_positions()
    # 计算每个岗位的完成阶段
    for r in rows:
        pos_dir = ROOT / r["path"]
        baseline = int(r.get("基线完成阶段", "-1") or "-1")
        completed = max(baseline, folder_completed_index(pos_dir))
        r["_completed"] = completed
        r["_files"] = uploaded_files(pos_dir)

    total = len(rows)
    n_todo = sum(1 for r in rows if r["_completed"] < 0)
    n_doing = sum(1 for r in rows if 0 <= r["_completed"] < len(STAGES) - 1)
    n_done = sum(1 for r in rows if r["_completed"] >= len(STAGES) - 1)

    L = []
    L.append("# 8月迭代 · 各岗位审题进度看板")
    L.append("")
    L.append("> 🤖 本看板由 GitHub Actions **自动生成**：每当有人往岗位的审核阶段文件夹里"
             "上传文件，进度就会自动刷新，无需手动修改本文件。")
    L.append("> 进度依据 = 各阶段文件夹中是否已上传文件（与 `data/positions.csv` 里的基线进度取较大值）。")
    L.append("")
    L.append("## 总览")
    L.append("")
    L.append(f"- 岗位总数：**{total}**")
    L.append(f"- 🟥 待出题：**{n_todo}**　🟨 进行中：**{n_doing}**　🟩 已完成：**{n_done}**")
    L.append("- 图例：✅ 已完成　🔄 进行中　⬜ 未开始")
    L.append("")

    # 按 行业 / 子行业 分组
    order = []
    for r in rows:
        k = (r.get("行业", ""), r.get("子行业", "") or "（无子行业）")
        if k not in order:
            order.append(k)

    hdr = "| 岗位类型 | 岗位名称 | 分工 | 知识审核时间 | 语言审核时间 | 状态 | " + \
          " | ".join(COL_NAMES) + " | 已上传文件 |"
    sep = "|---|---|---|---|---|---|" + ":-:|" * len(COL_NAMES) + "---|"

    L.append("## 进度明细（按子行业分组）")
    L.append("")
    for ind, sub in order:
        rs = [r for r in rows if r.get("行业", "") == ind and
              (r.get("子行业", "") or "（无子行业）") == sub]
        L.append(f"### {ind} / {sub}")
        L.append("")
        L.append(hdr)
        L.append(sep)
        for r in rs:
            cc = cells(r["_completed"])
            files = "；".join(r["_files"]) if r["_files"] else "—"
            L.append("| " + " | ".join([
                r.get("岗位类型", ""), r.get("岗位名称", ""), r.get("分工", "") or "—",
                r.get("知识审核时间", "") or "—", r.get("语言审核时间", "") or "—",
                badge(r["_completed"]), *cc, files]) + " |")
        L.append("")

    L.append("---")
    L.append("## 列名与文件夹对应关系")
    L.append("")
    L.append("| 阶段文件夹 | 对应共享表格列 |")
    L.append("|---|---|")
    mapping = [
        ("00_待审核题表", "待审核题表"),
        ("01_一审二审…", "一审 / 二审 / 二审结果 / 重新出题"),
        ("02_三审…", "待三审 / 三审 / 三审结果 / 重新出题"),
        ("03_四审…", "待四审 / 四审 / 四审结果 / 重新出题"),
        ("04_五审…", "待五审 / 五审 / 五审结果 / 重新出题"),
        ("05_六审…", "待六审 / 六审 / 六审结果 / 重新出题"),
        ("06_七审…", "待七审 / 七审 / 七审结果"),
        ("07_最后一轮重出", "最后一轮重出"),
        ("08_各轮审核结果看板与汇总", "各轮审核结果看板 / 汇总"),
        ("09_题干语言问题审核", "待语言问题审核 / 题干语言问题一审 / 一审结果 / 待重出 / 言语重出 / 题干语言问题二审"),
    ]
    for a, b in mapping:
        L.append(f"| `{a}` | {b} |")
    L.append("")

    out = ROOT / "进度看板.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"已生成 {out}（{total} 个岗位）")


if __name__ == "__main__":
    main()
