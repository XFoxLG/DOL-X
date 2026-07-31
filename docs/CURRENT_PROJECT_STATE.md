# DOL-X 当前项目状态

**核验日期**：2026-07-31

**事实基线**：`vega` 的 4.x 公开主线 + `vega-archive-0713` 历史稳定归档

本文是 DOL-X 当前状态的唯一总入口。带日期的会话记录、贴吧/Discord 抓取和
`MOD_MATRIX_RATIONALE.md` 中的旧决策只保留历史价值；与本文冲突时，以配置、锁文件、GitHub 实况和
本文列出的验证结果为准。

## 1. 项目与分支

- DOL-X 是 `XFoxLG/DOL-X` 自用整合包，不是 DoL、汉化组或 DoL-Lyra 官方发布渠道。
- 直接构建上游是 `DoL-Lyra/Lyra`，上游默认分支为 `vega`；同步方向是
  `DoL-Lyra/Lyra -> DOL-X`。
- 0713 稳定基线保存在 `vega-archive-0713`，归档分支已在 GitHub 核验存在。
- `vega` 从该干净基线重建为 4.x 公开主线，只包含公共配置、代码、测试和文档。GitHub Actions
  run `30611108121` 已完成 base 构建与 artifact 上传；最新已打 tag 的稳定 Release 仍是 0713。

## 2. 4.x 公开主线栈

当前 `vega` 使用 DoL `0.5.10.12` / 汉化 `1.0.8a`，框架与功能 mod 为：

- maplebirch Framework `4.1.13`（作者官方 Release）。
- Cheat Extended `1.20(dev260719)`（作者官方 Pre-release）。
- LongerCombat `1.0.1` 与 YanlingCheatCollection `1.0.1`（作者官方独立继任包）。
- Legacy-Art-Mods-Compat `1.0.3-plusV1.1`（社区二改，原作者 README 明确允许二改二传）。
- 旧 maplebirchEx `1.2.4` 与 `maplebirch-v3-layer-compat` 只保留作 3.x 回滚资料，不进入 4.x 产物。

用户真机日志证明 4.x 基础栈达到 `0 error / 0 warning / 340 info`，Cheat Extended UI 可打开且抽样
功能可用。LongerCombat 与 Yanling 已挂载，但没有逐功能遍历，因此状态是“运行时挂载通过”，不是
“全功能通过”。

## 3. 构建矩阵与公开分发边界

`config/combinations.toml` 仍保留四个本地构建码：

- base `15704320`
- AU-F `15705344`
- AU-M `15706368`
- AU-A `15708416`

AU 作者仓库 README 明确写明 AU 原版部件及衍生内容“严禁二传、倒卖、拆包”和未经授权搬运。
因此四码只代表本地构建能力，不等于四个包都可由公共 Actions 重新分发。

公开 `.github/workflows/build.yaml` 只构建并上传 base `15704320`。AU 三码必须由用户从作者官方 Release
获取资源后在本地自构建，或在获得作者明确授权后再开放公共 artifact/Release。历史 0713 曾公开包含
AU，不构成继续分发的授权依据。

GitHub Actions run [`30611108121`](https://github.com/XFoxLG/DOL-X/actions/runs/30611108121) 已在提交
`fedcbf5` 上成功生成并上传：

- `DoL-0.5.10.12-XFox-1.0.8a-base-0731.zip`
- `DoL-0.5.10.12-XFox-1.0.8a-base-0731.apk`

日志中的 `PUBLIC_BUILD_CODES` 为 `15704320`，输出目录只有上述两件 base 产物。该次运行由分支推送
触发，所以 release job 按设计跳过；产物保存在 Actions artifact，不等同于新建 GitHub Release。

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

本轮已核验：GitHub Release/branch 实况、官方资产 digest、plus ZIP manifest、配置加载、Quick Check、
Python 编译、195 项自动测试，以及 GitHub Actions base ZIP/APK 构建和 artifact 上传。AU 三个本地
变体仍未取得公开转载授权，也未由公共 Actions 构建或上传。
