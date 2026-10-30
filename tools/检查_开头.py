#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查_开头.py —— 第③段（开头）交付闸门

这一段的病根是「开头抢了中间段的活」，所以这里把三条判据做成硬检查。

七项
----
1. 开头方案、开头交接、单元/U01.md 三份都在
2. 开头段**工具数 = 0**（水枪/刷子/电钻/梯子/漆桶…一个都不许出现）
3. 开头段**工序数 = 0**（捡叶装袋除外，它是原片第 0 帧就有的接触）
4. 首帧六要素齐（含「观众第一反应」且是三选一）
5. 开头交接里有 T 值、T 秒末态键值、不可改动作
6. 开头时长 = 设定书的 T（差 ≤0.05 秒）
7. 工序名全部取自 19_工序词表.md

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

TOOLS = ['高压水枪', '水枪', '硬毛刷', '刷子', '抹布', '电钻', '起子', '螺丝刀',
         '梯子', '人字梯', '铝梯', '漆桶', '割灌机', '打草机', '独轮车',
         '铲子', '铁锹', '耙子', '滚筒', '卷尺']
REACTIONS = ['必须马上处理', '可以忍但不好看', '看着舒服']
EXEMPT = ['捡叶装袋', '捡叶', '拾叶', '清叶']          # 唯一允许出现在开头的动作
PROCESS = ['冲地', '刷墙', '铲除', '擦地', '擦桌面', '装搁板', '固定铝轨', '挂帘',
           '封侧边', '封底边', '砌路缘', '铺板', '铺草皮', '刷漆', '装灯', '装挂钩',
           '装排水', '摆茶几', '摆座椅', '挂吊蕨', '摆盆栽', '铺坐垫', '摆抱枕',
           '放水壶', '摆杯具', '摆软装', '收废料']


def read(p):
    for enc in ('utf-8', 'utf-8-sig', 'gbk'):
        try:
            return open(p, encoding=enc).read()
        except Exception:
            continue
    return ''


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

    # 2 工具数
    hits = sorted({t for t in TOOLS if t in body})
    rows.append(('开头段工具数', f'{len(hits)} 种', '= 0', not hits,
                 ('出现了：' + '、'.join(hits)) if hits else '—'))

    # 3 工序数（排除豁免）
    procs = sorted({p for p in PROCESS if p in body})
    rows.append(('开头段工序数', f'{len(procs)} 个', '= 0', not procs,
                 ('出现了：' + '、'.join(procs) + '（应退回中间段）') if procs else '—'))

    # 4 六要素
    six = {'受害物位置': '受害物', '威胁方向': '威胁方向', '距离': '距离',
           '人数': '人', '机位': '机位', '观众第一反应': '观众第一反应'}
    miss = [k for k, kw in six.items() if kw not in body]
    react = [r for r in REACTIONS if r in body]
    ok4 = (not miss) and (len(react) == 1)
    rows.append(('首帧六要素', f'{6-len(miss)}/6', '= 6', ok4,
                 ('缺：' + '、'.join(miss)) if miss else
                 ('观众反应：' + (react[0] if react else '没填'))))

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

    # 7 工序名在词表内（扫 U01 里出现的工序词）
    vocab = os.path.join(get_suite_root(), '19_工序词表.md')
    t_voc = read(vocab) if os.path.isfile(vocab) else ''
    if t_voc:
        used = [p for p in PROCESS if p in t_u01]
        bad = [p for p in used if p not in t_voc]
        rows.append(('U01 工序名取自词表', f'{len(used)-len(bad)}/{len(used)}', '全部',
                     not bad, ('不在词表：' + '、'.join(bad)) if bad else '—'))
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
            a, b = float(m.group(1)), float(m.group(2))
            durs.append(round(b - a, 2))
            ranges.append((a, b))
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
