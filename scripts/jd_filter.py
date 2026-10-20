#!/usr/bin/env python3
"""JD 预筛器：岗位描述（JD）的确定性初筛。

设计动机：Agent 擅长语义判断，但薪资/年限/学历/关键词这类可规则化的
信息应该交给确定性代码——可测试、可复核、零幻觉。

本工具负责：薪资区间抽取、城市/远程识别、经验与学历要求抽取、
关键词命中统计、红旗检测、加权评分。评分口径与
references/scoring-rubric.md 对齐：≥70 推荐 / 40-69 可考虑 / <40 不推荐。

用法：
    python scripts/jd_filter.py jd.txt
    python scripts/jd_filter.py --json jd.txt
    python scripts/jd_filter.py --years 4 --education 本科 jd.txt

退出码：0 正常；1 输入为空；2 文件不存在。
"""

import argparse
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------- 常量

CITIES = [
    "北京", "上海", "广州", "深圳", "杭州", "成都", "武汉", "南京", "西安",
    "苏州", "厦门", "长沙", "重庆", "天津", "合肥", "郑州", "青岛", "济南",
    "东莞", "佛山", "珠海", "中山", "惠州", "宁波", "无锡", "福州", "大连",
    "沈阳", "哈尔滨", "昆明", "贵阳", "南昌", "南宁", "石家庄", "太原",
    "乌鲁木齐", "兰州", "西宁", "银川", "呼和浩特", "海口", "温州", "常州",
]

CORE_KEYWORDS = [
    "AI应用", "AI 应用", "Agent", "智能体", "LLM", "大模型",
    "RAG", "MCP", "Prompt", "提示词", "AIGC", "大语言模型",
]
SECONDARY_KEYWORDS = [
    "Python", "自动化", "Docker", "运维", "API", "效率工具",
    "工作流", "爬虫", "脚本",
]

RED_FLAG_RULES = [
    (re.compile(r"能承受.{0,4}高压|高强度.{0,6}工作|弹性工作制"), "疑似加班暗语"),
    (re.compile(r"试用期.{0,8}无底薪|无责底薪"), "试用期薪资陷阱"),
    (re.compile(r"销售工程师|AI销售|销售.{0,10}熟悉\s*AI"), "岗位名带销售却要求 AI"),
]

EDU_LEVELS = {"不限": 0, "中专": 1, "高中": 1, "大专": 2, "专科": 2,
              "本科": 3, "硕士": 4, "研究生": 4, "博士": 5}

SALARY_RULES = [
    # (正则, 单位, 倍率)
    (re.compile(r"(\d+(?:\.\d+)?)\s*[-~至到]\s*(\d+(?:\.\d+)?)\s*[kK]"), "K/月", 1000),
    (re.compile(r"(\d+(?:\.\d+)?)\s*[kK]\s*[-~至到]\s*(\d+(?:\.\d+)?)\s*[kK]"), "K/月", 1000),
    (re.compile(r"(\d+(?:\.\d+)?)\s*万\s*[-~至到]\s*(\d+(?:\.\d+)?)\s*万"), "万/月", 10000),
    (re.compile(r"(\d+(?:\.\d+)?)\s*[-~至到]\s*(\d+(?:\.\d+)?)\s*万"), "万/月", 10000),
    (re.compile(r"(\d{4,6})\s*[-~至到]\s*(\d{4,6})\s*元"), "元/月", 1),
    (re.compile(r"(\d{4,6})\s*[-~至到]\s*(\d{4,6})\s*/月"), "元/月", 1),
]
SALARY_NEGOTIABLE = re.compile(r"面议|薪资不限|negotiable", re.IGNORECASE)

YEARS_RULES = [
    (re.compile(r"(\d+)\s*[-~至到]\s*(\d+)\s*年"), "range"),
    (re.compile(r"(\d+)\s*年以上"), "min"),
    (re.compile(r"(\d+)\s*年以下"), "max"),
]
YEARS_UNLIMITED = re.compile(r"经验不限|不限经验|无经验|应届亦可")

EDU_RULES = [
    (re.compile(r"硕士及以上|研究生及以上|硕士学历|硕士优先|硕士"), "硕士"),
    (re.compile(r"本科及以上|本科学历|统招本科|全日制本科|本科"), "本科"),
    (re.compile(r"大专及以上|专科学历|大专学历|高职|大专"), "大专"),
    (re.compile(r"学历不限|不限学历|无学历要求"), "不限"),
]

REMOTE_HINT = re.compile(r"远程办公|可远程|支持远程|remote", re.IGNORECASE)

# ---------------------------------------------------------------- 抽取器


def read_text(path):
    """读 JD 文本：utf-8 优先，gb18030 兜底（中文 JD 常按 GBK 保存）。"""
    data = Path(path).read_bytes()
    for enc in ("utf-8-sig", "gb18030"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def extract_salary(text):
    """抽取月薪区间 → dict(min/max 为元)。识别不了时 negotiable/None。"""
    for pat, unit, mult in SALARY_RULES:
        m = pat.search(text)
        if m:
            lo, hi = sorted((float(m.group(1)), float(m.group(2))))
            out = {"raw": m.group(0), "unit": unit, "negotiable": False,
                   "min": int(lo * mult), "max": int(hi * mult)}
            if out["min"] >= 50000:
                out["note"] = "数值偏大，可能为年薪口径，请人工复核"
            return out
    if SALARY_NEGOTIABLE.search(text):
        return {"raw": "面议", "unit": None, "negotiable": True,
                "min": None, "max": None}
    return {"raw": None, "unit": None, "negotiable": False,
            "min": None, "max": None}


def extract_city(text):
    for c in CITIES:
        if c in text:
            return c
    return None


def extract_years(text):
    """抽取经验要求 → dict(min/max/unlimited)。"""
    for pat, kind in YEARS_RULES:
        m = pat.search(text)
        if m:
            if kind == "range":
                lo, hi = sorted((int(m.group(1)), int(m.group(2))))
                return {"raw": m.group(0), "min": lo, "max": hi, "unlimited": False}
            if kind == "min":
                return {"raw": m.group(0), "min": int(m.group(1)),
                        "max": None, "unlimited": False}
            return {"raw": m.group(0), "min": 0, "max": int(m.group(1)),
                    "unlimited": False}
    if YEARS_UNLIMITED.search(text):
        return {"raw": "经验不限", "min": None, "max": None, "unlimited": True}
    return {"raw": None, "min": None, "max": None, "unlimited": False}


def extract_education(text):
    for pat, level in EDU_RULES:
        if pat.search(text):
            return level
    return None


def count_keywords(text):
    t = text.lower()
    return {
        "core": [k for k in CORE_KEYWORDS if k.lower() in t],
        "secondary": [k for k in SECONDARY_KEYWORDS if k.lower() in t],
    }


def detect_red_flags(text):
    return [label for pat, label in RED_FLAG_RULES if pat.search(text)]


def parse_jd(text):
    """JD 全量抽取：一个入口拿齐所有确定性字段。"""
    return {
        "salary": extract_salary(text),
        "city": extract_city(text),
        "remote": bool(REMOTE_HINT.search(text)),
        "years": extract_years(text),
        "education": extract_education(text),
        "keywords": count_keywords(text),
        "red_flags": detect_red_flags(text),
    }


# ---------------------------------------------------------------- 评分


def score(parsed, config=None):
    """确定性加权评分（口径对齐 references/scoring-rubric.md）。

    关键词 40 / 薪资 20 / 经验 20 / 学历 15 / 城市 5，红旗每个 -8。
    """
    cfg = {"salary_floor": 6000, "years": None, "education": "不限", "city": ""}
    if config:
        cfg.update(config)
    b = {}
    flags = list(parsed["red_flags"])

    kw = parsed["keywords"]
    b["关键词"] = min(40, len(kw["core"]) * 12 + len(kw["secondary"]) * 6)

    sal = parsed["salary"]
    if sal["negotiable"] or sal["min"] is None:
        b["薪资"] = 10
    elif sal["min"] >= cfg["salary_floor"]:
        b["薪资"] = 20
    else:
        b["薪资"] = 0
        flags.append("薪资低于底线 %d" % cfg["salary_floor"])

    yrs = parsed["years"]
    if yrs["unlimited"]:
        b["经验"] = 20
    elif yrs["min"] is None and yrs["max"] is None:
        b["经验"] = 10
    elif cfg["years"] is None:
        b["经验"] = 10
    elif yrs["max"] is not None and yrs["max"] <= cfg["years"] + 2:
        b["经验"] = 20
    elif yrs["min"] is not None and yrs["min"] <= cfg["years"] + 2:
        b["经验"] = 16
    elif yrs["min"] is not None and yrs["min"] <= cfg["years"] + 4:
        b["经验"] = 10
    else:
        b["经验"] = 4

    edu_req = parsed["education"]
    if edu_req is None or edu_req == "不限":
        b["学历"] = 15
    elif cfg["education"] in ("不限", None):
        b["学历"] = 8
    elif EDU_LEVELS.get(edu_req, 0) <= EDU_LEVELS.get(cfg["education"], 0):
        b["学历"] = 15
    else:
        b["学历"] = 0
        flags.append("学历硬门槛：要求 %s" % edu_req)

    if cfg["city"]:
        b["城市"] = 5 if parsed["city"] == cfg["city"] else 0
        if parsed["city"] and parsed["city"] != cfg["city"]:
            flags.append("城市不匹配：岗位在 %s" % parsed["city"])
    else:
        b["城市"] = 3

    b["红旗"] = -8 * len(flags)
    total = max(0, sum(b.values()))
    v = "推荐" if total >= 70 else ("可考虑" if total >= 40 else "不推荐")
    if len(flags) >= 2 and v == "推荐":
        v = "可考虑"
    return {"total": total, "breakdown": b, "verdict": v, "red_flags": flags}


# ---------------------------------------------------------------- 输出


def render_text(parsed, result, cfg):
    sal = parsed["salary"]
    yrs = parsed["years"]
    lines = []
    if sal["negotiable"]:
        lines.append("薪资     : 面议")
    elif sal["min"] is not None:
        lines.append("薪资     : %d-%d 元/月（底线 %d，%s）"
                     % (sal["min"], sal["max"] or sal["min"], cfg["salary_floor"],
                        "满足" if sal["min"] >= cfg["salary_floor"] else "不足"))
    else:
        lines.append("薪资     : 未识别")
    lines.append("城市     : %s%s"
                 % (parsed["city"] or "未识别",
                    "（支持远程）" if parsed["remote"] else ""))
    if yrs["unlimited"]:
        lines.append("经验要求 : 不限")
    elif yrs["min"] is not None:
        if yrs["max"]:
            lines.append("经验要求 : %d-%d 年" % (yrs["min"], yrs["max"]))
        else:
            lines.append("经验要求 : %d 年以上" % yrs["min"])
    else:
        lines.append("经验要求 : 未识别")
    lines.append("学历要求 : %s" % (parsed["education"] or "未识别"))
    kw = parsed["keywords"]
    lines.append("关键词   : 核心 %d（%s）加分 %d（%s）"
                 % (len(kw["core"]), "、".join(kw["core"]) or "无",
                    len(kw["secondary"]), "、".join(kw["secondary"]) or "无"))
    lines.append("红旗     : %s" % ("；".join(result["red_flags"]) or "无"))
    lines.append("评分     : %d/100 → %s" % (result["total"], result["verdict"]))
    lines.append("  " + " | ".join("%s %+d" % (k, v)
                                   for k, v in result["breakdown"].items()))
    return "\n".join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(
        description="JD 预筛器：薪资/城市/年限/学历抽取 + 关键词命中 + 确定性评分 + 红旗")
    p.add_argument("file", nargs="?", help="JD 文本文件（缺省读标准输入）")
    p.add_argument("--json", action="store_true", dest="as_json",
                   help="输出机器可读 JSON")
    p.add_argument("--salary-floor", type=int, default=6000, help="月薪底线（元）")
    p.add_argument("--years", type=int, default=None, help="自身工作年限")
    p.add_argument("--education", default="不限", choices=list(EDU_LEVELS),
                   help="自身学历")
    p.add_argument("--city", default="", help="期望城市（如：深圳）")
    args = p.parse_args(argv)

    if args.file:
        if not Path(args.file).is_file():
            print("文件不存在: %s" % args.file, file=sys.stderr)
            return 2
        text = read_text(args.file)
    else:
        text = sys.stdin.read()
    if not text.strip():
        print("输入为空", file=sys.stderr)
        return 1

    cfg = {"salary_floor": args.salary_floor, "years": args.years,
           "education": args.education, "city": args.city}
    parsed = parse_jd(text)
    result = score(parsed, cfg)
    if args.as_json:
        print(json.dumps({"parsed": parsed, "score": result, "config": cfg},
                         ensure_ascii=False, indent=2))
    else:
        print(render_text(parsed, result, cfg))
    return 0


if __name__ == "__main__":
    sys.exit(main())
