# DOL-X 当前项目状态

**2026-11-14 当前状态**：稳定版为 [`v0.5.11.9-1.0.0a-1014`](https://github.com/XFoxLG/DOL-X/releases/tag/v0.5.11.9-1.0.0a-1014)，
提供基础版、AU-F、AU-M、AU-A 的 ZIP 与 APK。历史版本见 [Releases](https://github.com/XFoxLG/DOL-X/releases)。
十一月 MapleBirch 5.6.2 候选仍在测试，安卓启动、读档和地点图像问题尚待解决。
Lyra 的 [`1004.1`](https://github.com/DoL-Lyra/Lyra/releases/tag/v0.5.12.13-1.0.1a-1004.1) 为
0.5.12.13 预发布，提供 AU-F、AU-M、AU-A；上游发布与 DOL-X 自身验收分别记录。
下文日期记录保留历史版本信息，当前输入以配置和对应发布说明为准。

**核验日期**：2026-08-12

## 2. 4.x 公开主线栈

当前 `vega` 使用 DoL `0.5.10.12` / 汉化 `1.0.8a`，框架与功能 mod 为：

- maplebirch Framework `4.1.14`（作者官方 Release；已于 2026-08-10 升级并在 MuMu 12 通过
  AU-F 冒烟，状态 `runtime-smoke-passed`，见 `config/mods.lock.json` 与 CHANGELOG Unreleased）。
  未正式发版（`v4.1.14` 仍是 Unreleased），真机遍历尚未全量完成。
- Cheat Extended `1.20(dev2601001)`（作者官方 Release `V1.20Beta`，2026-10-01 由原
  Pre-release 通道转入正式 release；已加入 fail-closed digest 锁）。
- LongerCombat `1.0.1` 与 YanlingCheatCollection `1.0.1`（作者官方独立继任包）。
- Legacy-Art-Mods-Compat `1.0.3-plusV1.1`（社区二改，原作者 README 明确允许二改二传）。
- 旧 maplebirchEx `1.2.4` 与 `maplebirch-v3-layer-compat` 只保留作 3.x 回滚资料，不进入 4.x 产物。

设备日志记录 4.x 基础栈达到 `0 error / 0 warning`，Cheat Extended UI 可打开且抽样
功能可用。LongerCombat 与 Yanling 已挂载，但没有逐功能遍历，因此状态是“运行时挂载通过”，不是
“全功能通过”。
