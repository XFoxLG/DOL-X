# 会话状态 2026-08-10：退役 Maplebirch basehead 补丁

本文是当前恢复入口，优先级高于更早的会话状态记录。当前分支仍是 `vega`。本轮没有提交或推送。

## 最终决策

Maplebirch basehead fallback 本地补丁已经完整退役，不做成独立 mod，也不新增玩家警告。构建恢复 Maplebirch v4.1.14 上游原始 `basehead.srcfn` 行为，只保留两个独立且仍有净收益的兼容补丁：桌宠 passage remount 与 AU face variant。

这不是把旧补丁从硬编码压缩变量名改成动态解析变量名。动态解析是 2026-08-09 的中间修法，也已删除。当前构建不再读取、解析或引用 Maplebirch 的 `aP`、`aI`、`aO` 等压缩局部名，不再改写 basehead 图层。

## 单变量真机对照

对照与处置 APK 都由同一份 AU-F 0810 APK 制作，只改变内嵌 Maplebirch 的一条 basehead 表达式。两包使用同一本地测试签名和同一份已校验恢复的 48,619,488 字节 WebView profile，在 MuMu 12 上各完成两轮冷启动。

未打 basehead 补丁组两次都在首次真实点击“角色创建 *”后短暂请求 `img/face/default/base-head.png`。`Renderer.ImageErrors` 分别在约 0.84 秒和 1.64 秒出现一次，随后自动清除；桌宠分别约在 1.81 秒和 4.05 秒恢复为 17587/17588 个不透明像素。两轮都没有观察到可见错误红框。热状态逐个点击八种真实脸型链接时，8/8 都回退到 `img/body/base-head.png`，没有 basehead 错误或可见 reporter，画布保持 17587 至 17626 个不透明像素；部分合法脸型路径仍有独立的 eyes/mouth ImageErrors。

打补丁组两次都没有 base-head 错误请求，但首次打开角色创建面板后 17 秒内桌宠都没有自然挂载，末帧只有侧边栏小图，没有浮动桌宠。结合此前硬编码 `aP` 的 v4.1.14 补丁在真实开局 40 步产生 81 条 basehead 错误，说明该补丁的维护和失败面高于它避免的短暂自愈请求。

0805 的 v4.1.13 用户录像仍是有效历史证据，本次 v4.1.14 对照不能反向否定它。当前结论只针对待发布的 v4.1.14 栈：basehead 补丁没有证明净收益，因此采用最小改动，恢复上游行为。

## 已完成代码清理

`lyra/build.py` 已删除 basehead 常量、压缩 Set 解析正则、动态 replacement、补丁函数及 Maplebirch payload 链中的调用。当前 `_patch_maplebirch_payload()` 只进入桌宠 remount 补丁。

`lyra/compatibility.py` 已删除 basehead compatibility key 与 surface。`tests/test_maplebirch_basehead_patch.py` 已删除；AU、registry 与 pet remount 测试夹具已去除对旧链式补丁的依赖。pet remount 集成测试新增负向断言：注入后必须保留上游 `aO([候选, 回退])` basehead 表达式，不允许重新出现直接 `.has()` 改写。

## AU 换脸与桌宠问题重新分类

用户纠正的玩家可见现象成立：只点击 AU 脸型时，角色预览可能已经显示新脸，浮动桌宠却仍像旧脸、
闭眼、缺眼或空白。此前只验证 `V.facestyle/V.facevariant` 合法、桌宠 canvas 非空和不透明像素数，
不足以证明桌宠画面真的跟着换脸；将这些证据直接表述为“桌宠外观已同步”属于证据越界。

2026-08-10 在同一 AU-F 候选上补做了三层真机证据：

1. 八个真实脸型入口的调用链均为 `updatesidebarimg -> pet.sync -> requestAnimationFrame -> pet.render`。
   `updatesidebarimg` 进入时 sidebar cache 还是旧脸，但在 `pet.sync()` 开始前已经提交为新脸；
   `pet.render()` 读取的也是新 cache。没有发现同 Passage 内缺少同步或读取旧 cache 的竞态。
2. 合法 variant 组逐个抓取明确的 `#startImg` 角色预览与 `#maplebirch-character-pet` 画布。八个桌宠
   最终都非空，哈希随脸型变化；Kiss、Nss、Twinkle、加辣、沅芷的预览与桌宠哈希完全一致，兔子和
   碱性糖受异步/遮罩布局影响哈希不同，但画面均可见且脸型已变化。
3. 从设备拉取当前 132,386,526 字节候选，制作只移除 AU variant runtime IIFE、保留 pet remount
   与所有其他嵌套成员的单变量控制 APK。原位覆盖后，七个 AU 入口全部自然形成 `style/default`，
   `Renderer.CanvasModelCaches.main.sidebar` 也保存同一非法组合。Kiss、Nss、Twinkle、加辣的角色预览
   仍可经 fallback 显示某张脸，但桌宠显示不同退化结果；兔子、沅芷或碱性糖的桌宠变为 0 像素空白。
   这与只在刷新宏前临时恢复 `style/default` 的运行时对照一致。

最终分类：**问题的可见载体主要是桌宠，但根因是三个换脸入口写入非法的共享 variant 状态。**
Maplebirch 确实刷新了桌宠；只是角色预览的 fallback 掩盖错误，而桌宠退化更明显。当前 AU variant
补丁修在正确的状态 owner，仍应保留；passage remount 只负责翻页后新 StoryFooter 容器为空，是另一
独立问题；不应再新增桌宠专用换脸同步路径。另需收紧错误表述：0810 basehead 报告在合法 variant
下仍记录部分 `eyes.png` / `mouth-smile.png` ImageErrors，因此只能声称“无 basehead 错误、无可见
reporter、桌宠非空”，不能笼统声称“零图片缓存错误”或“AU 素材全部完整”。

## 验证结果

完整 pytest：269 passed。比此前 277 项少的 10 项均属于已退役 basehead 兼容面的专属测试，随后新增了构建门禁和 APK 审计两项 CRLF 回归。

真实构建最初在 AU source gate 被拒绝：当前汉化 Release 的 APK `index.html` 使用 CRLF，而门禁上下文使用 LF，直接原始计数误报 `legacy_switch_contexts=[0,0,0]`。独立验证证明只规范化比较副本的换行后严格计数恢复为 old `[1,1,1]`、new `[0,0,0]`、migration `1/0`。构建门禁和 `tools/au_artifact_check.py` 现只在比较时规范化 CRLF/CR，不写回 HTML，原有非 UTF-8 前后缀无损和真实漂移 fail-closed 测试继续通过。

当前源代码已成功构建 `output/DoL-0.5.10.12-XFox-1.0.8a-au-f-0810.apk`，manifest SHA-256 为 `43706a569efde0c01c6cdfd3bb3f12826da2b30f1fd65a28a5de6e2c7a9fb674`。候选使用本地测试证书 `8c6eb4d6c9c889fa790bc07e0f53c07d714706a7be4fab2313d8fd23b1a0d2ed`，zipalign 与 v1/v2/v3 签名验证通过。AU 产物门禁通过且错误数组为空：switch marker 3、migration marker 1、post-I18N marker 1、blush 层 1 至 5 齐全。

独立 payload 断言确认唯一 Maplebirch `4.1.14` payload，上游 `aO([候选, body fallback])` basehead 表达式恰好一次，pet remount 与 AU face marker 各一次，`aP` / `aI` 直接 basehead 改写均为 0。

候选通过 `adb install -r` 原位覆盖，应用 `firstInstallTime` 保持 `2026-08-10 14:27:08`，没有清 profile。MuMu 12 冷首开真实点击“角色创建 *”后：约 0.762 秒出现一次内部 `img/face/default/base-head.png` 错误，约 1.145 秒挂载 0 像素 canvas，约 1.661 秒缓存 `img/body/base-head.png`，最终 17587/17588 像素，全程无可见错误红框。八种真实脸型链接 8/8 都形成合法仪态、解析到 body fallback、无抛错、无 basehead 错误且无可见 reporter，桌宠 17587 至 17625 像素；独立读取完整 ImageErrors 时仍能看到部分合法路径的 eyes/mouth 请求，不能概括为零图片错误。点击真实“(1) 开始游戏！”后从 Start 进入 Start2，旧 StoryFooter 容器已脱离，新活容器自动重挂 256×256、17588 像素 canvas，无可见错误。

`python -m compileall -q lyra tests tools`、`config/mods.lock.json` JSON 解析、Quick Check 与 `git diff --check` 均通过。Maplebirch 状态已提升为 `runtime-smoke-passed`。准确边界仍是：只验证了本地测试签名 AU-F；正式签名、base/AU-M/AU-A、长期旧存档迁移和全功能遍历未覆盖。

## 文档与历史边界

`CHANGELOG.md` 的 Unreleased 已新增 Removed 结论并保留 81 条回归作为退役依据。`README.md` 当前升级说明已改为只保留两个补丁。`config/mods.lock.json` 已新增 2026-08-10 的 A/B 证据，并把 2026-08-09 的动态解析修法标记为已被退役决策取代。

0808 Release 说明只回写了 AU 换脸的根因分类：保留已发布的 v4.1.13 版本、当时测试范围和结果，
但把“桌宠没更新”修正为“桌宠刷新了非法 variant，预览与桌宠 fallback 不同”。没有用 v4.1.14
证据替换 0808 的版本身份或冒充当时已完成的测试。

## 工作区边界

工作区另有 `.gitignore`、`.vscode/settings.json`、`tests/test_download_latest_build.py` 和 `tools/browser_smoke_test.py` 等既有改动。本轮没有修改或回退它们。提交前必须按文件审阅，只暂存本轮 basehead 退役相关改动，除非用户另有指示。

## 下一步

本轮技术验证已经完成。提交前按文件审阅工作区，只暂存本轮退役 basehead、CRLF 门禁和事实文档相关改动，不混入既有的编辑器/下载工具改动。提交并推送后应让 CI 构建 base + AU-F 两种格式并运行 AU 产物门禁；若准备发版，再补正式签名候选与全四码构建证据。长期 0808 存档迁移和其余体型真机验证仍是可选的后续覆盖，不应在完成前声称通过。
