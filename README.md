# DOL-X / XFox 自用整合包

[![Build](https://github.com/XFoxLG/DOL-X/actions/workflows/build.yaml/badge.svg)](https://github.com/XFoxLG/DOL-X/actions/workflows/build.yaml)

## 目录

- [简介](#简介)
- [特色](#特色)
- [下载](#下载)
- [版本说明](#版本说明)
- [疑难解答](#疑难解答)
- [更新日志](#更新日志)
- [使用须知](#使用须知)
- [Credits](#credits)

---

## 简介

DOL-X 是 XFox 自用整合包发布仓库。本项目基于 [DoL-Lyra](https://github.com/DoL-Lyra/Lyra) 构建系统（直接上游构建流程来源），但不是本仓库的项目身份。

本项目使用 [汉化仓库][github-chs] 的汉化产物，通过 GitHub Actions 自动化构建，提供多种 Mod 组合，并跟随游戏和汉化更新。

**本仓库不是 DoL 或汉化组官方发布渠道**

**APK 包名**: DoL XFox (`com.vrelnir.dol.xfox`)

---

## 与上游 DoL-Lyra 的关系

DOL-X 基于 [DoL-Lyra](https://github.com/DoL-Lyra/Lyra) 构建系统，采用"**上游友好**"策略：

- ✅ **核心同步**：保持构建系统 (`lyra/`) 与上游同步，跟随上游 bug 修复和性能优化
- 🎨 **Mod 独立**：维护独立的 Mod 组合策略，针对自用场景优化
- 📚 **文档完整**：详细记录与上游的差异和决策理由

### 主要差异

| 对比项 | 上游 Lyra | DOL-X |
|--------|-----------|-------|
| **身份标识** | Lyra | XFox |
| **基础美化** | BESC 推荐 | UCB 唯一 |
| **AU 组合** | AU（单独） | AU+UCB |
| **作弊 Mod** | cheat + CSD | cheatExtended + maplebirch |
| **版本数量** | 约 10 个 | 4 个（精简） |

### 相关文档

- 📖 [Mod 矩阵决策说明](MOD_MATRIX_RATIONALE.md) - 为什么这样选择 Mod 组合？

---

## 快速开始

### 开发者

#### 本地验证（< 2 分钟）

修改配置后快速检查：

```bash
python tools/quick_check.py
```

#### 测试流程

GitHub Actions 构建完成后：

```bash
# 1. 生成测试清单
python tools/download_latest_build.py --build-code 15706368

# 2. 手动下载 APK 到 downloads/test_builds/{date}-{commit}/

# 3. 安装测试（按照自动生成的 TEST_CHECKLIST.md）
```

详见 [docs/TESTING_GUIDE.md](docs/TESTING_GUIDE.md)

---

## 版本追踪

### APK 文件名格式（2026-06-24 更新）

```
DoL-{dol_ver}-XFox-{chs_ver}-{mod_suffix}-{date}-{commit}.apk
```

示例：`DoL-0.5.8.10-XFox-3.1.3a-ucb-more-love-...-0615-e0b1a4b.apk`

- `e0b1a4b`：commit hash 短码（7位）- 清晰标识版本
- 每次构建文件名唯一，避免测试混淆

详见 [CHANGELOG.md](CHANGELOG.md)

### Mod 开发

想开发自己的 Mod？DOL-X 提供完整的开发工具链：

- 🚀 [TypeScript Mod 模板](https://github.com/XFoxLG/DOL-X-TS-Mod-Template) - 现代化 TS 开发环境
- 📚 [高级 Mod 开发指南](docs/ADVANCED_MOD_DEV.md) - 完整开发文档
- 🔧 [ModLoader 文档](docs/MODLOADER_OVERVIEW.md) - ModLoader 使用说明
- ✅ [同步检查清单](UPSTREAM_SYNC_CHECKLIST.md) - 如何保持与上游同步

---

## 特色

- ✅ **自动化构建**：GitHub Actions 云端构建，每周自动检测更新
- ✅ **多版本支持**：基础版 + 3 个 AU 变体（AU-F、AU-M、AU-A）
- ✅ **现代框架**：秋枫白桦框架 + cheatExtended 作弊扩展
- ✅ **完整集成**：ModLoader + 汉化 + 美化包（UCB）
- ✅ **双平台**：ZIP（浏览器版）+ APK（Android 版）

### 包含的 Mod

**基础 Mod**（所有版本，名称对应汉化 [模组列表 Wiki](https://degreesoflewditycn.miraheze.org/wiki/%E6%A8%A1%E7%BB%84%E5%88%97%E8%A1%A8)）：
- ModLoader GUI - 模组管理器
- ModI18N - 汉化支持
- 秋枫白桦框架（maplebirch）+ 秋枫白桦扩展包
- [通用战斗美化](https://github.com/site098/mysterious)（UCB）
- [更多恋人](https://github.com/Nephthelana/DoL-More-Love-Interests-Mod)
- [自定义染发](https://github.com/HiddenCirno/DoL-CustomHair/tree/CustomHair)
- [NPC侧边栏头像](https://github.com/Maenoko/Mae-s-Picvary-NPC-mod/tree/DOL)（Mae's Picvary）
- [NPC社交栏头像](https://github.com/Eudemonism00/DOL-npcicon-mods/)
- [控制NPC嘴部](https://github.com/Ayndpa/DOL-GuideToMe)
- [作弊拓展](https://github.com/chris81605/Degrees-of-Lewdity_Cheat_Extended)（cheatExtended，含言灵集）
- [D.O.L.I](https://github.com/ArsNativa/Degrees-of-Lewdity-Intelligence)（AI 对话/战斗文本，需玩家自填 API key）
- NeoUI Patch - UI 美化
- `maplebirch-v3-layer-compat` - 自研兼容 mod（NPC 侧边栏图层命名兼容）

**可选 AU 系列**：
- AU-F：AU 女性模型 v0.9.3（与上游 Lyra 当前 AU model 对齐）
- AU-M：AU 男性模型 v0.4.2
- AU-A：AU 双性模型 v0.1.1

> AU 模型使用 AOKIUTAGE `mod` release 的 ModLoader 直装方式；AU Face 改脸扩展是 `facemod` release 下的独立 mod，当前禁用。

## 下载

访问 [Releases](https://github.com/XFoxLG/DOL-X/releases) 下载最新版本。

### 版本选择

从 [Releases](https://github.com/XFoxLG/DOL-X/releases) 按文件名后缀选择，每个版本都有 ZIP（浏览器版）和 APK（安卓版）：

| 版本 | 文件名后缀 | 说明 | 推荐 |
|------|-----------|------|------|
| 基础版 | `-base-` | 当前启用 Mod 集合，不含 AU 体型模型 | ⚪ |
| AU-F 版 | `-au-f-` | 基础版 + AU 女性模型 | ⭐ |
| AU-M 版 | `-au-m-` | 基础版 + AU 男性模型 | ⭐ |
| AU-A 版 | `-au-a-` | 基础版 + AU 双性模型 | ⭐ |

> **💡 推荐说明**：
> - ⭐ **AU 变体**：推荐版本，包含完整的视觉美化和体型模型（AU-F 为已实测版本）
> - ⚪ **基础版**：不含 AU 模型，适合偏好原版体型或自行加载 AU 模型的用户
> 
> **AU 状态**：AU 体型模型（AU-F v0.9.3 / AU-M / AU-A）已随对应版本内置；AU Face 改脸扩展当前禁用，不进入构建。

> **⚠️ 重要更新（2026-06-15）**：
> - Build Code 已更新，新增 3 个 ModLoader Mod（custom_hair、mae_picvary、maplebirch_expansion）
> - **重要**：移除 Custom-Spellbook（功能已被 Cheat Extended 言灵集完全覆盖）
> - **版本兼容性警告**：Custom Hair Mod 仅支持 DoL v0.5.2.7 - v0.5.2.10，升级游戏版本前请查阅 [已知问题文档](docs/KNOWN_ISSUES.md)
> - Longer Combat 使用非官方修复版，已验证与 maplebirch 框架兼容
> - 详见 [MOD_MATRIX_RATIONALE.md](MOD_MATRIX_RATIONALE.md) 和 [已知问题文档](docs/KNOWN_ISSUES.md)

## 版本说明

### 当前稳定版本（tag `v0.5.10.12-1.0.8a-0713`）

当前构建配置：
- **游戏版本**：DoL 0.5.10.12（跟随汉化仓库更新）
- **框架**：maplebirch v3.1.14（B 线稳定分支）+ cheatExtended v1.18
- **基础 Mod**：UCB + more_love + maplebirch + maplebirch_expansion + cheatExtended + custom_hair + mae_picvary + guide_to_me + npc_social_icon + DOLI
- **自研兼容 mod**：`maplebirch-v3-layer-compat`（把 maplebirch v4 的 NPC 侧边栏图层连字符命名逻辑 back-port 到 v3.1.14，修复侧边栏立绘与衣服层）
- **产物**：4 体型（base / AU-F / AU-M / AU-A）× 双格式（ZIP + APK），共 8 个
- **构建方式**：GitHub Actions 云端自动化，推 tag 触发出包并发布 Release
- **测试状态**：AU-F 包已在 MuMu 模拟器（APK）+ 浏览器上实测通过（DOLI 悬浮窗图标正常、NPC 侧边栏立绘正常）；其余 base / AU-M / AU-A 三个包同批构建、共用同一套 mod（仅体型资源不同），预期一致但未逐个上机验证。

> **已知情况说明（非缺陷）**：
> - **同时开启「NPC 侧边栏图像显示」+「PC 模型模式」两个开关后，侧边栏里有名字的剧情角色（如萨姆）不显示衣服**：这些角色在模型系统里没有配套衣服数据可显示，是秋枫白桦框架的设计边界（框架未给原版 NPC 配衣柜数据），并非本整合的 bug，也无法通过重新打包修复。**规避**：只开「NPC 侧边栏图像显示」即可正常显示 NPC 立绘，不要再叠加「PC 模型模式」（两开关都在「模组设置 → 秋枫白桦框架」里）。
> - **AU 改脸切换时出现 `Failed to load image .../eyes.png` 提示**：是 AU 改脸包自身缺合并图层的无害提示，图像仍正常加载、不影响游戏；弹出红框可直接点 **Clear** 或 **Close** 消掉。
>
> 详见 [CHANGELOG.md](CHANGELOG.md)。

### ⚠️ 历史版本兼容性警告

**已废弃版本（2026-06-13 及之前）**：
- Build Codes：~~57346 / 58370 / 59394 / 61442~~
- **问题**：配置错误（缺少 UCB 美化，cheat_csd 残留）
- **状态**：技术上可运行，但不推荐使用
- **建议**：请下载最新的 GitHub Actions 构建产物

**如何获取最新版本**：
1. 访问 [Actions 页面](https://github.com/XFoxLG/DOL-X/actions?query=branch%3Avega+is%3Asuccess)
2. 点击最新的成功构建（绿色✓）
3. 下载 Artifacts 中的 `dol-builds-zip` 或 `dol-builds-apk`
4. 产物保留期：90 天

> **2026-06-13 更新**：移除 BESC，改用 UCB 作为唯一战斗美化。详见 [MOD_MATRIX_RATIONALE.md](MOD_MATRIX_RATIONALE.md)。

## 疑难解答

> [!NOTE]
>
>  参考 [【疑难解答】](https://dol-lyra.github.io/hub/troubleshoot/)

> [!IMPORTANT]
>
> **使用本整合出现各种问题时请先使用 [汉化仓库][github-chs] 发布的版本，或是汉化仓库提供的 [汉化在线版][github-chs-pages]，测试是否同样出现问题，参考 [发布下载版](https://github.com/Eltirosto/Degrees-of-Lewdity-Chinese-Localization/blob/main/README.md#%E5%8F%91%E5%B8%83%E4%B8%8B%E8%BD%BD%E7%89%88)。如问题同样能够复现请前往汉化仓库反馈；如问题只在本整合内出现请向本仓库反馈**

> [!IMPORTANT]
>
> 本仓库无法受理任何打包问题以外的美化问题

- APK 版打开之后是英文，左下角也没有 modloader？

  更新系统 `webview`，或尝试使用 `兼容版`，都不行可以使用现代浏览器打开 [在线版](#在线)

- 为什么用 modloader 加载 zip 会提示 `bootJson文件 [boot.json] 无效`？

  本仓库分发的为完整游戏本体+mod的 **`整合包`**，并非单独的 mod，请勿使用 modloader 加载

- 中英文混杂？

  卸载 `modloader - 旁加载` 中的汉化 mod，整合包已经自带了对应游戏版本的最新汉化

- 明明下载了有美化的包为什么美化没有生效？

  检查是否加载了图片包 mod `GameOriginalImagePack-*.mod.zip`，有则 **`卸载`**

  本整合并未使用 mod 方式加载图片资源，图片包 mod 优先级在游戏 `img` 文件夹之上，所以在加载了图片包 mod 的情况下整合自带的图片不会生效

- 美化出现了奇怪的错位/黑边/光头？

  所使用的美化未跟进最新的游戏内容

## 更新日志

<details>
<summary>点击展开</summary>

- 20260121

  重构打包脚本

- 20251216

  通过修改 `ModLoader` 使内置的 `汉化/作弊/CSD` 可被禁用/调整顺序

  默认将全部内置以降低打包成本

- 20250201

  添加新美化，移除旧美化

- 20240415

  添加 `kr特写刘海补充`

- 20240310

  添加 `Susato Model`

- 20240215

  添加 `DOL_BJ_hair_extend`

- 20240102

  添加 polyfill 版本

  重命名仓库

- 1118

  使用 ModLoader 打包

- 1110

  HP 重命名为 CSD

- 1017

  版本说明及下载表格移至独立发布页

- 1014

  作弊添加更多功能：关闭成就锁、启用言灵

- 1009

  更精细的美化版本种类

- 1007

  添加 BEEESSS Wax 身体美化

- 0914

  移除世界扩展

  使用新格式HP显示

- 0911

  修改特写命名

  > 特写1 -> KR特写
  > 特写2 -> BJ特写

- 0908

  新增世界扩展作为底包

- v1.3.0-0904

  修正特写2未被应用的问题

- v1.3.0-0903

  添加特写1和特写2及HP显示

- v1.3.0-0902

  首次更新

</details>

## 整合包使用须知

- 版本格式

  - 文件名格式
    - `dol-{原版版本号}-chsmods-{汉化版本号}-{MODS}-{日期}[.{修订号}].{zip,apk}`
  - tag 格式
    - `{原版版本号}-{汉化版本号}-{日期}[.{修订号}]`

- 本整合包为完整游戏本体，请勿将压缩包作为 mod 在 modloader 内加载

- 本整合包中 Android 端应用名称修改为 `DoL XFox`，包名为 `com.vrelnir.dol.xfox`，且与原版及汉化版共存，请使用导出存档功能转移存档

- 根据汉化仓库中的 [免责声明](https://github.com/Eltirosto/Degrees-of-Lewdity-Chinese-Localization/blob/main/README.md#%E5%85%8D%E8%B4%A3%E5%A3%B0%E6%98%8E)

  > 汉化组不对任何修改后的汉化版本负责，包括但不限于修改游戏本体 html 文件，使用可能改变游戏内容的模组，使用他人发布的整合包等；汉化组也不会为任何第三方发布的模组版/修改版/魔改版/整合包等背书或担保。请在反馈问题前检查游戏是否已被修改，若被修改请勿提交，我们可能不会接受使用修改版本的内容反馈。

  在使用本整合包出现问题时在未判断问题是否由本整合包引入之前请勿向汉化仓库反馈

## Credits

- <img decoding="async" src="https://gitgud.io/uploads/-/system/user/avatar/9096/avatar.png" width="24"> $\color{purple} {Vrelnir}$
  - [Vrelnir 的博客][blog]
  - [英文游戏维基][wiki-en]
  - [中文游戏维基][wiki-cn]
  - [官方 Discord][discord]
  - [游戏源码仓库][gitgud]
- [原版汉化仓库][github-chs]
  - [为汉化仓库做出过贡献的诸位][github-chs-credits]
- [DoL-Lyra][github-lyra]
- Mod
  - [Lyra-CombatStatusDisplay][lyra-csd]
  - [Lyra-Cheat][lyra-cheat]
- 美化
  - [Degrees of Lewdity Plus][dolp]
  - [Degrees of Lewdity Graphics Mod][beeesss]
    - BEEESSS
  - [BEEESSS Community Sprite Compilation][beeesss-ext]
    - BEEESSS, ethanatortx, MatchaCrepeCakes, LedhaKuromi, Tommohas, Jessplayin690, SkyFall669/SomethingIsHuntingYou, AvinsXD, okbd321, cloversnipe, Elegant_Dress_5771, doseonseng, G259M, VanityDecay, Hikari, luoyin mengling, Tieba user_5CU79bt, Xiaochien, cheese shredded cake, artiste (the gayest man alive), Suqi eggplant stew, Paril, La Maritza, AD calcium, Isari, 森谷華子, aqua, superhydroxide, 再3棘, 567600, ToumanLin, Isopod, ◌/あきやま, Poop, SydNekoKawaii, Bunnyberry<3, Mizzy, 長門有栖☆, 七玳, 墮天使
  - [BEEESSS Wax][beeesss-wax]
    - Paril, b333sss
  - [Susato Model][susato-model]
    - susato, miyako2428
  - [通用战斗美化 UCB][ucb-github]
    - 贴吧用户\_GaC5V7E
- 特写
  - [Hikari][hikari]
  - [Goose][goose]
  - [Paril Double Cheeseburger][sideview-dc]
    - Paril, b333sss, Zubonko, Blaine
  - [DOL BJ hair extend][sideview-bj-extend]
    - Zubonko
  - [韩站特写][sideview-kr]
    - G259M
  - [KR特写刘海补充][sideview-kr-extend]
    - 贴吧用户\_GaC5V7E

[blog]: https://vrelnir.blogspot.com
[wiki-en]: https://degreesoflewdity.miraheze.org/wiki
[wiki-cn]: https://degreesoflewditycn.miraheze.org/wiki
[gitgud]: https://gitgud.io/Vrelnir/degrees-of-lewdity/-/tree/master
[discord]: https://discord.gg/VznUtEh
[github-chs]: https://github.com/Eltirosto/Degrees-of-Lewdity-Chinese-Localization
[github-chs-credits]: https://github.com/Eltirosto/Degrees-of-Lewdity-Chinese-Localization/blob/main/CREDITS.md
[github-chs-pages]: https://eltirosto.github.io/Degrees-of-Lewdity-Chinese-Localization/
[beeesss]: https://gitgud.io/BEEESSS/degrees-of-lewdity-graphics-mod
[beeesss-ext]: https://gitgud.io/Kaervek/kaervek-beeesss-community-sprite-compilation
[beeesss-wax]: https://gitgud.io/GTXMEGADUDE/beeesss-wax
[sideview-dc]: https://gitgud.io/GTXMEGADUDE/double-cheeseburger
[sideview-bj-extend]: https://github.com/zubonko/DOL_BJ_hair_extend
[sideview-kr]: https://arca.live/b/textgame/83875947
[sideview-kr-extend]: https://tieba.baidu.com/p/9055647926
[github-lyra]: https://github.com/DoL-Lyra
[lyra-csd]: https://github.com/DoL-Lyra/CombatStatusDisplay
[lyra-cheat]: https://github.com/DoL-Lyra/Cheat
[susato-model]: https://discord.com/channels/675158131688603721/1216104862870147303
[ucb-github]: https://github.com/site098/mysterious
[dolp]: https://gitgud.io/Frostberg/degrees-of-lewdity-plus
[hikari]: https://gitgud.io/HikariT/hikari-mods
[goose]: https://gitgud.io/goose/createshit
