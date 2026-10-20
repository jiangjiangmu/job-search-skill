"""jd_filter 单元测试：抽取器与评分器逐项验证。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import jd_filter  # noqa: E402


SAMPLE_JD = """
职位：AI 应用工程师（示例，虚构）
薪资：15-25K·14薪
城市：深圳
要求：本科及以上学历，3-5 年后端经验；
熟悉 AI Agent / RAG / MCP 相关技术栈，熟练使用 Python，
有自动化运维经验加分。能承受高强度工作压力。
"""


class TestSalary(unittest.TestCase):
    def test_k_range(self):
        sal = jd_filter.extract_salary("薪资 15-25K")
        self.assertEqual((sal["min"], sal["max"]), (15000, 25000))

    def test_wan_range(self):
        sal = jd_filter.extract_salary("薪资 1.5万-2.5万")
        self.assertEqual((sal["min"], sal["max"]), (15000, 25000))

    def test_yuan_range(self):
        sal = jd_filter.extract_salary("8000-12000元/月")
        self.assertEqual((sal["min"], sal["max"]), (8000, 12000))

    def test_negotiable(self):
        sal = jd_filter.extract_salary("薪资面议，能力强者优先")
        self.assertTrue(sal["negotiable"])


class TestYears(unittest.TestCase):
    def test_range(self):
        yrs = jd_filter.extract_years("要求 3-5 年经验")
        self.assertEqual((yrs["min"], yrs["max"]), (3, 5))

    def test_min_only(self):
        yrs = jd_filter.extract_years("5 年以上经验优先")
        self.assertEqual(yrs["min"], 5)
        self.assertIsNone(yrs["max"])

    def test_unlimited(self):
        yrs = jd_filter.extract_years("经验不限，欢迎应届")
        self.assertTrue(yrs["unlimited"])


class TestEducation(unittest.TestCase):
    def test_bachelor(self):
        self.assertEqual(jd_filter.extract_education("本科及以上学历"), "本科")

    def test_master(self):
        self.assertEqual(jd_filter.extract_education("硕士及以上优先"), "硕士")

    def test_bare_terms(self):
        self.assertEqual(jd_filter.extract_education("要求：本科"), "本科")
        self.assertEqual(jd_filter.extract_education("要求：硕士"), "硕士")
        self.assertEqual(jd_filter.extract_education("要求：大专"), "大专")


class TestKeywordsAndFlags(unittest.TestCase):
    def test_core_hits(self):
        kw = jd_filter.count_keywords("熟悉 AI Agent、RAG、MCP 技术栈")
        self.assertIn("Agent", kw["core"])
        self.assertIn("RAG", kw["core"])
        self.assertIn("MCP", kw["core"])

    def test_red_flag(self):
        flags = jd_filter.detect_red_flags("能承受高强度工作压力，弹性工作制")
        self.assertEqual(len(flags), 1)


class TestScore(unittest.TestCase):
    def test_full_pipeline(self):
        parsed = jd_filter.parse_jd(SAMPLE_JD)
        result = jd_filter.score(parsed)
        self.assertIsInstance(result["total"], int)
        self.assertIn(result["verdict"], ("推荐", "可考虑", "不推荐"))

    def test_below_floor_penalized(self):
        parsed = jd_filter.parse_jd("薪资 5-6K，AI Agent 开发，Python，自动化")
        result = jd_filter.score(parsed, {"salary_floor": 6000})
        self.assertEqual(result["breakdown"]["薪资"], 0)
        self.assertIn("薪资低于底线", "；".join(result["red_flags"]))

    def test_high_score_recommended(self):
        parsed = jd_filter.parse_jd(
            "AI Agent 开发，熟悉 RAG MCP Prompt，Python 自动化，"
            "薪资 15-25K，深圳，本科，3-5 年")
        result = jd_filter.score(parsed, {"years": 4, "education": "本科",
                                          "city": "深圳"})
        self.assertGreaterEqual(result["total"], 70)
        self.assertEqual(result["verdict"], "推荐")


if __name__ == "__main__":
    unittest.main()
