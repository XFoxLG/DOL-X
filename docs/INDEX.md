# DOL-X 文档索引

**最后更新**: 2026-08-05

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
