# 会话状态 2026-08-01：仓库清理与公开构建分档

本文是当前恢复入口，优先级高于所有更早的 `SESSION_STATUS_*` 文档。
`docs/SESSION_STATUS_2026-07-28.md` 仍以 `next-4` 为实验主线，那个描述已被取代：
4.x 早已合入 `vega` 公开主线。

## 基线

- 主线 `vega`：`e9a7f9578f9009cd1841c9b660fa740898e2c950`（本轮清理起点）
- 历史稳定归档：`origin/vega-archive-0713` = `75d752edf5952ec83a616d1023e9fde93b113dcd`
- 上游 `DoL-Lyra/Lyra` 默认分支 `vega` = `e61352e8ff329dbc06786d46dd36c53e8d707405`
- 与上游关系：`0 behind / 193 ahead`，无待同步提交
- 上游 `main` / `hub` / `lyra` 与 `vega` 无共同祖先，不是同步债务，不参与 ahead/behind 计算

## 构建矩阵

四个构建码不变：

- base `15704320`
- AU-F `15705344`
- AU-M `15706368`
- AU-A `15708416`

公开 CI 分两档：

- 分支推送（`vega`）：构建 base + AU-F
- tag 发版：构建全部四码，并创建 Release

构建码在 workflow 里必须**逗号分隔**：`main.py` 的 `_split_build_codes` 只按逗号拆分，
空格分隔会被当成单个构建码并在校验阶段失败。由
`tests/test_public_distribution_boundary.py` 锁定该约束。

`warmup` 与 `build` 共用同一组解析后的构建码，避免预热资源集合与构建目标不一致。

分档已由 GitHub Actions run
[`30686010865`](https://github.com/XFoxLG/DOL-X/actions/runs/30686010865) 在提交
`66a28e5` 上验证，产出四件：

- `DoL-0.5.10.12-XFox-1.0.8a-base-0801.zip` / `.apk`
- `DoL-0.5.10.12-XFox-1.0.8a-au-f-0801.zip` / `.apk`

## 本轮退役的组件

以下组件已无调用方或本身已损坏，全部删除：

- `lyra/local_mod.py` 与 `mods/maplebirch-v3-layer-compat/`：4.x 的本地 mod 注入
  列表为空，整条链空转。4.1.13 已原生使用新式图层命名。
- `config/profiles.toml` 与 `tools/profile_builder.py`：后者导入不存在的
  `load_profiles_config`，导入阶段即失败；profile 构建码也早已过时。
- `config/compatibility_matrix.toml`：只有注释、没有 loader。活跃的兼容登记表是
  `lyra/compatibility.py`。
- `tools/` 下失效或不安全的脚本：`auto_executor.py`、`commit_docs_reorganization.py`、
  `validate_mod_addition.py`、`verify_docs_structure.py`、两个 `system_health_check*`、
  `check_imagepack_cache.py`、`dev_mod.py`、`plugin_wizard.py`、`dev/` 整套 Commit2Mod 原型。
- `.github/.trigger` 与零运行的 `.github/workflows/trigger.yaml`。

`docs/ADVANCED_MOD_DEV.md` 与 `docs/COMMIT2MOD_USAGE.md` 只描述上述已删除工具，
已移入 `docs/archive/`。

回滚不再依赖仓库内保留源码，由 `vega-archive-0713` 与提交历史承担。

## 其他修正

- `mod-update-check.yml`：仓库 Issues 已关闭，原有的建 Issue 步骤必然失败。
  改为写入 Step Summary 与 `mod-update-report` artifact。
- `config/mods.lock.json`：移除退役的 maplebirchEx v1.2.4 owner 条目（历史叙述归
  CHANGELOG）；修正 Cheat Extended 中关于上游 v1.19 是否存在的自相矛盾说明。
- `build.yaml`：清理指向已删除文件的 `paths-ignore` 与失效的 `!*-compat-*` tag 规则。

## 当前 4.x 栈

DoL `0.5.10.12` / 汉化 `1.0.8a`：

- maplebirch Framework `4.1.13`
- Cheat Extended `1.20(dev260719)` Pre-release
- LongerCombat `1.0.1` + YanlingCheatCollection `1.0.1`（旧 maplebirchEx 的官方继任者）
- Legacy-Art-Mods-Compat `1.0.3-plusV1.1`
- AU Face 仅进入三个 AU 码

## 待验证边界

- AU Face 在三种体型上的真机视觉验收尚未完成（设置 UI 与配置交互已通过）。
- LongerCombat 与 Yanling 已挂载，但未逐功能遍历。
- maplebirch「PC 模型模式」需要 NPC wardrobe 数据；当前无 mod 注册衣柜，
  动态 NPC 回落 `naked` 是设计行为，不是路径 bug。
