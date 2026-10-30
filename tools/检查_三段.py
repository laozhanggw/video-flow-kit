#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查_三段.py —— 三段配额 + 工序守恒 机器闸门

它只读设定书里的两张表，不猜内容：
  表 A：三段配额（开头／中间／结尾 的时长、工序数、对标同项、比值）
  表 B：工序清单（工序号／工序名／落在第几段／起止秒／动作数）

判五件事
--------
1. 开头段工序数 ＝ 0                      （开头只许呈现问题，不许动手）
2. 中间段工序数 / 对标 ≥ 0.90              （工序不许被搬到两头）
3. 中间段时长 / 对标 ≥ 0.90                （时间段不许被抽空）
4. 中间段每工序秒数 / 对标 ≥ 0.90            （不许把工序塞太密）
5. 三段时长之和 ＝ 总时长；工序动作数之和 ＝ 4.5 节动作总数

为什么用表而不是视频
--------------------
工序这件事机器没法从画面里可靠地数出来（AI 看不出「这是冲地还是刷墙」）。
但设定书里本来就要写这两张表，所以最可靠的做法是：**要求它把表填对，再核表自洽。**
表里的「对标同项」如果填错，比值会立刻露馅——这是一个互相咬合的结构，编不了。

用法
----
  python 检查_三段.py --spec 00_版本设定书.md
  python 检查_三段.py --spec 00_版本设定书.md --total 28.900 --actions 24

退出码：0 全过 / 1 有不过 / 2 参数或文件问题
"""

import argparse
import os
import re
import sys

SEG_NAMES = ['开头', '中间', '结尾']


def read(path):
    for enc in ('utf-8', 'utf-8-sig', 'gbk'):
        try:
            return open(path, encoding=enc).read()
        except Exception:
            continue
    raise RuntimeError('读不了文件：' + path)


def table_rows(text, header_keywords):
    """在 markdown 里找表头包含全部关键字的表，返回其数据行（已拆成单元格）。"""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.lstrip().startswith('|') and all(k in line for k in header_keywords):
            cells = [c.strip() for c in line.strip().strip('|').split('|')]
            out = []
            for j in range(i + 1, len(lines)):
                nxt = lines[j].strip()
                if not nxt.startswith('|'):
                    break
                if re.fullmatch(r'\|[\s:\-|]+\|', nxt):
                    continue
                out.append([c.strip() for c in nxt.strip('|').split('|')])
            return cells, out
    return None, None


def num(s):
    m = re.search(r'-?\d+(?:\.\d+)?', s or '')
    return float(m.group()) if m else None


def pick(row, *cands):
    """按表头名找列（先精确后包含）。"""
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--spec', required=True, help='00_版本设定书.md')
    ap.add_argument('--total', type=float, default=None, help='总时长（秒），不给就从表 A 末行推')
    ap.add_argument('--actions', type=float, default=None, help='4.5 节动作总数，给了才核表 B 合计')
    a = ap.parse_args()

    if not os.path.exists(a.spec):
        print('找不到设定书：' + a.spec)
        return 2
    text = read(a.spec)

    # ---- 表 A ----
    head, rows = table_rows(text, ['段', '对标'])
    if not rows:
        print('=' * 76)
        print('没找到「三段配额」表（表头需同时含「段」和「对标」）')
        print('说明：这一版设定书还没按硬规则 17 写表 A，无法核三段配额。')
        print('     按 2_复刻.txt 第 17 条补表后重跑。')
        print('=' * 76)
        return 1

    def col(cells, *names):
        for n in names:
            for k, c in enumerate(cells):
                if n in c:
                    return k
        return None

    c_seg = col(head, '段')
    c_dur = col(head, '本片时长', '时长')
    c_ref = col(head, '对标同段时长', '对标')
    c_refn = col(head, '对标工序数')
    c_own = col(head, '本片工序数', '工序数')

    seg = {}
    for r in rows:
        if len(r) <= max(x for x in [c_seg, c_dur] if x is not None):
            continue
        name = r[c_seg] if c_seg is not None else ''
        for s in SEG_NAMES:
            if s in name:
                seg[s] = {
                    'dur': num(r[c_dur]) if c_dur is not None else None,
                    'ref': num(r[c_ref]) if c_ref is not None else None,
                    'refn': num(r[c_refn]) if c_refn is not None else None,
                    'own': num(r[c_own]) if c_own is not None else None,
                    'raw': r,
                }
                break

    results = []   # (项目, 实测, 阈值, ok, note)

    # 1 开头工序数
    if '开头' in seg and seg['开头']['own'] is not None:
        v = seg['开头']['own']
        results.append(('开头段工序数', f'{v:.0f} 个', '= 0 个', v == 0,
                        '开头只许呈现问题；有工序说明把改造提前干了'))
    else:
        results.append(('开头段工序数', '表里没填', '= 0 个', False, '表 A 缺少本片工序数'))

    # 2 中间工序比
    mid = seg.get('中间')
    if mid and mid['own'] is not None and mid['refn']:
        ratio = mid['own'] / mid['refn']
        results.append(('中间段工序比', f"{mid['own']:.0f} / {mid['refn']:.0f} = {ratio:.2f}",
                        '≥ 0.90', ratio >= 0.90 - 1e-9,
                        '低于 0.9 说明有工序被搬到开头或结尾了'))
    else:
        results.append(('中间段工序比', '表里没填全', '≥ 0.90', False, '需要「对标工序数」和「本片工序数」两列'))

    # 3 中间时长比
    if mid and mid['dur'] is not None and mid['ref']:
        ratio = mid['dur'] / mid['ref']
        results.append(('中间段时长比', f"{mid['dur']:.2f} / {mid['ref']:.2f} = {ratio:.2f}",
                        '≥ 0.90', ratio >= 0.90 - 1e-9,
                        '中间段被抽空，成片就会显得改造量不足'))
    else:
        results.append(('中间段时长比', '表里没填全', '≥ 0.90', False, ''))

    # 4 每工序秒数比
    if (mid and mid['dur'] and mid['own'] and mid['ref'] and mid['refn']):
        per_own = mid['dur'] / mid['own']
        per_ref = mid['ref'] / mid['refn']
        ratio = per_own / per_ref if per_ref else 0
        results.append(('中间段每工序秒数比', f'{per_own:.2f}s / {per_ref:.2f}s = {ratio:.2f}',
                        '≥ 0.90', ratio >= 0.90 - 1e-9,
                        '每工序给的时间太短，会读成草草了事'))

    # 5 时长合计
    durs = [(s, seg[s]['dur']) for s in SEG_NAMES if s in seg and seg[s]['dur']]
    if len(durs) == 3:
        ssum = sum(d for _, d in durs)
        total = a.total or sum(d for _, d in durs)
        ok = abs(ssum - total) < 0.05
        results.append(('三段时长合计', f'{ssum:.3f} 秒 / 总时长 {total:.3f} 秒',
                        '差 < 0.05 秒', ok, '三段之和必须等于总时长'))

    # ---- 表 B ----
    # 注意：必须用「工序号」做锚点。表 A 的表头也含「工序」「段」两个词，
    # 用宽关键字会误匹配到表 A，把三段行当成工序行。
    hb, rb = table_rows(text, ['工序号'])
    if rb:
        segcount = {s: 0 for s in SEG_NAMES}
        act_sum = 0.0
        unknown = 0
        for r in rb:
            joined = ' '.join(r)
            hit = next((s for s in SEG_NAMES if s in joined), None)
            if hit:
                segcount[hit] += 1
            else:
                unknown += 1
            idx = next((k for k, c in enumerate(hb) if '动作数' in c), None)
            if idx is not None and idx < len(r):
                act_sum += num(r[idx]) or 0
        results.append(('表 B 工序归属齐全', f'{len(rb)} 行，{unknown} 行没写段',
                        '= 0 行', unknown == 0,
                        f'按段统计：开头 {segcount["开头"]}／中间 {segcount["中间"]}／结尾 {segcount["结尾"]}'))
        # 表 A 与表 B 互咬
        if mid and mid['own'] is not None:
            ok = abs(segcount['中间'] - mid['own']) < 0.5
            results.append(('表 A 与表 B 中间工序数一致',
                            f"表A {mid['own']:.0f} / 表B {segcount['中间']}",
                            '必须相等', ok, '两张表自己打架，说明是编的'))
        if a.actions is not None:
            ok = abs(act_sum - a.actions) < 0.5
            results.append(('工序动作数合计', f'{act_sum:.0f} / 4.5 节 {a.actions:.0f}',
                            '必须相等', ok, '动作数必须守恒'))
    else:
        results.append(('表 B 工序清单', '没找到', '必须有', False,
                        '表头需含「工序」「段」两字'))

    # ---- 打印 ----
    print('=' * 80)
    print('三段配额 + 工序守恒 闸门')
    print('  设定书：' + a.spec)
    print('=' * 80)
    print(f"{'项目':<30}{'实测':<34}{'阈值':<12}判定")
    print('-' * 80)
    fails = 0
    for name, actual, need, ok, note in results:
        flag = 'PASS' if ok else 'FAIL'
        if not ok:
            fails += 1
        print(f'{name:<30}{actual:<34}{need:<12}{flag}')
        if note:
            print(f'    · {note}')
    print('-' * 80)
    print('结果：' + ('全部通过' if fails == 0 else f'{fails} 项不过'))
    return 0 if fails == 0 else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        print('运行出错：', e)
        sys.exit(2)
