# job-search-skill · AI 求职工作台

把「找工作」工程化：**搜岗位 → 分析匹配 → 生成话术 → 追踪投递**，一条完整流水线交给 AI Agent 跑。

这不是一组聊天提示词，而是一个带**数据契约、输出规范、泄密哨兵**的 Agent 技能包——每次开工，Agent 都接着上次的进度干：搜过、分析过、发过的东西全部沉淀在仓库里。

## 技能一览

| 技能 | 职责 | 触发示例 |
|---|---|---|
| `job-search` | 按搜索策略找岗位，串起全流程 | 「搜一下 {{方向}} 的岗位」 |
| `job-analyze` | JD 拆解 + 薪资水位 + 匹配评分 | 「分析这个岗位」（截图/链接/文字都行） |
| `job-communication` | 四原则生成 HR 开场白并归档 | 「帮我写开场白」 |

## 目录结构

```
job-search-skill/
├── README.md
├── CHANGELOG-0.1.0.md
├── .codex-plugin/plugin.json        ← 插件身份注册（Codex/DSH 风格）
├── skills/                          ← 三个技能（触发条件/流程/输出契约）
│   ├── job-search/SKILL.md
│   ├── job-analyze/SKILL.md
│   └── job-communication/SKILL.md
├── references/                      ← 契约层（Agent 每次开工先读）
│   ├── 能力清单.md                   ← 你的技术画像（模板+示例，需替换）
│   ├── 分析模板.md
│   ├── 开场白模板.md
│   ├── search-policy.md             ← 搜索策略（关键词/渠道/筛选标准）
│   └── scoring-rubric.md            ← 匹配度评分口径
├── data/                            ← 数据区（个人求职数据只落这里）
│   ├── 投递追踪.md
│   ├── 话术库/已发送记录.md
│   └── 岗位分析/已分析岗位/          ← 已 gitignore
├── scripts/                         ← 执行层（预留）
└── tests/test_privacy.py            ← 泄密哨兵，提交前必跑
```

## 隐私设计（核心工程点）

求职数据是高敏个人信息：公司名、薪资、HR 对话、通勤范围全是谈判底牌。本仓库三层防线：

1. **模板与数据分离** —— `references/` 只放模板与策略，真实数据只允许写进 `data/`
2. **gitignore 防误提交** —— `data/岗位分析/已分析岗位/` 默认忽略；fork 自用时建议把 `data/投递追踪.md`、`data/话术库/已发送记录.md` 一并忽略，或改用 `.local.md` 后缀
3. **泄密哨兵** —— `tests/test_privacy.py` 用正则扫描手机号/身份证号/邮箱/本机绝对路径，`skills/`、`references/` 及根文件零容忍，命中即测试失败：

```bash
python tests/test_privacy.py
```

## 快速开始

1. Clone 到你的 Agent 技能目录（兼容 `.codex-plugin` 插件规范）
2. 把 `references/能力清单.md` 的示例画像换成你自己的（越具体，匹配评估越准）
3. 把 `references/search-policy.md` 里的 `{{占位符}}`（城市/方向/薪资线）改成你的策略
4. 对 Agent 说：「用 job-search-skill，搜一下 {{你的方向}} 岗位」

## 铁规矩

- 只分析真实搜到的职位，**不编造**
- 薪资以职位页显示为准，**不虚报**
- 投不投由用户拍板，Agent 只给建议和话术
- 手机号/身份证号/邮箱不允许出现在 `data/` 之外的任何文件（哨兵强制）

## 贡献者

- **主开发**：YD —— 技能设计、契约层、泄密哨兵
- **辅助开发**：黄学姐 —— 话术库试用反馈、文档校对、求职流程测试

## 版本

v0.1.0 · 见 [CHANGELOG-0.1.0.md](CHANGELOG-0.1.0.md)
