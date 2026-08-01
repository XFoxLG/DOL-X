# DOL-X 当前项目状态

**核验日期**：2026-08-02

**事实基线**：`vega` 的 4.x 公开主线 + `vega-archive-0713` 历史稳定归档

本文是 DOL-X 当前状态的唯一总入口。带日期的会话记录、贴吧/Discord 抓取和
`MOD_MATRIX_RATIONALE.md` 中的旧决策只保留历史价值；与本文冲突时，以配置、锁文件、GitHub 实况和
本文列出的验证结果为准。

## 1. 项目与分支

- DOL-X 是 `XFoxLG/DOL-X` 自用整合包，不是 DoL、汉化组或 DoL-Lyra 官方发布渠道。
- 直接构建上游是 `DoL-Lyra/Lyra`，上游默认分支为 `vega`；同步方向是
  `DoL-Lyra/Lyra -> DOL-X`。
- 0713 稳定基线保存在 `vega-archive-0713`，归档分支已在 GitHub 核验存在。
- `vega` 从该干净基线重建为 4.x 公开主线，只包含公共配置、代码、测试和文档。
  4.x 主线已由 tag `v0.5.10.12-1.0.8a-0802` 正式发版，取代 0713 成为最新稳定版。

## 2. 4.x 公开主线栈

当前 `vega` 使用 DoL `0.5.10.12` / 汉化 `1.0.8a`，框架与功能 mod 为：

- maplebirch Framework `4.1.13`（作者官方 Release）。
- Cheat Extended `1.20(dev260719)`（作者官方 Pre-release）。
- LongerCombat `1.0.1` 与 YanlingCheatCollection `1.0.1`（作者官方独立继任包）。
- Legacy-Art-Mods-Compat `1.0.3-plusV1.1`（社区二改，原作者 README 明确允许二改二传）。
- 旧 maplebirchEx `1.2.4` 与 `maplebirch-v3-layer-compat` 只保留作 3.x 回滚资料，不进入 4.x 产物。

用户真机日志证明 4.x 基础栈达到 `0 error / 0 warning`，Cheat Extended UI 可打开且抽样
功能可用。LongerCombat 与 Yanling 已挂载，但没有逐功能遍历，因此状态是“运行时挂载通过”，不是
“全功能通过”。

### 上游版本核对（2026-08-02）

逐个仓库核对结果：maplebirch `4.1.13`、LongerCombat `1.0.1`、YanlingCheatCollection `1.0.1`、
NeoUI `1.1.0`、GuideToMe `1.1.0`、CustomHair、Mae's Picvary `1.3.2`、NPC Avatars `1.4.1`
均已是上游最新，无待升级项。

唯一存在上游新版的是 More Love Interests Mod：上游已发布 `v0.1.7.0`（2026-06-27），
本仓库仍钉 `v0.1.6.0`。依赖上可升（`v0.1.7.0` 要求 GameVersion `>=0.5.10.0`，当前游戏
`0.5.10.12` 满足），但恋人系统改动会碰 `Widgets Attitudes` 与 `time.js` 的替换规则，
属存档相关高影响面，0802 发版刻意不带，留给下一轮单独验证。

AU 四个资产（三个 model + AU Face）与 Cheat Extended 的官方 asset digest 逐一比对
`config/mods.lock.json`，全部一致，无同 tag 原位换包。

### Release tag 与包内声明版本不一致的两个 mod

以下差异属上游作者未同步 manifest，不是构建取错版本：

| Mod | Release tag | 包内 `boot.json` | 运行时显示 |
|-----|------------|-----------------|-----------|
| DOLI | `v0.2.3` | `0.2.2` | `0.2.2` |
| NPC Avatars | `1.4` | `1.4.1` | `1.4.1` |

ModLoader 读取包内 `boot.json`，所以 Mod 管理器里看到的版本以该列为准。

另有一处此前的记录错误已在本轮修正：DOLI 的 `dependenceInfo` 只要求 ModLoader `^2.0.0`，
maplebirch 出现在 `addonPlugin` 且范围为 `^3.1.0`，**不覆盖当前的 4.1.13**，因此框架内的
Options 入口在 4.x 下不注册。DOLI 自带 `patches/overlay-replace.json`，在检测不到
maplebirch 时于游戏原生 Options 覆盖层补一个 DOLI 按钮，配置入口仍可达、功能不失效。

## 3. 构建矩阵与公开分发边界

`config/combinations.toml` 仍保留四个本地构建码：

- base `15704320`
- AU-F `15705344`
- AU-M `15706368`
- AU-A `15708416`

公开 CI 分支推送构建 base + AU-F，tag 发版构建全部四码。手动触发
（`workflow_dispatch`）新增 `build_tier` 输入，选 `release` 可在不打 tag 的前提下
干跑全四码，release job 仍受 `github.ref_type == 'tag'` 保护、不会误发 Release。

AU-M 与 AU-A 在此之前从未经 CI 构建过（分支档只含 base + AU-F）。首次全四码干验证由
run [`30709200905`](https://github.com/XFoxLG/DOL-X/actions/runs/30709200905) 完成，
8 个产物（四体型 × ZIP/APK）全部生成，证明这两个组合的资源链可用。

真机测试只覆盖 AU-F；base / AU-M / AU-A 使用同一套 mod、仅体型资源不同，构建成功但
未逐个上机验证。

## 4. AU Face 与 plus

AU Face 官方资产存在三层版本身份：Release 正文 `1.0.4`、外层 `boot.json` `1.1.0`、解密后内层
`1.2.8`。AU-F 真机已验证设置 UI 和交互可用，但内层会请求旧式 `blushN` / `tearN` 图片名。

社区 plus 增加对应 `blush-N` / `tears-N` 映射。用户旁加载 A/B 后，旧路径红框消失、独立嘴部仪态
有效；面纹和流泪视觉仍未完整验收。plus 通过 additive ImageLoaderHook side hook 工作，不修改
`lyra/` 核心。DOL-X Release `legacy-art-compat-plus-v1.1` 的资产 SHA-256 为：

`df1debd4425467c60553a15e090a870b6924c2102614ccab4ff716776d17a727`

## 5. 已知产品边界

- maplebirch “PC 模型模式”需要 NPC wardrobe 数据。当前没有 mod 注册衣柜，动态 NPC 回落
  `naked` 是数据缺失后的设计行为；使用 Mae's Picvary 静态侧边栏图即可规避。
- maplebirch 云存档没有公共服务地址。官方只提供 Go+SQLite 与 Cloudflare Worker+R2+D1 自建源码；
  Go 后端还缺客户端会调用的 `/save-code` 路由。
- AU model 的 `kiss改脸/.../eyes.png` 缺图与 AU Face 的 `blushN`/`tearN` 是两类问题，不应混记。
- AU Face 面纹/流泪剩余视觉问题位于加密内层运行时边界，DOL-X 没有白盒修复手段，不阻塞 base 主线。

## 6. 来源与验证

主要原始来源：

- DOL-X：https://github.com/XFoxLG/DOL-X
- DoL-Lyra：https://github.com/DoL-Lyra/Lyra
- 汉化：https://github.com/Eltirosto/Degrees-of-Lewdity-Chinese-Localization
- maplebirch：https://github.com/MaplebirchLeaf/SCML-DOL-maplebirchFramework
- Cheat Extended：https://github.com/chris81605/Degrees-of-Lewdity_Cheat_Extended
- LongerCombat：https://github.com/MaplebirchLeaf/LongerCombat
- Yanling：https://github.com/MaplebirchLeaf/YanlingCheatCollection
- AU：https://github.com/AOKIUTAGE/UTAGEsDOL3.0
- Legacy compat：https://github.com/mirrormirroronwall/Legacy-Art-Mods-Compat

本轮已核验：GitHub Release/branch 实况、官方资产 digest、上游各 mod 最新版本、
包内 `boot.json` 声明版本、plus ZIP manifest、配置加载、Python 编译、201 项自动测试，
以及 GitHub Actions 全四码构建（run `30709200905`，8 个产物）。

真机验收只覆盖 AU-F；AU-M / AU-A 仅有构建成功记录，无上机验证。
