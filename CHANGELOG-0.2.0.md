# 0.2.0（2026-10-20）

补齐确定性执行层：语义判断归 Agent，可规则化的环节全部落成可测试代码。

- 新增 `scripts/jd_filter.py`：JD 预筛器——薪资/城市/年限/学历抽取、关键词命中、红旗检测、与 scoring-rubric 对齐的加权评分
- 新增 `scripts/funnel_report.py`：投递漏斗周报——周投递量、状态分布、投递→回复→面试→offer 转化率、匹配度分布、话术回复率
- 新增 `scripts/privacy_scan.py` + `privacy_rules.json`：泄密哨兵 CLI 化，规则外置可扩展，支持 JSON 输出与 CI 退出码
- 测试扩到 28 个用例：三工具单元测试 + 哨兵自测（虚构 PII 样例）+ 仓库集成扫描
- README 增补工具链用法与「Agent 语义层 / 代码确定性层」分工说明
