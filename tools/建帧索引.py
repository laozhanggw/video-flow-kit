#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
建帧索引：把图片包里的帧，变成一张「秒 -> 帧文件」的表。

为什么要有它
--------------------------
2026-10-30。原来下游三段（③ 开头 / ④ 小分镜 / ⑤ 生产单元）只读文字表，
没看过原片，于是「手在哪、两个人站多近、盘子朝哪边」这类文字写不出的东西
只能靠猜。而拆解阶段其实已经抽好了帧，文件名里就带着精确秒数
（形如 F000012_00000.200000s.jpg），只是没人把它们和 4.5 表的秒数连起来。

这个脚本只做一件事：把帧文件名解析成秒，输出一张索引表。
它不判断内容、不改任何素材、不复制图片（105MB 不重复占地方）。

用法
--------------------------
  python 建帧索引.py "<图片包目录>" --out "<01_原片证据>"
  python 建帧索引.py "<图片包目录>" --out "<01_原片证据>" --from 0 --to 3.0

输出（都在 --out 目录下）
--------------------------
  帧索引.csv        秒,帧号,文件名,相对路径
  00_帧索引.md      人读版：怎么用、每段从哪一帧看到哪一帧

退出码
--------------------------
  0 成功；2 找不到 frames 目录或没有可解析的帧。
"""
import argparse
import csv
import io
import os
import re
import sys

PAT = re.compile(r"^F(\d+)_(\d+\.\d+)s\.[A-Za-z]+$")


def scan(frames_dir):
    rows = []
    for name in os.listdir(frames_dir):
        m = PAT.match(name)
        if not m:
            continue
        rows.append({
            "秒": round(float(m.group(2)), 3),
            "帧号": int(m.group(1)),
            "文件名": name,
            "绝对路径": os.path.join(frames_dir, name),
        })
    rows.sort(key=lambda r: r["秒"])
    return rows


def main():
    ap = argparse.ArgumentParser(description="把图片包的帧建成「秒 -> 帧文件」索引")
    ap.add_argument("pack", help="图片包目录（下面应该有 frames\\）")
    ap.add_argument("--out", required=True, help="输出目录，通常是 01_拆解\\01_原片证据")
    ap.add_argument("--from", dest="t0", type=float, default=None, help="只列这一段（起，秒）")
    ap.add_argument("--to", dest="t1", type=float, default=None, help="只列这一段（止，秒）")
    a = ap.parse_args()

    frames_dir = os.path.join(a.pack, "frames")
    if not os.path.isdir(frames_dir):
        # 允许直接指向 frames
        if os.path.isdir(os.path.join(a.pack)) and PAT.match(os.listdir(a.pack)[0] or ""):
            frames_dir = a.pack
        else:
            print(f"找不到 frames 目录：{frames_dir}")
            return 2

    rows = scan(frames_dir)
    if not rows:
        print(f"没有可解析的帧文件名（应为 F000012_00000.200000s.jpg 这种）：{frames_dir}")
        return 2

    sel = rows
    if a.t0 is not None or a.t1 is not None:
        lo = -1e9 if a.t0 is None else a.t0
        hi = 1e9 if a.t1 is None else a.t1
        sel = [r for r in rows if lo - 1e-6 <= r["秒"] <= hi + 1e-6]

    os.makedirs(a.out, exist_ok=True)

    csv_path = os.path.join(a.out, "帧索引.csv")
    with io.open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["秒", "帧号", "文件名", "绝对路径"])
        for r in sel:
            w.writerow([f'{r["秒"]:.3f}', r["帧号"], r["文件名"], r["绝对路径"]])

    # 人读版
    md = []
    md.append("# 00_帧索引｜按秒查原片画面\n")
    md.append("> 自动生成，别手改。生成的命令在文件末尾。\n")
    md.append(f"- 图片包：`{a.pack}`")
    md.append(f"- 帧总数：**{len(rows)}**（本表列出 {len(sel)} 帧）")
    md.append(f"- 覆盖：{rows[0]['秒']:.3f} – {rows[-1]['秒']:.3f} 秒\n")
    md.append("## 怎么用\n")
    md.append("1. 查 `帧索引.csv`，找你的「起止秒」落在哪两帧之间。")
    md.append("2. 只打开那几帧看，**不要逐帧全看**（一段 2 秒可能几十帧）。")
    md.append("3. 看图只许补文字写不出的细节：姿态、朝向、两个人站多近、物件在谁手里、挡没挡住。")
    md.append("4. **不许因为画面去改 T_段、刀数、景别、动作数。**")
    md.append("   画面和设定书冲突时，写进待裁决、报给用户，由 ② 改表——不许自己改。\n")
    md.append("## 密度参考（每 5 秒取一帧，方便先看全貌）\n")
    md.append("| 秒 | 帧文件 |")
    md.append("|---|---|")
    step = 5.0
    nxt = 0.0
    for r in rows:
        if r["秒"] + 1e-6 >= nxt:
            md.append(f'| {r["秒"]:.2f} | `{r["文件名"]}` |')
            nxt = r["秒"] + step
    md.append("\n## 重新生成\n")
    md.append("```")
    md.append(f'python tools\\建帧索引.py "{a.pack}" --out "{a.out}"')
    md.append("```")

    md_path = os.path.join(a.out, "00_帧索引.md")
    io.open(md_path, "w", encoding="utf-8", newline="\n").write("\n".join(md) + "\n")

    print(f"帧 {len(rows)} 张，本表 {len(sel)} 行")
    print(f"写入：{csv_path}")
    print(f"写入：{md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
