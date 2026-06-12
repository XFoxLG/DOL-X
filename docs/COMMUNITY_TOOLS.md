# DoL 社区工具指南

本文档整理 Degrees of Lewdity 模组开发社区的常用工具，帮助 DOL-X 项目选择合适的工具集成。

---

## 开发工具

### DoL-Commit2Mod（优先级 1 - 计划集成）

**仓库**: https://github.com/Lethivia/DoL-Commit2Mod

**功能**: 将 git commit 转换为 ModLoader 兼容的 mod 包

**适用场景**:
- 快速测试上游 Lyra 的最新提交
- 将特定功能提交打包为独立 mod
- 实验性功能验证

**计划集成方式**:
```bash
# 使用方式（集成后）
python main.py dev commit-to-mod <commit-hash>

# 示例：测试上游新功能
python main.py dev commit-to-mod abc1234 --repo https://github.com/DoL-Lyra/Lyra.git
python main.py build --profile experimental --mod workspace/experimental_mods/abc1234.mod.zip
```

**状态**: 待调研实现细节

---

### DoLModRspackExampleTS（优先级 3 - 推荐参考）

**仓库**: https://github.com/Muromi-Rikka/DoLModRspackExampleTS

**功能**: 基于 Rspack + TypeScript 的 mod 开发模板

**技术栈**:
- Rspack（类 Webpack 的快速构建工具）
- TypeScript（类型安全）
- 现代前端工具链

**适用场景**:
- 需要开发自定义 mod（如兼容性 shim）
- 需要 TypeScript 类型支持
- 需要现代化的开发体验（热重载、模块化）

**推荐用途**:
- 作为 DOL-X 自研 mod 的开发模板
- 学习 ModLoader 的最佳实践
- 参考构建配置

**示例项目结构**:
```
my-mod/
├── src/
│   ├── index.ts          # mod 入口
│   ├── components/       # 组件
│   └── utils/            # 工具函数
├── rspack.config.js      # 构建配置
├── boot.json             # ModLoader 元数据
└── package.json
```

**状态**: 文档化推荐，按需使用

---

### DOL-Mod-Created-Helper（优先级 2 - 借鉴测试能力）

**仓库**: https://github.com/NumberSir/DOL-Mod-Created-Helper  
**简称**: MCH

**功能**: 
1. Mod 创建脚手架
2. **自动化测试（REMOTE_TEST）** ← DOL-X 主要借鉴对象
3. Mod 管理工具

**测试能力**:
- REMOTE_TEST: 远程游戏逻辑测试
- 模拟游戏流程（passage 导航、选项点击）
- 验证游戏状态（变量、存档）

**DOL-X 借鉴方向**:

#### 1. 开发服务器（`tools/dev_server.py`）
```python
# 监控 mod 源码变更 -> 自动重新打包 -> 触发浏览器测试
python tools/dev_server.py --watch mods/my_mod
```

#### 2. 游戏逻辑测试（`tests/test_game_logic.py`）
```python
@pytest.mark.parametrize("build_code", ["57601", "58625"])
def test_orphanage_intro_flow(build_code):
    """测试孤儿院开场流程"""
    result = run_browser_smoke(
        f"output/DoL-*-{build_code}-*.zip",
        assertions=[
            "passage == 'Orphanage Intro'",
            "V.money >= 0",
            "V.name != undefined"
        ]
    )
    assert result["success"]
```

#### 3. Mod 功能验证
```python
def test_cheat_extended_menu_available():
    """测试 cheatExtended 菜单可用性"""
    # 打开游戏 -> 点击作弊菜单 -> 验证选项可见
    pass
```

**实施计划**:
1. 研究 MCH 的 REMOTE_TEST 实现
2. 在 DOL-X 实现类似的测试框架
3. 扩展 `browser_smoke_test.py` 支持热加载

**状态**: 计划借鉴，待深入研究

---

### rust-mod-dev（已废弃 - 不推荐）

**仓库**: https://github.com/Paul-16098/rust-mod-dev  
**状态**: 已归档（2026-03-01）

**归档原因**:
- 功能被 Python 工具链（MCH）覆盖
- Rust 生态在 DoL mod 开发中未成主流
- 维护成本高

**替代方案**: NumberSir/DOL-Mod-Created-Helper

**历史价值**:
- 探索了 Rust 在 mod 工具中的应用
- 提供了一些设计思路

**结论**: DOL-X 不集成此工具

---

## 工具对比矩阵

| 工具 | 主要功能 | 技术栈 | 活跃度 | DOL-X 相关性 | 集成计划 |
|------|----------|--------|--------|-------------|----------|
| DoL-Commit2Mod | Commit → Mod | Python? | 活跃 | ⭐⭐⭐⭐⭐ | 优先级 1：立即集成 |
| DoLModRspackExampleTS | Mod 开发模板 | Rspack + TS | 活跃 | ⭐⭐⭐ | 优先级 3：文档化推荐 |
| DOL-Mod-Created-Helper | Mod 工具 + 测试 | Python | 活跃 | ⭐⭐⭐⭐ | 优先级 2：借鉴测试能力 |
| rust-mod-dev | Rust 工具链 | Rust | ❌ 已归档 | ⭐ | 不推荐 |

---

## 集成路线图

### Phase 1: 快速集成（本周）
- ✅ 创建本文档
- [ ] 调研 DoL-Commit2Mod 实现
- [ ] 集成 `commit-to-mod` 到 `main.py`

### Phase 2: 测试能力扩展（下周）
- [ ] 研究 MCH REMOTE_TEST
- [ ] 创建 `tools/dev_server.py`
- [ ] 扩展 `browser_smoke_test.py`
- [ ] 添加 `tests/test_game_logic.py`

### Phase 3: 文档完善（持续）
- [ ] 编写 mod 开发指南
- [ ] 推荐 DoLModRspackExampleTS 模板
- [ ] 维护工具更新日志

---

## 使用建议

### 场景 1: 测试上游新功能
**推荐工具**: DoL-Commit2Mod
```bash
# 1. 查看上游最新提交
git log upstream/vega --oneline --max-count=10

# 2. 转换为 mod 测试
python main.py dev commit-to-mod <hash>

# 3. 构建并测试
python main.py build --profile experimental
python tools/browser_smoke_test.py output/*.zip
```

### 场景 2: 开发自定义 mod
**推荐工具**: DoLModRspackExampleTS
```bash
# 1. 克隆模板
git clone https://github.com/Muromi-Rikka/DoLModRspackExampleTS.git my-mod
cd my-mod

# 2. 修改为自己的 mod
# 编辑 boot.json、src/ 等

# 3. 构建
npm install
npm run build

# 4. 集成到 DOL-X
cp dist/my-mod.mod.zip /e/game/repo/DOL-X/workspace/custom_mods/
```

### 场景 3: 热加载开发
**推荐工具**: MCH 启发的 dev_server（待实现）
```bash
# 启动开发服务器
python tools/dev_server.py --watch mods/my_mod

# 文件变更时自动:
# 1. 重新打包 mod
# 2. 构建游戏
# 3. 运行浏览器测试
# 4. 显示测试结果
```

---

## 相关文档

- [构建系统](../BUILD.md)
- [游戏逻辑测试](GAME_LOGIC_TESTING.md)（待创建）
- [Mod 开发指南](MOD_DEVELOPMENT_GUIDE.md)（待创建）
- [上游同步策略](../UPSTREAM_FRIENDLY_STRATEGY.md)

---

## 贡献

如果发现新的有用工具，请：
1. 在 Issue 中提出
2. 评估工具价值（功能、活跃度、技术栈）
3. 更新本文档

---

**最后更新**: 2026-06-13  
**维护者**: DOL-X 项目组
