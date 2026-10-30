#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查_动作预算.py —— 动作预算闸门（通用版）

【为什么要有它】
    原片一镜只做一件事，我们的小分镜经常一镜写五件事。
    光靠"要求写少一点"拦不住，必须有一把能量出来的尺子；
    而且这把尺子要用本条原片自己当基准，换任何片子都自动校准，不用记数字。

【检查哪四类文件】（自动识别，不用指定类型）
    breakdown  02_开头拆解 / 03_整片拆解
               逐段表有没有「状态变化 / 动作数 / 位移」三列；动作数合计＝本条原片基准
    setting    00_版本设定书
               有没有 4.5 逐刀动作预算表；动作数是否只有 0/1；合计是否≈原片 ±20%
    board      后段小分镜
               每刀动作数、汇总密度、位移刀是否短到看不清（<1 秒）
    unit       生产单元划分与取用联合检查 / 单元/U*.md
               有没有动作总数、动作密度、位移刀位置；并按分镜复核

【怎么判】
    优先读文件里写明的「动作数」字段（作者自己填的，可靠）。
    老文件没有这个字段，就按文字里的动作句估算，并标「估算」提醒你回填。

【用法】
    python 检查_动作预算.py <文件或目录> [--baseline <对标库/B####/03_整片拆解.md>]

    # 例：先看原片基准
    python 检查_动作预算.py "E:\\...\\对标库\\B0001_la_casa_del_sueno\\03_整片拆解.md"

    # 例：查我们的分镜（带上原片，才能判密度）
    python 检查_动作预算.py "E:\\...\\V03\\分镜\\后段小分镜_有效.md" ^
        --baseline "E:\\...\\对标库\\B0001_la_casa_del_sueno\\03_整片拆解.md"

【退出码】
    0 = 通过
    1 = 不通过（结构性错误或密度超基准×1.2）—— 不许提交下一段
    2 = 文件格式不认识，没法检查（不是通过）
"""

import argparse
import json
import re
import sys
from pathlib import Path

# ══════════════════ 词表 ══════════════════

ACTION_VERBS = list(
    "推压塞敲撕拧扣拽抹拉提放蹲站走转抬挂捏拖擦刷冲捡抓按拔插扶抱递接"
    "掰旋踩踢弯伸收甩搬跨顶托举夹抽送挑退靠坐揭卷倒端握咬拧拍抖蹭刮抠"
)

MOVE_WORDS = [
    "走到", "走向", "跨过", "跨进", "穿过", "进屋", "出门", "回屋", "走进",
    "拖", "搬", "绕到", "退半步", "推着", "挪到", "起身走", "经过", "走过去",
    "抬进", "抬到", "抱到", "搬到", "推回", "拉到",
]

# ══════════════════ 正则 ══════════════════

# 小分镜段标题：### N03｜3.100–4.530｜建议 1.43 秒
CLIP_RE = re.compile(
    r"\n#{2,4}\s*(N\d{2})\s*[｜|]\s*([\d.]+)\s*[–\-~—]\s*([\d.]+)\s*[｜|]\s*建议\s*([\d.]+)\s*秒"
)

# 动作栏：兼容 "人物具体做什么" / "那一个动作"，带不带 ** 都认
ACT_RE = re.compile(
    r"[-*]?\s*(?:\d+[.、)]\s*)?\**\s*(?:人物具体做什么|那一个动作)\**\s*[：:](.*?)"
    r"(?=\n[-*]\s|\n\s*\d+[.、]|\n\*\*|\n#{2,4}|\Z)",
    re.S,
)

PRE_RE = re.compile(
    r"[-*]?\s*\**\s*从什么动作开始\**\s*[：:](.*?)(?=\n[-*]\s|\n\*\*|\Z)", re.S
)

# 显式动作数字段：4b. 动作数：1 / **动作数**：1 / | 动作数 | 1 |
DECL_RE = re.compile(r"(?:4[bB][.、)]?\s*)?动作数\s*[：:|]\s*(\d+)")

# 逐段表数据行：| 2 | 3.100 – 4.530 | ... |
ROW_RE = re.compile(r"^\|\s*(\d+)\s*\|\s*([\d.]+)\s*[–\-~—]\s*([\d.]+)\s*\|(.+)$", re.M)

# 单元覆盖刀范围：N02–N11
RANGE_RE = re.compile(r"(N\d{2})\s*[–\-~—至]\s*(N\d{2})")


# ══════════════════ 基础工具 ══════════════════

def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def count_steps(text: str) -> int:
    """按 ；。 切句，数含动作动词的句子。括号里的说明不算。"""
    if not text:
        return 0
    text = re.sub(r"[（(][^）)]{0,40}[）)]", "", text)
    text = re.sub(r"\d+\.\d+\s*[–\-~—]\s*\d+\.\d+", " ", text)  # 去掉时间码本身
    clauses = [c for c in re.split(r"[；。]", text) if len(c.strip()) > 4]
    return sum(1 for c in clauses if any(v in c for v in ACTION_VERBS))


def is_move(text: str) -> bool:
    return any(w in text for w in MOVE_WORDS)


def declared_steps(block: str):
    """读作者写明的「动作数」。读不到返回 None。"""
    for line in block.splitlines():
        s = line.replace("**", "").strip().strip("|").strip()
        if "动作数" not in s and "4b" not in s.lower():
            continue
        m = DECL_RE.search(s)
        if m:
            return int(m.group(1))
    return None


def md_tables(text: str):
    """抽出所有 markdown 表格 → [(header, rows)]"""
    out, lines, i = [], text.splitlines(), 0
    while i < len(lines):
        if lines[i].strip().startswith("|"):
            block = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                block.append(lines[i].strip())
                i += 1
            if len(block) >= 2:
                header = [c.strip() for c in block[0].strip("|").split("|")]
                rows = []
                for b in block[1:]:
                    if re.fullmatch(r"\|[\s\-:|]+\|", b):
                        continue
                    rows.append([c.strip() for c in b.strip("|").split("|")])
                out.append((header, rows))
        else:
            i += 1
    return out


CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"


def is_seg_label(s: str) -> bool:
    """这一段行首是不是段号。认 N01 / P01 / 01 / ① / 段1 / 镜1 / R1 这些写法。"""
    x = (s or "").strip().strip("*").strip().replace(" ", "")
    if not x:
        return False
    if x[0] in CIRCLED:
        return True
    if re.fullmatch(r"[一二三四五六七八九十]+", x):
        return True
    return bool(re.fullmatch(r"(?:[A-Z]{1,3})?\d+", x))


def _sum_steps_from_md(text: str) -> int:
    """把一份拆解里「动作数」那一列加起来。没有这一列就返回 0。"""
    total = 0
    for h, rows in md_tables(text):
        idx = next((k for k, c in enumerate(h) if "动作数" in c), None)
        if idx is None:
            continue
        for r in rows:
            if not r or idx >= len(r):
                continue
            if not is_seg_label(r[0]):
                continue
            m = re.search(r"\d+", r[idx])
            if m:
                total += int(m.group(0))
    return total


def detect_kind(path: Path) -> str:
    name = path.name
    parent = path.parent.name
    if "拆解" in name:
        return "breakdown"
    if "版本设定书" in name:
        return "setting"
    if "小分镜" in name:
        return "board"
    if "生产单元" in name or parent == "单元" or re.fullmatch(r"U\d{2}\.md", name):
        return "unit"
    # 文件名不规范时看内容（很多人会把分镜存成"回归测试""第4步"这种名字）
    try:
        head = read(path)[:20000]
    except Exception:
        return "unknown"
    if len(CLIP_RE.findall(head)) >= 2:
        return "board"
    if "4.5" in head and "动作数" in head:
        return "setting"
    if "起止秒" in head and ("画面做了什么" in head or "状态变化" in head):
        return "breakdown"
    return "unknown"


# ══════════════════ breakdown ══════════════════

def check_breakdown(path: Path):
    """查拆解逐段表：三列在不在，动作数合计多少。"""
    text = read(path)
    print(f"【拆解】{path.name}")

    table = None
    for h, rows in md_tables(text):
        joined = "|".join(h)
        if ("起止" in joined or "时间" in joined) and ("画面" in joined or "做了什么" in joined):
            table = (h, rows)
            break

    if not table:
        print("  没找到逐段表。表头需要含「起止秒」和「画面做了什么」。")
        return {"kind": "breakdown", "ok": False, "reason": "无逐段表", "path": str(path)}

    h, rows = table
    has_state = any("状态变化" in c or "变成" in c for c in h)
    has_steps = any("动作数" in c for c in h)
    has_move = any("位移" in c for c in h)

    marks = [("状态变化", has_state), ("动作数", has_steps), ("位移", has_move)]
    missing = [n for n, ok in marks if not ok]
    print(f"  表头 {len(h)} 列：" + " / ".join(h))
    if missing:
        print(f"  ✗ 缺列：{'、'.join(missing)}")
    else:
        print("  ✓ 三列齐全")

    # 取列索引
    i_step = next((k for k, c in enumerate(h) if "动作数" in c), None)
    i_desc = next((k for k, c in enumerate(h) if "画面" in c or "做了什么" in c), None)
    i_move = next((k for k, c in enumerate(h) if "位移" in c), None)
    i_time = next((k for k, c in enumerate(h) if "起止" in c or "时间" in c), None)

    total_steps, total_sec, n_rows, sec_by_name = 0, 0.0, 0, []
    first_start = None
    for r in rows:
        if not r:
            continue
        seg = r[0].strip().strip("*").strip()
        # 段号写法放宽：N01 / P01 / 01 / ① / 段1 / 镜1 / R1 / S1 / B1 / E1 都算
        if not is_seg_label(seg):
            continue
        n_rows += 1
        # 秒数
        sec = 0.0
        if i_time is not None and i_time < len(r):
            m = re.search(r"([\d.]+)\s*[–\-~—]\s*([\d.]+)", r[i_time])
            if m:
                sec = float(m.group(2)) - float(m.group(1))
                if first_start is None:
                    first_start = float(m.group(1))
        if sec <= 0:
            m = re.match(r"^\s*(\d+)\s*\|\s*([\d.]+)\s*[–\-~—]\s*([\d.]+)", "|".join(r))
            if m:
                sec = float(m.group(3)) - float(m.group(2))
        total_sec += max(sec, 0)

        # 动作数：优先读列，读不到就按描述估
        st = None
        if i_step is not None and i_step < len(r):
            m = re.search(r"\d+", r[i_step])
            if m:
                st = int(m.group(0))
        if st is None and i_desc is not None and i_desc < len(r):
            st = count_steps(r[i_desc])
        total_steps += (st or 0)

    rate = total_steps / total_sec if total_sec else 0
    print(f"  {n_rows} 段 / {total_sec:.2f} 秒 / 动作数合计 {total_steps}"
          f" = {rate:.2f} 步/秒" + ("" if has_steps else "（估算，未填动作数列）"))

    # ── 口径核对：这份整片拆解是从 0.000 开始的，还是只有后半段？ ──
    # B0004 那种写法（"后半段定义：从 4.267 秒起"）如果不补开头，
    # 下游拿 58.15 秒和全片 62.415 秒比，等于拿苹果比橘子。
    start = first_start or 0.0
    full_sec, full_steps, open_steps = round(total_sec, 2), total_steps, 0
    if start > 0.05:
        open_f = path.parent / "02_开头拆解.md"
        if open_f.exists():
            open_steps = _sum_steps_from_md(read(open_f))
        full_sec = round(start + total_sec, 2)
        full_steps = total_steps + open_steps
        print(f"  这份是后半段口径（从 {start:g} 秒起）。全片 {full_sec:g} 秒 / "
              f"全片动作 {full_steps}（含开头 {open_steps}）")
    print(f"【基准行】start={start:g} full_sec={full_sec:g} full_steps={full_steps} "
          f"open_steps={open_steps}")

    ok = not missing
    print(f"  【闸门】{'通过' if ok else '不通过 —— 回填三列，否则下游只能靠猜'}")
    return {"kind": "breakdown", "ok": ok, "steps": total_steps,
            "sec": round(total_sec, 2), "rate": round(rate, 2),
            "start": start, "full_sec": full_sec, "full_steps": full_steps,
            "missing": missing, "path": str(path)}


# ══════════════════ setting ══════════════════

def check_setting(path: Path, base=None):
    """查设定书 4.5 逐刀动作预算表。"""
    text = read(path)
    print(f"【设定书】{path.name}")

    # 只认标题行，避免匹配到正文里的小数（如 "4.530 下肢近景…"）
    m = re.search(r"^#{1,4}\s*4\.5[^\n]*", text, re.M)
    if not m:
        print("  ✗ 没有 4.5 节「逐刀动作预算表」。")
        print("  【闸门】不通过 —— 这一节缺席，下游四个环节都拿不到动作数，等于整条链没有守恒量。")
        return {"kind": "setting", "ok": False, "reason": "缺 4.5 节", "path": str(path)}

    print(f"  ✓ {m.group(0).strip()[:60]}")

    # 4.5 之后的第一张表
    tail = text[m.start():]
    nxt = re.search(r"\n##?\s", tail[1:])
    scope = tail[: nxt.start() + 1] if nxt else tail
    tables = md_tables(scope)
    if not tables:
        print("  ✗ 4.5 节里没有表格。")
        return {"kind": "setting", "ok": False, "reason": "4.5 无表", "path": str(path)}

    h, rows = tables[0]
    print(f"  表头：{' / '.join(h)}")
    i_step = next((k for k, c in enumerate(h) if "动作数" in c), None)
    i_move = next((k for k, c in enumerate(h) if "位移" in c), None)
    i_sec = next((k for k, c in enumerate(h) if "秒" in c), None)

    if i_step is None:
        print("  ✗ 表里没有「动作数」列。")
        return {"kind": "setting", "ok": False, "reason": "无动作数列", "path": str(path)}

    bad, total, total_sec = [], 0, 0.0
    for r in rows:
        if not r or not re.match(r"^N?\d", r[0].strip()):
            continue
        mm = re.search(r"\d+", r[i_step])
        if not mm:
            continue
        st = int(mm.group(0))
        total += st
        if st > 1:
            bad.append(r[0].strip())
        if i_sec is not None and i_sec < len(r):
            ms = re.search(r"([\d.]+)\s*[–\-~—]\s*([\d.]+)", r[i_sec])
            if ms:
                total_sec += float(ms.group(2)) - float(ms.group(1))

    print(f"  {len(rows)} 行 / 动作数合计 {total}"
          + (f" / {total_sec:.2f} 秒 = {total/total_sec:.2f} 步/秒" if total_sec else ""))

    ok = not bad
    if bad:
        print(f"  ✗ 动作数 >1 的刀：{'、'.join(bad)}（必须拆刀或改成原地单动作）")

    if base and base.get("steps"):
        ref = base["steps"]
        lo, hi = ref * 0.8, ref * 1.2
        inrange = lo <= total <= hi
        print(f"  原片动作数 {ref}，允许区间 {lo:.0f}–{hi:.0f}；本版 {total} → "
              f"{'在区间内' if inrange else '超出区间'}")
        ok = ok and inrange

    print(f"  【闸门】{'通过' if ok else '不通过'}")
    return {"kind": "setting", "ok": ok, "steps": total,
            "sec": round(total_sec, 2), "bad": bad, "path": str(path)}


# ══════════════════ board ══════════════════

def check_board(path: Path, base=None, tol=1.2):
    """查小分镜每一刀的动作数与汇总密度。"""
    text = read(path)
    print(f"【小分镜】{path.name}")

    hits = list(CLIP_RE.finditer(text))
    if not hits:
        print("  没解析到 N 段。标题需要形如：### N03｜3.100–4.530｜建议 1.43 秒")
        return {"kind": "board", "ok": False, "reason": "无 N 段", "path": str(path)}

    rows = []
    for i, m in enumerate(hits):
        end = hits[i + 1].start() if i + 1 < len(hits) else len(text)
        block = text[m.end():end]
        act = ACT_RE.search(block)
        pre = PRE_RE.search(block)
        decl = declared_steps(block)

        act_txt = act.group(1) if act else ""
        pre_txt = pre.group(1) if pre else ""
        est = count_steps(act_txt) + (1 if pre_txt.strip() else 0)
        steps = decl if decl is not None else est

        rows.append({
            "clip": m.group(1),
            "sec": float(m.group(4)),
            "steps": steps,
            "declared": decl is not None,
            "est": est,
            "rate": round(steps / float(m.group(4)), 2) if float(m.group(4)) else 0,
            "move": is_move(pre_txt + act_txt),
            "chars": len(act_txt.strip()),
        })

    declared_ratio = sum(1 for r in rows if r["declared"]) / len(rows)
    print(f"  {len(rows)} 刀；其中 {sum(1 for r in rows if r['declared'])} 刀写了显式动作数"
          + ("" if declared_ratio > 0.9 else "  ← 旧格式，未填的按文字估算"))

    print(f"\n  {'刀':>4} {'秒':>6} {'动作句':>6} {'步/秒':>6} {'位移':>4} {'动作栏字数':>8}  判定")
    print("  " + "-" * 60)
    over, too_long = [], []
    for r in rows:
        bad = r["steps"] > 1
        long_bad = r["chars"] > 40
        if bad:
            over.append(r)
        if long_bad:
            too_long.append(r)
        tag = "合格"
        if bad and long_bad:
            tag = "超标(写成步骤)"
        elif bad:
            tag = "超标(多句)"
        elif long_bad:
            tag = "超标(超40字)"
        print(f"  {r['clip']:>4} {r['sec']:6.2f} {r['steps']:6d} {r['rate']:6.2f} "
              f"{'是' if r['move'] else '否':>4} {r['chars']:8d}  {tag}")

    tot_s = sum(r["sec"] for r in rows)
    tot_a = sum(r["steps"] for r in rows)
    avg = tot_a / tot_s if tot_s else 0

    print("  " + "-" * 60)
    print(f"  合计 {len(rows)} 刀 / {tot_s:.2f} 秒 / {tot_a} 个动作句")
    if base:
        print(f"  原片基准 {base['steps']} 个动作 / {base['sec']} 秒 = {base['rate']} 步/秒")
        print(f"  本版 {avg:.2f} 步/秒，是原片的 {avg/base['rate']:.1f} 倍")

    ok = True
    if over:
        print(f"  动作栏写了多句的刀：{'、'.join(r['clip'] for r in over)}")
        print("   ↳ 一句能说完的事被拆成了几段（\"扣扳机→批头转→起子下沉→起子抬起\"其实是一件事）。")
    if too_long:
        print(f"  动作栏超过 40 字的刀：{'、'.join(r['clip'] for r in too_long)}")
        print("   ↳ 40 字是「一句话」的上限。超了就是把步骤写进来了，删到只剩那一下。")
    if over or too_long:
        ok = False

    limit = round(base["rate"] * tol, 2) if base else None
    if limit:
        if avg > limit:
            ok = False
            print(f"  【闸门】密度 {avg:.2f} > 上限 {limit}（原片{base['rate']}×{tol}）→ 不通过")
        else:
            print(f"  【闸门】密度 {avg:.2f} ≤ 上限 {limit} → 通过")

    # 2026-10-27：取消「位移刀 ≥2 秒」。那是剪辑规则，不是拍摄规则。
    # 现在只提一句：位移刀要排在单元前两刀（保留率高），不再规定秒数。
    short = [r for r in rows if r["move"] and r["sec"] < 1.0]
    if short:
        print(f"  注意：{len(short)} 刀是位移类且不足 1 秒（{'、'.join(r['clip'] for r in short)}）。"
              "低于 1 秒观众看不清在移动，建议给足素材秒；秒数本身不设下限，只别低于 1 秒。")

    if base and tot_a > base["steps"] * 1.2:
        print(f"  注意：动作总数 {tot_a} 超过原片 {base['steps']} 的 1.2 倍。"
              "28 秒级片子装不下这么多动作，要删，不是拆刀。")

    print(f"  【结论】{'通过' if ok else '不通过'}")
    return {"kind": "board", "ok": ok, "rows": rows, "steps": tot_a,
            "sec": round(tot_s, 2), "rate": round(avg, 2),
            "over": [r["clip"] for r in over], "too_long": [r["clip"] for r in too_long],
            "path": str(path)}


# ══════════════════ unit ══════════════════

def check_unit(path: Path, base=None, tol=1.2):
    """查生产单元表：三列在不在；能读到分镜就按覆盖刀复核动作总数。"""
    text = read(path)
    print(f"【生产单元】{path.name}")

    tgt = None
    for h, rows in md_tables(text):
        joined = "|".join(h)
        if "单元" in joined and ("生成" in joined or "覆盖" in joined):
            tgt = (h, rows)
            break

    if not tgt:
        print("  这是单元卡，不是单元表（没有「单元/生成」表），跳过。")
        return {"kind": "unit", "ok": None, "reason": "单元卡，跳过", "path": str(path)}

    h, rows = tgt
    print(f"  表头：{' / '.join(h)}")
    need = ["动作总数", "动作密度", "位移刀"]
    missing = [n for n in need if not any(n in c for c in h)]
    if missing:
        print(f"  ✗ 缺列：{'、'.join(missing)}")
    else:
        print("  ✓ 动作预算三列齐全")

    # 找同目录分镜，按覆盖刀复核
    board = None
    for cand in [path.parent / "分镜" / "后段小分镜_有效.md",
                 path.parent.parent / "分镜" / "后段小分镜_有效.md",
                 path.parent / "后段小分镜_有效.md"]:
        if cand.exists():
            board = cand
            break

    detail = []
    if board:
        btext = read(board)
        hits = list(CLIP_RE.finditer(btext))
        per_clip = {}
        for i, m in enumerate(hits):
            end = hits[i + 1].start() if i + 1 < len(hits) else len(btext)
            block = btext[m.end():end]
            act = ACT_RE.search(block)
            pre = PRE_RE.search(block)
            decl = declared_steps(block)
            est = count_steps(act.group(1) if act else "") + (1 if pre and pre.group(1).strip() else 0)
            per_clip[m.group(1)] = decl if decl is not None else est

        i_name = next((k for k, c in enumerate(h) if "单元" in c), 0)
        i_gen = next((k for k, c in enumerate(h) if "生成" in c), None)
        i_cov = next((k for k, c in enumerate(h) if "覆盖" in c), None)
        i_move = next((k for k, c in enumerate(h) if "位移刀" in c), None)

        print(f"\n  {'单元':>6} {'生成秒':>6} {'刀数':>4} {'动作数':>6} {'步/秒':>6}  判定")
        print("  " + "-" * 50)
        for r in rows:
            if not r or len(r) <= i_name:
                continue
            name = r[i_name].strip()
            if not re.match(r"^U\d", name):
                continue
            gen = 0.0
            if i_gen is not None and i_gen < len(r):
                m = re.search(r"([\d.]+)", r[i_gen])
                if m:
                    gen = float(m.group(1))
            total, cnt = 0, 0
            if i_cov is not None and i_cov < len(r):
                rg = RANGE_RE.search(r[i_cov])
                if rg:
                    a, b = int(rg.group(1)[1:]), int(rg.group(2)[1:])
                    for n, s in per_clip.items():
                        if a <= int(n[1:]) <= b:
                            total += s
                            cnt += 1
                else:
                    single = re.search(r"N(\d{2})", r[i_cov])
                    if single:
                        key = "N" + single.group(1)
                        if key in per_clip:
                            total += per_clip[key]
                            cnt += 1
            rate = total / gen if gen else 0
            limit_u = base["rate"] * tol if base else 1.5
            bad = bool(gen) and rate > limit_u
            detail.append({"unit": name, "gen": gen, "clips": cnt,
                           "steps": total, "rate": round(rate, 2), "bad": bad})
            print(f"  {name:>6} {gen:6.1f} {cnt:4d} {total:6d} {rate:6.2f}  "
                  f"{'超标' if bad else '合格'}")
        if base:
            print(f"\n  上限 {base['rate']*tol:.2f} 步/秒（原片 {base['rate']} × {tol}）")
        else:
            print("\n  未给原片基准，暂用参考上限 1.50 步/秒判；带上 --baseline 才准。")
        i_mv = next((k for k, c in enumerate(h) if "位移刀" in c), None)
        if i_mv is None:
            print("  提示：没有「位移刀位置」列。位移刀排单元前两刀，素材保留 90–99%；排最后一刀只剩 65–76%。")
    else:
        print("  没找到同目录的分镜，跳过逐单元复核。")

    ok = not missing and not any(d["bad"] for d in detail)
    print(f"  【闸门】{'通过' if ok else '不通过'}")
    return {"kind": "unit", "ok": ok, "missing": missing, "units": detail,
            "path": str(path)}


# ══════════════════ 主流程 ══════════════════

def check_one(path: Path, base=None, tol=1.2):
    kind = detect_kind(path)
    if kind == "breakdown":
        return check_breakdown(path)
    if kind == "setting":
        return check_setting(path, base)
    if kind == "board":
        return check_board(path, base, tol)
    if kind == "unit":
        return check_unit(path, base, tol)
    print(f"【跳过】{path.name}：认不出类型（拆解 / 设定书 / 小分镜 / 生产单元）")
    return {"kind": "unknown", "ok": None, "path": str(path)}


def main():
    # 输出编码：被别的程序用管道读时（GUI/子进程），统一用 UTF-8；
    # 直接在 cmd 里跑时保持系统默认，免得控制台乱码。
    for _s in (sys.stdout, sys.stderr):
        try:
            if sys.platform == "win32" and not _s.isatty():
                _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    ap = argparse.ArgumentParser(description="动作预算闸门")
    ap.add_argument("path", nargs="?", help="要检查的文件或目录")
    ap.add_argument("--baseline", help="原片拆解 03_整片拆解.md，用来算本条基准")
    ap.add_argument("--tol", type=float, default=1.2, help="允许超过基准的倍数，默认 1.2")
    ap.add_argument("--json", help="结果另存 json")
    args = ap.parse_args()

    base = None
    if args.baseline:
        b = Path(args.baseline)
        if not b.exists():
            print(f"找不到基准文件：{b}")
            return 2
        r = check_breakdown(b)
        print()
        if not r.get("ok"):
            print("★ 基准文件不合格：动作数是估出来的，先回填三列再拿它当基准。\n")
        base = {"steps": r.get("steps", 0), "sec": r.get("sec", 0),
                "rate": r.get("rate", 0)}

    if not args.path:
        return 0

    p = Path(args.path)
    if not p.exists():
        print(f"找不到：{p}")
        return 2

    files = [p] if p.is_file() else [
        f for f in sorted(p.rglob("*.md"))
        if (detect_kind(f) != "unknown" and "_旧" not in f.name
                and "备份" not in str(f) and not f.name.startswith("_"))
    ]
    if not files:
        print("目录里没有可检查的文件。")
        return 2

    results = []
    for f in files:
        if base and f.resolve() == Path(args.baseline).resolve():
            continue
        results.append(check_one(f, base, args.tol))
        print()

    fails = [r for r in results if r.get("ok") is False]
    passed = [r for r in results if r.get("ok") is True]
    print("=" * 62)
    print(f"通过 {len(passed)} / 不通过 {len(fails)} / 跳过 {len(results)-len(passed)-len(fails)}")
    if fails:
        print("不通过：" + "、".join(Path(r["path"]).name for r in fails))
        print("\n退出码 1 —— 不许提交下一段。")
    else:
        print("退出码 0 —— 可以提交下一段。")

    if args.json:
        Path(args.json).write_text(
            json.dumps({"baseline": base, "results": results}, ensure_ascii=False, indent=1),
            encoding="utf-8")
        print(f"已写出：{args.json}")

    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
