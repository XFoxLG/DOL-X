# 0707 整合包「组件忠实重建」记录（2026-10-16）

本文件记录 `v0.5.10.12-1.0.8a-0707` 的本地重建过程与对照验证结果。
0707 的 Release 与 tag 在线上均已不存在，唯一幸存的原件是它的 **AU-F APK**；
因此本轮的验证强度接近 0713：AU-F 能做到**逐条目 + 签名块**对照，
base / AU-M / AU-A 三码与全部 ZIP 只能做**组件级 + 交叉一致性**验证。

相关路径：

- 原件对照物：`.local/release-assets-recovery/0707/DoL-0.5.10.12-XFox-1.0.8a-au-f-0707.apk`
  （sha256 `244ba1a07543f03f4e8753ab7f6b385ca2063ea21bd3f80c6fca7e8bd995dba3`，130,555,614 B）
- 从对照物提取的输入件：`.local/release-assets-recovery/0707/embedded/`
- 本机重建驱动（不入库）：`.local/rebuild_0707_pipeline.py`
- 重建产物：`DOL-X-rebuild-0707\output\`（本机路径，与本仓库同级）

## 一、结果速览

| 项目 | 结论 |
|---|---|
| 重建 AU-F APK vs 原件 AU-F APK | 21,939 个条目：**内容差异 0、头部差异 0** |
| 重建 AU-F APK 字节数 | 130,555,614，与原件**完全相同** |
| `META-INF/DOL.RSA` / `DOL.SF` / `MANIFEST.MF` | **逐字节一致**（用正式密钥签名后） |
| 重建 AU-F ZIP vs 原件 APK 槽位 | **36/36 全等** |
| 重建 AU-M / AU-A ZIP vs 原件 APK 槽位 | 各 2 处差异：AU 模型槽 + Lyra 标题槽 |
| 重建 base ZIP vs 原件 APK 槽位 | 槽 0–23 全等；槽 25–35 仅 Lyra 标题槽不同 |
| ZIP ↔ APK 载体一致性（四码各自内部） | 36/36、36/36、36/36、35/35 **全等** |
| 四码签名证书 | 均为正式密钥 `B2:1C:D1:5B:…:B8:29:EC:E6` |
| 剩余差异 | 仅 ZIP 条目**存放顺序**与**时间戳**（不影响内容） |

结论口径：0707 的 AU-F 可以陈述为「与原件**逐条目一致、含签名块**」；
其余七件因原件不存在，只能陈述为「组件级一致 + 交叉一致性成立」。
**不得**陈述为「0707 的八件产物都与原件逐字节相同」。

## 二、身份与时间线

| 项 | 值 | 证据 |
|---|---|---|
| tag | `v0.5.10.12-1.0.8a-0707` | 发布命名规则；线上已删除 |
| 构建提交点 | `b4b1c48`（2026-07-07 00:53:57 +0800） | 强推断：Lyra 槽时间戳在其之后 6 分钟，且它是 0713 tag 的祖先 |
| Lyra zip 时间戳 | `(2026, 7, 6, 16, 59, 50)` UTC = 北京 2026-07-07 00:59:50 | 从原件 APK 的 Lyra 槽直接读出 |
| 原件槽数 | 36 | 比 0713 少一个自研 mod 槽（`maplebirch-v3-layer-compat` 是 07-12 才加的） |

**取证限制**：0707 的远端 tag、本地 tag、Release 都已不存在；本仓库的
Actions 运行历史只保留到 2026-10-04，`gh run list` 里查不到 0707 当天的构建记录，
因此 **0707 的 ZIP 原件尺寸清单不可得**——本轮所有 ZIP 都没有尺寸对照物。

## 三、输入与证据等级

| 输入 | 取值 | 证据等级 |
|---|---|---|
| 构建配置 | `b4b1c48` 自带的 `config/*` | **确定** |
| 游戏 / 汉化 | DoL 0.5.10.12 + chs 1.0.8a | **确定**（prepare 下载，与原件同代） |
| ModLoaderGui | 925,677 B（boot.json `1.9.1`，2026-01-20 构建），取自原件槽 0 | **确定**（重建槽 0 与原件槽 0 逐字节相同） |
| 版本表 16 行 | 原件 APK 的 Lyra 槽内嵌版本表 | **确定**（重建 AU-F ZIP 槽 35 与原件槽 35 逐字节相同） |
| More Love | 原件槽 25 载荷（10,592 B，boot.json `0.1.6.0`，已带 drag 补丁） | **确定** |
| DOLI | 原件槽 34 载荷（1,137,387 B，boot.json `0.2.2`） | **确定** |
| Cheat Extended | 镜像 `cheat-extended-mirror-v1.18`（157,071 B） | **确定**（与原件槽 27 逐字节相同） |
| maplebirch | 上游 v3.1.14（136,144 B） | **确定**（与原件槽 26 逐字节相同） |
| maplebirchEx | 1.2.4（66,958 B） | **确定**（与原件槽 30 逐字节相同） |
| AU-F / AU-M / AU-A 模型载荷 | 本机缓存 `au_f/au_m/au_a.cache` | **确定到 0808 原件**（见第四节） |

**原件自身的一处不一致（照原样复现，未修正）**：0707 的版本表里 DOLI 行写的是
`v0.2.3`，而槽 34 载荷的 `boot.json` 是 `0.2.2`。重建按原件同时复刻了这两项
（版本表来自原件版本表、载荷来自原件槽），因此 AU-F ZIP 才能与原件槽位 36/36 全等。
这不是重建引入的问题，也不在本轮做「修正」——改任何一项都会立刻破坏逐字节等价。

## 四、AU 三个美化包：用 0808 原件做时代交叉证明

0707 的 AU-F APK 只内嵌 AU-F 一个模型，AU-M / AU-A 载荷无法从 0707 原件取证。
本轮改用**同代**的 0808 全套原件（8 件齐全）做交叉证明：把 0808 的
`au-f / au-m / au-a` APK 的槽 24 取出，与 0707 重建将使用的三份载荷逐字节比对。

| 载荷 | 字节数 | sha256（前 16） | 与 0808 原件槽 24 |
|---|---|---|---|
| AU-F | 54,519,851 | `6c20236bc300d794` | **相同** |
| AU-M | 46,875,870 | `c46389de100c2b6c` | **相同** |
| AU-A | 52,734,714 | `e93c82e20fbb8e80` | **相同** |

AU-A 另有一条独立佐证：本轮直接从上游 URL 重新下载
`AUandrogynous.model_v0.1.1.zip`，得到的字节与上表 `e93c82e2…` 完全一致
（即 0707 版本表里记录的 `AU-A v0.1.1`）。

三条证据合起来说明：0707 重建所用的三份美化包**就是那个时代的载荷字节**，
而不是「今天能下到的同名文件」。

## 五、重建过程中真正踩到的三个坑

1. **AU-A 载荷下载被 SSL 抖动打断**。`warmup` 在
   `AUandrogynous.model_v0.1.1.zip` 上报
   `SSL: UNEXPECTED_EOF_WHILE_READING`，属于代理/链路抖动而非上游缺失：
   同一 URL 单发重试即成功，且字节与缓存、0808 原件三方一致。
   处置：把已证明同字节的载荷预置进 `workspace/temp/au_a.mod.zip`，
   `warmup` 见到已存在文件会跳过下载（0713 / 0802 / 0804 用的是同一机制）。
2. **驱动脚本的输入校验路径写错**。ModLoaderGui 由下载钩子覆盖到
   `base/mods/`，而校验函数只查 `mods/`，于是把正确的输入报成 `MISSING`
   并中止（导致 `versions.json` 覆写没执行）。修正后 12 项输入全部 OK。
3. **worktree 里没有 `dol.jks`**。0707 年代的构建期签名会读仓库根的开发密钥，
   缺失时四码 APK 会在签名步骤失败（首轮 4 个里只成功 1 个）。
   补上密钥后按码重跑即 4/4 成功。开发签名只是中间态，最终四码都用
   **正式密钥**重签（见 0804 档案第三节的密钥说明）。

## 六、产物清单（正式密钥签名后）

| 文件 | 字节数 | sha256 |
|---|---|---|
| `-base-0707.zip` | 62,899,022 | `9885cdc7843be6312d5244f3489a931a9690e3d4b485653d949d7da9c043fc20` |
| `-au-f-0707.zip` | 111,784,128 | `9fbe25f1e3c178617c450867250635e39d6cf6254df38ca1c67b623fc67a8032` |
| `-au-m-0707.zip` | 103,932,370 | `1bfdca09fc005681dcb8868ef65aa63f581d6740c67451c156f6f92722ee0bbd` |
| `-au-a-0707.zip` | 109,883,285 | `62bf875e6b6ffc7cabf74fc736406fc49605c8f42c4f34d06cf05f70cc5dd961` |
| `-base-0707.apk` | 81,669,296 | `d72aad97bed8246fe4267e451d4dca6bc7fad67499c32d9044a0e26e129c62a0` |
| `-au-f-0707.apk` | 130,555,614 | `1966d0a733dcfbab5a97fc00fdca16183c3bdae82083328508cbaea9215067bf` |
| `-au-m-0707.apk` | 122,703,582 | `6fe601befa11418c827b29d27137c281322f510c4a91bc2c58e8bf72b0aef30c` |
| `-au-a-0707.apk` | 128,655,070 | `6781c0d6cc88f9c2497d9e0f708c4ddf9c8fcdc526fec1be2798b438a91fcda9` |

注意：`-au-f-0707.apk` 的 sha256 与原件 `244ba1a0…` **不同**——两者条目集合、
每一条目的未压缩内容、压缩方式、压缩后大小、标志位与签名块都相同，
差别只在 ZIP 条目的存放顺序，所以整个文件的哈希必然不同。

## 七、验证方法与实测输出

```text
verify_apk_equivalence.py  原件 au-f APK  vs  重建 au-f APK
  entries: A=21939 B=21939  same-set=True   same-order=False
  CONTENT mismatches (sha256 of stored data): 0
  header-level mismatches (same content): 0
  META-INF/DOL.RSA / DOL.SF / MANIFEST.MF: IDENTICAL

compare_slots.py  原件 au-f APK  vs  重建 au-f ZIP
  slots=36 vs 36    differing slots: 0 / 36

_aligned_slot_check.py  重建 au-m ZIP  vs  原件 au-f APK
  36 槽中 2 处不同：槽 24（AU 模型，型号不同）、槽 35（Lyra 标题行）

_aligned_slot_check.py  重建 au-a ZIP  vs  原件 au-f APK
  36 槽中 2 处不同：槽 24（AU 模型，型号不同）、槽 35（Lyra 标题行）

_aligned_slot_check.py  重建 base ZIP  vs  原件 au-f APK（分段对齐）
  槽 0–23 全等；槽 25–35 只有 Lyra 槽不同（1011 B vs 1017 B）

compare_slots.py  四码各自 ZIP vs APK
  au-f 36/36、au-m 36/36、au-a 36/36、base 35/35   全等

keytool -printcert -jarfile（四个 APK）
  SHA256 均为 B2:1C:D1:5B:…:B8:29:EC:E6（正式密钥）

输入复核（warmup 后、构建前，逐槽 sha256）
  12/12 OK（modloader_gui / au_f / more_love / maplebirch / cheat_extended /
  custom_hair / mae_picvary / maplebirch_expansion / guide_to_me /
  neoui_patch / npc_social_icon / doli）
```

## 八、边界（必须写进任何对外说明）

- **逐字节一致仅指逐条目内容**：ZIP 条目存放顺序与时间戳仍与原件不同，
  文件级 sha256 必然不同；本条与 0713 / 0804 的结论口径相同。
- **0707 只有 AU-F APK 一件原件**。base / AU-M / AU-A 三个 APK 与四份 ZIP
  都没有原件，只能做组件级与交叉一致性验证；0707 的 ZIP 尺寸也**没有**任何
  历史清单可比（Actions 历史已不可得）。
- **构建提交点是强推断**：由 Lyra 槽时间戳、祖先关系与提交语义共同推出，
  不是 tag 记录的直接证据。
- **载体结构性差异**：ZIP 比 APK 多 `CREDITS.md` / `LICENSE` / `README.md`，
  APK 多 Cordova 脚手架文件，属载体固有区别，不是构建错误。
- **本轮未发布**：八件产物只留在本机 `DOL-X-rebuild-0707\output\`（本机路径，与本仓库同级）；
  0707 的远端 tag 与 Release 目前都不存在，任何恢复线上条目的动作
  （创建 tag、触发 CI、公开可见）都需要先经用户确认。
