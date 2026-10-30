#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
检查_提示词.py —— 生成前扫一遍提示词，拦住"人记不住"的四类错

为什么要有这个脚本（2026-10-29）：
    整数秒这条规则在四个文件里各写了一遍（SKILL.md L22、3_开头 L540、
    5_生产单元 L901、00_从这里开始 L267），当天写的提示词照样写成 10.6 秒。
    同一天还有三次同类失手：凭空加刀、1.2 秒一刀、"画面停住"。
    结论：靠人记规则必然反复出错，必须机器扫。

用法：
    python 检查_提示词.py 提示词.txt
    python 检查_提示词.py 提示词.txt --shots 7 --seconds 11

退出码：
    0 = 全过    1 = 有 FAIL（不许提交）
"""
import io
import re
import sys
import argparse

# ── 禁写词：动作收尾的确认手势（4_小分镜【到位即松手】）
BANNED_GESTURE = [
    "拍两下", "压两下", "敲两下", "拍一下", "压一下", "摸一下", "抹一下",
    "抹平", "推平", "推开", "踩实", "压实", "压紧", "拍进", "敲实",
]
# ── 禁写词：准备 / 收拾动作（每刀职责四类，禁"准备"）
BANNED_PREP = [
    "走过来", "走过去", "走近", "蹲下去", "蹲下", "直起腰", "直起身",
    "站起来", "起身", "伸手去拿", "拿起锹", "拿起工具", "收拾", "插好",
    "放好", "整理衣服", "环顾", "看一眼成果", "退半步",
]
# ── 允许的例外（写成这些不算违规）
ALLOW = [
    "已经", "已在", "起手状态", "手已经", "已经握住", "已经踩",
]

SHOT_RE = re.compile(r"【镜头\s*(\d+)\s*[｜|]\s*([\d.]+)\s*秒\s*[｜|]\s*([^｜|]+)")
TOTAL_RE = re.compile(r"(?:生成\s*[：:]\s*)?([\d.]+)\s*秒\s*[。.]?\s*(?:9\s*[:：]\s*16|$)", re.M)
ACTION_LINE_RE = re.compile(r"(那一个动作|终点状态|起手状态)[：:]\s*(.+)")

# 景别归一：把各种写法收敛到一档
SHOT_SIZE_RULES = [
    ("特写", ["特写"]),
    ("近景", ["近景"]),
    ("中景", ["中景"]),
    ("全景", ["全景", "远景", "大全景", "广角"]),
]


def load(path):
    with io.open(path, encoding="utf-8") as f:
        return f.read()


def norm_size(raw):
    raw = raw.strip()
    for name, keys in SHOT_SIZE_RULES:
        for k in keys:
            if k in raw:
                return name
    return raw


def check_shot_size_alternate(text):
    """⑥ 相邻两刀景别不许相同（2026-10-29 新增，这是最贵的一条）

    实测依据（59 号）：11 秒 7 刀的测试里，镜头 2 和镜头 3 都写成「中景」，
    结果那两刀被模型连成一条 4.2 秒的连续镜头，7 刀只切出 4 个切点。
    同景别的"切"观众看不见，模型就当成长镜头演下去 —— 刀数写了也没用。
    """
    shots = SHOT_RE.findall(text)
    if len(shots) < 2:
        return True, "镜头不足 2 个，跳过"
    sizes = [(int(i), norm_size(s)) for i, _, s in shots]
    bad = []
    seq = []
    for k in range(len(sizes)):
        seq.append("%s%s" % (sizes[k][1], "" if k == 0 else
                             ("＝" if sizes[k][1] == sizes[k - 1][1] else "→")))
        if k > 0 and sizes[k][1] == sizes[k - 1][1]:
            bad.append("镜头 %d 和镜头 %d 都是「%s」——这一对切点会消失" %
                       (sizes[k - 1][0], sizes[k][0], sizes[k][1]))
    detail = "序列：" + "  ".join(seq)
    if bad:
        return False, bad + [detail]
    return True, detail


def check_int_seconds(text, expect_seconds):
    """① 生成秒必须是整数"""
    hits = []
    # 末尾那种「11 秒。9:16。」
    for m in re.finditer(r"([\d.]+)\s*秒\s*[。.]?\s*9\s*[:：]\s*16", text):
        hits.append(m.group(1))
    # 卡头部「生成：14 秒」
    for m in re.finditer(r"生成\s*[：:]\s*([\d.]+)\s*秒", text):
        hits.append(m.group(1))
    if expect_seconds is not None:
        hits.append(str(expect_seconds))

    bad = [h for h in hits if "." in h]
    if bad:
        return False, "生成秒出现小数：%s（网站只认整数 4–15）" % "、".join(sorted(set(bad)))
    if not hits:
        return False, "没找到生成秒（应在末尾写「N 秒。9:16。」或卡头「生成：N 秒」）"
    vals = sorted(set(hits))
    if len(vals) > 1:
        return False, "生成秒前后不一致：%s" % "、".join(vals)
    v = int(float(vals[0]))
    if not (4 <= v <= 15):
        return False, "生成秒 %d 超出平台容量 4–15" % v
    return True, "生成秒 %d 秒（整数，在 4–15 内）" % v


def check_shots_sum(text, total_seconds):
    """② 各镜秒数之和 == 生成秒"""
    shots = SHOT_RE.findall(text)
    if not shots:
        return False, "没解析到「【镜头 N｜X 秒…】」，无法核对时长分配"
    vals = [float(s[1]) for s in shots]
    s = round(sum(vals), 2)
    if total_seconds is None:
        return True, "%d 个镜头，合计 %.1f 秒（未给生成秒，跳过比对）" % (len(vals), s)
    diff = abs(s - total_seconds)
    if diff > 0.5:
        return False, "%d 个镜头合计 %.1f 秒，与生成秒 %d 差 %.1f 秒（应相等）" % (
            len(vals), s, total_seconds, diff)
    return True, "%d 个镜头合计 %.1f 秒，与生成秒 %d 相符" % (len(vals), s, total_seconds)


def check_words(text):
    """③ 禁写词（只看动作行，避开负面词区）"""
    # 先把负面词 / 不能出现 那两段切掉，否则"不许再拍一下"会被误报
    body_text = text
    for kw in ("【负面词】", "【不能出现的未来状态】"):
        if kw in body_text:
            body_text = body_text.split(kw)[0]
    problems = []
    for m in ACTION_LINE_RE.finditer(body_text):
        field, body = m.group(1), m.group(2)
        if field == "起手状态":
            allowed = True
        else:
            allowed = any(a in body for a in ALLOW)
        for w in BANNED_GESTURE:
            if w in body and not allowed:
                problems.append("确认手势「%s」出现在%s：%s" % (w, field, body[:40]))
        for w in BANNED_PREP:
            if w in body:
                problems.append("准备动作「%s」出现在%s：%s" % (w, field, body[:40]))
    # 「连做N下」「敲N下」用正则兜
    for m in re.finditer(r"(连做|敲|拍|压)\s*[一二三四五六七八九十两\d]+\s*下", body_text):
        seg = m.group(0)
        ctx = body_text[max(0, m.start() - 30):m.start()]
        if "不许" in ctx or "不要" in ctx or "禁止" in ctx:
            continue
        problems.append("次数型收尾「%s」" % seg)
    return (not problems), (problems if problems else "未命中禁写词")


def check_required_fields(text):
    """④ 每刀要有「下游」，从第二刀起要有「消费」

    判据（别设太死）：
      下游 ≥ 刀数 - 1   最后一刀是终点，可以不写"结果在哪一刀被看见"
      消费 ≥ 刀数 - 1   第一刀没有上一刀可消费
    """
    n_shots = len(SHOT_RE.findall(text))
    n_down = len(re.findall(r"下游[：:]", text))
    n_cons = len(re.findall(r"消费[：:]", text))
    need = max(0, n_shots - 1)
    msgs, ok = [], True
    if n_down < need:
        ok = False
        msgs.append("「下游」只有 %d 处，%d 刀至少要 %d 处（最后一刀可不写）" % (n_down, n_shots, need))
    else:
        msgs.append("「下游」%d 处，需 %d 处 ✓" % (n_down, need))
    if n_cons < need:
        ok = False
        msgs.append("「消费」只有 %d 处，%d 刀至少要 %d 处（第一刀没有可消费的）" % (n_cons, n_shots, need))
    else:
        msgs.append("「消费」%d 处，需 %d 处 ✓" % (n_cons, need))
    return ok, msgs


def check_shot_length_floor(text, total_seconds):
    """⑤ 每刀不低于 1.2 秒（动作切片下限）"""
    shots = SHOT_RE.findall(text)
    short = [(s[0], s[1]) for s in shots if float(s[1]) < 1.2]
    if short:
        return False, "这些刀低于 1.2 秒下限：%s" % "、".join(
            "镜头%s=%.1f" % (i, float(v)) for i, v in short)
    if shots:
        avg = sum(float(s[1]) for s in shots) / len(shots)
        return True, "每刀 %s–%s 秒，平均 %.2f 秒" % (
            min(float(s[1]) for s in shots), max(float(s[1]) for s in shots), avg)
    return True, "无镜头可查"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--seconds", type=int, default=None, help="预期生成秒（整数）")
    ap.add_argument("--shots", type=int, default=None, help="预期刀数")
    a = ap.parse_args()

    text = load(a.path)
    total = a.seconds
    if total is None:
        m = re.search(r"生成\s*[：:]\s*(\d+)\s*秒", text)
        if m:
            total = int(m.group(1))
        else:
            m = re.search(r"(\d+)\s*秒\s*[。.]?\s*9\s*[:：]\s*16", text)
            if m:
                total = int(m.group(1))

    results = []
    results.append(("① 生成秒是整数",) + check_int_seconds(text, a.seconds))
    results.append(("② 镜头秒数合计 = 生成秒",) + check_shots_sum(text, total))
    results.append(("③ 每刀 ≥1.2 秒",) + check_shot_length_floor(text, total))
    ok3, msg3 = check_words(text)
    results.append(("④ 无确认手势 / 无准备动作", ok3, msg3))
    ok4, msg4 = check_required_fields(text)
    results.append(("⑤ 下游 / 消费 齐全", ok4, "\n      ".join(msg4)))
    ok6, msg6 = check_shot_size_alternate(text)
    results.append(("⑥ 相邻两刀景别不同（切点才存在）", ok6, msg6))

    print("=" * 60)
    print("提示词检查：%s" % a.path)
    print("=" * 60)
    fail = 0
    for name, ok, detail in results:
        print("[%s] %s" % ("PASS" if ok else "FAIL", name))
        if isinstance(detail, list):
            for d in detail[:12]:
                print("      · %s" % d)
        else:
            print("      %s" % detail)
        if not ok:
            fail += 1
    print("-" * 60)
    if fail:
        print("结论：%d 项不过，不许提交。" % fail)
        sys.exit(1)
    print("结论：全部通过。")


if __name__ == "__main__":
    main()
