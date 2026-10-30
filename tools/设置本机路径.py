# -*- coding: utf-8 -*-
"""配置当前套件；搬家后重跑。不从旧备份恢复，不安装软件，不上传。"""
import argparse
import datetime
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / ".路径配置.json"


def targets():
    files = [p for p in ROOT.iterdir() if p.is_file() and p.suffix in (".md", ".txt", ".html")
             and p.name not in ("流程导图.html", "index.html")]
    for name in ("指令", "skills", "模板"):
        base = ROOT / name
        if base.is_dir():
            files.extend(p for p in base.rglob("*") if p.is_file() and p.suffix in (".md", ".txt", ".html")
                         and not any("backup" in x.lower() or "备份" in x or x == "__pycache__" for x in p.relative_to(base).parts))
    return sorted(set(files))


def run_tool(name, *args):
    p = ROOT / "tools" / name
    if not p.is_file():
        print("[错误] 缺工具：", p)
        return 2
    result = subprocess.run([sys.executable, str(p), *args], cwd=ROOT)
    return result.returncode


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--media", action="store_true", help="同时强制检查 ffmpeg/ffprobe")
    args = ap.parse_args()
    if sys.version_info < (3, 10):
        print("[错误] 需要 Python 3.10 或以上。")
        return 2
    print("套件位置：", ROOT, flush=True)
    extra = ["--media"] if args.media else []
    # 先查依赖；失败不改文件，也不声称就绪。
    if run_tool("自检引用.py", "--preconfigure", *extra):
        print("[未就绪] 先解决以上缺项，再重新运行配置。")
        return 2
    previous = None
    if STATE.exists():
        try:
            previous = json.loads(STATE.read_text(encoding="utf-8"))["root"]
            if not isinstance(previous, str) or not Path(previous).is_absolute():
                raise ValueError("root 必须是绝对路径")
        except (ValueError, KeyError, OSError) as e:
            print("[错误] 路径状态损坏，停止以免覆盖编辑：", e)
            return 2
    current = ROOT.as_posix()
    changes = []
    for path in targets():
        text = path.read_text(encoding="utf-8-sig")
        new = text
        if previous and previous != current:
            # 最长先替换；只换已记录套件根，不碰其它项目绝对路径。
            variants = {previous, previous.replace("\\", "/"), previous.replace("/", "\\")}
            for old in sorted(variants, key=len, reverse=True):
                # 只替换完整路径前缀；suite-other 不能被当成 suite 的内容。
                pattern = re.escape(old) + r"(?=$|[/\\\s\"'`<>，。；：|()（）\]、])"
                new = re.sub(pattern, lambda match: current, new, flags=re.I)
        new = new.replace("{{ROOT}}", current)
        if new != text:
            changes.append((path, new))
    if changes:
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup = ROOT / "_配置备份" / stamp
        # 先全部备份，任何失败均不进入修改阶段。
        for path, _ in changes:
            dest = backup / path.relative_to(ROOT)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
        print("本次改动前备份：", backup)
        for path, text in changes:
            path.write_text(text, encoding="utf-8", newline="\n")
    STATE.write_text(json.dumps({"format_version": 1, "root": current}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("已更新 %d 个当前文件；未从旧备份还原。" % len(changes), flush=True)
    for name, tool_args in (("生成流程导图.py", []), ("检查_导图同步.py", ["--dir", str(ROOT)]),
                            ("自检引用.py", extra)):
        if run_tool(name, *tool_args):
            print("[未就绪] %s 未通过；修复后重跑，不算配置成功。" % name)
            return 2
    print("[基础环境已就绪] 可以开始项目；这不是项目内容验收，也不是生成效果实测。")
    print("未使用 --media 时，成片媒体验收仍需 ffmpeg 与 ffprobe，不能记成已通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
