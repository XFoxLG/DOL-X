# DOL-X Mod 矩阵决策说明

**最后更新**: 2026-06-15  
**版本**: v1.0

---

## 上游友好声明

根据 [上游友好策略](UPSTREAM_FRIENDLY_STRATEGY.md)，Mod 矩阵属于 DOL-X 自治范围：

> **保留 DOL-X 的（不同步）**
> - Mod 矩阵：`config/combinations.toml` 中的 `build_codes`

本文档说明 DOL-X 的 Mod 选择和组合策略，以及与上游 DoL-Lyra 的差异。

---

## 当前 Mod 矩阵

### 构建代码

| Build Code | 组合 | 说明 |
|------------|------|------|
| 499968 | UCB + more_love + cheatExtended + custom_hair + mae_picvary + maplebirch_expansion | 基础版，完整 Mod 集合 |
| 500992 | AU-F + UCB + more_love + cheatExtended + custom_hair + mae_picvary + maplebirch_expansion | 女性体型 + 完整 Mod |
| 502016 | AU-M + UCB + more_love + cheatExtended + custom_hair + mae_picvary + maplebirch_expansion | 男性体型 + 完整 Mod |
| 504064 | AU-A + UCB + more_love + cheatExtended + custom_hair + mae_picvary + maplebirch_expansion | 中性体型 + 完整 Mod |

### Feature Bits 分解

```
499968 = 256 (UCB) + 8192 (more_love) + 32768 (cheatExtended+maplebirch) + 65536 (custom_hair) + 131072 (mae_picvary) + 262144 (maplebirch_expansion)
500992 = 499968 + 1024 (AU-F)
502016 = 499968 + 2048 (AU-M)
504064 = 499968 + 4096 (AU-A)
```

---

## 与上游 DoL-Lyra 的差异

### 上游策略（参考 v0.5.8.10-3.1.3a-0401）

**推荐版本**：
- BESC（单独，code=3）
- BESC+HIKARI（code=35）
- GOOSE（单独，code=514）
- AU-F（单独，code=1026）

**非推荐版本**：
- BESC+UCB（code=259）
- UCB+AU-F（code=1282）

**上游文档**: https://dol-lyra.github.io/hub/docs/

### DOL-X 策略

**选择**：
- 基础版：UCB（单独）
- AU 版本：AU+UCB（组合）
- **不使用 BESC**（features.toml 中 skip=true）

**差异总结**：

| 对比项 | 上游 Lyra | DOL-X |
|--------|-----------|-------|
| 推荐基础美化 | BESC | UCB |
| AU 组合 | AU（单独） | AU+UCB |
| BESC 使用 | 推荐使用 | **不使用（skip=true）** |
| 额外 Mod | cheat + CSD | more_love + custom_spellbook + cheatExtended+maplebirch + custom_hair + mae_picvary + maplebirch_expansion |

---

## 决策理由

### 为什么使用 UCB 而非 BESC？

**配置状态**：
- `config/features.toml`: BESC 设置为 `skip=true`（跳过，不生成包含此功能的组合）
- `config/build.toml`: BESC 配置保留但添加注释说明不使用
- `config/combinations.toml`: build_codes 不包含 BESC bit（bit 1）

**决策理由**：

1. **战斗覆盖**
   - UCB（Universal Combat Beautification）专注战斗场景美化
   - BESC 覆盖更广但与 AU 系列存在策略分歧（上游分开发布）

2. **与 AU 的兼容性**
   - 上游虽推荐 AU（单独），但也提供 UCB+AU 组合（code=1282/2306/4354）
   - UCB 和 AU 的美化范围互补（UCB=战斗，AU=体型+特写）

3. **实际效果**
   - 构建系统按顺序应用 imagepack：BESC → HIKARI → GOOSE → UCB
   - 如果同时包含 BESC 和 UCB，UCB 会覆盖 BESC 的战斗图片
   - 因此 BESC+UCB 组合中，最终效果接近 UCB（单独）
   - **上游也不推荐 BESC+UCB 组合**（code=259）

4. **自用定位**
   - DOL-X 是自用整合包，战斗美化优先级高于综合美化
   - UCB 图片质量稳定，更新活跃
   - 避免冗余下载和构建时间

5. **配置保留**
   - `config/build.toml` 中保留 BESC imagepack 配置
   - 未来如需恢复：修改 `features.toml` 中 `skip=false`，添加 bit 1 到 build_codes
   - 保留配置方便快速回退决策

### 为什么 AU 版本使用 AU+UCB？

1. **上游先例**
   - 上游虽不推荐，但提供了 UCB+AU-F/M/A 组合
   - 说明技术上这两者可以共存

2. **美化范围互补**
   - AU：体型美化（胸部、生殖器等）+ 特写头像
   - UCB：战斗场景美化（NPC、动作等）
   - 两者覆盖范围不重叠

3. **用户体验**
   - AU 用户仍能享受战斗美化
   - 避免"选择 AU 就没有战斗美化"的遗憾

### 为什么包含 more_love + custom_spellbook？

1. **功能增强**
   - More Love Interests Mod：扩展恋人数量
   - Custom Spellbook：自定义魔法书

2. **稳定性**
   - 两者都是成熟稳定的 Mod
   - 更新活跃，维护良好

3. **默认启用**
   - DOL-X 定位为"功能完整的整合包"
   - 用户可通过 ModLoader 禁用不需要的 Mod

### 为什么使用 cheatExtended+maplebirch？

1. **替代旧作弊**
   - 上游使用 cheat + CSD（战斗状态显示）
   - DOL-X 使用 cheatExtended（功能更强，更新更频繁）

2. **框架选择**
   - cheatExtended 支持两种框架：Simple Frameworks / maplebirch
   - DOL-X 选择 maplebirch（更完整的框架实现）

3. **长期维护**
   - cheatExtended 作者活跃，持续更新
   - 功能可替代上游的 cheat + CSD

### 为什么添加 CustomHair（自定义染发）？

**添加时间**: 2026-06-15

- **功能**: 扩展默认的染发颜色选项
- **来源**: https://github.com/HiddenCirno/DoL-CustomHair
- **兼容性**: 纯美化 mod，无框架依赖，与现有 mod 无冲突
- **类型**: ModLoader mod，作为必选包含在所有构建中
- **决策**: 作为轻量级美化增强，不影响游戏平衡

### 为什么添加 Mae's Picvary（NPC侧边栏头像）？

**添加时间**: 2026-06-15

- **功能**: 在侧边栏显示 NPC 的二次创作小头像，根据态度和状态变化表情
- **来源**: https://github.com/Maenoko/Mae-s-Picvary-NPC-mod
- **兼容性**: 纯 UI mod，不影响游戏逻辑，与现有 mod 无冲突
- **类型**: ModLoader mod，作为必选包含在所有构建中
- **注意**: 只有 main 分支，模组列表中提到的 "DOL 分支" 可能已合并
- **决策**: 增强 UI 体验，不影响游戏机制

### 为什么移除 Custom-Spellbook？

**移除时间**: 2026-06-17  
**移除原因**: 实际游戏测试发现功能重复

**测试发现**：
- Cheat Extended v1.17 的"自定义言灵集"功能与 Custom-Spellbook 高度重叠
- Cheat Extended 提供的言灵集管理（新增、编辑、删除）已满足需求
- Custom-Spellbook 的"跨存档保存"功能使用频率低
- 密码输入（`DOL-Custom-Spellbook-Mod`）增加启动摩擦

**功能对比**：

| 功能 | Custom-Spellbook | Cheat Extended 言灵集 |
|------|------------------|-----------------------|
| 新增言灵 | ✅ | ✅ |
| 编辑言灵 | ✅ | ✅ |
| 删除言灵 | ✅ | ✅ |
| 手动执行 | ✅ | ✅ |
| 快速预设 | ❌ | ✅ (Quick Yanling) |
| 跨存档保存 | ✅ (IndexedDB) | ❌ |
| 导出/导入 | ✅ (JSON) | ❌ |
| 批量操作 | ✅ | ❌ |
| 侧边栏集成 | ❌ | ✅ |
| 密码保护 | ✅ (启动时输入) | ❌ (无摩擦) |

**保留 Cheat Extended 的优势**：
- 原生集成，无需额外密码
- 自动执行机制更符合作弊场景
- Quick Yanling 提供预设快捷功能
- 与侧边栏深度集成
- 无启动摩擦（Custom-Spellbook 每次启动需输入密码）

**Custom-Spellbook 的独特功能使用频率评估**：
- **跨存档保存**：实际使用中频率极低（大部分用户每个存档使用不同的言灵）
- **导出/导入**：备份场景少见（言灵代码简单，重新输入成本低）
- **批量操作**：使用场景有限

**决策**：移除 Custom-Spellbook，简化 mod 栈。

**Build Code 变化**：
- 旧版：516352（包含 bit 16384）
- 新版：499968（移除 bit 16384）
- 差值：-16384

**来源**：
- Custom-Spellbook: https://github.com/ZeroRing233/DOL-Custom-Spellbook-Mod
- Cheat Extended: https://github.com/chris81605/Degrees-of-Lewdity_Cheat_Extended

### 为什么使用 maplebirchExpansion 而非独立 LongerCombat？

**替换时间**: 2026-06-15  
**原 Mod**: LongerCombat Fixed (ReFix V2.4 by 隨風飄逸)  
**新 Mod**: maplebirchExpansion v1.2.4 (官方框架扩展)

**替换原因**：

1. **版本冲突问题**
   - 独立 LongerCombat mod 的 `boot.json` 声明依赖 Simple Frameworks v2.0.5
   - DOL-X 使用 maplebirch v4.1.7，导致依赖检查失败
   - 运行时出现 `setup is not defined` 等致命错误

2. **官方集成**
   - maplebirchExpansion 是 maplebirch 框架的官方扩展包
   - 由框架作者 MaplebirchLeaf 维护，兼容性有保障
   - v1.2.4 更新日志明确提到"删除更长遭遇战的中途射精功能"、"优化更长遭遇战衔接文本"
   - 说明该扩展包**已内置更长遭遇战功能**

3. **功能更丰富**
   - 除了更长遭遇战，还包含：
     - 作弊集（额外的作弊功能）
     - 音乐播放器
     - 定制纹身系统
     - 核心属性扩展：理智、灵性
     - 新增恐惧/侵蚀状态
     - 6级等级属性提升至7级
     - 日食新月触发规则
   
4. **完美兼容**
   - 专为 maplebirch v4.x 设计
   - 不会出现框架版本检查失败
   - 无需非官方修复补丁

5. **长期维护**
   - 官方扩展包持续更新（最新版 2026-03-11）
   - 与框架同步更新，兼容性有保障
   - 独立 LongerCombat 原作者已停更

**技术对比**：

| 对比项 | LongerCombat Fixed | maplebirchExpansion |
|--------|-------------------|---------------------|
| 维护状态 | 非官方修复，原作者停更 | 官方维护，持续更新 |
| 框架兼容 | boot.json 依赖冲突 | 原生兼容 v4.x |
| 功能范围 | 仅遭遇战延长 | 遭遇战+作弊+音乐+纹身+属性 |
| 安装方式 | GitHub Issue 附件 | GitHub Release |
| 版本管理 | 无版本号追踪 | 有明确版本标签 |

**决策**：使用 maplebirchExpansion 代替独立的 LongerCombat，bit 262144 保持不变。

**来源**：
- 官方仓库: https://github.com/MaplebirchLeaf/SCML-DOL-maplebirchExpansion
- Release: https://github.com/MaplebirchLeaf/SCML-DOL-maplebirchExpansion/releases/tag/release-v1.2.4

### 为什么不添加旧版作弊扩展（HSSkyBoy）？

**调研时间**: 2026-06-15

- **原因**: 新版作弊扩展（chris81605）完全覆盖旧版所有 16 项功能
- **作者关系**: 隨風飄逸（原版）→ HSSkyBoy（二开，2024-08-23 停更）→ chris81605（隨風飄逸继续更新，2026-03-25）
- **功能对比**: 新版包含 30+ 项功能，包括旧版所有功能并大幅扩展
- **维护状态**: 新版持续更新，旧版停更 19 个月
- **决策**: DOL-X 已使用新版，无需添加旧版

---

## 技术实现细节

### Imagepack 应用顺序

代码位置：[`lyra/build.py`](lyra/build.py) 第 329-350 行

```python
# 按顺序处理美化
order = [
    ModCode.BESC,           # 1. 先应用 BESC（如果启用）
    ModCode.SIDEVIEW_HIKARI,# 2. 应用 HIKARI（如果启用）
    ModCode.SIDEVIEW_GOOSE, # 3. 应用 GOOSE（如果启用）
    ModCode.UCB,            # 4. 最后应用 UCB（会覆盖前面的）
]
```

**关键点**：UCB 最后应用，会覆盖之前的图片。

### 为什么上游不推荐 BESC+UCB？

从技术角度看：
1. UCB 会覆盖 BESC 的部分图片
2. BESC 的优势（覆盖面广）被削弱
3. 不如直接使用 BESC（单独）或 UCB（单独）

DOL-X 的选择：
- 既然会覆盖，不如直接移除 BESC，只用 UCB
- 节省图片包下载和构建时间

---

## 技术验证

**UCB 与 AU 兼容性验证**:

根据 [UCB 兼容性验证报告](docs/UCB_COMPATIBILITY_REPORT.md) 的深度分析：

1. **UCB 官方设计**: 仅替换战斗图片（DoLModding Wiki 明确说明）
2. **路径无重叠**: UCB 在 `img/sex/`、`img/combat/`，AU 在 `img/body/`、`img/face/`
3. **加载机制不同**: AU 通过 ModLoader 运行时加载，优先级高于 imagepack
4. **兼容性保障**: DOL-X 已实现 `_apply_au_face_compatibility_aliases()` 处理路径别名

**结论**: UCB + AU 组合技术可行，不存在冲突。

详细验证过程见 [UCB_COMPATIBILITY_REPORT.md](docs/UCB_COMPATIBILITY_REPORT.md)。

---

## 未来调整可能性

### 可能添加的 Mod

参考上游和社区：
- HIKARI（特写美化，依赖 BESC）
- GOOSE（特写美化）
- 其他新兴 Mod

### 可能的矩阵扩展

当前矩阵较小（4 个版本），未来可能：
1. 添加 GOOSE 版本（如果需求高）
2. 添加纯净版（无美化，只有 more_love + custom_spellbook + cheatExtended）
3. 添加 BESC 版本（如果用户反馈需要）

### 决策流程

参考 [`UPSTREAM_FRIENDLY_STRATEGY.md`](UPSTREAM_FRIENDLY_STRATEGY.md) 第 5 节：
1. 评估 Mod 来源和质量
2. 测试兼容性
3. 记录决策理由
4. 更新本文档

---

## 结论

DOL-X 的 Mod 矩阵设计遵循以下原则：

1. **最小化冲突**：移除会被后续 mod 覆盖的内容（如 BESC）
2. **保持简洁**：只包含必需的 mod，避免冗余
3. **上游友好**：核心构建系统保持兼容，Mod 选择在自治范围内
4. **官方优先**：优先选择官方维护的版本（如 maplebirchExpansion）
5. **功能完整**：优先选择功能更强、维护更活跃的版本（如新版作弊扩展）

---

**维护者**: DOL-X 团队  
**最后更新**: 2026-06-15

## 参考资料

### 上游文档
- [DoL-Lyra 版本说明](https://dol-lyra.github.io/hub/docs/)
- [DoL-Lyra 下载页面](https://dol-lyra.github.io/hub/downloads/v0.5.8.10-3.1.3a-0401/)

### DOL-X 文档
- [上游友好策略](UPSTREAM_FRIENDLY_STRATEGY.md)
- [上游同步清单](UPSTREAM_SYNC_CHECKLIST.md)
- [配置文件说明](config/README.md)

### 技术文档
- [构建系统实现](lyra/build.py)
- [Feature 定义](config/features.toml)
- [Combinations 配置](config/combinations.toml)
