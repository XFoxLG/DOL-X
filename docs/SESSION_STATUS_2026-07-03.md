# 会话状态 2026-07-03

承接 2026-07-02 会话。上一份 `SESSION_STATUS_2026-07-02.md` 记录了 D.O.L.I 落地与 AGENTS.md 退役，本会话为准备首个正式 Release 做准备。

## 一句话现状

当前工作区干净（commit `11de1c6`），build_codes 为 15704320 系列（4 个构建：base + AU-F/M/A，包含 D.O.L.I + NeoUI）。用户要求先保存进度到记忆/文档，然后调研上游 Lyra 的 CSD 及相关源码，为发版做准备。

## 本会话待办事项

### 1. ✅ 回退错误操作

早前误操作试图集成 CSD 但实际未修改 combinations.toml，导致测试失败。已通过 `git reset --soft HEAD~1` + `git restore` 回退到干净状态（commit `11de1c6`）。

### 2. ⏳ 调研上游 Lyra 的 CSD 实现

用户要求全面调研上游 DoL-Lyra 的 CSD (战斗状态显示) 及所有相关源码，了解：
- CSD 的技术实现方式
- 在上游构建系统中的集成方式
- 与其他 mod 的依赖关系
- 是否适合集成到 DOL-X

### 3. ⏳ 准备首个正式 Release

用户要求准备首个正式 GitHub Release，需要：
- 详尽完整深入地写出本项目和上游的差异、区别
- 按照 Keep a Changelog 和 SemVer 最佳实践更新 CHANGELOG
- 了解 GitHub Releases 的各个组成部分用途

## 提交记录

本会话暂无新提交。当前停留在：
- `11de1c6` — docs: record D.O.L.I landing in session status, align changelog codes

## 待办 / 下一步

### 发版准备（用户请求）

用户要求准备首个正式 Release，具体要求：
1. **详尽完整深入地写出本项目和上游的差异、区别**
2. **按照 Keep a Changelog 和 SemVer 最佳实践更新 CHANGELOG**
3. **了解 Releases 的各个组成部分用途**（参考 https://github.com/XFoxLG/DOL-X/releases）
4. 教程慢慢来（后续）

### 发版流程（待执行）

1. ⏳ 确定版本号（按 SemVer，需与用户讨论）
2. ⏳ 完善 CHANGELOG（可能需要重组 Unreleased 段为具体版本）
3. ⏳ 编写 Release 说明（与上游 Lyra 的差异对比）
4. ⏳ 创建 Git tag
5. ⏳ 推送并触发 CI 构建
6. ⏳ 在 GitHub 创建 Release（附带构建产物）

### 其他待办

- 首次 D.O.L.I CI 构建加载日志验证（确认与 NeoUI/maplebirch 共存）
- 美化包冲突（inuno/犬野等）仍暂缓，后续单独规划

## 当前配置口径

- `config/combinations.toml`: build codes **15704320 / 15705344 / 15706368 / 15708416** (4 个)，base_code=15704320
- `config/features.toml`: 
  - doli(8388608, required) ✅
  - neoui_patch(2097152, required) ✅
  - bunny_transformation skip=true ❌
  - au_face enabled=false ❌
  - **CSD 尚未集成**
- `config/build.toml`: 
  - DOLI 钉死 v0.2.3
  - NeoUI Patch 钉死 v1.1.0
  - AU-F = AUfemale.model_v0.9.3.zip
- 版本锁: maplebirch v3.1.14、cheat extended v1.17、maplebirchExpansion v1.2.4

## DOL-X 与上游 Lyra 的核心差异（为发版准备）

### 项目定位
- **DOL-X**: 自用整合包，Python 3.12+，个人维护
- **上游 Lyra**: 社区整合包，公开发行
- **Fork 源**: https://github.com/DoL-Lyra/Lyra

### 技术栈
- **构建系统**: 完全相同（Python + lyra/build.py），持续同步核心构建逻辑
- **CI/CD**: 都使用 GitHub Actions，完整构建在云端

### Mod 矩阵差异（DOL-X 自治领域）

| 维度 | 上游 Lyra | DOL-X |
|------|----------|-------|
| **版本策略** | 跟随最新 | 保守锁定 v3.1.14 栈 |
| **maplebirch** | v4.x+ | v3.1.14（expansion v1.2.4 兼容性） |
| **cheat extended** | v1.19+ | v1.17 |
| **AU 系列** | 灵活组合 | 3 个固定变体（AU-F / AU-M / AU-A） |
| **D.O.L.I** | 未集成 | v0.2.3（LLM AI 增强）|
| **CSD** | 与旧 Cheat 捆绑 | v1.0.1（独立恢复）|
| **guide_to_me** | 未集成 | v1.1.0 |
| **npc_social_icon** | 未集成 | v1.4.1 |
| **NeoUI Patch** | 未集成 | 可选（诊断用） |
| **BunnyTransformation** | 正常 | 禁用（v0.3.1β 崩溃） |
| **AU Face expansion** | 正常 | 禁用（v3.x 贴图 bug） |

### 构建矩阵
- **上游 Lyra**: 动态组合，根据规则生成
- **DOL-X**: 精确控制 5 个 build_codes，每个 code 对应明确的 mod 组合

当前 DOL-X 矩阵（30384384 系列）：
```
base      30384384  无 AU 体型
AU-F      30385408  女性体型（无 NeoUI）
AU-F+Neo  32482560  女性体型 + NeoUI（诊断对比）
AU-M      30386432  男性体型
AU-A      30388480  全体型
```

### 同步策略
- ✅ **同步**: `lyra/` 核心构建代码、游戏版本更新、本地化更新
- ❌ **不同步**: mod 矩阵决策（DOL-X 独立决策）
- 📋 **审查**: 文档和工作流改进

### 文档差异
- **DOL-X 特有**:
  - `docs/SESSION_STATUS_*.md` - 会话状态跟踪
  - `docs/AU_MODEL_DIAGNOSTIC_MATRIX_*.md` - AU 诊断记录
  - `docs/WAF_TROUBLESHOOTING.md` - WAF 403 排障
  - `MOD_MATRIX_RATIONALE.md` - mod 选择决策记录
  - `.local/` 目录 - 本地测试报告（不提交）

### 使用场景
- **上游 Lyra**: 社区玩家，多种 mod 组合选择，公开 Release
- **DOL-X**: 个人自用，5 个固定构建，GitHub Actions 私有构建

## 已知噪声（承接前序会话，接受现状）

加载日志的 3 error / 2 warning（cheat v1.17 的 Widgets Market、maplebirchEx v1.2.4 的 time.js beauty、1 个 CSS、maplebirch zone 的 Eden 正则 2 warning）是版本轻微漂移导致的补丁失配，不阻断，接受现状。

## 环境约束（不变）

- **本地能跑**: pytest、git、`python main.py matrix`、curl、gh
- **本地不能**: 完整构建、APK 签名、imagepack 解压（缺 unrar）
- **完整构建**: 走 GitHub Actions
- **Windows 限制**: bash 需用 `C:\Program Files\Git\bin\bash.exe`; PowerShell 不支持 heredoc，多行提交信息走 `git commit -F 文件`

## Git 状态

- **分支**: vega
- **最新提交**: `6adc395` - feat(mod): restore CSD (CombatStatusDisplay) from upstream
- **工作区**: 有 CHANGELOG.md 和本文档的未提交改动
- **待推送**: commit `6adc395` + 即将提交的文档更新

## 下一步行动（等待用户确认）

1. 提交文档更新（CHANGELOG + SESSION_STATUS）
2. 与用户讨论版本号（SemVer 规范）
3. 编写 Release 说明（重点：与上游差异）
4. 创建 tag 并推送
5. 在 GitHub 创建 Release（附带 CI 构建的 APK）
