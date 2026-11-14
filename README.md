# DOL-X / XFox 游戏整合包

[![Build](https://github.com/XFoxLG/DOL-X/actions/workflows/build.yaml/badge.svg)](https://github.com/XFoxLG/DOL-X/actions/workflows/build.yaml)

## 目录

**玩家看这里**

- [简介](#简介)
- [特色](#特色)
- [下载与版本选择](#下载与版本选择)
- [包含哪些 Mod](#包含哪些-mod)
- [当前版本说明](#当前版本说明)
- [玩家更新日志](玩家更新日志.md)
- [疑难解答](#疑难解答)
- [使用须知](#整合包使用须知)

**开发者看这里**

- [与上游 DoL-Lyra 的关系](#与上游-dol-lyra-的关系)
- [开发者指南](#开发者指南)
- [历史更新日志](#历史更新日志)
- [Credits](#credits)

---

## 简介

DOL-X 是由 XFoxLG 维护的游戏整合包，基于 [DoL-Lyra](https://github.com/DoL-Lyra/Lyra) 构建系统。

本项目使用 [汉化仓库][github-chs] 的正式发行，整合汉化、美化与功能模组。各版本的内容和适用范围见发布说明。

**当前稳定版：[1014](https://github.com/XFoxLG/DOL-X/releases/tag/v0.5.11.9-1.0.0a-1014)**。提供基础版、AU-F、AU-M、AU-A 的 ZIP 与 APK；历史版本见 [Releases](https://github.com/XFoxLG/DOL-X/releases)。十一月候选仍在测试。

**APK 包名**: DoL XFox (`com.vrelnir.dol.xfox`)

---

## 与上游 DoL-Lyra 的关系

DOL-X 跟随 [DoL-Lyra](https://github.com/DoL-Lyra/Lyra) 的游戏、汉化及通用构建更新，维护自己的模组组合与兼容修复。

- **版本组合**：提供基础版及 AU-F、AU-M、AU-A。
- **基础美化**：采用通用战斗美化（UCB）。
- **兼容维护**：按游戏、框架与模组版本验证更新。

### 相关文档

- 📌 [当前项目状态](docs/CURRENT_PROJECT_STATE.md) - 当前版本与测试状态
- 📖 [上游友好策略](UPSTREAM_FRIENDLY_STRATEGY.md) - 同步流程与项目配置
- 📋 [上游差异摘要](UPSTREAM_DIFF_SUMMARY.md) - 当前长期维护差异
- 📖 [Mod 矩阵决策说明](MOD_MATRIX_RATIONALE.md) - 为什么这样选择 Mod 组合？

---

## 特色

- ✅ **自动化构建**：基于 Lyra 构建与上游检查流程
- ✅ **多版本支持**：基础版 + 3 个 AU 变体（AU-F、AU-M、AU-A）
- ✅ **模组框架**：秋枫白桦框架 + cheatExtended 作弊扩展
- ✅ **内置组件**：ModLoader + 汉化 + 美化包（UCB）
- ✅ **双平台**：ZIP（浏览器版）+ APK（Android 版）

### 包含的 Mod

**1014 稳定版的基础 Mod**（四种版本共有；名称对应汉化 [模组列表 Wiki](https://degreesoflewditycn.miraheze.org/wiki/%E6%A8%A1%E7%BB%84%E5%88%97%E8%A1%A8)）：
- ModLoader GUI - 模组管理器
- ModI18N - 汉化支持
- 秋枫白桦框架（maplebirch）+ 官方拆分功能包（更长遭遇战、言灵作弊集）
- [通用战斗美化](https://github.com/site098/mysterious)（UCB）
- [更多恋人](https://github.com/Nephthelana/DoL-More-Love-Interests-Mod)
- [自定义染发](https://github.com/HiddenCirno/DoL-CustomHair/tree/CustomHair)
- [NPC侧边栏头像](https://github.com/Maenoko/Mae-s-Picvary-NPC-mod/tree/DOL)（Mae's Picvary）
- [NPC社交栏头像](https://github.com/Eudemonism00/DOL-NPC-Avatars-Mod)
- [控制NPC嘴部](https://github.com/Ayndpa/DOL-GuideToMe)
- [作弊拓展](https://github.com/chris81605/Degrees-of-Lewdity_Cheat_Extended)（cheatExtended）
- [更长遭遇战](https://github.com/MaplebirchLeaf/LongerCombat)（LongerCombat）
- [言灵作弊集](https://github.com/MaplebirchLeaf/YanlingCheatCollection)（YanlingCheatCollection）
- [旧版图片名称适配](https://github.com/mirrormirroronwall/Legacy-Art-Mods-Compat)（社区 plus 版，来源见[附件说明](https://github.com/XFoxLG/DOL-X-Mirrors/releases/tag/legacy-art-compat-plus-v1.1)）
- [D.O.L.I](https://github.com/ArsNativa/Degrees-of-Lewdity-Intelligence)（AI 对话与战斗文本，需自行配置 API 密钥）
- NeoUI Patch - UI 美化

**可选 AU 系列**：

> AU（AOKIUTAGE）是一整套大型美化体系，包含人物模型、服装模型、脸部模型；下面列的是其中的
> 体型模型（各版本三选一），脸部模型由独立的 AU Face 脸部扩展提供。

- AU-F：AU 女性模型 v0.9.3
- AU-M：AU 男性模型 v0.4.2
- AU-A：AU 双性模型 v0.1.1

> AU 模型使用 AOKIUTAGE 官方 `mod` 发布页的 ModLoader 直装方式。

## 下载与版本选择

在 [1014 稳定版](https://github.com/XFoxLG/DOL-X/releases/tag/v0.5.11.9-1.0.0a-1014)或 [Releases 页面](https://github.com/XFoxLG/DOL-X/releases)下载对应版本：

- **ZIP**：电脑浏览器直接打开玩
- **APK**：安卓设备安装使用，兼容性见对应版本说明

| 版本 | 文件名后缀 | 内容 |
|------|-----------|------|
| 基础版 | `-base-` | 不含 AU 体型模型（用游戏原版体型） |
| AU-F 版 | `-au-f-` | 基础版 + AU 女性模型 |
| AU-M 版 | `-au-m-` | 基础版 + AU 男性模型 |
| AU-A 版 | `-au-a-` | 基础版 + AU 双性模型 |

> AU Face 脸部扩展仅加入三个 AU 版本；基础版不含 AU 模型或 AU Face。Legacy-Art-Mods-Compat plus 用于四种 4.x 版本。

## 包含哪些 Mod

**1014 稳定版内置以下 Mod**（名称对应汉化 [模组列表 Wiki](https://degreesoflewditycn.miraheze.org/wiki/%E6%A8%A1%E7%BB%84%E5%88%97%E8%A1%A8)；历史版本的组成以对应 Release 为准）：

| Mod | 作用 |
|-----|------|
| ModLoader GUI | 游戏内的模组管理器 |
| 汉化（ModI18N） | 自带对应游戏版本的简体中文汉化 |
| [秋枫白桦框架](https://github.com/MaplebirchLeaf/SCML-DOL-maplebirchFramework)（maplebirch） | 其他 Mod 依赖的核心框架；1014 使用 4.1.14，0802、0804、0808 使用 4.1.13，0707、0713 使用 3.1.14 |
| [更长遭遇战](https://github.com/MaplebirchLeaf/LongerCombat) | 旧扩展包对应功能的官方独立继任者；4.x 主线使用 v1.0.1 |
| [言灵作弊集](https://github.com/MaplebirchLeaf/YanlingCheatCollection) | 旧扩展包言灵功能的官方独立继任者；4.x 主线使用 v1.0.1 |
| [通用战斗美化](https://github.com/site098/mysterious)（UCB） | 战斗画面美化 |
| [更多恋人](https://github.com/Nephthelana/DoL-More-Love-Interests-Mod) | v0.1.7.0；增加可攻略 NPC，并适配 DoL 0.5.10.x 食物系统 |
| [自定义染发](https://github.com/HiddenCirno/DoL-CustomHair/tree/CustomHair) | 自定义发色 |
| [NPC侧边栏头像](https://github.com/Maenoko/Mae-s-Picvary-NPC-mod/tree/DOL)（Mae's Picvary） | 侧边栏显示 NPC 立绘头像 |
| [NPC社交栏头像](https://github.com/Eudemonism00/DOL-NPC-Avatars-Mod) | 社交界面显示 NPC 头像 |
| [控制NPC嘴部](https://github.com/Ayndpa/DOL-GuideToMe) | 控制 NPC 嘴部动作 |
| [作弊拓展](https://github.com/chris81605/Degrees-of-Lewdity_Cheat_Extended)（cheatExtended） | 作弊功能；1014 使用 v1.20，头部遮罩相容模式也由它提供 |
| [旧版图片名称适配](https://github.com/mirrormirroronwall/Legacy-Art-Mods-Compat) | 社区 plus 提供旧/新图片命名兼容；来源与许可见[附件说明](https://github.com/XFoxLG/DOL-X-Mirrors/releases/tag/legacy-art-compat-plus-v1.1) |
| [D.O.L.I](https://github.com/ArsNativa/Degrees-of-Lewdity-Intelligence) | AI 对话与战斗文本增强，使用 AI 功能需在游戏内自行配置服务和 API 密钥 |
| NeoUI Patch | 界面美化（侧边栏点击外部关闭等） |

> `maplebirch-v3-layer-compat` 只属于 0713 的 maplebirch 3.x 稳定栈。4.x 升到 4.1.13 后已退役，不再注入；源码仅作为旧版回滚资料保留。

**历史 AU 整合版额外内置的体型模型**（每版只含其中一个）：

- **AU-F 版**：AU 女性模型
- **AU-M 版**：AU 男性模型
- **AU-A 版**：AU 双性模型

## 当前版本说明

**当前稳定版本**：`v0.5.11.9-1.0.0a-1014`

- **游戏版本**：DoL 0.5.11.9（“伟大等同者”）· **汉化**：1.0.0a
- **Mod 栈**：maplebirch 4.1.14 + Cheat Extended 1.20 + LongerCombat 1.0.1 + YanlingCheatCollection 1.0.1 + Legacy-Art-Mods-Compat plus 1.0.3-plusV1.1
- **下载**：提供基础版、AU-F、AU-M、AU-A 的浏览器版 ZIP 和安卓版 APK。
- **测试情况**：AU-F 版在 MuMu 12（Android 12）上验证了换脸、桌宠、作弊菜单、存读档与开局流程；基础版、AU-M、AU-A 仅完成构建和打包内容检查。详见 [1014 Release 说明](docs/release-notes/v0.5.11.9-1.0.0a-1014.md)。
- **框架 4.1.14** 恢复了「每日 NPC 怀孕周期」。退回旧框架前请导出存档，新版写入的怀孕数据可能无法由旧版继续处理。
- 0.5.10.12 线的 `-0808`、`-0804`、`-0802`、`-0713` 与 `-0707` 同样提供四种版本的 ZIP、APK；兼容性以对应版本说明为准。
- **模组附件**：[DOL-X-Mirrors](https://github.com/XFoxLG/DOL-X-Mirrors) 提供部分版本归档，作者来源与校验值见镜像清单。
- 各版本玩家可感知的变化见 [玩家更新日志](玩家更新日志.md)；当前版本与测试状态见 [`docs/CURRENT_PROJECT_STATE.md`](docs/CURRENT_PROJECT_STATE.md)。

> **已知问题与使用提示（1014 稳定版）**：
> - 开启「PC 模型模式」后，部分具名 NPC 缺少动态服装数据。可关闭该模式，使用「NPC 侧边栏图像显示」。
> - AU Face 换脸后仪态不匹配的问题已在 0808 修复。其它脸部报错请保留存档与错误信息反馈。
> - AU Face 的雀斑、腮红、泪痕显示仍有待验证；1014 的取图兼容调整未观察到视觉改善。
> - 「碱性糖改脸」的小人和桌宠眼睛发白，尚未修复，可暂时换用其它脸型。
> - AU 桌宠右侧出现脸部特写边缘时，可将「桌宠遮罩分割线」设为 0px。
> - DOLI 发布版本为 v0.2.3，包内显示 0.2.2；NPC Avatars 发布版本为 1.4，包内显示 1.4.1。
> - 云存档需自行配置服务器；本地存档与导出存档可独立使用。
>
> 完整变更记录见 [CHANGELOG.md](CHANGELOG.md)。

> **旧版本提示**：2026-06-13 及更早的版本（文件名带 `57346 / 58370 / 59394 / 61442` 等旧编号）配置有误、缺少美化，建议使用 1014 稳定版或[汉化组正式发行][github-chs]。历史版本的兼容性以对应更新说明为准。

## 疑难解答

> [!NOTE]
>
>  参考 [【疑难解答】](https://dol-lyra.github.io/hub/troubleshoot/)

> [!IMPORTANT]
>
> **使用本整合出现各种问题时请先使用 [汉化仓库][github-chs] 发布的版本，或是汉化仓库提供的 [汉化在线版][github-chs-pages]，测试是否同样出现问题，参考 [发布下载版](https://github.com/Eltirosto/Degrees-of-Lewdity-Chinese-Localization/blob/main/README.md#%E5%8F%91%E5%B8%83%E4%B8%8B%E8%BD%BD%E7%89%88)。如问题同样能够复现请前往汉化仓库反馈；如问题只在本整合内出现请向本仓库反馈**

> [!IMPORTANT]
>
> 本整合中的兼容或显示问题可在 [Issues](https://github.com/XFoxLG/DOL-X/issues) 反馈，请附版本、复现步骤与错误信息。

- APK 版打开之后是英文，左下角也没有 modloader？

  更新 Android System WebView 后重试；仍无法使用时，可尝试浏览器版 ZIP。

- 为什么用 modloader 加载 zip 会提示 `bootJson文件 [boot.json] 无效`？

  本仓库分发的为完整游戏本体+mod的 **`整合包`**，并非单独的 mod，请勿使用 modloader 加载

- 中英文混杂？

  卸载 `modloader - 旁加载` 中的汉化 mod，整合包已自带对应游戏版本的汉化

- 明明下载了有美化的包为什么美化没有生效？

  检查是否加载了图片包 mod `GameOriginalImagePack-*.mod.zip`，有则 **`卸载`**

  本整合并未使用 mod 方式加载图片资源，图片包 mod 优先级在游戏 `img` 文件夹之上，所以在加载了图片包 mod 的情况下整合自带的图片不会生效

- 美化出现了奇怪的错位/黑边/光头？

  请先移除旁加载的图片包并复测；仍有异常时，附截图、版本与复现步骤反馈。

---

## 开发者指南

> 以下内容面向想参与构建、测试或二次开发的开发者，普通玩家无需阅读。

### 本地验证

修改配置后快速检查：

```bash
python tools/quick_check.py
```

### 测试流程

GitHub Actions 构建完成后：

```bash
# 1. 生成公开 base 测试清单
python tools/download_latest_build.py --build-code 15704320

# 2. 手动下载 APK 到 downloads/test_builds/{date}-{commit}/

# 3. 安装测试（按照自动生成的 TEST_CHECKLIST.md）
```

详见 [docs/TESTING_GUIDE.md](docs/TESTING_GUIDE.md)。

### 产物文件名格式

```
DoL-{原版版本}-XFox-{汉化版本}-{体型}-{日期}.apk
```

示例：`DoL-0.5.10.12-XFox-1.0.8a-base-0730.apk`。完整 mod 组成由本页和构建记录承载；稳定 Release 以 tag、体型和日期识别。完整变更记录见 [CHANGELOG.md](CHANGELOG.md)。

### Mod 开发工具链

- 🚀 [TypeScript Mod 模板](https://github.com/XFoxLG/DOL-X-TS-Mod-Template) - 现代化 TS 开发环境
- 🔧 [ModLoader 文档](docs/MODLOADER_OVERVIEW.md) - ModLoader 使用说明
- ✅ [同步检查清单](UPSTREAM_SYNC_CHECKLIST.md) - 如何保持与上游同步

---

## 历史更新日志

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
    - `DoL-{游戏版本}-XFox-{汉化版本}-{体型}-{日期}.{zip,apk}`
  - tag 格式
    - `v{游戏版本}-{整合版本}a-{日期}`

- 本整合包为完整游戏本体，请勿将压缩包作为 mod 在 modloader 内加载

- 本整合包中 Android 端应用名称修改为 `DoL XFox`，包名为 `com.vrelnir.dol.xfox`，且与原版及汉化版共存，请使用导出存档功能转移存档

- 根据汉化仓库中的 [免责声明](https://github.com/Eltirosto/Degrees-of-Lewdity-Chinese-Localization/blob/main/README.md#%E5%85%8D%E8%B4%A3%E5%A3%B0%E6%98%8E)

  > 汉化组不对任何修改后的汉化版本负责，包括但不限于修改游戏本体 html 文件，使用可能改变游戏内容的模组，使用他人发布的整合包等；汉化组也不会为任何第三方发布的模组版/修改版/魔改版/整合包等背书或担保。请在反馈问题前检查游戏是否已被修改，若被修改请勿提交，我们可能不会接受使用修改版本的内容反馈。

  在使用本整合包出现问题时在未判断问题是否由本整合包引入之前请勿向汉化仓库反馈

- 第三方作品归各作者所有，来源与许可证见[资源说明](docs/DISTRIBUTION_POLICY.md)。

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
