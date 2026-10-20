#!/usr/bin/env python3
"""泄密哨兵 CLI：扫描公开仓库的受保护范围，报告 PII 与本机路径。

规则外置在同目录 privacy_rules.json：检测模式（正则）、保护范围、
封禁子串均可扩展，无需改代码。

用法：
    python scripts/privacy_scan.py                 # 扫描当前目录
    python scripts/privacy_scan.py --root ..       # 指定仓库根
    python scripts/privacy_scan.py --format json   # CI 友好输出

退出码：0 干净；1 发现违规；2 规则文件或根目录缺失。

说明：tests/fixtures 与测试代码里故意包含虚构 PII 用于哨兵自测，
因此 tests/ 不在保护范围内。
"""

import argparse
import json
import re
import sys
from pathlib import Path

DEFAULT_RULES = Path(__file__).with_name("privacy_rules.json")


def load_rules(path=DEFAULT_RULES):
    """读规则 JSON → (原始 dict, 编译后的模式列表)。"""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    patterns = []
    for p in raw["patterns"]:
        patterns.append({
            "id": p["id"],
            "name": p["name"],
            "severity": p.get("severity", "high"),
            "re": re.compile(p["regex"]),
        })
    return raw, patterns


def iter_guarded(root, raw):
    """按规则枚举受保护文件（去重后排序，保证扫描顺序稳定）。"""
    seen = set()
    for dirname, globs in raw["guarded"]["dirs"].items():
        d = Path(root) / dirname
        if not d.is_dir():
            continue
        for g in ([globs] if isinstance(globs, str) else globs):
            for f in d.rglob(g):
                if f.is_file():
                    seen.add(f.resolve())
    for g in raw["guarded"].get("root_globs", []):
        for f in Path(root).glob(g):
            if f.is_file():
                seen.add(f.resolve())
    return sorted(seen)


def scan_file(path, patterns, blocked=()):
    """扫描单文件 → 违规列表。每行每模式至多报一次。"""
    violations = []
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return violations
    for i, line in enumerate(text.splitlines(), 1):
        for p in patterns:
            m = p["re"].search(line)
            if m:
                violations.append({
                    "file": str(path), "line": i, "pattern": p["name"],
                    "id": p["id"], "severity": p["severity"],
                    "match": m.group(0),
                })
        for s in blocked:
            if s and s in line:
                violations.append({
                    "file": str(path), "line": i, "pattern": "封禁子串",
                    "id": "blocked:%s" % s, "severity": "medium",
                    "match": s,
                })
    return violations


def scan_repo(root, raw=None, patterns=None):
    """扫描整个仓库受保护范围 → 报告 dict。"""
    if raw is None or patterns is None:
        raw, patterns = load_rules()
    blocked = raw.get("blocked_strings", [])
    files = iter_guarded(root, raw)
    violations = []
    for f in files:
        violations.extend(scan_file(f, patterns, blocked))
    return {"root": str(root), "scanned_files": len(files),
            "violations": violations}


def render_text(report):
    lines = ["泄密哨兵扫描报告",
             "  范围   : %s" % report["root"],
             "  扫描量 : %d 个文件" % report["scanned_files"]]
    vs = report["violations"]
    if not vs:
        lines.append("  违规   : 0 ✓ 干净，可以提交")
    else:
        lines.append("  违规   : %d" % len(vs))
        for v in vs:
            lines.append("  [%s] %s 第 %d 行命中%s：%s"
                         % (v["severity"], v["file"], v["line"],
                            v["pattern"], v["match"]))
    return "\n".join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(description="泄密哨兵：PII/本机路径扫描")
    p.add_argument("--root", default=".", help="仓库根目录（默认当前目录）")
    p.add_argument("--rules", default=str(DEFAULT_RULES), help="规则 JSON 路径")
    p.add_argument("--format", choices=("text", "json"), default="text")
    args = p.parse_args(argv)

    root = Path(args.root)
    if not root.is_dir():
        print("根目录不存在: %s" % root, file=sys.stderr)
        return 2
    try:
        raw, patterns = load_rules(args.rules)
    except (OSError, ValueError, KeyError) as e:
        print("规则文件加载失败: %s" % e, file=sys.stderr)
        return 2

    report = scan_repo(root, raw, patterns)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_text(report))
    return 1 if report["violations"] else 0


if __name__ == "__main__":
    sys.exit(main())
