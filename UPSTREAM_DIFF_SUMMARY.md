# DOL-X 与上游 Lyra 的差异总结

**生成日期**: 2026-06-13  
**上游仓库**: https://github.com/DoL-Lyra/Lyra  
**对比分支**: upstream/vega...vega

---

## 执行摘要

DOL-X 是 DoL-Lyra/Lyra 的自用整合包 Fork，保持核心构建系统与上游同步，同时维护独立的 Mod 矩阵和实验性功能。

**同步策略**: 核心同步 + Mod 独立

---

## 1. 核心差异

### 1.1 身份标识（`config/build.toml`）

| 配置项 | DOL-X | 上游 Lyra |
|--------|-------|-----------|
| **name** | `XFox` | `Lyra` |
| **apk_name** | `DoL XFox` | `DoL Lyra` |
| **package** | `com.vrelnir.dol.xfox` | `com.vrelnir.dol.lyra` |
| **GitHub owner** | `sakarie9` | `sakarie9` |
| **GitHub repo** | `DoL-Lyra` | `DoL-Lyra` |

**目的**: 区分自用构建和上游官方构建

---

## 2. Mod 矩阵差异（`config/combinations.toml`）

### 2.1 当前 DOL-X 配置（2026-06-13 更新）

```toml
build_codes = ["57600", "58624", "59648", "61696"]
base_code = 57600
recommended = "57600"
```

**计算**（修复后）:
- `57600` = UCB (256) + more_love (8192) + custom_spellbook (16384) + cheatExtended+maplebirch (32768)
- `58624` = 57600 + AU-F (1024)
- `59648` = 57600 + AU-M (2048)
- `61696` = 57600 + AU-A (4096)

**关键修复**：移除了错误的 BESC (bit 1)，因为：
1. UCB 会覆盖 BESC 的战斗图片（应用顺序：BESC → UCB）
2. 上游不推荐 BESC+UCB 组合（code=259）
3. DOL-X 选择 UCB 作为唯一战斗美化

### 2.2 与上游 DoL-Lyra 的对比

**上游推荐矩阵**（参考 v0.5.8.10-3.1.3a-0401）:

| Build Code | 组合 | 推荐度 |
|------------|------|--------|
| 3 | BESC | ⭐⭐⭐ 推荐 |
| 35 | BESC + HIKARI | ⭐⭐⭐ 推荐 |
| 514 | GOOSE | ⭐⭐⭐ 推荐 |
| 1026 | AU-F | ⭐⭐⭐ 推荐 |
| 259 | BESC + UCB | ❌ 不推荐 |
| 1282 | UCB + AU-F | ❌ 不推荐 |

**DOL-X 矩阵**:

| Build Code | 组合 | 策略 |
|------------|------|------|
| 57600 | UCB + more_love + custom_spellbook + cheatExtended | 基础版 |
| 58624 | AU-F + UCB + more_love + custom_spellbook + cheatExtended | AU 女性版 |
| 59648 | AU-M + UCB + more_love + custom_spellbook + cheatExtended | AU 男性版 |
| 61696 | AU-A + UCB + more_love + custom_spellbook + cheatExtended | AU 中性版 |

### 2.3 核心差异说明

| 对比项 | 上游 Lyra | DOL-X | 理由 |
|--------|-----------|-------|------|
| **基础美化** | BESC | UCB | 战斗美化优先，避免 BESC+UCB 覆盖 |
| **AU 组合** | AU（单独） | AU+UCB | 美化范围互补（AU=体型，UCB=战斗） |
| **BESC** | ✅ 推荐 | ❌ 不使用 | UCB 会覆盖，选择其一 |
| **作弊 Mod** | cheat + CSD | cheatExtended + maplebirch | 功能更强，更新活跃 |
| **矩阵大小** | ~10 个版本 | 4 个版本 | 自用精简，质量优先 |

### 2.4 关键特性状态

| Feature | DOL-X | 上游 | 说明 |
|---------|-------|------|------|
| **BESC** | ❌ 禁用 | ✅ 推荐 | DOL-X 选择 UCB |
| **UCB** | ✅ 启用 | ⚠️ 不推荐单独 | DOL-X 作为基础美化 |
| **AU + UCB** | ✅ 启用 | ❌ 不推荐 | DOL-X 组合使用 |
| **more_love** | ✅ 默认 | ⚠️ 可选 | 扩展恋人数量 |
| **custom_spellbook** | ✅ 默认 | ⚠️ 可选 | 自定义魔法书 |
| **cheatExtended** | ✅ 实验性 | ❌ 无 | 替代 cheat + CSD |
| **maplebirch** | ✅ 主框架 | ❌ 无 | 秋枫白桦框架 |

### 2.5 详细决策文档

详见 [`MOD_MATRIX_RATIONALE.md`](MOD_MATRIX_RATIONALE.md)，包含：
- 为什么使用 UCB 而非 BESC
- 为什么 AU 版本使用 AU+UCB 组合
- 为什么包含 more_love + custom_spellbook
- 为什么使用 cheatExtended+maplebirch
- 技术实现细节（imagepack 应用顺序）
- 未来调整可能性

---

## 3. 特有功能

### 3.1 逆向分析工具

DOL-X 新增：
- [`tools/reverse_au_face.py`](tools/reverse_au_face.py) - AU Face 逆向分析
- [`tools/au_face_interceptor.js`](tools/au_face_interceptor.js) - 浏览器拦截器
- [`docs/MOD_REVERSE_ENGINEERING_GUIDE.md`](docs/MOD_REVERSE_ENGINEERING_GUIDE.md) - 逆向工程指南
- [`.github/workflows/reverse-au-face.yml`](.github/workflows/reverse-au-face.yml) - 自动化逆向工作流

**目的**: 分析私有/加密 mod 的依赖关系

### 3.2 兼容性注册表

DOL-X 新增：
- [`lyra/compatibility.py`](lyra/compatibility.py) - 兼容性注册表系统
- [`tests/test_compatibility_registry.py`](tests/test_compatibility_registry.py) - 兼容性测试

**目的**: 管理 mod 间的兼容性表面和补丁策略

### 3.3 cheatExtended 金丝雀系统

DOL-X 新增：
- [`tools/cheat_extended_canary.py`](tools/cheat_extended_canary.py) - 金丝雀构建系统
- [`tests/test_cheat_extended_canary.py`](tests/test_cheat_extended_canary.py) - 金丝雀测试

**目的**: 在实验性 profile 中测试 cheatExtended 集成

### 3.4 AU 系列集成

DOL-X 新增：
- [`docs/AU_MODS_DEPENDENCY_ANALYSIS.md`](docs/AU_MODS_DEPENDENCY_ANALYSIS.md) - AU mod 依赖分析
- [`docs/AU_MODS_INTEGRATION.md`](docs/AU_MODS_INTEGRATION.md) - AU mod 集成指南
- [`tests/test_au_face_compat.py`](tests/test_au_face_compat.py) - AU Face 兼容性测试
- [`tools/au_artifact_check.py`](tools/au_artifact_check.py) - AU 产物检查
- [`tools/au_matrix_gate.py`](tools/au_matrix_gate.py) - AU 矩阵门控

**目的**: 深入集成 AU 系列 mod（AU Face、AU 武术、AU 小巷）

---

## 4. 工作流差异

### 4.1 禁用的工作流

DOL-X 可能禁用或修改：
- 在线部署工作流（如果上游有）
- 公开发布工作流

### 4.2 新增的工作流

DOL-X 新增：
- [`.github/workflows/maplebirch-version-gate.yml`](.github/workflows/maplebirch-version-gate.yml) - maplebirch 版本门控
- [`.github/workflows/baseline-candidate-gate.yml`](.github/workflows/baseline-candidate-gate.yml) - 基线候选门控
- [`.github/workflows/reverse-au-face.yml`](.github/workflows/reverse-au-face.yml) - AU Face 逆向分析
- [`.github/workflows/mod-update-check.yml`](.github/workflows/mod-update-check.yml) - Mod 更新检测

---

## 5. 测试覆盖差异

### 5.1 DOL-X 新增测试

| 测试文件 | 目的 |
|----------|------|
| `test_au_face_compat.py` | AU Face 兼容性 |
| `test_au_matrix_gate.py` | AU 矩阵门控 |
| `test_baseline_candidate_gate.py` | 基线候选验证 |
| `test_canary_payload_introspect.py` | 金丝雀负载检查 |
| `test_cheat_extended_audit.py` | cheatExtended 审计 |
| `test_cheat_extended_canary.py` | cheatExtended 金丝雀 |
| `test_compatibility_registry.py` | 兼容性注册表 |
| `test_embedded_mod_source_scan.py` | 嵌入式 mod 源码扫描 |
| `test_maplebirch_version_matrix.py` | maplebirch 版本矩阵 |
| `test_more_love_drag_patch.py` | More Love 拖放补丁 |
| `test_project_boundaries.py` | 项目边界 |

**目的**: 更严格的质量门控和实验性功能验证

---

## 6. 文档差异

### 6.1 DOL-X 特有文档

**调研与分析**:
- `FRAMEWORK_PROVIDER_RESEARCH.md` - 框架提供者源码研究
- `GREENFIELD_DESIGN_SPIKE.md` - 绿地设计探索
- `CHEATEXTENDED_REPLACEMENT_NOTES.md` - cheatExtended 替换笔记
- `CHEATEXTENDED_SOURCE_ANALYSIS.md` - cheatExtended 源码分析
- `DOL-X_PROJECT_REVIEW.md` - DOL-X 项目审阅
- `TECHNICAL_FEASIBILITY_ASSESSMENT_REPORT.md` - 技术可行性评估

**集成指南**:
- `AU_APK_RUNTIME_INVESTIGATION.md` - AU APK 运行时调查
- `docs/AU_MODS_DEPENDENCY_ANALYSIS.md` - AU mod 依赖分析
- `docs/AU_FACE_DEPENDENCY_ANALYSIS_FINAL.md` - AU Face 最终依赖分析
- `docs/REVERSE_AU_FACE_GUIDE.md` - AU Face 逆向指南
- `docs/MOD_REVERSE_ENGINEERING_GUIDE.md` - Mod 逆向工程指南

**策略与清单**:
- `UPSTREAM_FRIENDLY_STRATEGY.md` - 上游友好策略
- `UPSTREAM_SYNC_CHECKLIST.md` - 上游同步清单
- `CHEAT_EXTENDED_MANUAL_TEST_CHECKLIST.md` - cheatExtended 手动测试清单
- `EXPERIMENT_MERGE_PLAN.md` - 实验合并计划
- `MIGRATION_NOTICE.md` - 迁移通知

**工具与参考**:
- `docs/COMMUNITY_TOOLS.md` - 社区工具指南
- `QUICK_REFERENCE.md` - 快速参考
- `docs/MODLOADER_*.md` - ModLoader 系列文档

---

## 7. 同步策略

### 7.1 保持同步（从上游拉取）

✅ **核心构建系统** (`lyra/`)
- `lyra/build.py` - 构建逻辑
- `lyra/combo.py` - 组合计算器
- `lyra/config_loader.py` - 配置加载器
- `lyra/parallel.py` - 并行执行
- Bug 修复和性能优化

✅ **通用工具改进** (`tools/` 部分)
- HTML/Browser/APK 烟雾测试改进
- 打包和签名工具更新

✅ **依赖和配置模板**
- `requirements.txt` 更新
- CI/CD 基础设施改进

### 7.2 保持独立（不同步）

❌ **身份配置** (`config/build.toml [identity]`)
- `name = "XFox"`
- `apk_name`, `package` 等

❌ **Mod 矩阵** (`config/combinations.toml`)
- `build_codes` 列表
- `base_code`, `recommended`

❌ **实验性功能**
- cheatExtended + maplebirch 集成
- AU 系列深度集成
- 逆向分析工具

❌ **DOL-X 特有文档**
- 所有 `*_INVESTIGATION*.md`
- 所有 `*_DEPENDENCY*.md`
- 策略和清单文档

### 7.3 待评估（需审查）

⚠️ **上游新增 mod**
- 评估是否适合 DOL-X
- 检查与现有 mod 的兼容性
- 决策是否集成

⚠️ **工作流优化**
- 评估是否适用于 DOL-X 场景
- 保留自用限制（如禁用在线部署）

⚠️ **测试框架改进**
- 通用改进：同步
- 特定于上游 Mod 矩阵：不同步

---

## 8. 差异生成命令

### 8.1 生成完整差异

```bash
# 核心构建系统
git diff upstream/vega...vega -- lyra/ > output/upstream_diff_lyra.patch

# 配置文件
git diff upstream/vega...vega -- config/ > output/upstream_diff_config.patch

# 工具脚本
git diff upstream/vega...vega -- tools/ > output/upstream_diff_tools.patch

# 工作流
git diff upstream/vega...vega -- .github/workflows/ > output/upstream_diff_workflows.patch

# 测试
git diff upstream/vega...vega -- tests/ > output/upstream_diff_tests.patch

# 文档
git diff upstream/vega...vega -- docs/ *.md > output/upstream_diff_docs.patch
```

### 8.2 生成提交日志

```bash
# 提交差异
git log upstream/vega..vega --oneline --graph > output/upstream_diff_commits.txt

# 统计
git log upstream/vega..vega --oneline | wc -l  # 领先提交数
git log vega..upstream/vega --oneline | wc -l  # 落后提交数
```

---

## 9. 同步检查清单

参考 [`UPSTREAM_SYNC_CHECKLIST.md`](UPSTREAM_SYNC_CHECKLIST.md) 执行同步：

- [ ] 拉取上游最新更新 (`git fetch upstream`)
- [ ] 审查上游变更日志
- [ ] 对比核心构建系统差异
- [ ] 选择性合并通用改进
- [ ] 保留 DOL-X 身份和 Mod 矩阵
- [ ] 运行完整测试套件
- [ ] 更新本文档

---

## 10. 关键指标

### 10.1 代码行数（估算）

| 组件 | DOL-X 新增/修改 |
|------|----------------|
| 核心代码 (`lyra/`) | ~500 行（兼容性注册表） |
| 工具脚本 (`tools/`) | ~5000 行（逆向、金丝雀、门控） |
| 测试 (`tests/`) | ~3000 行（新增测试） |
| 文档 (`docs/`, `*.md`) | ~8000 行（DOL-X 文档） |
| 工作流 (`.github/workflows/`) | ~500 行（新增工作流） |

**总计**: ~17000 行 DOL-X 特有代码和文档

### 10.2 文件数量（估算）

- 新增文件: ~40 个
- 修改文件: ~20 个
- 上游同步文件: ~30 个

---

## 11. 维护建议

### 11.1 定期同步（每月）

1. 拉取上游更新
2. 审查变更日志
3. 选择性合并
4. 运行测试
5. 更新差异总结

### 11.2 重大变更（随时）

- 上游重构核心系统 → 立即评估
- 上游添加新 mod → 评估是否集成
- 上游安全修复 → 立即同步

### 11.3 文档更新（持续）

- 每次同步后更新本文档
- 记录冲突解决方案
- 维护同步决策日志

---

## 12. 联系与参考

- **上游仓库**: https://github.com/DoL-Lyra/Lyra
- **上游友好策略**: [`UPSTREAM_FRIENDLY_STRATEGY.md`](UPSTREAM_FRIENDLY_STRATEGY.md)
- **同步清单**: [`UPSTREAM_SYNC_CHECKLIST.md`](UPSTREAM_SYNC_CHECKLIST.md)
- **DOL-X 项目审阅**: [`DOL-X_PROJECT_REVIEW.md`](DOL-X_PROJECT_REVIEW.md)

---

**最后更新**: 2026-06-13  
**下次同步**: 2026-07-13（建议）  
**维护者**: DOL-X 项目组
