# DOL-X 与 DoL-Lyra 差异摘要

本文只记录当前需要长期维护的差异。历史试验、失败候选与调研细节放在 CHANGELOG、带日期状态文档
或本地归档，不在这里展开。

## 项目身份

| 项目 | DoL-Lyra | DOL-X |
|---|---|---|
| 产物身份 | Lyra | XFox |
| APK 名称 | DoL Lyra | DoL XFox |
| APK 包名 | `com.vrelnir.dol.lyra` | `com.vrelnir.dol.xfox` |
| 直接上游 | 汉化仓库 | DoL-Lyra/Lyra + 汉化仓库 |

身份差异集中在 `config/build.toml`，不写死在通用构建函数中。

## 构建矩阵

DOL-X 本地矩阵是 base/AU-F/AU-M/AU-A 四码，统一使用 UCB、maplebirch、Cheat Extended 和项目选择的
功能 mod。矩阵由 `config/combinations.toml` 精确控制，不跟随 Lyra 推荐组合变化。

分支推送构建 base + AU-F，tag 发版构建全部四码。

## 当前框架栈

- maplebirch `4.1.13`
- Cheat Extended `1.20(dev260719)` Pre-release
- LongerCombat `1.0.1`
- YanlingCheatCollection `1.0.1`
- Legacy-Art-Mods-Compat `1.0.3-plusV1.1`

旧 maplebirchEx `1.2.4` 和本地 `maplebirch-v3-layer-compat` 不进入 4.x 构建。版本、digest 和验证状态
由 `config/mods.lock.json` 负责。

## 通用代码差异

| 文件 | DOL-X 差异 | 维护原则 |
|---|---|---|
| `lyra/config_loader.py` | 每个 mod 可声明 `include_prerelease_updates` | 默认 false，旧配置行为不变 |
| `lyra/downloader.py` | GitHub API 可使用 `GITHUB_TOKEN`/`GH_TOKEN` | 无 token 时保持匿名请求 |
| `lyra/build.py` | 4.x 不再注入 v3 图层兼容 mod；按兼容登记对固定第三方 payload 应用 fail-closed 补丁 | base 与无关组合保持原行为；来源版本、精确 owner、测试和移除条件集中登记 |
| `lyra/compatibility.py` | 登记 DOL-X 的第三方兼容面、来源版本、失败策略和移除条件 | 上游或资产漂移时停止构建，不用静默 fallback 伪装兼容 |
| `tools/au_artifact_check.py` | 对 AU ZIP/APK 检查资源层和汉化后换脸补丁 | 保留 ModI18N 原始输入；补丁缺失、错位、重复或旧预汉化补丁残留均拒绝产物 |
| `tools/check_mod_updates.py` | 支持 Pre-release 和 asset digest | 项目更新策略留在 tools，不扩散进核心 |
| `tools/quick_check.py` | 使用 `requests` 检查 Release URL | 显式跟随重定向，不静默镜像 fallback |

AU 换脸兼容只对 AU-F/AU-M/AU-A 生效。它复用 Maplebirch `modifyFaceStyle()` 的汉化后 Passage
执行载体，不修改 ModI18N 的原始 HTML。已知的 DoL 原始字节上下文或 Maplebirch 插入点漂移会在
构建期明确失败；未知的翻译行为变化仍需由 CI 产物检查与运行时 smoke 发现，不能把静态门禁写成
对所有未来汉化变化的证明。
如果 DoL 改为选择脸型已注册的合法仪态，或三个 AU model 都为每个脸型提供真实 `default` 仪态，
三个实时选择替换应删除而不是继续叠加；旧存档迁移则需保留到会产生非法组合的历史 DOL-X 版本
退出支持的存档升级窗口。

## 工作流差异

- `build.yaml` 使用 XFox 身份、签名 secret 和双档构建矩阵。
- tag 构建才创建 Release；普通分支构建只保留 Actions artifact。
- `mod-update-check.yml` 每周检查作者官方 Release。

## 文档与支持边界

DOL-X 对自身打包和自有集成负责。复现问题时应先用汉化官方包或原版确认 owner；整合包问题不得直接
转嫁给汉化组、Lyra 或 mod 作者。当前事实入口是 `docs/CURRENT_PROJECT_STATE.md`。
