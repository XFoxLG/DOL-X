# DOL-X 与 DoL-Lyra 的维护差异

直接构建上游是 [DoL-Lyra/Lyra](https://github.com/DoL-Lyra/Lyra)。保留上游根目录、`lyra/`、`config/`、`scripts/` 和工作流位置。

| 范围 | DOL-X 的维护内容 |
|---|---|
| 项目身份 | XFox 名称、APK 包名 `com.vrelnir.dol.xfox` 与既有签名 |
| 构建组合 | 基础版、AU-F、AU-M、AU-A；由 `config/combinations.toml` 定义 |
| 下载与版本 | `config/build.toml` 与锁文件保存来源、版本、附件和校验值 |
| 兼容修复 | 在原有构建阶段处理必要的输入修补；运行时修复归自研兼容模组 |
| 检查工具 | 验证实际模组、依赖、功能、存档与 ZIP/APK 内容 |
| 发布说明 | 正式中文使用说明、版本记录和原作者归属 |

1014 稳定版使用 maplebirch 4.1.14 和作弊拓展 1.20。十一月候选采用 5.6.2 与作弊拓展 1.20.3.1，尚在验收；具体组合与状态见[当前项目状态](docs/CURRENT_PROJECT_STATE.md)。

第三方独立附件按模组归档于 [DOL-X-Mirrors](https://github.com/XFoxLG/DOL-X-Mirrors)。DOL-X 保留整合包构建、兼容源码与维护文档。

同步时比较上游源码、正式发行与预发布，通用构建改动复用原模块；项目选择通过配置表达。操作步骤见[上游同步策略](UPSTREAM_FRIENDLY_STRATEGY.md)。
