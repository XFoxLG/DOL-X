# 技术档案：灾备镜像（2026-08）

> 玩家向正文：`docs/release-notes/` 下的 `*-mirror-*` 文件（每个镜像 tag 一个）。
> 本文件是技术证据档，只进仓库，不会成为 GitHub Release 正文。

## 为什么要做镜像

上游作者会删除 release、也会在固定 tag 上原位换包（`Pre-release` 类 tag 已被多次换包）。
本仓库的构建输入必须能在「官方资产消失或被换包」时复现，因此对关键资产做逐字节灾备副本。

## 镜像清单

| tag | 上游仓库 | 资产 | 字节数 | sha256 | 上游发布日 |
|---|---|---|---|---|---|
| `maplebirch-framework-mirror-v4.1.14` | MaplebirchLeaf/SCML-DOL-maplebirchFramework | `maplebirch-0.5.10.12-v4.1.14.mod.zip` | 186903 | `e44c9aeda62e8cf9cf76a85907c55b8b651541bccb8c6da0ee1b4eda965923a4` | 2026-08-02 |
| `cheat-extended-mirror-v1.20` | chris81605/Degrees-of-Lewdity_Cheat_Extended | V1.20Beta 通道 2026-10-02 快照 | 见镜像 Release 附件 | 随附件一同记录 | 2026-10-02 |
| `longer-combat-mirror-v1.0.1` | MaplebirchLeaf/LongerCombat | `LongerCombat` 1.0.1 | 见镜像 Release 附件 | 随附件一同记录 | 2026-08-11 |
| `yanling-cheat-mirror-v1.0.1` | MaplebirchLeaf/YanlingCheatCollection | 言灵作弊集 1.0.1 | 见镜像 Release 附件 | 随附件一同记录 | 2026-08-11 |
| `maplebirch-framework-mirror-v4.1.13` | MaplebirchLeaf/SCML-DOL-maplebirchFramework | `maplebirch-0.5.10.12-v4.1.13.mod.zip` | 186010 | `f5161eed8a4828baac8d7667ad4311fa214f02855c32c190ac1087902e9be955` | 2026-07-01 |

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
  AU Face 的调用方在运行时解密的载荷里，静态审计看不到，只有运行时能抓到。
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
- 本机持有的官方原件 sha256：4.1.13 = `f5161eed8a4828baac8d7667ad4311fa214f02855c32c190ac1087902e9be955`（186010 字节，2026-10-15 已补建为镜像 tag）、
  4.1.14 = `e44c9aeda62e8cf9cf76a85907c55b8b651541bccb8c6da0ee1b4eda965923a4`（186903 字节）。

## 用法

DOL-X 默认仍从官方源下载（`track_upstream = true`）。镜像只在官方资产消失或被换包时启用：
把 `config/build.toml` 里 maplebirch 段的 `download_url` 指向镜像资产，
并在 `config/mods.lock.json` 里记录同样的 sha256。

## 追加镜像（2026-10-15）：maplebirch v4.1.13

框架作者已把 4.1.13 的 release 连 tag 一起删除（2026-10-15 实测：上游 Release API 与
网页均 404，`git ls-remote` 亦无该 tag）。它是 `-0802` / `-0804` 两次发布的构建输入，
因此按「内容认版本」流程把本机原件补成公开镜像。

| 项 | 值 |
|---|---|
| 镜像 tag | `maplebirch-framework-mirror-v4.1.13` |
| 上游 release | `maplebirch-release-v4.1.13`（已删除） |
| 资产文件名 | `maplebirch-0.5.10.12-v4.1.13.mod.zip` |
| 字节数 | 186010 |
| sha256 | `f5161eed8a4828baac8d7667ad4311fa214f02855c32c190ac1087902e9be955` |
| `boot.json` version | `4.1.13` |
| `dependenceInfo` GameVersion | `>=0.5.10.12` |
| 上游发布日 | 2026-07-01（8 月构建配置注释记录） |
| 契约等价性 | 与 4.1.14 在 GameVersion 下限、`faceStyleSrcFn` 导出与三条补丁 needle 计数上等价；两者字节不同（186010 vs 186903） |

来源链路：

- 本机原件保存在私有目录 `.local/maplebirch-414-investigation/`（mtime 2026-08-08 18:35:29），
  sha256 与 8 月 `config/mods.lock.json` 的 `last_tested_sha256` 逐字节一致；
- 源码 tag `maplebirch-release-v4.1.13` 由 fork `JohnLiao501/SCML-DOL-maplebirchFramework`
  保全（annotated tag 对象 `9932d2a0…`，peel 到 commit `dac8bed4235ad33d6b16a01f8f9e5d9462ca67e1`，
  `package.json` version 4.1.13，2026-10-15 实测）；该 fork 的 Releases 端点返回 0 个附件，
  即构建包本体此前只存在于本机；
- `maplebirch-framework-mirror-v4.1.13` 这个位置自 2026-08 起就写在 8 月构建配置的注释里
  （约定的人工灾备 tag，注明「只作官方资产消失时的人工灾备」），但当时从未真正创建；
  2026-10-15 首次创建，补齐这条保管链。

回退提示：4.1.13 是文档化的回退候选，不是 0.5.11.9 生产锁定版本。回退前先导出存档备份；
若存档已写入 4.1.14 引入的孕期名单数据，回退不保证无损——切换前按
`config/framework-contract-matrix.toml` 的 4.1.13 行备注检查。

## 追加镜像（2026-10-15）：框架 3.1.x / 4.1.x / 4.3.x 共 14 个缺失版本（源码重建）

上游连 release 带 tag 一起删除之后，可达性盘点确认 **14 个版本已经没有任何可用包**
（release 无、CI artifact 无、本机无、镜像无）。这 14 个版本用 fork 保全的源码 tag
**按官方 CI 配方重建**，并公开为镜像。

重建能力本身经过对照验证：4.1.13 / 4.1.14 / 4.2.9 / 4.3.5 四个仍有官方原件的版本，
在本机重建后**整包 sha256 与官方原件逐字节一致**。因此下面这些包可以视为
「官方当年那份文件的等价重建」，但**不能声称与已丢失的原件逐字节相同**（无法对照）。

完整配方、证据链与校验方式见
[framework-source-rebuild-2026-10-15.md](framework-source-rebuild-2026-10-15.md)。

| 镜像 tag | 版本 | 字节数 | sha256 | GameVersion 下限 |
|---|---|---|---|---|
| `maplebirch-framework-mirror-v3.1.8` | 3.1.8 | 148487 | `593e87a48c86098bc9b670555b35ce44040d3a5a8b965f245be991f992c0cf88` | >=0.5.8.9 |
| `maplebirch-framework-mirror-v3.1.9` | 3.1.9 | 151381 | `013eff21b553aae25acc0b6662e0afd4befb047aa2defd98c070a415e0492862` | >=0.5.8.9 |
| `maplebirch-framework-mirror-v3.1.10` | 3.1.10 | 164270 | `c6effdb240641d0f933ede79ee8c4f744cb7e72e4e61f094c165419f812dd890` | >=0.5.8.10 |
| `maplebirch-framework-mirror-v3.1.11` | 3.1.11 | 164303 | `06d8a849ee259e58826b7f22e3c2a5904715128af6f4183e73c49985d9bd9dfa` | >=0.5.8.10 |
| `maplebirch-framework-mirror-v3.1.13` | 3.1.13 | 165706 | `1061048d46bc0f02eca8532c487a5ee23041c718377788ab3d664ac326207b57` | >=0.5.8.10 |
| `maplebirch-framework-mirror-v4.1.0` | 4.1.0 | 179347 | `0b700f85ae4f8bf741ac5b610069c630bfdc27d39e5685498c7444b2034c03b3` | >=0.5.10.8 |
| `maplebirch-framework-mirror-v4.1.6` | 4.1.6 | 185391 | `19988a2d128f13c34caef703630828e043ce62dbff9e9c6764e9f84c95be56c1` | >=0.5.10.11 |
| `maplebirch-framework-mirror-v4.1.7` | 4.1.7 | 185389 | `583e98f5a49e16ed2ab90b0219a4464b6c23941110884aedd4731acb2e79e157` | >=0.5.10.11 |
| `maplebirch-framework-mirror-v4.1.8` | 4.1.8 | 186416 | `39d2a303f7acdf2c901dfb29eccb6704b767cc378e14bd3c12d8d40cef0b9dd3` | >=0.5.10.12 |
| `maplebirch-framework-mirror-v4.1.9` | 4.1.9 | 185703 | `3a56d67baaca0c54693668b99bbaeba7c9cf9a522ee54550be71443e117f64c3` | >=0.5.10.12 |
| `maplebirch-framework-mirror-v4.1.10` | 4.1.10 | 185699 | `579b1afb6148da698a098d5a26ed3cf6f80c98d67363909a487b737f686b2965` | >=0.5.10.12 |
| `maplebirch-framework-mirror-v4.1.12` | 4.1.12 | 185831 | `f7f33b73fb2e5c2dc9ab7b089cfa9fc0211397edf1dd87fee3691cd5bf1b0b05` | >=0.5.10.12 |
| `maplebirch-framework-mirror-v4.3.0` | 4.3.0 | 174343 | `26dab71167df0b342fb04ebebe00dcc35f1c362c3d8d891227e4b4ce9acad53a` | >=0.5.12.11 |
| `maplebirch-framework-mirror-v4.3.2` | 4.3.2 | 176506 | `8665496f30e36a33d838e85737526967bdd89473e0ba13fbc0c1b75a9d105f62` | >=0.5.12.11 |

边界：

- 4.1.7 本机曾有一份 `maplebirch-0.5.8.10-v4.1.7.mod.zip`，但它把 GameVersion 下限改成
  `>=0.5.8.10`（源码声明 `>=0.5.10.11`），属第三方改包，所以 4.1.7 仍按缺失补齐。
- 4.3.0 / 4.3.2 的官方 CI 在 `Verify framework and generated types` 步骤失败，
  官方**从未发布过**这两个版本的包；玩家向说明已如实标注。
- 3.1.x 在 GitHub 上查不到构建记录，压缩包时间戳为本次重建时间。
- 这些旧版本**没有**做过 0.5.11.9 实机验证（只有 4.1.13 / 4.1.14 做过），
  不要用它们替换当前整合包内置的框架。
