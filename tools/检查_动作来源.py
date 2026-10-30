#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查_动作来源.py —— 动作来源闸门

【为什么要有它】
    2026-10-27：U04＋U05 两条成片 23 秒里，有 5.9 秒（26%）是"人物白走、直起腰、擦汗、戳耙子"。
    查下来这些动作**小分镜里一处都没有**，全是写卡时为了"这一刀别太静"临时加的。
    光在模板里写"不许自加动作"拦不住——要靠人记着，就等于没有。
    所以做成脚本：每一刀、每一个过渡动作，都去小分镜里逐字找一遍，找不到就报。

【查三类】

    一、结构
        13–15 秒一组、6–7 刀（每刀约 2 秒）、相邻刀景别不同、每处切点单独一行「硬切至镜头N」、
        提示词 ≤4096 字符（按 UTF-16 + CRLF 保守算）、只有一个 ```text 块

    二、过渡动作来源
        从卡片每刀的「动作」块里抽出所有动作条（①②③），
        凡是**过渡类动词**（走／站／转／直起腰／擦／退／停手／看／并步／戳／拍…）都单独提出来：
          · 小分镜该刀写了没有？没写 = 「自加」，必须删或改
          · 写了，有没有限秒数（"两声后停住"／"0.5 秒"／"原地"）？没限 = 「会漂」，必须限秒

    三、对照物
        分镜该刀正文里出现的对照物关键词（钢索／白菊…），卡片正文必须提到至少一次。
        2026-10-27 实测：U04 禁止项写「不要出现绳索栏杆」，把开头那根旧钢索一起杀掉了，
        而分镜明写「钢索不得在这一刀消失（它是开头的证据）」。

【用法】
    python 检查_动作来源.py <单元卡.md> --board <后段小分镜_有效.md>

    # 例
    python 检查_动作来源.py "...\\单元\\U04_v02.md" ^
        --board "...\\分镜\\后段小分镜_有效.md"

    # 一次查整个单元目录
    python 检查_动作来源.py "...\\单元" --board "...\\分镜\\后段小分镜_有效.md"

【退出码】
    0 = 通过
    1 = 不通过（有自加动作 / 结构不合格 / 对照物缺失）
    2 = 文件读不懂（不是通过）
"""

import argparse
import re
import sys
from pathlib import Path

# ══════════════════ 词表 ══════════════════

# 过渡类动词：这类动词本身不产生物件状态变化，是最容易被"为了别太静"塞进来的
TRANSITION_WORDS = [
    "直起腰", "弯腰站", "站起来", "站起", "站起身",
    "擦汗", "擦一下", "擦额头", "拍手上的灰", "拍拍手", "抖手",
    "后退", "退半步", "上前", "往前挪", "并步", "并一下步",
    "走过来", "走过去", "走向", "走到", "走开", "走两步", "跑过去",
    "停手", "停住", "停下", "住手",
    "看一眼", "抬头看", "回头", "环视", "打量", "望",
    "戳", "杵", "拄",
    "叹气", "呼气", "松口气", "耸肩", "点点头", "摇头",
    "转身", "转过来", "背对镜头",
]

# 限秒数／限位移的标志词：出现这些，说明作者已经管住了这段过渡
LIMIT_MARKERS = [
    "只许", "只演", "不许走", "原地", "两声", "两步", "半步",
    "0.3 秒", "0.4 秒", "0.5 秒", "约 0 秒",
    "不许先走", "不许往前走", "不许走出画面",
]

# 对照物关键词（同义不同字，按组算）
PROP_GROUPS = [
    {"钢索", "钢缆", "钢丝绳", "缆"},
    {"警戒带", "警戒线", "封带"},
    {"白菊", "菊花", "盆花"},
    {"旧板", "旧木板"},
]

# 同义归并：卡片用的词 → 分镜里可能用的等价说法
# 纯字面比对会把「停手」和分镜的「停住」判成两回事，误报。这里只归并明确等价的。
ALIAS = {
    "停手": ["停手", "停住", "停下", "停"],
    "直起腰": ["直起腰", "起身", "直起身"],
    "站起来": ["站起来", "站起", "起身"],
    "转身": ["转身", "转过来", "背对", "转过"],
    "并步": ["并步", "并一下步", "脚步", "两步", "停住"],
    "走过来": ["走过来", "走上", "走进"],
    "走过去": ["走过去", "走向", "走向镜头"],
    "跑过去": ["跑过去", "跑向", "冲过去", "跑下", "跑过"],
    "走到": ["走到", "走到"],
    "走向": ["走向", "走向"],
    "后退": ["后退", "退半", "倒退"],
    "看一眼": ["看一眼", "看", "扫一眼"],
    "环视": ["环视", "四周"],
    "擦汗": ["擦汗", "擦一下", "抹"],
    "呼气": ["呼气", "吐气"],
    "点点头": ["点头"],
    "戳": ["戳", "杵", "拄"],
    "停住": ["停住", "停", "停手", "停下"],
    "停下": ["停下", "停", "停手"],
}

# 景别
SHOT_SIZES = ["大特写", "特写", "近景", "中景", "全景", "远景"]

# ══════════════════ 解析 ══════════════════


def read(p):
    return Path(p).read_text(encoding="utf-8", errors="replace")


def get_prompt(card_text):
    """取视频正文那一块 ```text。返回 (正文, 含镜头的块数)

    2026-10-28 修：开头 U01 按 `3_开头.txt` 第七节第 5 项要求「图提示词」和「视频提示词」
    分开写两块，所以一张卡里有两个 ```text 是合法的。原来按「块数 > 1 就报错」，
    等于 U01 永远过不了这道闸。现在只数「含镜头的块」，那才是视频正文。
    """
    blocks = re.findall(r"```text\r?\n(.*?)```", card_text, re.S)
    if not blocks:
        return None, 0
    video = [b for b in blocks if "镜头" in b]
    if video:
        return video[0], len(video)
    return blocks[0], len(blocks)


def parse_card_shots(prompt):
    """把提示词拆成 [{no, sec, size, jw, body}]

    要同时认三种实际出现过的写法（2026-10-28 补）：
      【镜头1】（2.0秒）广角，固定机位，机位高 1.6 米…
      【镜头 1｜0–2.6 秒】广角，固定机位，机位高 1.6 米…
      【镜头 1｜2.0 秒｜全景｜机位高 1.6 米｜俯视约 12 度｜广角】
    原来只认第一种，后两种会被解析成 0 刀 —— 闸门静默跳过，等于没查。
    """
    shots = []
    pat = re.compile(r"【\s*镜头\s*(\d+)\s*([^【】\n]*)】")
    marks = list(pat.finditer(prompt))
    for i, m in enumerate(marks):
        start = m.end()
        end = marks[i + 1].start() if i + 1 < len(marks) else len(prompt)
        body = prompt[start:end]
        head = (m.group(2) or "").strip()

        # 景别：先看镜头头，再看这一刀正文的前 120 字
        size = next((s for s in SHOT_SIZES if s in head), None)
        if size is None:
            size = next((s for s in SHOT_SIZES if s in body[:120]), "?")

        # 时长：头里给「A–B 秒」取差；给「X 秒」直接用
        sec = 0.0
        mr = re.search(r"(\d+(?:\.\d+)?)\s*秒?\s*[–\-~—]\s*(\d+(?:\.\d+)?)\s*秒", head)
        if mr:
            sec = float(mr.group(2)) - float(mr.group(1))
        else:
            ms = re.search(r"(\d+(?:\.\d+)?)\s*秒", head)
            if ms:
                sec = float(ms.group(1))
            else:
                ms = re.search(r"（\s*(\d+(?:\.\d+)?)\s*秒\s*）", body[:40])
                if ms:
                    sec = float(ms.group(1))

        # 机位：优先「机位：」那一行；头里写了高度/俯仰/焦段的也算写了
        jw = ""
        mj = re.search(r"机位[:：]\s*(.+)", body)
        if mj:
            jw = mj.group(1).strip()
        elif any(k in head for k in ("机位", "高度", "米", "俯视", "平视", "仰视", "广角", "焦")):
            jw = head

        shots.append(
            dict(no=int(m.group(1)), sec=round(sec, 2),
                 size=size, jw=jw, body=body)
        )
    return shots


def parse_actions(body):
    """抽「动作：」块里的 ①②③ 条，返回 [(标号, 文本)]"""
    m = re.search(r"动作[:：]\s*\n(.*?)(?=\n⚠️|\n【|$)", body, re.S)
    if not m:
        return []
    out = []
    for line in m.group(1).split("\n"):
        line = line.strip()
        mm = re.match(r"([①②③④⑤⑥])\s*(.+)", line)
        if mm:
            out.append((mm.group(1), mm.group(2).strip()))
    return out


def parse_card_mapping(card_text):
    """从「为什么这么切」表里读 镜头→分镜段 的映射：| 镜头1 | N09 前段 | ... |"""
    mp = {}
    for m in re.finditer(r"\|\s*镜头\s*(\d+)\s*\|\s*(N\d+)([^|]*)\|", card_text):
        mp[int(m.group(1))] = (m.group(2), m.group(3).strip())
    return mp


def parse_board(board_text):
    """拆小分镜：{N09: '全文'}"""
    secs = {}
    pat = re.compile(r"^###\s*(N\d+)[｜|](.*)$", re.M)
    marks = list(pat.finditer(board_text))
    for i, m in enumerate(marks):
        start = m.end()
        end = marks[i + 1].start() if i + 1 < len(marks) else len(board_text)
        secs[m.group(1)] = board_text[start:end]
    return secs


# ══════════════════ 检查 ══════════════════


def check_structure(prompt, shots, blocks):
    errs, warns = [], []
    if blocks > 1:
        errs.append(f"有 {blocks} 个 ```text 块，单元卡只许一个")
    if not shots:
        return errs, warns
    # 生产档位 13–15 秒（一组装满；平台容量 4–15，末组除不尽可短）
    # 2026-10-27 晚改自「4–10 秒 / 2–4 刀」——旧口径来自单镜头盒的丢件样本，已撤销
    # 刀数不设死上限，改成卡「平均每刀秒数」：实测 ≤2.6 秒 5/5 有用，≥2.8 秒 1/4 有用
    total = sum(x["sec"] for x in shots)
    if total > 15:
        errs.append(f"生成 {total:.0f} 秒，超平台单段上限 15 秒（拆成两盒）")
    if total and total < 4:
        errs.append(f"生成 {total:.0f} 秒，低于 4 秒下限")
    if total and shots:
        avg = total / len(shots)
        if avg > 3.0:
            errs.append(f"{len(shots)} 刀装进 {total:.0f} 秒，平均每刀 {avg:.1f} 秒"
                        f"（应约 2 秒／刀；超过 3 秒必然出现傻站或走位，刀数应是 {round(total/2)} 刀左右）")
        if avg < 1.5:
            errs.append(f"{len(shots)} 刀装进 {total:.0f} 秒，平均每刀不到 1.5 秒，刀碎得没法看")
    for s in shots:
        # 刀没有最小时长（阿初 15 秒组 = 2/2/2/3/5/1，含 1 秒刀）
        if s["sec"] <= 0:
            errs.append(f"镜头{s['no']} 没写秒数")
        if not s["jw"]:
            errs.append(f"镜头{s['no']} 没有机位行")
        if s["size"] == "?":
            errs.append(f"镜头{s['no']} 没写景别")
    for a, b in zip(shots, shots[1:]):
        if a["size"] != "?" and a["size"] == b["size"]:
            errs.append(
                f"镜头{a['no']}与镜头{b['no']}都是{a['size']}，相邻刀景别必须不同")
    n_cut = prompt.count("硬切至镜头")
    if n_cut < len(shots) - 1:
        errs.append(f"{len(shots)} 刀应有 {len(shots)-1} 处切点，实有 {n_cut}")
    size = len(prompt) + prompt.count("\n")  # UTF-16 + CRLF 保守值
    if size > 4096:
        errs.append(f"提示词 {size} 字符，超 4096（按 UTF-16+CRLF 算）")
    elif size > 3800:
        warns.append(f"提示词 {size} 字符，接近 4096 上限")
    return errs, warns


def is_main_action(ref, word):
    """这个词是不是分镜「那一个动作」本身。是 → 它就是这一刀的主体，不是过渡，不用报"""
    m = re.search(r"那一个动作[:：](.+)", ref)
    if not m:
        return False
    line = m.group(1)
    return any(c in line for c in ALIAS.get(word, [word]))


def find_ref_sentence(ref, word):
    """在分镜正文里找这个词（连同义说法）的出处，返回原句；找不到返回 None"""
    cands = ALIAS.get(word, [word])
    for c in cands:
        i = ref.find(c)
        if i >= 0:
            s = max(0, i - 45)
            e = min(len(ref), i + 65)
            return ref[s:e].replace("\n", " ").strip()
    return None


def check_actions(shots, mapping, board):
    """逐刀核每个动作条的来源。返回 (找不到出处的, 找到了但没限秒的, 已核对数)"""
    missing, unlimited, checked = [], [], 0
    for s in shots:
        acts = parse_actions(s["body"])
        n, sub = mapping.get(s["no"], (None, ""))
        ref = board.get(n, "") if n else ""
        ref_label = f"{n}{sub}" if n else "（卡片没写这刀对应哪个N）"
        for tag, txt in acts:
            hits = [w for w in TRANSITION_WORDS if w in txt]
            if not hits:
                continue
            for w in hits:
                checked += 1
                if not n:
                    missing.append((s["no"], tag, w, txt, ref_label, None))
                    continue
                if is_main_action(ref, w):
                    continue  # 主体动作，不是过渡，跳过
                sent = find_ref_sentence(ref, w)
                if sent is None:
                    missing.append((s["no"], tag, w, txt, ref_label, None))
                else:
                    # 限秒约束常写在这一刀的 ⚠️ 行里，所以查整刀正文，不只查这一条动作
                    limited = any(k in s["body"] for k in LIMIT_MARKERS)
                    if not limited:
                        unlimited.append((s["no"], tag, w, txt, ref_label, sent))
    return missing, unlimited, checked


def check_props(prompt, shots, mapping, board):
    """分镜该刀写了对照物，卡片正文必须提到同组任意一个词"""
    missing = []
    for s in shots:
        n, sub = mapping.get(s["no"], (None, ""))
        if not n:
            continue
        ref = board.get(n, "")
        for grp in PROP_GROUPS:
            if any(w in ref for w in grp):
                if not any(w in prompt for w in grp):
                    missing.append((s["no"], "/".join(sorted(grp)[:2]), n))
    seen, out = set(), []
    for x in missing:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def run_one(card_path, board):
    text = read(card_path)
    prompt, blocks = get_prompt(text)
    name = Path(card_path).name
    if prompt is None:
        return name, ["读不到 ```text 块"], [], [], ([], [], 0, [])

    shots = parse_card_shots(prompt)
    mapping = parse_card_mapping(text)

    if not shots:
        # 旧格式卡：没有【镜头N】块，不是"不通过"，是本脚本管不了
        return name, [], ["旧格式（没有【镜头N】块），本脚本跳过"], "OLD"

    errs, warns = check_structure(prompt, shots, blocks)
    if not mapping:
        warns.append("卡片里没有「为什么这么切」映射表，动作来源无法逐刀核对")
    missing, unlimited, checked = check_actions(shots, mapping, board)
    props = check_props(prompt, shots, mapping, board)

    if missing:
        errs.append(f"{len(missing)} 处过渡动作在小分镜里找不到出处")
    if props:
        errs.append(f"{len(props)} 处对照物在卡片里丢了")
    if unlimited:
        warns.append(f"{len(unlimited)} 处过渡动作在分镜里有、但没限秒数")

    return name, errs, warns, (missing, unlimited, checked, props)


def main():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("target", nargs="?", help="单元卡 .md 或 单元目录")
    ap.add_argument("--board", help="分镜\\后段小分镜_有效.md")
    ap.add_argument("-h", "--help", action="help")
    a = ap.parse_args()

    if not a.target:
        print(__doc__)
        return 2

    tgt = Path(a.target)
    cards = sorted(tgt.glob("U*.md")) if tgt.is_dir() else [tgt]
    cards = [c for c in cards if not c.name.startswith("_")]
    if not cards:
        print(f"没找到单元卡：{tgt}")
        return 2

    board = parse_board(read(a.board)) if a.board else {}
    if a.board and not board:
        print(f"分鉴别不出来：{a.board}")
        return 2

    bad = 0
    skipped = 0
    for c in cards:
        name, errs, warns, detail = run_one(c, board)
        if detail == "OLD":
            skipped += 1
            continue
        missing, unlimited, checked, props = detail if detail else ([], [], 0, [])
        print("=" * 68)
        print(name)
        if checked:
            print(f"  过渡动作逐条核过 {checked} 处")
        if missing:
            print("  ✗ 找不到出处的过渡动作——最可能是自己加的，删掉或退回分镜改：")
            for no, tag, w, txt, ref, _s in missing:
                print(f"    镜头{no} {tag}「{w}」  ← 对应 {ref}（分镜里没有这个动作）")
                print(f"      卡片写的是：{txt[:62]}")
        if props:
            print("  ✗ 对照物在卡片里丢了：")
            for no, w, n in props:
                print(f"    镜头{no}：{n} 里有「{w}」，卡片正文一次都没提到")
        if unlimited:
            print("  ⚠ 分镜里有出处、但没限秒数（模型会漂成整段）——照着下面这句把它框住：")
            for no, tag, w, txt, ref, sent in unlimited:
                print(f"    镜头{no} {tag}「{w}」  ← {ref}")
                print(f"      分镜原句：…{sent}…")
                print(f"      加一句「只许原地……约 0.4 秒」")
        for w in warns:
            print(f"  ⚠ {w}")
        for e in errs:
            print(f"  ✗ {e}")
        if not errs:
            print("  ✓ 通过" + ("（有提醒）" if warns else ""))
        if errs:
            bad += 1

    print("=" * 68)
    msg = f"{len(cards) - skipped} 张卡（旧格式跳过 {skipped} 张），{bad} 张不通过。"
    print(msg)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
