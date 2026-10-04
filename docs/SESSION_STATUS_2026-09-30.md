# 会话状态 2026-09-30：路线 B 的 B2 真机验收通过

本文是当前恢复入口，优先级高于更早的会话状态记录。分支 `vega-0511-prep`，HEAD `3a06d1d`。
本轮在 MuMu 12 真机上完成 B2 验收，结论是 **通过**，并给桌宠补丁出了确定性的存废结论。

## 一句话结论

`0.5.11.9 + maplebirch 4.1.14 + CE 1.20(dev260928)` 的 0915 AU-F 产物在 MuMu 12 上通过全部
B2 检查项；桌宠 passage-remount 补丁经严格单变量 A/B 证明**必须保留**。

## 一、被验收的对象

| 产物 | sha256 |
|---|---|
| base zip | `b60b4cb4f00c9c90f20cc92135829e24f39ca5bfe660a579328e8003589b1538` |
| au-f zip | `c5ca5b68825f22fc56c454cfda2bde0b2500b3b483b6c01e6379a33e9f2f3a4c` |
| base apk | `d8120674a8738a8cc29a10b238999593170364480229924fbd461a0e4334af72` |
| au-f apk | `56dd6491ec0eabe32a4bad366bcda19b4009c4c6fc871c4327f7787e179d6e3f` |

设备是 MuMu 12（Android 12、1600x900、2 核 2GB、ADB `127.0.0.1:16384`）。回拉设备上的
`base.apk` 得到 sha256 `56dd6491…`，与本地 AU-F 0915 产物**逐字节一致**，证明被测对象就是
本轮构建的产物，而不是任何遗留的对照包。

## 二、桌宠补丁存废：单变量 A/B（本轮最有价值的结果）

**方法修正（重要的方法论发现）**：既有的 `measure_pet_remount_ab.py` 在每次翻页后都会再跑一次
含 `$.wiki("<<updatesidebarimg>>")` 的 helper。这个宏正是补丁本身在 `:passagedisplay` 上调用的
东西，等于**测试脚本替补丁做了重挂**。结果是对照组与处理组都测出 17587 像素，把真实差异抹平，
该脚本的结论不可用。本轮改写了只读版脚本（`.local/mumu-verify/verify_pet_remount_ab_clean.py`），
桌宠只启用一次，翻页后只探测、不干预。

对照组从当前 0915 AU-F APK 派生，只还原 `dolxPetRemountAfterPassageDisplay` 那一个 IIFE，
其余成员逐字节不变，并额外做了 `node --check` 语法检查（防 2026-09-26 的双逗号事故重演）。

| 组 | 翻页 1 | 翻页 2 | 翻页 3 | 翻页 4 |
|---|---|---|---|---|
| ON（补丁在位，0915 AU-F） | 17587 px | 17587 px | 17587 px | 17587 px |
| OFF（仅移除该 IIFE） | 无画布 | 无画布 | 无画布 | 无画布 |

对照组的 DOM 证据显示翻页后 `#maplebirch-character-pet` 被 SugarCube 重建为 `children=0` 的新节点，
画布彻底消失（不是变裸模）。这同时否定了「上游已有的 `:passageend` 直接 sync 足够」这一 5.x
迁移假设：4.1.14 上直接 sync 会走裸模路径（16316 px），而宏路径是带服装的 17587 px。

**判定：保留补丁。** 若将来迁移 maplebirch 5.x，needle 需要迁到
`e.host.sugarcube.require().Macro` 形态，并保证仍走宏路径而不是直接 `pet.sync()`。

## 三、B2 检查项结果（全部通过）

| 检查项 | 结果 | 证据 |
|---|---|---|
| 冷启动无红框 | 通过 | 无 FATAL / AndroidRuntime / pageerror，`topResumedActivity` 正常 |
| ModLoader 错误与警告 | 0 错误 | logcat 全量过滤 `FATAL`/`ModLoader.*error`/`maplebirch.*error`/`[Cheat Extended].*error` 全为 0 |
| CE 界面可开 | 通过 | `CEiconClicked()` 打开，截图见 `b2-ce-menu.png`：九个主分类 + 言靈集面板全部渲染；`CE v1.20(dev260928)` |
| AU-F 八脸型桌宠互异 | 通过 | 八个脸型桌宠 canvas 全部非空且哈希不同，见下表 |
| More Love 食物偏好 | 通过 | `Attitudes -> 查看NPC喜爱的食物 -> Food Preference` 页面正常渲染，无红框 |
| LongerCombat / Yanling 挂载 | 通过 | `maplebirch.modList` 含两者；模块注册表里 `combat`、`yanlingCheat` 均 state=1 |
| Save/Load 往返 | 通过 | `idb.saveState(3)` -> 导航离开 -> `loadState(3)` 回到 `Start2`，console errors = 0；测试槽已清理 |

AU-F 八脸型桌宠像素（`capture_face_preview_pet.py valid`）：

| 脸型 | 变体 | 像素 |
|---|---|---|
| 传统 | default | 17588 |
| Kiss改脸 | 大眼鼠鼠 | 17588 |
| Nss改脸 | 冷脸萌 | 17588 |
| Twinkle改脸 | 猫猫脸 | 17626 |
| 兔子改脸 | 宝石糖 | 17588 |
| 加辣改脸 | 温柔改 | 17588 |
| 沅芷改脸 | 小圆眼 | 17588 |
| 碱性糖改脸 | Q萌一号 | 17588 |

## 四、CE 环境守卫复核

`CE_environmentGuard.js` 的判定是 `/\bDoLP\b/i.test(window.StartConfig?.version)`：命中才视为
DolPlus 环境，其余归为普通 DOL 并放行 `cheat extended`。DOL-X 的 `StartConfig.version` 是
`0.5.11.9`，不含 `DoLP`，**不误伤**。真机也没有出现禁用弹窗，CE 正常加载并显示版本号。

另一个设计细节：该 hook 在 `ModLoaderLoadEnd` 里**故意不 await** `runEnvironmentGuard()`，
否则会和 `StartConfig.version` 的产生时机形成死锁。这是上游有意的实现，不要误改成 await。

## 五、边界

- AU-M / AU-A 仍按既定决策不做真机验收，只承认 CI 构建 + 静态审计。
- maplebirch 5.x 迁移未执行。本轮 A/B 给出了一个此前没有的硬约束：5.x 若只靠
  `:passageend` 直接 sync，会退化成裸模，必须验证宏路径仍可用。
- 桌宠像素数在 passage 切换瞬间存在异步过渡窗口，本轮的判据是稳定后的像素数，不是首帧。
- 对照组 APK 是测量工具，位于 `output/pet-remount-control-0915/`，**不得发布**。

## 六、下一步

1. 提交并推送本轮 B2 证据（本文件 + 工具脚本）。
2. 需要时再评估 maplebirch 5.x：先确认 5.0.4 上宏路径 needle 可迁移，再谈升级。
3. 与 `vega` 主线合流前，确认是否保留 0915 这条 0.5.11.9 线还是继续等汉化跟进 0.5.12.x。
