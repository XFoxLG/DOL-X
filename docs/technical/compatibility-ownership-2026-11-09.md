# 自研兼容模组的归属、可行性与迁移决策

核验日期：2026-11-09。对象：DOL-X 十一月正式中文候选，DoL `0.5.12.13-chs-1.0.1a`、MapleBirch `5.6.2`、AU 面部扩展 `1.2.16`。本记录说明兼容模组的执行时机、版本依据与迁移范围。

## 结论

**运行时修复归入独立兼容模组；资源与 APK 修复在既有构建阶段执行。AU 面部路径和桌宠图层已有独立模组对照。**

上一轮为完成统一候选，把修复集中放进已有构建补丁入口，配合版本锁、精确匹配和回归验证。这使候选可以复现和验收，但不是最终维护位置；把项目专属规则长期积累在 `lyra/build.py` 和 `lyra/candidate_compat.py` 中，也不符合本仓库优先使用独立兼容模组的策略。

推荐：**统一维护归属，按实际发生时机选择执行位置。** 用一个新的 DOL-X 兼容模组承接运行时适配；压缩包读取、资源修复及 APK 包装继续由现有构建流程负责；确实需要改第三方内部实现的少量补丁继续精确修补构建副本，等待作者修复或可靠的公开接口。不是另建构建系统，也不是恢复两条长期游戏维护线。

本记录主体保留 2026-11-09 的源码核验与原型结论。2026-11-12 已正式实现 `mods/dolx-compat/` 和 `source_dir` 构建输入，移除现代组合对 AU `svr.js` 的重复修补。新产物另做完整验收；此前八件候选保留作对照与回退，状态以当次验收报告为准。

## 1. 自研兼容模组确实存在过，但已退役

| 事实 | 核验证据 | 对本轮的意义 |
|---|---|---|
| `maplebirch-v3-layer-compat` 是 DOL-X 自研模组 | 7 月提交历史及 `8813e6b` 的 `boot.json`、`framework.js`、README | 适用 3.x 的既有实现可从历史提交核对 |
| 它解决的是 3.x 图层命名 | boot 声明 MapleBirch `>=3.1.0 <4.0.0`；源码通过 `char.use` 回补身体、脸部、服装路径 | 其身份和适用范围不能直接代表 5.6.2 兼容层 |
| 8 月已经删除实现与注入链 | `6f9a4b31bd1129db0868949be46333401e140728` 同时删除 `mods/maplebirch-v3-layer-compat/`、`lyra/local_mod.py` 与对应构建注入代码 | 当前候选没有一个正在运行、只需继续添代码的旧本地 mod |
| 回退源码在历史中 | 删除提交明确写“回滚依赖 vega-archive-0713 与提交历史，不再靠仓库内保留源码” | README 原来的“源码保留”需要明确为历史归档 |
| 内置 `Lyra` 是信息模组 | `lyra/lyra_mod.py` 的脚本列表为空，只生成 boot 与说明 | 不适合把 DOL-X 运行修复隐藏在 Lyra 名下 |

原模组：[固定历史源码](https://github.com/XFoxLG/DOL-X/tree/8813e6b/mods/maplebirch-v3-layer-compat)。退役原因：[删除提交](https://github.com/XFoxLG/DOL-X/commit/6f9a4b31bd1129db0868949be46333401e140728)。本仓库策略：[UPSTREAM_FRIENDLY_STRATEGY.md](../../UPSTREAM_FRIENDLY_STRATEGY.md)，尤其“项目专属策略优先放在 tools、配置或独立兼容 mod”“运行时兼容优先使用公开 hook/API”。

历史版本 `0713` 的恢复不应依赖本轮新实现；新实现使用新的名称，例如 `dolx-compat`，避免玩家误认为旧 3.x 补丁可以通用于所有框架。

## 2. AU 当前修复了什么

面部扩展原件在缺少旧 `faceStyleSrcFn` 的新框架下自带替代实现，因此不能把 4.x 的旧函数补丁无条件加回。实际问题在替代实现与整合环境的接缝：

1. **“可能有对应旧图”被当成“选中的图片包确实有文件”。** 面扩查询 `modImgLoaderHooker.checkImageExist`；旧图兼容钩子的推测式匹配会使它提前选中不存在的路径。当前修复按 BSA 当前生效素材表，再按实际基础图片清单选择路径。
2. **旧模型使用 `tear-N.png`，面扩请求 `tears-N.png`。** 修复只在当前图片包有相应文件时使用单数名称；眼睛附加层关闭或泪量为零时不发出无效图片请求。
3. **主角色和桌宠不是同一份图层集合。** 原件只调用 `maplebirch.char.use(layers)`；当前修复使用 `char.use(layers, "main", {pet:true})`，再在初始化时重建一次已提前捕获的桌宠定义。
4. **桌宠裁剪与 AU-M 图片残片是另外两项。** 新档 AU 桌宠 mask 从 25 改为 0；AU-M 0.4.2 的一张模型 PNG 清除第二帧 213 个孤立像素的 alpha。这两项没有因本轮独立面部模组验证而消失，也没有改写旧档已经保存的 mask 偏好。

2026-11-09 候选的构建修补见 [candidate_compat.py](../../lyra/candidate_compat.py)；2026-11-12 面部及桌宠运行适配已迁入 [dolx-compat](../../mods/dolx-compat/README.md)，登记、版本范围和退出条件见 [compatibility.py](../../lyra/compatibility.py)。原先四 ZIP、四 APK 的完整验收仍以[统一候选验收记录](november-unified-acceptance-2026-11-09.md)为准。

## 3. 独立 AU 兼容模组的实际对照

实验使用已验收候选作为相同底包，只将其内嵌 AU 面部扩展还原为归档原件，再追加一个独立 mod。没有修改交付 ZIP、APK、源码配置或玩家存档。

- 原件四条损坏空目录记录仅在读取副本时去除；十个实际文件逐一比较，内容全部与原件一致。
- 独立 mod 使用正常脚本阶段注册 AU 图层，经日志确认三个变体注册时主角色模型缓存均为空，随后第一次创建模型就使用修复后的图层。
- 只迁移 `au_face_actual_paths` 所承载的面部路径、可选图层与桌宠图层逻辑；其他候选修复、框架裁剪设置、AU-M 图片修复仍保留。
- 使用隔离 Chrome 浏览器数据；检查进入游戏、鞋袜、桌宠三次显示、脸型遍历及四组表情。

| 实验组合 | 脸型/仪态组合 | 表情组 | 桌宠三次可见 | 运行错误 | 图片错误 | 结果 |
|---|---:|---:|---|---:|---:|---|
| AU-F 原始面扩，不加独立兼容 mod | 18 | 4 | 是 | 0 | 7 | 复现缺图，失败对照成立 |
| AU-F 原始面扩 + 独立兼容 mod | 18 | 4 | 是 | 0 | 0 | 通过 |
| AU-M 原始面扩 + 独立兼容 mod | 6 | 4 | 是 | 0 | 0 | 通过 |
| AU-A 原始面扩 + 独立兼容 mod | 6 | 4 | 是 | 0 | 0 | 通过 |

这证明“保留 AU 面扩实际文件原样，由独立兼容模组处理这部分接缝”可行。它不等于完成整个兼容层的正式迁移验收。


## 4. 不能只把所有代码搬进一个游戏启动后的脚本

本轮按实际候选使用的 ModLoader `2.101.1` 固定提交 `17c16d91b6c10ea14ee19a4ddd49a3f76bd1655f` 核验，而非套用最新分支文档。

加载顺序为：读取包与 boot → 各 mod 的 `inject_early` → `afterModLoad` → `earlyload` → 合并正常脚本/Twee → 替换补丁 → preload → SugarCube 游戏脚本与初始化。

有三个会改变方案选择的事实：

**第一，mod 自身也能包含早期脚本和加载钩子。** `afterModLoad(bootJson, zip, modInfo)` 是加载器公开的修改模组入口。CustomHair 的 `main.js`、更多恋人的正常脚本/Twee，可以在执行前通过这个入口或 ReplacePatcher 修正；“独立 mod 一定太晚”不成立。但此时其他 mod 的 `inject_early` 已经执行，CE 的 `CERegist.js`、DOLI 主 bundle、旧图兼容的注册脚本不能用同一时机补救。

**第二，MapleBirch 5.6.2 的 `char.use` 不是旧版行为的完全替代。** 新实例在构造时合并已注册图层；对已经缓存的实例，`patchCachedLayers` 只添加缺少的层，不覆盖已有层的 `srcfn`。旧 mod 的 `:storyready` 接入时机不能照搬。本轮原型在首个主角色缓存生成前注册，实际验证了正确时机。

**第三，依赖声明和抛异常不等于阻止启动。** `DependenceChecker.checkFor` 记录不匹配但最终返回 true，正常 `check()` 的返回值也没有作为停止加载的条件；装载阶段仍按给定顺序执行。`afterModLoad` 内异常会被捕获并记入日志，随后继续其他回调。新模组需要版本与加载顺序校验，构建和验收仍须拒绝未应用、重复应用或接口失配的产物，不能仅凭 boot 依赖声明宣称自动安全。

对应源码：

- [ModLoader 加载过程](https://github.com/Lyoko-Jeremie/sugarcube-2-ModLoader/blob/17c16d91b6c10ea14ee19a4ddd49a3f76bd1655f/src/BeforeSC2/ModLoader.ts#L445)
- [afterModLoad 异常处理](https://github.com/Lyoko-Jeremie/sugarcube-2-ModLoader/blob/17c16d91b6c10ea14ee19a4ddd49a3f76bd1655f/src/BeforeSC2/ModLoadController.ts#L302)
- [依赖检查实现](https://github.com/Lyoko-Jeremie/sugarcube-2-ModLoader/blob/17c16d91b6c10ea14ee19a4ddd49a3f76bd1655f/src/BeforeSC2/DependenceChecker.ts#L42)
- [5.6.2 图层注册与缓存行为](https://github.com/MaplebirchLeaf/SCML-DOL-maplebirchFramework/blob/d9199cd26c9884339a13a1a62281164e45e9197b/src/modules/Character.ts#L349)
- [5.6.2 桌宠捕获逻辑](https://github.com/MaplebirchLeaf/SCML-DOL-maplebirchFramework/blob/d9199cd26c9884339a13a1a62281164e45e9197b/src/modules/CharacterAddon/Pet.ts#L319)

## 5. 每项修复的推荐归属

“归入兼容维护范围”与“全部改成运行时执行”是两件事。下面覆盖本轮候选及仍需维护的旧组合接缝。

| 修复 | 当前位置/触发点 | 推荐归属与顺序 | 判断依据 |
|---|---|---|---|
| AU 面部真实路径、`tear-N`、可选眼睛和泪层 | 改 AU `scripts/svr.js` 副本 | **第一批迁入独立 mod 的正常脚本** | 三种模型原件 + 独立 mod 已通过对照 |
| AU 桌宠图层捕获 | 同一 AU 副本补丁 | **与上一项一同迁入** | 使用公开 `char.use(...,{pet:true})`，在初始化时捕获一次；不能恢复旧的反复套宏方案 |
| AU 新档桌宠 mask 默认值 | 框架 `dist/inject_early.js` 副本 | 同属 AU 适配模块，但迁移须独立验证新档初始化接口与顺序 | 不得在每次读档时重写旧用户设置；本轮原型没有迁移此项 |
| AU 面扩四条坏空目录 | ZIP 读取之前 | **保留构建输入规范化** | 独立 mod 执行前，加载器已需成功读包；无需让游戏承担容器修复 |
| AU-M 一 PNG 的第二帧残片 | 图片包副本 | **保留无损资源修复** | 是已发布图片数据缺陷；运行时遮挡会扩大影响并掩盖原图问题 |
| 新 `.modpack` 容器转换 | Python 构建输入 | **保留通用构建支持** | 用于现有 ZIP 注入链读取第三方格式，不是游戏行为 |
| CustomHair 离线颜色初始化、移除示例域名请求 | 正常脚本 `main.js` | 第二批评估独立 mod 的执行前修补；当前精确副本补丁可继续使用 | 单纯启动后重新初始化无法撤销已发送请求；需要在原脚本执行前修改，不能全局拦截 fetch |
| 更多恋人可选依赖判断 | 正常脚本及 Twee | 第二批通过公开加载钩子/最终 passage 修改迁移 | 让可选依赖查询不产生“必需 mod 不存在”错误；保留原协作语义 |
| 更多恋人拖动事件修复 | 对应正常脚本内部处理器 | 与该 mod 的兼容模块统一登记，选执行前修补 | 继续覆盖原事件行为，不在全局事件层吞错 |
| DOLI 设置入口 | `overlay-replace.json` | 第二批迁入最终中文设置 passage 适配，调用原 `doli.renderOptionsTab()` | 不复制第二套设置页；上游 PR #4 已修复，应跟随包含修复的新发行退出补丁 |
| DOLI 旧图标路径 | `dist/DOLI.js` | 与上项共管；可保留精确源补丁或资源别名，待新发行退出 | 上游已接受同一修复；不能仅因 master 修复就假设当前 Release 已包含 |
| DOLI 回退计数与历史状态 | `dist/DOLI.js` 中 narrator 状态与异步生成路径 | **保留目标源码层的精确修补，优先上游修复** | `doli.combatNarrator` 确实可访问；不是闭包绝对不能改。但只包装换页回调不足以涵盖异步输出、重新生成和读档状态 |
| CE 可选框架查询 | 既含 `inject_early` 的 `CERegist.js`，也含正常脚本 | **暂保留精确副本补丁**，作为独立兼容模块的早期加载能力专项 | 不把 `getMod` 全局换成静默查询；晚期 mod 不能撤回启动阶段错误 |
| 旧图兼容只尝试真实存在素材 | `dolrename.js` 早期注册与内部闭包 | 暂保留精准修补，持续与作者 Plus 更新做同场景比较 | 不能叠加两套不一致的图片回退优先级，也不能用 Plus V3 版本号代替有效性证明 |
| 狼图标同字节别名 | 基础资源目录 | 保留现有资源别名；未来可随兼容资源包携带，但必须验载入时机与优先级 | 原图复制即可，不需要再造一套全局图片改写器 |
| APK 身份、签名、外部 modList 清单 | 克隆构建缓存后的 APK 包装 | **仍属构建器** | 运行中的 JS mod 不能完成安装包身份与签名修复 |
| 4.1.14 旧 AU 选脸/旧档修复、旧桌宠重挂 | 旧框架的已发布回退组合 | 保持其现有适用范围；本轮新 mod 不自动接管 | 旧组合是存量支持义务；不能把 4.x 的接口和历史错误推广为所有 5.x 都有 |

当前 `doli_settings_entry` 登记同时描述设置入口与历史修复。正式整理时宜分成两个实际补丁条目，因为它们的上游修复与退出条件不同；继续使用现有登记机制即可。

## 6. 上游、Fork 和社区能借鉴什么

### MapleBirch 与加载器

5.6.2 自身已有角色层注册、面向桌宠的层注册及换页同步。不应把旧 4.x 桌宠补丁、旧 `faceStyleSrcFn` 或旧 v3 全服装命名表一并搬回。以固定版本公开接口承接当前组合，后续升级重新核对实际代码。

11-09 重新获取了 MapleBirch 的三个公开 Fork：

| Fork | 本轮查到的事实 | 用途 |
|---|---|---|
| [JohnLiao501](https://github.com/JohnLiao501/SCML-DOL-maplebirchFramework) | 相对 5.6.2 固定提交 ahead=0、behind=153；此前与上游 4.3.5 精确比较为 identical；无 Release 附件的既有核验仍保留 | 历史源码、旧标签恢复与行为对照，不是本轮 5.6.2 的增强替代 |
| [Nixdorfer](https://github.com/Nixdorfer/maplebirch-framework) | main 为 `46e4aa18`，提交说明 `update-v3.1.14`；GitHub 与当前 5.6.2 比较返回无共同祖先 | 旧框架资料；不把无法直接 compare 解释成没有代码 |
| [Muromi-Rikka](https://github.com/Muromi-Rikka/SCML-DOL-maplebirchFramework) | main 为 `c32bdbbe`，提交说明 `add number funcion`；与当前 5.6.2 无共同祖先 | 具体旧接口改动的参考，未找到能据此取代当前组合的证据 |

同时阅读了 MapleBirch 的 ModLoader Fork 与候选实际 ModLoader 2.101.1。最终时序与错误处理结论采用后者，避免把 Fork 最新实现当成已内置能力。

### DOLI：已有上游修复，也有尚未解决的缺陷

- [PR #4](https://github.com/ArsNativa/Degrees-of-Lewdity-Intelligence/pull/4) 已于 2026-09-20 合并，明确修复图标和枫桦环境下的选项按钮。
- [最新正式 Release](https://github.com/ArsNativa/Degrees-of-Lewdity-Intelligence/releases/tag/v0.2.3) 本轮 API 仍返回 `v0.2.3`；tag 固定提交是 `00a6fc037cdf38c549c9fdc487bcc1dcd85fab8f`，实际归档包的 boot 版本字段仍为 `0.2.2`。来源 tag、包内容与运行时版本字段需要分别核对，不能把合并后的 master 当作该附件的内容。
- [回退计数 issue #2](https://github.com/ArsNativa/Degrees-of-Lewdity-Intelligence/issues/2) 本轮仍为 open。
- [JohnLiao501/DOLI](https://github.com/JohnLiao501/Degrees-of-Lewdity-Intelligence) 的 master 与该 v0.2.3 比较 identical，ahead=0、behind=0。
- [sch-chun/DOLI](https://github.com/sch-chun/Degrees-of-Lewdity-Intelligence) 相对 v0.2.3 多三个提交，涉及开发脚本、忽略文件与玩家状态信息采集。比较文件清单没有改动 `src/combat-narrator/index.ts`，没有可直接替代本轮 narrator 历史修复的证据。

固定源码 `src/init.ts` 明确暴露 `window.doli.combatNarrator` 与 `renderOptionsTab()`。因此对“外部模组能不能接入”应分别判断：设置 UI 有清晰入口；历史修复依赖内部状态的一致保存与恢复，仅因为 JS 能读字段就改用全面包装，不会更容易维护。

### GenesisCompat：适合借鉴组织方式与来源追踪

[GenesisCompat 架构](https://github.com/anlimi555s/DoL-Genesis-LTS/blob/fc0fce524d0828cebfb343a83fe263612867c549/compat/genesis-compat/ARCHITECTURE.md) 与源码体现了有价值的方式：兼容层单独成 mod；旧包主动声明；路径规则从官方历史重命名提取；区分普通图片表和 BSA 素材表；将旧数据迁移和路径修复分开。

实际 `img-translate.js` 通过 `afterModLoad` 改普通 mod 图片表，并在 BSA 加载后处理其表。这是“独立 mod 可以在加载阶段适配其他包”的直接例证。

它也有与 DOL-X 不同的目标：文档提出 0.5.8 沙盒、264 层整体回退和旧引擎派生维护，并明确旧人模与新衣服混用不保证。当前检查到的 boot 直接列出的入口是 `retro-path-translate.js`、`img-translate.js`、`migrate.js`；本轮没有把文档列出的整套沙盒能力都当成已在 DOL-X 验证的功能。DOL-X 保持正式中文、现代主线及现有构建链，借鉴其中必要的接缝处理，不承担另一套游戏引擎维护。

### Legacy Plus、遮罩补丁、社区派生项目

[chris81605/Legacy-Art-Mods-Compat](https://github.com/chris81605/Legacy-Art-Mods-Compat/blob/c3bf6c891b152549425a5a8dfca5310e7b7be96b/dolrename.js) 的源码和作者 [Discord 原帖](https://discord.com/channels/1103864219620884560/1232768523990728785/1544732448502583411) 相互印证：Plus V3 是原 CE 作者隨風飄逸维护；原作另为鎖鏈蝴蝶。Plus 的 before-native、原生现代路径、after-native、旧路径候选有不同优先级，不修改 BSA `imgListRef`；这与 Genesis 的装载期重写不是同一个机制。本轮其公开 Fork 列表为空。

借鉴点是明确规则所有者和优先级。不能把两者的路径规则全部叠加后宣称覆盖更广。上一轮同场景对照未证明 Plus V3 / Renderer.Mask.Compat 为当前组合带来所需收益，因此这一轮不会仅为“合入更多兼容代码”而纳入。

[DOL-Compatibility-Mods](https://github.com/chris81605/DOL-Compatibility-Mods) 将 HeadMask、服装 trait、Renderer mask 问题分别处理，README 也区分游戏版本和具体症状。这支持针对可达故障使用小模块，不支持预先装入所有补丁。

[DoL-NPC-Avatars-Compat](https://github.com/102326/DoL-NPC-Avatars-Compat) 的既有归档说明提供了另一种有效实践：派生修复声明范围、保留图片原件、提供差异和验证记录。对确实需要修改第三方内部代码的修复，明确标注派生副本也比伪称原件更诚实。

### Discord、贴吧与中文材料

复核了 11-07 至 11-09 已抓取的社区档案，包括 AU 作者 1.2.16 发布说明、Plus V3 原作者帖子及附件消息、贴吧资源帖。AU 面部扩展、AU 三种模型图片包及已失效的旧头发扩展始终作为不同对象，不因名字相近混为同一个版本。

- [AU 1.2.16 作者消息](https://discord.com/channels/1103864219620884560/1368992933243654164/1566065930646069270)：表情、半闭眼和泪痕等修订；实际兼容仍以归档附件和运行结果为准。
- [Plus V3 附件消息](https://discord.com/channels/1103864219620884560/1232768523990728785/1544732529066508339)：与 GitHub 固定提交分别留档，不能假设同名必然同字节。
- [旧图适配贴吧资源帖](https://tieba.baidu.com/p/10695251870)、[美化工具说明帖](https://tieba.baidu.com/p/11147977575)、[更长战斗资源帖](https://tieba.baidu.com/p/11080014608)、[资源整理帖](https://tieba.baidu.com/p/11053516690)：用于核对来源和用户反馈；不把其他画风的问题自动推广到 AU。
- 中文优先顺序保持：正式中文基础、原生中文/有维护的对应汉化、再对照英文原作更新。兼容 mod 的玩家说明使用正式中文，并保留作者名、版本与可定位的技术标识。


## 7. 采用方案与具体实施次序

| 方案 | 维护与技术代价 | 本轮判断 |
|---|---|---|
| 所有修复继续放构建器里 | 现有交付易复现，但 DOL-X 专属代码持续侵入 Lyra 构建核心；原附件和派生包更难分辨 | 保留必要的输入/内部补丁，AU 运行适配迁出 |
| 所有修复放一个 `:storyready` 脚本 | 早期代码已经执行；新框架缓存未必更新；无法处理 ZIP 与 APK | 不采用 |
| DOL-X 兼容模组 + 现有构建补丁，统一登记 | 运行适配使用公开接口；源/资源修复在真实边界执行；版本与验收归属清楚 | **采用此方向；AU 先迁，其他项目逐项迁** |
| 整体切换 Genesis 或长期维护游戏/框架大 Fork | 涉及旧引擎、重命名策略、更多用户存量和内容合并 | 本轮没有这种收益或必要性 |

具体次序：

1. **把本轮 AU 原型收敛为正式 `dolx-compat` 源码模块。** 限定已确认的框架＋面扩组合，脚本在 AU 正常脚本之后、第一次角色模型创建之前执行；记录实际应用结果。恢复面扩的十个原始文件，只保留四空目录的构建规范化。第一批只承接已经证明的面部/桌宠图层修复。
2. **在同一配置与注入路径接入本地兼容 ZIP。** 复用 `--config-dir`、下载缓存、`ModInjector`、现有补丁登记与产物审计。为本地 mod 增加必要的打包/注入步骤即可；不复活旧 profiles，不另写一套配置系统或自动补丁引擎。
3. **清除同一修复的第二个执行者。** AU 独立 mod 生效后，构建器不再修改同一 `svr.js`；其余补丁仍有各自明确归属。没有必要一次性迁完十几项。
4. **再处理 DOLI 设置、CustomHair、更多恋人。** 优先官方发布修复和公开生命周期；需要执行前替换时明确标记为“装载期源码修补”，不包装成无侵入 API。CE 早期修复、DOLI 历史和旧图闭包保持现有精准补丁直到新方案有相同证据。
5. **按真实退出条件跟随上游。** 新附件到来先比实际内容，确认作者已修复后撤下对应项目。版本号更新、作者说兼容、仓库 master 合并、Fork 有新提交，都不等于现用发行已经修好。

这些步骤继续当前统一 5.6.2 候选路线；4.1.14 维持回退组合。公开发布及默认切换仍是完成验收后的独立步骤。

## 8. 正式归并的验收条件

- 四变体版本和实际模组列表正确；基础版不要求存在 AU，AU 规则仅在所支持的实际组合下应用。
- 原面扩文件逐项保持原样；独立 mod 确实加载并在预期阶段应用；既不能只靠“控制台没有红字”，也不能同时保留两份相同修复。
- 同场景比较主角色和桌宠的脸型、仪态、半闭眼、创伤表情、雀斑、腮红、泪痕、鞋袜与发色；检查请求路径、可见像素、截图和完整错误日志。
- 新档初始化及旧档保存设置分别验证；载入已发布旧档不能因默认值修复而覆盖用户设置。
- 沿用原 1014 存档副本、原版 CE 操作、DOLI 离线设置和真实历史回退流程，再做 MuMu 触摸与重启读档。若改变共享构建入口，补测原 4.x 组合。
- 重新构建的四 ZIP/APK 核对内容、版本、签名与完整性，明确新实验和原八件候选之间的区别。
- 非支持组合的校验必须能让构建/验收失败并定位具体模组和版本；不得通过删错误、放宽断言或给缺图返回空白图片获得通过。

## 9. 资料与覆盖范围

本次依据包括对应提交的框架、加载器、Genesis、Plus 与 DOLI 文档和源码，项目历史、附件版本与三个模型的对照结果。

集中说明限制：本轮不是全部 Discord 私密频道、已删除附件、所有贴吧楼层或所有代码托管平台的穷举；没有将搜索零结果当作资源不存在，也没有确认官方创意工坊入口。两个老框架 Fork 与现主线没有共同祖先，不能编造 ahead/behind 或全代码兼容结论。社区证据复用了最近几日的归档，本轮实时更新重点是相关 GitHub 源码与状态。独立 AU 原型仅在 Chrome 验证，尚未作为新的四 ZIP/APK 重做完整迁移验收；原候选的 MuMu 验收不能自动转移给新原型。无真实安卓设备、HarmonyOS、个人长期档及 DOLI 在线 AI 服务的新增证明。原型初次运行中自建 HTTP 服务缺少 `modList.json`、提前关闭服务以及一次浏览器上下文关闭异常属于实验工具问题；已恢复既有服务约定、保留失败记录后重新执行，最终统计来自修正后的完整对照，

本文中的独立模组建议由源码及隔离实测支持；“全部归并完成”和“可公开发布”不在本轮已完成事项内。
