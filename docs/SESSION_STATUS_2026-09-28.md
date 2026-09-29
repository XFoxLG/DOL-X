# 会话状态 2026-09-28：框架定版 v4.1.14（推翻 4.2.9 实验）+ 灾备镜像建立

## 一句话结论

`vega-0511-prep` 上跑的 maplebirch **4.2.9 是坏版本**，已用离线浏览器冒烟实测出三条真回归，
现已回退到 **4.1.14**；同时确认 **0.5.11.9 本体 + 4.1.14 框架可以直接用上游现有的
0.5.10.12 命名资产**，并建立了 `maplebirch-framework-mirror-v4.1.14` 灾备镜像。

## 一、这次要回答的问题

1. 4.1.14 之后被作者删掉的版本里，有没有比 4.1.14 更好的？
2. "旧的 4.x 框架"是不是需要复原？
3. 能不能把最好的版本提取成镜像？

## 二、被删版本的完整找回与逐版核验

作者在 2026-09-24 批量删除了 20 多个 release tag。Release API 只剩 9 个，但
**GitHub Actions artifacts 一件都没丢**（`expired=false`，31 件）。本轮把 31 件全部下载解包，
逐版读了 `boot.json` 与 `dist/inject_early.js`：

| 版本 | 资产 | GameVersion 要求 | `faceStyleSrcFn` | error 自递归 |
|---|---|---|---|---|
| 4.1.2 | 0.5.11.9 | ≥0.5.11.9 | 0 | 0 |
| 4.1.12 / 4.1.13 / **4.1.14** | 0.5.10.12 | ≥0.5.10.12 | **1** | 0 |
| 4.2.0 | 0.5.11.9 | ≥0.5.11.9 | 0 | 0 |
| 4.2.1 – 4.2.8 | 0.5.11.9 | ≥0.5.11.9 | 0 | 0 |
| 4.2.9 | 0.5.11.9 | ≥0.5.11.9 | 0 | **1** |
| 4.3.1 / 4.3.3 / 4.3.4 / 4.3.5 | 0.5.12.11 | ≥0.5.12.11 | 0 | 0 |
| 4.4.0 | 0.5.12.11 | ≥0.5.12.11 | 0 | 0 |
| 4.4.1 | 0.5.12.13 | ≥0.5.12.13 | 0 | 0 |
| 5.0.0 – 5.0.4 | 两个变体 | ≥0.5.11.9 / ≥0.5.12.13 | 0 | 0 |

关键事实：**`faceStyleSrcFn` 这个导出只在 4.1.12 / 4.1.13 / 4.1.14 三版存在**。
4.2.0 把它连同 `FaceStyleOptions` / `FaceStyleNameFn` / `FaceStyleName` 一起删了，
4.2.1 恢复了 faceStyle 渲染但没有恢复该导出，之后所有版本都没有。

另外注意到上游有一条长期存在的 `dol-v0.5.11.9` 分支（最早提交可追到 2026-02-27），
4.1.2 的 artifact 就是它为 0.5.11.9 出的包 —— 说明"0.5.11.9 本体 + 4.x 框架"上游自己在做，
只是 4.1.14 那一版没有同时出 0.5.11.9 变体。

## 三、决定性实测：三条真回归

方法：取已构建的 `output/DoL-0.5.11.9-XFox-1.0.0a-au-f-0915.zip`，**只把
`window.modDataValueZipList` 里的 maplebirch 载荷替换掉**，其余成员逐字节不动，
然后跑 `tools/browser_smoke_test.py --profile ucb-cheat-extended-maplebirch`。

| 产物 | high | `faceStyleSrcFn` | 栈溢出 | `UIBar` | 桌宠丢失 |
|---|---|---|---|---|---|
| 0915 原版（mb **4.2.9** + DOL-X 补丁） | 26 | **3** | **2** | **24** | 0 |
| 0915 + mb **4.1.14**（不打补丁） | 18 | **0** | **0** | **0** | 1 |
| 0915 + mb **4.1.14** + DOL-X 补丁 | 19 | **0** | **0** | **0** | **0** |
| 0810 已发布基线（0.5.10.12 + mb 4.1.14） | — | 0 | 0 | 0 | 0 |

三条回归的原文：

```
TypeError: faceStyleSrcFn is not a function
  at eval (...Degrees of Lewdity.html:3:153894, <anonymous>:150119:26)

ModLoader ====== AddonPluginManager.triggerHookWhenSC2() error [maplebirch]
  [maplebirchAddon] [whenSC2PassageEnd]  RangeError: Maximum call stack size exceeded
    at EventEmitter.error (<anonymous>:59:24847)
    at EventEmitter.error (<anonymous>:59:24863)   ← 自递归，4.2.9 独有

ReferenceError: UIBar is not defined
```

**AU Face 为什么静态审计抓不到**：调用方不在可解析的成员里。真实逻辑打包在
`【AUsDoL】facial expansion.zip.crypt`（9332 B 密文）+ `.salt` + `.nonce`，
由 `SimpleCryptWrapper.js`（5.49 MB，32 处 `eval`）运行时解密。所以
`tools/au_artifact_check.py` 三个 AU 审计全 PASS，运行时照样抛错。
**只有运行时冒烟能发现这一类"框架删 API + 加密 mod 调用它"的组合。**

## 四、跨本体兼容性（为什么不需要复原、也不需要自建补丁）

把 0.5.10.12（0810）与 0.5.11.9（0915）两个产物的游戏 HTML 逐锚点对比：

| 锚点 | 0.5.10.12 | 0.5.11.9 |
|---|---|---|
| `updatesidebarimg` | 177 | 180 |
| `Renderer` | 1015 | 1016 |
| `CanvasModels` | 29 | 29 |
| `setup.faceStyleOptions` | 11 | 11 |
| `setup.faceVariantOptions` | 6 | 6 |
| `npcPregnancyCycle` | 2 | 2 |
| `recordSperm` | 167 | 167 |
| `pregnancyDaysEta` | 6 | 6 |
| `getChildDays` | 5 | 5 |
| `V.facestyle` / `V.facevariant` | 2 / 1 | 2 / 1 |

宿主契约没有变化。4.1.14 的 `boot.json` 声明 `GameVersion >=0.5.10.12`，0.5.11.9 满足下限，
所以这个 0.5.10.12 命名的资产可以直接装在 0.5.11.9 本体上跑 —— 上面的实测已经证实。

两个补丁的 needle 在官方 4.1.14 资产上实测：pet remount **1 命中**（193 B）、
AU face variant **1 命中**（129 B），打完补丁 `node --check` 通过，两个 marker 各 1 处。

## 五、这次的改动

| 文件 | 改动 |
|---|---|
| `config/build.toml` | maplebirch 段回退到 `maplebirch-release-v4.1.14` / `maplebirch-0.5.10.12-v4.1.14.mod.zip`；镜像注释更正为真实存在的 `maplebirch-framework-mirror-v4.1.14` |
| `config/mods.lock.json` | maplebirch 条目回退到 `v4.1.14` + `e44c9aed…`，`last_tested_dol_version` 记为 `0.5.11.9`，新增 REVERTED 证据条目 |
| `lyra/build.py` | pet remount needle 回退到 4.1.14 形态（去掉 4.2.9 插进来的 `e.on(":language",…)` 前缀） |
| `lyra/compatibility.py` | 两条 maplebirch surface 回退到 4.1.14 指纹；说明文字更新为回退理由 |
| `lyra/warmup.py` | **`maplebirch` 加入 fail-closed digest 名单**（原先只有四个 AU 载荷） |
| `tests/` | 三个测试文件的版本期望串改回 4.1.14 |
| `docs/CURRENT_PROJECT_STATE.md` | 新增「框架版本决策」小节 |
| `docs/release-notes/maplebirch-framework-mirror-v4.1.14.md` | 镜像 release 正文 |

## 六、灾备镜像（已建立）

- Release：[`maplebirch-framework-mirror-v4.1.14`](https://github.com/XFoxLG/DOL-X/releases/tag/maplebirch-framework-mirror-v4.1.14)
- 资产：`maplebirch-0.5.10.12-v4.1.14.mod.zip`，186903 B，
  sha256 `e44c9aeda62e8cf9cf76a85907c55b8b651541bccb8c6da0ee1b4eda965923a4`
- 与官方资产**逐字节相同**（GitHub 报告的 digest 与官方 Release API 一致）
- 上游是 MIT 许可（Copyright (c) 2026 楓樺葉），允许再分发
- **默认仍走官方源**；镜像只在官方资产消失或被原位换包时人工启用
- 顺带更正：历史注释里的 `maplebirch-framework-mirror-v4.1.13` **从未真正创建**（远端 404），
  旧记录有误

## 七、缓存缺口已堵

`lyra/warmup.py` 的 `LOCKED_AU_PAYLOAD_CACHE_NAMES` 现在包含 `maplebirch`。
回退时实测到两边缓存都是错的 —— `workspace/temp/maplebirch.mod.zip` 是 **4.2.9**、
`output/cache/maplebirch.cache` 是 **4.1.13**，而版本守卫正确报出
`MISMATCH ('maplebirch-release-v4.1.14', '4.2.9')`。已把核验过的 4.1.14 载荷装回
`workspace/temp/`，digest 守卫 PASS。

## 八、验证记录

- `python -m pytest -q` → **286 passed**
- `compatibility_source_errors` → 两条 maplebirch surface 全 OK，无任何错误
- `tools/quick_check.py` → **13/13 mod URLs 可访问**，`mods.lock.json` 与 `build.toml` 同步
- 官方 4.1.14 资产上：两个 needle 各 1 命中，打完补丁 `node --check` rc=0，marker 各 1 处
- 浏览器冒烟四组对照（见第三节表格）

## 九、仍未做 / 边界

- **真机（MuMu 12）验收未做。** 本轮全部证据来自离线浏览器冒烟；真机 B2 复测仍待执行。
- `vega-0511-prep` 的改动**未提交、未推送**；`vega` 主线分支未被触碰。
- 0.5.11.9 本体的正式产物**尚未用 4.1.14 重新构建**。本轮验证用的是手工换载荷的测试包，
  不是 `prepare → warmup → build` 全链路产物。
- AU-M / AU-A 仍按既定决策不做真机验收。

## 十、下一步

1. 用回退后的配置跑一次完整构建（`prepare → warmup → build zip/apk`），产出
   `0.5.11.9 + 4.1.14` 的正式四产物候选。
2. 对候选跑 `tools/au_artifact_check.py` + 浏览器冒烟门禁，确认与手工测试包一致。
3. 真机 B2 复测。
4. 通过后再决定 `vega-0511-prep` 的提交与推送。
5. 长期：把浏览器冒烟纳入 AU-F 的构建后门禁（本轮已经两次证明它能抓住静态审计抓不到的问题）。
