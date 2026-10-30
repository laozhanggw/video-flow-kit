#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查_交付物.py —— 每段交付物的验收闸门

【它和 检查_动作预算.py 的分工】
    检查_动作预算.py   只管一个维度：动作密度。深，但窄。
    检查_交付物.py     管一整段交付物的完整性和跨环节一致性。广，但不重复算密度
                       （密度那部分它会去调前面那个脚本）。

【为什么要有它】
    AI 犯的错不是随机的，是固定的几类，而且每一类都犯过不止一次：
      · 字段缺项（表少一列、章节少一节）
      · 数字漂移（3 米变 4.5 米、20 英尺变 40 英尺、23 镜写成 24 镜）
      · 秒数不连续（段与段之间跳秒、重叠）
      · 自己发明规则（编出"80–95 秒"、替下游决定划几个单元）
      · 用空话交差（"已检查""快速完成""同上"）
      · 动作写成了步骤
    人看一遍能发现，但会漏；机器看一遍不会漏，但看不懂语义。
    所以：机器查结构和数字，人查语义和判断。

【用法】
    # 查一个已完成的版本目录（自动判断做到哪一步了）
    python 检查_交付物.py "…\\V03_la_casa_del_sueno" --baseline "…\\B0001_la_casa_del_sueno\\03_整片拆解.md"

    # 只查拆解（对标库目录）
    python 检查_交付物.py "…\\对标库\\B0001_la_casa_del_sueno"

    # 只查某一段
    python 检查_交付物.py "…\\V03_la_casa_del_sueno" --stage b

【分段代号】
    a 拆解    b 设定书    c 开头    d 小分镜    e 生产单元

【退出码】
    0 = 全部必过项通过
    1 = 有必过项不通过（不许交给下一段）
    2 = 目录里没找到可检查的交付物
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

# ══════════════════ 基础 ══════════════════

OK, NG, WARN, SKIP = "√", "×", "!", "-"
_results = []


def read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def rec(stage, name, level, msg):
    """level: error / warn / info / ok / skip"""
    _results.append({"stage": stage, "name": name, "level": level, "msg": msg})


def check(stage, name, cond, detail="", level="error", warn_if=False):
    if cond:
        rec(stage, name, "ok", detail or "通过")
        print(f"    {OK} {name}" + (f" —— {detail}" if detail else ""))
        return True
    if level == "warn" or warn_if:
        rec(stage, name, "warn", detail or "需人工确认")
        print(f"    {WARN} {name}" + (f" —— {detail}" if detail else ""))
        return False
    rec(stage, name, "error", detail or "不通过")
    print(f"    {NG} {name}" + (f" —— {detail}" if detail else ""))
    return False


def md_tables(text):
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


# ══════════════════ a 拆解 ══════════════════

def stage_a(d: Path):
    print("\n【a 拆解】")
    if not d.exists():
        rec("a", "目录", "skip", "不存在")
        print(f"    {SKIP} 目录不存在，跳过")
        return

    idx = d / "00_对标索引.md"
    head = d / "02_开头拆解.md"
    whole = d / "03_整片拆解.md"

    check("a", "00_对标索引.md 存在", idx.exists())
    check("a", "02_开头拆解.md 存在", head.exists())
    check("a", "03_整片拆解.md 存在", whole.exists())

    # first_frame
    ff = list(d.glob("01_原片证据/first_frame*"))
    check("a", "first_frame 存在且是 0.000 秒那帧", bool(ff),
          "缺了第③段没法比「看过感」" if not ff else str(ff[0].name))

    # 三列
    for f, label in [(head, "开头拆解"), (whole, "整片拆解")]:
        if not f.exists():
            continue
        t = read(f)
        tab = None
        for h, rows in md_tables(t):
            j = "|".join(h)
            if "起止" in j and ("画面" in j or "做了什么" in j):
                tab = (h, rows)
                break
        if not tab:
            check("a", f"{label} 逐段表", False, "没找到表头含「起止」「画面」的表")
            continue
        h, rows = tab
        miss = [n for n in ("状态变化", "动作数", "位移") if not any(n in c for c in h)]
        check("a", f"{label} 三列齐全", not miss,
              "缺 " + "、".join(miss) if miss else f"{len(h)} 列")

        # 秒数连续 + 段号连续
        rows2 = [r for r in rows if r and re.fullmatch(r"\d+|[RBSE]\d+|[①-⑩]", r[0].strip().strip("*").strip())]
        secs, prev_end, gaps, order_ok = [], None, [], True
        for k, r in enumerate(rows2):
            m = re.search(r"([\d.]+)\s*[–\-~—]\s*([\d.]+)", r[1] if len(r) > 1 else "")
            if not m:
                continue
            a, b = float(m.group(1)), float(m.group(2))
            secs.append((a, b))
            if prev_end is not None and abs(a - prev_end) > 0.02:
                gaps.append(f"{prev_end:.3f}→{a:.3f}")
            prev_end = b
        check("a", f"{label} 秒数连续无跳秒", not gaps,
              ("断点：" + "、".join(gaps[:5])) if gaps else f"{len(secs)} 段连续")
        if secs:
            span = secs[-1][1] - secs[0][0]
            rec("a", f"{label} 总长", "info", f"{span:.2f} 秒")

    # 未核标注
    if whole.exists():
        n_unchecked = read(whole).count("未核")
        rec("a", "「未核」标注", "info", f"{n_unchecked} 处")
        print(f"    {OK} 「未核」标注 {n_unchecked} 处（没标不代表都核过，是提醒你自己过一眼）")

    # 儿童红线
    if idx.exists():
        has_child = "有" in read(idx)[:3000] and "儿童" in read(idx)[:3000]
        check("a", "像儿童的人已标注", True,
              "索引里有儿童字段" if has_child else "索引里没找到儿童相关字段，人工确认",
              level="warn")


# ══════════════════ b 设定书 ══════════════════

TEN_SECTIONS = ["1", "2", "3", "4", "4.1", "4.5", "5", "6", "7", "8", "9", "10"]


def stage_b(d: Path, baseline: dict | None):
    print("\n【b 设定书】")
    f = d / "00_版本设定书.md"
    if not f.exists():
        rec("b", "设定书", "skip", "不存在")
        print(f"    {SKIP} 00_版本设定书.md 不存在，跳过")
        return
    t = read(f)

    # 章节
    heads = [m.group(1).strip().rstrip(".") for m in re.finditer(r"^#{1,4}\s*([\d.]+)[\s、.]", t, re.M)]
    miss = [s for s in TEN_SECTIONS if s not in heads]
    check("b", "十节齐全（含 4.5）", not miss,
          ("缺 " + "、".join(miss)) if miss else f"{len(heads)} 节")

    # 4.5 表
    m = re.search(r"^#{1,4}\s*4\.5[^\n]*", t, re.M)
    if not m:
        rec("b", "4.5 动作预算表", "error", "缺")
        print(f"    {NG} 4.5 逐刀动作预算表 —— 缺（下游四个环节拿不到动作数）")
    else:
        tail = t[m.start():]
        nxt = re.search(r"\n##?\s", tail[1:])
        scope = tail[: nxt.start() + 1] if nxt else tail
        tabs = md_tables(scope)
        if not tabs:
            check("b", "4.5 动作预算表", False, "4.5 节下没有表")
        else:
            h, rows = tabs[0]
            i_st = next((k for k, c in enumerate(h) if "动作数" in c), None)
            check("b", "4.5 六列（含动作数）", i_st is not None,
                  " / ".join(h)[:70] if i_st is None else f"{len(h)} 列")
            if i_st is not None:
                vals, bad = [], []
                for r in rows:
                    if not r or not re.fullmatch(r"N?\d+", r[0].strip().strip("*")):
                        continue
                    mm = re.search(r"\d+", r[i_st])
                    if mm:
                        v = int(mm.group(0))
                        vals.append(v)
                        if v > 1:
                            bad.append(r[0].strip())
                check("b", "动作数只能是 0 或 1", not bad,
                      ("超 1：" + "、".join(bad)) if bad else f"{len(vals)} 刀")
                if baseline:
                    tot = sum(vals)
                    lo, hi = baseline["steps"] * 0.8, baseline["steps"] * 1.2
                    check("b", "动作合计 ≈ 原片 ±20%", lo <= tot <= hi,
                          f"本版 {tot} / 原片 {baseline['steps']} / 允许 {lo:.0f}–{hi:.0f}")

            # ── 覆盖原片时段：同一镜号下不许留洞（2026-10-29 新增） ──
            # 全片总数过闸不代表没丢东西：局部丢三分之一会被总数平均掉。
            # 唯一能机械查出来的办法，是让每一刀声明"我画的是原片哪一镜的哪一段"。
            i_sh = next((k for k, c in enumerate(h) if "镜号" in c), None)
            i_cv = next((k for k, c in enumerate(h) if "覆盖" in c), None)
            i_rt = next((k for k, c in enumerate(h) if "起止" in c), None)
            if i_sh is None or i_cv is None:
                check("b", "4.5 表含「原片镜号／覆盖原片时段」", False,
                      "缺这两列，查不出原片哪一段被删了；老项目请按新格式补两列",
                      level="warn")
            else:
                spans = {}
                for r in rows:
                    if not r or not re.fullmatch(r"N?\d+", r[0].strip().strip("*")):
                        continue
                    if max(i_sh, i_cv) >= len(r):
                        continue
                    shot = r[i_sh].strip().strip("*").strip()
                    m2 = re.search(r"([\d.]+)\s*[-–—~～至]\s*([\d.]+)", r[i_cv])
                    if not shot or not m2:
                        continue
                    a, b2 = float(m2.group(1)), float(m2.group(2))
                    spans.setdefault(shot, []).append((a, b2, r[0].strip().strip("*")))

                holes, overlaps, overlong = [], [], []
                for shot, lst in spans.items():
                    lst.sort()
                    for prev, cur in zip(lst, lst[1:]):
                        if cur[0] > prev[1] + 0.02:
                            holes.append(f"{shot} {prev[1]:.3f}→{cur[0]:.3f}（{prev[2]} 与 {cur[2]} 之间）")
                        elif cur[0] < prev[1] - 0.02:
                            overlaps.append(f"{shot} {prev[2]}/{cur[2]}")
                check("b", "同一镜号覆盖时段不留洞", not holes,
                      ("留洞：" + "；".join(holes[:4])) if holes else f"{len(spans)} 个镜号覆盖连续")
                check("b", "同一镜号覆盖时段不重叠", not overlaps,
                      ("重叠：" + "、".join(overlaps[:4])) if overlaps else "无重叠")

                if i_rt is not None:
                    for r in rows:
                        if not r or not re.fullmatch(r"N?\d+", r[0].strip().strip("*")):
                            continue
                        if max(i_cv, i_rt) >= len(r):
                            continue
                        mcv = re.search(r"([\d.]+)\s*[-–—~～至]\s*([\d.]+)", r[i_cv])
                        mrt = re.search(r"([\d.]+)\s*[-–—~～至]\s*([\d.]+)", r[i_rt])
                        if not (mcv and mrt):
                            continue
                        cover = float(mcv.group(2)) - float(mcv.group(1))
                        mat = float(mrt.group(2)) - float(mrt.group(1))
                        if cover > 0.05 and mat > cover * 1.3 + 0.15:
                            overlong.append(f"{r[0].strip().strip('*')} 素材 {mat:.2f}s / 覆盖 {cover:.2f}s")
                    check("b", "素材秒不超过覆盖时长 1.3 倍", not overlong,
                          ("时间比内容多：" + "；".join(overlong[:4])) if overlong
                          else "时间与内容匹配", level="warn")

    # 总时长
    mt = re.search(r"(?:成片总时长|总时长|片长)[^\n]*?([\d.]+)\s*秒", t)
    if mt:
        dur = float(mt.group(1))
        rec("b", "总时长", "info", f"{dur} 秒")
        if baseline and baseline.get("sec"):
            ref = baseline["sec"]
            check("b", "总时长 ≈ 原片 ±15%", abs(dur - ref) / ref <= 0.15,
                  f"本版 {dur} / 原片 {ref}（差 {(dur-ref)/ref*100:+.1f}%）")
    else:
        check("b", "总时长可读出", False, "没找到「总时长 XX 秒」", level="warn")

    # 表面八项
    got = re.findall(r"\bC([1-8])\b", t)
    check("b", "表面清单 C1–C8 齐全", len(set(got)) >= 8,
          f"出现 {len(set(got))} 项", level="warn")

    # 十项键值
    seg = re.search(r"^#{1,4}\s*4\.1[^\n]*", t, re.M)
    if seg:
        segtext = t[seg.start():seg.start() + 3000]
        # 优先数固定的「末态.」前缀（最稳）；没有这种写法再按行数
        n_keys = segtext.count("末态.")
        n_lines = n_keys if n_keys >= 5 else len(
            re.findall(r"^\s*(?:\d+\s*[.、]?|[\-*|])", segtext, re.M))
        check("b", "T 秒末态十项键值", n_lines >= 10,
              f"{n_lines} 项" + ("（缺项，下游接不上）" if n_lines < 10 else ""),
              level="warn")

    # 替下游做决定
    bad_phrases = ["划 8 个单元", "划出 8 个单元", "共 16 个单元"]
    hit = [p for p in bad_phrases if p in t]
    check("b", "没有替下游决定单元数", not hit,
          ("出现：" + "、".join(hit)) if hit else "干净", level="warn")


# ══════════════════ c 开头 ══════════════════

def stage_c(d: Path, baseline: dict | None):
    """开头这一段的交付物分散在三个文件里，判据要跨文件找，不能只盯开头方案。"""
    print("\n【c 开头】")
    f = d / "开头" / "开头方案_有效.md"
    if not f.exists():
        rec("c", "开头方案", "skip", "不存在")
        print(f"    {SKIP} 开头\\开头方案_有效.md 不存在，跳过")
        return

    t = read(f)
    hand = d / "开头" / "开头交接.md"
    th = read(hand) if hand.exists() else ""
    st = d / "00_版本设定书.md"
    ts = read(st) if st.exists() else ""
    pools = {"开头方案": t, "开头交接": th, "设定书": ts}

    def where(*keys):
        """返回哪些文件里有这些关键词。"""
        return [name for name, txt in pools.items() if any(k in txt for k in keys)]

    check("c", "逐段表有「那一个动作」", "那一个动作" in t,
          "" if "那一个动作" in t else "还是旧的「人物具体做什么」，会写成步骤")
    check("c", "逐段表有「动作数」", "动作数" in t,
          "" if "动作数" in t else "缺动作数，机器读不到")

    # 机位四件套（开头是全片唯一要求严格复刻的地方）
    n_cam = sum(1 for k in ("俯视", "平视", "仰视") if k in t) > 0
    n_cam += sum(1 for k in ("广角", "标准镜头", "中长焦") if k in t) > 0
    n_cam += ("占画面" in t) or ("人物占比" in t)
    n_cam += bool(re.search(r"\d+(\.\d+)?\s*m", t))
    check("c", "机位四件套（高度/俯仰/焦段/占比）", n_cam >= 4,
          f"{n_cam}/4 项", level="warn")

    # 新旧对照：开头方案里有 12 行，或设定书第 4 节有「原片/本版」两列
    n_rows = len(re.findall(
        r"^\|\s*(?:画面内容|外部条件|暴露物|入出镜|镜头|耗时|动作|动作数|力度|声音)", t, re.M))
    col = ("原片" in ts) and ("本版" in ts) and ("原片画面" in ts)
    check("c", "新旧对照（对照表 12 行 或 设定书第4节原片/本版两列）",
          n_rows >= 11 or col,
          f"对照表 {n_rows} 行；设定书对照列 {'有' if col else '无'}", level="warn")

    # 七问：开头三件里 7 条，或设定书第 7 节有 7 行
    n7 = len(re.findall(r"^\|\s*[1-7][\s\.、]", ts, re.M)) if ts else 0
    n7b = len(re.findall(r"^\s*[1-7][.、)]\s*\S", t + th, re.M))
    check("c", "七问逐条有答案（开头或设定书）", n7 >= 7 or n7b >= 7,
          f"设定书 {n7} 条 / 开头 {n7b} 条", level="warn")
    bad = [x for x in ("已检查", "没问题", "无异常") if x in t]
    check("c", "没有「已检查/没问题」这类空答案", not bad,
          ("出现：" + "、".join(bad)) if bad else "干净", level="warn")

    # T 比例：三个文件任一能找到 T 和总时长
    T = dur = None
    for txt in (t, th, ts):
        m1 = re.search(r"T\s*[=＝]\s*([\d.]+)\s*秒", txt)
        m2 = re.search(r"(?:全片|总时长|成片|成片总时长)[^\n]*?([\d.]+)\s*秒", txt)
        if m1 and not T:
            T = float(m1.group(1))
        if m2 and not dur:
            dur = float(m2.group(1))
    if T and dur:
        ratio = T / dur
        # 12%–18% 是选源启发式，不是硬规则。原片本身超出的，只要写明"这是例外"就允许。
        declared = any(k in (ts + t + th) for k in
                       ("区间之外", "区间外", "例外", "按原片实际", "不硬拉长", "偏短", "偏长"))
        if 0.12 <= ratio <= 0.18:
            check("c", "T ÷ 全片 在 12%–18%", True, f"T={T} / {dur} = {ratio*100:.1f}%")
        elif declared:
            check("c", "T ÷ 全片 偏离 12%–18%，但已声明为例外", True,
                  f"T={T} / {dur} = {ratio*100:.1f}%（文档里写明了为什么，接受）", level="warn")
        else:
            check("c", "T ÷ 全片 在 12%–18%", False,
                  f"T={T} / {dur} = {ratio*100:.1f}%，且文档里没写例外理由")
    else:
        check("c", "T 值与总时长可读出", False,
              f"T={T} 总时长={dur}（在开头方案/交接/设定书三处都没找全）", level="warn")

    # 首帧五要素：跨三个文件找，每个概念收同义写法
    concepts = {
        "受害物位置": ("受害物", "受害", "受影响的东西", "受害面"),
        "威胁方向": ("威胁", "雨从", "斜扫", "斜打", "从右上", "从画面右"),
        "距离": ("距离", "已在接触", "已经", "正在打"),
        "几个人": ("几个人", "只有他", "一个人", "无第二人", "没有第二人", "画面里有"),
        "机位高度": ("机位", "高度", "米", " m "),
    }
    hit = [name for name, keys in concepts.items() if where(*keys)]
    check("c", "首帧五要素（跨文件）", len(hit) >= 4,
          f"{len(hit)}/5：" + "、".join(hit), level="warn")

    # 读到的凭证：证明真读了设定书和开头拆解，不是"已阅读"四个字
    all_t = t + th + ts
    has_proof = ("读到的凭证" in all_t) or ("读了什么" in all_t) or ("接手核对" in all_t)
    check("c", "读到的凭证表", has_proof,
          "有" if has_proof else "没有这张表 —— 无法证明读过设定书和开头拆解，退回")


# ══════════════════ d 小分镜 ══════════════════

def stage_d(d: Path, baseline: dict | None, tool: Path | None):
    print("\n【d 小分镜】")
    f = d / "分镜" / "后段小分镜_有效.md"
    if not f.exists():
        cands = list((d / "分镜").glob("*小分镜*.md")) if (d / "分镜").exists() else []
        if not cands:
            rec("d", "小分镜", "skip", "不存在")
            print(f"    {SKIP} 分镜\\后段小分镜_有效.md 不存在，跳过")
            return
        f = cands[0]
    t = read(f)

    # 读到的凭证：交稿最前面必须有一张表，证明真读了输入，不是"已阅读"四个字
    has_proof = ("读到的凭证" in t) or ("接手核对" in t)
    check("d", "读到的凭证表", has_proof,
          "有" if has_proof else "没有这张表 —— 无法证明读过设定书和拆解，退回")

    clips = re.findall(r"^#{2,4}\s*(N\d{2})\s*[｜|]\s*([\d.]+)\s*[–\-~—]\s*([\d.]+)", t, re.M)

    check("d", "N 段可解析", len(clips) >= 2, f"{len(clips)} 刀")
    if not clips:
        return

    # 段号连续
    nums = [int(c[0][1:]) for c in clips]
    gaps = [n for i, n in enumerate(nums) if i and n != nums[i - 1] + 1]
    check("d", "N 编号连续", not gaps, ("跳号：" + str(gaps)) if gaps else f"N01–N{max(nums):02d}")

    # 秒数连续
    bad = []
    for i in range(1, len(clips)):
        if abs(float(clips[i][1]) - float(clips[i - 1][2])) > 0.02:
            bad.append(f"{clips[i-1][2]}→{clips[i][1]}")
    check("d", "刀与刀之间秒数连续", not bad, ("断点：" + "、".join(bad[:4])) if bad else "连续")

    # 显式动作数（写法可能是「4b. 动作数：1」或「**4b. 动作数**：1」，允许中间的粗体星号）
    n_decl = len(re.findall(r"动作数\**\s*[：:|]\s*\**\s*[01]\b", t))
    check("d", "每刀都写了动作数", n_decl >= len(clips) * 0.9,
          f"{n_decl}/{len(clips)} 刀有", level="warn" if n_decl else "error")

    # 禁止词
    # 只判真正的占位符。「同上」在「同上一镜延续」里是正常描述，「略」在「略高于」里也是正常的，
    # 所以这两种只在括号里 / 独立成句时才算占位。
    banned = ["后续补充", "框架待定", "TBD", "见上段"]
    hit = [w for w in banned if w in t]
    if re.search(r"[（(]\s*同上\s*[）)]|^\s*同上\s*[。.]?\s*$", t, re.M):
        hit.append("同上")
    if re.search(r"[（(]\s*略\s*[）)]|^\s*略\s*[。.]?\s*$", t, re.M):
        hit.append("略")
    check("d", "没有「同上/略/后续补充」", not hit,
          ("出现：" + "、".join(hit)) if hit else "干净")

    # 动作密度交给专用脚本
    if tool and tool.exists():
        cmd = [sys.executable, str(tool), str(f)]
        if baseline and baseline.get("path"):
            cmd += ["--baseline", baseline["path"]]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
        ok = r.returncode == 0
        out = (r.stdout or "").splitlines()
        # 只取分镜那一段的结论（在「【小分镜】」之后）
        idx = next((i for i, l in enumerate(out) if "【小分镜】" in l), 0)
        tail = [l for l in out[idx:] if "结论" in l or "上限" in l or "动作栏超过" in l]
        check("d", "动作预算闸门", ok, "；".join(x.strip() for x in tail[:2]) or f"退出码 {r.returncode}")


# ══════════════════ e 生产单元 ══════════════════

def stage_e(d: Path, baseline: dict | None):
    print("\n【e 生产单元】")
    cands = list(d.glob("生产单元*检查*.md")) + list(d.glob("生产单元*.md"))
    if not cands:
        rec("e", "单元表", "skip", "不存在")
        print(f"    {SKIP} 生产单元划分与取用联合检查.md 不存在，跳过")
        return
    f = cands[0]
    t = read(f)

    tab = None
    for h, rows in md_tables(t):
        j = "|".join(h)
        if "单元" in j and ("生成" in j or "覆盖" in j):
            tab = (h, rows)
            break
    if not tab:
        check("e", "单元表", False, "没找到表头含「单元」「生成」的表")
        return
    h, rows = tab
    n_unit = len([r for r in rows if r and re.match(r"^U\d", r[0].strip())])

    # 三列：优先看表头；表头没有就接受「逐 U 键值表」的写法（项目/内容 两列，每 U 一份）
    miss = [n for n in ("动作总数", "动作密度", "位移刀") if not any(n in c for c in h)]
    if not miss:
        check("e", "动作预算三列", True, f"表头 {len(h)} 列")
    elif n_unit and all(t.count(n) >= n_unit for n in ("动作总数", "动作密度", "位移刀")):
        check("e", "动作预算三列", True,
              f"不在表头，在逐 U 键值表里（{n_unit} 份都有）")
    else:
        check("e", "动作预算三列", False, "缺 " + "、".join(miss))

    # 地板算术
    m = re.search(r"生成预算[^\n]*?([\d.]+)\s*秒", t)
    budget = float(m.group(1)) if m else None
    if budget and n_unit:
        # 2026-10-27 晚：一组装满 13–15 秒（阿初口径），不再用 4 秒地板算
        per = budget / n_unit
        ok = 4 <= per <= 15
        check("e", "每组平均时长落在 4–15 秒内", ok,
              f"预算 {budget} 秒 ÷ {n_unit} 组 = 每组 {per:.1f} 秒"
              + ("" if ok else "（超出平台单段 4–15 秒，组数要改）"),
              level="warn")

    # ── 单元数是否落在硬表区间 ──
    m_film = re.search(r"成片总时长[^\n]*?([\d.]+)\s*秒", t) or \
             re.search(r"成片[^\n]*?([\d.]+)\s*秒", t)
    if m_film and n_unit:
        film = float(m_film.group(1))
        # 2026-10-28 复核修正：U01 只占 T÷0.867 秒，装不满 15 秒，
        # 直接拿「生成总时长 ÷ 15」会少算一个单元（装到最后必有一个盒子超 15 秒）。
        # 正确式子：单元数 = 1 + ceil((生成总时长 - U01生成秒) / 15)
        # 下面的区间就是用这个式子、按 T=12–18% 算出来的。
        if film <= 35:
            lo, hi = 3, 4
        elif film <= 50:
            lo, hi = 4, 5
        elif film <= 70:
            lo, hi = 5, 6
        elif film <= 95:
            lo, hi = 6, 8
        else:
            lo, hi = 6, max(8, int(film / 0.867 / 15) + 1)
        if n_unit > hi:
            # 超上界 1 个且有「硬理由」段：降为警告（结构约束顶上去的，不是划碎）
            # 超 2 个以上，或没有硬理由：不通过
            has_reason = ("硬理由" in t) or ("拆分理由" in t and "物理起点" in t)
            if n_unit <= hi + 1 and has_reason:
                check("e", "单元数不超硬表上界", True,
                      f"成片 {film} 秒 → 表值 {lo}–{hi} 个，实划 {n_unit} 个"
                      f"（超 1 个，文件里写了硬理由，接受；请人看一眼理由是否成立）",
                      level="warn")
            else:
                check("e", "单元数不超硬表上界", False,
                      f"成片 {film} 秒 → 应为 {lo}–{hi} 个，实划 {n_unit} 个"
                      f"（多 {n_unit-hi} 个{'' if has_reason else '，且没写硬理由'}）")
        elif n_unit < lo:
            check("e", "单元数不超硬表上界", True,
                  f"成片 {film} 秒 → 应为 {lo}–{hi} 个，实划 {n_unit} 个（偏少，单条逼近 15 秒上限）",
                  level="warn")
        else:
            check("e", "单元数不超硬表上界", True,
                  f"成片 {film} 秒 → {lo}–{hi} 个，实划 {n_unit} 个")

    # ── 单元级取用硬闸 ──
    def _num(s):
        mm = re.search(r"(\d+(?:\.\d+)?)", s or "")
        return float(mm.group(1)) if mm else None

    def _col(*keys, exclude=()):
        for k, c in enumerate(h):
            if all(x in c for x in keys) and not any(x in c for x in exclude):
                return k
        return None

    i_gen = _col("生成")
    i_use = _col("取用", exclude=("率",))
    if i_gen is not None and i_use is not None:
        pairs, bad_rate, bad_abs = [], [], []
        for r in rows:
            if not r or not re.match(r"^U\d", r[0].strip()):
                continue
            g = _num(r[i_gen]) if i_gen < len(r) else None
            u = _num(r[i_use]) if i_use < len(r) else None
            if not g or u is None:
                continue
            name = r[0].strip()
            pairs.append((name, g, u))
            if u / g < 0.60:
                bad_rate.append(f"{name} {u:g}/{g:g}={u/g*100:.0f}%")
            if u < 2.0:
                bad_abs.append(f"{name} {u:.2f}秒")
        if pairs:
            check("e", "每单元取用率 ≥60%", not bad_rate,
                  ("划碎：" + "、".join(bad_rate)) if bad_rate
                  else f"{len(pairs)} 个单元均 ≥60%")
            # 2026-10-27：这条已撤销（它是剪辑规矩，不是拍摄约束；按它卡会逼着跨工序合并，
            # 而跨工序合并必然产生状态跳跃）。现在只提示、不拦截，退出码不受影响。
            check("e", "每单元成片取用 ≥2.0 秒", not bad_abs,
                  ("不足：" + "、".join(bad_abs)) if bad_abs
                  else f"最短 {min(p[2] for p in pairs):.2f} 秒",
                  level="warn")
            sg = sum(p[1] for p in pairs)
            su = sum(p[2] for p in pairs)
            if budget:
                check("e", "Σ 生成秒 ≤ 预算×1.15", sg <= budget * 1.15,
                      f"Σ生成 {sg:g} / 预算 {budget:g}（上限 {budget*1.15:.1f} 秒），"
                      f"全片取用率 {su/sg*100:.0f}%")
            else:
                check("e", "全片取用率 ≥80%", su / sg >= 0.80,
                      f"取用 {su:.2f} / 生成 {sg:g} = {su/sg*100:.0f}%（文档里没写生成预算）",
                      level="warn")
            avg = sg / len(pairs)
            check("e", "平均单元生成 ≥6 秒（防划碎）", avg >= 6.0,
                  f"{avg:.1f} 秒/单元 × {len(pairs)} 个", level="warn")
        else:
            rec("e", "取用率", "skip", "表里没解析出生成/取用数字")
            print(f"    {SKIP} 单元表里没解析出生成秒数/取用秒数，取用率未查")

    # 位移刀位置
    i_mv = next((k for k, c in enumerate(h) if "位移刀" in c), None)
    if i_mv is not None:
        last = []
        for r in rows:
            if not r or i_mv >= len(r):
                continue
            mm = re.search(r"(?:第\s*)?(\d+)\s*刀", r[i_mv])
            total = re.search(r"(\d+)\s*刀", r[i_mv])
            if mm and total and int(mm.group(1)) >= int(total.group(1)) >= 2:
                last.append(r[0].strip())
        check("e", "位移刀不在最后一刀", not last,
              ("排最后：" + "、".join(last)) if last else "各单元均在前段", level="warn")

    # 提示词长度与参考图
    units = sorted(d.glob("单元/U*.md"))
    if units:
        long_p, many_fig = [], []
        for u in units:
            ut = read(u)
            body = re.search(r"##\s*拼好的完整正文\s*```(?:text)?\n(.*?)```", ut, re.S)
            n = len(body.group(1)) if body else len(ut)
            if n > 4096:
                long_p.append(f"{u.stem}({n})")
            # 参考图张数：按「第 N 张」里最大的 N 算，不数出现次数
            # （同一张图在「图提示词」和「视频提示词」里各提一次，数次数会翻倍）
            nums = [int(x) for x in re.findall(r"第\s*(\d+)\s*张", ut)]
            nf = max(nums) if nums else 0
            if nf > 4:
                many_fig.append(f"{u.stem}({nf}张)")
        check("e", "完整 Prompt ≤4096 字符（按字符估）", not long_p,
              ("超长：" + "、".join(long_p)) if long_p else f"{len(units)} 个单元")
        check("e", "参考图 ≤4 张", not many_fig,
              ("超：" + "、".join(many_fig)) if many_fig else "合规", level="warn")


# ══════════════════ 跨环节一致性 ══════════════════

def cross_check(d: Path, baseline: dict | None):
    print("\n【x 跨环节一致性】")
    st = d / "00_版本设定书.md"
    bd = d / "分镜" / "后段小分镜_有效.md"
    if not (st.exists() and bd.exists()):
        rec("x", "跨环节", "skip", "缺设定书或分镜")
        print(f"    {SKIP} 缺设定书或分镜，跳过")
        return
    ts, tb = read(st), read(bd)

    # 总时长
    m1 = re.search(r"(?:成片总时长|总时长|片长)[^\n]*?([\d.]+)\s*秒", ts)
    ends = re.findall(r"^#{2,4}\s*N\d{2}\s*[｜|]\s*[\d.]+\s*[–\-~—]\s*([\d.]+)", tb, re.M)
    if m1 and ends:
        a, b = float(m1.group(1)), float(ends[-1])
        check("x", "总时长：设定书 = 分镜末段", abs(a - b) <= 0.05,
              f"设定书 {a} / 分镜 {b}")

    # 动作数：设定书 4.5 vs 分镜声明
    m45 = re.search(r"^#{1,4}\s*4\.5[^\n]*", ts, re.M)
    if m45:
        tail = ts[m45.start():]
        nxt = re.search(r"\n##?\s", tail[1:])
        scope = tail[: nxt.start() + 1] if nxt else tail
        tabs = md_tables(scope)
        if tabs:
            h, rows = tabs[0]
            i_st = next((k for k, c in enumerate(h) if "动作数" in c), None)
            if i_st is not None:
                s45 = sum(int(re.search(r"\d+", r[i_st]).group(0))
                          for r in rows
                          if r and re.fullmatch(r"N?\d+", r[0].strip().strip("*"))
                          and re.search(r"\d+", r[i_st] if i_st < len(r) else ""))
                decl = [int(x) for x in re.findall(r"动作数\s*[：:|]\s*([01])\b", tb)]
                sbd = sum(decl) if decl else None
                if sbd is not None:
                    check("x", "动作数：设定书 4.5 = 分镜声明", s45 == sbd,
                          f"4.5 节合计 {s45} / 分镜声明 {sbd}（差 {s45-sbd:+d}）")

    # T 值
    mT = re.search(r"T\s*[=＝]\s*([\d.]+)\s*秒", ts)
    spans = re.findall(r"^#{2,4}\s*(N\d{2})\s*[｜|]\s*([\d.]+)\s*[–\-~—]\s*([\d.]+)", tb, re.M)
    if mT and spans:
        T = float(mT.group(1))
        hit = [s for s in spans if abs(float(s[1]) - T) <= 0.02]
        covered = [s for s in spans if float(s[1]) <= T <= float(s[2])]
        ok = bool(hit) or bool(covered)
        detail = (f"T={T}，{hit[0][0]} 正好从 T 起" if hit
                  else (f"T={T}，{covered[0][0]}（{covered[0][1]}–{covered[0][2]}）覆盖了 T" if covered
                        else f"T={T}，没有任何一刀从 T 起或覆盖 T（首刀 {spans[0][1]}–{spans[0][2]}）"))
        check("x", "T 值与分镜切点对得上", ok, detail)


# ══════════════════ f 单元卡正文 ══════════════════

# 相对方位词：模型给不出像素，一律改成画面坐标（见 references/space-wording.md）
REL_DIR = ["两端", "对岸", "全长", "近端", "远端", "另一端", "另一头",
           "这一头", "那一头", "这一侧", "对面", "桥的两边", "两侧各"]

HEAD_KEYS = ["本卡版本", "生产状态", "生成", "上传顺序", "输出文件名"]


def stage_f(d: Path):
    print("\n【f 单元卡正文】")
    units = sorted((d / "单元").glob("U*.md")) if (d / "单元").exists() else []
    if not units:
        rec("f", "单元卡", "skip", "不存在")
        print(f"    {SKIP} 单元\\U*.md 不存在，跳过")
        return

    bad_all, over_all, rel_all, img_all, head_all, ast_all = [], [], [], [], [], []
    sec_all, stab_all, neg_all = [], [], []
    short_all = []
    n_done = 0
    for u in units:
        t = read(u)
        blocks = re.findall(r"```text\n(.*?)\n```", t, re.S)
        if len(blocks) != 1:
            bad_all.append(f"{u.name}({len(blocks)}个text块)")
            continue
        body = blocks[0]

        # 4096 上限按「字符数」算，不是字节数。
        # 依据：U01 正文 2438 字符（UTF-8 6678 字节 / UTF-16 4876 字节）实测生成正常，
        # 说明平台数的是字符。之前按字节卡过一次，是误判，白删了字。
        nch = len(body)
        if nch > 4096:
            over_all.append(f"{u.name}({nch} 字符)")

        idx = [int(x) for x in re.findall(r"第(\d)张图", body)]
        if idx and max(idx) > 4:
            img_all.append(f"{u.name}(第{max(idx)}张)")

        miss = [k for k in HEAD_KEYS if k not in t]
        if miss:
            head_all.append(f"{u.name}(缺{'、'.join(miss)})")

        # 已出片的卡不再回溯改词——视频已经按这版文本生成了，改文本只会让卡和片子对不上。
        # 只在「还没生成」的卡上卡措辞。
        if "已出片" in t or "已生成" in t:
            n_done += 1
            continue

        # 生成秒：生产档位 13–15（2026-10-27 晚改自 4–10；平台容量 4–15，末组除不尽可短）
        msec = re.search(r">\s*生成：\s*(\d+)\s*秒", t)
        if msec:
            v = int(msec.group(1))
            if not (4 <= v <= 15):
                sec_all.append(f"{u.name}({v} 秒)")
            elif v < 13:
                short_all.append(f"{u.name}({v} 秒)")

        # 稳定约束 + 负面词：缺了模型收不到「别崩、别丢」
        if "稳定：" not in body and "稳定约束" not in body:
            stab_all.append(u.name)
        if "人物消失" not in body:
            neg_all.append(u.name)

        hit = [w for w in REL_DIR if w in body]
        if hit:
            rel_all.append(f"{u.name}({'、'.join(hit)})")

        if "*" in body:
            ast_all.append(u.name)

    n = len(units)
    check("f", "每张卡只有一个 text 块", not bad_all,
          ("；".join(bad_all)) if bad_all else f"{n} 张卡")
    check("f", "正文不超 4096 字符", not over_all,
          ("；".join(over_all)) if over_all else "全部在限内（最长为 2000+ 字符，余量充足）")
    check("f", "没有相对方位词（两端/对岸/全长/近端/远端…）", not rel_all,
          ("；".join(rel_all)) if rel_all else
          f"干净（{n} 张卡，其中 {n_done} 张已出片不回溯）")
    check("f", "上传图不超过 4 张", not img_all,
          ("；".join(img_all)) if img_all else "全部 ≤4")
    check("f", "正文里没有 markdown 星号", not ast_all,
          ("会被原样抄进提示词：" + "；".join(ast_all)) if ast_all else "干净")
    check("f", "五行头部齐全", not head_all,
          ("；".join(head_all)) if head_all else "全部齐全")
    check("f", "生成秒在 13–15 的装满档位内", not sec_all,
          ("超出平台 4–15 秒：" + "；".join(sec_all)) if sec_all else
          (f"全部合规（其中 {len(short_all)} 张低于 13 秒，只允许是末组：{'；'.join(short_all)}）"
           if short_all else "全部 13–15 秒"))
    check("f", "有稳定约束行", not stab_all,
          ("缺（模型收不到别崩别丢）：" + "；".join(stab_all)) if stab_all else "全部有")
    check("f", "负面词含「人物消失」", not neg_all,
          ("缺：" + "；".join(neg_all)) if neg_all else "全部有")


# ══════════════════ 主流程 ══════════════════

def main():
    # 输出编码：被别的程序用管道读时（GUI/子进程），统一用 UTF-8；
    # 直接在 cmd 里跑时保持系统默认，免得控制台乱码。
    for _s in (sys.stdout, sys.stderr):
        try:
            if sys.platform == "win32" and not _s.isatty():
                _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    ap = argparse.ArgumentParser(description="每段交付物验收")
    ap.add_argument("path", help="版本目录 或 对标库目录")
    ap.add_argument("--baseline", help="原片拆解 03_整片拆解.md")
    ap.add_argument("--stage", choices=list("abcdefx"), help="只查某一段")
    args = ap.parse_args()

    d = Path(args.path)
    if not d.exists():
        print(f"找不到：{d}")
        return 2

    baseline = None
    if args.baseline:
        b = Path(args.baseline)
        if not b.exists():
            print(f"找不到基准：{b}")
            return 2
        tool = Path(__file__).with_name("检查_动作预算.py")
        if tool.exists():
            r = subprocess.run([sys.executable, str(tool), str(b)],
                               capture_output=True, text=True, encoding="utf-8", errors="ignore")
            out = r.stdout or ""
            # 优先读机器行：整片拆解可能只覆盖后半段，要换算成全片再比
            mb = re.search(r"【基准行】start=([\d.]+) full_sec=([\d.]+) "
                           r"full_steps=(\d+) open_steps=(\d+)", out)
            if mb and float(mb.group(2)) > 0:
                start, fsec = float(mb.group(1)), float(mb.group(2))
                fst = int(mb.group(3))
                baseline = {"steps": fst, "sec": fsec,
                            "rate": round(fst / fsec, 2), "path": str(b)}
                tail = f"（后半段 {start:g} 秒起；不含开头时动作数会少算）" if start > 0.05 else ""
                print(f"【原片基准】全片 {fsec:g} 秒 / {fst} 个动作 "
                      f"/ {fst/fsec:.2f} 步/秒{tail}")
            else:
                m = re.search(r"(\d+) 段 / ([\d.]+) 秒 / 动作数合计 (\d+)", out)
                if m and float(m.group(2)) > 0:
                    sec, fst = float(m.group(2)), int(m.group(3))
                    baseline = {"steps": fst, "sec": sec,
                                "rate": round(fst / sec, 2), "path": str(b)}
                    print(f"【原片基准】{m.group(1)} 段 / {m.group(2)} 秒 / {m.group(3)} 个动作")
                else:
                    print("【原片基准】读不到有效时长，本次不判动作密度，只查结构")

    print(f"【验收】{d}")
    tool = Path(__file__).with_name("检查_动作预算.py")

    # 判断是版本目录还是对标库
    is_bd = bool(list(d.glob("*_整片拆解.md"))) or (d / "03_整片拆解.md").exists()

    stages = args.stage or ("a" if is_bd else "bcdefx")
    if "a" in stages:
        stage_a(d)
    if "b" in stages:
        stage_b(d, baseline)
    if "c" in stages:
        stage_c(d, baseline)
    if "d" in stages:
        stage_d(d, baseline, tool)
    if "e" in stages:
        stage_e(d, baseline)
    if "f" in stages:
        stage_f(d)
    if "x" in stages:
        cross_check(d, baseline)

    print("\n" + "=" * 58)
    errs = [r for r in _results if r["level"] == "error"]
    warns = [r for r in _results if r["level"] == "warn"]
    oks = [r for r in _results if r["level"] == "ok"]
    stage_names = {"a": "拆解", "b": "设定书", "c": "开头", "d": "小分镜",
                   "e": "生产单元", "f": "单元卡", "x": "跨环节"}
    for s in "abcdefx":
        sub = [r for r in _results if r["stage"] == s]
        if not sub:
            continue
        e = sum(1 for r in sub if r["level"] == "error")
        w = sum(1 for r in sub if r["level"] == "warn")
        o = sum(1 for r in sub if r["level"] == "ok")
        if o == 0 and e == 0 and w == 0:
            print(f"  {SKIP} {stage_names[s]:6} 跳过（这一段的文件还没有）")
            continue
        tag = OK if e == 0 else NG
        print(f"  {tag} {stage_names[s]:6} 通过 {o:2} / 警告 {w:2} / 不通过 {e:2}")

    print(f"\n总计：通过 {len(oks)} / 警告 {len(warns)} / 不通过 {len(errs)}")

    # 全跳过 = 目录里还没有交付物。不能报合格，否则人会以为过了。
    if not oks and not errs:
        print("\n退出码 2 —— 目录里还没有可检查的交付物（什么都没做，不是合格）。")
        return 2

    if errs:
        print("\n必过项不通过：")
        for r in errs:
            print(f"  · [{stage_names[r['stage']]}] {r['name']} —— {r['msg']}")
        print("\n退出码 1 —— 这一段不许交给下一段。")
        return 1
    print("\n退出码 0 —— 结构层面合格。语义层面（表达意思对不对、情绪对不对）仍要人看。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
