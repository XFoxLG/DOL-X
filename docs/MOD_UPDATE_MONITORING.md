# Mod 与上游更新检查

检查器报告两类来源：`config/build.toml` 中启用且允许追踪的安装项，以及
`config/upstream-watch.toml` 中的 Lyra、正式汉化、新内容和 Fork 候选。
观察清单不会安装 Mod，也不会修改构建配置或锁文件。

```bash
python tools/check_mod_updates.py --output output/mod-updates.json --markdown output/mod-updates.md
python tools/check_mod_updates.py --include-prerelease --summary
```

周检在每周日 UTC 00:00（北京时间 08:00）运行，也可通过 Actions 手动触发。
结果写入 Step Summary 和保留 30 天的 `mod-update-report` artifact。
工作流只读，不创建 Issue 或发送邮件。

## 如何理解结果

- **发现变化**：发布标签不同，或同标签资产 SHA-256 与记录不同；仍需重新验证兼容性。
- **未发现版本变化**：只限本次成功检查的来源，不代表所有 Mod 都是最新版。
- **仅标签比较**：没有进行资产字节身份比较，不能排除同标签附件被替换。
- **新版本需重新选择资产**：标签有变化，但旧文件名未在新 Release 命中。
- **主动锁定／已禁用／未配置仓库**：列入跳过项，不能当成检查成功。
- **检查失败**：保留具体仓库和错误；即使其他来源成功，检查仍以退出码 1 结束。

JSON 保留 `updates`、`errors`、`all_results` 等安装项字段，并增加 `skipped`、
`references`、`reference_updates` 和 `check_complete`。`errors` 汇总两类来源的失败，
`total_checked` 与 `updates_available` 仅统计安装项。

退出码约定已由“总是 0”改为：全部检查成功时为 0，任何来源失败时为 1。
失败结果仍先写入报告；配置文件损坏则直接报错，不使用空配置掩盖问题。

## 版本渠道与资产身份

普通安装项默认检查正式 Release；`--include-prerelease` 包含安装项预发布。
单个安装项可设置 `include_prerelease_updates = true`。
观察清单独立使用 `include_prerelease`：Lyra 包含预发布，正式汉化只看正式发行。
候选清单的 `observed_tag` 表示已审阅版本，不表示已经安装或通过运行验收。

固定标签需要同时记录 `asset_pattern` 与 `sha256` 才能比较附件身份。
更新检查只用 GitHub 提供的 digest，不额外下载大包；正式构建仍按锁文件验证实际下载字节。
发布标签、资产名称或依赖有变化后，应在隔离工作区验证，再更新安装配置与验收记录。

## 风险与后续处理

大版本变化或已知不兼容为 high，小版本变化或预发布通常为 medium；风险等级不是兼容认证。
预发布标记不会把大版本风险降为 medium。
候选必须完成准备、预热、构建、产物身份检查与对应运行验收，再考虑替换正式输入。

请求限流时可通过环境变量 `GITHUB_TOKEN` 或 `GH_TOKEN` 提供已有凭据，勿将凭据写入配置。
更多回退操作见 [MOD_UPDATE_ROLLBACK.md](MOD_UPDATE_ROLLBACK.md)。
