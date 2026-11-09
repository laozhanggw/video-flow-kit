#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查_导图同步.py —— 「只改磁盘不改网站」的闸门

【为什么要有它】
    用户实际复制的是 流程导图.html 上那份指令，不是磁盘上的 .txt。
    改了 .txt 没重跑生成器，等于没改——人复制到的还是旧规则。
    2026-10-27 真实事故：一整天改的全在 指令\\5_生产单元.txt 上，
    流程导图.html 还停在 10-26 13:04，第 5 份指令少了 4,872 字。
    这条坑在《五、踩过的坑》里早就写着，还是又犯了一次。
    「记得重跑」不算防住，要有退出码。

【怎么判】
    1. 网页版本条里内嵌的「指令字数」五个数
       ↔ 本机 指令\\*.txt 的实际字符数（len，和生成器同一算法）
       任何一个对不上 → 退出码 1
    2. 指令、skill、参考表（词表／卡住了怎么办）、写卡格式（5B／格式全文）
       的全文快照与磁盘逐字比对（等长修改也拦截）
    3. 源文件最新修改时间按秒比较 > 网页生成时间 → 退出码 1
    4. 网页生成时间或全文快照读不到 → 退出码 2（文件坏了，不是通过）

【用法】
    python 检查_导图同步.py
    python 检查_导图同步.py --dir "E:\\...\\00_视频生产流程规范_v1"

    不带参数时，从脚本自身位置向上找 00_视频生产流程规范_v1 或直接当成目录。

【退出码】
    0 = 已同步
    1 = 没同步（网页是旧的，去重跑 tools\\生成流程导图.py）
    2 = 读不懂（不是通过）
"""

import argparse
import datetime
import io
import json
import os
import re
import sys
from pipeline_runtime import get_instruction_dir, get_suite_root

INSTR_FILES = {
    "1": "1_拆解.txt",
    "2": "2_复刻.txt",
    "3": "3_开头.txt",
    "4": "4_小分镜.txt",
    "5": "5_生产单元.txt",
}

# 网页「复制参考表」按钮装的快照，顺序与 生成流程导图.py 的 REF_FILES 一致
REF_FILES = [
    ("V1", "19_工序词表.md"),
    ("V2", "00_卡住了怎么办.md"),
]

# 网页「写卡格式」按钮装的快照（生成器 VG_FILES）。
# 第一份在 指令/ 下，第二份在 skills/ 下——路径基准不同，所以分开存。
VG_TXT = "5B_写卡格式_通用.txt"
VG_MD = "skills/adaptive-video-production/references/生产单元_写卡格式_v1.md"

# 网页「② 复刻 · 对账指令」按钮装的快照（生成器 AUDIT_FILES）。
# 三份都要逐字比：对账指令改了不重跑，人粘到的就是旧判据。
# 2026-11-02 之前这里没查，2B 新增当天就发现「检查说已同步、其实没验过」。
AUDIT_FILES = [
    ("2B", "2B_复刻对账_通用.txt", "tpl"),
    ("32", "32_废动作怎么防_阿初的判据_20261027.md", "base"),
    ("20", "20_读到的证明_抽查机制.md", "base"),
]

# 网页「八、skill 全文」那一节内嵌的快照，顺序必须和 生成流程导图.py 的 SKILL_FILES 一致
SKILL_FILES = [
    ("s1", "benchmark-select-and-breakdown/SKILL.md"),
    ("s2", "benchmark-video-deconstruction/SKILL.md"),
    ("s3", "benchmark-batch-variants/SKILL.md"),
    ("s4", "benchmark-adapt-hook/SKILL.md"),
    ("s5", "full-storyboard-design/SKILL.md"),
    ("s6", "adaptive-video-production/SKILL.md"),
    ("s7", "adaptive-video-production/references/internal-cut.md"),
    ("s8", "adaptive-video-production/references/material-seconds.md"),
]


def find_base(hint=None):
    if hint:
        return os.path.abspath(hint)
    try:
        return get_suite_root()
    except FileNotFoundError:
        return None


def main():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--dir", help="规范目录（含 流程导图.html 与 指令/ 或 指令模板_v3/）")
    ap.add_argument("-h", "--help", action="help")
    a = ap.parse_args()

    base = find_base(a.dir)
    if not base:
        print("找不到 00_视频生产流程规范_v1 目录，用 --dir 指定")
        return 2

    html_path = os.path.join(base, "流程导图.html")
    if not os.path.exists(html_path):
        print("找不到 流程导图.html：", html_path)
        return 2

    html = io.open(html_path, encoding="utf-8").read()

    m = re.search(r"生成于 <b>([\d\-: ]+)</b>", html)
    if not m:
        print("网页里读不到「生成于」时间戳，文件可能坏了")
        return 2
    try:
        page_time = datetime.datetime.strptime(m.group(1).strip(), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        print("时间戳格式不认识：", m.group(1))
        return 2

    # 网页里内嵌的五个字数
    page_chars = {}
    for mm in re.finditer(r'<span class="vc"><b>(\d)</b> ([\d,]+)</span>', html):
        page_chars[mm.group(1)] = int(mm.group(2).replace(",", ""))

    try:
        tpl = get_instruction_dir(base)
        marker = re.search(r"\bconst\s+DATA\s*=\s*", html)
        if not marker:
            raise ValueError("缺少 const DATA 全文快照")
        snapshot, _ = json.JSONDecoder().raw_decode(html[marker.end():])
        if not isinstance(snapshot, dict) or not isinstance(snapshot.get("instr"), dict) \
                or not isinstance(snapshot.get("skills"), dict):
            raise ValueError("指令或 skill 全文快照结构错误")
    except (FileNotFoundError, ValueError) as e:
        print("无法校验网页全文快照：", e)
        return 2
    print("规范目录：", base)
    print("网页生成：", page_time.strftime("%Y-%m-%d %H:%M:%S"))
    print()
    print(f'{"份":<3}{"本机 txt":>10}{"网页内嵌":>10}{"差":>8}   状态')
    print("-" * 46)

    bad = []
    newest = None
    for k in sorted(INSTR_FILES):
        p = os.path.join(tpl, INSTR_FILES[k])
        if not os.path.exists(p):
            print(f"{k:<3}{'缺文件':>10}{'-':>10}{'-':>8}   ✗")
            bad.append(f"第 {k} 份 .txt 不存在")
            continue
        text = io.open(p, encoding="utf-8").read()
        real = len(text)
        if snapshot["instr"].get(k) != text:
            bad.append(f"第 {k} 份：网页全文快照与 txt 不一致（含等长改动）")
        shown = page_chars.get(k)
        mt = datetime.datetime.fromtimestamp(os.path.getmtime(p))
        if newest is None or mt > newest:
            newest = mt
        if shown is None:
            print(f"{k:<3}{real:>10,}{'没读到':>10}{'-':>8}   ✗")
            bad.append(f"第 {k} 份：网页版本条里读不到字数")
            continue
        diff = real - shown
        ok = diff == 0
        print(f"{k:<3}{real:>10,}{shown:>10,}{diff:>+8}   {'✓' if ok else '✗ 网页是旧的'}")
        if not ok:
            bad.append(f"第 {k} 份：txt {real:,} 字，网页 {shown:,} 字，差 {diff:+,}")

    # ── skill 快照比对（网页「八、skill 全文」那一节）
    sk_chars = {}
    for mm in re.finditer(r'<span class="vc"><b>(s\d+)</b> ([\d,]+)</span>', html):
        sk_chars[mm.group(1)] = int(mm.group(2).replace(",", ""))
    if not sk_chars:
        bad.append("网页版本条缺少 skill 字数")
    else:
        print()
        print(f'{"skill":<5}{"本机文件":>12}{"网页内嵌":>12}{"差":>8}   状态')
        print("-" * 48)
        for key, rel in SKILL_FILES:
            fp = os.path.join(base, "skills", *rel.split("/"))
            if not os.path.exists(fp):
                print(f"{key:<5}{'缺文件':>12}{'-':>12}{'-':>8}   ✗")
                bad.append(f"{key}：skills/{rel} 不存在")
                continue
            text = io.open(fp, encoding="utf-8").read()
            real = len(text)
            stored = next((v for v in snapshot["skills"].values()
                           if isinstance(v, dict) and v.get("path") == "skills/" + rel), None)
            if stored is None or stored.get("text") != text:
                bad.append(f"{key}：skills/{rel} 全文快照不一致或缺失（含等长改动）")
            shown = sk_chars.get(key)
            mt = datetime.datetime.fromtimestamp(os.path.getmtime(fp))
            if newest is None or mt > newest:
                newest = mt
            if shown is None:
                print(f"{key:<5}{real:>12,}{'没读到':>12}{'-':>8}   ✗")
                bad.append(f"{key}：网页里读不到这份 skill 的字数")
                continue
            diff = real - shown
            ok = diff == 0
            print(f"{key:<5}{real:>12,}{shown:>12,}{diff:>+8}   {'✓' if ok else '✗ 网页是旧的'}")
            if not ok:
                bad.append(f"{key}：skills/{rel} 本机 {real:,} 字，网页 {shown:,} 字，差 {diff:+,}")

    # ── 参考表（refs）与写卡格式（vg）：网页上那两个复制按钮装的也是全文快照。
    #    2026-11-01 之前这里没查，词表／卡住了怎么办／5B 改了不会有人发现。
    print()
    print(f'{"参考":<5}{"本机文件":>12}{"网页内嵌":>12}   状态')
    print("-" * 48)
    refs_snap = snapshot.get("refs") if isinstance(snapshot.get("refs"), dict) else {}
    for key, fn in REF_FILES:
        fp = os.path.join(base, fn)
        if not os.path.exists(fp):
            print(f"{key:<5}{'缺文件':>12}{'-':>12}   ✗")
            bad.append(f"{key}：{fn} 不存在")
            continue
        text = io.open(fp, encoding="utf-8").read()
        real = len(text)
        stored = refs_snap.get(key)
        ok = isinstance(stored, dict) and stored.get("text") == text
        if not ok:
            bad.append(f"{key}：{fn} 全文快照不一致或缺失（含等长改动）")
        mt = datetime.datetime.fromtimestamp(os.path.getmtime(fp))
        if newest is None or mt > newest:
            newest = mt
        print(f"{key:<5}{real:>12,}{'一致' if ok else '旧了':>12}   {'✓' if ok else '✗ 网页是旧的'}")

    vg = snapshot.get("vg") if isinstance(snapshot.get("vg"), dict) else {}
    parts = {os.path.basename(p.get("path", "")): p.get("text")
             for p in (vg.get("parts") or []) if isinstance(p, dict)}
    for rel, root in ((VG_TXT, tpl), (VG_MD, base)):
        fp = os.path.join(root, *rel.split("/"))
        name = os.path.basename(rel)
        if not os.path.exists(fp):
            print(f"{'vg':<5}{'缺文件':>12}{'-':>12}   ✗")
            bad.append(f"{rel} 不存在")
            continue
        text = io.open(fp, encoding="utf-8").read()
        real = len(text)
        ok = parts.get(name) == text
        if not ok:
            bad.append(f"{rel} 全文快照不一致或缺失（含等长改动）")
        mt = datetime.datetime.fromtimestamp(os.path.getmtime(fp))
        if newest is None or mt > newest:
            newest = mt
        print(f"{'vg':<5}{real:>12,}{'一致' if ok else '旧了':>12}   {'✓' if ok else '✗ 网页是旧的'}  {name}")

    # ── 复刻对账包（audit）：2026-11-02 新增的那个橙色按钮。
    #    它装着对账指令 ＋ 32／20 号判据原文，三份都得比，否则改了没人发现。
    aud = snapshot.get("audit") if isinstance(snapshot.get("audit"), dict) else {}
    aud_parts = {os.path.basename(p.get("path", "")): p.get("text")
                 for p in (aud.get("parts") or []) if isinstance(p, dict)}
    for key, rel, root_key in AUDIT_FILES:
        root = tpl if root_key == "tpl" else base
        fp = os.path.join(root, *rel.split("/"))
        name = os.path.basename(rel)
        if not os.path.exists(fp):
            print(f"{key:<5}{'缺文件':>12}{'-':>12}   ✗")
            bad.append(f"{rel} 不存在")
            continue
        text = io.open(fp, encoding="utf-8").read()
        real = len(text)
        ok = aud_parts.get(name) == text
        if not ok:
            bad.append(f"{rel} 对账包快照不一致或缺失（含等长改动）")
        mt = datetime.datetime.fromtimestamp(os.path.getmtime(fp))
        if newest is None or mt > newest:
            newest = mt
        print(f"{key:<5}{real:>12,}{'一致' if ok else '旧了':>12}   {'✓' if ok else '✗ 网页是旧的'}  {name}")

    print("-" * 46)
    if newest:
        print("最新 .txt 改动：", newest.strftime("%Y-%m-%d %H:%M:%S"))
        if newest.replace(microsecond=0) > page_time:
            bad.append("有 .txt 比网页新，改完没重跑生成器"
                       f"（txt {newest:%m-%d %H:%M} > 网页 {page_time:%m-%d %H:%M}）")

    if bad:
        print()
        print("✗ 没同步。逐条：")
        for b in bad:
            print("   ·", b)
        print()
        print("去跑：")
        print(f'   "{sys.executable}" "{os.path.join(base, "tools", "生成流程导图.py")}"')
        print(f'   "{sys.executable}" "{os.path.abspath(__file__)}" --dir "{base}"')
        return 1

    print()
    print("✓ 已同步：网页里嵌的就是磁盘上这份，可以复制。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
