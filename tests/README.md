# DoL-X 自动化测试

Phase 1 和 Phase 2 的自动化测试已实现。

## 本地运行

### 安装依赖

```bash
pip install -r requirements.txt
```

### 运行配置测试

```bash
# 运行所有配置测试
pytest tests/test_build_matrix.py tests/test_mod_config.py -v

# 只运行构建矩阵测试
pytest tests/test_build_matrix.py -v

# 只运行 mod 配置测试
pytest tests/test_mod_config.py -v
```

### 运行 Mod 资源审计

```bash
# 审计所有 mod 并生成报告
python tools/mod_audit.py

# 指定输出目录
python tools/mod_audit.py --output-dir output

# 禁用缓存（每次重新下载）
python tools/mod_audit.py --no-cache
```

输出文件：
- `output/mod-compatibility-report.json` - JSON 格式报告
- `output/mod-compatibility-report.md` - Markdown 格式报告
- `output/cache/` - 下载缓存目录

### 运行 cheatExtended 替代性审计

```bash
# 下载并审计 cheatExtended 最新 release，但不启用或替换现有 mod
python tools/cheat_extended_audit.py --output-dir output
```

输出文件：
- `output/cheat-extended-replacement-report.json` - JSON 格式报告
- `output/cheat-extended-replacement-report.md` - Markdown 格式报告

该审计会检查：
- cheatExtended 的 release asset、boot.json、readme.md 和 SHA256
- 对 Cheat / CSD / BJX / BCCM 的静态覆盖程度
- `maplebirch` 与 `Simple Frameworks` 的二选一框架要求
- 和当前配置中旧作弊栈、AU 面部扩展、UCB 的潜在冲突与耦合

## GitHub Actions

每次推送到 `vega` 分支时自动运行：

1. **配置与矩阵测试** - 验证构建组合、polyfill、mod 配置
2. **Mod 资源审计** - 下载并检查所有 mod 资源
3. **cheatExtended 替代性审计** - 评估其是否适合作为 Cheat/CSD/BJX/BCCM 的候选替代

查看结果：
- Actions 页面：https://github.com/XFoxLG/DOL-X/actions
- 下载 artifacts 查看详细报告

## 测试覆盖

### Phase 1: 配置与矩阵测试

- ✓ 只构建 4 个自用组合 (258, 1282, 2306, 4354)
- ✓ polyfill 已关闭
- ✓ 基础版不包含 AU
- ✓ AU 三版本包含对应 AU feature
- ✓ 所有版本包含 UCB + 作弊/CSD
- ✓ Mod 配置正确性
- ✓ feature_ids 有效性
- ✓ cache_name 唯一性

### Phase 2: Mod 资源审计

- ✓ GitHub release asset 可访问
- ✓ 文件下载成功
- ✓ SHA256 校验和
- ✓ ZIP 文件完整性
- ✓ Mod 结构验证
- ✓ 风险等级评估
- ✓ cheatExtended 替代性/框架/冲突审计

## 下一步

Phase 3: HTML 浏览器 smoke test（待实现）
- 使用 Playwright 或 agent-browser-cli
- 打开本地 HTML
- 采集 console、network、截图
