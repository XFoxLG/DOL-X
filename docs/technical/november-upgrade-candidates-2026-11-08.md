# 2026-11-08 正式中文升级候选与验证记录

本轮已把生态调研转成可重复构建的候选包和运行证据。中文基础为正式发行
`0.5.12.13-chs-1.0.1a`；使用 Lyra 构建链及其加载器 GUI 更新方式。
没有采用 0.5.13.8 自动翻译 nightly。候选仍未晋级正式发行。

实现分支为 `codex/november-upgrade`，基于 `8a1a84ff0bca0915968108fe84628cbad68ccc75`。
默认 build/features/combinations 配置未改变，锁文件纠正 Legacy Plus 作者署名。

## 已生成的候选

每条线路均保留完整 `config/`、输入资产、构建清单与运行结果。
全体产物路径、大小、SHA-256 和 ZIP CRC 结果见该目录的 `artifacts.json`。

| 线路 | 实际输入 | 产物 | 已完成的运行检查 |
|---|---|---|---|
| legacy | 正式 CHS 0.5.12.13、MapleBirch 4.1.14、CE 1.20.3.1、更多恋人 0.1.8.0、原 AU 栈 | base / AU-F / AU-M / AU-A，各 ZIP 与 APK | base、AU-F 浏览器启动和桌宠；AU-F 存档恢复及 Android 抽样 |
| modern | 同一正式中文底包、MapleBirch 5.6.2、CE 1.20.3.1、枯木逢春 2.5.8、归途之书 1.4.6 | base ZIP、APK | 浏览器启动、桌宠与存档恢复 |
| modern-ce-fork | modern 输入，CE 换为 Modernization 1.20.3.1-rebuild.30 | base ZIP | 浏览器启动、桌宠与存档恢复 |
| legacy Plus V3 对照 | legacy AU-F，仅替换旧图片适配模组 | AU-F ZIP | 同输入、同检查的浏览器对照 |

新框架候选没有装入旧 AU 面部扩展，也没有同时装入 LongerCombat、Yanling 拆分包。
这不代表新框架已支持完整 AU 栈。LongerCombat 是框架作者此前拆分的官方功能包，
并非社区兼容补丁；这里避免它与枯木逢春的内置功能重复。

legacy APK 包名为 `com.vrelnir.dol.xfox.candidate.legacy`；modern 为
`com.vrelnir.dol.xfox.candidate.modern`，可与稳定游玩版并存。同一线路的四种外观是替换选择。
候选均保持既有无损图片处理方式。

## 构建链的实际改动

- `main.py --config-dir` 选择完整的独立配置目录；通过环境变量传递给 Windows spawn
  工作进程。构建清单记录实际配置目录。默认调用方式继续有效。
- 支持作者已经发布的 JeremieModLoader v1 `.modpack` 外层容器。按上游
  `scripts/modpack.ts` 的 BSON 元数据、64 字节块布局和 xxHash64 校验读取，转换为现有
  ZIP 注入链可读的形式。内部文件逐字节保留，不执行或解密内部代码。
- warmup 保留并校验原始 `.modpack` 的锁定 SHA-256，重新生成派生 ZIP；原始载荷不通过校验时，
  不留下可被下一次 build 使用的旧派生缓存。
- 更多恋人 0.1.8.0 的拖动脚本与已支持的 0.1.7.0 相同，因此只增加这一个明确来源的版本许可。
  原“未来版本拒绝”测试改用尚未支持的 0.1.9.0；这是明确扩大支持范围。
- MapleBirch 5.6.2 已自行在 `:passageend` 同步桌宠。仅在版本与发布代码精确匹配时使用上游行为，
  不套用旧 4.x remount 补丁；AU 专用兼容仍只允许已验证的 4.1.14。
- 更新检查分开记录安装项、主动锁定／禁用项，以及 Lyra、正式 CHS、新内容和 CE Fork 观察项。
  网络或元数据失败会留下报告并返回失败，Actions 不再把缺失报告解释为“没有更新”。
  观察配置不参与安装或自动升级。

## 运行证据

三条主要线路都真实进入 `Orphanage Intro`。浏览器抽样中没有捕获到页面未处理异常。
功能检查使用独立浏览器上下文，未读取个人存档。每组均导出游戏存档、重载页面、导入，并检查
提交到历史帧的标记和场景是否恢复；三组均通过。保存前会正常切换页面提交状态，避免把未进入
SugarCube 历史帧的临时控制台赋值误当成存档丢失。

| 检查项 | legacy base | legacy AU-F | modern base | modern CE Fork |
|---|---:|---:|---:|---:|
| 进入游戏 | 通过 | 通过 | 通过 | 通过 |
| 桌宠启动与连续两次换页 | 通过 | 通过 | 通过 | 通过 |
| 桌宠不透明像素抽样 | 5924 | 17587 | 5924 | 5924 |
| 重载后存档恢复 | 未单独测 | 通过 | 通过 | 通过 |
| 恢复后的可见错误 / Renderer.ImageErrors | 未单独测 | 0 / 0 | 0 / 0 | 0 / 0 |

modern 运行时实际列出 `maplebirch 5.6.2`、`deadwood-reblooms 2.5.8`、
`revelation-the-book-of-return 1.4.6`。Fork 组实际列出
`cheat extended 1.20.3.1-rebuild.30`。这是加载与抽样证据，不是全部内容剧情验收。

Android 抽样使用 MuMu 15。
AU-F 正常候选已安装并启动；为了检查 WebView，另生成只增加 `android:debuggable=true`
的诊断副本。`debug-equivalence.json` 验证两者全部 `assets/www/` 文件字节一致。
诊断副本实际进入同一场景；桌宠启动为 17588 个不透明像素，连续两次换页均为 17587，
最终没有可见错误、没有残留 Renderer.ImageErrors。原生截图需要选中游戏所在的独立显示屏；
默认显示屏是模拟器桌面，不能凭它判断游戏退出。

证据位置：

- `legacy/functional-au-f-committed-state/functional.json`
- `modern/functional-base-committed-state/functional.json`
- `modern-ce-fork/functional-base/functional.json`
- `legacy/android-au-f/device-functional.json`、`after-pet.png`
- 各线路 `smoke-*/browser-smoke-report.json` / `.md` 及截图

## Plus V3 与 Fork 的取舍

Plus V3 来自作者仓库
<https://github.com/chris81605/Legacy-Art-Mods-Compat> 的固定提交
`c3bf6c891b152549425a5a8dfca5310e7b7be96b`，使用原仓库 boot.json 和脚本打包。
它不是未经核实的 Discord 附件副本。AU-F 对照确认产物仅 HTML 中的这个模组变化，
全部图片字节不变；两组桌宠均为 17587 像素，冒烟检查均记录 19 个高等级日志条目。
因此本轮没有证据证明 V3 能解决现存 AU 视觉问题，不替换默认版本。

CE Modernization 已通过新框架上的启动和自建存档恢复，具备继续比较的可运行基线。
原作 CE 同样通过这些检查，不能仅凭 Fork 更新较多认定它全面更优。
当前优先保留原作候选，Fork 继续作为功能对照。

## 测试与构建校验

- 全测试套件：1037 passed、9 skipped。
- 之后配置、容器、更新检查与清单改动的定向回归：36 passed。
- 最后派生缓存失效处理：19 passed；同时完成 `compileall`。
- `quick_check.py`：配置、四构建码、锁文件同步及 13/13 模组 URL 检查通过。
- 在线更新检查完成：3 个安装项、5 个观察来源；安装项发现 MapleBirch 和 CE 两项变化。
- 5.6.2 框架合同检查 consistent；原版 .modpack / ZIP 对照文件逐字节一致。
- 12/12 产物通过 CRC 与游戏版本／内置模组身份检查，见 `artifacts.json`、`package-checks.json`；
  APK 签名以及配置、构建清单均留档。AU-F 诊断副本的 22155 个 Web 资产与正常候选字节一致。
- 设备检查结束后已恢复非 debug 的 AU-F 候选，保留候选数据；稳定包未被覆盖。

APK 使用既有签名，构建结果分别记录。

## 限制与晋级条件

当次浏览器完整冒烟报告为 FAIL，具体问题包括：

1. CustomHair 的 `main.js` 请求示例域名 `https://api.example.com/data`，并在失败分支初始化颜色。
   因而不能简单删掉请求调用；后续应将现有颜色初始化从网络错误分支中独立出来，再验证染发。
2. 旧图片适配／脸型搜索会产生缺图探测。AU-F 恢复后的 ImageErrors 为空，但这不足以证明
   所有脸型、白虹膜、雀斑、腮红、泪痕均已正确。Plus V3 本轮没有改善这项抽样。
3. 更多恋人 0.1.8.0 查询可选 `Wraith'sReflection` 时加载器会记 console.error；源码显示为可选
   恋人槽位检测，当前未观察到可见故障。仍保留原始错误计数。
4. base 中狼图标、鞋袜旧命名有缺图日志；需要在对应实际界面确认最终资源与显示效果。
5. 本轮存档验证为候选内自建存档往返，未证明个人旧长档从 1014 跨版本迁移、跨 CE Fork 迁移。
   AU-M/A 仅构建与静态检查；新框架 APK 未做设备功能验收；手机和 HarmonyOS 未覆盖。
6. 未运行远端 GitHub Actions，未提交、推送或发布；第三方候选素材和原始社区档案保留在本地。

下一次正式晋级应先解决有明确触发路径的残留问题、完成旧存档副本迁移与目标场景验证，
再切换默认正式中文基线。稳定 1014 仍作为回滚选择。观察上游继续跟进，安装选择由证据决定。
