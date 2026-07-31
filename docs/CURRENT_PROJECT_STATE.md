# DOL-X 当前项目状态

**核验日期**：2026-07-31

## 2. 4.x 公开主线栈

当前 `vega` 使用 DoL `0.5.10.12` / 汉化 `1.0.8a`，框架与功能 mod 为：

- maplebirch Framework `4.1.13`（作者官方 Release）。
- Cheat Extended `1.20(dev260719)`（作者官方 Pre-release）。
- LongerCombat `1.0.1` 与 YanlingCheatCollection `1.0.1`（作者官方独立继任包）。
- Legacy-Art-Mods-Compat `1.0.3-plusV1.1`（社区二改，原作者 README 明确允许二改二传）。
- 旧 maplebirchEx `1.2.4` 与 `maplebirch-v3-layer-compat` 只保留作 3.x 回滚资料，不进入 4.x 产物。

设备日志记录 4.x 基础栈达到 `0 error / 0 warning / 340 info`，Cheat Extended UI 可打开且抽样
功能可用。LongerCombat 与 Yanling 已挂载，但没有逐功能遍历，因此状态是“运行时挂载通过”，不是
“全功能通过”。

## 4. AU Face 与 plus

AU Face 官方资产存在三层版本身份：Release 正文 `1.0.4`、外层 `boot.json` `1.1.0`、内层运行时
`1.2.8`。AU-F 真机已验证设置 UI 和交互可用，但内层会请求旧式 `blushN` / `tearN` 图片名。

社区 plus 增加对应 `blush-N` / `tears-N` 映射。旁加载对照后，旧路径红框消失、独立嘴部仪态
有效；面纹和流泪视觉仍未完整验收。plus 通过 additive ImageLoaderHook side hook 工作，不修改
`lyra/` 核心。DOL-X Release `legacy-art-compat-plus-v1.1` 的资产 SHA-256 为：

`df1debd4425467c60553a15e090a870b6924c2102614ccab4ff716776d17a727`

## 5. 已知产品边界

- maplebirch “PC 模型模式”需要 NPC wardrobe 数据。当前没有 mod 注册衣柜，动态 NPC 回落
  `naked` 是数据缺失后的设计行为；使用 Mae's Picvary 静态侧边栏图即可规避。
- maplebirch 云存档没有公共服务地址。官方只提供 Go+SQLite 与 Cloudflare Worker+R2+D1 自建源码；
  Go 后端还缺客户端会调用的 `/save-code` 路由。
- AU model 的 `kiss改脸/.../eyes.png` 缺图与 AU Face 的 `blushN`/`tearN` 是两类问题，不应混记。

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

本轮已核验：GitHub Release/branch 实况、官方资产 digest、plus ZIP manifest、配置加载、Quick Check、
Python 编译、195 项自动测试，以及 GitHub Actions base ZIP/APK 构建和 artifact 上传。AU 三个本地
变体仍未取得公开转载授权，也未由公共 Actions 构建或上传。
