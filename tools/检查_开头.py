#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查_开头.py —— 第③段（开头）交付闸门

这一段的病根是「开头抢了中间段的活」，所以这里把三条判据做成硬检查。

七项
----
1. 开头方案、开头交接、单元/U01.md 三份都在
2. 开头段**工具数 = 0**（工具名以 19_工序词表.md 的「工具词表」为准，脚本里不写死题材）
3. 开头段**工序数 = 0**（捡叶装袋除外，它是原片第 0 帧就有的接触）
4. 首帧六要素齐（含「观众第一反应」且是三选一）
5. 开头交接里有 T 值、T 秒末态键值、不可改动作
6. 开头时长 = 设定书的 T（差 ≤0.05 秒）
7. 工序名全部取自 19_工序词表.md（U01 里按「N03 冲地」写才能查）

两条判定口径（2026-10-31 修，都是为了让写的人敢写具体名词）
------------------------------------------------------------
· 「不许出现水枪」这种**禁令句**不算违规——只记在备注里，不做静默放过。
  以前不分禁令和实操，写的人只好把具体器械名全换成「施工器械与材料」这种泛称。
· 两字**别名**必须在词边界上才算（「脚踩上门前」不能算成工序「装门」）。
  一字别名不参与匹配，标准名已经能覆盖。

用法
----
  python 检查_开头.py --版本 "…/V01_la_casa_del_sueno"

退出码：0 全过 / 1 有不过 / 2 出错
"""

import argparse
import os
import re
import sys
from pipeline_runtime import get_suite_root

# 词表：不在脚本里写死（2026-10-31 修）
# ---------------------------------------------------------------
# 原来 TOOLS / PROCESS 是两张写死在代码里的表，只覆盖「清理 + 园艺」类片子。
# 换成集装箱改造（角磨机、圆锯、焊机）或别的题材，脚本认不出来，开头塞满工具也照样全绿。
# 现在两张表都从 19_工序词表.md 读；只有词表缺失时才退回下面这份兜底表。
TOOLS_FALLBACK = ['高压水枪', '水枪', '硬毛刷', '刷子', '抹布', '电钻', '起子', '螺丝刀',
                  '梯子', '人字梯', '铝梯', '漆桶', '割灌机', '打草机', '独轮车',
                  '铲子', '铁锹', '耙子', '滚筒', '卷尺']
PROCESS_FALLBACK = ['冲地', '刷墙', '铲除', '擦地', '擦桌面', '装搁板', '固定铝轨', '挂帘',
                    '封侧边', '封底边', '砌路缘', '铺板', '铺草皮', '刷漆', '装灯', '装挂钩',
                    '装排水', '摆茶几', '摆座椅', '挂吊蕨', '摆盆栽', '铺坐垫', '摆抱枕',
                    '放水壶', '摆杯具', '摆软装', '收废料']
REACTIONS = ['必须马上处理', '可以忍但不好看', '看着舒服']
# 唯一允许出现在开头的动作（19_工序词表.md §三.3 登记的唯一例外）
EXEMPT = ['捡叶装袋', '捡叶', '拾叶', '清叶']

# 「禁令句」标记：句子里出现这些词，说明这句是在**禁止**某个东西，不是在**做**它。
#   工具一律不许出现（如水枪、刷子）   → 只是提了一嘴禁令，不该算违规
#   0.8 秒：他举起水枪冲地面            → 真在用，算违规
# 不区分这两种，写的人就只敢写「施工器械与材料」这种泛称，信息被主动降级。
NEG_WORDS = ('不许', '不得', '禁止', '不允许', '禁用', '不出现', '不能出现',
             '不要出现', '不要用', '别用', '不写', '避免', '不涉及', '不包含', '一律不')
ZERO_RE = re.compile(r'[=＝]\s*0(?![.\d])')


def read(p):
    for enc in ('utf-8', 'utf-8-sig', 'gbk'):
        try:
            return open(p, encoding=enc).read()
        except Exception:
            continue
    return ''


def sentences(text):
    """按行 + 句号/分号/问叹号切句。禁不禁令，是按句子判的，不是按整篇判的。"""
    out = []
    for line in text.splitlines():
        for s in re.split(r'[。；;！？]', line):
            s = s.strip()
            if s:
                out.append(s)
    return out


def is_rule_sentence(s):
    """这句是在立规矩（禁止 / 计数为零），不是在描述动作。"""
    return bool(ZERO_RE.search(s)) or any(w in s for w in NEG_WORDS)


def hit_word(s, w, is_alias):
    """一个词是不是真出现在这句里。

    标准名照旧全文搜（「冲地」出现在「冲地面」里，那是真在冲）。
    别名要更严：别名本来就是给读旧文件用的，两个字太容易撞车——
    「脚踩**上门**前那条台阶」里的「上门」，不是工序「装门」的别名。
    所以两字别名必须落在词边界上；一字别名直接不认（「刮」「铲」撞车率太高，标准名已经能覆盖）。
    """
    if len(w) < 2:
        return False
    if not (is_alias and len(w) == 2):
        return w in s
    return re.search(r'(?<![\u4e00-\u9fa5A-Za-z0-9])' + re.escape(w)
                     + r'(?![\u4e00-\u9fa5A-Za-z0-9])', s) is not None


def scan(text, groups):
    """groups = [(标准名, [(词, 是否别名), ...])]，返回 (违规名, 被判为禁令语境而放过的名)。

    同一个词只要有一处是真在用，就算违规；只是被提到禁止的，记进 muted，不算违规，
    但会在备注里列出来，让人能复核——不做静默放过。
    """
    hits, muted = set(), set()
    for s in sentences(text):
        for name, ws in groups:
            if not any(hit_word(s, w, a) for w, a in ws):
                continue
            (muted if is_rule_sentence(s) else hits).add(name)
    return sorted(hits), sorted(muted - hits)


SEP_RE = re.compile(r'^[-:—\s]*$')
HEADER_WORDS = {'类别', '项', '工具', '工具名', '标准名', '说明', '值'}


def load_vocab(path):
    """从 19_工序词表.md 读两张表，换题材只改词表、不改脚本。

    · 工序：`标准名 | 允许别名 | 一句话定义` 三列，只认第一格带反引号的行
      （避开 §四 那张「对标叫 / 我们叫」对照表，它不是词表）
    · 工具：「工具词表」一节，`类别 | 工具A、工具B` 两列
    读不到就返回空，调用方退回兜底表。
    """
    text = read(path)
    if not text:
        return {}, []
    proc, tools, zone = {}, [], ''
    for line in text.splitlines():
        s = line.strip()
        if s.startswith('#'):
            zone = s
            continue
        if not s.startswith('|'):
            continue
        cells = [c.strip() for c in s.strip('|').split('|')]
        if len(cells) < 2:
            continue
        # 跳过表头行和 |---|---| 分隔行，否则「工具」「---」会被当成工具名
        if all(SEP_RE.match(c) for c in cells) or cells[0] in HEADER_WORDS:
            continue
        if '工具' in zone:
            for c in cells[1:]:
                tools.extend(x.strip() for x in re.split(r'[、,，/]', c)
                             if x.strip() and x.strip() != '—')
            continue
        if not cells[0].startswith('`'):
            continue
        name = cells[0].replace('`', '').replace('*', '').strip()
        if not name or set(name) <= set('-: '):
            continue
        alias = [x.strip() for x in re.split(r'[、,，/]', cells[1])
                 if x.strip() and x.strip() != '—']
        proc[name] = alias
    if len(proc) < 5:
        proc = {}
    return proc, sorted(set(tools))


# 「离场」「空镜」在词表里是为了统一命名，不是工序——
# 词表 §一 的反例写得很清楚：「走过去」是走位，不是工序。所以不计入开头工序数。
NOT_PROCESS = {'离场', '空镜'}


def proc_groups(proc_map):
    """把词表变成 [(标准名, [(词, 是否别名)])]，跳过允许出现在开头的那一条。"""
    if not proc_map:
        return [(p, [(p, False)]) for p in PROCESS_FALLBACK]
    out = []
    for std, alias in proc_map.items():
        if std in EXEMPT or std in NOT_PROCESS:
            continue
        ws = [(std, False)]
        for a in alias:
            if a not in EXEMPT and len(a) >= 2:
                ws.append((a, True))
        out.append((std, ws))
    return out


def label_rows(text):
    """表格行的 (第一格, 第二格)。按「行标签」找值，比全文搜关键词稳。"""
    rows = []
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith('|'):
            continue
        cells = [c.strip() for c in s.strip('|').split('|')]
        if len(cells) >= 2:
            rows.append((cells[0].replace('*', '').replace(' ', ''), cells[1]))
    return rows


def pick_reaction(text):
    """观众第一反应必须三选一。

    先看「第一反应」那一行；没有再看全文，但跳过「A／B／C 三选一」这种把三个选项
    原样抄一遍的句子——那是在抄规则，不是在填答案（旧版会因此误判成「填了 3 个」）。
    """
    for lab, val in label_rows(text):
        if '第一反应' in lab:
            if '／' in val or '三选一' in val:
                break          # 这一格是把三个选项抄了一遍，不是答案，往下走
            got = [r for r in REACTIONS if r in val]
            if got:
                return got
    got = []
    for s in sentences(text):
        if '／' in s or '三选一' in s or '三 选 一' in s:
            continue
        got.extend(r for r in REACTIONS if r in s)
    return sorted(set(got))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--版本', '--version-dir', dest='ver', required=True)
    a = ap.parse_args()

    if not os.path.isdir(a.ver):
        print('找不到目录：' + a.ver)
        return 2

    plan = os.path.join(a.ver, '开头', '开头方案_有效.md')
    hand = os.path.join(a.ver, '开头', '开头交接.md')
    u01 = os.path.join(a.ver, '单元', 'U01.md')
    spec = os.path.join(a.ver, '00_版本设定书.md')

    t_plan = read(plan) if os.path.exists(plan) else ''
    t_hand = read(hand) if os.path.exists(hand) else ''
    t_u01 = read(u01) if os.path.exists(u01) else ''
    t_spec = read(spec) if os.path.exists(spec) else ''

    if not (os.path.exists(spec) or os.path.exists(plan) or os.path.exists(hand)):
        print('这一版还没开始做开头：缺 00_版本设定书.md、开头\\开头方案_有效.md、开头\\开头交接.md')
        return 2

    rows = []

    # 1 三份产物
    got = [os.path.exists(x) for x in (plan, hand, u01)]
    rows.append(('三份产物齐全', f'{sum(got)}/3', '= 3', all(got),
                 '缺：' + '、'.join(os.path.basename(x) for x, g in zip((plan, hand, u01), got) if not g) or '—'))

    body = t_plan + '\n' + t_hand

    # 词表：工序和工具都从 19_工序词表.md 读，脚本里不留写死的题材词
    vocab = os.path.join(get_suite_root(), '19_工序词表.md')
    t_voc = read(vocab) if os.path.isfile(vocab) else ''
    proc_map, tool_words = load_vocab(vocab) if t_voc else ({}, [])
    if not tool_words:
        tool_words = TOOLS_FALLBACK
    groups = proc_groups(proc_map)

    # 2 工具数
    hits, muted = scan(body, [(t, [(t, False)]) for t in tool_words])
    note = ('出现了：' + '、'.join(hits)) if hits else '—'
    if muted:
        note = (note + '｜' if hits else '') + '仅在禁令语境提到（不算）：' + '、'.join(muted)
    rows.append(('开头段工具数', f'{len(hits)} 种', '= 0', not hits, note))

    # 3 工序数（排除豁免）
    procs, pmuted = scan(body, groups)
    note = ('出现了：' + '、'.join(procs) + '（应退回中间段）') if procs else '—'
    if pmuted:
        note = (note + '｜' if procs else '') + '仅在禁令语境提到（不算）：' + '、'.join(pmuted)
    rows.append(('开头段工序数', f'{len(procs)} 个', '= 0', not procs, note))

    # 4 六要素（按表格行标签找，退路：没有表格就按关键词找）
    six = {'受害物位置': ('受害物',), '威胁方向': ('威胁方向',), '距离': ('距离',),
           '人数': ('人数', '几个人'), '机位': ('机位',), '观众第一反应': ('第一反应',)}
    labels = [lab for lab, _ in label_rows(body)]
    if labels:
        miss = [k for k, alts in six.items()
                if not any(a in lab for a in alts for lab in labels)]
    else:
        miss = [k for k, alts in six.items() if not any(a in body for a in alts)]
    react = pick_reaction(body)
    ok4 = (not miss) and (len(react) == 1)
    rows.append(('首帧六要素', f'{6-len(miss)}/6', '= 6', ok4,
                 ('缺：' + '、'.join(miss)) if miss else
                 ('观众反应：' + (react[0] if len(react) == 1 else
                                f'填了 {len(react)} 个（' + '、'.join(react) + '），必须三选一'))))

    # 5 交接三样
    hand_ok = ('T =' in t_hand or 'T=' in t_hand) and ('末态' in t_hand) and ('不可改' in t_hand)
    rows.append(('交接含 T / 末态 / 不可改动作', '齐' if hand_ok else '不齐', '三样都要',
                 hand_ok, 'T 秒末态必须是键值表，不许写成散文'))

    # 6 时长与 T 对齐
    m = re.search(r'T\s*[=＝]\s*([\d.]+)', t_spec)
    t_val = float(m.group(1)) if m else None
    seg = re.search(r'(\d+\.\d+)\s*[–\-~]\s*(\d+\.\d+)', t_hand)
    len_ok = True
    detail = '—'
    if t_val and seg:
        head_end = float(seg.group(2))
        diff = abs(head_end - t_val)
        len_ok = diff <= 0.05
        detail = f'交接末秒 {head_end:.2f} vs 设定书 T {t_val:.2f}，差 {diff:+.2f}'
    else:
        detail = '从交接里没读到 T 或末秒'
        len_ok = False
    rows.append(('开头时长 = 设定书 T', '一致' if len_ok else '不一致', '差 ≤0.05 秒',
                 len_ok, detail))

    # 7 工序名在词表内（U01 里按「N03 冲地」的写法取名字，再查词表）
    # 旧版是「拿写死的工序表去 U01 里搜」，搜不到就 0/0 PASS —— 假绿灯。
    # 改成：取 U01 里真实写下的工序名，逐个查；取不到就明说查不了，不冒充通过。
    if t_voc:
        known = set()
        for std, alias in proc_map.items():
            known.add(std)
            known.update(alias)
        if not known:
            known = set(PROCESS_FALLBACK) | set(EXEMPT)
        named = re.findall(r'[NU]\d{2,3}\s+([\u4e00-\u9fa5]{2,8})', t_u01)
        bad = sorted({n for n in named if n not in known})
        if named:
            rows.append(('U01 工序名取自词表', f'{len(named)-len(bad)}/{len(named)}', '全部',
                         not bad, ('不在词表：' + '、'.join(bad)) if bad else '—'))
        else:
            rows.append(('U01 工序名取自词表', 'U01 没写工序名', '按「N03 冲地」写', None,
                         'U01 里没有「刀号 + 工序名」，这一项查不了（不是通过）'))
    else:
        rows.append(('U01 工序名取自词表', '词表不可用', '必须有词表', False,
                     '19_工序词表.md 缺失、为空或无法读取：' + vocab))

    # 8 U01 的刀结构与时间轴（2026-10-28 新增）
    # 前三项查的是「有没有干活」，查不出「刀怎么切」：
    #   0.5 秒的刀、时间轴只写到 5.0 而生成 6 秒、状态跳跃——前面七项全绿，毛病全漏。
    # 两种写法都认：
    #   【镜头 1｜0–2.6 秒】  （给起止，取差值）
    #   【镜头 1｜2.0 秒｜全景｜…】（只给时长）
    durs, ranges = [], []
    for blk in re.findall(r'【\s*镜头[^【】]*】', t_u01):
        m = re.search(r'(\d+(?:\.\d+)?)\s*秒?\s*[–\-~—]\s*(\d+(?:\.\d+)?)\s*秒', blk)
        if m:
            # 2026-10-31 修：这里原来写 a, b = float(...)，把上面的 argparse 对象 a 覆盖了，
            # 导致 L183 的 a.ver 必崩（TypeError: 'float' object has no attribute 'ver'）。
            t1, t2 = float(m.group(1)), float(m.group(2))
            durs.append(round(t2 - t1, 2))
            ranges.append((t1, t2))
        else:
            m = re.search(r'｜\s*(\d+(?:\.\d+)?)\s*秒', blk)
            if m:
                durs.append(round(float(m.group(1)), 2))
    mg = re.search(r'生成[：:]\s*(\d+(?:\.\d+)?)\s*秒', t_u01)
    gen = float(mg.group(1)) if mg else None
    if durs and gen:
        n = len(durs)
        want = gen / 2
        total = round(sum(durs), 2)
        cnt_ok = abs(n - want) <= 1.0
        min_ok = all(d >= 0.99 for d in durs)
        full_ok = abs(total - gen) <= 0.1
        rows.append(('U01 刀数 ≈ 生成秒÷2', f'{n} 刀 / 生成 {gen:g} 秒', f'≈ {want:.1f} 刀',
                     cnt_ok, '刀长：' + ' / '.join(f'{d:.2f}' for d in durs)))
        rows.append(('U01 单刀 ≥1 秒', f'最短 {min(durs):.2f} 秒', '≥ 1.0', min_ok,
                     '太短的刀演不完一个状态变化，模型只挑一个动作做' if not min_ok else '—'))
        rows.append(('U01 时间轴铺满生成秒', f'合计 {total:.2f} 秒', f'= {gen:g} 秒', full_ok,
                     f'差 {gen-total:+.2f} 秒，模型会自己编走位填上' if not full_ok else '—'))
        # 切点号连续：给了起止的，上一刀末端要等于下一刀起手
        if len(ranges) == n and n > 1:
            gap = [f'{ranges[i][0]:.2f}≠{ranges[i-1][1]:.2f}'
                   for i in range(1, n) if abs(ranges[i][0] - ranges[i-1][1]) > 0.02]
            rows.append(('U01 切点首尾相接', '连续' if not gap else f'{len(gap)} 处断口',
                         '上一刀止 = 下一刀起', not gap, '；'.join(gap) if gap else '—'))
    else:
        rows.append(('U01 刀结构', '未解析', '要有「镜头N｜X 秒」', None,
                     'U01 里没读到镜头时长或「生成：N 秒」'))

    # 打印
    W = 82
    print('=' * W)
    print('第③段 · 开头 交付闸门')
    print('  版本：' + a.ver)
    print('=' * W)
    print(f"{'项目':<26}{'实测':<14}{'要求':<20}判定")
    print('-' * W)
    fails = 0
    for name, actual, need, ok, note in rows:
        if ok is False:
            fails += 1
        flag = '跳过' if ok is None else ('PASS' if ok else 'FAIL')
        print(f'{name:<26}{actual:<14}{need:<20}{flag}')
        if note and note != '—':
            print(f'    · {note}')
    print('-' * W)
    print('结果：' + ('全过，可以进第④段' if fails == 0 else f'{fails} 项不过，退回改'))
    return 0 if fails == 0 else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        print('运行出错：', e)
        sys.exit(2)
