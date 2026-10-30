#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抽查.py —— 把「读没读全」从自述变成可核对的字符串

原理
----
读是不可见的，输出是可见的，所以模型必然优先优化输出。
唯一的办法：给「读」造一个**不可伪造的痕迹**。

做法分两步：

  第一步 出题（在对话框开工之前）：
    从必读文件里随机抽 K 句话，写成一张「抽问单」。
    把抽问单连同指令一起发给对话框，并写明：
    「交付物里必须有一节『读到的原文』，把这 K 句一字不改地抄进去。」

  第二步 核对（在对话框交活之后）：
    检查每句是否原样出现在交付物里。缺一句就是没读全。

为什么编不出来
--------------
· 句子是**随机**抽的：不读完整份文件，抽不到的那几句就抄不出来。
· 核对是**字符串比对**，不是判断：不存在「大概意思对」这种空间。
· 每句截取 40 字的窗口，抄错一个字就算不过。

用法
----
  出题：
    python 抽查.py make --files "a.md,b.md" --k 6 --out 抽问单.md

  核对：
    python 抽查.py verify --sheet 抽问单.md --answer 交付物.md

  --files 支持逗号分隔，也可以给目录（目录会递归取 .md/.txt）。

退出码：0 全对 / 1 有缺 / 2 出错
"""

import argparse
import glob
import os
import random
import re
import sys

WIN = 40          # 每句截取的窗口长度
MIN_LINE = 24     # 太短的行不要（没信息量）
SKIP_PAT = re.compile(r'^[\s|:\-—=═·*#`>]*$')


def load_lines(path):
    out = []
    for enc in ('utf-8', 'utf-8-sig', 'gbk'):
        try:
            text = open(path, encoding=enc).read()
            break
        except Exception:
            text = None
    if text is None:
        return out
    for raw in text.splitlines():
        s = raw.strip()
        if len(s) < MIN_LINE or SKIP_PAT.match(s):
            continue
        # 去掉 markdown 表格分隔、纯标题
        if re.fullmatch(r'\|?[\s:\-|]+\|?', s):
            continue
        if s.startswith('#') and len(s) < 40:
            continue
        out.append(s)
    return out


def collect(files_arg):
    paths = []
    for part in files_arg.split(','):
        p = part.strip()
        if not p:
            continue
        if os.path.isdir(p):
            for ext in ('*.md', '*.txt'):
                paths += glob.glob(os.path.join(p, '**', ext), recursive=True)
        elif os.path.exists(p):
            paths.append(p)
        else:
            print(f'  [跳过] 找不到：{p}')
    return paths


def make(a):
    paths = collect(a.files)
    if not paths:
        print('没有可用的文件')
        return 2
    random.seed(a.seed)
    pool = []
    for p in paths:
        lines = load_lines(p)
        for s in lines:
            pool.append((p, s))
    if len(pool) < a.k:
        print(f'可用句子只有 {len(pool)} 条，少于要抽的 {a.k} 条')
        return 2
    picked = random.sample(pool, a.k)

    with open(a.out, 'w', encoding='utf-8') as f:
        f.write('# 抽问单（随机抽取，不许跳）\n\n')
        f.write('> 用法：把本文件连同指令一起发给对话框，并在指令里加这一句：\n')
        f.write('> 「交付物最前面必须有一节『读到的原文』，把下面每一句**一字不改**地抄进去，')
        f.write('> 抄不出就是没读到，这一版不收。」\n\n')
        f.write('| # | 取自 | 必须原样出现的句子 |\n|---|---|---|\n')
        for i, (p, s) in enumerate(picked, 1):
            core = s
            if len(core) > WIN * 2:
                mid = len(core) // 2
                core = core[max(0, mid - WIN):mid + WIN].strip()
            core = core.replace('|', '｜')
            f.write(f'| {i} | {os.path.basename(p)} | {core} |\n')

        f.write('\n---\n\n## 可直接复制的附加指令（贴在原指令后面）\n\n')
        f.write('```text\n')
        f.write('【读到的证明｜硬规定，不交这一节视为没读】\n')
        f.write('交付物的第一节必须叫「读到的原文」，把上面抽问单里的每一句\n')
        f.write('一字不改地抄进去，编号对齐。抄不出、改写、概括、只写「已阅读」，\n')
        f.write('一律算没读到，这一版直接打回。抄错一个字也算没过。\n')
        f.write('```\n')
    print(f'已出题 {a.k} 条 → {os.path.abspath(a.out)}')
    for i, (p, s) in enumerate(picked, 1):
        print(f'  {i}. [{os.path.basename(p)}] {s[:60]}...')
    return 0


def verify(a):
    if not os.path.exists(a.sheet):
        print('找不到抽问单：' + a.sheet)
        return 2
    if not os.path.exists(a.answer):
        print('找不到交付物：' + a.answer)
        return 2
    sheet = open(a.sheet, encoding='utf-8').read()
    answer = open(a.answer, encoding='utf-8').read()
    norm = lambda t: re.sub(r'\s+', '', t)
    ans = norm(answer)

    rows = [l for l in sheet.splitlines() if l.strip().startswith('|') and '---' not in l]
    items = []
    for l in rows[1:]:
        cells = [c.strip() for c in l.strip().strip('|').split('|')]
        if len(cells) >= 3 and cells[0].isdigit():
            items.append((cells[0], cells[1], cells[2]))

    if not items:
        print('抽问单里没读到题目行')
        return 2

    print('=' * 72)
    print(f'抽查核对：{len(items)} 条')
    print('=' * 72)
    bad = 0
    for no, src, sent in items:
        ok = norm(sent) in ans
        if not ok:
            bad += 1
        print(f'  {no:>2}. {"PASS" if ok else "MISS"}  [{src}] {sent[:46]}')
    print('-' * 72)
    if bad:
        print(f'结果：{bad} 条没抄进交付物 → 判定「没读到／没读全」')
        print('处置：退回重做，不许进入下一段。')
    else:
        print('结果：全部抄对 → 判定「这几处确实读到了」')
    return 0 if bad == 0 else 1


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)

    m = sub.add_parser('make', help='出题')
    m.add_argument('--files', required=True)
    m.add_argument('--k', type=int, default=6)
    m.add_argument('--seed', type=int, default=None)
    m.add_argument('--out', default='抽问单.md')

    v = sub.add_parser('verify', help='核对')
    v.add_argument('--sheet', required=True)
    v.add_argument('--answer', required=True)

    a = ap.parse_args()
    return make(a) if a.cmd == 'make' else verify(a)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        print('运行出错：', e)
        sys.exit(2)
