#!/usr/bin/env python3
"""投递漏斗统计：把 data/ 下的 Markdown 追踪表变成周报。

数据源（相对 --data-dir，默认 data/）：
    投递追踪.md            —— 每行一次投递
    话术库/已发送记录.md    —— 每行一段已发送话术（含 HR 回复列）

输出：每周投递量、状态分布、转化漏斗（投递→回复→面试→offer）、
匹配度分布、话术回复率。纯 stdlib，无外部依赖。

用法：
    python scripts/funnel_report.py
    python scripts/funnel_report.py --json
    python scripts/funnel_report.py --data-dir path/to/data

退出码：0 正常输出（空数据也算正常）；2 数据目录不存在。
"""

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d")

STATUS_RULES = [
    ("offer", ("offer", "录用", "入职")),
    ("面试", ("面试", "约面", "笔试")),
    ("已回复", ("回复", "已读", "沟通中", "感兴趣")),
    ("已投递", ("已投", "投递", "已发送", "待")),
    ("终止", ("拒", "不合适", "取消", "终止")),
]
BUCKET_ORDER = ["已投递", "已回复", "面试", "offer", "终止"]
FUNNEL_STAGES = ["已投递", "已回复", "面试", "offer"]


def parse_markdown_table(path):
    """解析 Markdown 表格 → [{列名: 值}, ...]。只取文件里第一张表。"""
    headers = None
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s.startswith("|"):
            if headers:
                break
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if cells and all(re.fullmatch(r"[-: ]*", c) for c in cells):
            continue
        if headers is None:
            headers = cells
        else:
            rows.append(dict(zip(headers, cells)))
    return rows


def parse_date(s):
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime((s or "").strip(), fmt).date()
        except ValueError:
            continue
    return None


def week_key(d):
    iso = d.isocalendar()
    return "%d-W%02d" % (iso[0], iso[1])


def normalize_status(s):
    """自由文本状态 → 五个标准桶：已投递/已回复/面试/offer/终止。"""
    t = (s or "").strip().lower()
    if not t:
        return "已投递"
    for bucket, keys in STATUS_RULES:
        if any(k in t for k in keys):
            return bucket
    return "已投递"


def build_stats(tracker_rows, sent_rows, missing):
    """从两张表的行数据聚合出周报所需的全部统计量。"""
    weeks = Counter()
    statuses = Counter()
    match = Counter()
    funnel = {stage: 0 for stage in FUNNEL_STAGES}
    unparsed_dates = 0

    for r in tracker_rows:
        d = parse_date(r.get("日期", ""))
        if d:
            weeks[week_key(d)] += 1
        else:
            unparsed_dates += 1
        statuses[normalize_status(r.get("状态", ""))] += 1
        m = (r.get("匹配度", "") or "").strip()
        if m:
            match["高" if m.startswith("高") else
                  "中" if m.startswith("中") else
                  "低" if m.startswith("低") else "其他"] += 1

    # 漏斗按阶段包含关系累计：offer 行同时计入 已回复/面试/已投递
    rank = {"已投递": 0, "已回复": 1, "面试": 2, "offer": 3}
    for bucket, n in statuses.items():
        if bucket == "终止":
            continue
        for stage in FUNNEL_STAGES:
            if rank.get(bucket, 0) >= rank[stage]:
                funnel[stage] += n

    replied_msgs = 0
    for r in sent_rows:
        hr = (r.get("HR 回复", "") or r.get("HR回复", "") or "").strip()
        if hr and hr not in ("无", "-", "—"):
            replied_msgs += 1

    return {
        "tracker": {
            "total": len(tracker_rows),
            "weeks": dict(sorted(weeks.items())),
            "statuses": {b: statuses.get(b, 0) for b in BUCKET_ORDER},
            "funnel": funnel,
            "match": dict(match),
            "unparsed_dates": unparsed_dates,
        },
        "sent": {"total": len(sent_rows), "hr_replied": replied_msgs},
        "missing_files": missing,
    }


def render_markdown(stats):
    tr = stats["tracker"]
    sent = stats["sent"]
    lines = ["# 投递漏斗周报", ""]
    if stats["missing_files"]:
        lines.append("> 缺数据文件：%s" % "、".join(stats["missing_files"]))
        lines.append("")
    if tr["total"] == 0:
        lines.append("暂无投递记录。先用 job-search 技能搜岗，投递后回填追踪表。")
        return "\n".join(lines) + "\n"

    lines.append("- 累计投递：%d 条" % tr["total"])
    if tr["unparsed_dates"]:
        lines.append("- ⚠ 无法解析日期：%d 条" % tr["unparsed_dates"])

    lines += ["", "## 每周投递", "", "| 周 | 投递数 |", "|---|---|"]
    for wk, n in tr["weeks"].items():
        lines.append("| %s | %d |" % (wk, n))

    lines += ["", "## 状态分布", "", "| 状态 | 条数 |", "|---|---|"]
    for b, n in tr["statuses"].items():
        if n:
            lines.append("| %s | %d |" % (b, n))

    f = tr["funnel"]
    base = f["已投递"] or 1
    lines += ["", "## 转化漏斗", ""]
    lines.append("投递 %d → 有回复 %d（%d%%）→ 面试 %d（%d%%）→ offer %d（%d%%）"
                 % (f["已投递"], f["已回复"], round(100 * f["已回复"] / base),
                    f["面试"], round(100 * f["面试"] / base),
                    f["offer"], round(100 * f["offer"] / base)))

    if tr["match"]:
        lines += ["", "## 匹配度分布", "",
                  "高 %d / 中 %d / 低 %d / 其他 %d"
                  % (tr["match"].get("高", 0), tr["match"].get("中", 0),
                     tr["match"].get("低", 0), tr["match"].get("其他", 0))]

    lines += ["", "## 话术回复率", ""]
    if sent["total"]:
        lines.append("已发送 %d 条，HR 回复 %d 条（%d%%）"
                     % (sent["total"], sent["hr_replied"],
                        round(100 * sent["hr_replied"] / sent["total"])))
    else:
        lines.append("暂无已发送话术记录。")
    return "\n".join(lines) + "\n"


def main(argv=None):
    p = argparse.ArgumentParser(description="投递漏斗统计周报")
    p.add_argument("--data-dir", default="data", help="数据目录（默认 data）")
    p.add_argument("--json", action="store_true", dest="as_json",
                   help="输出机器可读 JSON")
    args = p.parse_args(argv)

    root = Path(args.data_dir)
    if not root.is_dir():
        print("数据目录不存在: %s" % root, file=sys.stderr)
        return 2

    missing = []
    tracker_rows, sent_rows = [], []
    tracker = root / "投递追踪.md"
    sent = root / "话术库" / "已发送记录.md"
    if tracker.is_file():
        tracker_rows = parse_markdown_table(tracker)
    else:
        missing.append("投递追踪.md")
    if sent.is_file():
        sent_rows = parse_markdown_table(sent)
    else:
        missing.append("话术库/已发送记录.md")

    stats = build_stats(tracker_rows, sent_rows, missing)
    if args.as_json:
        print(json.dumps(stats, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(stats), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
