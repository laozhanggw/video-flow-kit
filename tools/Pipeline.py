#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
流程.py —— 唯一入口。只记这一个文件。

原来 8 个脚本、4 个 bat，各叫各的、参数各不相同，用起来像捉迷藏。
这里把它们收进一个门，你只要记三个动词：

    流程.py 说明                     打印整张地图（哪一步、查什么、跑哪条）
    流程.py 查 <阶段> [参数]          过闸门，只输出 PASS/FAIL
    流程.py 看 <图>   [参数]          出一张图，让你一眼判
    流程.py 抽 make|verify           随机抽查（防没读全）

阶段：拆解 / 设定书 / 开头 / 分镜 / 单元 / 成片 / 全部
图　：环节 / 四层 / 对比

例：
    python 流程.py 说明
    python 流程.py 查 设定书 --版本 "…\\V01_la_casa_del_sueno"
    python 流程.py 查 成片   --视频 "…\\成品.mp4" --起 23.670
    python Pipeline.py 查 全部   --版本 "…\\V01" --视频 "…\\成品.mp4"
    python 流程.py 看 四层   --头 开头.csv --段 后段.csv --单元 "U01=N01;U02=N02-N07"
    python 流程.py 抽 make   --files "00_版本设定书.md" --k 6 --out 抽问单.md

所有参数都透传给底下的引擎，风格统一成「--中文短名」，也认原来的英文长名。
退出码：0 全过 / 1 有不过 / 2 出错
"""

import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

ENG = {
    '拆解': '检查_拆解.py',
    '开头': '检查_开头.py',
    '交付物': '检查_交付物.py',
    '动作预算': '检查_动作预算.py',
    '三段': '检查_三段.py',
    '结尾': '检查_结尾.py',
    '环节': '看板_环节.py',
    '四层': '看板_四层.py',
    '对比': '看板_对比.py',
    '抽查': '抽查.py',
}

STAGES = ['拆解', '设定书', '开头', '分镜', '单元', '成片', '全部']

MAP = """
╔══════════════════════════════════════════════════════════════════════════╗
║  七段流程 · 每段只有三件事：查什么、看什么、什么时候能往下走               ║
╚══════════════════════════════════════════════════════════════════════════╝

  段        你跑什么                        它判什么
  ────────  ──────────────────────────────  ──────────────────────────────
  ① 拆解    查 拆解                        字段齐不齐、工序占比填了对不对
            看 环节   （可选）              对标工序格子条

  ② 设定书  查 设定书                      三段配额、工序守恒、表A与表B互咬
            看 环节                        我们的工序 vs 对标，缺哪格

  ③ 开头    查 开头                        开头工序数必须 0、不许有工具
            看 环节 --模式 seq             镜数、每镜秒数、景别是否一致

  ④ 小分镜  查 分镜                        动作数密度、刀数、位移刀秒数
            看 环节                        工序缺没缺

  ⑤ 单元    查 单元                        盒子秒数、覆盖表、跨段混装
            看 四层                        ★ 分镜 ↔ 单元 有没有漏、重、超 15 秒

  ⑥ 成片    查 成片                        结尾亮度比、末镜时长、验证段镜数
            看 对比                        ★ 并排看，像不像
                                          （成片前 看 四层 再看一眼）

  ⑦ 复盘    手动                          把成片当新对标，回填数据

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
每段开工前，都先跑一次「抽 make」出题，交活后「抽 verify」核对。
这一步不是可选的——它管的是"AI 到底读没读"，其它所有检查都假设它读了。
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

记不住就跑：  Pipeline.py 查 全部 --版本 <版本目录> --视频 <成品.mp4>
它会把能查的一次查完，最后给一行总判定。
"""


def ask(prompt, allow_empty=False):
    try:
        v = input(prompt).strip().strip('"').strip("'")
    except (EOFError, KeyboardInterrupt):
        return None
    if not v and not allow_empty:
        return None
    return v


MENU = """
你要做什么？输数字，回车。

  1  查一条片子的整条流程   （把「版本文件夹」拖进来）
  2  查对标拆解做全了没     （把「对标库那条」拖进来）
  3  查成片结尾对不对       （把「成品.mp4」拖进来）
  4  抽查出题：考 AI 有没有真读
  5  抽查核对：看它抄回来没有
  6  看整张流程图
  0  退出
"""


def do_menu():
    while True:
        print(MENU)
        c = ask('  请输入编号：', allow_empty=True)
        if c is None:
            return 2
        c = c.strip()

        if c == '0':
            print('\n有事再叫我。')
            return 0

        elif c == '1':
            v = ask('  把「版本文件夹」拖到这里，回车：')
            if not v:
                print('  [没给路径]')
                continue
            print()
            rc = do_check(argparse.Namespace(
                阶段='全部', 版本=v, 视频=None, 基准=None, 总长=None,
                起=None, 对标=None, 对标起=None, 对标库=None))
            print()
            input('  按回车回菜单…')

        elif c == '2':
            r = ask('  把「对标库那条」拖到这里（形如 B0001_xxx），回车：')
            if not r:
                print('  [没给路径]')
                continue
            print()
            rc = do_check(argparse.Namespace(
                阶段='拆解', 版本=None, 视频=None, 基准=None, 总长=None,
                起=None, 对标=None, 对标起=None, 对标库=r))
            print()
            input('  按回车回菜单…')

        elif c == '3':
            f = ask('  把「成品.mp4」拖到这里，回车：')
            if not f:
                print('  [没给路径]')
                continue
            st = ask('  验证段从第几秒开始？（设定书第 9 节里有；不知道就直接回车）',
                     allow_empty=True)
            print()
            rc = do_check(argparse.Namespace(
                阶段='成片', 版本=None, 视频=f, 基准=None, 总长=None,
                起=(float(st) if st else None), 对标=None, 对标起=None, 对标库=None))
            print()
            input('  按回车回菜单…')

        elif c == '4':
            fs = ask('  要考哪几份文件？（多个用逗号隔开，也可以拖文件夹）')
            if not fs:
                print('  [没给文件]')
                continue
            k = ask('  抽几句？（直接回车 = 6）', allow_empty=True) or '6'
            out = ask('  存成什么名字？（直接回车 = 抽问单.md）', allow_empty=True) or '抽问单.md'
            print()
            run('抽查', ['make', '--files', fs, '--k', k, '--out', out])
            print(f'\n  题目已生成：{out}    把它连同指令一起发给对话框。')
            input('  按回车回菜单…')

        elif c == '5':
            sh = ask('  把「抽问单.md」拖进来，回车：')
            an = ask('  把 AI 交回来的「交付物.md」拖进来，回车：')
            if not sh or not an:
                print('  [缺文件]')
                continue
            print()
            rc = run('抽查', ['verify', '--sheet', sh, '--answer', an])
            print()
            input('  按回车回菜单…')

        elif c == '6':
            print(MAP)
            input('  按回车回菜单…')

        else:
            print('  只有 0–6 这几个编号。')


LOGS = []


def run(script, args, show=False):
    """跑一个引擎。默认把它的输出收进日志，不刷屏。"""
    path = os.path.join(HERE, ENG[script])
    if not os.path.exists(path):
        LOGS.append((script, 2, f'缺工具：{path}'))
        return 2
    r = subprocess.run([PY, path] + args, capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    out = (r.stdout or '') + (('\n' + r.stderr) if r.stderr else '')
    LOGS.append((script, r.returncode, out))
    if show:
        print(out)
    return r.returncode


HUMAN = {
    '拆解-字段':  ('对标拆解', '拆解那一步没做全', '让做拆解的那个对话框，按提示把缺的字段补齐'),
    '设定书-三段': ('设定书', '没写「三段配额」那张表，没法核', '让写设定书的对话框，按 2_复刻 第 17 条补一张表'),
    '设定书-交付物': ('设定书', '结构字段有缺', '让写设定书的对话框补上'),
    '开头-闸门':  ('开头', '开头干了不该干的活', '让写开头的对话框，把「动手」的活退回中间段'),
    '分镜-交付物': ('分镜', '字段、秒数或动作数有问题', '让写分镜的对话框改'),
    '单元-交付物': ('单元', '盒子的秒数或取用率有问题', '让划单元的对话框改'),
    '动作预算':   ('动作密度', '动作排得太密', '让写分镜的对话框，把每刀的动作减到 1 个'),
    '成片-结尾':  ('结尾', '结尾不达标', '重新生成结尾那一盒'),
}


def do_check(a):
    v, vid = a.版本, a.视频
    if a.阶段 != '全部' and not (v or vid or a.对标库):
        print('\n  缺参数。跑「6 看流程图」，或从菜单里选。\n')
        return 2

    results = []          # (key, rc)

    def add(key, rc):
        results.append((key, rc))

    # ① 拆解
    if a.阶段 in ('拆解', '全部'):
        if a.对标库:
            add('拆解-字段', run('拆解', ['--repo', a.对标库]))

    # ③ 开头
    if a.阶段 in ('开头', '全部') and v:
        add('开头-闸门', run('开头', ['--版本', v]))

    # ② 设定书
    if a.阶段 in ('设定书', '全部') and v:
        args = ['--spec', os.path.join(v, '00_版本设定书.md')]
        if a.总长:
            args += ['--total', str(a.总长)]
        add('设定书-三段', run('三段', args))

    # ②④⑤ 字段闸门
    if a.阶段 in ('设定书', '分镜', '单元', '全部') and v:
        stage_map = {'设定书': 'b', '分镜': 'd', '单元': 'e'}
        items = [('设定书-交付物', 'b'), ('分镜-交付物', 'd'), ('单元-交付物', 'e')] \
            if a.阶段 == '全部' else [(f'{a.阶段}-交付物', stage_map[a.阶段])]
        for key, st in items:
            base = ['--baseline', a.基准] if a.基准 else []
            add(key, run('交付物', [v, '--stage', st] + base))

    # 动作预算：只查该查的两个文件，不再扫全目录
    if a.阶段 in ('分镜', '单元', '全部') and v:
        base = ['--baseline', a.基准] if a.基准 else []
        targets = [os.path.join(v, '00_版本设定书.md'),
                   os.path.join(v, '分镜', '后段小分镜_有效.md')]
        targets = [t for t in targets if os.path.exists(t)]
        if targets:
            worst = 0
            for t in targets:
                worst = max(worst, run('动作预算', [t] + base))
            add('动作预算', worst)

    # ⑥ 成片
    if a.阶段 in ('成片', '全部') and vid:
        args = ['--video', vid]
        if a.起:
            args += ['--end-start', str(a.起)]
        if a.对标:
            args += ['--ref', a.对标]
        if a.对标起:
            args += ['--ref-end-start', str(a.对标起)]
        if v:
            args += ['--version-dir', v]
        add('成片-结尾', run('结尾', args))

    if not results:
        print('\n  这次没有可查的东西——参数没给全。\n')
        return 2

    # ---- 写日志 ----
    log_path = os.path.join(HERE, '_上次检查日志.txt')
    try:
        with open(log_path, 'w', encoding='utf-8') as f:
            for script, rc, out in LOGS:
                f.write(f'\n{"="*70}\n【{script}】退出码 {rc}\n{"="*70}\n{out}\n')
    except Exception:
        log_path = None

    # ---- 只打一张卡 ----
    bad = [(k, rc) for k, rc in results if rc != 0]
    total = len(results)
    passed = total - len(bad)

    print()
    print('  ' + '─' * 58)
    if not bad:
        print(f'  这条片子：可以往下走   （{passed}/{total} 项通过）')
        print('  ' + '─' * 58)
        print('  没有要改的。')
    else:
        print(f'  这条片子：先别往下走   （{total} 项里 {len(bad)} 项不过）')
        print('  ' + '─' * 58)
        print(f'  要改 {len(bad)} 处：\n')
        for n, (k, rc) in enumerate(bad, 1):
            name, what, how = HUMAN.get(k, (k, '不过', '看日志'))
            print(f'   {n}. 【{name}】{what}')
            print(f'      怎么办：{how}\n')
    print('  ' + '─' * 58)
    if log_path:
        print(f'  想看细节：{log_path}')
        print('  （不用看。上面那几句话已经说完了。）')
    print('  ' + '─' * 58)
    return 0 if not bad else 1


def do_show(a):
    kind = a.图
    if kind == '环节':
        args = ['--stage', a.标题 or '环节']
        if a.模式:
            args += ['--mode', a.模式]
        if a.对标工序:
            args += ['--ref', a.对标工序]
        if a.我们工序:
            args += ['--ours', a.我们工序]
        if a.对标景别:
            args += ['--ref-lbl', a.对标景别]
        if a.我们景别:
            args += ['--ours-lbl', a.我们景别]
        if a.单元:
            args += ['--map', a.单元]
        if a.出:
            args += ['--out', a.出]
        return run('环节', args)

    if kind == '四层':
        args = []
        if a.对标:
            args += ['--ref-file', a.对标]
        if a.头:
            args += ['--head-file', a.头]
        if a.段:
            args += ['--shots-file', a.段]
        if a.单元:
            args += ['--units', a.单元]
        if a.出:
            args += ['--out', a.出]
        if not a.头 or not a.段 or not a.单元:
            print('四层 需要 --头、--段、--单元 三个参数')
            return 2
        return run('四层', args)

    if kind == '对比':
        args = []
        if a.对标:
            args += ['--ref', a.对标]
        if a.视频:
            args += ['--ours', a.视频]
        if a.对标起:
            args += ['--ref-ends', a.对标起]
        if a.起:
            args += ['--ours-ends', a.起]
        if a.出:
            args += ['--out', a.出]
        if not a.对标 or not a.视频:
            print('对比 需要 --对标 <对标.mp4> 和 --视频 <成品.mp4>')
            return 2
        return run('对比', args)

    print(f'不认识的图：{kind}（可用：环节 / 四层 / 对比）')
    return 2


def do_sample(a):
    if a.动作 == 'make':
        return run('抽查', ['make', '--files', a.文件, '--k', str(a.数量), '--out', a.出 or '抽问单.md'])
    return run('抽查', ['verify', '--sheet', a.单, '--answer', a.答])


def main():
    if len(sys.argv) == 1 or sys.argv[1] in ('菜单', 'menu'):
        print()
        print('  视频流程 · 验收工具')
        return do_menu()
    if sys.argv[1] in ('说明', '-h', '--help', 'help'):
        print(MAP)
        return 0

    # 英文别名 → 中文（方便 .bat 用纯 ASCII 调，避免编码问题）
    ALIAS_VERB = {'check': '查', 'show': '看', 'sample': '抽',
                  'menu': '菜单', 'help': '说明'}
    ALIAS_WORD = {'all': '全部', 'deconstruct': '拆解', 'spec': '设定书',
                  'head': '开头', 'shots': '分镜', 'units': '单元', 'video': '成片',
                  'stage': '环节', 'layers': '四层', 'compare': '对比',
                  'make': 'make', 'verify': 'verify'}
    argv = list(sys.argv)
    for i in (1, 2):
        if i < len(argv):
            argv[i] = ALIAS_VERB.get(argv[i], ALIAS_WORD.get(argv[i], argv[i]))
    sys.argv = argv

    verb = sys.argv[1]
    rest = sys.argv[2:]

    if verb == '查':
        ap = argparse.ArgumentParser(prog='流程.py 查')
        ap.add_argument('阶段', choices=STAGES)
        ap.add_argument('--版本', '--version-dir', dest='版本')
        ap.add_argument('--对标库', '--repo', dest='对标库')
        ap.add_argument('--视频', '--video', dest='视频')
        ap.add_argument('--基准', '--baseline', dest='基准')
        ap.add_argument('--总长', '--total', dest='总长', type=float)
        ap.add_argument('--起', '--end-start', dest='起', type=float)
        ap.add_argument('--对标', '--ref', dest='对标')
        ap.add_argument('--对标起', '--ref-end-start', dest='对标起', type=float)
        return do_check(ap.parse_args(rest))

    if verb == '看':
        ap = argparse.ArgumentParser(prog='流程.py 看')
        ap.add_argument('图', choices=['环节', '四层', '对比'])
        ap.add_argument('--标题', dest='标题')
        ap.add_argument('--模式', dest='模式', choices=['name', 'seq'])
        ap.add_argument('--对标工序', dest='对标工序')
        ap.add_argument('--我们工序', dest='我们工序')
        ap.add_argument('--对标景别', dest='对标景别')
        ap.add_argument('--我们景别', dest='我们景别')
        ap.add_argument('--对标', dest='对标')
        ap.add_argument('--视频', dest='视频')
        ap.add_argument('--头', dest='头')
        ap.add_argument('--段', dest='段')
        ap.add_argument('--单元', dest='单元')
        ap.add_argument('--起', dest='起')
        ap.add_argument('--对标起', dest='对标起')
        ap.add_argument('--出', dest='出')
        return do_show(ap.parse_args(rest))

    if verb == '抽':
        ap = argparse.ArgumentParser(prog='流程.py 抽')
        ap.add_argument('动作', choices=['make', 'verify'])
        ap.add_argument('--files', dest='文件')
        ap.add_argument('--k', dest='数量', type=int, default=6)
        ap.add_argument('--out', dest='出')
        ap.add_argument('--sheet', dest='单')
        ap.add_argument('--answer', dest='答')
        a = ap.parse_args(rest)
        if a.动作 == 'make' and not a.文件:
            print('抽 make 需要 --files')
            return 2
        if a.动作 == 'verify' and (not a.单 or not a.答):
            print('抽 verify 需要 --sheet 和 --answer')
            return 2
        return do_sample(a)

    print(f'不认识的动词：{verb}（可用：说明 / 查 / 看 / 抽）')
    return 2


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(2)
