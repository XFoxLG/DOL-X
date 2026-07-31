# DOL-X 上游友好策略

DOL-X 的直接构建上游是 [DoL-Lyra/Lyra](https://github.com/DoL-Lyra/Lyra)。上游友好不等于
逐文件保持相同，也不等于把 DOL-X 的自用矩阵推回上游；它要求差异有明确 owner、尽量配置化、能被
审计和安全同步。

## 1. 同步方向与基线

- 同步方向固定为 `DoL-Lyra/Lyra -> DOL-X`。
- 核对前先读取 `upstream/HEAD`；当前指向 `upstream/vega`，不能默认用 `upstream/main`。
- 游戏和汉化升级是主要同步触发器；上游构建修复和安全修复可提前同步。
- 每次同步前保留可回滚分支或 tag，并确认工作区不含私有/版权受限内容。

## 2. DOL-X 自治范围

以下内容由 DOL-X 自己负责，不应伪装成 Lyra 默认方案：

- `config/build.toml` 中的 XFox 身份、APK 包名、第三方 mod 和下载源。
- `config/combinations.toml` 的 build codes 与推荐矩阵。
- `config/mods.lock.json` 的验收状态、digest 和回滚记录。
- 兼容补丁、更新检查策略、DOL-X 文档和测试。
- GitHub Actions 的公开分发边界。

## 3. 核心代码边界

- 优先通过 TOML 配置表达差异，不在 `lyra/` 中硬编码项目身份或 mod 矩阵。
- 必须修改 `lyra/` 时，改动应通用、默认向后兼容，并有聚焦测试。
- 项目专属策略优先放在 `tools/`、配置或独立兼容 mod；不把 XFox 的选择变成上游行为。
- 第三方 mod 的运行时兼容优先使用其公开 hook/API；避免解密、拆包重分发或直接 patch 上游核心。

## 4. 来源与供应链

- 日常下载优先作者官方 Release；DOL-X 镜像只作明确标注的人工灾备。
- 锁文件同时记录 tag、asset 名、SHA-256、目标 DoL 版本和实际验证层级。
- Pre-release 或固定 tag 原位换包必须比较 asset digest，不能只比较 tag 字符串。
- 下载失败应 fail closed；不得静默切到陈旧镜像并生成看似成功的残缺包。

## 5. 公共与私有边界

- 第三方资产进入公开 `vega` 前必须确认许可证或取得明确转载授权。
- AU 作者 README 明确禁止二传和拆包；公开 Actions 当前只构建 base。AU 三码仅保留本地自构建能力，
  获得作者明确授权前不上传 artifact/Release。
- 原始 Discord/贴吧抓取、下载缓存和一次性分析脚本不进入主线；提炼后的结论必须标注来源与验证层级。

## 6. 同步验收

每次同步或主线迁移至少完成：

1. `git diff upstream/vega...HEAD` 审阅核心差异。
2. `python -m pytest tests -q`。
3. `python tools/quick_check.py`。
4. `python -m compileall -q lyra tools scripts main.py`。
5. 真实 GitHub Actions base 构建及产物检查。
6. 对涉及运行时的 mod 做浏览器/模拟器 smoke，并把“已挂载”“抽样通过”“全功能通过”分开记录。

详细的当前差异见 [UPSTREAM_DIFF_SUMMARY.md](UPSTREAM_DIFF_SUMMARY.md)，操作清单见
[UPSTREAM_SYNC_CHECKLIST.md](UPSTREAM_SYNC_CHECKLIST.md)。
