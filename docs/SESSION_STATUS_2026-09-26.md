# 会话状态 2026-09-26:路线 B 真机验收(B2)发现回归,阶段 2 完成,阶段 3 暂停

本文是当前恢复入口,优先级高于更早的会话状态记录。当前分支 `vega-0511-prep`,
HEAD `415ab78`,本轮**未提交、未推送**,`vega` 主线与工作区既有改动未动。

## 一句话结论

**阶段 1(B2 真机验收)未通过。** 0.5.11.9 + maplebirch 4.2.9 的产物在浏览器侧复现出
两条**真回归**:maplebirch 4.2.9 的 `whenSC2PassageEnd` 递归栈溢出(影响 base 与 AU-F 全部),
以及 AU Face 调用已被 4.2.9 删除的 `faceStyleSrcFn` 导致致命 `TypeError`(AU-F 专属)。
按计划「阶段 1 未通过不进阶段 3」,**maplebirch 5.0.4 迁移未执行**;但 5.0.4 的静态取证已完成,
并发现**升级到 5.0.4 同样修不好 AU Face**(5.0.4 也删掉了 `faceStyleSrcFn`)。
阶段 2(作弊拓展差异分析)**已完成**,结论:`CE_environmentGuard` 不误伤 DOL-X,可采用 dev260923。

桌宠补丁存废问题(A/B)已出结论:**补丁不是回归原因,删除它不改变任何错误计数**。

---

## 一、验收对象与完整性(先确认对象没被换过)

四个产物在磁盘上,未重新构建,sha256 与 `build-manifest-0511*.json` 一致:

| 产物 | 字节 | sha256(前 24) |
|---|---|---|
| `output/DoL-0.5.11.9-XFox-1.0.0a-base-0915.zip` | 64,280,464 | `47b371931880d089506a5b1d` |
| `output/DoL-0.5.11.9-XFox-1.0.0a-au-f-0915.zip` | 114,798,537 | `3b00c98f921ec81446e6b769` |
| `output/DoL-0.5.11.9-XFox-1.0.0a-base-0915.apk` | 79,661,623 | `c5ae6d43c99f4bbfe57b8dac` |
| `output/DoL-0.5.11.9-XFox-1.0.0a-au-f-0915.apk` | 130,182,245 | `58ca2ab9b8a3f6268d40e620` |

`build-manifest-0511.json` / `build-manifest-0511-apk.json` 均 `success=true`,2/2 成功。
**注意**:这四个 APK 用的是本地测试证书 `8C6EB4D6...`,不是正式证书。

## 二、回归证据(与已发布的 0808 逐项对照)

工具:`tools/browser_smoke_test.py`(Playwright,需系统 Chrome channel 回退)。
对照组是**已发布、已真机用过的** `DoL-0.5.10.12-XFox-1.0.8a-au-f-0808`(0.5.10.12 + maplebirch 4.1.13)。

| 信号 | 0808 已发布 | B1 base 0915 | B1 au-f 0915 | B1 au-f **删掉桌宠补丁** |
|---|---|---|---|---|
| `whenSC2PassageEnd` 栈溢出 | 0 | **1** | **1** | **1** |
| `Maximum call stack` / `RangeError` | 0 | 1 | 1 | 1 |
| `faceStyleSrcFn is not a function` | 0 | 0 | **2** | **2** |
| `<<CEstatebox>> does not exist` | 0 | 0 | 12 | 12 |
| `[Cheat Extended]` 日志条数 | 162 | 164 | **1** | 1 |

三条独立结论:

1. **桌宠补丁不是原因。** 单变量对照包(只删 `dolxPetRemountAfterPassageDisplay` 这一个 IIFE,
   其余成员逐字节相同)的错误计数与处理版**完全一致**。桌宠"是否带服装 / 不透明像素数"的
   像素级 A/B 在 MuMu 上无法可靠取数(CDP evaluate 超时),但**存废判断已不再依赖它**:
   回归与补丁无关,补丁没有制造问题。
2. **base 也中招。** 栈溢出不是 AU-F 专属,凡挂 maplebirch 4.2.9 就触发。base 的 CE 日志
   164 条正常,说明 CE 在 base 上照常工作。
3. **AU-F 的 CE 是被"连坐"的,不是 CE 自身坏了。** 0915 的 CE 日志只有 1 条(即
   `[Cheat Extended] 🔧 money 函數已掛到全局`),之后 CE 的初始化链在 `:storyready` 阶段被
   `faceStyleSrcFn` 的 `TypeError` 打断,于是 `CE_CheatExtendedVersion` / `CEstatebox` 这些宏
   **从未注册**,才在 `Start` / `Start2` 报 "macro does not exist"。
   对照 0808:`[Cheat Extended]` 162 条,宏全部正常。

### 2.1 根因定位:`faceStyleSrcFn` 在 4.2.9 被删除

直接对真实载荷取证(不是读源码猜):

| maplebirch 版本 | `dist/inject_early.js` 里 `faceStyleSrcFn` |
|---|---|
| 4.1.13(0808 实际挂载) | 1(并带 `faceStyleSrcFn=aD` 赋值 + `.d.ts` 声明) |
| **4.2.9**(0915 实际挂载) | **0(彻底删除)** |
| **5.0.4**(目标版本) | **0(同样没有)** |

调用方不在可静态解析的成员里(0915 的 AU-F HTML `faceStyleSrcFn` 计数为 0,说明调用发生在
**AU Face 自己的载荷** `【AUsDoL】facial expansion` 内部 —— 该包以加密形式分发,静态只能看到
外层加载器 `earlyload.js` 与其自带的解密入口)。
这与「4.1.x 能用、4.2.9 起致命」的观测完全自洽:**是框架删了 API,AU Face 还在调**。

**这意味着阶段 3 不能只换版本号。** 5.0.4 也删了该 API,单纯升到 5.0.4 后 AU-F 仍会致命。
要么 AU Face 出适配版,要么 DOL-X 自建一层 `faceStyleSrcFn` 兼容 shim,要么 AU-F 停在 4.1.x 线。

### 2.2 另一条:4.2.9 的 `whenSC2PassageEnd` 递归栈溢出

```
[error] ModLoader ====== AddonPluginManager.triggerHookWhenSC2() error
        [maplebirch] [maplebirchAddon] [whenSC2PassageEnd]  RangeError: Maximum call stack size exceeded
    at EventEmitter.error (<anonymous>:59:24847)
    at EventEmitter.error (<anonymous>:59:24863)   ← 无限自我递归
    ...
```

这是 maplebirch 自己的 `EventEmitter.error` 无限自递归,与 DOL-X 补丁无关(删补丁后仍在)。
`ModuleSystem` / `LanguageManager` 在 4.2.9 仍存在(分别 3 / 9 处),所以不是这两个接口被删导致。

### 2.3 LongerCombat / Yanling 在 4.2.9 上仍然挂载

两者的 `addonPlugin` 只声明 `modVersion: "^4.1.0"`(不覆盖 5.x),但实测在 4.2.9 上
`longer-combat@1.0.1` 与 `yanling-cheat-collection@1.0.1` **仍出现在已挂载 mod 列表里**,
日志与 0808 对照组条数一致(33–34 条)。所以「^4.1.0 不覆盖 4.2.9」在本轮**没有**表现为加载失败;
真正要担心的是阶段 3 的 5.x。功能可用性仍需真机点击验证,静态只能证明"挂上了"。

## 三、阶段 2:作弊拓展 dev260903 vs dev260923(已完成)

| 项 | dev260903(锁定版) | dev260923(当前 Pre-release) |
|---|---|---|
| 字节 | 350,866 | **598,600** |
| sha256 | `f0bcbdaf...` | `2c2f5604db3818f1184fd31714bef4529eabacfa19c340b5e63b0fabdc8e42e6` |
| boot.json version | `1.20(dev260903)` | `1.20(dev260923)` |
| GameVersion | `>=0.5.11.9` | `>=0.5.11.9` |

文件层面:**新增 11 个成员**(`CE_autoFarm`、`CE_brothelVending`、`CE_farmCheat`、
`CE_forestShop`、`CE_hopelessCycle`、`CE_manorHelper`、`CE_safehouseCheat`、若干 `PIC/*`),
**删除 1 个**(`game/CE_farmCheat.twee`),**修改 12 个**。

### 3.1 必须确认的风险点:`CE_environmentGuard` —— 结论是**安全**

关键更正:该脚本**两个版本都有**,不是 260923 新增的。判定逻辑是
「`StartConfig.version` 命中 `/\bDoLP\b/i` 才禁用 CE」。
DOL-X 构建产物里 `StartConfig.version = "0.5.11.9"`(那 3 处 `DoLP` 字节命中是 base64 噪声,
不是真实版本串)→ **不会误触发**。所以 dev260923 **可以采用**。

### 3.2 两版都有的既有上游 bug(不是本次引入)

`boot.json` 引用了不存在的 `addon-replace/Widgets State Man_1.txt` / `_2.txt`(悬空引用);
`boot.json` 带**尾随逗号**,严格 JSON 解析失败(运行时 ModLoader 用 `json5.parse()`,能容忍,
所以游戏内正常;这是审计工具比运行时更严,2026-09-15 已用 `parse_boot_json()` 处理)。

### 3.3 决策(待你点头后执行)

采用 dev260923,并**钉死 digest**。理由:该 tag 已**三次原位换包**,靠 tag 名锁不住。
两种钉法二选一:

- 上传到 DOL-X 自建 `cheat-extended-mirror-*` 不可变 Release(与既有灾备 tag 惯例一致);或
- 把 `cheat_extended` 加进 `lyra/warmup.py` 的 digest 强制名单
  (`LOCKED_AU_PAYLOAD_CACHE_NAMES` 目前只有 `au_f/au_m/au_a/au_face`)。

注意现有缓存守卫对它无效:`_pinned_version_from_release_tag("Pre-release")` 与
`_payload_boot_version("1.20(dev260923)")` 都解析失败 → 双 None → 走"视为可信"分支。

## 四、阶段 3:maplebirch 5.0.4 静态取证(已做,但执行被阶段 1 阻塞)

目标资产已独立下载核验:`maplebirch-0.5.11.9-v5.0.4.mod.zip`,**213,331 字节**,
sha256 `27d1e35f170b0f92a1064864b7970770c03d21d61ab01bc33797b1a670be37d8` —— 与计划完全一致。

| 项 | 实测 |
|---|---|
| boot.json version | `5.0.4` |
| `addonPlugin` | `[]`(0 条) |
| `dependenceInfo` | 8 条,末端 `GameVersion >=0.5.11.9` |
| `ModuleSystem` / `LanguageManager` | **0 / 0(已移除,与计划预判一致)** |
| `host.sugarcube.require` | 35 处(4.x 是 `e.SugarCube.Macro`,5.x 改形态) |
| **桌宠 needle `MAPLEBIRCH_PET_REMOUNT_OLD`** | **0 命中** → fail-closed 会拦下构建 |
| **AU Face 插入 needle** | **1 命中**(仍可用) |

所以阶段 3 若执行,必须同时处理:桌宠补丁二选一(退役 / 迁移 needle 到 5.x 形态)、
`config/build.toml` 的 tag/asset/url、`lyra/compatibility.py` 两条 surface 指纹、
`config/mods.lock.json` digest、三个测试文件的版本期望串。

**但即使全做完,AU-F 仍会被 `faceStyleSrcFn` 打死**(见 2.1),这是阶段 3 的**新阻塞项**,
计划里没有预见。

## 五、设备状态(已复原,已确认可启动)

验收前备份了设备数据:仓库内 `.local/mumu-verify/device-backup-20260926/xfox-data.tar`(153,278,976 字节)。

测试流程:卸载旧包 → 装测试签名 B1 包 → 卸载 → 装回正式签名 `DoL-0.5.10.12-XFox-1.0.8a-au-f-0808.apk`
→ 把 tar 备份解回 `/data/data/com.vrelnir.dol.xfox`(owner `u0_a139:10139`)。

**已确认复原成功**:签名回到 `3769a739`(原正式签名),`app_webview` / `shared_prefs` 目录在位,
`am force-stop` + `monkey` 冷启动后 `topResumedActivity` 是
`com.vrelnir.dol.xfox/com.vrelnir.dol_debug.MainActivity`,logcat 无 FATAL / AndroidRuntime 崩溃。
用户侧存档与设置仍在。

## 六、上游实况(2026-09-26 核验)

- **构建系统上游 `DoL-Lyra/Lyra` 无新提交。** `upstream/vega` HEAD = `e61352e`,
  日期 **2026-05-18**,`git rev-list --left-right --count upstream/vega...HEAD` = **`0  226`**
  → **落后 0、领先 226**。结论:构建系统保持被动跟随,当前无任何需要跟的东西。
- **枯木逢春 `MaplebirchLeaf/Deadwood-Reblooms` 没有被删除**,仓库存在且活跃
  (main,最后推送 2026-09-21,TypeScript + bun,README 声明依赖 `maplebirch >=4.3.6`),
  但 **0 个 release / 0 个 tag** → 没有可钉死的下载输入,暂不接入。
- **被删除的是 `MaplebirchLeaf/SCML-DOL-maplebirchExpansion`(maplebirchEx v1.2.4,404)**,
  这才是"旧版框架扩展模型被删"。已更正 `docs/research/2026-09-26-full-research-and-optimal-path.md`。
- **作弊拓展确实更新了**(同 tag 第三次原位换包),已做差异分析,见第三节。
- 汉化仓库最新仍是 `v0.5.11.9-chs-1.0.0a`,**无 0.5.12.x**,所以 0.5.12.13 路线仍被汉化硬阻塞。
- LongerCombat / Yanling 仍 v1.0.1(资产面向 0.5.10.12),未动。

## 六之二、补充取证(2026-09-26 追加,回答用户三个提问)

### A. 「刚开始的错误」= 我自己第一版对照包的语法错误,不是产物缺陷

截图那条 `SyntaxError: Unexpected token ','` 的时标(13:37)落在我造对照包的时间窗内。
已确定性复现其成因并留成脚本 `.local/mumu-verify/repro_double_comma.py`:

桌宠补丁的 needle 以**逗号开头**(`,e.on(":passagedisplay",...)`),它是前一个表达式的
**续接分隔符**。第一版对照包只删掉订阅文本、**留下了这个逗号**,于是变成

```
.. t.sync()})}),,this.use(  ← 双逗号
```

`node --check` 报 `SyntaxError: Unexpected token ','`,ModLoader 在
`do_initModInjectEarlyLoadDomScript` 阶段抛错 → 弹 Alert。
**修复方式**:连前导逗号一起删(脚本里 `good_removal` 分支)。
已核验磁盘上的最终对照包与 0915 处理包**都不含** `,,this.use(`(各 0 处),即那个破包已被覆盖,
现存产物干净。

**同时这也顺带证明了一件重要的事**:ModLoader 的 early-load 语法错误会**整个中止**
`injectEarlyLoadDomScript`,所以「一个 mod 写坏一个字节 → 整场启动失败」是真实存在的失败模式。
这正是把 `browser_smoke_test.py` 纳入门禁的价值。

### B. 变身兔兔:mod 早已禁用,截图里的"兔兔"是桌宠和服装名,不是那个 mod

- `config/build.toml`:`enabled = false`,注释写明 `Disabled (2026-06-24)`。
- `config/features.toml`:`required = false` 且 **`skip = true`**。
- `config/combinations.toml`:「已禁用: 1048576 (bunny_transformation) — v0.3.1β 不兼容,
  导致战斗系统崩溃(16 个 TweeReplacer 错误)」;`build_codes` 里没有它。
- 位运算复核:`base 15704320` 与 `au-f 15705344` 的 bit 1048576 **都未置位**。
- 载荷复核:0808 与 0915 两个 AU-F 产物内,`BunnyTrans`/`bunnybuild`/`bunnyTransform`
  计数**均为 0**(即兔兔 mod 的变身系统不在包里)。
  "bunny" 字样在 `ModI18N` 的 i18n.json 里有 78 处、`旧版图片名称适配` 的
  dolrename.js 里有 56 处,但那只是把 "bunny ears" / "bunny outfit" / "bunny leotard"
  这类**服装名**翻译成"兔耳" / "兔女郎装" / "紧身兔女郎装"
  (i18n.json 里兔女郎 15 处、兔耳 11 处、兔子 33 处),不是变身系统。
- 原版本体复核(勘误我上一版的表述):0.5.11.9 的 `setup.transformations`
  **不含 bunny**(只有 wolf/cat/cow/bird/fox/angel/fallenangel/demon),
  Cheats 页 `tficon "bunny"` 计数为 **0**;vanilla 里**没有** bunny 变身。
- 兔兔 mod 的 boot.json 显示它自己定义 `bunny`/`bunnybuild` 变量、`<<bunnyTransform>>` 宏,
  依赖的游戏系统里有 harpy(14 处)+ `tf_harpy`(2 处)——
  而当前 0.5.11.9 里 `tf_harpy` 计数为 **0**(harpy 已被重命名为 bird,
  `harpyTransform` 有 6 处)。这是它 2025-03 之后没再更新的根本原因。

你截图里看到的"兔兔"**不是 DOL-X 的兔兔 mod**——载荷里没有它。来源是:

1. **游戏本体的兔子服装**。vanilla 0.5.11.9 自带 "bunny ears" / "bunny leotard" /
   "bunny collar" 这类服装(`bunny ears` 15 处、`bunny leotard` 18 处、`bunny collar` 3 处),
   汉化包把它们翻译成"兔耳" / "兔女郎装" / "紧身兔女郎装"。
2. **maplebirch 的桌宠画布**。你截图右下角的小动画头像就是它(带拖拽的桌面宠物),
   与兔兔 mod 无关。三个版本都有这个桌宠
   (4.1.14 / 4.2.9 各 5 处 `maplebirch-character-pet`,5.0.4 有 3 处),
   所以换框架版本不会让它消失。

注意区分:**「变身兔兔」mod**(sylphiet/Bunny-TransformationCN v0.3.1β)是**变身系统扩展**,
它自己定义 `bunny` / `bunnybuild` 变量和 `<<bunnyTransform>>` 宏,依赖的旧游戏系统里有
harpy / `tf_harpy` 等旧名(0.5.11.9 已把 harpy 重命名为 bird),这就是它
2025-03 后没再更新的根本原因。
该 mod 2026-06-24 已被本项目永久禁用;**vanilla 里没有 bunny 变身**
(`setup.transformations` 不含 bunny,Cheats 页 `tficon "bunny"` 为 0)。
vanilla 里 `"bunny"`(9 处)全部是**服装/物品名**:animal slippers 的 `variable`、
slippers 的 `pattern`(bunny/ducky/foxy/kitty 等)、贴纸图案列表、
Gwylan 的 bunny 服装请求、`bunnyears` / `bunnycollar` 变量,和变身系统无关。

### C. AU 美化确实被框架的破坏性更新打断了 —— 4.1.x 可以用,4.2.9 起不行,5.0.4 也修不好

这不是「AU 不兼容新框架」的模糊说法,是**框架删除了 AU Face 依赖的公开 API**。已从
`.d.ts` 逐行取证(4.1.14 vs 4.2.9 的 unified diff):

```diff
-interface FaceStyleOptions { ... }
-type FaceStyleNameFn = (options: FaceStyleOptions) => string | string[];
-type FaceStyleName = string | string[];
-declare function faceStyleSrcFn(name: FaceStyleNameFn | FaceStyleName): (layerOptions: FaceStyleOptions) => string;
-    readonly faceStyleSrcFn: typeof faceStyleSrcFn;
+    faceStyleImagePaths(files: Record<string, unknown>): void;   ← 4.1.14 是 Promise<void>
+    private faceStyleSetupOption;                                 ← 4.1.14 是 _faceStyleSetupOption
```

即 **4.1.14 → 4.2.9 一次性删掉了 `FaceStyleOptions` / `FaceStyleNameFn` / `FaceStyleName` /
`faceStyleSrcFn` 四个导出**,并把 `faceStyleImagePaths()` 从无参 `Promise<void>` 改成
接收 `files` 参数的同步方法。这是**不向后兼容的签名破坏**,不是重命名。

运行时的后果正是 0915 AU-F 的致命错误:

```
TypeError: faceStyleSrcFn is not a function
  at eval (eval at call.output.output (...Degrees%20of%20Lewdity.html:3:153894), <anonymous>:150119:26)
```

调用方**不在可静态解析的成员里**——已确认 AU Face 的真实逻辑打包在
`【AUsDoL】facial expansion.zip.crypt`(9,332 字节密文)等成员里,由包内自带的解密入口
在运行时加载。
所以:静态审计看不到调用点,**三个 AU 静态审计全 PASS 也照样漏掉**。

**5.0.4 同样没有 `faceStyleSrcFn`**(d.ts 0 处、js 0 处)。升级到 5.0.4 **修不好 AU Face**。

## 七、新发现的独立缺陷(未修,仅记录)

1. **mod 缓存会静默给错版本。** `output/cache/maplebirch.cache` 实际是 **4.1.13**(186,010 B),
   不是 4.2.9。`_download_modloader_mod()` 只看 `dest_path.exists()` 就跳过,而 digest 校验
   不覆盖 maplebirch。这次没造成错误产物(0915 的构建用的是 4.2.9,已核验),
   但**下一次 warmup 若命中该缓存,会静默产出"0.5.11.9 + 4.1.13"这个从未打算测的组合**。
   建议把 maplebirch 纳入 digest 强制名单,或让缓存命中时校验 `boot.json` 版本与配置一致。
2. **`faceStyleSrcFn` 这类框架 API 删除没有任何构建期守卫。** 三个 AU-F 静态审计
   (`tools/au_artifact_check.py`) 全 PASS,因为 AU Face 载荷是加密的、审计只看得到
   `earlyload.js`。这类"框架删 API + 加密 mod 调用它"的组合只能靠运行时冒烟或真机发现。
   建议把 `browser_smoke_test.py` 纳入 AU-F 的构建后门禁(见第八节)。

## 八、建议的下一步(按优先级)

1. **先决定 AU Face 的方向**(阻塞阶段 3 的前置):向上游确认 AU Face 是否计划适配
   maplebirch 4.2+/5.x;若无,则 DOL-X 侧要么自建 `faceStyleSrcFn` shim,要么 AU-F 停在 4.1.x 线。
2. **把浏览器冒烟纳入门禁。** `browser_smoke_test.py` 能在几分钟内、不碰真机就抓住这次的
   两条回归;它是本轮最有价值的副产品。建议至少对 AU-F 强制跑。
3. **钉死 CE 构建输入**(自建镜像或 digest 名单),并顺手把 maplebirch 也纳入(第七节缺陷 1)。
4. **阶段 1 重做。** 若 AU Face 方向定为"停在 4.1.x",则阶段 1 的验收对象应换成
   0.5.11.9 + maplebirch **4.1.14**(或 4.1.13)组合重新构建;若定为"打 shim",则先做 shim 再验。
5. **仍不做** `vega-0511-prep` 的提交与推送(阶段 1 未通过)。

## 九、执行细节(下次直接复用)

- 网络分域路由:`HTTP_PROXY`/`HTTPS_PROXY=http://127.0.0.1:7890`,
  同时 `NO_PROXY`/`no_proxy=api.github.com`(`github.com` 走代理、`api.github.com` 必须直连)。
  **`release-assets.githubusercontent.com` 必须直连**(走代理会 SSL EOF)。
- tag 格式是 DOL-X 自己的 `v{本体}-{汉化}-{日期}`(如 `v0.5.11.9-1.0.0a-0915`);
  不要传汉化仓库的 `v0.5.11.9-chs-1.0.0a`。
- pack type 是位置参数:`build zip` / `build apk`。
- 冒烟命令:
  `python -u -B tools/browser_smoke_test.py <zip|dir> --profile <none|ucb-cheat-extended-maplebirch> --timeout-ms 180000 --settle-ms 15000 --output-dir <dir>`
  (默认 profile 是陈旧的 `ucb-more-love-custom-spellbook`,AU-F 要用 `ucb-cheat-extended-maplebirch`)。

## 十、子代理故障记录

本轮派出的 5 个子代理全部未能产出结果,均为**基础设施故障**,不是任务本身的问题:

- `/root/community_eco`:**上游 502**(Codey 线路请求 `glm-5.3-flash` 时上游返回 HTTP 502)。
- `/root/local_inventory`、`/root/upstream_mods`:**`CODEY_SUBAGENT_UNBOUND_ATTEMPT`**
  —— PreToolUse 门禁拒绝所有读取工具,无法把子代理与有效 attempt 安全关联。
- `/root/build_gate_scan`、`/root/upstream_v5_scan`:**429 Too Many Requests**(超出重试上限)。

按"全部失败则由主代理接管"的规则,本轮的调研、取证、写档全部由主代理本地完成。

## 十一、工作区边界

本轮**未修改任何源码/配置**,只新增/更正文档:

- 更正 `docs/research/2026-09-26-full-research-and-optimal-path.md`(枯木逢春条目)。
- 新增本文档。

未跟踪:`docs/research/`、`docs/SESSION_STATUS_2026-09-26.md`、`build-manifest-0511*.json`。
工作区既有改动(14 个已跟踪 + 未跟踪测试)本轮未动。
