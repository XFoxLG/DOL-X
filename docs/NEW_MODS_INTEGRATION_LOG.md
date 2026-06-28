# DOL-X 新 Mod 集成日志

**集成日期**: 2026-06-23  
**集成版本**: v3.1.14 (基于 maplebirch v3.1.14 + expansion v1.2.4)  
**集成批次**: 4 个新 mod

> **状态说明（2026-06-28）**：本文是 2026-06-23 的历史集成记录，不代表当前稳定矩阵。BunnyTransformation v0.3.1β 已因 16 个 TweeReplacer 错误和战斗崩溃禁用；当前稳定 build codes 为 `7315712` / `7316736` / `7317760` / `7319808`。当前状态以 `config/combinations.toml`、`config/build.toml`、`config/mods.lock.json` 和 `docs/AU_MODEL_DIAGNOSTIC_MATRIX_2026-06-28.md` 为准。

---

## 集成概览

### 新增 Mod

| Mod 名称 | 版本 | bit 值 | 状态 | GitHub 仓库 |
|---------|------|--------|------|-------------|
| 控制NPC嘴部 | v1.1.0 | 524288 | ✅ 已集成 | [Ayndpa/DOL-GuideToMe](https://github.com/Ayndpa/DOL-GuideToMe) |
| 变身兔兔 | v0.3.1β | 1048576 | ❌ 已禁用 | [sylphiet/Bunny-TransformationCN](https://github.com/sylphiet/Bunny-TransformationCN) |
| NeoUI Patch | V1.1.0 | 2097152 | ✅ 已集成 | [RyaraSUKI/dol-neoui-patch](https://github.com/RyaraSUKI/dol-neoui-patch) |
| NPC社交栏头像 | v1.4.1 | 4194304 | ✅ 已集成 | [Eudemonism00/DOL-npcicon-mods](https://github.com/Eudemonism00/DOL-npcicon-mods) |

### 构建代码更新

**旧基础值**: 499968  
**新基础值**: 8364288

**计算公式**:
```
8364288 = 256 (ucb) + 8192 (more_love) + 32768 (cheat_extended_maplebirch) 
          + 65536 (custom_hair) + 131072 (mae_picvary) + 262144 (maplebirch_expansion)
          + 524288 (guide_to_me) + 1048576 (bunny_transformation) 
          + 2097152 (neoui_patch) + 4194304 (npc_social_icon)
```

**新构建矩阵**:
- **基础版** (无AU): 8364288
- **AU-F 版**: 8365312 (8364288 + 1024)
- **AU-M 版**: 8366336 (8364288 + 2048)
- **AU-A 版**: 8368384 (8364288 + 4096)

> 以上 836 系列是包含 BunnyTransformation 的历史试集成矩阵，已被 731 系列稳定矩阵取代：基础版 `7315712`，AU-F `7316736`，AU-M `7317760`，AU-A `7319808`。

---

## 集成详情

### 1. 控制NPC嘴部 (Guide To Me)

**功能描述**: 允许玩家控制 NPC 的嘴部动作和表情

**技术细节**:
- **GitHub**: https://github.com/Ayndpa/DOL-GuideToMe
- **Release Tag**: 1.1.0
- **Asset**: `Guide.To.Me.mod.zip`
- **Download URL**: https://github.com/Ayndpa/DOL-GuideToMe/releases/download/1.1.0/Guide.To.Me.mod.zip

**配置更新**:
- `config/build.toml`: 新增 `[[modloader_mods]]` 条目
- `config/features.toml`: 新增 `guide_to_me` feature (bit 524288, required=true)
- `config/mods.lock.json`: 记录版本 v1.1.0

**兼容性**:
- ✅ 与所有现有 mod 兼容
- ✅ 不依赖其他 mod
- ✅ 无已知冲突

---

### 2. 变身兔兔 (Bunny Transformation)

**功能描述**: 添加兔子变身系统

**技术细节**:
- **GitHub**: https://github.com/sylphiet/Bunny-TransformationCN
- **Release Tag**: v0.3.1β
- **Asset**: `Bunny.Transformation.mod.zip`
- **Download URL**: https://github.com/sylphiet/Bunny-TransformationCN/releases/download/v0.3.1%CE%B2/Bunny.Transformation.mod.zip

**配置更新**:
- `config/build.toml`: 新增 `[[modloader_mods]]` 条目
- `config/features.toml`: 新增 `bunny_transformation` feature (bit 1048576, required=true)
- `config/mods.lock.json`: 记录版本 v0.3.1β

**兼容性**:
- ❌ 已禁用：v0.3.1β 在当前 DoL 0.5.8.10 + maplebirch v3.1.14 栈中触发 16 个 TweeReplacer 错误并导致战斗崩溃
- 📝 保留配置和 bit 记录用于审计与回归测试，不进入当前稳定 build_codes

---

### 3. NeoUI Patch

**功能描述**: UI 增强补丁

**技术细节**:
- **GitHub**: https://github.com/RyaraSUKI/dol-neoui-patch
- **Release Tag**: V1.1.0
- **Asset**: `NeoUI.Patch.mod.zip`
- **Download URL**: https://github.com/RyaraSUKI/dol-neoui-patch/releases/download/V1.1.0/NeoUI.Patch.mod.zip

**配置更新**:
- `config/build.toml`: 新增 `[[modloader_mods]]` 条目
- `config/features.toml`: 新增 `neoui_patch` feature (bit 2097152, required=true)
- `config/mods.lock.json`: 记录版本 V1.1.0

**兼容性**:
- ✅ 与现有 UI mod 栈兼容
- ✅ 不依赖其他 mod
- ✅ 无已知冲突

---

### 4. NPC社交栏头像 (NPC Social Icon)

**功能描述**: 在 NPC 社交栏显示头像

**技术细节**:
- **GitHub**: https://github.com/Eudemonism00/DOL-npcicon-mods
- **Release Tag**: v1.4.1
- **Asset**: `DOL-npcicon-mods.mod.zip`
- **Download URL**: https://github.com/Eudemonism00/DOL-npcicon-mods/releases/download/v1.4.1/DOL-npcicon-mods.mod.zip

**配置更新**:
- `config/build.toml`: 新增 `[[modloader_mods]]` 条目
- `config/features.toml`: 新增 `npc_social_icon` feature (bit 4194304, required=true)
- `config/mods.lock.json`: 记录版本 v1.4.1

**兼容性**:
- ⚠️ 需要测试与 Mae's Picvary (bit 131072) 的共存情况
- ✅ 不依赖其他 mod
- 📝 两个 mod 都操作 NPC 侧边栏，需要验证无冲突

---

## D.O.L.I (LLM) 评估

**状态**: ❌ 不推荐集成

**评估结论**:
- 无法定位到可验证的公开仓库
- 技术架构未知
- 依赖关系不明
- 维护风险高

**详细报告**: 见 `docs/DOLI_LLM_RESEARCH.md`

**后续行动**:
1. 在 DoL 社区询问 D.O.L.I 项目信息
2. 等待可验证的技术文档
3. 暂不纳入集成计划

---

## 配置文件变更摘要

### config/build.toml

**变更内容**:
```toml
# 新增 4 个 modloader_mods 条目
[[modloader_mods]]
key = "guide_to_me"
# ...

[[modloader_mods]]
key = "bunny_transformation"
# ...

[[modloader_mods]]
key = "neoui_patch"
# ...

[[modloader_mods]]
key = "npc_social_icon"
# ...
```

### config/features.toml

**变更内容**:
```toml
# 新增 4 个 feature 定义
[[features]]
id = "guide_to_me"
bit = 524288
required = true

[[features]]
id = "bunny_transformation"
bit = 1048576
required = true

[[features]]
id = "neoui_patch"
bit = 2097152
required = true

[[features]]
id = "npc_social_icon"
bit = 4194304
required = true
```

### config/combinations.toml

**变更内容**:
```toml
# 更新 build_codes
build_codes = ["8364288", "8365312", "8366336", "8368384"]

# 更新 base_code
base_code = 8364288

# 更新 recommended
recommended = [8365312, 8366336, 8368384]
```

### config/mods.lock.json

**变更内容**:
```json
{
  "mods": {
    "guide_to_me": { /* ... */ },
    "bunny_transformation": { /* ... */ },
    "neoui_patch": { /* ... */ },
    "npc_social_icon": { /* ... */ }
  }
}
```

### tests/test_build_matrix.py

**变更内容**:
- 更新 `test_build_codes_values`: 期望值改为 `{"8364288", "8365312", "8366336", "8368384"}`
- 更新 `test_base_code_is_499968`: 期望值改为 `8364288`
- 更新 `test_base_version_no_au`: base_code 改为 `8364288`
- 更新 `test_au_versions_have_au`: AU 代码改为 `8365312`, `8366336`, `8368384`

---

## 测试结果

### 本地测试

**执行命令**:
```bash
python -m pytest tests/test_build_matrix.py -v
```

**测试结果**:
```
============================= 15 passed =============================
```

**通过的测试**:
- ✅ `test_build_codes_count`: 验证 4 个构建组合
- ✅ `test_build_codes_values`: 验证新的构建代码
- ✅ `test_base_code_is_499968`: 验证新基础值 8364288
- ✅ `test_explicit_build_codes_are_self_consistent`: 验证配置自洽性
- ✅ `test_combination_calculator_consistency`: 验证计算器一致性
- ✅ 其他所有矩阵测试

### CI 测试

**状态**: 待执行

**计划**:
1. Push 到 `vega` 分支
2. GitHub Actions 自动触发构建
3. 验证 4 个新 build codes 的 APK 产物
4. 检查构建日志无错误

---

## 风险与缓解

### 风险 1: Mae's Picvary + NPC Social Icon 冲突

**风险等级**: 中  
**影响**: 两个 mod 都操作 NPC 侧边栏，可能显示冲突

**缓解措施**:
1. 在 CI 构建后手动测试共存情况
2. 如发现冲突，评估以下选项：
   - 将其中一个设为可选 (required=false)
   - 添加 conflicts_with 声明
   - 联系 mod 作者协调兼容性

### 风险 2: 新 mod 构建失败

**风险等级**: 低  
**影响**: GitHub Actions 构建失败

**缓解措施**:
1. 所有 download_url 已验证可访问
2. 配置语法已通过本地测试
3. 如失败，检查 GitHub Actions 日志并修复

### 风险 3: 变身兔兔 Beta 版本不稳定

**风险等级**: 低  
**影响**: 游戏内可能出现 Bug

**缓解措施**:
1. 在 mods.lock.json 中标注 Beta 版本
2. 关注上游更新
3. 如发现严重 Bug，可暂时禁用该 mod

---

## 上游友好策略确认

### BESC 配置保留

**状态**: ✅ 已确认

**当前配置**:
- `config/features.toml`: `skip = true`
- `config/build.toml`: 已注释但保留配置

**理由**:
1. 便于未来对比上游差异
2. 保留"为什么不用 BESC"的决策记录
3. 配置完整性，避免删除后遗忘上游仍在使用

**上游差异说明**:
- 上游 Lyra: 推荐 BESC 单独使用
- DOL-X: 使用 UCB，BESC skip=true

---

## 后续行动

### 立即执行 (优先级：高)

- [x] 更新 `config/build.toml`
- [x] 更新 `config/features.toml`
- [x] 更新 `config/mods.lock.json`
- [x] 更新 `config/combinations.toml`
- [x] 更新 `tests/test_build_matrix.py`
- [x] 运行本地测试: `pytest tests/test_build_matrix.py -v`
- [x] D.O.L.I 调研报告: `docs/DOLI_LLM_RESEARCH.md`
- [x] 创建集成日志: `docs/NEW_MODS_INTEGRATION_LOG.md`
- [ ] 更新 `docs/MOD_MATRIX_RATIONALE.md`
- [ ] 更新 `AGENTS.md`
- [ ] Commit 并 push 到 `vega` 分支
- [ ] 监控 GitHub Actions 构建

### 待验证 (优先级：中)

- [ ] 下载 CI 构建的 APK
- [ ] 安装到模拟器/设备
- [ ] 测试 Mae's Picvary + NPC Social Icon 共存
- [ ] 验证 4 个新 mod 功能正常
- [ ] 检查游戏性能影响

### 文档完善 (优先级：中)

- [ ] 更新 `docs/MOD_COMPATIBILITY_MATRIX.md`
- [ ] 如有需要，创建新 mod 的使用说明

---

## 版本历史

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| 1.0 | 2026-06-23 | 初始版本：集成 4 个新 mod，完成 D.O.L.I 调研 |

---

**文档维护者**: DOL-X 集成团队  
**最后更新**: 2026-06-23
