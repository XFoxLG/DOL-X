# DOL-X 当前项目状态

**2026-11-14 当前下载摘要**：0707、0713、0802、0804、0808、1014 六个历史正式版的

原发布内容与标签保留，Latest 为 `v0.5.11.9-1.0.0a-1014`。独立模组镜像维持逐件许可核验；
Build 工作流继续停用。

历史隐私扫描与上游命中复核完成，但旧提交页面缓存仍可访问，支持工单尚未发送。

详见[最新保存与整理报告](technical/preservation-privacy-and-distribution-2026-11-13.md)与
[分发政策](DISTRIBUTION_POLICY.md)。下文日期记录保留历史证据，不代表当前下载或许可状态。

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
