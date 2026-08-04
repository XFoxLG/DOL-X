# DOL-X 测试指南

本文档介绍 DOL-X 项目的测试流程、工具和最佳实践。

---

## 快速开始

### 本地开发验证（< 2 分钟）

修改配置后，运行快速检查：

```bash
python tools/quick_check.py
```

检查项：
- ✅ 配置文件一致性
- ✅ Mod URL 可达性
- ✅ Build codes 计算
- ✅ 新 mod 检测
- ✅ mods.lock.json 同步

### GitHub Actions 构建后测试（15-20 分钟）

1. **生成测试清单目录**：
   ```bash
   python tools/download_latest_build.py --build-code 15705344
   ```

2. **手动下载 APK**：
   - 访问 GitHub Actions
   - 下载最新成功构建的 APK
   - 保存到 `downloads/test_builds/{date}-{commit}/`

3. **执行测试**：
   - 安装 APK 到 MuMu 模拟器
   - 按照自动生成的 `TEST_CHECKLIST.md` 逐项测试

---

## 测试策略

### 代表性测试

**真机代表**：AU-F (build_code 15705344)
- 原因：维护者实际使用和验收的体型
- 时间：涉及运行时行为的候选版按需做 15-20 分钟手动测试

**CI 自动化**：
- 分支推送：base (15704320) + AU-F (15705344)
- 发版干跑与 tag：base / AU-F / AU-M / AU-A 全四码
- 构建前运行完整 pytest；构建后对 ZIP 执行 AU 面部别名静态审计

AU-M / AU-A 按既定决策不做真机验收，验证层级止于 CI 构建成功和静态 payload 检查。
CI 不等于浏览器或模拟器真机测试，不能把“构建成功”表述为“运行时全部通过”。

### 测试触发条件

**必须深度测试**：
- 新增 mod
- mod 版本升级
- 框架版本变更
- 上游游戏版本更新

**可以跳过**：
- 仅文档更新
- CI 配置调整
- 工具脚本优化

---

## 工具说明

### tools/quick_check.py

**用途**：本地快速验证配置，无需完整构建

**使用场景**：
- 修改 `config/*.toml` 后
- 提交代码前
- 怀疑配置不一致时

**运行时间**：< 2 分钟

**示例**：
```bash
# 运行所有检查
python tools/quick_check.py

# 只检查 URL
python tools/quick_check.py --checks urls
```

### tools/download_latest_build.py

**用途**：准备测试目录并生成清单；artifact 仍通过 Actions 页面或 `gh run download` 下载

**使用场景**：
- GitHub Actions 构建完成后
- 准备手动测试前

**示例**：
```bash
# 生成默认 AU-F 测试清单
python tools/download_latest_build.py

# 生成指定 build_code 的清单
python tools/download_latest_build.py --build-code 15704320

# 记录指定 Run ID 到准备流程
python tools/download_latest_build.py --run-id 27995040396
```

**输出**：
```
downloads/test_builds/20260624-e0b1a4b/
├── TEST_CHECKLIST.md         # 自动生成的测试清单
└── (手动下载的 APK 放这里)
```

### AU 诊断测试证据

AU 相关问题必须绑定到具体构建，避免把旧 APK 日志当成当前配置结论。每次 AU 手测至少记录：

- GitHub Actions run ID
- artifact 名称与 APK 文件名
- build code：Base `15704320`、AU-F `15705344`、AU-M `15706368`、AU-A `15708416`
- ModLoader 已加载列表中的 AU、NeoUI、Mae's Picvary、NPC Avatars、Lyra 条目（BunnyTransformation 已禁用，不应出现）
- 侧边栏展开/收起截图
- 战斗是否能正常开始

当前 AU model 诊断矩阵见 `docs/AU_MODEL_DIAGNOSTIC_MATRIX_2026-06-28.md`。

---

## 测试清单

### 基础启动测试（5分钟）

1. APK 安装到 MuMu 模拟器
2. 游戏启动，进入主菜单
3. 版本信息正确（APK 文件名 commit hash）

### Mod 加载验证（5分钟）

1. 打开 ModLoader 管理器（Alt+M）
2. 确认所有 mod 已加载：
   - maplebirch v4.1.13
   - Cheat Extended v1.20(dev260719)
   - LongerCombat v1.0.1
   - YanlingCheatCollection v1.0.1
   - maplebirchEx v1.2.4 不应出现（已退役）
   - CustomHair v1.0.0
   - Mae's Picvary v1.3.2
   - More Love Interests Mod v0.1.7.0
   - 当前启用的新 mod（guide_to_me, npc_social_icon）
   - NeoUI Patch 应出现（2026-07-05 升为必选，全部包内置）
   - BunnyTransformation 不应出现（已禁用，若出现说明测试包不是当前配置）
   - AU model（根据构建）
3. 加载日志无 error

### 核心功能抽查（10分钟）

1. **作弊扩展**：
   - 启用强制作弊
   - 验证侧边栏作弊按钮
   - 测试快速言灵

2. **更多恋人**：
   - 在正式游戏的“态度”页确认出现“查看NPC喜爱的食物”入口
   - 空列表应正常显示“你还没有对任何NPC产生恋爱兴趣”，不得出现红框
   - 有恋爱兴趣 NPC 的存档再验证食物图标、配方材料；Avery 应显示舒芙蕾

3. **新增功能**（选测 1-2 项）：
   - 控制NPC嘴部
   - NPC社交栏头像

### 开发内容检查（5分钟）

1. 打开浏览器 Console（F12）
2. 观察日志：
   - ModLoader 正常日志
   - 是否有多余 console.log
   - 是否有 ERROR/WARNING

### 已知问题验证（5分钟）

以 [`CURRENT_PROJECT_STATE.md`](CURRENT_PROJECT_STATE.md) 的“已知产品边界”和
[`MOD_COMPATIBILITY_MATRIX.md`](MOD_COMPATIBILITY_MATRIX.md) 为可复核事实来源。

---

## 版本追踪

### APK 文件名格式

```
DoL-{dol_ver}-XFox-{chs_ver}-{mod_suffix}-{date}-{commit}.apk
```

示例：
```
DoL-0.5.8.10-XFox-3.1.3a-ucb-more-love-...-0615-e0b1a4b.apk
                                                 ^^^^^^^^
                                                 commit hash
```

### BUILD_MANIFEST.json

每个 build_code 一个清单：
- 构建元数据（日期、commit、环境）
- Mod 版本信息
- SHA256 校验和
- GitHub Actions Run ID

---

## 已知问题

### CustomHair 十六进制输入框

- **状态**：误报已纠正
- **说明**：需先点击“自定义染发”选项，十六进制输入框才会出现。
- **计划**：不再作为 bug 跟踪。

### AU Face 部分验收

- **状态**：三个 AU 构建均启用；设置 UI 与配置交互已通过。
- **静态门禁**：CI 验证 `img/face/default/default/blush-1..5.png` 兼容别名。
- **运行时边界**：脸红、流泪和部分改脸视觉未完整遍历，不把加载成功外推为视觉全通过。

### 自定义言灵集报错

- **替代方案**：快速言灵正常
- **影响**：低

---

## 测试最佳实践

### 提交前检查

```bash
# 1. 快速验证
python tools/quick_check.py

# 2. 运行单元测试
pytest tests/test_quick_check.py -v

# 3. 检查是否有敏感文件
git status | grep -E "\\.env|credentials"
```

### 构建后测试

```bash
# 1. 生成测试清单
python tools/download_latest_build.py --build-code 15705344

# 2. 手动下载 APK

# 3. 安装测试

# 4. 填写测试清单

# 5. 更新锁文件 notes 与当前状态文档
```

### 问题报告

发现新问题时：

1. 记录到 `config/mods.lock.json` 的 `notes`
2. 更新 `docs/CURRENT_PROJECT_STATE.md` 或兼容矩阵中的验证边界
3. 仓库 Issues 当前关闭；需长期跟进时写入仓库文档或用户私有任务记录

---

## CI 自动化测试

当前 `.github/workflows/build.yaml` 的强制门禁：

- 构建前运行完整 `python -m pytest tests -q`
- 分支推送构建 base + AU-F；发版干跑和 tag 构建全四码
- 构建后、上传前运行 `tools/au_artifact_check.py`
- tag 才允许 release job 创建 GitHub Release

浏览器 smoke、APK CDP 与真机行为属于更深层验证工具，不应在未实际执行时写成 CI 已覆盖。

---

## 参考

- [tests/README.md](../tests/README.md) - 自动测试分层与文件索引
- [CHANGELOG.md](../CHANGELOG.md) - 版本变更历史
- [config/mods.lock.json](../config/mods.lock.json) - Mod 版本锁定
- [MANUAL_TESTING_CHECKLIST.md](MANUAL_TESTING_CHECKLIST.md) - 手动测试详细步骤
