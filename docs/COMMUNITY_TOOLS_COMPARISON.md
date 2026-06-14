# 社区 Mod 开发工具对比

**调研日期**: 2026-06-14  
**调研人**: DOL-X 项目组

---

## 📋 概述

本文档对比了 DOL 社区中 4 个主要的 Mod 开发工具，基于 GitHub 公开信息和最新活跃度进行评估。

---

## 🔍 工具对比表

| 工具 | 语言 | Stars | 状态 | 最后更新 | 主要功能 |
|------|------|-------|------|----------|----------|
| **DoL-Commit2Mod** | Python | 2 | 🟡 活跃（低频） | 2025-04 | Git commit → Mod |
| **DoLModRspackExampleTS** | TypeScript | 4 | 🟢 非常活跃 | 2026-06 | TypeScript 开发模板 |
| **rust-mod-dev** | Rust | 0 | 🔴 已归档 | 2026-03 | CLI 打包工具 |
| **DOL-Mod-Created-Helper** | Python | 46 | 🟡 维护中 | 2026-04 | 自动化 + 测试 |

---

## 1. DoL-Commit2Mod

**仓库**: https://github.com/Lethivia/DoL-Commit2Mod  
**作者**: Lethivia

### 功能

轻量级 Python 脚本，根据 Git commit 自动生成 Mod：

- 分析指定 commit 的变更内容
- 按原目录结构放置新增文件
- 提取 Twee 文件差异 → `TweeReplacer` 参数
- 提取 JS 文件差异 → `ReplacePatcher` 参数
- 自动生成 `boot.json`

### 使用场景

```bash
python main.py --commit abc123 --name mymod --version 1.0
```

### 评估

**优点**:
- ✅ 轻量级，专注于从 Git 提交生成 Mod
- ✅ 适合快速从上游 commit 生成 Mod

**缺点**:
- ❌ 功能单一，不支持复杂的开发工作流
- ❌ 更新频率低（仅 2 次提交）

**建议**: DOL-X 已有类似功能，可参考其实现

---

## 2. DoLModRspackExampleTS ⭐ 推荐

**仓库**: https://github.com/Muromi-Rikka/DoLModRspackExampleTS  
**作者**: Muromi-Rikka  
**DOL-X Fork**: https://github.com/XFoxLG/DOL-X-TS-Mod-Template

### 功能

现代化 TypeScript + Rspack 开发模板：

- 使用 **Rspack** 构建（性能优于 Webpack）
- 完整的 **TypeScript** 支持
- 开发服务器（`pnpm dev` → `localhost:5678`）
- 自动生成 `boot.json`
- 支持材质替换（`originImage` 文件夹）
- 支持 Mod 加密（可配置密码）

### 项目结构

```
src/
├── scriptFileList/           # TypeScript 脚本
├── scriptFileList_preload/   # 预加载脚本
├── scriptFileList_earlyload/ # 早期加载脚本
├── tweeFileList/             # Twee 文件
├── styleFileList/            # CSS 文件
├── imgFileList/              # 图片
└── addonPlugin/              # 插件配置
```

### 评估

**优点**:
- ✅ **极其活跃**：几乎每天都有依赖更新（通过 Renovate bot）
- ✅ **现代化技术栈**：Rspack 2.x、ESLint 10.x、TypeScript
- ✅ **开发体验好**：热重载、类型安全、自动打包
- ✅ **模板性质**：标记为 "Public template"，鼓励使用

**建议**: **强烈推荐作为 DOL-X 的官方开发模板**（已 fork）

---

## 3. rust-mod-dev

**仓库**: https://github.com/Paul-16098/rust-mod-dev  
**状态**: 🔴 已归档（2026-03-01）

### 功能

Rust 编写的 CLI 工具：

- 扫描 `mods/` 下的每个 Mod 子文件夹
- 标准化 `boot.json`（自动补全文件列表）
- 可选 TypeScript 编译（调用 `tsc`）
- 打包为 `.zip` 文件
- 支持多语言（中文、英文、繁体中文）

### 评估

**优点**:
- ✅ 功能完善、性能好（Rust）

**缺点**:
- ❌ **已归档**，不再维护
- ❌ 缺乏社区支持（0 star）
- ❌ 需要 Rust 工具链

**建议**: 不推荐使用，除非需要高性能且愿意 fork 维护

---

## 4. DOL-Mod-Created-Helper ⭐ 推荐

**仓库**: https://github.com/NumberSir/DOL-Mod-Created-Helper  
**作者**: NumberSir

### 功能

Python 自动化工具，专注于简化 Mod 编写流程：

- 自动下载游戏源码
- 根据模组内容自动生成 `boot.json`
- 处理并打包为 `.mod.zip`
- **本地测试服务器**（`REMOTE_TEST = True`）
  - 自动启动服务器（`http://localhost:52525`）
  - 自动复制 Mod 到 ModLoader
  - 每次打包后只需刷新浏览器

### 特殊插件支持

- **TweeReplacer**：替换 `.twee` 文件中的文本
- **ReplacePatch**：替换 JS/CSS 文件内容
- **ImgLoaderHooker**：图片加载钩子

### 评估

**优点**:
- ✅ **社区认可度最高**（46 stars）
- ✅ 自动化测试流程完善
- ✅ 与 ModLoader 集成好
- ✅ 文档完善（中英文 README）

**建议**: **推荐参考其自动化测试流程**，集成到 DOL-X 工作流

---

## 🎯 推荐组合

### 方案 1：现代化开发流程（推荐）

```
DoLModRspackExampleTS（开发） + DOL-Mod-Created-Helper（打包测试）
```

**理由**:
- ✅ **开发体验好**：TypeScript + 热重载
- ✅ **自动化测试**：Python 工具提供本地服务器
- ✅ **社区支持**：两者都在活跃维护

**工作流**:
1. 使用 `DoLModRspackExampleTS` 作为项目模板
2. 使用 `pnpm dev` 进行开发
3. 使用 `DOL-Mod-Created-Helper` 打包并测试
4. 通过本地服务器快速迭代

---

### 方案 2：纯 Python 流程（简单）

```
DOL-Mod-Created-Helper（全流程）
```

**理由**:
- ✅ **一站式解决方案**
- ✅ **学习成本低**
- ❌ **缺少 TypeScript 类型检查**

---

## 🔗 与上游友好策略

### 分析

所有工具都**不与上游冲突**，因为：

1. **都依赖 ModLoader**：这些工具生成的 Mod 需要通过官方 ModLoader 加载
2. **不修改原游戏**：所有工具都是基于 Mod 系统，不直接修改游戏源码
3. **社区生态**：这些工具丰富了 DOL 的 Mod 生态，对上游有益

### 建议

- ✅ 通过 ModLoader 加载（不修改原游戏）
- ✅ 遵守原游戏许可证
- ✅ 如果基于上游 fork 开发，优先考虑贡献回流而非仅通过 Mod 修改

---

## 📚 参考资源

- DoL-Commit2Mod: https://github.com/Lethivia/DoL-Commit2Mod
- DoLModRspackExampleTS: https://github.com/Muromi-Rikka/DoLModRspackExampleTS
- rust-mod-dev: https://github.com/Paul-16098/rust-mod-dev
- DOL-Mod-Created-Helper: https://github.com/NumberSir/DOL-Mod-Created-Helper
- DOL-X TypeScript 模板: https://github.com/XFoxLG/DOL-X-TS-Mod-Template

---

**最后更新**: 2026-06-14  
**调研结论**: 推荐使用 DoLModRspackExampleTS 作为开发模板，配合 DOL-Mod-Created-Helper 的自动化测试流程
