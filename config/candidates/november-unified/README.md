# 2026-11 中文统一候选配置

本目录通过现有 `--config-dir` 入口选择，默认配置继续服务现行稳定版。
目标为正式中文 0.5.12.13-chs-1.0.1a、MapleBirch 5.6.2、原作作弊拓展 1.20.3.1，
以及基础 / AU-F / AU-M / AU-A 四种外观。AU 面部扩展为 1.2.16，图片包分别保留 0.9.3 / 0.4.2 / 0.1.1。

AU 面部扩展原始附件使用本目录 `inputs/AUsDoL-facial-expansion-v1.2.16.zip`。该附件不随 Git 源码发布，
需在本地构建环境中放入同名文件；构建前按 `mods.lock.json` 校验。
归档附件来源：
<https://discord.com/channels/1103864219620884560/1368992933243654164/1566065993858682990>。
构建不依赖会过期的 Discord 附件 URL，文件摘要由本目录 `mods.lock.json` 校验。
三种模型图片包通过作者的 `mod` 发布获取，并核对既有摘要。
AU 模型与面部扩展按作者原说明使用；相关原附件与 AU 成品不在本仓库分发，
运行验收按作者说明进行。公共构建所需输入均在构建时提供。
来源与使用说明见 [分发政策](../../../docs/DISTRIBUTION_POLICY.md)。

复现继续使用项目原有命令与缓存：

```powershell
python main.py --config-dir config/candidates/november-unified warmup --workspace <已有候选缓存> --codes 15704320,15705344,15706368,15708416
foreach ($code in '15704320','15705344','15706368','15708416') {
  python main.py --config-dir config/candidates/november-unified build zip --workspace <已有候选缓存> --tag v0.5.12.13-1.0.1a-1109 --codes $code -j 1
  if ($LASTEXITCODE -ne 0) { throw "ZIP 构建失败：$code" }
}
foreach ($code in '15704320','15705344','15706368','15708416') {
  python main.py --config-dir config/candidates/november-unified build apk --workspace <已有候选缓存> --tag v0.5.12.13-1.0.1a-1109 --codes $code -j 1
  if ($LASTEXITCODE -ne 0) { throw "APK 构建失败：$code" }
}
```

正式中文底包与构建工具沿用本次候选缓存中的既有 prepare 结果。完整输入来源、实际构建命令、
逐包清单和运行证据随本地交付保留；不得用未经确认的自动翻译 nightly 替代底包。
并行执行浏览器与大包构建会占用大量内存，复现时按包串行执行，每包使用独立命令。

枯木逢春已含更长遭遇战，因此独立 LongerCombat 与旧言灵拆分包均禁用。
CE Modernization、Legacy Plus V3、Renderer Mask Compat 均不自动纳入。
本配置是测试候选，公开发布与默认切换需要独立验收决定。
