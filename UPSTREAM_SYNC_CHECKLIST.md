# DOL-X 上游同步检查清单

直接构建上游为 [DoL-Lyra/Lyra](https://github.com/DoL-Lyra/Lyra)，同步方向为 `DoL-Lyra/Lyra -> DOL-X`。

## 同步前

- 检查当前分支、未提交改动和待推送提交，保存可恢复基线。
- 核对 `upstream/HEAD`、游戏与正式汉化发行、Lyra 正式发行和预发布。
- 比较通用构建模块及工作流；项目身份、模组选择和兼容修复分别核对。
- 按具体游戏版本检查模组附件、依赖和社区已知问题。

## 合并与适配

- 保留上游根目录、`lyra/`、`config/`、`scripts/` 和工作流位置。
- APK 名称、包名、版本组合及下载源通过配置维护。
- 通用修复放在原模块，项目运行时修复归自研兼容模组。
- 同步源码时保留当前稳定组合，版本升级先使用候选配置验证。
- 工作流以实际权限和上传检查为准，核对 ZIP、APK 与 Release 的各自入口。

## 验证

```bash
python -m pytest tests -q
python tools/player_docs_check.py
python tools/mod_audit.py --output-dir output/audit
python tools/au_artifact_check.py output --output output/au-artifact-report.json
```

根据改动运行对应检查。完整游戏验证覆盖加载、显示、实际操作、存读档与产物；共享逻辑涉及旧组合时覆盖回退版本。

检查文件名、实际内嵌模组、签名和版本说明。候选通过必要验收后，公开发布与默认版本切换分别执行。

当前版本见[项目状态](docs/CURRENT_PROJECT_STATE.md)，维护范围见[上游差异](UPSTREAM_DIFF_SUMMARY.md)。
