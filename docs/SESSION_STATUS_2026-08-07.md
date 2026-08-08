# 会话状态 2026-08-07：AU 换脸同步与旧存档迁移

本文是当前恢复入口，优先级高于更早的会话状态记录。当前分支是 `vega`，本轮起点
HEAD 为 `4bfe21cf891308bbfd9aff4e7504693c363a791d`。本轮修复已提交为 `cf60d15` 并推送
`vega`，分支 CI 与全四码干跑均已通过；截至 2026-08-08 尚未打 tag 或创建 Release。

正式 APK 签名已经通过一次性公钥加密 Actions 流程从现有 `SIGNING_KEY` Secret 恢复。本机恢复的
PKCS12 keystore 只有一个 `dol` PrivateKeyEntry，证书 SHA-256 为
`b21cd15b9ff02d603a20d94b8403d5d9661946518f88e0551474c93ab829ece6`，并已完成真实 JAR
签名/验签。项目内副本位于 `.local/DO_NOT_UPLOAD_FORMAL_SIGNING_KEY/dol-release-formal.jks`，
`.local/` 受 Git 忽略且目录 ACL 仅允许当前 Windows 账户；项目外 Documents 副本保留作第二份
备份。恢复用临时远程分支、加密 artifact、一次性私钥、密文和 worktree 均已删除；GitHub 原 Secret
未修改。项目根目录的 `dol.jks` 仍是不同指纹的测试 key，不能用于正式覆盖安装。

## 用户复现与根因

用户在 AU-F 角色创建中复现：只切换脸型、不再选择仪态时，模型没有正确同步并会缺少
眼睛；选一次仪态后才恢复。过去的 8/8 测试在每次换脸时同时指定了第一个合法仪态，绕过了
这个真实路径，因此旧结论不能覆盖本次问题。

真实 DoL 0.5.10.12 的角色创建、镜子和作弊页三个换脸入口，在切换 `$facestyle` 后都把
`$facevariant` 固定设为 `default`。DoL 自带脸型遵循这个约定，但 AU model 的非传统脸型
把真实图片目录名注册为仪态值，例如“大眼鼠鼠”“猫猫脸”“Q萌一号”，没有相应的
`default` 目录。于是 UI 稳定地产生非法的 `facestyle/default` 组合，并请求不存在的 eyes、
sclera、iris、eyelids、lashes 图片。这是 DoL UI 与 AU model 脸型注册值之间的契约问题，
不是独立的“AU面部扩展”加密选择器问题，也不是随机图片加载失败。

## 已实现修复

`lyra/build.py` 增加 AU-only 的 Maplebirch payload 补丁：复用框架现有的
`modifyFaceStyle()` owner，在 `ModI18N` 完成翻译后修改最终 Passage。三个换脸入口都从
`setup.faceVariantOptions[$facestyle]` 选择第一个已注册值；只有脸型没有任何注册仪态时才
回退到 `default`。base 构建码 `15704320` 明确跳过，AU-F/M/A 三个公开码均应用。

旧存档修复放在 DoL `backComp` 的无条件兼容区。当前脸型存在注册仪态且保存值不在合法列表
中时，才改成第一个合法值。合法值保持不变；没有注册仪态列表的第三方脸型保持不变。该行为是
用户选择的“自动修复非法脸型/仪态组合”方案，不仅限于非法值恰好等于 `default` 的情况。

最初实现是在构建期直接改主 HTML。运行时 A/B 已证明该 owner 错误：正式 0807 包与隔离热修包
均加载 `ModI18N 1.0.8a` 且主语言为 `zh`，正式包的 `Widgets Settings` 为中文，而预先改写
HTML 的热修包整段仍为英文。`ModI18N` 的 `i18n.json` 明确包含“请选择游戏模式、角色创建、
体型、脸型、仪态”等规则，并依赖 Passage 与位置；预先改变同一 Passage 会使整组规则不应用。
因此旧 HTML 写入路径已退役。构建现在只读验证三个 UI 与一个迁移的原始 HTML 上下文仍各一次、
旧预汉化补丁为零；真正修复只写入 Maplebirch `dist/inject_early.js`。payload patch 要求真实
`modifyFaceStyle()` 插入点唯一，运行时又要求四个最终 Passage 的旧上下文各唯一，否则 fail-closed。

`tools/au_artifact_check.py` 已扩展为同时审计 ZIP 和 APK。AU 产物必须保持原 HTML 四个未改写的
翻译输入，同时内嵌 Maplebirch payload 必须包含唯一后汉化 marker 与完整 3+1 行为规则，不能只
凑够 marker；同时必须覆盖互异的嵌套腮红层号 1、2、3、4、5，外层和内嵌 payload
的重复层不重复计数，`blush-6` 等额外编号不能替代缺失层。workflow 在 ZIP/APK 上传前运行该
审计。构建矩阵完整性继续由 `main.py build` 作为唯一 owner：每个请求码乘两种格式都会创建任务，
任一任务失败都会返回非零，不在 AU 审计器内重复维护第二份矩阵。

## MuMu 12 运行时证据

正式应用 `com.vrelnir.dol.xfox` 与独立测试应用
`com.vrelnir.dol.xfox.facehotfix` 并行安装。正式应用没有卸载、覆盖或清数据；最终核对仍为
`firstInstallTime=2026-07-20 02:48:30`、`lastUpdateTime=2026-08-07 13:10:24`。

角色创建真实 UI 验证不是直接改变量：逐个点击传统、Kiss、Nss、Twinkle、兔子、加辣、沅芷、
碱性糖八个真实脸型链接，每次不再点击仪态。8/8 都立即选中合法仪态，选中 radio 标签与
`$facevariant` 一致，角色内容 canvas 的八个哈希互不相同，reporter、console error、page error
均为零。

汉化安全候选使用正式 0807 原始 LF HTML，只替换一个内嵌 Maplebirch Base64 payload。源与目标
均为 995770 个 LF、0 个 CRLF；候选用隔离包名与本地测试证书覆盖测试应用，`firstInstallTime`
保持不变。运行时 `ModI18N 1.0.8a`、主语言 `zh`；`Widgets Settings` 中“请选择游戏模式、
角色创建、体型、脸型、仪态”全部存在，对应四个英文设置词全部不存在。`Widgets Mirror`、
`Cheats`、`Widgets Settings` 各有一个换脸 marker，`Widgets variablesVersionUpdate` 有一个迁移
marker，reporter 不可见。相同候选重新逐个点击八个真实脸型，8/8 合法且八个 canvas 哈希互异。

旧存档自然加载验证使用完整有效开局状态。第一次直接改 `V` 后立即保存没有提交 SugarCube
history，读档回到旧值，因此该尝试不算证据。最终流程先设置 `kiss改脸/default`，调用
`SugarCube.State.create(SugarCube.State.passage)` 提交 turn，再保存到隔离应用槽位 8；随后提交
`default/default`，再通过 `SugarCube.Save.slots.load(8)` 真实加载。结果正常进入
`Orphanage Intro`，自动迁移为 `kiss改脸/大眼鼠鼠`，reporter 不可见；页面有 4 个 canvas，
最大非透明像素数为 49972。槽位 8 已删除。

## APK 与签名边界

MuMu 正式候选包证书 SHA-256 是
`b21cd15b9ff02d603a20d94b8403d5d9661946518f88e0551474c93ab829ece6`；仓库本地
`dol.jks` 证书 SHA-256 是
`8c6eb4d6c9c889fa790bc07e0f53c07d714706a7be4fab2313d8fd23b1a0d2ed`。两者不同，
本地签名 APK 无法通过 `install -r` 覆盖 CI 候选，因此本轮使用独立包名运行时验证，不读取、
猜测或提交 GitHub signing secret。

历史并行测试 APK 在手工制作阶段曾把整份 HTML 换成 CRLF；该包以及后续直接改 LF HTML 的候选
都属于已退役的错误 owner，不能作为发布候选。新的隔离候选使用正式 0807 原始 LF HTML并只替换
Maplebirch payload，已通过新严格审计：原翻译输入 3+1、payload 行为 3+1、后汉化 marker 1、
腮红层号 1 至 5、零错误。候选证书为本地测试指纹 `8c6e…d2ed`，不是正式发布包。

## 验证与审查

新增测试覆盖：原 HTML 只读保持、三个入口、三个公开 AU 码、base 跳过、真实 Maplebirch owner、
幂等、上游方法/UI/迁移漂移、错误位置 marker、ZIP/APK 缺 payload 补丁、base APK 跳过、互异
腮红层 1 至 5，以及 workflow 在两种格式上传前执行审计。

独立 review 的首轮中等 finding 已处理：marker-only 假阳性、兼容登记 source 归属、第三方脸型
措辞、AU-F 状态和真机结果外推范围均已收紧。二次 review 找出的 base 补丁表述错误和腮红层只数
文件不验层号也已处理。汉化 A/B 又发现并纠正了预汉化 HTML owner；后续独立审查发现并关闭了
marker-only/截断 payload、只声明不执行、完整 IIFE 脱离 owner、重复 Maplebirch owner、AU 缺
Maplebirch 缓存、AU 产物改名和损坏嵌入清单七类 fail-open 边界。发布前最后一轮复审又关闭了两个
fail-open：`window.modDataValueZipList` 出现多次赋值时旧解析器只取第一个（运行时以最后一个为准，
审计会看到与实际加载不同的列表），现在判为 `duplicate_assignment` 不可审计错误；产物文件名含
零个或多个身份 token 时旧逻辑仅在检测到 AU payload 才报错，现在无条件要求每个 ZIP/APK 文件名
恰好声明一个 `base/au-f/au-m/au-a`。两处修复由 ZIP 与 APK 两条路径共享。最终完整 pytest 为 274 passed，
Python 编译、真实 Maplebirch 4.1.13 payload patch、新 APK 最终严格审计、MuMu 中文与换脸/读档
运行时均通过；最终独立复审无新 finding，`git diff --check` 返回 0（仅有 CRLF→LF 提示）。

## 仍未覆盖的边界

- 最初另一个旧存档错误涉及 `eyesFacestyle`、`mouthFacestyle`、`eyeColor` 等更老字段；失败
  存档已删除，无法确定正确迁移值。本轮不能声称修复了该独立问题。
- 运行时只覆盖 AU-F。AU-M/A 共享同一后汉化 Maplebirch payload 补丁但使用不同 model payload；base 明确不应用
  本补丁。三者都不能用 AU-F 结果冒充真机验证。
- 角色创建入口已用八个真实链接逐项验证；镜子和作弊页由同一逻辑的精确源码上下文、单元测试和
  产物门禁覆盖，但本轮没有分别在真机 UI 中逐个点击八种脸型。
- 正式发布仍需 CI 生成同源签名候选，下载后复核 ZIP/APK 审计报告，再用同证书 APK 覆盖安装
  MuMu 正式应用进行最终回归。
- MuMu 中仍安装独立测试应用 `DoL XFox Face Hotfix Test`。它与正式应用数据隔离；没有得到用户
  删除确认前不擅自卸载。

## 下一步顺序

最终全量 pytest 274 passed、Python 编译、JSON 解析、精确 APK 审计与 `git diff --check` 已完成并通过。
commit/push、branch CI 与全四码 release-tier 干跑均已完成（见下节）。`tests/test_download_latest_build.py`、
`tests/test_maplebirch_basehead_patch.py`、`tools/browser_smoke_test.py` 是 Windows CRLF 状态假阳性，
Git blob 已证明与 HEAD 完全一致，不要回滚也不要提交。剩余唯一动作是打 tag 并创建 Release，
需要用户明确授权。

## 最终验证结果（2026-08-08）

候选提交 `cf60d15` 已推送 `vega`。分支 CI run `31239491888` success（测试、构建、ZIP/APK 产物
审计、上传全部通过）。手动触发的全四码 `release-tier` 干跑 run `31239641405` success，release job
按分支语义 skipped，未创建 Release；8 个产物全部生成并通过新严格审计：AU 三码各命中 3+1+1
marker 与 5 个腮红层，base 干净；四个 APK 签名指纹均为正式
`b21cd15b9ff02d603a20d94b8403d5d9661946518f88e0551474c93ab829ece6`。

MuMu 12 上已用四码干跑生成的正式签名 AU-F APK 覆盖安装正式应用，`firstInstallTime` 保留、
`lastUpdateTime` 更新为 2026-08-08。运行时复验：Start 段落完整中文；8 个脸型链接逐个点击且不点
仪态时全部立即选中第一个合法仪态（default、大眼鼠鼠、冷脸萌、猫猫脸、宝石糖、温柔改、小圆眼、
Q萌一号），radio 均勾选，渲染画布哈希互异；`kiss改脸/default` 测试存档加载后自动迁移为
`kiss改脸/大眼鼠鼠`，reporter 为空，测试槽位已删除；console 无异常抛出，错误级条目全部为
离线环境网络拒绝与 Simple Frameworks 可选查找等良性/环境性日志，无 `img/face` 加载失败。

至此，除打 tag 与创建 Release 外的发布前验证全部完成。tag/Release 属于公开发布动作，仍需用户
明确授权后执行；授权后将使用现有正式签名 APK 四码产物与
`docs/release-notes/v0.5.10.12-1.0.8a-0808.md` 正文发布。发布 tag 为
`v0.5.10.12-1.0.8a-0808`，与 CHANGELOG 最新条目一致；workflow 按
`docs/release-notes/${GITHUB_REF_NAME}.md` 解析正文，缺文件时 fail-closed。
