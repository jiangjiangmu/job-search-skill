"""funnel_report 单元测试：表格解析、状态归一、漏斗计算。"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import funnel_report as fr  # noqa: E402


TRACKER_MD = """# 投递追踪总表

| 日期 | 公司 | 岗位 | 薪资 | 匹配度 | 状态 | 下一步 | 备注 |
|---|---|---|---|---|---|---|---|
| 2026-10-19 | 示例公司A | AI应用工程师 | 15-25K | 高 | 已投递 | 等回复 | |
| 2026-10-20 | 示例公司B | Agent开发 | 12-18K | 中 | 已回复 | 准备笔试 | |
| 2026-10-20 | 示例公司C | AI运维 | 10-15K | 高 | 面试中 | 二面 | |
| 2026-10-20 | 示例公司D | Python后端 | 15-25K | 低 | offer | 谈薪 | |
| 2026-10-20 | 示例公司E | AI落地 | 15-25K | 中 | 不合适 | 无 | |
"""


def _write(td, name, text):
    p = Path(td) / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


class TestParse(unittest.TestCase):
    def test_parse_rows(self):
        with tempfile.TemporaryDirectory() as td:
            rows = fr.parse_markdown_table(_write(td, "tracker.md", TRACKER_MD))
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[0]["公司"], "示例公司A")
        self.assertEqual(rows[-1]["状态"], "不合适")

    def test_parse_empty_table(self):
        with tempfile.TemporaryDirectory() as td:
            rows = fr.parse_markdown_table(
                _write(td, "tracker.md", "| 日期 | 公司 |\n|---|---|\n"))
        self.assertEqual(rows, [])


class TestNormalize(unittest.TestCase):
    def test_buckets(self):
        self.assertEqual(fr.normalize_status("面试中"), "面试")
        self.assertEqual(fr.normalize_status("已约面试"), "面试")
        self.assertEqual(fr.normalize_status("不合适"), "终止")
        self.assertEqual(fr.normalize_status("Offer"), "offer")
        self.assertEqual(fr.normalize_status(""), "已投递")


class TestStats(unittest.TestCase):
    def _rows(self):
        with tempfile.TemporaryDirectory() as td:
            return fr.parse_markdown_table(_write(td, "tracker.md", TRACKER_MD))

    def test_weekly_grouping(self):
        stats = fr.build_stats(self._rows(), [], [])
        weeks = stats["tracker"]["weeks"]
        # 10-19（周一）与 10-20（周二）同属一个 ISO 周
        self.assertEqual(len(weeks), 1)
        self.assertEqual(sum(weeks.values()), 5)

    def test_funnel(self):
        stats = fr.build_stats(self._rows(), [], [])
        f = stats["tracker"]["funnel"]
        self.assertEqual(f["已投递"], 4)   # 终止不计入漏斗
        self.assertEqual(f["已回复"], 3)
        self.assertEqual(f["面试"], 2)
        self.assertEqual(f["offer"], 1)

    def test_render_markdown(self):
        stats = fr.build_stats(self._rows(), [], [])
        md = fr.render_markdown(stats)
        self.assertIn("投递漏斗周报", md)
        self.assertIn("转化漏斗", md)

    def test_empty_renders_placeholder(self):
        stats = fr.build_stats([], [], ["投递追踪.md"])
        md = fr.render_markdown(stats)
        self.assertIn("暂无投递记录", md)


if __name__ == "__main__":
    unittest.main()
