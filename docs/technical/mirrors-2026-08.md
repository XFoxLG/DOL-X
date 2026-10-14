# 技术档案：灾备镜像（2026-08）

> 玩家向正文：`docs/release-notes/` 下的四个 `*-mirror-*` 文件。
> 本文件是技术证据档，只进仓库，不会成为 GitHub Release 正文。

## 为什么要做镜像

上游作者会删除 release、也会在固定 tag 上原位换包（`Pre-release` 类 tag 已被多次换包）。
本仓库的构建输入必须能在「官方资产消失或被换包」时复现，因此对关键资产做逐字节灾备副本。

## 四份镜像

| tag | 上游仓库 | 资产 | 字节数 | sha256 | 上游发布日 |
|---|---|---|---|---|---|
| `maplebirch-framework-mirror-v4.1.14` | MaplebirchLeaf/SCML-DOL-maplebirchFramework | `maplebirch-0.5.10.12-v4.1.14.mod.zip` | 186903 | `e44c9aeda62e8cf9cf76a85907c55b8b651541bccb8c6da0ee1b4eda965923a4` | 2026-08-02 |
| `cheat-extended-mirror-v1.20` | chris81605/Degrees-of-Lewdity_Cheat_Extended | V1.20Beta 通道 2026-10-02 快照 | 见镜像 Release 附件 | 随附件一同记录 | 2026-10-02 |
| `longer-combat-mirror-v1.0.1` | MaplebirchLeaf/LongerCombat | `LongerCombat` 1.0.1 | 见镜像 Release 附件 | 随附件一同记录 | 2026-08-11 |
| `yanling-cheat-mirror-v1.0.1` | MaplebirchLeaf/YanlingCheatCollection | 言灵作弊集 1.0.1 | 见镜像 Release 附件 | 随附件一同记录 | 2026-08-11 |

`maplebirch` 4.1.14 的其它核对项：`boot.json` version `4.1.14`、
`dependenceInfo` GameVersion `>=0.5.10.12`、上游构建提交 `cf57f88c`、许可 MIT（Copyright (c) 2026 楓樺葉）。

## 框架版本为什么钉在 4.1.14

离线浏览器冒烟实测（同一份 0.5.11.9 产物，只替换 maplebirch 载荷）：

| 信号 | v4.2.9 | v4.1.14 |
|---|---|---|
| `faceStyleSrcFn is not a function` | 3 | 0 |
| `whenSC2PassageEnd` 递归栈溢出 | 2 | 0 |
| `ReferenceError: UIBar is not defined` | 24 | 0 |

- `faceStyleSrcFn` 等四个导出在 4.2.0 被删除，4.2.1 恢复了 faceStyle 渲染但没有恢复该导出；
  AU Face 的调用方在随包加载的内层载荷里，静态审计看不到，只有运行时能抓到。
- 4.2.9 引入了一个自递归的 `EventEmitter.error(e){return this.error(e)}`。
- 4.3.5 / 4.4.x 只面向 0.5.12.11 / 0.5.12.13 本体，而汉化仓库没有 0.5.12.x 发行。
- 5.x 重构移除了 `ModuleSystem` / `LanguageManager`，LongerCombat / Yanling / DOLI 均不覆盖。

## 考古档案（供核对版本真伪）

- 上游 `MaplebirchLeaf/SCML-DOL-maplebirchFramework` 连 tag 一起删除，现存 tag 只剩 9 个。
- fork `JohnLiao501/SCML-DOL-maplebirchFramework` 保全 34 个被删 tag，覆盖 3.1.8 → 4.3.5。
- `v4.1.2` 是陷阱样本：tag 指向 2026-08-27 的一次手滑提交（package.json 写 4.1.2，
  但 `faceStyleSrcFn` 计数 0、GameVersion 下限已是 `>=0.5.11.9`），按 tag 名认版本会得到一个
  从未真正存在过的版本。详见 `config/framework-contract-matrix.toml`。
- Software Heritage 对本仓库未归档（`/api/1/origin/.../get/` 返回 404）。
- 本机持有的官方原件 sha256：4.1.13 = `f5161eed8a4828baac8d7667ad4311fa214f02855c32c190ac1087902e9be955`（186010 字节）、
  4.1.14 = `e44c9aeda62e8cf9cf76a85907c55b8b651541bccb8c6da0ee1b4eda965923a4`（186903 字节）。

## 用法

DOL-X 默认仍从官方源下载（`track_upstream = true`）。镜像只在官方资产消失或被换包时启用：
把 `config/build.toml` 里 maplebirch 段的 `download_url` 指向镜像资产，
并在 `config/mods.lock.json` 里记录同样的 sha256。
