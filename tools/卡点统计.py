# -*- coding: utf-8 -*-
"""卡点统计.py —— 把所有项目的 `_卡点日志.md` 汇总成一张表，看流程哪一段最卡。

用途：日志只记一行一行，攒到十几条人就看不出来了。这个脚本把同一类问题数出来，
到 3 次就提示「这不是偶发，是流程缺口」，并告诉你去改哪个文件。

用法
----
  python tools/卡点统计.py                 # 扫 {{ROOT}}/_项目 下所有项目
  python tools/卡点统计.py <目录>          # 扫指定目录（可以是单个项目文件夹）
  python tools/卡点统计.py <目录> --明细     # 连每一行都列出来

只读，不改任何文件。
"""
import argparse
import os
import re
import sys
from collections import Counter, defaultdict

TYPES = ['缺输入', '规则打架', 'AI 编了', '闸门不过', '该签字', '工具坏了', '我不懂']
STATUS = ['已解', '待解', '已沉淀']
# 每种卡点该往哪儿沉淀：到 3 次就把这句话打出来，省得人再想
SINK = {
    '缺输入': '查 `00_字段契约.md` 里这一段该交的字段，缺的补进上游交付清单',
    '规则打架': '加一条到 `00_规则优先级表.md` 的裁决；两条互斥规则不许同时活着',
    'AI 编了': '在对应指令里写死「这个数只能来自哪个文件」，并加一条 `检查_自洽.py` 的检查',
    '闸门不过': '看是不是同一个字段反复不过；是就说明指令没讲清，改指令，别改产物',
    '该签字': '写进 `00_决策点清单.md` 并给一个默认值；常规项不该每次都要人签',
    '工具坏了': '修 `09 工具/` 里那个脚本，并把这次的错例加成回归样本',
    '我不懂': '**先分清是流程漏了还是培训漏了**：一页 `00_卡住了怎么办.md` 有没有覆盖到？没覆盖就补它',
}


def read(p):
    for enc in ('utf-8', 'utf-8-sig', 'gbk'):
        try:
            return open(p, encoding=enc).read()
        except Exception:
            continue
    return ''


def rows_of(path):
    """取出日志里「## 日志」之后的表格行，返回 [(日期, 段, 卡在哪, 类型, 怎么解, 状态)]。"""
    text = read(path)
    if not text:
        return []
    body = text.split('## 日志', 1)[1] if '## 日志' in text else text
    out = []
    for line in body.splitlines():
        s = line.strip()
        if not s.startswith('|'):
            continue
        cells = [c.strip() for c in s.strip('|').split('|')]
        if len(cells) < 6:
            continue
        if set(''.join(cells)) <= set('-: '):        # |---|---|
            continue
        if cells[0] in ('日期', '') or '卡在哪' in cells[2]:
            continue
        out.append(tuple(cells[:6]))
    return out


def find_logs(root):
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if d not in {'_备份', '_历史', '_构建临时', '__pycache__', '.git',
                                    '_项目骨架', '模板', '指令', '指令模板_v3', 'skills'}
                       and '备份' not in d]
        for fn in filenames:
            if fn == '_卡点日志.md':
                found.append(os.path.join(dirpath, fn))
    return sorted(found)


def bar(n, width=24):
    n = min(n, width)
    return '█' * n + '·' * (width - n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('root', nargs='?', default=None)
    ap.add_argument('--明细', '--detail', dest='detail', action='store_true')
    a = ap.parse_args()

    root = a.root
    if not root:
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cand = os.path.join(here, '_项目')
        root = cand if os.path.isdir(cand) else here
    if not os.path.isdir(root):
        print('找不到目录：' + root)
        return 2

    logs = find_logs(root)
    if not logs:
        print('在 %s 下面没找到 `_卡点日志.md`。' % root)
        print('建一份：把 `模板\\_卡点日志.md` 复制到项目根目录，改名 `_卡点日志.md`。')
        return 1

    all_rows = []
    for p in logs:
        proj = os.path.basename(os.path.dirname(p))
        for r in rows_of(p):
            all_rows.append((proj,) + r)

    # 列序：(项目, 日期, 段, 卡在哪, 类型, 怎么解, 状态) → 下标 0–6
    real = [r for r in all_rows if r[3] != '无卡点']
    print('=' * 66)
    print('卡点统计｜扫了 %d 份日志，共 %d 条记录（其中「无卡点」%d 条）'
          % (len(logs), len(all_rows), len(all_rows) - len(real)))
    print('=' * 66)
    if not real:
        print('一条卡点都没有。要么真顺，要么日志没在写——先确认每个对话框交付前都写了吗。')
        return 0

    cnt = Counter(r[4] for r in real)
    # 已经沉淀成规则的，说明这一类已经修过了，不再算「该动」
    live = Counter(r[4] for r in real if r[6] != '已沉淀')
    print('\n一、按类型（未沉淀的到 3 次就是流程缺口，不是偶发）\n')
    for t in TYPES:
        n = cnt.get(t, 0)
        if not n:
            continue
        m = live.get(t, 0)
        flag = '  ← 该动了（%d 条还没沉淀）' % m if m >= 3 else ('  ✓ 已修过' if n else '')
        print('  %-6s %s %2d%s' % (t, bar(n), n, flag))
    unknown = [t for t in cnt if t not in TYPES]
    if unknown:
        print('  %-6s %2d  （这几个词不在七个类型里，统计会漏，回去改日志）'
              % ('其他', sum(cnt[t] for t in unknown)))

    seg = Counter(r[2] for r in real)
    print('\n二、按段（哪一段最卡，就从哪一段开始改）\n')
    for s, n in sorted(seg.items(), key=lambda x: -x[1]):
        print('  %-6s %s %2d' % (s, bar(n), n))

    proj = Counter(r[1] for r in real)
    if len(proj) > 1:
        print('\n三、按项目\n')
        for s, n in sorted(proj.items(), key=lambda x: -x[1]):
            print('  %-28s %2d' % (s[:28], n))

    todo = [r for r in real if r[6] == '待解']
    print('\n四、还挂着的（%d 条）\n' % len(todo))
    if not todo:
        print('  没有。')
    for r in todo:
        print('  %s｜%s｜%s' % (r[2], r[4], r[3]))

    done = [r for r in real if r[6] == '已沉淀']
    print('\n五、已经沉淀成规则的：%d 条' % len(done))
    stuck = [r for r in real if r[6] == '已解']
    print('    只当场解了、还没沉淀的：%d 条 —— 这些下次还会再犯' % len(stuck))

    hits = [(t, live[t]) for t in TYPES if live.get(t, 0) >= 3]
    if hits:
        print('\n' + '-' * 66)
        print('该动哪儿（同一类攒到 3 次，按这个顺序改）：\n')
        for i, (t, n) in enumerate(sorted(hits, key=lambda x: -x[1]), 1):
            print('  %d. %s（%d 次）→ %s' % (i, t, n, SINK[t]))
        print('\n改完把日志里那几行状态改成「已沉淀」，写清搬到哪了。')
        print('-' * 66)

    if a.detail:
        print('\n六、全部明细\n')
        for r in all_rows:
            print('  %s｜%s｜%s｜%s｜%s｜%s' % r)

    return 0


if __name__ == '__main__':
    sys.exit(main())
