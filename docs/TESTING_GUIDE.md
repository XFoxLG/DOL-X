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

1. **下载测试清单**：
   ```bash
   python tools/download_latest_build.py --build-code 7317760
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

**每次必测**：AU-M (build_code 7317760)
- 原因：最常用，功能最全
- 时间：15-20 分钟手动测试

**CI 自动化**：其他 3 个构建
- 基础版 (7315712)
- AU-F (7316736)
- AU-A (7319808)
- 验证：启动成功 + mod 加载完整

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

**用途**：下载测试构建并生成测试清单

**使用场景**：
- GitHub Actions 构建完成后
- 准备手动测试前

**示例**：
```bash
# 下载 AU-M 构建（默认）
python tools/download_latest_build.py

# 下载指定 build_code
python tools/download_latest_build.py --build-code 7315712

# 下载指定 Run ID
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
- build code：Base `7315712`、AU-F `7316736`、AU-M `7317760`、AU-A `7319808`
- ModLoader 已加载列表中的 AU、NeoUI、Mae's Picvary、NPC Avatars、BunnyTransformation、Lyra 条目
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
   - maplebirch v3.1.14
   - cheat extended v1.17
   - maplebirchEx v1.2.4
   - CustomHair v1.0.0
   - Mae's Picvary v1.3.2
   - More Love Interests Mod v0.1.6.0
   - 当前启用的新 mod（guide_to_me, neoui_patch, npc_social_icon）
   - BunnyTransformation 不应出现（已禁用，若出现说明测试包不是当前配置）
   - AU model（根据构建）
3. 加载日志无 error

### 核心功能抽查（10分钟）

1. **作弊扩展**：
   - 启用强制作弊
   - 验证侧边栏作弊按钮
   - 测试快速言灵

2. **更多恋人**：检查相关 NPC

3. **新增功能**（选测 1-2 项）：
   - 控制NPC嘴部
   - NeoUI Patch
   - NPC社交栏头像

### 开发内容检查（5分钟）

1. 打开浏览器 Console（F12）
2. 观察日志：
   - ModLoader 正常日志
   - 是否有多余 console.log
   - 是否有 ERROR/WARNING

### 已知问题验证（5分钟）

详见 MCP 记忆 `core://dol-x-test-management`

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

### CustomHair 十六进制输入缺失

- **状态**：已接受
- **影响**：低（预设颜色可用）
- **计划**：等待 mod 更新

### AU Face 已禁用

- **原因**：maplebirch v3.1.14 路径问题
- **计划**：框架升级到 v4.x 后重新启用
- **验证**：侧边栏无错位

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
python tools/download_latest_build.py --build-code 7317760

# 2. 手动下载 APK

# 3. 安装测试

# 4. 填写测试清单

# 5. 记录结果到 MCP 记忆
```

### 问题报告

发现新问题时：

1. 记录到 `config/mods.lock.json` 的 `notes`
2. 更新 MCP 记忆 `core://dol-x-test-management`
3. 如需跟进，创建 GitHub Issue

---

## CI 自动化测试

### Phase 1A: 基线验证

- Warmup 资源
- 构建 4 个 variants
- Browser smoke test (ZIP)
- APK CDP smoke test (Android)

### Phase 1B/1C: Mod 兼容性

- maplebirch 版本检查
- expansion 更新检查

详见 `.github/workflows/baseline-candidate-gate.yml`

---

## 参考

- [AGENTS.md](AGENTS.md) - Agent 使用指南
- [CHANGELOG.md](CHANGELOG.md) - 版本变更历史
- [config/mods.lock.json](../config/mods.lock.json) - Mod 版本锁定
- [MANUAL_TESTING_CHECKLIST.md](MANUAL_TESTING_CHECKLIST.md) - 手动测试详细步骤
