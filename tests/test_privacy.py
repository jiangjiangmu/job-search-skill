"""泄密哨兵自测：用虚构 PII 验证扫描器本身，再对仓库做一次集成扫描。

注意：本文件里的 PII 全部是虚构样例——tests/ 不在
privacy_rules.json 的保护范围内，专门用来测哨兵。
"""
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

import privacy_scan  # noqa: E402

RAW, PATTERNS = privacy_scan.load_rules(privacy_scan.DEFAULT_RULES)


class TestScanner(unittest.TestCase):
    def _scan_tmp(self, content):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "sample.md"
            f.write_text(content, encoding="utf-8")
            return privacy_scan.scan_file(f, PATTERNS,
                                          RAW.get("blocked_strings", []))

    def test_detects_phone(self):
        vs = self._scan_tmp("联系电话：13800138000，欢迎咨询")
        self.assertTrue(any(v["id"] == "phone" for v in vs))

    def test_detects_id_card(self):
        vs = self._scan_tmp("证件号 11010119900307867X")
        self.assertTrue(any(v["id"] == "id_card" for v in vs))

    def test_detects_email(self):
        vs = self._scan_tmp("简历投递：demo@example.com")
        self.assertTrue(any(v["id"] == "email" for v in vs))

    def test_detects_abs_path(self):
        vs = self._scan_tmp("运行目录 D:\\demo\\repo")
        self.assertTrue(any(v["id"] == "abs_path" for v in vs))

    def test_clean_file_passes(self):
        vs = self._scan_tmp("普通技术文本：AI Agent、RAG、MCP，无任何隐私。")
        self.assertEqual(vs, [])

    def test_rules_json_shape(self):
        for key in ("patterns", "guarded"):
            self.assertIn(key, RAW)
        ids = {p["id"] for p in RAW["patterns"]}
        self.assertLessEqual({"phone", "id_card", "email"}, ids)


class TestRepoClean(unittest.TestCase):
    def test_repo_guarded_files_clean(self):
        """集成扫描：公开范围零违规。"""
        report = privacy_scan.scan_repo(REPO, RAW, PATTERNS)
        self.assertGreater(report["scanned_files"], 10)
        self.assertEqual(report["violations"], [])


if __name__ == "__main__":
    unittest.main()
