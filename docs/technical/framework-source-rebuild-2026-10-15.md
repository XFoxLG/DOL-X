# 技术档案：框架历史版本源码重建（2026-10-15）

> 玩家向正文：`docs/release-notes/maplebirch-framework-mirror-v*.md`。
> 本文件只进仓库，不会成为 GitHub Release 正文。

## 起因

框架作者（`MaplebirchLeaf/SCML-DOL-maplebirchFramework`，MIT，Copyright (c) 2026 楓樺葉）
会删除旧 release；34 个源码 tag 由 fork `JohnLiao501/SCML-DOL-maplebirchFramework` 保全，
但该 fork **Releases = 0、树内无任何 zip**，也就是说它只保存了源码。

2026-10-15 的完整可达性盘点（脚本 `.local/_framework_matrix2.py`）结论：

- 上游 release 端点只剩 10 个包：3.1.14 / 4.0.2 / 4.1.14 / 4.2.9 / 4.3.5 / 4.4.1 /
  5.0.4 / 5.1.3 / 5.4.2 / 5.4.3；
- 上游 CI 的 45 个未过期 artifact 已全部抢救到 `.local/framework-artifacts-archive/`
  （`manifest.json` 记录 artifact id / 时间 / sha256，抽样与 release digest 一致），
  覆盖 4.1.2、4.1.14、4.2.0–4.2.9、4.3.1、4.3.3–4.3.5、4.4.0–4.4.1、5.0.0–5.4.3；
- **14 个版本没有任何可用包**（上游 release 无、CI artifact 无、本机无、镜像无）：
  3.1.8 / 3.1.9 / 3.1.10 / 3.1.11 / 3.1.13 / 4.1.0 / 4.1.6 / 4.1.7 / 4.1.8 / 4.1.9 /
  4.1.10 / 4.1.12 / 4.3.0 / 4.3.2。

其中 4.1.7 有一份本机副本（`E:\projects\DoL-XFox\.mods\maplebirch-0.5.8.10-v4.1.7.mod.zip`），
但它**不是官方原件**：`boot.json` 的 GameVersion 下限写成 `>=0.5.8.10`，而该 tag 源码声明
`>=0.5.10.11`，属于被改过的第三方重打包，因此不计入可达性。

## 结论：可以按官方配方重建，且能验证到逐字节一致

作者的 release workflow（`.github/workflows/release.yml`，tag `maplebirch-release-v*` 触发）是：

```text
setup-bun(latest) → bun install → bun run build:all → upload package/*.zip
```

把这套流程搬到本机、并消除两处“环境指纹”之后，**我们手上仍有官方原件的四个版本全部
复现到逐字节一致**：

| 版本 | 官方原件 sha256 | 本机重建 sha256 | 结果 |
|---|---|---|---|
| 4.1.13 | `f5161eed8a4828baac8d7667ad4311fa214f02855c32c190ac1087902e9be955` | 同左 | ✅ 逐字节一致（186010 B） |
| 4.1.14 | `e44c9aeda62e8cf9cf76a85907c55b8b651541bccb8c6da0ee1b4eda965923a4` | 同左 | ✅ 逐字节一致（186903 B） |
| 4.2.9 | `0063defa94b57ea0fa05e503ec956d8ad8ecc5eafa7b884f3dca737fc83f5975` | 同左 | ✅ 逐字节一致（180036 B） |
| 4.3.5 | `67a59bc841441ded0713769fd3dba9e73d19d15f19e9e6d271ee91c4d7b85e93` | 同左 | ✅ 逐字节一致（179769 B） |

四个对照横跨 2026-07-01 → 2026-09-14（rspack 时代 → rolldown 时代），说明配方在整个
4.x 范围成立；而本次要补的 14 个版本全部落在这个范围内。

### 配方（脚本 `.local/build_framework_from_source.py`）

1. **LF 检出**：`core.autocrlf=false`。CI 跑在 ubuntu-latest，检出是 LF；Windows 默认
   检出成 CRLF 会让字符串字面量里混进 `\r\n`，而压缩器的变量命名表是按字符频率排的，
   于是**整个 bundle 的变量名一起漂移**、体积差 4 KB。这是最隐蔽的一条。
2. `bun install --frozen-lockfile`：tag 内 `bun.lock` 把依赖钉死（154 包，
   `@rspack/core 2.0.8` / `tsup 8.5.1` / `typescript 6.0.3` / `adm-zip 0.5.17`）。
3. **冻结 `lastUpdate`**：`scripts/prep.ts` 会把当天日期写进 `package.json`，
   再由 `src/core.ts` 嵌进产物（`"q8":"YYYY.MM.DD"`）。跳过 `prep`、用官方构建当天的
   日期重新执行 `build` → `types` → `package`。
4. **归一化 zip 容器**：
   - 每个条目的 DOS 时间戳 = 官方构建那一刻（本机 adm-zip 写的是当前时间）；
   - 中央目录 `version made by` 的宿主字节 = UNIX（`0x03`）；Windows 上是 `0x0a`。
     这是整包 sha256 与官方原件唯一剩下的差异（4 个条目各 1 字节）。

用 `4.1.13` 验证时，前三步完成后四个条目的**未压缩字节与压缩后字节全部相同**
（`README.md` / `boot.json` / `inject_early.js` / `maplebirch.d.ts`），只剩容器时间戳与
宿主字节；补上第 4 步后整包 sha256 与官方原件一致。

### 关键核对手段

- 条目级比对：`.local/_cmp_zip.py`（窗口化字节 diff，避免对 500 KB 压缩产物做 O(n²) 对比）；
- 语法级比对：`.local/_canon_ast.mjs`（用 TypeScript 解析器把两份 bundle 规范化为
  “变量名无关”的语法树再比对，用来确认差异只是重命名，而不是代码内容不同）；
- 容器字段：`.local/_zip_headers.py`（逐字段打印 local header / central directory）；
- 时间线标定：`.local/_artifact_lag.py`（用仍有原件的版本量出「zip 写盘时刻 − CI 运行时刻」，
  样本为 −4…−1 秒；据此推算缺失版本的时间戳，误差约 ±10 秒内）。

## 本次重建的 14 个镜像

全部来自 fork 保全的源码 tag，构建日期取官方 CI 当天的 UTC 日期；带“官方 CI”一列的版本
说明**官方当年确实产出过包**（release 已删 / artifact 已过期），时间戳按该次运行的开始
时刻 + 25 秒推算：

| 版本 | 字节数 | sha256 | GameVersion 下限 | 官方 CI |
|---|---|---|---|---|
| 3.1.8 | 148487 | `593e87a48c86098bc9b670555b35ce44040d3a5a8b965f245be991f992c0cf88` | >=0.5.8.9 | 无记录 |
| 3.1.9 | 151381 | `013eff21b553aae25acc0b6662e0afd4befb047aa2defd98c070a415e0492862` | >=0.5.8.9 | 无记录 |
| 3.1.10 | 164270 | `c6effdb240641d0f933ede79ee8c4f744cb7e72e4e61f094c165419f812dd890` | >=0.5.8.10 | 无记录 |
| 3.1.11 | 164303 | `06d8a849ee259e58826b7f22e3c2a5904715128af6f4183e73c49985d9bd9dfa` | >=0.5.8.10 | 无记录 |
| 3.1.13 | 165706 | `1061048d46bc0f02eca8532c487a5ee23041c718377788ab3d664ac326207b57` | >=0.5.8.10 | 无记录 |
| 4.1.0 | 179347 | `0b700f85ae4f8bf741ac5b610069c630bfdc27d39e5685498c7444b2034c03b3` | >=0.5.10.8 | 2026-06-10 ✅ |
| 4.1.6 | 185391 | `19988a2d128f13c34caef703630828e043ce62dbff9e9c6764e9f84c95be56c1` | >=0.5.10.11 | 2026-06-13 ✅ |
| 4.1.7 | 185389 | `583e98f5a49e16ed2ab90b0219a4464b6c23941110884aedd4731acb2e79e157` | >=0.5.10.11 | 2026-06-14 ✅ |
| 4.1.8 | 186416 | `39d2a303f7acdf2c901dfb29eccb6704b767cc378e14bd3c12d8d40cef0b9dd3` | >=0.5.10.12 | 2026-06-18 ✅ |
| 4.1.9 | 185703 | `3a56d67baaca0c54693668b99bbaeba7c9cf9a522ee54550be71443e117f64c3` | >=0.5.10.12 | 2026-06-23 ✅ |
| 4.1.10 | 185699 | `579b1afb6148da698a098d5a26ed3cf6f80c98d67363909a487b737f686b2965` | >=0.5.10.12 | 2026-06-24 ✅ |
| 4.1.12 | 185831 | `f7f33b73fb2e5c2dc9ab7b089cfa9fc0211397edf1dd87fee3691cd5bf1b0b05` | >=0.5.10.12 | 2026-07-01 ✅ |
| 4.3.0 | 174343 | `26dab71167df0b342fb04ebebe00dcc35f1c362c3d8d891227e4b4ce9acad53a` | >=0.5.12.11 | 2026-09-12 ❌ 失败 |
| 4.3.2 | 176506 | `8665496f30e36a33d838e85737526967bdd89473e0ba13fbc0c1b75a9d105f62` | >=0.5.12.11 | 2026-09-13 ❌ 失败 |

两处必须写明的边界：

- **4.3.0 / 4.3.2 官方从未发布过包**。两次 CI 都在 `Verify framework and generated types`
  步骤失败（构建成功、校验失败），因此上传与 release 步骤被跳过。这里给的是按源码重建的
  版本，玩家向说明里已如实标注「不是当年的官方产物」。
- **3.1.x 在 GitHub 上查不到任何该 tag 的构建记录**（工作流可能当年还不存在，也可能被删除），
  因此它们的压缩包时间戳就是本次重建的真实时间，不做伪装。

### 一致性校验

`.local/verify_framework_mirrors.py` 对 17 个产物（14 个缺失版本 + 4 个对照中的 3 个重建）逐个检查：

- `boot.json` 可解析，`version` 与 tag 一致（4.1.x 的四个条目：`boot.json`、
  `dist/inject_early.js`、`dist/maplebirch.d.ts`、`README.md`；3.1.x 是另一套布局，
  含 `translations/*.yaml`、`styles/*.css`，由各 tag 自己的打包脚本产生）；
- GameVersion 下限与该 tag 的 `package.json` 声明逐字一致；
- 内嵌 JS 通过 `node --check` 语法检查；
- sha256 与构建记录一致。

## 仍未解决的边界

- 6 个「官方确实产出过、但现在拿不到原件」的版本（4.1.0 / 4.1.6 / 4.1.7 / 4.1.8 /
  4.1.9 / 4.1.10 / 4.1.12，共 7 个）只能靠源码重建，**无法与当年那份文件逐字节对照**；
  逐字节能力是用 4.1.13 / 4.1.14 / 4.2.9 / 4.3.5 四个对照版本证明的。
- 本机 `E:\projects\DoL-XFox\.mods\framework.maplebirch-4.1.11.mod.zip`（版本 4.1.11，
  下限 `>=0.5.10.12`）与上游 CI 抢救件互为印证，无需重建。
- 更早的 3.0.x / 2.x 系列：fork 只保全到 3.1.8 为止，更早的 tag 连源码都已不存在，
  不在本次范围。

## 复现命令

```powershell
# 单个版本（以 4.1.9 为例；日期与时间戳取官方 CI 运行时刻）
python .local/build_framework_from_source.py 4.1.9 --last-update 2026.06.23 `
    --zip-mtime "2026-06-23 13:02:41"

# 批量（本次 14 个版本的日期表写在脚本顶部）
python .local/build_framework_batch.py

# 校验
python .local/verify_framework_mirrors.py
```

产物落在 `.local/framework-source-mirrors/v<版本>/`，随后上传为
`maplebirch-framework-mirror-v<版本>` 的 Release 附件（该 tag 前缀已被 build workflow
的 `!*-mirror-*` 排除，不会触发构建）。
