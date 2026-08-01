# 会话状态 2026-08-01：仓库清理与公开构建分档

本文是当前恢复入口，优先级高于所有更早的会话状态记录。仓库内不再保留
带日期的 `next-4` 实验期快照——4.x 早已合入 `vega` 公开主线，那些描述已被取代。

## 基线

- 主线 `vega`：`e9a7f9578f9009cd1841c9b660fa740898e2c950`（本轮清理起点）
- 历史稳定归档：`origin/vega-archive-0713` = `75d752edf5952ec83a616d1023e9fde93b113dcd`
- 上游 `DoL-Lyra/Lyra` 默认分支 `vega` = `e61352e8ff329dbc06786d46dd36c53e8d707405`
- 与上游关系：`0 behind / 193 ahead`，无待同步提交
- 上游 `main` / `hub` / `lyra` 与 `vega` 无共同祖先，不是同步债务，不参与 ahead/behind 计算

## Tag 拓扑与 `--prune-tags` 禁令

本地 tag 分三类，不是两类。误判这一点会导致把上游 tag 当成本地独有资产：

- 来自上游 `DoL-Lyra/Lyra` 的 113 个：fork 时随 clone 进入本地，从未推送到 `origin`。
  按 `origin` 判断会误认为「仅本地存在」。可随时 `git fetch upstream --tags` 重取。
- DOL-X 自有的 8 个：7 个在 `origin` 上有对应 Release，`backup/pre-scrub` 在 bundle 内。
- 本地 tag 总数应为 121（113 + 8）。

**禁止在本仓库执行 `git fetch --prune-tags`。** fork 仓库的多数本地 tag 来源是
`upstream` 而非 `origin`，按 `origin` 剪枝会一次性删除上百个上游 tag。本轮曾因此
将本地 tag 从 59 误删至 7；因上游可重取、自有 tag 有 Release 与 bundle 双备份，
实际数据损失为零，但恢复过程耗费了整轮会话的尾段。

判断某个 tag 是否真的独有，必须同时对比 `git ls-remote --tags origin` 与
`git ls-remote --tags upstream`，不能只看其中一个。

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
