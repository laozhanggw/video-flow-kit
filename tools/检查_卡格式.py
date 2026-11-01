#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""检查_卡格式.py —— 导入前只读检查卡的格式（不花积分、不改任何文件）

为什么要有这个脚本（2026-11-01）：
    B0018 V02_front_steps 的三条单元卡把「（已有）」写在参考图路径尾巴上，
    程序把它们判成"素材没到位"静默跳过，界面上只显示"完成"，少跑 37 秒。
    这类错误不会报错，只能靠机器扫。

用法：
    python 检查_卡格式.py <项目文件夹>
    python 检查_卡格式.py <项目文件夹> --strict     # 警告也算失败
    python 检查_卡格式.py <项目文件夹> --quiet      # 只打印问题

退出码：
    0 = 通过（无 FAIL）    1 = 有 FAIL    2 = 路径不对/不是项目文件夹
"""
import argparse
import io
import re
import sys
from pathlib import Path

IMAGE_EXT = ('.png', '.jpg', '.jpeg', '.webp')
UNIT_DIR = '单元'
CARD_FILE = '共用卡制卡词.md'
HEAD_LIMIT = 15
MAX_REFS = 4
PROMPT_ALIASES = ('拼好的完整正文', '完整正文', '最终提示词', '最终正文',
                  '提示词正文', '提交用提示词', '可直接提交的正文', '视频提示词')
FENCE_LANGS = {'', 'text', 'txt', 'plain', 'plaintext', 'prompt', 'markdown', 'md'}
PAREN = re.compile(r'\s*[（(].*?[）)]\s*')
TRAILING_NOTE = re.compile(r'\s*[（(][^（）()]{1,24}[）)]\s*$')
EXISTING_MARK = re.compile(
    r'已有文件|已有成品|已有图|已有素材|不重新出图|不重出图|不重新生成|不重生成|不重制|跳过生成|沿用已有')
CARD_HEAD_H2 = re.compile(r'^##\s+([A-Za-z][A-Za-z0-9_\-]*)')
CARD_HEAD_H3 = re.compile(r'^###\s+([A-Za-z][A-Za-z0-9_\-]*)\s*(?:[｜|·:：]|\s)')
SHOT_RE = re.compile(r'【\s*镜头\s*(\d+)\s*[｜|]\s*([\d.]+)\s*秒\s*[｜|]\s*([^｜|\]】]+)')
GEN_RE = re.compile(r'\s*(\d+(?:\.\d+)?)\s*秒')
ORDER_RE = re.compile(r'\s*(\d+)\s+.+?=\s*(.+?)\s*$')
VER_RE = re.compile(r'^v\d+$')

FAIL, WARN, OK = 'FAIL', 'WARN', 'OK'


class Report(object):
    def __init__(self):
        self.items = []

    def add(self, level, where, msg):
        self.items.append((level, where, msg))

    def fail(self, where, msg):
        self.add(FAIL, where, msg)

    def warn(self, where, msg):
        self.add(WARN, where, msg)

    def ok(self, where, msg):
        self.add(OK, where, msg)

    @property
    def fails(self):
        return [x for x in self.items if x[0] == FAIL]

    @property
    def warns(self):
        return [x for x in self.items if x[0] == WARN]


def read_lines(p):
    return p.read_text(encoding='utf-8-sig').splitlines()


def fence_blocks(lines, start, end):
    out, i = [], max(0, start)
    while i < end:
        s = lines[i].strip()
        if not s.startswith('```'):
            i += 1
            continue
        lang = s[3:].strip().lower()
        j = i + 1
        while j < end and not lines[j].strip().startswith('```'):
            j += 1
        out.append((lang, '\n'.join(lines[i + 1:j]).strip('\n'), i))
        i = j + 1
    return out


def head_value(head, key):
    """单个值：取到下一个 ｜ 为止（和导入器一致，用于 本卡版本/生产状态/输出文件名）。"""
    for x in head:
        if not x.startswith('>'):
            continue
        m = re.search(re.escape(key) + r'\s*[:：]\s*([^｜|\n]*)', x)
        if m:
            return m.group(1).strip()
    return None


def head_line(head, key):
    """整行剩余：生成、上传顺序 本身就是 ｜ 分隔的多段，不能被第一个 ｜ 截断。"""
    for x in head:
        if not x.startswith('>'):
            continue
        m = re.search(re.escape(key) + r'\s*[:：]\s*(.+)$', x)
        if m:
            return m.group(1).strip()
    return None


def md_field(lines, names):
    for line in lines:
        s = line.strip().lstrip('>').strip().strip('*').strip()
        m = re.match(r'^([^：:]{1,12})\s*[：:]\s*(.+)$', s)
        if m and m.group(1).strip() in names:
            return m.group(2).strip()
        t = s.strip('|')
        if '|' in t:
            cells = [c.strip() for c in t.split('|')]
            if len(cells) >= 2 and cells[0].strip('* ') in names:
                return cells[1]
    return None


def split_refs(raw):
    """父图/上传顺序的原始值 -> 路径列表（保持上传顺序）。"""
    out = []
    if not raw:
        return out
    for part in re.split(r'[｜|]', raw):
        part = part.strip()
        if not part:
            continue
        if '=' in part:
            part = part.split('=', 1)[1]
        out.append(part.strip().strip('`"'))
    return out


def norm_rel(p):
    return str(p).replace('/', '\\').strip()


def strip_prefix(p):
    return re.sub(r'^项目文件夹[\\/]?', '', norm_rel(p))


def looks_image(p):
    return norm_rel(p).casefold().endswith(IMAGE_EXT)


def resolve_ref(project, raw, upstream):
    """返回 (状态, 绝对路径)。状态：exists / upstream / missing / bad_ext"""
    rel = strip_prefix(raw)
    p = project / rel
    if not looks_image(rel):
        return 'bad_ext', p
    if p.is_file():
        return 'exists', p
    name = Path(rel).name
    if name in upstream:
        return 'upstream', p
    return 'missing', p


def check_units(project, rep, upstream):
    d = project / UNIT_DIR
    if not d.is_dir():
        rep.fail('项目', '没有 %s 文件夹' % UNIT_DIR)
        return
    files = sorted(d.glob('*.md'))
    if not files:
        rep.fail(UNIT_DIR, '一条视频卡都没有')
        return
    for f in files:
        where = '%s\\%s' % (UNIT_DIR, f.name)
        if not re.fullmatch(r'[A-Za-z0-9_\-]+', f.stem):
            rep.warn(where, '文件名不能当任务编号（只能字母数字下划线连字符）；'
                            '这条不会导入，也不会花钱，建议移到 说明\\')
            continue
        if not f.stem.upper().startswith('U'):
            rep.warn(where, '不是 U 开头的视频卡；说明文件请放 说明\\（否则每次导入多一条「不导入」）')
        lines = read_lines(f)
        head = [x for x in lines[:HEAD_LIMIT] if x.startswith('>')]

        # 1) 五个头部字段（缺一个报一条，不中断，好让 AI 一轮改完）
        need = ['本卡版本', '生产状态', '生成', '上传顺序', '输出文件名']
        for k in need:
            if not head_value(head, k):
                rep.fail(where, '头部缺字段「%s」（必须在前 %d 行内、以 > 开头）' % (k, HEAD_LIMIT))
        ver = (head_value(head, '本卡版本') or '').strip().lower()
        if ver and not VER_RE.match(ver):
            rep.fail(where, '本卡版本 "%s" 不是 v01 这种写法' % ver)
        out_name = head_value(head, '输出文件名')
        if out_name:
            want = r'%s_v\d+\.mp4' % re.escape(f.stem)
            if not re.fullmatch(want, out_name):
                rep.warn(where, '输出文件名 %s 与卡编号/版本不一致（建议 %s_%s.mp4）'
                         % (out_name, f.stem, ver or 'v01'))
            elif ver and out_name != '%s_%s.mp4' % (f.stem, ver):
                rep.warn(where, '输出文件名 %s 与 本卡版本 %s 不一致' % (out_name, ver))

        # 2) 生成
        gen = head_line(head, '生成')
        gm = GEN_RE.match(gen or '')
        seconds = None
        if not gen:
            pass  # 上面已报缺字段
        elif not gm:
            rep.fail(where, '生成 "%s" 开头不是「数字 秒」（不许写"约"）' % gen)
        else:
            seconds = float(gm.group(1))
            if seconds != int(seconds):
                rep.warn(where, '生成写了 %g 秒，网页只认整秒，会被向上取整' % seconds)
        params = [x.strip() for x in re.split(r'[｜|]', gen or '')[1:]]
        has_model = any(re.search(r'[A-Za-z]', x) for x in params)
        has_ratio = any(re.fullmatch(r'\d+:\d+', x) for x in params)
        if gen and not has_model:
            rep.warn(where, '生成里没有模型名，会退回默认模型')
        if gen and not has_ratio:
            rep.warn(where, '生成里没有比例（如 9:16），会退回默认 9:16')

        # 3) 上传顺序
        order = head_line(head, '上传顺序')
        refs = split_refs(order)
        if order and not refs:
            rep.fail(where, '上传顺序读不出任何参考图')
        if len(refs) > MAX_REFS:
            rep.fail(where, '参考图 %d 张，超过上限 %d 张' % (len(refs), MAX_REFS))
        nums = []
        for part in re.split(r'[｜|]', order or ''):
            if not part.strip():
                continue
            m = ORDER_RE.match(part)
            if not m:
                rep.fail(where, '上传顺序这段拆不开：%s（要写成 "1 名称 = 路径"）' % part.strip()[:40])
            else:
                nums.append(int(m.group(1)))
        if nums and nums != list(range(1, len(nums) + 1)):
            rep.fail(where, '上传顺序编号不连续：%s' % nums)
        # 换行检测：下一行以 "> 数字 名称 =" 开头，就是上传顺序被拆成了两行
        for i, line in enumerate(lines[:HEAD_LIMIT]):
            if '上传顺序' in line and line.startswith('>'):
                nxt = lines[i + 1].strip() if i + 1 < len(lines) else ''
                if re.match(r'^>\s*\d+\s+\S+\s*=', nxt):
                    rep.fail(where, '上传顺序换行了（第 %d 行还在继续）：必须整行写完，'
                                    '否则程序只读到前半截' % (i + 2))
                break

        for raw in refs:
            if PAREN.search(Path(norm_rel(raw)).name) and not looks_image(raw):
                rep.fail(where, '参考图路径尾巴带括号注解：%s' % Path(norm_rel(raw)).name)
                continue
            state, p = resolve_ref(project, raw, upstream)
            if state == 'bad_ext':
                rep.fail(where, '参考图不是图片文件名（生产时会一直等它）：%s' % p.name)
            elif state == 'missing':
                rep.fail(where, '参考图既不存在、也不是本项目任何卡的输出：%s' % norm_rel(raw))
            elif state == 'upstream':
                rep.ok(where, '依赖上游：%s' % p.name)

        # 4) 提示词块
        hits = [n for n, x in enumerate(lines) if any(a in x for a in PROMPT_ALIASES)]
        start = next((n for n in hits if lines[n].lstrip().startswith(('#', '**'))),
                     hits[0] if hits else None)
        if start is None:
            rep.fail(where, '找不到「## 拼好的完整正文」')
            continue
        end = len(lines)
        for n in range(start + 1, len(lines)):
            if re.match(r'^##\s', lines[n]):
                end = n
                break
        blocks = [b for b in fence_blocks(lines, start, end) if b[0] in FENCE_LANGS and b[1]]
        if not blocks:
            rep.fail(where, '「拼好的完整正文」下面没有代码块')
            continue
        if len(blocks) > 1:
            rep.warn(where, '这一节有 %d 个提示词类代码块，程序只取第一个' % len(blocks))
        body = blocks[0][1]
        if '{{' in body or '}}' in body:
            rep.fail(where, '提示词里还有 {{占位}}')
        for bad in ('同上', '见上文', '待补', '参考之前版本'):
            if bad in body:
                rep.warn(where, '提示词里出现「%s」，程序会原样提交' % bad)

        # 5) 第 N 张 vs 实际张数
        used = [int(x) for x in re.findall(r'第\s*(\d+)\s*张', body)]
        if used and max(used) > len(refs):
            rep.fail(where, '正文写到「第 %d 张」，但上传顺序只有 %d 张' % (max(used), len(refs)))

        # 6) 镜头时长之和
        shots = SHOT_RE.findall(body)
        if shots and seconds:
            total = sum(float(s[1]) for s in shots)
            if abs(total - seconds) > 0.15:
                rep.fail(where, '镜头时长之和 %.1f 秒 ≠ 生成 %g 秒（差 %.1f 秒，模型会自己编）'
                         % (total, seconds, total - seconds))
            sizes = [s[2].strip() for s in shots]
            for i in range(1, len(sizes)):
                if sizes[i] == sizes[i - 1]:
                    rep.warn(where, '镜头%d 与镜头%d 景别相同（%s），观众看不见这个切'
                             % (i, i + 1, sizes[i]))
            if seconds and total > 0 and not any('硬切' in body for _ in [0]) and len(shots) > 1:
                rep.warn(where, '有 %d 个镜头但没写「⚠️硬切」提示' % len(shots))


def check_cards(project, rep):
    f = project / CARD_FILE
    if not f.is_file():
        rep.warn('项目', '没有 %s（这个项目不生成图？）' % CARD_FILE)
        return set()
    lines = read_lines(f)
    heads = []
    for n, x in enumerate(lines):
        m = CARD_HEAD_H2.match(x) or CARD_HEAD_H3.match(x)
        if m:
            heads.append((n, m.group(1)))
    if not heads:
        rep.fail(CARD_FILE, '一张 RC 卡都没读到（标题要写 ## RC01｜名称）')
        return set()
    outputs = set()
    seen = {}
    for k, (start, code) in enumerate(heads):
        end = heads[k + 1][0] if k + 1 < len(heads) else len(lines)
        sec = lines[start:end]
        where = '%s 第%d行 %s' % (CARD_FILE, start + 1, code)
        if code in seen:
            rep.fail(where, '编号重复（第%d行已有 %s）' % (seen[code], code))
        seen[code] = start + 1
        state = md_field(sec, ('生产状态', '状态'))
        parent = md_field(sec, ('父图', '参考图', '父图与参考图', '参考图与父图', '要上传几张'))
        output = md_field(sec, ('输出', '输出文件', '输出文件名'))
        if not output:
            rep.fail(where, '缺「输出：」')
            continue
        if parent is None:
            rep.fail(where, '缺「父图：」（纯文字生图要写 父图：无）')
        parts = [x.strip() for x in re.split(r'[｜|]', output)]
        name = Path(norm_rel(parts[0])).name
        if not re.fullmatch(r'%s_.+_v\d+\.png' % re.escape(code), name):
            rep.fail(where, '输出文件名 %s 应为 %s_名称_v01.png' % (name, code))
        if not norm_rel(parts[0]).startswith('生成\\'):
            rep.warn(where, '输出路径不在 生成\\ 下：%s' % parts[0])
        outputs.add(name)
        if PAREN.search(name):
            rep.fail(where, '输出文件名里有括号，程序会删掉括号内容')
        if parent and parent.strip().strip('。.') not in ('无', '没有', '不需要', '不用', 'none', '-', '—', '/'):
            refs = split_refs(parent)
            if len(refs) > MAX_REFS:
                rep.fail(where, '父图 %d 张，超过上限 %d 张' % (len(refs), MAX_REFS))
            for raw in refs:
                if PAREN.search(Path(norm_rel(raw)).name):
                    rep.fail(where, '父图文件名里有括号（会被整段删掉）：%s'
                             % Path(norm_rel(raw)).name)
                rel = strip_prefix(raw)
                if not looks_image(rel):
                    rep.fail(where, '父图不是图片文件名：%s' % rel)
                elif not (project / rel).is_file() and Path(rel).name not in outputs:
                    rep.warn(where, '父图还不存在（若它是本项目要生成的图，会在生产时等上游）：%s'
                             % Path(rel).name)
        blocks = [b for b in fence_blocks(lines, start, end) if b[0] in FENCE_LANGS and b[1]]
        existing = EXISTING_MARK.search(output) or EXISTING_MARK.search(parent or '')
        if not blocks:
            if existing:
                rep.ok(where, '已有成品卡，无制卡词（不生成，正常）')
            else:
                rep.fail(where, '缺 ```text 制卡词')
        else:
            if '{{' in blocks[0][1]:
                rep.fail(where, '制卡词里还有 {{占位}}')
            if len(blocks) > 1:
                rep.warn(where, '这一节有 %d 个代码块，程序只取第一个' % len(blocks))
    return outputs


def main():
    ap = argparse.ArgumentParser(description='导入前只读检查卡格式')
    ap.add_argument('project', help='项目文件夹')
    ap.add_argument('--strict', action='store_true', help='警告也算失败')
    ap.add_argument('--quiet', action='store_true', help='只打印问题')
    args = ap.parse_args()

    project = Path(args.project)
    if not project.is_dir():
        print('不是文件夹：%s' % project)
        return 2
    if not (project / UNIT_DIR).is_dir() and not (project / CARD_FILE).is_file():
        print('这里既没有 %s 也没有 %s，不是项目文件夹：%s' % (UNIT_DIR, CARD_FILE, project))
        return 2

    rep = Report()
    outputs = check_cards(project, rep)
    check_units(project, rep, outputs)

    for level, where, msg in rep.items:
        if level == OK and args.quiet:
            continue
        print('[%s] %s：%s' % (level, where, msg))

    n_fail, n_warn = len(rep.fails), len(rep.warns)
    print('-' * 60)
    print('项目：%s' % project)
    print('图片卡输出：%d 个｜失败 %d 条｜警告 %d 条' % (len(outputs), n_fail, n_warn))
    if n_fail == 0 and (n_warn == 0 or not args.strict):
        print('结论：通过')
        return 0
    print('结论：%s' % ('有 FAIL，先改卡再导入' if n_fail else '只有警告（--strict 下算失败）'))
    return 1


if __name__ == '__main__':
    sys.exit(main())
