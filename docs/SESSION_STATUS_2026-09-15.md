# 会话状态 2026-09-15：路线 B 沙盒构建闭环（ZIP + APK，四产物审计通过）

本文是当前恢复入口，优先级高于更早的会话状态记录。当前分支是 `vega-0511-prep`（路线 B 沙盒分支）。
本轮没有提交，也没有推送。`vega` 主线与工作区既有改动全程未动。

## 本轮结论一句话

路线 B 的 0.5.11.9 + maplebirch 4.2.9 + CE 1.20(dev260903) 组合已在本机成功构建出全部四个产物
（base/AU-F 各 ZIP+APK），四个产物的 AU 审计均 PASS、errors 为空数组，两个 APK 的
zipalign 与 v1/v2/v3 签名均核验通过。真机验收（B2）尚未进行。

## 一、网络根因与解法（关键，下次直接复用）

之前判断的「代理坏了」和「没用代理」都不对。真实情况是**不同域必须走不同路**：

| 目标 | 直连 | 走代理 127.0.0.1:7890 |
|---|---|---|
| `github.com`（release 下载） | 三次全失败（exit 28/35） | 200，稳定拿到 180036 字节 |
| `api.github.com`（Release API） | 200 | 三次全 exit 35（SSL connect error） |

系统代理为 mihomo-alpha，注册表 `ProxyEnable=1`、`ProxyServer=127.0.0.1:7890`，监听地址是 `::`。

**解法**：设 `HTTP_PROXY`/`HTTPS_PROXY` 指向 7890，同时设 `NO_PROXY=api.github.com`
（大小写两个变量都设）。一个环境变量实现分域路由，不用改任何代码。
`tools/quick_check.py` 由此从 13/13 全红变为 **13/13 全绿，PASS**。

## 二、tag 格式陷阱（上一轮计划里写错了）

DOL-X 自己的 tag 格式是 `v{本体}-{汉化}-{日期}`，例如 `v0.5.11.9-1.0.0a-0915`。
不要传汉化仓库的 tag（`v0.5.11.9-chs-1.0.0a`）：`LyraVersion.from_tag()` 会把它解析成
`chs_ver=chs`，最终去请求不存在的 `v0.5.11.9-chs-chs`。

## 三、构建链执行结果

`prepare --tag v0.5.11.9-1.0.0a-0915` 成功，耗时约 8 分钟。
下载选中 `DoL-ModLoader-0.5.11.9-v2.101.1.APK` 与同名 `.zip`（**不是** polyfill 变体），
另加 `GameOriginalImagePack-0.5.11.9.mod.zip`、`ModI18N-0.5.11.9-chs-1.0.0a.mod.zip`。
`base/base.zip` 内 HTML 为 82,267,118 字节，与 0.5.11.9 的 81MB 量级相符。
`base/versions.json` 记录汉化仓库版本 `v0.5.11.9-chs-1.0.0a`。

`warmup --codes 15704320,15705344` 成功。maplebirch 三重校验通过：180036 字节、
`boot.json` 版本 `4.2.9`、sha256 `0063defa…5975` 与 `config/mods.lock.json` 逐字符一致。
CE 确认 `1.20(dev260903)`，`GameVersion >=0.5.11.9`。

`build zip --codes 15704320,15705344` 成功（注意 pack type 是位置参数，不是 `--pack-type`）：

- `output/DoL-0.5.11.9-XFox-1.0.0a-base-0915.zip`，61.3 MB，sha256 `47b371931880d089…`
- `output/DoL-0.5.11.9-XFox-1.0.0a-au-f-0915.zip`，109.5 MB，sha256 `3b00c98f921ec814…`

`build-manifest-0511.json`：`success=true`，`success_count=2`，`fail_count=0`。

`tools/au_artifact_check.py` 两个产物均 PASS，`errors` 为空数组。AU-F 关键计数：
blush 层 1-5 齐全、face variant switch marker 3、migration marker 1、post-I18N marker 1。
base 正确地不含任何 AU 标记与 AU 载荷。

## 四、缓存陷阱（差点毁掉整轮验证）

首次 warmup 打印「预热 modloader mod」后一个 mod 都没下载。根因：
`ResourceWarmer._download_modloader_mod()` 只判断 `dest_path.exists()` 就跳过，
而 digest 校验（`_validate_locked_au_payload_digest`）只覆盖
`LOCKED_AU_PAYLOAD_CACHE_NAMES = {au_f, au_m, au_a, au_face}` 四个 AU 载荷，
**maplebirch 不在校验名单内**。

`workspace/temp/maplebirch.mod.zip` 当时是上一轮的 **4.1.14**（186903 字节）。若直接构建，
产物会是「0.5.11.9 本体 + 4.1.14 框架」这个从未打算测试的组合，而且构建大概率仍会成功。

处置：清理 17 个陈旧 mod 缓存（保留有 lock digest 保护的 AU 载荷与图片包目录），重新 warmup。

**未修复的独立缺陷**：建议把 maplebirch（及其他钉版本的 mod）纳入 digest 校验名单，
或让缓存命中时校验 `boot.json` 版本与配置一致。本轮未动，避免扩大改动范围。

## 五、fail-closed 闸门拦下真实上游漂移（B0 预留验证点兑现）

首次构建失败：`Maplebirch pet remount compatibility patch failed: patch_needle_not_found`。
这不是误报，是 4.2.9 的真实代码漂移。

`Character.preInit()` 在 4.2.9 里变成：

```
preInit(){let{core:e,pet:t}=this;
  e.on(":language",()=>this.faceStyleSetupOption(),"face style setup options"),   // 新增
  e.once(":storyready",()=>{this.faceStyleSetupOption();                          // 新增此调用
    let n=e.SugarCube.Macro.get("updatesidebarimg");...}),
  e.on(":passageend",()=>void t.sync()),                                          // 新增
  this.use("pre",aM,"main"),this.use(aP,"main")}
```

每个片段单独都还在（这解释了为什么 B0 的逐锚点计数全过），但拼接后的完整 OLD 串计数为 0。
**教训：锚点存在性无法证明装配顺序**。这条已写入 `lyra/build.py` 的注释。

处置（选项 A，最小可逆）：把 OLD/NEW 串更新为 4.2.9 实际文本。needle 通过程序从真实载荷中
提取，不手工转录。针对真实 4.2.9 载荷验证：OLD 命中恰好 1 次，打补丁后 marker 恰好 1 个，
上游 `:passageend` 完整保留，体积增量 258 字节。

**未决策项：桌宠补丁是否该退役。** 上游 4.2.9 新增的 `e.on(":passageend",()=>void t.sync())`
与本补丁目标相同，但走的是本项目实测判定为不足的直接 `pet.sync()` 路径
（16316 不透明像素/裸模 vs 走宏 17588/带服装）。这是运行时问题，静态读码无法定论。
按项目先例（8 月退役 basehead 补丁用的是单变量真机 A/B），退役判断留给 B2 真机对照。
本补丁保留守卫：仅在桌宠启用**且**活容器为空时动作，不会与上游的无条件 sync 抢。

## 六、审计工具比运行时更严（已修）

AU 审计报 `embedded mod entry 28 is unreadable: JSONDecodeError`。定位为 cheat_extended
`1.20(dev260903)` 的 `boot.json` 在 `scriptFileList` 末尾有**尾随逗号**（第 52-54 行）。

关键证据：构建产物内的 ModLoader 用 `json5.parse()` 解析 boot.json
（源码 `json5__WEBPACK_IMPORTED_MODULE_7___default().parse`），json5 容忍尾随逗号。
所以 **CE 在游戏里能正常加载，是审计工具的严格 `json.loads()` 比运行时更严**。

处置：`tools/artifact_inspection.py` 新增 `parse_boot_json()`，先试严格 JSON，失败后用 json5；
json5 不可用时用窄回退（仅处理已观察到的尾随逗号形态）。`tools/au_artifact_check.py`
的 boot.json 解析改用它。修复后两个产物审计均 PASS。

注意 `json5` 未在 `requirements.txt` 中声明，因此回退路径有专门测试覆盖。

## 七、测试与验证

`python -m pytest -q`：**286 passed**（本轮起点 269，新增 17）。ReadLints 无诊断。

新增测试文件：

- `tests/test_chs_asset_selection.py`（11 项）。此前 `download_from_chs_repo()` 零覆盖。
  夹具用 0.5.11.9 真实资产名逐字写死。**上一轮我把资产名写错了**：曾写
  `Degrees of Lewdity v0.5.11.9-chs.APK`（不存在），真实名为
  `DoL-ModLoader-0.5.11.9-v2.101.1.APK`。已按 API 实际返回重写。
  新增一条锁住更阴的陷阱：真 APK 与 polyfill APK 都以 `.APK` 结尾、都含 `ModLoader`，
  且 polyfill 在 API 返回中排在前面，漏掉排除逻辑会**静默打包错包**。
- `tests/test_boot_json_parsing.py`（6 项）。覆盖尾随逗号、BOM、json5 缺失时的回退，
  以及「真正损坏的 JSON 仍须抛错」。

**测试有效性已逐项反证**（不是只看绿灯）：把每处修复临时改回缺陷形态跑测试确认变红，
再从快照恢复并核对无残留。
- `endswith(".APK")` 大小写硬编码 → 2 项失败（大写用例仍过）
- fail-fast 分支短路 → 4 项失败
- APK 匹配器移除 polyfill 守卫 → 6 项失败
- boot.json 解析改回严格 → 2 项失败（严格与损坏守卫仍过）

另外独立于审计工具验证了出厂产物：AU-F 内嵌 maplebirch 版本 4.2.9、remount marker 恰好 1、
上游 `:passageend` 保留、`:storyready` 接线保留。`OLD` 串在补丁后仍计数 1 属预期，
因为 `NEW` 以 `OLD` 为前缀再追加尾串（已验证 `NEW.startswith(OLD)` 为真），
幂等性由 marker 计数把关。

## 八、下一步

1. APK 构建（本轮只出了 ZIP）。命令：`python main.py build apk --codes ...`，需 apktool + 签名。
2. B2 真机验收（MuMu 12）。重点：
   - 桌宠补丁存废——建议做单变量对照 APK（两包只差这一个补丁），沿用 8 月 basehead 的方法论。
   - More Love 食物偏好页（B0 已从一票否决降为低风险，需真机复核）。
   - 4.2.x 是大重构线（AddonPluginProcess 移除、ModuleSystem 重写），静态相容不等于运行相容。
3. 建议把 maplebirch 纳入 warmup 的 digest 校验名单（见第四节）。
4. 考虑把 `json5` 加入 `requirements.txt`，或保留当前窄回退（已有测试覆盖）。

## 九、记忆系统写入失败（需留意）

本轮 Nocturne Memory 写入多次失败，报错均为参数丢失（`uri Field required`,`input_value={}`）。
读取正常，且本轮早期有两次写入成功，判断为传输层故障而非载荷问题；小载荷成功率较高。
本文档因此承担进度快照职责。工具恢复后应把关键结论回写进
`core://dol-x-project-info/research_gap_audit_20260913/route_b_b0_precheck_state_20260914`。

## 十、工作区边界

本轮改动：`config/build.toml`、`config/mods.lock.json`、`lyra/build.py`、`lyra/compatibility.py`、
`lyra/downloader.py`、`tools/artifact_inspection.py`、`tools/au_artifact_check.py`、
`tests/test_au_face_compat.py`、`tests/test_compatibility_registry.py`、
`tests/test_maplebirch_pet_remount_patch.py`。
新增：`tests/test_chs_asset_selection.py`、`tests/test_boot_json_parsing.py`、本文档。
构建产生未跟踪文件 `build-manifest-0511.json`（构建证据，非源码）。

工作区另有既有改动 `.gitignore`、`.vscode/settings.json`、`docs/CURRENT_PROJECT_STATE.md`
与未跟踪目录 `docs/research/`，本轮没有修改或回退它们。提交前须按文件审阅，只暂存本轮相关改动。
