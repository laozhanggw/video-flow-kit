# -*- coding: utf-8 -*-
"""分发自检：包内文件闭环、可迁移路径、运行环境。历史材料不冒充执行依赖。"""
import argparse
import ast
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ("benchmark-select-and-breakdown", "benchmark-video-deconstruction", "benchmark-batch-variants",
          "benchmark-adapt-hook", "full-storyboard-design", "adaptive-video-production")
SCRIPTS = ("Pipeline.py", "体检.py", "抽查.py", "检查_拆解.py", "检查_开头.py", "检查_交付物.py",
           "检查_动作预算.py", "检查_三段.py", "检查_结尾.py", "检查_动作来源.py", "看板_环节.py",
           "看板_四层.py", "看板_对比.py", "检查_导图同步.py", "pipeline_runtime.py", "检查_提示词.py",
           "检查_口径一致.py", "生成流程导图.py", "设置本机路径.py", "自检引用.py")
AUTHOR_TOOLS = re.compile(r"[A-Za-z]:[/\\]+智线出海内容运营[/\\]+09 工具", re.I)
AUTHOR_PROJECTS = re.compile(r"[A-Za-z]:[/\\]+智线出海内容运营[/\\]+13_内容复盘[/\\]+YouTube[/\\]+我的频道全套数据[/\\]+06_制作对话与决策", re.I)
EXTERNAL = re.compile(r"(?:[A-Za-z]:[/\\]|\\\\[0-9])")
LINK = re.compile(r"(?<!!)\[[^\]\n]+\]\(([^)\n]+)\)")
SKIP_PARTS = ("_配置备份", "_原始备份", "_项目", "对标库", "__pycache__", ".git", ".venv", "venv", ".env", "node_modules")


def text_files():
    for folder, dirs, files in os.walk(ROOT):
        # 剪枝而不只是忽略输出；自定义虚拟环境通过pyvenv.cfg识别。
        dirs[:] = [name for name in dirs if name not in SKIP_PARTS
                   and "backup" not in name.lower() and "备份" not in name
                   and not (Path(folder) / name / "pyvenv.cfg").is_file()
                   and not (Path(folder) / name).is_symlink()]
        for name in files:
            path = Path(folder) / name
            if path.suffix in (".md", ".txt", ".py", ".html") and not path.is_symlink():
                yield path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--preconfigure", action="store_true", help="配置前允许ROOT占位符")
    ap.add_argument("--structure-only", action="store_true", help="只查打包结构，不判运行环境就绪")
    ap.add_argument("--media", action="store_true", help="强制要求 ffmpeg 与 ffprobe")
    ap.add_argument("--partial-release", action="store_true", help="只验证显式部分发布中的现有文件；仅可配合--structure-only，不代表套件就绪")
    args = ap.parse_args()
    if args.partial_release and (not args.structure_only or args.media):
        ap.error("--partial-release 仅允许用于--structure-only结构核对")
    fails, warnings = [], []
    deferred = set()
    manifest_path = ROOT / "tools" / "套件清单.json"
    required = {"指令/%s" % s for s in ("1_拆解.txt", "2_复刻.txt", "3_开头.txt", "4_小分镜.txt", "5_生产单元.txt")}
    required.update("skills/%s/SKILL.md" % s for s in SKILLS)
    required.update("tools/" + s for s in SCRIPTS)
    required.update(("19_工序词表.md", "流程导图.html", "65_上岗手册_对话版_20261029.html", "tools/套件清单.json"))
    manifest = {}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("format_version") != 1 or not isinstance(manifest.get("required_files"), list) or not manifest["required_files"]:
            raise ValueError("清单格式或必需文件列表不正确")
        for item in manifest["required_files"]:
            if not isinstance(item, str) or Path(item).is_absolute() or ".." in Path(item).parts or "\\" in item or ":" in item:
                raise ValueError("清单含越界文件名")
            required.add(item)
    except (OSError, ValueError, TypeError) as e:
        fails.append("套件清单不可用：%s" % e)
    if not args.partial_release and manifest.get("release_status") == "partial":
        fails.append("本包仍标注部分发布：手动补文件后还需正式转换、重建清单和完整核验，不自动视为就绪")
    if args.partial_release:
        if manifest.get("release_status") != "partial":
            fails.append("只有显式标注partial的清单可做部分发布核对")
        for item in manifest.get("deferred_files", []):
            name = item.get("target", "") if isinstance(item, dict) else ""
            if name not in {"tools/" + script for script in SCRIPTS}:
                fails.append("待补清单含非生产工具或非法路径：" + str(name))
            else:
                deferred.add(name)
        if not deferred:
            fails.append("部分发布缺少明确待补清单")
    for name in sorted(required):
        if not (ROOT / name).is_file():
            (warnings if name in deferred else fails).append("缺必需文件：" + name)
    for name in ("指令", "skills", "模板", "对标库", "_项目", "tools"):
        if not (ROOT / name).is_dir():
            fails.append("缺目录：" + name)
    deps = manifest.get("script_dependencies", {})
    if not isinstance(deps, dict):
        fails.append("script_dependencies 必须是字典")
        deps = {}
    for caller, children in deps.items():
        if not isinstance(children, list):
            fails.append("脚本依赖不是列表：" + str(caller))
            continue
        for child in children:
            rel = child if child.startswith("tools/") else "tools/" + child
            if not (ROOT / rel).is_file():
                (warnings if rel in deferred else fails).append("传递依赖缺失：%s -> %s" % (caller, rel))
    history = set(manifest.get("historical_root_documents", []))
    checked_script_refs = set()
    for path in text_files():
        rel = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8-sig")
        active = rel.startswith(("指令/", "skills/", "模板/")) and "/examples/" not in rel and "来源" not in path.name
        # 历史案例绝不当必需依赖，活指令/工具引用则不允许借用作者磁盘。
        if path.suffix == ".py":
            try:
                tree = ast.parse(text, filename=rel)
            except SyntaxError as e:
                fails.append("Python语法错误：%s:%s %s" % (rel, e.lineno, e.msg))
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and re.fullmatch(r"[^/\\\s]+\.py", node.value):
                    if not (ROOT / "tools" / node.value).is_file():
                        (warnings if "tools/" + node.value in deferred else fails).append("源码中引用的工具未入包：%s -> %s" % (rel, node.value))
            if path.name not in ("自检引用.py",):
                compatibility_nodes = set()
                if path.name == "生成流程导图.py":
                    for function in tree.body:
                        if isinstance(function, ast.FunctionDef) and function.name == "distribution_nodes":
                            compatibility_nodes.update(id(n) for n in ast.walk(function))
                for node in ast.walk(tree):
                    if id(node) not in compatibility_nodes and isinstance(node, ast.Constant) and isinstance(node.value, str) and AUTHOR_TOOLS.search(node.value):
                        fails.append("脚本仍写死作者工具路径：%s:%s" % (rel, node.lineno))
                        break
        elif active and AUTHOR_TOOLS.search(text):
            fails.append("活文件仍引用作者工具目录：" + rel)
        if active and AUTHOR_PROJECTS.search(text):
            fails.append("活文件仍引用作者项目根：" + rel)
        if active and not args.preconfigure and "{{ROOT}}" in text:
            fails.append("未配置ROOT：" + rel)
        if active:
            for tool in re.findall(r"(?:tools|09 工具)[/\\]+([^/\\\s\"'`<>，。；：|()（）]+\.(?:py|bat|cmd))", text):
                key = (rel, tool)
                if key not in checked_script_refs and not (ROOT / "tools" / tool).is_file():
                    (warnings if "tools/" + tool in deferred else fails).append("活文件引用工具未入包：%s -> %s" % (rel, tool))
                checked_script_refs.add(key)
        if path.suffix == ".md":
            for target in LINK.findall(text):
                target = target.strip().split(" \"")[0].split("#")[0]
                if not target or "://" in target or target.startswith(("mailto:", "#")) or EXTERNAL.search(target) or "<" in target:
                    continue
                from urllib.parse import unquote
                target = target.replace("{{ROOT}}", ROOT.as_posix())
                dest = (path.parent / unquote(target.replace("\\", "/"))).resolve()
                if not dest.is_file() and not dest.is_dir():
                    msg = "本地链接缺失：%s -> %s" % (rel, target)
                    if rel in history or "/examples/" in rel or "来源" in path.name:
                        warnings.append(msg + "（历史资料）")
                    else:
                        fails.append(msg)
        # 外部来源只计提示；作者执行工具路径另有硬检查，不能借 exists() 蒙混。
        if path.suffix == ".md" and EXTERNAL.search(text) and not rel.startswith("指令/"):
            warnings.append("保留历史来源/示例路径：" + rel + "；不表示收件人可回读")
    if not args.structure_only:
        if sys.version_info < (3, 10):
            fails.append("需要 Python 3.10+")
        if importlib.util.find_spec("PIL") is None:
            fails.append("缺 Pillow；请在本机虚拟环境安装 Pillow 后用该环境Python重跑")
        elif (ROOT / "tools" / "pipeline_runtime.py").is_file():
            try:
                import pipeline_runtime
                pipeline_runtime.get_font(18)
                pipeline_runtime.get_font(18, bold=True)
            except Exception as e:
                fails.append("中文字体不可用：%s" % e)
        missing_media = [name for name in ("ffmpeg", "ffprobe") if shutil.which(name) is None]
        if missing_media:
            msg = "缺媒体工具：%s；成片验收不能记为通过" % ", ".join(missing_media)
            (fails if args.media else warnings).append(msg)
    for msg in dict.fromkeys(warnings):
        print("[提示]", msg)
    for msg in dict.fromkeys(fails):
        print("[FAIL]", msg)
    print("已核对 %d 个必需文件、%d 组脚本依赖。" % (len(required), len(deps)))
    if fails:
        print("[未就绪] %d 项错误。" % len(set(fails)))
        return 1
    if args.partial_release:
        print("[部分更新现有文件核对通过] 仍有%d个待补工具；完整自检、配置与生产未通过。" % len(deferred))
    elif args.structure_only:
        print("[结构通过] 未检查运行环境；不等于可以运行生产。")
    elif args.preconfigure:
        print("[配置前检查通过] 尚未配置本机路径。")
    else:
        print("[基础环境通过] 不代表项目内容验收或生成效果已通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
