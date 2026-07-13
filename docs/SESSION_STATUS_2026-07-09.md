# 会话状态 2026-07-09

承接 next-4x / vega 双线并行阶段。本会话把 B 线（vega 稳定分支）的兼容 mod 从源码方案真正落地成一个可注入构建的正式 mod，并接线进构建流程，出了带兼容 mod 的 3.x 测试包交用户真机测试。

## 一句话现状

`feat/maplebirch-v3-layer-compat` 分支上，自研兼容 mod `maplebirch-v3-layer-compat` 已完成并接线进 `lyra/build.py` 的注入流程，本地成功构建出两个带该 mod 的 3.x ZIP 测试包，等用户真机验证 NPC 侧边栏 `nnpc_*` / `blush` 报错是否消失。

> **⚠️ 2026-07-09 晚间更新（第一版实测失败 → 已定位并修复，见文末「boot.json 校验坑」章节）**：第一版 au-f-0709 包用户实测，NPC 贴图/模型错误依旧存在。经拆包+对比游戏引擎源码坐实：兼容 mod **进了包但被 ModLoader 的 `validateBootJson` 静默拒绝**，从未加载。根因是 boot.json 缺了 `styleFileList`/`tweeFileList`/`imgFileList` 等必需空数组字段。已补齐并重建包，本地模拟引擎校验门通过，待用户重测。

## 本会话核心成果

### 1. ✅ 兼容 mod 落地为正式 mod

仓库内新增 `mods/maplebirch-v3-layer-compat/`（`boot.json` + `framework.js` + `README.md`）。

- **作用**：把 maplebirch v4.1.6–v4.1.12 修好的「连字符图层命名」逻辑 back-port 到 v3.1.14 上，修复 AU-F 包侧边栏 `nnpc_head`/`nnpc_body`/`nnpc_breasts`/`nnpc_leftarm`/`nnpc_rightarm` 缺层 + PC `blush` 脸红层 404。
- **实现方式**：不改框架源码，走 maplebirch 公开 API `char.use()` 深度合并，只覆盖每个受影响图层的 `srcfn` 叶子，其余字段（showfn/zfn/filters 等）保持框架自身逻辑。
- **加载时机**：监听 `:storyready`，确保在框架自己的 `NPCSidebar.init()` 注册基础图层之后合并，让覆盖最后落地生效。
- **版本闸门**：`boot.json` 声明依赖 `maplebirch >=3.1.0 <4.0.0`，4.x 线会被 ModLoader 依赖检查自动跳过，无需在构建期按框架版本分流。

### 2. ✅ 接线进构建流程

`lyra/build.py`：

- 新增 import `from .local_mod import build_local_mod`
- `PackageBuilder` 基类新增 `_inject_local_mods()`：以 `(feature_id, mod目录名)` 表驱动，命中 feature 就现场打包 `.mod.zip` 并注入 HTML。当前注册 `("cheat_extended_maplebirch", "maplebirch-v3-layer-compat")`——借用 maplebirch 框架必选位触发，不新增 feature bit。
- ZIP 与 APK 两个 builder 的 `build()` 都在 `_inject_lyra_mod()` 之前调用 `_inject_local_mods()`。

验证：`python -c "import lyra.build"` 通过；`python main.py matrix` 正常输出 4 码；ReadLints 无错。

### 3. ✅ 本地出包成功

warmup 完整跑通（base.zip = 游戏 0.5.8.10 + 汉化 3.1.3a，全部 mod 下载到缓存）。构建两个 ZIP：

- `output/DoL-0.5.8.10-XFox-3.1.3a-au-f-0709.zip`（105.2 MB）← 重点测，复现 AU-F 报错场景（UCB + AU 女性模型 + 完整 3.x 栈）
- `output/DoL-0.5.8.10-XFox-3.1.3a-base-0709.zip`（58.6 MB）← 对照组，无 AU 模型

两个包的构建日志都确认兼容 mod 被打包并注入（AU-F 包内为第 36 个 mod）。

## 待用户真机验证

装 `au-f-0709.zip` 进游戏，重点看：

1. NPC 侧边栏立绘是否完整（`nnpc_head`/`nnpc_body`/`nnpc_breasts`/`nnpc_leftarm`/`nnpc_rightarm` 不再缺层）
2. 加载日志里 `Failed to load image img/body/base*.png for layer nnpc_*` 与 `img/face/default/default/blush*.png for layer blush` 报错是否消失
3. 开启「NPC 侧边栏图像显示」+「PC 模型模式」两个开关后，侧边栏是否还有贴图重叠/异常

## 分线现状（承接双线并行决策）

### B 线 = vega 稳定分支（本会话主攻）
- 保持 maplebirch v3.1.14 + maplebirchEx v1.2.4 + cheat v1.17/1.18 + DOLI v0.2.3
- 通过兼容 mod 修 v3 的图层命名 bug，保住只兼容 3.x 的 DOLI 与 maplebirchEx
- 当前在 `feat/maplebirch-v3-layer-compat` 分支，验证通过后合入 vega

### A 线 = next-4x 分支（备用/并行）
- maplebirch 升 v4.1.13 + cheat V1.19 + 放弃 maplebirchEx，理论根治图层问题
- 已出包 `output/next4x-run28884545699/`（run 2884545699），4 个 APK 待实测
- 关键未决：DOLI 闸门（DOLI bot.json 要求 maplebirch `^3.1.0`，可能拒 4.x）
- next-4x 的 WIP 改动（`.gitignore`/`config/mods.lock.json`/两份诊断文档）已 `git stash`，切分支时保留

## 根因回顾（已坐实）

AU-F 包侧边栏缺层 + blush 报错 = maplebirch v3.14 的 NPC 侧边栏渲染代码在游戏 0.5.9.8+ 上有「连字符命名」bug：v3 用无连字符旧命名（`basehead.png`/`blush1.png`/`breasts0.png`/`leftarmidle-classic.png`），游戏 0.5.9.8+ 和 AU 模型包都用带连字符新命名（`base-head.png`/`blush-1.png`/`breasts-0.png`/`left-arm-idle-classic.png`）。与 AU 模型、AU 面部扩展、NeoUI、imgpack 全无关。上游 Lyra 没这问题是因为它栈里根本没装 maplebirch。详见 `docs/AU_SIDEBAR_ROOTCAUSE_2026-07-07.md`。

## 完整旧→新命名映射（兼容 mod 依据）

- nnpc_body: `basenoarms-classic.png` → `base-classic.png`
- nnpc_head: `basehead.png` → `base-head.png`
- nnpc_breasts: `breasts{size}{suffix}` → `img/body/breasts/{type}-{size}.png`（type = cleavage && size>=3 ? 'clothed' : 'breasts'）
- nnpc_leftarm: `leftarmidle-classic.png` → `left-arm-idle-classic.png`
- nnpc_rightarm: `rightarmidle-classic.png` → `right-arm-idle-classic.png`
- blush（在 Character.ts）: `blush{N}` → `blush-{N}`；makeup_blusher 层两版都是 'blusher' 不变

## 环境约束（不变）

- **本地能跑**: pytest、git、`python main.py matrix/warmup/build zip`、curl、gh
- **本地不能**: APK 签名（需 keystore）、imagepack 解压（缺 unrar）；ZIP 构建本地可完整跑
- **Windows/PowerShell**: 不支持 heredoc/tail/head；`Get-ChildItem` 对含连字符路径的通配偶发空返回，用 `cmd /c dir /b` 或显式文件名兜底

## Git 状态

- **分支**: `feat/maplebirch-v3-layer-compat`
- **本会话改动**: `lyra/build.py`（接线 local mod）；`mods/maplebirch-v3-layer-compat/` 三文件此前已在分支上
- **next-4x WIP**: 已 stash 保留（`.gitignore` + `config/mods.lock.json` + 两份诊断文档）
- **未提交**: `lyra/build.py` 接线改动待提交

## 下一步

1. 用户真机测 `au-f-0709.zip`，回报侧边栏/报错情况
2. 若验证通过 → 提交 `lyra/build.py` 接线改动 → 合入 vega → 触发 CI 出正式包
3. 若仍有残留 → 对照 base 包报错，定位是兼容 mod 覆盖未生效还是别的图层
4. A 线 next-4x 的 DOLI 闸门实测并行推进

---

# 【2026-07-09 晚间】boot.json 校验坑 —— 第一版实测失败的完整根因与修复

## 用户实测反馈

第一版 `au-f-0709.zip` 装机后：DOLI 右下角悬浮窗好了（这是 NeoUI/其他改动的功劳），但**曾经的 NPC 贴图/模型错误回来了**（侧边栏立绘异常）。用户点明 DoL-XFox（另一独立项目）的包不会这样。

## 拆包 + 引擎源码双重坐实的根因

**兼容 mod 进了包，但被 ModLoader 静默拒绝，从未加载。**

证据链（全部可复现，非推测）：

1. **进包确认**：从 au-f-0709.zip 的 HTML 里解出 `window.modDataValueZipList`（37 个 base64 mod），我的 mod 在**第 35 位**（DOLI=34 之后、Lyra=36 之前），boot.json 完整。
2. **未加载确认**：实测加载日志里 `ModZipReader init()` 只有 **36 行**，从 ModLoaderGui 到 DOLI 再直接跳到 Lyra，**唯独跳过第 35 位我的 mod**。mod 管理器列表里也没有它。37 进数组、36 被 init，差的就是它。
3. **拒绝原因**：日志里那行 `02:48:07.291 validateBootJson(bootJ) failed. [true,true,true,true,false,...,false,...,false,...]` 时间戳正好卡在 DOLI(07.264) 与 Lyra(07.293) 之间——**就是我的 mod 被拒的记录**（我最初误判成 DOLI 的，后用引擎源码纠正）。
4. **逐位对照引擎源码**：从游戏 HTML 里挖出 `ModZipReader.validateBootJson` 的布尔门 `c` 表达式，它硬性要求 6 项：
   - `name` 非空字符串
   - `version` 非空字符串
   - `styleFileList` 是字符串数组（**必须显式存在**）
   - `scriptFileList` 是字符串数组
   - `tweeFileList` 是字符串数组（**必须显式存在**）
   - `imgFileList` 是字符串数组（**必须显式存在**）

   失败数组第 5/9/11 位的 false 正好对应 `styleFileList`/`tweeFileList`/`imgFileList` 我全省略了。

**为什么第一版会犯**：写 boot.json 时图简洁，只保留实际用到的 `scriptFileList`，省掉了那三个"反正是空的"列表。但 ModLoader 的校验门要求它们**即使为空也必须显式声明为数组**，否则 `isArray(undefined)===false`，整个 mod 被判无效、静默跳过。

**对照旁证**：同样结构简单的 `GuideToMe` 能正常加载，因为它老实写全了 `styleFileList`/`tweeFileList`/`imgFileList` 空数组。

## 修复

`mods/maplebirch-v3-layer-compat/boot.json` 补齐 `styleFileList: []`、`tweeFileList: []`、`imgFileList: []`、`imgFileReplaceList: []`。重建 au-f-0709.zip，从新包里解出 boot.json 用引擎的 6 项校验门逐位模拟 → **全部 PASS**，ModLoader 这次会接受并 init。

## 教训（写进流程，避免复发）

1. **本地"验证通过"的盲区**：第一版我只验证了 mod "进包 + 能打包 + import 无错"，但**没验证它能通过 ModLoader 运行时的 `validateBootJson`**。这是真实的验证盲区——本地不跑浏览器就发现不了。
2. **补救手段已建立**：现在可以在本地**静态模拟引擎校验门**（从 HTML 挖 `validateBootJson` 的 `c` 表达式，用 Python 逐字段核对进包的 boot.json）。这比只看"构建日志说注入成功"强得多，应作为本地 mod 的标准验收步骤。
3. **local_mod.py 可加护栏（待办）**：`lyra/local_mod.py` 的 `build_local_mod` 目前只校验"声明的文件存在"，不校验 boot.json 是否满足 ModLoader 的必需字段门。可加一个 `styleFileList/scriptFileList/tweeFileList/imgFileList` 必存在检查，把这个坑挡在构建期而非真机。

## 待用户重测（第二版 au-f-0709.zip，boot.json 已修）

重点仍是那三条：侧边栏 nnpc_* 立绘完整？nnpc_/blush 的 `Failed to load image` 报错消失？两开关全开无贴图重叠？

---

# 用户两个遗留问题的回答（待展开）

## Q1: 改脸 eyes.png 报错来源（`img/face/kiss改脸/大眼鼠鼠/eyes.png` 等）

这批 `Failed to load image img/face/XX改脸/YY/eyes.png for layer eyes` 与 nnpc_/blush **不是同一个根因**。它来自"改脸"资源（自定义脸型 mod 的 eyes 图层），属于另一条线索，本会话未深入。待排查：是改脸资源包本身缺 eyes.png，还是命名/路径层级问题。

## Q2: maplebirchEx 能否支持高版本框架 4.x

这是 A 线放弃 maplebirchEx 的核心原因。maplebirchEx v1.2.4 **只有 3.x 构建**，其 dist/framework.js 依赖 v3 的 API 语义（char.use 的 merge 覆盖语义等，v4 已改成数组 push）。要让它上 4.x，需要 maplebirchEx 作者出 4.x 兼容版，或我方 fork 改写其 API 调用——成本高、维护重。本会话未展开，是后续要专门调研的课题（对应用户"能不能让框架扩展在高版本框架上运行"的提问）。

---

# 【2026-07-09 深夜】第二版实测通过 + maplebirchEx 4.x 调研定论 + 兼容 mod 规范化

## 第二版 au-f-0709 实测：兼容 mod 生效，主问题已修

用户装第二版（boot.json 修复后）实测，拆日志坐实：
- 37 个 mod 全部 init，`maplebirch-v3-layer-compat` 在列，`validateBootJson failed` = 0
- 旧的 `Failed to load image ... for layer nnpc_*/blush` 报错两个日志里**全部归零**
- **用户明确纠正**：稳定包（3.x + 兼容 mod）的**贴图/模型是好的**，兼容 mod 确实修复了 NPC 侧边栏。**只剩"切换改脸"时的游戏内报错**。

## 改脸 eyes.png 报错（与兼容 mod 无关，AU 资源自身问题，待单独修）

游戏脸部路径模板是两级 `img/face/${facestyle}/${facevariant}/eyes.png`。失败分两种：
1. facevariant 为空 → 路径塌成一级（`img/face/kiss改脸/lashes.png` 找不到，实际在 `kiss改脸/大眼鼠鼠/` 下）
2. AU 模型给自定义改脸只打包了**拆分眼图层**（iris/sclera/lashes/eyelids），**没有合并的 eyes.png**，游戏却仍按老逻辑请求合并 eyes.png
这是 AU 改脸包的 variant/图层系统问题，需补 AU 缺的 eyes.png 或改 variant 逻辑，独立任务。

## maplebirchEx 能否上 4.x：GitHub 一手源码调研定论（curl 走系统代理 127.0.0.1:7890）

**结论：不能简单升级，且作者已用新项目取代它。**
- 框架本体活跃更新到 **v4.1.13**（2026-07-01，作者 MaplebirchLeaf/枫桦叶）。
- maplebirchEx 停在 **v1.2.4（2026-03-11）**，package.json 硬绑 `maplebirch ^3.1.0`，源码全是 v3 语义调用（`maplebirch.use('ExMod')`、`maplebirch.combat` 等）。
- 框架 v4.0.2 是破坏性大版本：删 `:onLoadSave`、废战斗反应/射精/异装对话模块、改工具函数写法、类型包改名 `@scml-maplebirch/types`。
- 作者另起 **Deadwood-Reblooms（枯木逢春）**（基于框架 4.x，`@scml-maplebirch/types ^4.1.8`），重构更多恋人/NPC头像等——这是 maplebirchEx 在 4.x 的继任者，但**未定稿（1.0.0 之前，无 release）**。
- 对策略含义：**B 线 3.x + 兼容 mod 是当下最稳、不依赖作者后续更新**；A 线 4.x 等 Deadwood-Reblooms 出正式版再评估，不急。
- 对作者的判断（用户问）：不是不负责——框架本体一个月连发 8 个修复版、配类型包/云存档，是认真做开源框架；破坏性更新在跟着游戏本体改版的 mod 框架里是常态。真正风险是"扩展与框架更新节奏错位"的真空期。

## Wiki 模组工具页（curl 本机 SSL 被挡，Tavily 抓取通道成功）

DoL 中文 Wiki 收录的模组工具（对做兼容 mod 有用的）：
- **DoLModRspackExampleTS（rikka）**：模组打包工具，**无需手写 boot.json**——正好规避本次踩的空数组坑，做规范 mod 的首选脚手架。
- **MCH 模组编写助手（Number_Sir）**：社区标准 mod 制作+测试工具。
- 其余：JML(ModLoader)、美化/衣服模组生成器、DOL烤饼机、rust-mod-dev、Commit2Mod、DOL Mod Protection Tools（枫桦叶）。
- 注意：Wiki 秋枫白桦框架词条停在 v3.2.3（落后 GitHub 的 v4.1.13），以 GitHub 为准。

## 兼容 mod 规范化（用户选"做1"，本次完成）

- README 补上第 5、6 条制作经验：**boot.json validateBootJson 校验坑**（缺 styleFileList/tweeFileList/imgFileList 空数组 → mod 被静默拒绝）+ **本地模拟引擎校验门的方法**。
- `lyra/local_mod.py` 新增 `_validate_boot_json()` 守卫：打包前模拟 ModLoader 的 6 项必需字段门，缺字段直接构建期报错，把这个坑挡在真机之前。正负用例已测（合规放行、缺字段拦下）。
- 三文件（boot.json/framework.js/README）已达发布质量，本地校验门 PASS、打包干净（3 文件无重复）。

## 待用户决策：发布形式

兼容 mod 已规范化。下一步二选一（等用户定）：
1. **维持构建期注入**（现状：build 时自动打包注入 DOL-X 包，够用）
2. **额外发独立 GitHub Release tag**（打包成 standalone .mod.zip 供旁加载/分享，需 commit+push）

## 本会话未提交改动
- `mods/maplebirch-v3-layer-compat/`（boot.json 补空数组 + README 补经验）
- `lyra/build.py`（接线 local mod，之前）
- `lyra/local_mod.py`（新增 validateBootJson 守卫）
- 等用户确认发布形式后统一提交合入 vega。

---

# 【2026-07-12】兼容 mod 从"身体层"扩到"全侧边栏衣服层" + 已推 vega + CI 出包待实测

## 一句话现状

上一版兼容 mod 只修了 NPC 侧边栏的**身体层**（头/身/胸/手臂）和脸红，用户实测仍报"NPC 模型异常、像没穿衣服"。本轮查明：**衣服层**从没被修，而衣服层才是侧边栏占比最大的部分。已把 v4.1.12 的全部衣服层 `srcfn` 路径逻辑 back-port 进兼容 mod，提交推送到 vega，CI 构建成功（run `29195346344`，3m25s），4 个包已下载，等用户真机验证 au-f 包的 NPC 衣服层是否恢复正常。

## 本轮做了什么（先查证再动手）

对比 maplebirch v3.1.14 与 v4.1.12 的侧边栏图层源码（探针目录 `mb_src_probe/`，本地临时不进仓库），逐键坐实：

1. **v3 和 v4 的衣服图层键名完全一致**（v4 只多兽耳/尾巴/精液等变身层，非衣服）→ 覆盖键名安全，不会错配。
2. **命名 bug 只在 `srcfn`（请求哪个路径）里**；showfn/zfn 在 v3 本来就对。→ 只覆盖 `srcfn` 一个字段，其余保留框架 v3 逻辑，避开 v3/v4 的 ZIndices 键差异。
3. **三处故意不改，均有依据**：
   - **脸部叶子层**（eyes/iris/sclera/lashes/eyelids/brows/mouth/ears/freckles）：v3 与 v4 构造的路径**逐字节相同**，无命名 bug。→ 反证 `eyes.png` 改脸报错是 AU 改脸 mod 自身素材问题，不在本修复范围。
   - **nnpc_penis**：v3 源码开头 `if (!!nnpc.name) return ''`，对有名字的侧边栏 NPC 根本不渲染；且 v4 读的数据模型（`nnpc.balls` + 完整 penis 描述符）v3 的 NPCSidebar 从不生成，无法用 char.use() 忠实重建。→ 硬移植只会把一个错路径换成另一个错路径，留空。
   - **sidepart 包装层**（upper/lower/legs/feet/hands）：返回预存的自定义立绘 `.img`，不构造身体路径，无 bug。

## 实现细节

`mods/maplebirch-v3-layer-compat/framework.js` 从"身体层+blush"扩写到全覆盖（+440 行，26789 字节）：

- 移植 v4 的 `normaliseFileName()`（clothes 文件夹 `over_upper`→`over-upper`）与全部连字符后缀（`_alt/_down/_acc/_rolled`→`-alt/-down/-acc/-rolled`）。
- 覆盖约 90 个 `nnpc_*` 衣服图层的 `srcfn`（upper/over_upper/under_upper/lower/over_lower/under_lower/legs/feet/neck/head/over_head/handheld 全家族 + arm/breasts/back/hand 等各类构造器）。
- 仍走公开 API `maplebirch.char.use()` 深合并、`:storyready` 时机应用，不改框架源码。
- 头部注释新增「DELIBERATELY NOT PORTED」段，把上述三处不改的依据写死在代码里。

## 验证

- JS 语法检查（`node --check`）通过；所有引用的构造函数确认已定义。
- 16 个相关 Python 构建测试（test_au_face_compat + test_compatibility_registry）全绿。
- **从下载的 au-f 成品包里解出兼容 mod 二次确认是本轮新版**：index 35/共 37 mod，含 `buildClothingLayers`、`normaliseFileName`、`DELIBERATELY NOT PORTED` 三个标志串。

## Git / CI

- 提交 `09a4542`：`feat(mod): backport v4 clothing-layer srcfn naming into v3-layer-compat`，已 push 到 **vega**（不是 feat 分支——前几轮已合入 vega，本轮直接在 vega 上推进）。
- push 自动触发 `build.yaml`（vega 分支 push 即构建，`mods/**` 不在 paths-ignore）→ run `29195346344` 成功。
- 探针目录 `au_probe/`、`mb_src_probe/` 是本地调查产物（解压的游戏资源与框架源码），**未提交**，也未加进 .gitignore（下次留意别误提交）。

## 待用户真机验证（本轮测试包）

`output/v3compat-clothing-test/DoL-0.5.10.12-XFox-1.0.8a-au-f-0712.zip`（同目录另有 au-a/au-m/base 三个备用）。

重点看：**NPC 侧边栏衣服层贴图是否恢复正常**（之前是"没穿衣服"异常）。
预期仍有：`eyes.png` 改脸报错——AU 改脸 mod 自身素材问题，不在本轮范围，已多次查证。

## 下一步

1. 用户真机测 au-f-0712，回报 NPC 衣服层是否正常。
2. 若通过 → 本轮修复闭环，衣服层 bug 彻底解决；可考虑是否给兼容 mod 发独立 Release（此前待决的"发布形式"二选一仍悬置）。
3. 若仍异常 → 对照 base 包报错定位是覆盖未生效还是别的图层。
4. 改脸 eyes.png（AU 资源问题）仍是独立待办。

---

# 【2026-07-13】DOLI 悬浮窗图裂修复 + 萨姆"默认无衣服"定性为框架行为

## 一句话现状

DoL-XFox 真机测试暴露两件事，本会话都查到源码级根因并分别处理：**DOLI 悬浮窗图标裂**（真 bug，已修，构建期补丁 + 测试，未提交）；**侧边栏萨姆没穿衣服**（不是 bug，是 maplebirch v3.14 NamedNPC 系统未给香草 NPC 铺穿着数据的默认行为，不修，记录归档）。改脸 `eyes.png` 报错继续维持"AU 改脸素材自身问题、非本项目范围"的既有结论。

## Q1：DOLI 悬浮窗图裂（真 bug，已修）

**根因**（与 maplebirch 连字符 bug 同类——第三方 mod 用了旧版 DoL 资源命名）：
- DOLI v0.2.3 在 `dist/DOLI.js` 的 `FloatButton.mount()` 里硬编码 `icon.src = 'img/ui/sym_awareness.png'`（下划线）。
- DoL 0.5.9.8+ 把全部 `sym_*.png` 重命名为 `sym-*.png`（连字符）；当前 0.5.10.12 包里实际文件是 `img/ui/sym-awareness.png`。
- 旧下划线路径不存在 → 悬浮按钮图标 404 图裂。同文件另一图标 `img/ui/options.png`（约 26070 行）命名没变，仍有效，所以只有悬浮按钮裂。
- 坐实：`GameOriginalImagePack-0.5.8.10` 里是老命名 `sym_awareness.png`，而 0.5.10.12 成品包 `img/ui/` 里已是 `sym-awareness.png`（连字符）；DOLI 是构建期从 GitHub 现下 `DOLI.mod.zip`，本地改不到，必须走管线 repack。

**修法**（照搬 more_love 的下载期 payload-patch 范式）：
- `lyra/build.py` 新增常量 `DOLI_CACHE_NAME/DOLI_FLOAT_ICON_MEMBER/DOLI_FLOAT_ICON_OLD/NEW` 与函数 `patch_doli_float_icon_path()`：只把 `dist/DOLI.js` 里 `sym_awareness.png`→`sym-awareness.png` 一个字符串替换，其余 zip 条目原样保留（含重复条目）。
- 把 `_modloader_mod_path_for_injection` 从"只认 more_love"拆成 `_patch_more_love_payload` + `_patch_doli_payload` 两分支；DOLI 走 **fail-closed**：源仓库/tag/asset 元数据漂移或找不到 needle 时构建期报错，绝不静默发出坏图标。
- `lyra/compatibility.py` 注册兼容面 `DOLI_FLOAT_ICON_PATCH_KEY`（scope `default-path`、kind `payload-patch`、fail-closed，移除条件=DOLI 出对齐 `sym-*` 命名的版本）。

**验证**：
- 新增 `tests/test_doli_float_icon_patch.py`（6 项：改写/重复条目保留/幂等/构建期用补丁包/needle 漂移 fail-closed/元数据漂移 fail-closed）；同步更新 `tests/test_compatibility_registry.py`（surface 集合 + default-path payload-patch 列表加入 DOLI）。21 项补丁/注册表测试全绿，ReadLints 无错。
- **拿真实 `workspace/temp/doli.mod.zip` 跑了一遍**：`status: patched`，旧下划线路径消失、新连字符路径就位。临时验证产物已删。

## Q2：萨姆侧边栏"没穿衣服"= 框架默认行为（不是 bug，不修）

用户两次纠正推翻了我最初"可能是自定义外观"的猜测：**默认外观也没衣服，且游戏里改不了萨姆的衣服**。翻 maplebirch v3.1.14 源码（探针 `mb_src_probe/v3`）逐层坐实：

1. **具名 NPC 初始只有裸体衣柜**：`NPCWardrobe.init` 里 `this.clothes[name] ??= new WardrobeClothing(name, ['naked'])`——萨姆这类香草 NPC 建出来只有 `naked` 一件。
2. **匹配不到穿着就回落裸体**：`WardrobeClothing.worn` 结尾 `... ?? 'naked'`，无任何穿着条件命中时直接返回 `naked`。
3. **框架从没给香草 NPC 注册真实穿着**：全源码搜 `.clothes.register(` / `.clothes.add(` 给萨姆铺衣服的调用——一处都没有。`VanillaClothes.init()` 只定义 `neutralDefault/hermDefault` 两套占位，没"穿"到具体 NPC 身上。

结论：侧边栏渲染萨姆时衣服层 `srcfn` 拿到 `naked`，自然不画衣服图，**且无任何 `Failed to load image` 报错**（用户已确认）——与之前兼容 mod 修的"路径命名掉图 bug"根因完全不同。这属于 **maplebirch v3.14 NamedNPC 系统的未完成度**，不是 DOL-X 构建/兼容 mod/AU 美化的问题。真要给萨姆穿衣服需 mod 主动调 `maplebirch.npc.clothes.register(...)` 铺内容层数据，成本高、非路径兼容能解决，**不纳入修复范围**，与改脸 eyes.png 并列归"框架/资源自身、非本项目"类。

## 本会话未提交改动（累加在前面 07-12 之上）

- `lyra/build.py`：新增 DOLI float-icon payload-patch + 分发拆分（在 07-12 的 local-mod 接线基础上）。
- `lyra/compatibility.py`：注册 `doli_float_icon_path` 兼容面。
- `tests/test_doli_float_icon_patch.py`：新增（6 项）。
- `tests/test_compatibility_registry.py`：更新（纳入 DOLI surface）。
- `CHANGELOG.md`：Fixed 段新增 DOLI 图标修复条目。
- 探针 `au_probe/`、`mb_src_probe/` 仍是本地调查产物，未提交（下次留意别误提交）。

## 下一步（DOLI 线）

1. 等用户确认后统一提交（build.py + compatibility.py + 两个测试 + CHANGELOG）合入 vega，触发 CI 出带修复的包。
2. 用户真机装新包验证悬浮窗图标恢复正常。
3. 萨姆无衣服、改脸 eyes.png 两项维持"已定性、不修"，除非将来引入内容层 mod 或 AU 补齐素材。
