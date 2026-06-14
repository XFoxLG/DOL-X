# ModLoader 完整知识库索引

**创建日期**: 2026-06-11  
**文档版本**: 1.0  

---

## 📚 文档总览

本知识库提供 **ModLoader 的完整深度调研**，涵盖从基础概念到高级用法的所有内容。

**特点**:
- ✅ 模块化设计，每个文档 500-1000 行
- ✅ 基于官方文档和 DOL-X 实践
- ✅ 包含实战案例和故障排除
- ✅ 持续更新维护

---

## 🗂️ 文档列表

### 1. [MODLOADER_OVERVIEW.md](MODLOADER_OVERVIEW.md)
**ModLoader 概述** - 新手入门必读

**内容**:
- 项目简介和目标
- 核心能力（4 种 Mod 来源、管理功能、依赖管理、插件系统）
- 架构设计理念
- 与 SugarCube2 的关系
- 快速开始指南

**适合**:
- 第一次接触 ModLoader 的用户
- 想了解 ModLoader 能做什么
- 寻找快速入门教程

**篇幅**: ~600 行

---

### 2. [MODLOADER_BOOT_JSON.md](MODLOADER_BOOT_JSON.md)
**boot.json 完整规范** - Mod 开发核心文档

**内容**:
- boot.json 基础字段（name, version, nickName, alias）
- 资源文件列表（CSS, JS, Twee, 图片等）
- 4 个脚本加载阶段详解
- 依赖管理和版本约束
- 插件系统配置
- 完整示例（简单/复杂/图片 Mod）
- 常见错误和验证工具

**适合**:
- Mod 开发者
- 需要配置 boot.json 的用户
- 调试 Mod 加载问题

**篇幅**: ~900 行

---

### 3. [MODLOADER_FAQ.md](MODLOADER_FAQ.md)
**常见问题解答** - 快速解决问题

**内容**:
- 基础问题（SweetAlert2Mod、版本检查、安全模式）
- Mod 加载问题（boot.json 无效、不生效、找不到 Mod）
- 依赖和兼容性（maplebirch vs Simple Frameworks）
- 开发问题（earlyload 执行、调试、加载顺序）
- DOL-X 特定问题（build_code、AU 面部扩展）
- 故障排除流程图

**适合**:
- 遇到问题需要快速解答
- 了解 DOL-X 特定配置
- 学习实战案例

**篇幅**: ~700 行

---

## 📖 推荐的阅读顺序

### 对于玩家

1. **入门**: [MODLOADER_OVERVIEW.md](MODLOADER_OVERVIEW.md) - 了解 ModLoader 是什么
2. **使用**: 查看"快速开始"章节 - 学会加载和管理 Mod
3. **问题**: [MODLOADER_FAQ.md](MODLOADER_FAQ.md) - 遇到问题时查阅

### 对于 Mod 开发者

1. **概览**: [MODLOADER_OVERVIEW.md](MODLOADER_OVERVIEW.md) - 理解架构
2. **配置**: [MODLOADER_BOOT_JSON.md](MODLOADER_BOOT_JSON.md) - 学习 boot.json
3. **实践**: [MODLOADER_FAQ.md](MODLOADER_FAQ.md) - 查看开发问题章节
4. **参考**: 官方模板项目 - TypeScript/JavaScript 示例

### 对于 DOL-X 维护者

1. **所有文档**: 全面了解 ModLoader
2. **FAQ**: 重点关注 DOL-X 特定问题
3. **相关文档**: 
   - [`AU_FACIAL_DEPENDENCY_REPORT.md`](../AU_FACIAL_DEPENDENCY_REPORT.md)
   - [`FRAMEWORK_PROVIDER_RESEARCH.md`](../FRAMEWORK_PROVIDER_RESEARCH.md)
   - [`MODLOADER_METADATA_EXTENSION.md`](MODLOADER_METADATA_EXTENSION.md)

---

## 🔗 外部资源

### 官方资源

| 资源 | 链接 | 说明 |
|------|------|------|
| **官方仓库** | https://github.com/Lyoko-Jeremie/sugarcube-2-ModLoader | 源码和文档 |
| **中文流程** | ModLoaderAndModLoadingProcess - CN.md | 详细加载流程（未包含在本库中，见官方仓库） |
| **README** | 900+ 行完整说明 | 官方最全文档 |
| **预构建版** | https://github.com/Lyoko-Jeremie/DoLModLoaderBuild/releases | 带 ModLoader 的游戏 |

### 模板项目

| 项目 | 链接 | 说明 |
|------|------|------|
| **TypeScript 模板** | https://github.com/Lyoko-Jeremie/DoLModWebpackExampleTs | 推荐使用 |
| **JavaScript 模板** | https://github.com/Lyoko-Jeremie/DoLModWebpackExampleJs | 简单项目 |

### 官方 Mod 列表

| Mod | 类型 | 状态 | 功能 |
|-----|------|------|------|
| **ModLoaderGui** | Built-in | Stable | Mod 管理器 GUI |
| **ConflictChecker** | Built-in | Stable | 冲突检查 |
| **ImageLoaderHook** | Built-in | Stable | 图片替换 |
| **BeautySelectorAddon** | Built-in | Stable | 美化切换 |
| **SweetAlert2Mod** | Built-in | Stable | 弹窗提示 |
| **TweeReplacer** | Built-in | Stable | Passage 替换 |
| **ReplacePatch** | Built-in | Stable | 简单替换 |
| **SimpleCryptWrapper** | Tools | Stable | Mod 加密工具 |

完整列表见：https://github.com/Lyoko-Jeremie/sugarcube-2-ModLoader#modloader

---

## 🛠️ DOL-X 相关文档

### 核心配置

- [`config/build.toml`](../config/build.toml) - Mod 配置
- [`config/features.toml`](../config/features.toml) - Feature 定义
- [`config/combinations.toml`](../config/combinations.toml) - 构建矩阵
- [`config/profiles.toml`](../config/profiles.toml) - 用户场景

### 调研报告

- [`AU_FACIAL_DEPENDENCY_REPORT.md`](../AU_FACIAL_DEPENDENCY_REPORT.md) - AU 面部扩展依赖分析
- [`FRAMEWORK_PROVIDER_RESEARCH.md`](../FRAMEWORK_PROVIDER_RESEARCH.md) - 框架提供者源码研究
- [`PHASE0_INVESTIGATION_REPORT.md`](../PHASE0_INVESTIGATION_REPORT.md) - cheatExtended 问题分析
- [`TECHNICAL_FEASIBILITY_ASSESSMENT_REPORT.md`](../TECHNICAL_FEASIBILITY_ASSESSMENT_REPORT.md) - 技术可行性评估

### 扩展提案

- [`MODLOADER_METADATA_EXTENSION.md`](MODLOADER_METADATA_EXTENSION.md) - boot.json 扩展提案

---

## 🎯 核心概念速查

### Mod 加载顺序

```
HTML 内嵌 > 远程服务器 > LocalStorage > IndexDB
```

### 脚本加载阶段

```
inject_early → earlyload → 标准加载 → preload → SC2 启动
```

### 版本约束语法

| 语法 | 含义 |
|------|------|
| `^2.100.0` | 兼容 2.x 主版本 |
| `>=0.5.6` | 最低版本 |
| `>=3.1.13 <4.0.0` | 版本范围 |
| `*` | 任意版本（不推荐） |

### boot.json 必需字段

```json
{
  "name": "MyMod",              // 必需
  "version": "1.0.0",           // 必需
  "styleFileList": [],          // 必需（可为空）
  "scriptFileList": [],         // 必需（可为空）
  "tweeFileList": [],           // 必需（可为空）
  "imgFileList": [],            // 必需（可为空）
  "additionFile": []            // 必需（可为空）
}
```

---

## 🔍 快速查找

### 我想...

- **了解 ModLoader 是什么** → [MODLOADER_OVERVIEW.md](MODLOADER_OVERVIEW.md)
- **创建一个 Mod** → [MODLOADER_BOOT_JSON.md](MODLOADER_BOOT_JSON.md)
- **解决加载问题** → [MODLOADER_FAQ.md](MODLOADER_FAQ.md) - Q5-Q7
- **了解 SweetAlert2Mod** → [MODLOADER_FAQ.md](MODLOADER_FAQ.md) - Q2
- **理解 maplebirch vs Simple Frameworks** → [MODLOADER_FAQ.md](MODLOADER_FAQ.md) - Q8-Q9
- **调试 Mod** → [MODLOADER_FAQ.md](MODLOADER_FAQ.md) - Q12
- **了解 DOL-X build_code** → [MODLOADER_FAQ.md](MODLOADER_FAQ.md) - Q15

---

## 📝 文档维护

### 更新日志

| 日期 | 版本 | 更新内容 |
|------|------|----------|
| 2026-06-11 | 1.0 | 初始版本，创建 3 个核心文档 |

### 贡献指南

欢迎贡献：
1. **报告错误**: 提交 Issue 说明文档中的错误
2. **补充内容**: PR 添加缺失的信息
3. **新增 FAQ**: 提供常见问题和解答
4. **翻译**: 翻译为其他语言

### 待完成文档（未来计划）

- [ ] `MODLOADER_ARCHITECTURE.md` - 架构原理深度分析
- [ ] `MODLOADER_LIFECYCLE.md` - 21 步加载流程详解
- [ ] `MODLOADER_API.md` - 完整 API 文档
- [ ] `MODLOADER_BEST_PRACTICES.md` - 最佳实践指南
- [ ] `MODLOADER_ADDON_DEV.md` - Addon 开发指南
- [ ] `MODLOADER_ADVANCED.md` - 高级用法（懒加载、加密等）

**注**: 当前 3 个文档已覆盖最核心和最常用的内容。其他文档根据需求逐步添加。

---

## 🤝 获取帮助

### 社区支持

1. **官方 Issues**: https://github.com/Lyoko-Jeremie/sugarcube-2-ModLoader/issues
2. **DOL-X Issues**: https://github.com/XFoxLG/DOL-X/issues
3. **DoL 社区**: 百度贴吧、Reddit r/DegreesOfLewdity
4. **DoL Wiki**: https://dolmodding.miraheze.org/wiki/ModLoader

### 报告问题

提供以下信息：
1. ModLoader 版本
2. 游戏版本
3. Mod 列表
4. 错误信息（Console 截图）
5. 重现步骤

---

## 📊 统计信息

| 指标 | 数值 |
|------|------|
| 文档数量 | 3 个核心文档 |
| 总篇幅 | ~2200 行 |
| 覆盖的主题 | 概述、配置、FAQ |
| 实战案例 | 10+ 个 |
| FAQ 问题 | 18 个 |

---

## 🎓 学习路径

### 初级（玩家）

1. 阅读 [MODLOADER_OVERVIEW.md](MODLOADER_OVERVIEW.md) 的"快速开始"章节
2. 尝试加载一个 Mod
3. 遇到问题查阅 [MODLOADER_FAQ.md](MODLOADER_FAQ.md)

**预计时间**: 30 分钟

### 中级（Mod 开发者）

1. 完整阅读 [MODLOADER_OVERVIEW.md](MODLOADER_OVERVIEW.md)
2. 深入学习 [MODLOADER_BOOT_JSON.md](MODLOADER_BOOT_JSON.md)
3. 使用官方模板创建第一个 Mod
4. 参考 [MODLOADER_FAQ.md](MODLOADER_FAQ.md) 的开发问题章节

**预计时间**: 2-3 小时

### 高级（深度定制）

1. 阅读所有文档
2. 研究官方源码：https://github.com/Lyoko-Jeremie/sugarcube-2-ModLoader
3. 阅读官方中文流程文档：ModLoaderAndModLoadingProcess - CN.md
4. 实践 Addon 开发

**预计时间**: 1-2 天

---

## ✅ 总结

本知识库提供：
- ✅ **完整覆盖**: 从入门到进阶的所有内容
- ✅ **实战导向**: 基于 DOL-X 真实项目经验
- ✅ **持续更新**: 随 ModLoader 版本更新
- ✅ **易于查找**: 模块化设计 + 详细索引

**下一步**: 选择适合你的文档开始学习！

---

**最后更新**: 2026-06-11  
**维护者**: DOL-X 项目团队
