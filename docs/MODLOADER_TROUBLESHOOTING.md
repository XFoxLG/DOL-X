# ModLoader 故障排除指南

本文档帮助你诊断和解决 ModLoader 使用过程中的常见问题。

## 目录

- [Console 日志解读](#console-日志解读)
- [Mod 冲突排查](#mod-冲突排查)
- [依赖问题诊断](#依赖问题诊断)
- [常见错误解决方案](#常见错误解决方案)
- [性能问题](#性能问题)

---

## Console 日志解读

### 如何打开 Console

- **桌面浏览器**：按 `F12` → 选择 "Console" 标签
- **Android APK**：无法直接访问（需要使用 [APK 调试工具](../tools/apk_emulator_smoke_test.py)）

### 日志级别分类

| 级别 | 颜色 | 含义 | 是否需要处理 |
|------|------|------|-------------|
| **INFO** | 白色/灰色 | 正常运行信息 | ❌ 否 |
| **WARNING** | 黄色 | 警告（功能可能受影响） | ⚠️ 建议检查 |
| **ERROR** | 红色 | 错误（功能失败） | ✅ 必须处理 |
| **FATAL** | 深红色 | 致命错误（游戏无法运行） | 🔴 立即处理 |

---

## 10 个常见错误及解决方案

### 1. `ModOrderContainer.getByNameOne() cannot find mod: <mod_name>`

**原因**：ModLoader 找不到依赖的 mod。

**症状**：
```
ModLoader ====== ModOrderContainer.getByNameOne() cannot find mod: maplebirch-framework
```

**解决方案**：
1. 检查 `boot.json` 中的 `dependenceInfo`：
   ```json
   "dependenceInfo": [
     {"modName": "maplebirch-framework", "version": "^3.0.0"}
   ]
   ```
2. 确认依赖 mod 已安装且名称正确（区分大小写）
3. 检查依赖 mod 的加载顺序（在 ModLoader GUI 中调整）

---

### 2. `bootJson文件 [boot.json] 无效`

**原因**：`boot.json` 格式错误或字段缺失。

**症状**：
- ModLoader 拒绝加载 mod
- Console 显示 "bootJson文件无效"

**解决方案**：
1. 使用 [JSON 验证器](https://jsonlint.com/) 检查语法
2. 确认必需字段存在：
   ```json
   {
     "name": "模组名称",
     "version": "1.0.0"
   }
   ```
3. 检查文件编码（必须是 UTF-8）
4. 参考 [MODLOADER_BOOT_JSON.md](MODLOADER_BOOT_JSON.md)

---

### 3. `ImageLoaderHook2BeautySelectorAddon: skip <mod_name>`

**原因**：AU 美化 mod 与其他 mod 冲突（通常是 ModI18N）。

**症状**：
```
[ImageLoaderHook2BeautySelectorAddon] canLoadThisMod: skip ModI18N
```

**解决方案**：
- ✅ **这是正常行为**！AU 美化会跳过不需要美化的 mod
- ⚠️ 如果 AU 美化本身被跳过，检查是否安装了冲突的图片包 mod

---

### 4. `ModLoader ====== IndexDBLoader loadHiddenModList() cannot find modDataIndexDBZipListHidden`

**原因**：首次加载，IndexDB 中没有隐藏 mod 列表。

**症状**：
```
ModLoader ====== IndexDBLoader loadHiddenModList() cannot find modDataIndexDBZipListHidden
```

**解决方案**：
- ✅ **这是正常行为**！首次运行会自动创建
- ⚠️ 如果反复出现，清除浏览器缓存后重试

---

### 5. `依赖模组 [<mod_name>] 版本不匹配`

**原因**：依赖 mod 的版本不满足要求。

**症状**：
```
依赖模组 [maplebirch-framework] 版本不匹配：需要 ^3.0.0，当前 2.5.0
```

**解决方案**：
1. 升级依赖 mod 到要求的版本
2. 或降级当前 mod 到兼容旧依赖的版本
3. 参考 [语义化版本规则](https://semver.org/lang/zh-CN/)

---

### 6. `ModZipReader zip was released`

**原因**：Mod 的 ZIP 文件已被释放（内存优化）。

**症状**：
```
[浏览器] ModZipReader zip was released. [Object, ModZipReader]
```

**解决方案**：
- ✅ **这是正常行为**！ModLoader 在加载完 mod 后会释放 ZIP 以节省内存
- ⚠️ 如果后续出现资源加载失败，可能是 mod 依赖懒加载

---

### 7. `Simple Frameworks lookup failed`

**原因**：cheatExtended 依赖的框架未找到。

**症状**：
```
[警告] Simple Frameworks lookup failed
```

**解决方案**：
1. 确认已安装 `maplebirch-framework` 或 `SCMLSimpleFramework`
2. 检查框架 mod 的加载顺序（必须在 cheatExtended 之前）
3. **DOL-X 用户**：maplebirch 已默认集成，应该不会出现此错误

---

### 8. `Cannot read property 'addonName' of undefined`

**原因**：AddonPlugin 注册失败或格式错误。

**症状**：
```
TypeError: Cannot read property 'addonName' of undefined
```

**解决方案**：
1. 检查 `boot.json` 中的 `addonPlugin` 格式：
   ```json
   "addonPlugin": [
     {
       "modName": "TweeReplacer",
       "addonName": "TweeReplacerAddon",
       "modVersion": "^1.0.0",
       "params": [...]
     }
   ]
   ```
2. 确认 `addonName` 字段存在且正确

---

### 9. `Passage <passage_name> not found`

**原因**：Mod 尝试修改不存在的 Passage。

**症状**：
```
[错误] Passage 'NonExistentPassage' not found
```

**解决方案**：
1. 检查 Passage 名称拼写（区分大小写）
2. 确认游戏版本与 mod 版本匹配
3. 查看 mod 的兼容性说明

---

### 10. `加载模组时发生错误：<mod_name>`

**原因**：Mod 脚本执行失败（语法错误或运行时异常）。

**症状**：
```
加载模组时发生错误：my-mod
TypeError: undefined is not a function
```

**解决方案**：
1. 查看完整错误堆栈（向上滚动 Console）
2. 检查 mod 的 JavaScript 文件是否有语法错误
3. 联系 mod 作者报告 bug

---

## Mod 冲突排查

### 冲突类型

| 冲突类型 | 症状 | 常见原因 |
|---------|------|---------|
| **API 冲突** | `<函数名> is not a function` | 多个 mod 修改同一个全局函数 |
| **Passage 覆盖** | 游戏内容错乱、文本重复 | 多个 mod 替换同一个 Passage |
| **CSS 冲突** | 界面样式异常、元素重叠 | 多个 mod 修改同一个 CSS 选择器 |
| **依赖冲突** | `版本不匹配` | 两个 mod 依赖同一个 mod 的不同版本 |

### 二分法排查步骤

**目标**：快速定位哪两个 mod 冲突。

#### 步骤 1：禁用一半 mod

1. 打开 ModLoader GUI
2. 禁用**一半**的 mod
3. 重新加载游戏
4. 测试问题是否消失

#### 步骤 2：递归缩小范围

- **问题消失**：冲突 mod 在被禁用的一半中
  - 重新启用一半的被禁用 mod
- **问题依然存在**：冲突 mod 在启用的一半中
  - 禁用当前启用 mod 的一半

#### 步骤 3：最终验证

当只剩 2 个 mod 时：
1. 分别单独启用每个 mod，确认都能正常运行
2. 同时启用两个 mod，确认冲突复现
3. 记录冲突的两个 mod 名称和版本

### 5 个真实冲突案例

#### 案例 1：AU 美化 + 图片包 mod

**症状**：AU 美化不生效，显示原版图片。

**原因**：
- 图片包 mod（如 `GameOriginalImagePack-*.mod.zip`）优先级高于游戏 `img/` 文件夹
- AU 美化直接集成在 `img/` 中，被图片包 mod 覆盖

**解决方案**：
```
卸载图片包 mod（DOL-X 已内置 AU 美化）
```

#### 案例 2：cheatExtended + 旧作弊 mod

**症状**：作弊菜单重复、功能冲突。

**原因**：
- cheatExtended 与旧的 `cheat_csd` 功能重复
- 两者同时启用导致冲突

**解决方案**：
```
禁用旧作弊 mod（bjx_word_unlock、bjx_portable_word、bccm）
cheatExtended 已包含所有旧功能
```

#### 案例 3：maplebirch-framework + SCMLSimpleFramework

**症状**：cheatExtended 无法加载，Console 报 `undefined is not a function`。

**原因**：
- 两个框架互斥，只能选择一个
- 同时启用导致 API 冲突

**解决方案**：
```
只启用 maplebirch-framework（DOL-X 默认）
或只启用 SCMLSimpleFramework（社区其他整合包）
```

#### 案例 4：ModI18N + 旧汉化 mod

**症状**：中英文混杂、翻译不完整。

**原因**：
- ModI18N 已内置最新汉化
- 旧汉化 mod 覆盖了部分翻译

**解决方案**：
```
卸载 ModLoader - 旁加载 中的汉化 mod
DOL-X 已自带最新汉化
```

#### 案例 5：More Love + 自定义事件 mod

**症状**：More Love 的拖拽功能失效。

**原因**：
- 自定义事件 mod 修改了 `preventDefaultMLIM` 函数
- 阻止了 More Love 的事件监听器

**解决方案**：
```
联系自定义事件 mod 作者，要求兼容 More Love
或使用 DOL-X 内置的 More Love 补丁
```

---

## 依赖问题诊断

### `ModOrderContainer.getByNameOne()` 失败的 5 种场景

#### 场景 1：依赖 mod 未安装

**Console 日志**：
```
ModLoader ====== ModOrderContainer.getByNameOne() cannot find mod: MyDependency
```

**诊断**：
```bash
# 检查 boot.json
"dependenceInfo": [
  {"modName": "MyDependency", "version": "^1.0.0"}
]

# 确认 MyDependency 是否在 ModLoader GUI 的 mod 列表中
```

**解决方案**：安装缺失的依赖 mod。

---

#### 场景 2：依赖 mod 名称拼写错误

**Console 日志**：
```
ModLoader ====== ModOrderContainer.getByNameOne() cannot find mod: maplebrich-framework
# 正确拼写应为 maplebirch-framework
```

**诊断**：
```bash
# 对比 boot.json 中的名称与 ModLoader GUI 中显示的名称
"dependenceInfo": [
  {"modName": "maplebrich-framework", ...}  # 拼写错误！
]
```

**解决方案**：修正 `boot.json` 中的拼写。

---

#### 场景 3：版本不匹配

**Console 日志**：
```
依赖模组 [maplebirch-framework] 版本不匹配：需要 ^3.0.0，当前 2.5.0
```

**诊断**：
```bash
# 检查版本约束
"dependenceInfo": [
  {"modName": "maplebirch-framework", "version": "^3.0.0"}
]

# 在 ModLoader GUI 中查看实际安装的版本
```

**解决方案**：
- 升级依赖 mod 到 3.x 版本
- 或修改 `boot.json` 为 `"version": ">=2.5.0"`（如果兼容）

---

#### 场景 4：加载顺序错误

**Console 日志**：
```
ModLoader ====== ModOrderContainer.getByNameOne() cannot find mod: TweeReplacer
# 但 TweeReplacer 确实已安装
```

**诊断**：
- 依赖 mod 在**当前 mod 之后**加载
- ModLoader 按列表顺序加载，无法找到"未来"的 mod

**解决方案**：
1. 打开 ModLoader GUI
2. 将依赖 mod 拖到当前 mod **上方**
3. 重新加载游戏

---

#### 场景 5：循环依赖

**Console 日志**：
```
[错误] 检测到循环依赖：ModA -> ModB -> ModA
```

**诊断**：
```
ModA 依赖 ModB
ModB 依赖 ModA
```

**解决方案**：
- 这是 mod 设计错误，无法在用户端解决
- 联系 mod 作者修复依赖关系

---

## 常见错误解决方案

### Q1：为什么我的 mod 加载后不生效？

**可能原因**：
1. ✅ **Mod 未启用**：在 ModLoader GUI 中检查复选框
2. ✅ **依赖缺失**：查看 Console 是否有 `cannot find mod` 错误
3. ✅ **加载顺序错误**：依赖 mod 必须在当前 mod 之前加载
4. ✅ **与其他 mod 冲突**：使用[二分法](#二分法排查步骤)排查

### Q2：如何升级 ModLoader 版本？

**步骤**：
1. 访问 [ModLoader 官方仓库](https://github.com/Lyoko-Jeremie/DoLModLoaderBuild/releases)
2. 下载最新的 `ModLoader_xxx.mod.zip`
3. 使用新版本 ModLoader HTML 替换旧版本
4. ⚠️ **注意**：升级 ModLoader 可能导致旧 mod 不兼容

**DOL-X 用户**：
- DOL-X 已集成最新稳定版 ModLoader
- 无需手动升级

### Q3：为什么加载速度很慢？

**可能原因**：
1. ✅ **Mod 数量过多**：每个 mod 都需要解压和加载
2. ✅ **图片资源过大**：美化 mod 通常包含大量图片
3. ✅ **使用 IndexDB**：首次加载需要写入 IndexDB 缓存

**优化建议**：
- 禁用不需要的 mod
- 使用直链下载（`download_url`）而非 GitHub Releases
- 清除浏览器缓存后重新加载（重建 IndexDB）

### Q4：boot.json 中的版本号格式有什么要求？

**语义化版本（Semver）**：
```
主版本.次版本.修订号
1.2.3
```

**版本范围语法**：
| 语法 | 含义 | 示例 | 匹配版本 |
|------|------|------|---------|
| `^1.2.3` | 兼容 1.x.x（不升级主版本） | `^1.2.3` | 1.2.3, 1.3.0, 1.9.9 ❌ 2.0.0 |
| `~1.2.3` | 兼容 1.2.x（不升级次版本） | `~1.2.3` | 1.2.3, 1.2.9 ❌ 1.3.0 |
| `>=1.2.3` | 大于等于 | `>=1.2.3` | 1.2.3, 1.3.0, 2.0.0 |
| `1.2.3` | 精确匹配 | `1.2.3` | 仅 1.2.3 |

**推荐**：使用 `^` 语法，允许小版本更新。

### Q5：如何报告 ModLoader 或 Mod 的 bug？

**报告 ModLoader bug**：
1. 访问 [ModLoader Issues](https://github.com/Lyoko-Jeremie/DoLModLoaderBuild/issues)
2. 搜索是否已有相同问题
3. 提供：
   - 浏览器版本
   - ModLoader 版本
   - Console 完整日志
   - 重现步骤

**报告 Mod bug**：
1. 访问 mod 的 GitHub 仓库 Issues
2. 提供：
   - Mod 版本
   - 依赖 mod 版本
   - 游戏版本
   - 冲突的其他 mod（如有）

---

## 性能问题

### 加载时间过长（> 1 分钟）

**诊断步骤**：
1. 打开 Console，查看 `ModLoader ====== load mod: <mod_name>` 日志
2. 记录每个 mod 的加载时间
3. 找出耗时最长的 mod

**常见原因**：
- **大型美化 mod**：AU 美化包含数千张图片（正常耗时 10-30 秒）
- **网络下载**：使用 GitHub Releases 下载速度慢
- **IndexDB 写入**：首次加载需要缓存所有资源

**优化方案**：
1. 使用直链下载（`download_url`）
2. 禁用不常用的美化 mod
3. 使用本地缓存（IndexDB 在后续加载中会更快）

### 游戏运行卡顿

**诊断步骤**：
1. 按 `F12` → Performance 标签 → 录制 5 秒
2. 查看哪些脚本占用 CPU 时间最多

**常见原因**：
- **Passage 替换过多**：TweeReplacer 在每次段落切换时都会执行
- **图片加载延迟**：美化 mod 的图片资源过大
- **事件监听器过多**：多个 mod 监听同一个事件

**优化方案**：
1. 减少使用 TweeReplacer（改用 `tweeFileList` 直接替换 Passage）
2. 压缩图片资源（使用 WebP 格式）
3. 检查是否有 mod 在紧密循环中执行（联系 mod 作者）

---

## 进阶：开发者调试工具

### 1. ModLoader 调试模式

在 Console 中启用：
```javascript
window.modUtils.setDebugMode(true);
```

输出更详细的日志（包括 mod 加载时间、依赖解析等）。

### 2. 导出 Mod 列表

```javascript
console.log(JSON.stringify(window.modUtils.getModListData(), null, 2));
```

导出所有已加载 mod 的元数据。

### 3. 检查 Passage 内容

```javascript
// 查看某个 Passage 的当前内容
console.log(window.modSC2DataManager.getPassageByName("Start").content);
```

用于验证 Passage 是否被正确修改。

---

## 相关文档

- [ModLoader 概览](MODLOADER_OVERVIEW.md)
- [boot.json 规范](MODLOADER_BOOT_JSON.md)
- [ModLoader FAQ](MODLOADER_FAQ.md)
- [ModLoader API](MODLOADER_API.md)（开发者）

---

**最后更新**：2026-06-12  
**维护者**：DOL-X Team
