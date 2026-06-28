# AU Mods Integration Guide

本文档记录 AU 系列 mod（AU Face、AU 武术、AU 小巷等）的集成方法与依赖关系，基于实际测试结论。

## 核心原则

**以实测为准**：AU 系列 mod 的依赖关系通过实际游戏运行测试确认，不依赖静态分析或逆向工程。

**区分 release tag 和 asset**：`AOKIUTAGE/UTAGEsDOL3.0` 不是单一 mod 源码仓库，而是多个 AU 包的 GitHub Releases 存放地。DOL-X 必须按 release tag 与 asset 名称区分包身份。

| Release tag | 内容 | DOL-X 当前策略 |
|-------------|------|----------------|
| `mod` | AU model 与 AU imgpack | 默认只使用 `*.model_*.zip` 直装模组 |
| `facemod` | AU 面部扩展 | 当前禁用 |
| `hairmod` | AU hairplus | 不集成，发布标题标注不适配新版 |
| `psd` | 美术源文件 | 不集成 |

## 当前 AU Model 集成方式

DOL-X 与上游 `DoL-Lyra/Lyra` 一样，当前使用 AU release 里的 **model 直装模组方式**，不是 `imgpack` 覆盖图片包方式。

当前精确锁定的 model assets：

| Feature | Asset | 版本 | 状态 |
|---------|-------|------|------|
| `au-f` | `AUfemale.model_v0.9.3.zip` | v0.9.3 | 诊断中，用户复现侧边栏贴图错位 |
| `au-m` | `AUmale.model_v0.4.2.zip` | v0.4.2 | 需用最新构建重新测试 |
| `au-a` | `AUandrogynous.model_v0.1.1.zip` | v0.1.1 | 需用最新构建重新测试 |

`imgpack` 会覆盖 imagepack 层，和 UCB 等图片包路径更容易产生冲突。因此在上游友好策略下，默认保持 `model` 方式；只有确认 model 方式无法稳定时，才在独立诊断分支测试 `imgpack`。

## 框架依赖

### 简易框架 vs 秋枫白桦框架

**互斥关系**：简易框架和秋枫白桦框架只能二选一。

- **简易框架**（Simple Framework）：基础 ModLoader 框架的一部分。
- **秋枫白桦框架**（MaplebBirch Framework）：在简易框架基础上构建的扩展框架，包含简易框架的核心代码。

**DOL-X 项目选择**：秋枫白桦框架（maplebirch）
- 更丰富的功能
- 包含简易框架的全部基础能力
- 社区活跃度更高

## AU Mods 依赖策略

### AU Face（AU 面部扩展）

**当前状态**：禁用。AU Face 是 `facemod` release 下的独立 mod，不等同于 AU-F / AU-M / AU-A model 本体。

**依赖**：
- 必需：秋枫白桦框架（或简易框架）
- 可选：SweetAlert2Mod（用于密码输入弹窗，如果 mod 加密）

**集成方法**：
- 与秋枫白桦框架一同打包进同一个组合（combination）
- 在 `config/combinations.toml` 中确保 AU Face 和框架在同一 `codes` 列表中

**说明**：
- AU Face 的部分功能依赖框架提供的 API 钩子和注册机制
- 如果单独打包 AU Face（不含框架），运行时会因缺少依赖而出现功能异常
- AU Face 禁用后，AU model 本体仍可能影响侧边栏人物预览；这类问题应记录为 AU model / UI 交互问题，而不是自动归因到 AU Face

### AU Model 侧边栏诊断（2026-06-28）

用户最新 AU-F 测试显示：无 AU 基础包侧边栏正常，AU-F 包侧边栏人物预览出现头发/面部层错位。该包的 ModLoader 列表显示 `【AUfemale】model {v:0.9.3}`，未显示 AU Face `facemod`。

当前诊断矩阵见：`docs/AU_MODEL_DIAGNOSTIC_MATRIX_2026-06-28.md`。

下一步按以下顺序隔离：

1. Base 无 AU 作为对照组。
2. AU-F / AU-M / AU-A 三个 model 分别用最新构建测试。
3. 如 AU-F 仍出错，构建 AU-F without NeoUI 诊断包。
4. 如仍出错，构建 AU-F without Mae's Picvary / NPC Avatars 诊断包。
5. 必要时再回测 AU-F v0.8.7 判断 v0.9.3 是否回归。

### 其他 AU Mods（AU 武术、AU 小巷等）

**待测试**：目前项目主要测试了 AU Face。其他 AU mod 的框架依赖以实际测试为准。

**一般策略**：
- 首先尝试与秋枫白桦框架同包
- 如遇到加载或运行时错误，通过控制台日志排查缺失的依赖
- 更新本文档记录测试结论

## 组合配置示例

在 `config/combinations.toml` 中的典型配置：

```toml
[[combination]]
name = "ucb-au-face"
codes = [
    58110,  # maplebirch（秋枫白桦框架）
    58111,  # More Love Interests
    58112,  # Custom Spellbook
    58114,  # AU Face 面部扩展
]
enabled = true
```

**关键点**：
- `58110` (maplebirch) 必须与 `58114` (AU Face) 在同一组合中
- 框架代码（58110）应当在 mod 代码之前加载（通过 `codes` 列表顺序控制）

## 加密 Mods 说明

部分 AU mods（包括 AU Face）使用密码加密分发：
- 文件格式：`.crypt` + `.salt` + `.nonce`（libsodium chacha20poly1305 AEAD 加密）
- 密钥派生：用户输入密码 → Argon2 pwhash → 解密密钥
- **重要**：加密内容受作者版权保护，不得未经授权分发解密后的明文

**DOL-X 处理策略**：
- 不存储、不提交任何加密 mod 的密文或明文到 git 仓库
- `.gitignore` 已配置阻止 `*.crypt`、`*.salt`、`*.nonce` 文件进入版本控制
- 用户自行获取授权并本地解密后使用

## 测试与验证

### 浏览器烟雾测试

项目使用 `tools/browser_smoke_test.py` 进行自动化测试：
- 启动 Chromium headless 浏览器
- 加载游戏 HTML + ModLoader
- 监控控制台日志，检测 mod 加载错误或运行时异常

### 手动测试清单

参考 `CHEAT_EXTENDED_MANUAL_TEST_CHECKLIST.md` 中的测试流程：
1. 启动游戏并确认 ModLoader 界面出现
2. 检查 mod 列表中是否显示 AU Face
3. 进入游戏并触发面部相关功能（如镜子互动）
4. 确认无控制台错误且功能正常

## 未来扩展

- **cheatExtended**：计划替代上游的简单 cheats mod，依赖简易框架（与秋枫白桦互斥）。需在独立组合中测试。
- **更多 AU mods**：随着测试覆盖扩大，本文档会持续更新各 mod 的依赖关系。

## 参考资料

- [ModLoader 官方文档](https://github.com/Lyoko-Jeremie/DoLModLoaderBuild)
- [秋枫白桦框架说明](https://github.com/NumberSir/DoL-Lyra/tree/maplebirch)
- DOL-X 项目测试日志：`tests/test_browser_smoke.py` 输出

---

**最后更新**：2026-06-28
**维护者**：DOL-X 项目组
