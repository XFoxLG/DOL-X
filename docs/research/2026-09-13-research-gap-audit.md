# DOL-X 调研查漏补缺报告（2026-09-13）

本文是本轮全面调研的综合交付，按项目记录分层规范写作：稳定事实、历史结论、
推测与阻塞分开；未提交、不发布，作为下一阶段决策的依据。核验日期均为 2026-09-13。

## 1. 可复现性基线（最重要的新发现）

当前 `vega` 源码（`415ab78`）与"已发布的 0808"之间隔着两条**输入漂移链**，
它们决定"下次构建会得到什么"：

1. **汉化底包在分支构建上取 latest**：`lyra/downloader.py` 的
   `download_from_chs_repo()` 在无 `--tag` 时请求 `releases/latest`。汉化仓库
   2026-08-14 已发布 `v0.5.11.9-chs-1.0.8a` 之后的最新版
   `v0.5.11.9-chs-1.0.0a`，因此下一次分支推送构建会拿到 **0.5.11.9 本体**。
   而 [build.yaml](../../.github/workflows/build.yaml) 的 tag 构建传
   `--tag`，不受影响。
2. **cheat_extended 资产在同 tag 下漂移且不被构建期校验**：
   `config/build.toml` 的 `download_url` 指向可变的 `Pre-release` 资产；
   `lyra/warmup.py:30` 的 `LOCKED_AU_PAYLOAD_CACHE_NAMES` 只强制校验
   `au_f/au_m/au_a/au_face` 四个包。当前 Pre-release 资产已变为
   `1.20(dev260903)`（350,866 字节，作者 changelog 声明 Dev20260815 起最低
   游戏版本 0.5.11.9，并新增 `scriptEarly/CE_environmentGuard.js`
   环境检测：错误环境会弹窗并禁用模组）。

**推论（待验证，非已证）**：下一次分支 CI 若照常跑，大概率出现
0.5.11.9 本体 + 0.5.10.12 适配补丁的组合，AU face variant 的构建期源码
校验（`lyra/build.py` 的 `_validate_au_face_variant_source`，按 0.5.10.12
汉化 HTML 上下文计数、fail-closed）很可能拒绝构建；即使过了构建，
cheat_extended 在 0.5.10.12 上也可能被运行时禁用。
当前栈要稳定重现 0808 已测状态，需要同时钉住汉化 tag 与 cheat_extended
具体资产 digest；这正是锁文件目前"记录了 digest 但没有在构建期强制"的缺口
（AU 包除外）。

兼容层登记表（`lyra/compatibility.py`）共注册 6 个 surface，全部带
版本指纹与失败保护：More Love 拖拽加固、DOLI 悬浮图标、Maplebirch 桌宠
remount、AU face 别名、AU face variant 选择、APK CDP 重连。
其中两个 Maplebirch 补丁按 `release_tag=maplebirch-release-v4.1.14`
登记，升级框架时登记表会 fail-closed，这是设计好的迁移闸门。

## 2. 上一轮报告与记忆的勘误

| 原表述 | 修正后事实 | 依据 |
|---|---|---|
| "周检通知链路断了，是缺陷" | Issues 通知是**有意退役**：仓库已关闭 Issues，workflow 注释明示结果写入 Summary+artifact（commit `85f4a50`，2026-08-01 会话记录）。真问题是 `docs/MOD_UPDATE_MONITORING.md` 仍描述旧 Issue 机制，且 Summary 对失败情形一律写"所有 Mod 均为最新" | `.github/workflows/mod-update-check.yml` 注释与步骤列表 |
| "周检没报 maplebirch 更新（监控盲区）" | 周检**报了**：今日 run `34736902333` 的 `mod-updates.json` 工件含 maplebirch v4.1.14→v4.3.1（high）与 cheat_extended 同 tag 换包（medium） | 工件已下载核对 |
| "当前最优升级目标 = 0.5.11.9 + maplebirch 4.2.x" | 降级为**候选路线 B**，未经验证：4.2.x 是大重构线；汉化 1.0.0a 是新系列首版，成熟度证据仅一个月 | 本报告第 3 节 |
| "v4.1.14 随时可发版" | 增加两个前置：钉住 cheat_extended 漂移、确认分支/构建输入策略；tag 构建本身钉汉化，不受第一条影响 | 本报告第 1 节 |
| "AU 服装生态稀薄、bes 是绝对中心" | 保留为 7 月的**研究方向假设**。带日期的第三方评估（DoLModding Wiki Imagepacks 页）把 AU 列为 "Actively developed, almost complete"，与 Goose Female 同级；未做全量统计前不下生态排名 | dolmodding.miraheze.org/wiki/DoL_Plus/Imagepacks（本次抓取） |

## 3. 上游核验结论（全部经 Release API / 包内 boot.json 实证）

| 组件 | 当前锁定 | 上游现状 | 结论 |
|---|---|---|---|
| 汉化/本体 | 0.5.10.12 + 1.0.8a | `v0.5.11.9-chs-1.0.0a`（08-14）；原版已到 0.5.12.11（fishing、怀孕系统重写） | 候选升级底座，1.0.0a 成熟度待观察 |
| maplebirch | 4.1.14（runtime-smoke-passed，未发版） | 4.2.9 要求本体 >=0.5.11.9；4.3.4 要求 >=0.5.12.11（两者均由包内 `boot.json` dependenceInfo 确认）；4.2.x 重构了 AddonPlugin/模块系统 | 只能随底座整栈升级，不能单独跳 |
| Cheat Extended | Pre-release 快照 dev260719（digest 7aa8ab4c…） | 同 tag 资产现为 dev260903（digest f0bcbdaf…），最低本体 0.5.11.9 | **构建输入已漂移**，见第 1 节 |
| LongerCombat / Yanling | v1.0.1 | 无变化，资产仍标注 0.5.10.12 | 4.2.x 框架兼容性需真机复测（addonPlugin 声明 ^4.1.0，覆盖 4.2/4.3，但属"声明兼容"） |
| More Love | v0.1.7.0 | 无变化 | 不动 |
| DOLI | v0.2.3（CC BY-NC-SA 4.0） | 无变化；社区出现同类 AI 扩展"织境空间"（活跃，2026-08-22 v0.1.575） | 观察项 |
| AU 三模型 + AU Face | v0.9.3 / v0.4.2 / v0.1.1 / facemod | 资产 2026-05-28 后未变；AU 授权：README 明确禁止二传/倒卖/拆包、禁止未授权跨模型搬运（原文已核对） | 不动；公开分发 AU 的授权仍未闭环 |
| 枯木逢春 Deadwood-Reblooms | 未集成 | 仓库活跃（pushed 09-09），**GitHub Releases 为 0**（API 实证） | 继续观察，不是现成替代 |
| 其余固定 tag mod | CustomHair / Mae's / GuideToMe / NPC Avatars / NeoUI | 全部无变化 | 不动 |

ModLoader：汉化两个版本均随包发布 `v2.101.1`，无独立升级面。
上游 Lyra 构建系统最后提交 2026-05-18，无同步压力。

## 4. 社区与资源生态补充

本次新核验（来源：中文 Wiki 模组列表全文抓取，页面最后编辑 2026-09-06；
抓取存档见会话 agent-tools 文件；DoLModding Wiki；GitHub API）：

- **公开模组（CC-BY-NC-SA-4.0，JML 可加载）新候选**：猫咖出租屋
  （Maomaoi，2026-08-06 v1.1.8.2，活跃）、模拟人生 DolSims、Dom 罗宾
  （0.08-alpha-for-dol-5.10）、万物皆可种农场（随风飘逸 v0.20.1）、
  美甲拓展/特姿拓展（随风飘逸，特姿拓展服务于美化作者画特殊姿态）、
  更多农场升级、AngelHalos、时光项链/还俗等 MagicalAstrogy 系列。
  多数为小功能 mod，能否入包取决于与现有栈的冲突面，未验证。
- **私有模组区高价值候选**：泰拉瑞亚拓展（苯环＝More Love 作者，
  v0.2.12.1，明确适配 0.5.10.12 且依赖秋枫白桦框架——与本项目框架同源，
  是"框架 4.x 内容生态"的直接证据）；织境空间 WovenRealm（AI 剧情/生图，
  活跃，含料理/场景互动扩展，授权与 API 成本需单独评估）。
- **模型生态带日期评估**（DoLModding Wiki）：AU 与 Goose Female 为
  "活跃且接近完整"；Goose Masc 半活跃；Mikili 社区活跃但收录不全；
  Hikari/Susato/Kitmint 已弃坑或停更；**Rotten 为新出现模型**（活跃，
  尚不完整）；BEEESSS 靠社区补充接近完整；Mysterious（UCB）仅战斗。
  此表只代表该 wiki 维护者的评估，非全量统计。
- **工具侧**：北极星"美化模组生成器/衣服模组生成器"在
  `cphxj123/Dol-BJX-Mods` 仓库子目录（无 LICENSE，最后推送 2024-05，
  休眠）；DOL 烤饼机（omvjro/DOL-pancake，伪截图转 twee）；
  MCH 的 REMOTE_TEST 已确认为"打包+本地服务+人工刷新"，不是自动化测试。
  以上都只是候选，未验证能力。
- **贴吧 AU 资源**：总表 `tieba_data/AU_RESOURCE_MASTER.md` 本次不可读取
  （不判定删除）；7 月记录的网盘链接与群号仍以该表与记忆为准，
  使用前需重新验活。群内资源按"自行获取、旁加载"处理，授权不转移。
- **Steam 创意工坊**：两轮定向搜索均未发现 Degrees of Lewdity 的
  工坊条目（结果全为同名无关游戏/壁纸）。记录为"未发现证据"，
  不断言绝对不存在。
- **访问边界**：中文 Wiki 对 WebFetch 返回 403（tavily 通道可读，
  已留档）；登录后附件、群文件、失效网盘不绕过；加密 AU 面扩内层
  仍不做白盒。

## 5. 候选路线（细节见对照页，此处只记证据状态）

- **路线 A（守住已测栈）**：把 0808 状态变成可复现——钉 cheat_extended
  资产、明确分支构建的汉化 tag 策略、发 v4.1.14 版本。证据充分，
  改动面最小。
- **路线 B（升级 0.5.11.9）**：汉化 1.0.0a + maplebirch 4.2.x +
  cheat_extended dev260903 整栈联动。收益是汉化修复与新功能；
  代价是 4.2.x 重构 + 两个保留补丁重新验证 + AU face HTML 上下文
  重定位，验证成本最高。
- **路线 C（在合格底座上扩内容/美化）**：包括上述社区新候选与
  贴吧 AU 资源。依赖 A 或 B 先行；服装类必须先核对绘制目标模型。
  模型是否换出 AU 属用户主观偏好，已留待 grill-me。

## 6. 下一阶段最小验证步骤（供确认，本阶段未执行）

1. 复现验证（路线 A）：`python main.py prepare --tag v0.5.10.12-chs-1.0.8a`
   + warmup + build，观察 cheat_extended 拿到的是哪个 digest，确认钉资产
   方案（自建不可变镜像或改 download_url 指具体版本化资产）。
2. 路线 B 预检：分别解包 4.2.9 与现栈比对 `AddonPlugin` 处理差异；
   在 0.5.11.9 汉化 HTML 上重定位 AU face 四处上下文； LongerCombat/Yanling
   在 4.2.9 上真机冒烟。任一步失败即降级回 A。
3. 周检语义修复：`mod-update-check.yml` 的 Summary 区分"检查失败/报告缺失"
   与"无更新"；同步改写 `docs/MOD_UPDATE_MONITORING.md` 的 Issue 段落。
   不采用"有更新即红叉"。
4. 文档同步（按记录分层）：`docs/SAVE_COMPATIBILITY.md`、
   `docs/MOD_COMPATIBILITY_MATRIX.md`、`docs/AU_MODS_INTEGRATION.md`、
   `docs/TESTING_CAPABILITY_ASSESSMENT.md` 中的旧快照段落。

## 7. 覆盖与边界声明

本轮覆盖：项目全部活跃文档与配置、6 个兼容 surface 源码、全部直接依赖
上游、主要社区目录（中文 Wiki 全文、DoLModding、dolmods.net、GitHub 组织）、
贴吧资源的历史记录、4 个开发工具的作者仓库现状。
未覆盖（并明示）：私有群文件与未索引网盘的内部内容、已删除资料、
加密包内层、Steam 工坊（无证据）、候选 mod 的实际运行验证。
"重复扩搜不再改变主要选择"的收敛条件已达成。
