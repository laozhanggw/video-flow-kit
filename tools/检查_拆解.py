#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查_拆解.py —— 第①段（拆解）交付闸门

它查的是「该有的字段有没有、新加的硬字段填了没」，不判内容好坏。

七项
----
1. 四份产物齐不齐（索引 / 首帧图 / 开头拆解 / 整片拆解）
2. 开头拆解 有六张表（逐镜 / 七段 / 表面清单 / 首帧六要素 / 情绪弧 / 冲突强度）
3. 表面清单的「问题物」里写了画面占比（%），不是片数
4. 首帧第六项「观众第一反应」是三选一里的一个
5. 情绪弧那一句带 0–3 的数字
6. 索引里「骨架一句话」是三段式（改造前 / 改造 / 改造后）
7. 整片拆解里有终局兑现链，且区分了根治项与升华项

用法
----
  python 检查_拆解.py --repo "…\\对标库\\B0001_la_casa_del_sueno"

退出码：0 全过 / 1 有不过 / 2 出错
"""

import argparse
import math
import os
import re
import sys

OK = (42, 132, 78)
BAD = (198, 56, 56)

TOOLS = ['高压水枪', '水枪', '硬毛刷', '毛刷', '抹布', '电钻', '起子', '螺丝刀',
         '梯子', '人字梯', '铝梯', '漆桶', '割灌机', '打草机', '独轮车',
         '铲子', '铁锹', '耙子', '滚筒']
REACTIONS = ['必须马上处理', '可以忍但不好看', '看着舒服']


def read(p):
    for enc in ('utf-8', 'utf-8-sig', 'gbk'):
        try:
            return open(p, encoding=enc).read()
        except Exception:
            continue
    return ''


def has(text, *keys):
    return all(k in text for k in keys)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--repo', '--对标', dest='repo', required=True,
                    help='对标库里的那一条，例如 …\\B0001_la_casa_del_sueno')
    a = ap.parse_args()

    if not os.path.isdir(a.repo):
        print('找不到目录：' + a.repo)
        return 2

    idx = os.path.join(a.repo, '00_对标索引.md')
    head = os.path.join(a.repo, '02_开头拆解.md')
    full = os.path.join(a.repo, '03_整片拆解.md')
    ff = os.path.join(a.repo, '01_原片证据', 'first_frame-001.jpg')

    t_idx = read(idx) if os.path.exists(idx) else ''
    t_head = read(head) if os.path.exists(head) else ''
    t_full = read(full) if os.path.exists(full) else ''

    rows = []

    # 1 五份产物
    selfcheck = os.path.join(a.repo, '04_交付自查表.md')
    got = [os.path.exists(x) for x in (idx, ff, head, full, selfcheck)]
    rows.append(('五份产物齐全', f'{sum(got)}/5', '= 5', all(got),
                 '缺：' + '、'.join(os.path.basename(x) for x, g in
                    zip((idx, ff, head, full, selfcheck), got) if not g) or '—'))

    # 2 六张表
    tables = {
        '逐镜表': ('逐镜表',),
        '七段环节': ('七段',),
        '表面清单': ('表面清单',),
        '首帧六要素': ('六要素',),
        '情绪弧': ('情绪弧',),
        '冲突强度': ('冲突强度',),
    }
    miss = [n for n, ks in tables.items() if not has(t_head, *ks)]
    rows.append(('开头拆解六张表', f'{len(tables)-len(miss)}/6', '= 6', not miss,
                 '缺：' + '、'.join(miss) if miss else '—'))

    # 3 问题物带占比（固定写法 + 取值范围）
    #   容忍 Markdown 强调与全角空格：B0009 写成「问题物占全画面 **31.6%**」，
    #   原正则要求 % 前紧挨数字，被 ** 挡住，误判「没找到固定写法」。
    pat = re.compile(
        r'问题物占全画面[*_`\s\u3000]*[:：]?[*_`\s\u3000]*(\d+(?:\.\d+)?)[*_`\s\u3000]*%')
    found = [(float(m.group(1)), m.group(), m.group(1)) for m in pat.finditer(t_head)]
    if not found:
        rows.append(('问题物写了画面占比', '没找到固定写法', '问题物占全画面 XX.X%', False,
                     '必须写成「问题物占全画面 XX.X%」，不许写「约两成」「数十片」'))
    else:
        vals = []
        for v, s, n in found:
            if v not in [x[0] for x in vals]:
                vals.append((v, s, n))
        if len(vals) > 1:
            two = ' / '.join(n + '%' for _, _, n in vals[:2])
            rows.append(('问题物写了画面占比', two, '只能一个值', False,
                         '占比出现两个不同值：' + two))
        elif vals[0][0] < 0.5 or vals[0][0] > 100:
            rows.append(('问题物写了画面占比', vals[0][1], '0.5%–100%', False,
                         '数值 %s%% 超出合理范围，请重新数像素' % vals[0][2]))
        else:
            rows.append(('问题物写了画面占比', vals[0][1], '问题物占全画面 XX.X%', True,
                         '写「数十片」不算，必须给占画面百分比'))

    # 4 观众第一反应（只认「观众第一反应」这一行，不看别处）
    cands = []
    for ln in t_head.splitlines():
        s = ln.strip().lstrip('*->|｜ \u3000')
        if not s.startswith('观众第一反应'):
            continue
        pos = max(s.rfind('：'), s.rfind(':'))
        if pos >= 0:
            val = s[pos + 1:]
        elif '|' in s or '｜' in s:
            cells = [x for x in re.split(r'[|｜]', s) if x.strip()]
            val = cells[-1] if len(cells) >= 2 else ''
        else:
            continue
        for cut in ('｜', '|'):
            if cut in val:
                val = val.split(cut)[0]
        val = val.strip('* \t\u3000。.')
        if val:
            cands.append(val)
    multi = [v for v in cands if sum(r in v for r in REACTIONS) >= 2]
    exact = [v for v in cands if v in REACTIONS]
    uniq = []
    for v in exact:
        if v not in uniq:
            uniq.append(v)
    if len(uniq) > 1:
        two = ' / '.join(uniq)
        rows.append(('观众第一反应（三选一）', two, '只能一个值', False,
                     '写了两个不同的选项：' + two))
    elif uniq:
        rows.append(('观众第一反应（三选一）', uniq[0], '三选一', True,
                     '只能填一个，且不许用形容词'))
    elif multi:
        rows.append(('观众第一反应（三选一）', multi[0], '三选一', False,
                     '只能写一个，不要并列'))
    elif cands:
        rows.append(('观众第一反应（三选一）', cands[0], '三选一', False,
                     '只能填一个，且不许用形容词'))
    else:
        rows.append(('观众第一反应（三选一）', '没填', '三选一', False,
                     '只能填一个，且不许用形容词'))

    # 5 情绪弧带 0–3（按小节切，不用定长窗口）
    emo = ''
    i = t_head.find('情绪弧')
    if i >= 0:
        ls = t_head.rfind('\n', 0, i) + 1
        hm = re.match(r'(#{1,6})\s', t_head[ls:])
        lvl = len(hm.group(1)) if hm else 6
        m2 = re.search(r'\n#{1,%d}\s' % lvl, t_head[i + 3:])
        j = i + 3 + m2.start() if m2 else len(t_head)
        emo = t_head[i:j]
    num = re.search(r'(?:难受|强度)\s*[:：]?\s*([0-3])|[:：]\s*([0-3])\s*[）)]', emo)
    rows.append(('情绪弧带难受程度 0–3', '有' if num else '没找到', '必须带',
                 bool(num), '只写「闷、脏、潮」不算'))

    # 6 骨架一句话三段式
    three = has(t_idx, '改造前') and has(t_idx, '改造后') and ('根治' in t_idx) and ('升华' in t_idx or '升华项' in t_idx)
    rows.append(('骨架一句话三段式', '齐' if three else '不齐', '改造前/改造/改造后＋根治升华',
                 three, '写成动作流水账不算'))

    # 7 终局兑现链
    chain = has(t_full, '终局') and ('根治' in t_full) and ('升华' in t_full)
    rows.append(('终局兑现链（根治＋升华）', '齐' if chain else '不齐', '两项都要有',
                 chain, '只有「看起来好看」不算，要区分根治项与升华项'))

    # 8 人物四件套（事实字段，缺一件算没交）
    seg = ''
    lines = t_head.splitlines()
    for n, ln in enumerate(lines):
        cell = re.sub(r'^[\s|｜·\-+>]+', '', ln)
        cell = cell.split('|')[0].split('｜')[0].replace('*', '').strip()
        if not (cell == '人物' or cell.startswith('人物（') or cell.startswith('人物(')
                or cell.startswith('人物：') or cell.startswith('人物:')):
            continue
        if ln.lstrip().startswith('|'):
            seg = ln
        else:
            blk = [ln]
            for nx in lines[n + 1:]:
                t = nx.lstrip()
                if not t or t.startswith('|') or t.startswith('#'):
                    break
                blk.append(nx)
            seg = '\n'.join(blk)
        break
    need = {
        '人数': bool(re.search(r'\d+\s*个?\s*人|人数', seg)),
        '年龄外观': ('岁' in seg),
        '人脸特写次数': bool(re.search(r'人脸特写|特写\s*[:：]?\s*\d+|\d+\s*次', seg)),
        '正脸:侧脸:背影': bool(re.search(r'\d+\s*[:：]\s*\d+\s*[:：]\s*\d+', seg)),
    }
    miss = [k for k, v in need.items() if not v]
    rows.append(('人物四件套', f'{len(need)-len(miss)}/4', '= 4', not miss,
                 '缺：' + '、'.join(miss) + '（只报事实，不下能不能用的结论）' if miss else '—'))

    # 9 开头微段表（0.2 秒一格，最少 3 秒 = 15 格）
    m = re.search(r'T_钩\s*=\s*(\d+(?:\.\d+)?)\s*秒', t_head)
    rows9 = 0
    # 找「带微段表三个字的标题行」，从那一行往后数；找不到标题再退回第一次出现的位置
    starts = []
    for mt in re.finditer(r'^#{1,6}[^\n]*微段表[^\n]*$', t_head, re.M):
        starts.append(mt.start())
    base = max(starts) if starts else (t_head.find('微段表') if '微段表' in t_head else -1)
    if base >= 0:
        seg9 = t_head[base:]
        ends = []
        p = seg9.find('2）七段')
        if p > 0:
            ends.append(p)
        mh = re.search(r'\n#{1,6}\s', seg9)
        if mh:
            ends.append(mh.start())
        if ends:
            seg9 = seg9[:min(ends)]
        rows9 = sum(1 for ln in seg9.splitlines()
                    if re.match(r'^\s*\|\s*\d+\s*\|', ln))
    need9 = 15
    if m:
        need9 = max(15, math.ceil(float(m.group(1)) * 5 - 1e-9))
    ok9 = bool(m) and rows9 >= need9
    rows.append(('开头微段表（0.2 秒一格）',
                 f'{rows9} 格／要 {need9} 格' if m else '没写 T_钩',
                 'T_钩 ÷ 0.2，且 ≥15', ok9,
                 'T_钩 写在 02_开头拆解.md 开头一行；微段表一格不许合并'))

    # 打印
    W = 82
    print('=' * W)
    print('第①段 · 拆解 交付闸门')
    print('  对标库：' + a.repo)
    print('=' * W)
    print(f"{'项目':<26}{'实测':<20}{'要求':<26}判定")
    print('-' * W)
    fails = 0
    for name, actual, need, ok, note in rows:
        if not ok:
            fails += 1
        print(f'{name:<26}{actual:<20}{need:<26}{"PASS" if ok else "FAIL"}')
        if note and note != '—':
            print(f'    · {note}')
    print('-' * W)
    print('结果：' + ('全过，可以进第②段' if fails == 0 else f'{fails} 项不过，退回补'))
    return 0 if fails == 0 else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        print('运行出错：', e)
        sys.exit(2)
