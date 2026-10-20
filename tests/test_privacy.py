"""泄密哨兵：提交/发布前检查敏感信息。

用法（仓库根目录）：
    python tests/test_privacy.py

规则：个人求职数据只允许出现在 data/ 下；
skills/、references/ 及根文件出现 PII（手机号/身份证号/邮箱）或本机绝对路径，测试即失败。
"""
import re
import pathlib
import unittest

# PII 模式：完整手机号、身份证号、邮箱
PATTERNS = [
    (re.compile(r"1[3-9]\d{9}"), "手机号"),
    (re.compile(r"\d{17}[\dXx]"), "身份证号"),
    (re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"), "邮箱"),
]

GUARDED_DIRS = ["skills", "references"]
ROOT_FILES = ["README.md", "CHANGELOG-0.1.0.md", ".codex-plugin/plugin.json"]


def guarded_files():
    for d in GUARDED_DIRS:
        for f in pathlib.Path(d).rglob("*.md"):
            yield f
    for name in ROOT_FILES:
        p = pathlib.Path(name)
        if p.exists():
            yield p


class TestPrivacy(unittest.TestCase):
    def test_guarded_files_no_pii(self):
        """受保护文件里不许出现手机号/身份证号/邮箱"""
        for f in guarded_files():
            text = f.read_text(encoding="utf-8")
            for pat, name in PATTERNS:
                m = pat.search(text)
                self.assertIsNone(m, f"{f} 含疑似{name}: {m and m.group()}")

    def test_guarded_files_no_absolute_paths(self):
        """公开仓库不带本机绝对路径"""
        for f in guarded_files():
            text = f.read_text(encoding="utf-8")
            self.assertNotIn("E:\\", text, f"{f} 含本机绝对路径")


if __name__ == "__main__":
    unittest.main()
