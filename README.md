# DOL-X / XFox 自用整合包

[![Build](https://github.com/XFoxLG/DOL-X/actions/workflows/build.yaml/badge.svg)](https://github.com/XFoxLG/DOL-X/actions/workflows/build.yaml)

## 目录

**玩家看这里**

- [简介](#简介)
- [特色](#特色)
- [下载与版本选择](#下载与版本选择)
- [包含哪些 Mod](#包含哪些-mod)
- [当前版本说明](#当前版本说明)
- [疑难解答](#疑难解答)
- [使用须知](#整合包使用须知)

**开发者看这里**

- [与上游 DoL-Lyra 的关系](#与上游-dol-lyra-的关系)
- [开发者指南](#开发者指南)
- [历史更新日志](#历史更新日志)
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

- ✅ **选择性同步**：跟随上游通用构建修复，但不声称 `lyra/` 与上游逐文件相同
- 🎨 **Mod 独立**：维护独立的 Mod 组合策略，针对自用场景优化
- 📚 **差异可审计**：正式记录项目自治范围、供应链和公共/私有边界

### 主要差异

| 对比项 | 上游 Lyra | DOL-X |
|--------|-----------|-------|
| **身份标识** | Lyra | XFox |
| **基础美化** | BESC 推荐 | UCB 唯一 |
| **AU 组合** | AU（单独） | AU+UCB |
| **作弊 Mod** | cheat + CSD | cheatExtended + maplebirch |
| **构建矩阵** | 约 10 个 | 本地 4 码；公共 Actions 仅 base |

### 相关文档

- 📌 [当前项目状态](docs/CURRENT_PROJECT_STATE.md) - 当前事实、验证和发布边界
- 📖 [上游友好策略](UPSTREAM_FRIENDLY_STRATEGY.md) - 如何同步且不污染上游
- 📋 [上游差异摘要](UPSTREAM_DIFF_SUMMARY.md) - 当前长期维护差异
- 📖 [Mod 矩阵决策说明](MOD_MATRIX_RATIONALE.md) - 为什么这样选择 Mod 组合？

---

## 特色

- ✅ **自动化构建**：GitHub Actions 云端构建，每周自动检测更新
- ✅ **本地多版本支持**：基础版 + 3 个 AU 变体（AU-F、AU-M、AU-A）
- ✅ **现代框架**：秋枫白桦框架 + cheatExtended 作弊扩展
- ✅ **完整集成**：ModLoader + 汉化 + 美化包（UCB）
- ✅ **双平台**：ZIP（浏览器版）+ APK（Android 版）

### 包含的 Mod

**4.x 公开主线的基础 Mod**（四个本地构建码共有；名称对应汉化 [模组列表 Wiki](https://degreesoflewditycn.miraheze.org/wiki/%E6%A8%A1%E7%BB%84%E5%88%97%E8%A1%A8)）：
- ModLoader GUI - 模组管理器
- ModI18N - 汉化支持
- 秋枫白桦框架（maplebirch）+ 官方拆分功能包（更长遭遇战、言灵作弊集）
- [通用战斗美化](https://github.com/site098/mysterious)（UCB）
- [更多恋人](https://github.com/Nephthelana/DoL-More-Love-Interests-Mod)
- [自定义染发](https://github.com/HiddenCirno/DoL-CustomHair/tree/CustomHair)
- [NPC侧边栏头像](https://github.com/Maenoko/Mae-s-Picvary-NPC-mod/tree/DOL)（Mae's Picvary）
- [NPC社交栏头像](https://github.com/Eudemonism00/DOL-npcicon-mods/)
- [控制NPC嘴部](https://github.com/Ayndpa/DOL-GuideToMe)
- [作弊拓展](https://github.com/chris81605/Degrees-of-Lewdity_Cheat_Extended)（cheatExtended）
- [更长遭遇战](https://github.com/MaplebirchLeaf/LongerCombat)（LongerCombat）
- [言灵作弊集](https://github.com/MaplebirchLeaf/YanlingCheatCollection)（YanlingCheatCollection）
- [旧版图片名称适配](https://github.com/mirrormirroronwall/Legacy-Art-Mods-Compat)（DOL-X 使用经授权可二改二传的社区 plus）
- [D.O.L.I](https://github.com/ArsNativa/Degrees-of-Lewdity-Intelligence)（AI 对话/战斗文本，需玩家自填 API key）
- NeoUI Patch - UI 美化

**可选 AU 系列**：
- AU-F：AU 女性模型 v0.9.3（与上游 Lyra 当前 AU model 对齐）
- AU-M：AU 男性模型 v0.4.2
- AU-A：AU 双性模型 v0.1.1

> AU 模型使用 AOKIUTAGE `mod` Release 的 ModLoader 直装方式。作者 README 明确禁止二传、倒卖、
> 拆包和未经授权搬运，因此 DOL-X 保留 AU 三码给本地自构建，但公共 GitHub Actions 只构建、上传
> 不含 AU 资源的 base。获得作者明确授权前，不新增公开 AU artifact 或 Release。

## 下载与版本选择

到 [Releases 页面](https://github.com/XFoxLG/DOL-X/releases) 下载最新公开版本。每个公开版本可能提供：

- **ZIP**：电脑浏览器直接打开玩
- **APK**：安卓手机安装玩（推荐用 MuMu 等模拟器或较新手机）

0713 历史 Release 曾提供四种体型。新的 4.x 公共 Actions 在授权边界澄清前只发布 base；下表中的
AU 三码只表示本地构建能力，不表示可以从 DOL-X 公开下载：

| 版本 | 文件名后缀 | 和基础版的区别 | 推荐 |
|------|-----------|------|------|
| 基础版 | `-base-` | 不含 AU 体型模型（用游戏原版体型） | ✅ 公共 Actions |
| AU-F 版 | `-au-f-` | 基础版 + AU 女性模型 | 本地自构建 |
| AU-M 版 | `-au-m-` | 基础版 + AU 男性模型 | 本地自构建 |
| AU-A 版 | `-au-a-` | 基础版 + AU 双性模型 | 本地自构建 |

**怎么选：**公开下载请选择基础版。需要 AU 时，请遵守作者 README，从作者官方 Release 获取资源并
在本地自构建，不要转载 DOL-X 生成的整合包。

> 已公开的 0713 稳定版仍不内置 AU Face。4.x 主线把 AU Face 仅加入三个本地 AU 变体；base 不含
> AU model 或 AU Face。Legacy-Art-Mods-Compat plus 进入所有 4.x 构建码，不占独立 bit。

## 包含哪些 Mod

**4.x 四个本地构建码都内置以下 Mod**（名称对应汉化 [模组列表 Wiki](https://degreesoflewditycn.miraheze.org/wiki/%E6%A8%A1%E7%BB%84%E5%88%97%E8%A1%A8)；0713 稳定包的精确组成以对应 Release 为准）：

| Mod | 作用 |
|-----|------|
| ModLoader GUI | 游戏内的模组管理器 |
| 汉化（ModI18N） | 简体中文，已自带对应游戏版本的最新汉化 |
| [秋枫白桦框架](https://github.com/MaplebirchLeaf/SCML-DOL-maplebirchFramework)（maplebirch） | 其他 Mod 依赖的核心框架；4.x 主线使用作者官方 v4.1.13 |
| [更长遭遇战](https://github.com/MaplebirchLeaf/LongerCombat) | 旧扩展包对应功能的官方独立继任者；4.x 主线使用 v1.0.1 |
| [言灵作弊集](https://github.com/MaplebirchLeaf/YanlingCheatCollection) | 旧扩展包言灵功能的官方独立继任者；4.x 主线使用 v1.0.1 |
| [通用战斗美化](https://github.com/site098/mysterious)（UCB） | 战斗画面美化 |
| [更多恋人](https://github.com/Nephthelana/DoL-More-Love-Interests-Mod) | 增加可攻略 NPC |
| [自定义染发](https://github.com/HiddenCirno/DoL-CustomHair/tree/CustomHair) | 自定义发色 |
| [NPC侧边栏头像](https://github.com/Maenoko/Mae-s-Picvary-NPC-mod/tree/DOL)（Mae's Picvary） | 侧边栏显示 NPC 立绘头像 |
| [NPC社交栏头像](https://github.com/Eudemonism00/DOL-npcicon-mods/) | 社交界面显示 NPC 头像 |
| [控制NPC嘴部](https://github.com/Ayndpa/DOL-GuideToMe) | 控制 NPC 嘴部动作 |
| [作弊拓展](https://github.com/chris81605/Degrees-of-Lewdity_Cheat_Extended)（cheatExtended） | 作弊功能；4.x 主线使用官方 v1.20 Pre-release，头部遮罩相容模式也由它提供 |
| [旧版图片名称适配](https://github.com/mirrormirroronwall/Legacy-Art-Mods-Compat) | 社区 plus 提供旧/新图片命名兼容；原作者允许二改二传 |
| [D.O.L.I](https://github.com/ArsNativa/Degrees-of-Lewdity-Intelligence) | AI 对话/战斗文本增强，**需要你自己在游戏里填 AI 接口密钥才生效**，不填则不工作、不影响其他功能 |
| NeoUI Patch | 界面美化（侧边栏点击外部关闭等） |

> `maplebirch-v3-layer-compat` 只属于 0713 的 maplebirch 3.x 稳定栈。4.x 升到 4.1.13 后已退役，不再注入；源码仅作为旧版回滚资料保留。

**AU 版额外内置的体型模型**（取决于你下载的是哪个版本，每个 AU 版只含其中一个）：

- **AU-F 版**：AU 女性模型
- **AU-M 版**：AU 男性模型
- **AU-A 版**：AU 双性模型

## 当前版本说明

**当前稳定版本**：`v0.5.10.12-1.0.8a-0713`

- **游戏版本**：DoL 0.5.10.12（跟随汉化仓库更新）
- **产物**：4 个版本（基础版 + AU-F / AU-M / AU-A）× 两种格式（ZIP + APK），共 8 个文件
- **测试情况**：AU-F 版已在 MuMu 模拟器和浏览器上实机测试通过；其余 3 个版本用的是同一套 Mod（只有体型资源不同），预期表现一致，但没有逐个上机验证。

**当前 `vega` 公开主线**：4.x 栈（尚未创建新 tag/Release）

- maplebirch 4.1.13 + Cheat Extended 1.20 + LongerCombat 1.0.1 + YanlingCheatCollection 1.0.1。
- 基础栈用户真机日志为 `0 error / 0 warning / 340 info`，作弊界面可打开，抽样功能正常。
- GitHub Actions run [`30611108121`](https://github.com/XFoxLG/DOL-X/actions/runs/30611108121) 已成功构建并上传
  `DoL-0.5.10.12-XFox-1.0.8a-base-0731.zip` 与 `.apk`；公开输出仅有 base。
- 四个 ZIP 已在本地成功构建并通过静态 payload 检查；基础版不含 AU/AU Face，三个 AU 版各含正确体型和 AU Face 1.1.0。
- AU Face 尚未完成三种体型真机验收，因此三个 AU 本地变体不是新稳定 Release，也没有公开上传。
- 当前事实、来源和发布边界见 [`docs/CURRENT_PROJECT_STATE.md`](docs/CURRENT_PROJECT_STATE.md)。

> **已知边界（当前 4.x 主线）**：
> - **同时打开「NPC 侧边栏图像显示」+「PC 模型模式」后，具名剧情 NPC 在动态模型里不显示衣服**：两个开关不是同一张图。「NPC 侧边栏图像显示」使用预绘制静态图；「PC 模型模式」用玩家纸娃娃系统动态生成，需要独立 NPC 衣柜数据。当前 4.x 主线没有任何 mod 注册衣柜，框架会按设计回落到 `naked`，不是图片路径 bug。**解决办法**：关闭「PC 模型模式」，只保留「NPC 侧边栏图像显示」，即可使用 Mae's Picvary 静态立绘。完整方案是制作独立 wardrobe 数据 mod，为每个 NPC 按地点注册服装；尚未实现。
> - **AU Face 面部扩展测试中出现 `Failed to load image img/face/default/blushN.png` / `tearN.png` 红框**：这是 AU Face 内层请求旧式文件名，而当前资源使用新式 `blush-N.png` / `tears-N.png`，不是 AU model 的 `kiss改脸` 问题。AU Face 设置 UI 已确认可打开，但脸红/高潮流泪等视觉效果还没通过；不要用“ModLoader 0 error”替代视觉验收。
> - **切换 AU 改脸时弹出 `Failed to load image .../kiss改脸/.../eyes.png` 红框**：这是 AU 美化本体自带改脸目录的缺图层提示，与 AU Face 是另一个独立 mod；直接点 **Clear** 或 **Close** 关掉即可。
> - **云存档面板没有可预填的服务地址**：maplebirch 4.1.13 自带云存档客户端和两套官方自建后端（Go+SQLite、Cloudflare Worker+R2+D1），但作者没有提供公共实例。DOL-X 不代为部署远程资源；需要使用时按源码文档自建，且不要填写未知第三方地址。
>
> 完整变更记录见 [CHANGELOG.md](CHANGELOG.md)。

> **⚠️ 提醒**：2026-06-13 及更早的旧版本（文件名里带 `57346 / 58370 / 59394 / 61442` 这类旧编号）配置有误、缺少美化，请不要再用，直接下载上面的最新版本即可。

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

---

## 开发者指南

> 以下内容面向想参与构建、测试或二次开发的开发者，普通玩家无需阅读。

### 本地验证（< 2 分钟）

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
- 📚 [高级 Mod 开发指南](docs/ADVANCED_MOD_DEV.md) - 完整开发文档
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
