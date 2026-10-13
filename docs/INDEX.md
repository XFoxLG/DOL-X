# DOL-X 文档索引

**最后更新**: 2026-10-13

---

## 用户文档

- [README](../README.md) - 项目简介和快速开始
- [QUICK_REFERENCE](../QUICK_REFERENCE.md) - 快速命令参考
- [CHANGELOG](../CHANGELOG.md) - 完整技术更新日志
- [CURRENT_PROJECT_STATE](CURRENT_PROJECT_STATE.md) - 当前事实的唯一总入口
- [CHEAT_EXTENDED_FAQ](CHEAT_EXTENDED_FAQ.md) - Cheat Extended 使用常见问题
- [RELEASE_NOTES](release-notes/) - 面向玩家的各版本 Release 正文

## 开发文档

### Mod 矩阵与决策
- [MOD_MATRIX_RATIONALE](../MOD_MATRIX_RATIONALE.md) - Mod 选择和组合理由
- [MOD_COMPATIBILITY_MATRIX](MOD_COMPATIBILITY_MATRIX.md) - 当前 mod 版本、验证层级与边界
- [UCB_COMPATIBILITY_REPORT](UCB_COMPATIBILITY_REPORT.md) - UCB 与 AU 兼容性验证

### 上游同步
- [UPSTREAM_FRIENDLY_STRATEGY](../UPSTREAM_FRIENDLY_STRATEGY.md) - 上游友好策略
- [UPSTREAM_DIFF_SUMMARY](../UPSTREAM_DIFF_SUMMARY.md) - 与上游的差异对比
- [UPSTREAM_SYNC_GUIDE](UPSTREAM_SYNC_GUIDE.md) - 同步操作指南

### 技术参考
- [DOCUMENTATION_GUIDE](DOCUMENTATION_GUIDE.md) - CHANGELOG、Release 正文与状态文档写作规范
- [TESTING_GUIDE](TESTING_GUIDE.md) - 当前测试流程与验证边界
- [AUTOMATED_PASSAGE_SWEEP](AUTOMATED_PASSAGE_SWEEP.md) - Engine A 自动化测试套件总说明：全 passage 扫描 + 剧情场景/日循环 + 战斗 + 环境矩阵 + 夹具阶梯与存档安全 + 云端分片工作流
- [AUTOMATED_GAMEPLAY_EXPLORER](AUTOMATED_GAMEPLAY_EXPLORER.md) - 自然轨道自动玩家、语义动作轨迹、状态指纹、checkpoint 归因、失败重放缩减、Android semantic replay 的边界
- [Exploration Gate](../tools/exploration_gate.py) - 跨报告 target identity、coverage、failure attribution 与 release-ready 判定
- [Framework Contract Check](../tools/framework_contract_check.py) + [矩阵](../config/framework-contract-matrix.toml) - 按内容（package.json + 签名 + needle）而不是 tag 名认 maplebirch 版本
- [Static Reachability Solver](../tools/static_reachability_solver.py) - clingo bounded playtrace 的静态可达性见证；无见证时 fail-closed 区分 `unknown_dynamic_edges` / `unreachable_within_bound`
- [Story Graph Audit](../tools/story_graph_audit.py) + [白名单](../config/accepted-upstream-graph-defects.toml) - 死胡同/自环/未定义目标/零入边 passage 的图完整性审计，白名单每条引用 tag `0.5.11.9` 行号
- [Traversal Statistics](../tools/traversal_statistics.py) - 按 evidence track 分开统计访问率、边覆盖与唯一状态数
- [Query Regression](../tools/query_regression.py) + [查询集](../config/exploration-queries.toml) - 发布查询回归集（含 AU 契约、A/B verdict 钉子、符号化可达性与 story graph 回归）
- [外部测试方法基准](research/2026-10-13-external-testing-benchmarks.md) - CoT / DoL Plus evidence / i18nMod test / Lyra CI 等外部调研来源与负结论
- [COMMUNITY_TOOLS](COMMUNITY_TOOLS.md) - 社区工具评估
- [AU_MODS_INTEGRATION](AU_MODS_INTEGRATION.md) - AU Mod 集成说明
- [MODLOADER_TROUBLESHOOTING](MODLOADER_TROUBLESHOOTING.md) - ModLoader 排障
- [SAVE_COMPATIBILITY](SAVE_COMPATIBILITY.md) - 存档兼容性说明

## 本地文档（不上传）

这些文档位于 `.local/`，被 .gitignore 忽略：
- 临时分析报告
- 执行总结
- 项目回顾
- 自动化脚本

---

## 文档维护原则

1. **用户文档保持简洁**，面向使用者
2. **内部文档记录决策理由**，面向维护者
3. **临时文档不上传**，避免泄露敏感信息
4. **当前有效的核心文档在此索引**，历史研究与会话快照保留在原目录，不逐项列出

---

## 文档分类说明

### 用户文档（根目录）
面向 DOL-X 使用者的文档，包括安装、构建、使用说明。

### 内部文档（docs/）
面向 DOL-X 维护者的文档，包括技术决策、上游同步、开发指南。

### 临时文档（.local/，不上传）
临时分析、研究报告、自动化脚本，仅在本地使用。
