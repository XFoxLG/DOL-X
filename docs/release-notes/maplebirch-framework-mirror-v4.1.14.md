# maplebirch Framework v4.1.14 — 灾备镜像（与官方资产逐字节相同）

这是 [MaplebirchLeaf/SCML-DOL-maplebirchFramework](https://github.com/MaplebirchLeaf/SCML-DOL-maplebirchFramework)
官方 release `maplebirch-release-v4.1.14` 中资产 `maplebirch-0.5.10.12-v4.1.14.mod.zip`
的原样灾备副本。**未做任何修改**，字节数与 sha256 均与官方 Release API 报告的一致。

## 为什么需要这个镜像

上游作者在 2026-09-24 批量删除了 20 多个 release tag（含 4.2.0–4.2.8、4.3.0–4.3.4、4.4.0 等）。
该仓库的 Release 资产没有不可变性保证，`Pre-release` 之类的固定 tag 已被多次原位换包。
本镜像是为了让 DOL-X 的构建输入在"官方资产消失或被换包"时仍可复现。

## 校验

| 项 | 值 |
|---|---|
| 资产文件名 | `maplebirch-0.5.10.12-v4.1.14.mod.zip` |
| 字节数 | 186903 |
| sha256 | `e44c9aeda62e8cf9cf76a85907c55b8b651541bccb8c6da0ee1b4eda965923a4` |
| boot.json version | `4.1.14` |
| dependenceInfo GameVersion | `>=0.5.10.12` |
| 上游发布日 | 2026-08-02 |
| 上游构建提交 | `cf57f88c` |
| 许可证 | MIT (Copyright (c) 2026 楓樺葉) |

## 为什么 DOL-X 钉在 4.1.14 而不是更新的版本

离线浏览器冒烟实测（同一份 0.5.11.9 产物，只替换 maplebirch 载荷）：

| 信号 | v4.2.9 | v4.1.14 |
|---|---|---|
| `faceStyleSrcFn is not a function` | 3 | 0 |
| `whenSC2PassageEnd` 递归栈溢出 | 2 | 0 |
| `ReferenceError: UIBar is not defined` | 24 | 0 |

- `faceStyleSrcFn` 等四个导出在 4.2.0 被删除，4.2.1 恢复了 faceStyle 渲染但没有恢复该导出；
  AU Face 的调用方在运行时解密的 crypt 载荷里，静态审计看不到，只有运行时能抓到。
- 4.2.9 引入了一个自递归的 `EventEmitter.error(e){return this.error(e)}`。
- 4.3.5 / 4.4.x 只面向 0.5.12.11 / 0.5.12.13 本体，而汉化仓库没有 0.5.12.x 发行。
- 5.x 重构移除了 `ModuleSystem` / `LanguageManager`，LongerCombat / Yanling / DOLI 均不覆盖。

v4.1.14 是目前唯一同时具备 `faceStyleSrcFn` 导出、已验证补丁锚点和通过真机的 4.x 载荷。

## 用法

DOL-X 默认仍从官方源下载（`track_upstream = true`）。本镜像只在官方资产消失或被换包时启用。
切换方式是把 `config/build.toml` 里 maplebirch 段的 `download_url` 指向本镜像资产，
并在 `config/mods.lock.json` 里记录同样的 sha256。
