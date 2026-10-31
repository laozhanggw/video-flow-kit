#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
检查_自洽.py —— 一个数只许活在一个地方

为什么要有这个脚本（2026-10-31）：
    B0018 第③段交付后，一段 9.4 秒的片子出现了三个时长（9.433／9.36／9.53）、
    三个全片总长（47.300／47.08／47.368）、两个素材总秒（10.800／11.0），
    同一份文件里对白写成 3 句又写成 2 句。
    这些都不是判断问题，是算术问题。人工审计两轮都没抓全——因为人只能核销
    "我改的那处改了没"，核销不了"全文还剩几处"。机器可以。

它查什么（对应 00_字段契约.md 第六节）：
    C1  Σ素材 × 0.867 是否等于 T                     （派生链自洽）
    C2a 骨架段界 是否等于 按 4.5 素材秒累加出来的段界
    C2b ③段刀界 是否落在骨架段界上
    C3  三处素材总秒是否一致（4.5 / ③逐刀 / 单元生成秒）
    C4  对白条数全文是否只有一个值
    C5  末态是否恰好十行 键 = 值
    C9  骨架末值 是否等于「= 总时长」那个数
    C6  同一产物是否被同时标为「必读」和「不必读」（--spec）
    C7  旧文件名是否还有残留（--spec）

用法：
    python 检查_自洽.py --v <V目录>        检查一个版本
    python 检查_自洽.py --root <批次目录>   检查批次下所有 V 目录
    python 检查_自洽.py --spec <规范目录>   只查指令层（C6／C7）
    python 检查_自洽.py --v ... --spec ... 两样都查

退出码：0 = 全 PASS／WARN   1 = 有 FAIL
"""
import io
import os
import re
import sys
import argparse

TOL = 0.02          # 秒级容差
RATIO_MAT = 1.153   # 素材 / 覆盖
RATIO_FILM = 0.867  # 成片 / 素材

SEG_CHARS = "①②③④⑤⑥⑦⑧⑨"
CN_NUM = {"一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5,
          "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


# ─────────────────────────── 基础工具 ───────────────────────────

def read(p):
    try:
        return io.open(p, encoding="utf-8", errors="replace").read()
    except Exception:
        return ""


def split_tables(text):
    """把 markdown 表格切成 [(header, [(行号, cells)])]"""
    tables, hdr, cur = [], None, None
    for i, line in enumerate(text.split("\n"), 1):
        s = line.strip()
        if s.startswith("|") and s.count("|") >= 3:
            cells = [c.strip() for c in s.strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c.replace(" ", "")) for c in cells if c):
                continue
            if hdr is None:
                hdr, cur = cells, []
            else:
                cur.append((i, cells))
        else:
            if hdr is not None:
                tables.append((hdr, cur))
                hdr, cur = None, None
    if hdr is not None:
        tables.append((hdr, cur))
    return tables


def find_table(tables, pred):
    for hdr, rows in tables:
        try:
            if pred(hdr):
                return hdr, rows
        except Exception:
            continue
    return None, None


def col_of(hdr, *keys):
    for i, c in enumerate(hdr):
        if all(k in c for k in keys):
            return i
    return -1


def prange(s):
    """从 '0.000–2.900' 里取 (0.0, 2.9)；支持 – - ~ 至"""
    m = re.search(r"(\d+(?:\.\d+)?)\s*[–\-~—至]\s*(\d+(?:\.\d+)?)", s)
    if not m:
        return None
    return float(m.group(1)), float(m.group(2))


def fnum(s):
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    return float(m.group(1)) if m else None


def pdur(s):
    """素材秒时长，两种合法写法都认：
       · 区间 '3.300–6.200' → 2.9（素材时间轴上的起止）
       · 单值 '2.900'       → 2.9（直接就是时长）
       2026-10-31 修：原来只认区间，换一种写法就误报「没找到 4.5 逐刀表」。
    """
    r = prange(s)
    if r:
        return r[1] - r[0]
    return fnum(s)


def seg_key(name):
    for ch in name:
        if ch in SEG_CHARS:
            return ch
    return name.strip()[:4]


def r3(x):
    return ("%.3f" % x).rstrip("0").rstrip(".")


# ─────────────────────────── 结果收集 ───────────────────────────

class Report(object):
    def __init__(self, title):
        self.title = title
        self.items = []   # (level, code, msg)

    def add(self, level, code, msg):
        self.items.append((level, code, msg))

    def fails(self):
        return [x for x in self.items if x[0] == "FAIL"]

    def dump(self):
        print("=" * 70)
        print(self.title)
        print("=" * 70)
        order = {"FAIL": 0, "WARN": 1, "PASS": 2}
        for level, code, msg in sorted(self.items, key=lambda x: (order[x[0]], x[1])):
            mark = {"FAIL": "[FAIL]", "WARN": "[WARN]", "PASS": "[PASS]"}[level]
            print("%s %-4s %s" % (mark, code, msg))
        print("-" * 70)
        f = len(self.fails())
        if f:
            print("结论：%d 项 FAIL。这些是算术问题，不是判断问题，改完再往下走。" % f)
        else:
            print("结论：没有硬冲突。")
        return f


# ─────────────────────────── 设定书：C1 / C2a / C9 ───────────────────────────

def parse_settingbook(vdir):
    """返回 dict：骨架[(段key, (s,e), 行号)]、cover/mat[(刀, (s,e), 行号)]、文本"""
    p = os.path.join(vdir, "00_版本设定书.md")
    if not os.path.isfile(p):
        return None
    txt = read(p)
    tabs = split_tables(txt)

    hdr, rows = find_table(tabs, lambda h: h and h[0].strip() == "段"
                           and any("秒" in c for c in h[:3]))
    skel = []
    if rows:
        ci = col_of(hdr, "秒")
        for ln, cells in rows:
            if len(cells) <= ci:
                continue
            rg = prange(cells[ci])
            if rg:
                skel.append((seg_key(cells[0]), rg, ln))

    hdr, rows = find_table(tabs, lambda h: any("刀号" in c for c in h)
                           and any("覆盖" in c for c in h))
    cov, mat = [], []
    if rows:
        c_cov = col_of(hdr, "覆盖")
        c_mat = col_of(hdr, "素材")
        if c_mat < 0:
            c_mat = col_of(hdr, "起止")
        for ln, cells in rows:
            if len(cells) <= max(c_cov, c_mat):
                continue
            name = cells[0]
            rc = prange(cells[c_cov])
            d = pdur(cells[c_mat])
            if rc:
                cov.append((name, rc, ln))
            if d is not None:
                mat.append((name, (0.0, d), ln))
    return {"txt": txt, "path": p, "skel": skel, "cover": cov, "mat": mat}


def check_settingbook(vdir, rep):
    sb = parse_settingbook(vdir)
    if not sb:
        # 2026-10-31 修：原来是 WARN。结果路径指错、目录里根本没设定书，也照样报「没有硬冲突」，
        # 等于给了一盏假绿灯。设定书是这一版的地基，找不到就是 FAIL。
        rep.add("FAIL", "C0", "这个目录里没有 00_版本设定书.md：%s" % vdir)
        return
    if not sb["cover"] or not sb["mat"]:
        rep.add("WARN", "C0", "设定书里没找到 4.5 逐刀表（需同时有「刀号」「覆盖」列）")
        return
    if len(sb["cover"]) != len(sb["mat"]):
        rep.add("FAIL", "C0", "4.5 的「覆盖」列 %d 行、「素材」列 %d 行，行数不一致"
                % (len(sb["cover"]), len(sb["mat"])))

    # ── C1 全片派生链（15 刀累计，取整误差会累加，只报 WARN）
    T_cover = sb["cover"][-1][1][1]
    sum_mat = sum(e - s for _, (s, e), _ in sb["mat"])
    derived = sum_mat * RATIO_FILM
    diff = abs(derived - T_cover)
    if diff > 0.1:
        need = T_cover / RATIO_FILM
        rep.add("WARN", "C1",
                "全片 Σ素材 %s 秒 × 0.867 = %s 秒，覆盖列末值 %s 秒，差 %.3f 秒。"
                "→ 素材预算少 %.1f 秒（要 %.1f 秒才够剪满）。补素材，不许改覆盖列"
                % (r3(sum_mat), r3(derived), r3(T_cover), diff,
                   need - sum_mat, need))
    else:
        rep.add("PASS", "C1", "全片 Σ素材×0.867 = %s ≈ 覆盖末值 %s"
                % (r3(derived), r3(T_cover)))

    # ── C2a 逐刀素材秒是否等于 覆盖×1.153（允许 ±0.05 秒取整）
    bad = []
    for (name, (cs, ce), ln), (_, (ms, me), _) in zip(sb["cover"], sb["mat"]):
        if ce - cs <= 0:
            continue
        want = (ce - cs) * RATIO_MAT
        got = me - ms
        if abs(got - want) > 0.05 + 1e-9:
            bad.append("%s 素材 %.3f 秒，应为 %.3f（覆盖 %.3f×1.153，第%d行）"
                       % (name, got, want, ce - cs, ln))
    if bad:
        rep.add("FAIL", "C2a",
                "逐刀素材秒偏离「覆盖×1.153」超过 0.05 秒：" + "；".join(bad[:6]))
    else:
        rep.add("PASS", "C2a", "逐刀素材秒都等于 覆盖×1.153（±0.05 取整）")

    # ── C2a2 覆盖列是否连续、且逐段等于骨架段界（成片剪点只认覆盖列）
    if sb["skel"]:
        pairs = list(zip(sb["cover"], sb["mat"]))
        idx, problems = 0, []
        for seg, (ss, se), _ in sb["skel"]:
            if idx >= len(pairs):
                break
            first, last = pairs[idx][0][1][0], None
            while idx < len(pairs) and pairs[idx][0][1][0] < se - 1e-6:
                last = pairs[idx][0][1][1]
                idx += 1
            if last is None:
                continue
            if abs(first - ss) > TOL or abs(last - se) > TOL:
                problems.append("段%s 骨架 %s–%s，覆盖列 %s–%s"
                                % (seg, r3(ss), r3(se), r3(first), r3(last)))
        if problems:
            rep.add("FAIL", "C2a2", "覆盖列与骨架段界对不上：" + "；".join(problems))
        else:
            rep.add("PASS", "C2a2", "覆盖列逐段与骨架段界一致（成片剪点以覆盖列为准）")

    # ── C9 骨架末值 vs 「= 总时长」
    if sb["skel"]:
        last = sb["skel"][-1][1][1]
        # 全文每一处「总时长 X」都要等于骨架末值。两种写法都认：
        #   「总时长 = 47.1 秒」（数字在右）／「= 47.300 = 总时长。」（数字在左）
        # 2026-10-31 修：原来只 search 第一处，会漏掉交付契约里的另一个值
        hits = []
        for ln, line in enumerate(sb["txt"].split("\n"), 1):
            if "总时长" not in line:
                continue
            m = re.search(r"总时长\s*(?:[=＝]\s*)?([\d.]+)", line) \
                or re.search(r"([\d.]+)\s*=\s*总时长", line)
            if m:
                hits.append((ln, float(m.group(1))))
        bad = [(ln, v) for ln, v in hits if abs(v - last) > 0.1]
        if bad:
            rep.add("FAIL", "C9",
                    "骨架末段止于 %s 秒，但另有 %d 处写成别的值：%s "
                    "→ 全片总长不止一个家（另见母版实测）"
                    % (r3(last), len(bad),
                       "；".join("第%d行 %s" % (ln, r3(v)) for ln, v in bad[:5])))
        elif hits:
            rep.add("PASS", "C9", "全文 %d 处「总时长」都是 %s" % (len(hits), r3(last)))
        else:
            rep.add("WARN", "C9", "全文没写「总时长」，无法核对")


# ─────────────────────────── ③段：C2b / C3a ───────────────────────────

def find_opening(vdir):
    d = os.path.join(vdir, "开头")
    if not os.path.isdir(d):
        return None
    best, best_len = None, 0
    for fn in os.listdir(d):
        if not fn.endswith(".md"):
            continue
        p = os.path.join(d, fn)
        t = read(p)
        if "素材秒" in t and "成片" in t and len(t) > best_len:
            best, best_len = p, len(t)
    return best


def parse_opening_cuts(p):
    """解析 7.1 逐刀秒数表 → [(刀名, 素材秒, (成片起, 成片止), 段, 行号)]"""
    txt = read(p)
    tabs = split_tables(txt)
    hdr, rows = find_table(tabs, lambda h: any("素材秒" in c for c in h)
                           and any("成片" in c for c in h))
    out = []
    if not rows:
        return out
    c_mat = col_of(hdr, "素材")
    c_film = col_of(hdr, "成片")
    c_seg = col_of(hdr, "段")
    for ln, cells in rows:
        if len(cells) <= max(c_mat, c_film):
            continue
        m = fnum(cells[c_mat])
        rg = prange(cells[c_film])
        if m is None or not rg:
            continue
        seg = cells[c_seg] if 0 <= c_seg < len(cells) else ""
        out.append((cells[0], m, rg, seg.strip(), ln))
    return out


def check_opening(vdir, rep, sb):
    p = find_opening(vdir)
    if not p:
        rep.add("WARN", "C0", "找不到 ③ 段产物（开头目录里没有含「素材秒／成片」的文件）")
        return
    cuts = parse_opening_cuts(p)
    if not cuts:
        rep.add("WARN", "C0", "%s 里没找到逐刀秒数表（需同时有「素材秒」「成片」列）"
                % os.path.basename(p))
        return
    base = os.path.basename(p)

    # 刀号 → 骨架段（用 4.5 覆盖区间落在哪个骨架段里判定）
    cut2seg = {}
    if sb and sb["skel"]:
        for name, (cs, ce), _ in sb["cover"]:
            for seg, (ss, se), _ in sb["skel"]:
                if ss - 1e-6 <= cs and ce <= se + 1e-6:
                    cut2seg[name] = seg
                    break

    # C3a 素材总秒（只比 ③ 实际覆盖的那几刀，不跟全片比）
    # ③ 的刀名可能和 4.5 不同（如「镜头1」vs「N01」），也可能把 4.5 的刀号填在「段」列里。
    # 2026-10-31 修：原来只认「段」列，换一种填法就静默跳过，等于这项从来没查过。
    if sb and sb["mat"]:
        sb_by_name = {name.strip(): (s, e) for name, (s, e), _ in sb["mat"]}
        matched = [c for c in cuts
                   if c[0].strip() in sb_by_name or c[3].strip() in sb_by_name]
        if matched:
            sum_o = sum(c[1] for c in matched)
            keys = set()
            for c in matched:
                for cand in (c[0].strip(), c[3].strip()):
                    if cand in sb_by_name:
                        keys.add(cand)
            sum_sb = sum(e - s for k, (s, e) in sb_by_name.items() if k in keys)
            n = len(matched)
            if abs(sum_o - sum_sb) > 0.05 * n + 1e-9:
                rep.add("FAIL", "C3a",
                        "③逐刀素材合计 %s 秒，设定书同名刀素材合计 %s 秒，差 %.2f 秒（容差 %.2f）"
                        "→ 两处对同一批刀给了不同素材秒"
                        % (r3(sum_o), r3(sum_sb), abs(sum_o - sum_sb), 0.05 * n))
            else:
                rep.add("PASS", "C3a", "素材总秒一致（③ %s ／ 4.5 %s，%d 刀）"
                        % (r3(sum_o), r3(sum_sb), n))
        else:
            rep.add("WARN", "C3a",
                    "%s 的刀名（%s…）在 4.5 里一个都对不上，无法比较素材总秒"
                    % (base, cuts[0][0]))

    # C2b 刀界是否落在骨架段界上
    if sb and sb["skel"]:
        agg = {}
        for name, m, rg, seg, ln in cuts:
            k = cut2seg.get(seg.strip()) or (seg_key(seg) if seg else "")
            agg.setdefault(k, []).append((rg, ln))
        problems = []
        for key, (ss, se), _ in sb["skel"]:
            if key not in agg:
                continue
            f_start = min(r[0] for r, _ in agg[key])
            f_end = max(r[1] for r, _ in agg[key])
            if abs(f_start - ss) > TOL or abs(f_end - se) > TOL:
                problems.append("段%s 骨架 %s–%s，按刀累加 %s–%s"
                                % (key, r3(ss), r3(se), r3(f_start), r3(f_end)))
        if problems:
            rep.add("FAIL", "C2b",
                    "%s 的刀界没落在骨架段界上（刀跨了段，成片剪点会漂）：" % base
                    + "；".join(problems))
        else:
            rep.add("PASS", "C2b", "刀界与骨架段界对齐")


# ─────────────────────────── 全文：C4 / C5 ───────────────────────────

P_DLG = re.compile(r"(\d+|[一两二三四五六七八九十])\s*句\s*(对白|对话|台词)")
P_ONLY = re.compile(r"只有\s*(\d+|[一两二三四五六七八九十])\s*句")
P_SENT = re.compile(r"([一两二三四五六七八九十])\s*句话")


def cn2int(s):
    if s.isdigit():
        return int(s)
    return CN_NUM.get(s, None)


def check_dialogue(vdir, rep):
    hits = []
    for root, dirs, files in os.walk(vdir):
        dirs[:] = [d for d in dirs if not d.startswith("_") and d not in ("生成", "输入")]
        for fn in files:
            if not fn.endswith(".md"):
                continue
            p = os.path.join(root, fn)
            txt = read(p)
            # 表头含「原片」的表格描述的是对标片，不是我们这条片子，跳过
            skip = set()
            for hdr, rows in split_tables(txt):
                if any("原片" in c for c in hdr):
                    for ln, _ in rows:
                        skip.add(ln)
            for ln, line in enumerate(txt.split("\n"), 1):
                if ln in skip:
                    continue
                found = None
                m = P_DLG.search(line) or P_ONLY.search(line)
                if m:
                    found = cn2int(m.group(1))
                if found is None and not any(w in line for w in (
                        "动作", "≤", "不超过",
                        "一句话差异", "一句话概括", "一句话总结",
                        "骨架一句话", "情绪弧一句话", "一句话说")):
                    m = P_SENT.search(line)
                    if m and not line.lstrip().startswith("#") \
                            and line[max(0, m.start() - 1):m.start()] != "第":
                        found = cn2int(m.group(1))
                if found is not None:
                    hits.append((os.path.relpath(p, vdir), ln, found, line.strip()[:52]))
    vals = sorted(set(h[2] for h in hits))
    if len(vals) > 1:
        detail = "；".join("%s:%d 写「%d 句」" % (h[0], h[1], h[2]) for h in hits[:8])
        rep.add("FAIL", "C4", "对白条数有 %d 个值 %s → %s" % (len(vals), vals, detail))
    elif hits:
        rep.add("PASS", "C4", "对白条数全文只有 %d 这一个值" % vals[0])
    else:
        rep.add("WARN", "C4", "全文没找到对白条数表述，无法判断")


def check_final_state(vdir, rep):
    p = os.path.join(vdir, "00_版本设定书.md")
    if not os.path.isfile(p):
        return
    txt = read(p)
    blocks = re.findall(r"```(?:text)?\s*\n(.*?)```", txt, re.S)
    for b in blocks:
        lines = [l.strip() for l in b.split("\n") if l.strip()]
        fin = [l for l in lines if l.startswith("末态.")]
        if not fin:
            continue
        noeq = [l for l in fin if "=" not in l]
        if len(fin) != 10:
            rep.add("FAIL", "C5", "末态十项实有 %d 行（必须恰好 10 行）" % len(fin))
        elif noeq:
            rep.add("FAIL", "C5", "末态有 %d 行不是「键 = 值」：%s"
                    % (len(noeq), noeq[0][:40]))
        else:
            rep.add("PASS", "C5", "末态十项齐全，且都是「键 = 值」")
        return
    rep.add("WARN", "C5", "没找到末态十项的代码块")


# ─────────────────────────── 指令层：C6 / C7 ───────────────────────────

SKIP_WORDS = ("不必读", "可以不读", "不用读", "不是本段输入", "不作本段输入", "略过")
MUST_WORDS = ("必读", "必须全读", "必须先读", "必须读", "必全读")
NAME_RE = re.compile(r"([0-9A-Za-z_\u4e00-\u9fa5]+\.md)")
OLD_NAMES = {"01_中间过程稿.md": "01_微调大纲.md"}
EXCUSE = ("作废", "旧名", "改名", "已改", "原名", "曾叫", "旧称")


def check_directives(spec, rep):
    d = None
    for name in ("指令模板_v3", "指令"):
        p = os.path.join(spec, name)
        if os.path.isdir(p):
            d = p
            break
    if not d:
        rep.add("WARN", "C0", "%s 下找不到 指令模板_v3 或 指令" % spec)
        return

    n_files = 0
    for fn in sorted(os.listdir(d)):
        if not fn.endswith((".txt", ".md")):
            continue
        n_files += 1
        p = os.path.join(d, fn)
        marks = {}
        old_hits = []
        for ln, line in enumerate(read(p).split("\n"), 1):
            up = any(w in line for w in MUST_WORDS)
            sk = any(w in line for w in SKIP_WORDS)
            if up or sk:
                for nm in NAME_RE.findall(line):
                    m = marks.setdefault(nm, {"up": [], "sk": []})
                    if up and not sk:
                        m["up"].append(ln)
                    elif sk and not up:
                        m["sk"].append(ln)
            for old, new in OLD_NAMES.items():
                if old in line and not any(e in line for e in EXCUSE):
                    old_hits.append((ln, old, new, line.strip()[:50]))
        for nm, v in marks.items():
            if v["up"] and v["sk"]:
                rep.add("FAIL", "C6",
                        "%s：%s 既标必读（第 %s 行）又标不必读（第 %s 行）"
                        % (fn, nm, v["up"][:3], v["sk"][:3]))
        for ln, old, new, snip in old_hits:
            rep.add("FAIL", "C7",
                    "%s:%d 还写着旧名 %s（现名 %s）→ %s"
                    % (fn, ln, old, new, snip))
    if not rep.fails():
        rep.add("PASS", "C6", "%d 份指令里，同一产物没有被同时标成必读与不读" % n_files)
        rep.add("PASS", "C7", "%d 份指令里没有旧文件名残留" % n_files)


# ─────────────────────────── 主流程 ───────────────────────────

def check_version(vdir):
    rep = Report("自洽检查｜%s" % os.path.basename(vdir.rstrip("\\/")))
    sb = parse_settingbook(vdir)
    check_settingbook(vdir, rep)
    check_opening(vdir, rep, sb)
    check_dialogue(vdir, rep)
    check_final_state(vdir, rep)
    return rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--v", help="单个 V 目录")
    ap.add_argument("--root", help="批次目录（检查其下所有 V* 目录）")
    ap.add_argument("--spec", help="规范目录（只查指令层 C6／C7）")
    a = ap.parse_args()

    targets = []
    if a.v:
        targets.append(a.v)
    if a.root:
        for fn in sorted(os.listdir(a.root)):
            p = os.path.join(a.root, fn)
            if os.path.isdir(p) and fn.startswith("V"):
                targets.append(p)

    if not targets and not a.spec:
        ap.print_help()
        return 2

    missing = [t for t in targets if not os.path.isdir(t)]
    if missing:
        print("找不到目录：" + "、".join(missing))
        print("提示：--v 要指到「版本目录」（里面直接有 00_版本设定书.md），不是项目根目录。")
        return 2

    total_fail = 0
    for t in targets:
        total_fail += check_version(t).dump()
        print()

    if a.spec:
        rep = Report("指令层自洽检查｜%s" % os.path.basename(a.spec.rstrip("\\/")))
        check_directives(a.spec, rep)
        total_fail += rep.dump()

    return 1 if total_fail else 0


if __name__ == "__main__":
    sys.exit(main())
