# DOL-X 文档写作规范

**最后更新**：2026-10-16

本文规定 DOL-X 各类文档的受众、深度和禁止事项。目的是让同一次改动在不同文档里写不同深度，
而不是互相复制粘贴。

---

## 1. 文档分层

| 文档 | 受众 | 写什么 | 不写什么 |
|------|------|--------|----------|
| `CHANGELOG.md` | 会读 diff 的人 | 根因、机制、证据链、run 号 | 玩家操作指引 |
| `docs/release-notes/<tag>.md` | 下载整合包的玩家 | 装哪个、修了什么、什么没测 | 路径、函数名、版本区间 |
| `玩家更新日志.md` | 所有玩家 | 每个版本玩家能感知的变化（一句话一条） | 技术细节、判定状态、验证数字 |
| `docs/technical/<tag>.md` | 追溯者 / 维护者 | 目标身份、逐字节校验、工具输出、归因 | 面向玩家的措辞（不需要） |
| `docs/CURRENT_PROJECT_STATE.md` | 维护者 | 当前事实的唯一总入口 | 历史沿革 |
| `docs/archive/`、带日期的会话记录 | 追溯者 | 当时的判断与证据 | 事后回填修正 |
| `README.md` | 首次访问的玩家 | 当前稳定版、下载选择、常见问题 | 构建实现细节 |
| `QUICK_REFERENCE.md` | 构建维护者 | 实际可运行的短命令与当前构建码 | 待实现命令、无证据状态 |
| `docs/MOD_COMPATIBILITY_MATRIX.md` | 维护者 | 当前版本、验证层级、已知边界 | 把挂载成功写成全功能通过 |
| `docs/TESTING_GUIDE.md` | 测试者 | 可重复的测试步骤与判定标准 | 一次性会话过程 |

**归档文档里过时的版本号必须原样保留。** 它记录的是「当时我们这么认为」，回填等于篡改历史。
与当前状态冲突时，以 `CURRENT_PROJECT_STATE.md` 和配置文件为准。

### 公开资料与私人记录

GitHub 上的文件、提交说明、历史 diff、标签注释、Release 和 Actions 日志都属于公开资料。
技术文档可以解释兼容行为与验证结果，但不存口令、访问凭据、私钥、解密材料或私人存档。
公开提交说明只描述工程变化，例如「修正文档中的兼容性说明」，不要叙述私人研究过程。

私人研究另存隔离的私有档案。相同提交在不同远端的内容相同，不能依靠私有远端隐藏随后
推到公开远端的历史。真实凭据存于专用密钥存储或本机忽略文件，私有仓库也不代替密钥存储。

提交前运行 `python tools/publication_guard.py --staged --message-file <提交说明文件>`；
推送前检查新增提交范围，包含其中已经被后续提交删除的文件。检查只输出位置与规则，
不打印命中的内容。`python tools/save_safety_guard.py` 继续负责存档和本机路径检查。
发现历史遗留时先确认公开可达范围，再准备单独的历史清理，不以修改当前文件冒充已清除历史。

---

## 2. CHANGELOG 规则

沿用 [Keep a Changelog 1.1.0](https://keepachangelog.com/zh-CN/1.1.0/) 的六分类：
`Added` / `Changed` / `Deprecated` / `Removed` / `Fixed` / `Security`。

版本号格式为 `v{游戏版本}-{整合版本}a-{日期}`，**不是 SemVer**。整合版本部分参照
主.次.修订思路递增：构建体系不兼容改动进主版本、mod 集合新增进次版本、修复类进修订号。

**每个条目必须能追到证据：**

- 外部 mod 升级 → 写作者仓库的 issue 号或 README 依据
- 构建系统改动 → 写 Actions run 号并加链接
- 真机结论 → 写实测日期，并同时写覆盖边界

**禁止的表述**：「应该没问题」「预计正常」「理论上兼容」。没验证就写「未验证」，
不要用推断词掩盖。

**发现旧条目写错时**：在新版本条目里写 `Fixed` 说明纠正，不要偷偷改旧条目。

**CHANGELOG 保持技术向**：run 号、哈希、函数名留在这里没问题；但玩家能感知的变化
必须同时出现在 `docs/release-notes/<tag>.md` 和 `玩家更新日志.md` 里（用玩家语言），
不能只存在于技术条目中。

---

## 3. Release 正文规则

每份 `docs/release-notes/<tag>.md` 固定六段：

1. **本次更新** —— 一句话定性（大版本 / 维护版），加产物件数
2. **问题修复** 或 **主要变化** —— 玩家能感知的改动
3. **版本构成** —— 游戏本体、汉化、框架、核心 mod 列表（附作者仓库链接）
4. **下载说明** —— 哪个文件对应什么，APK/ZIP 区别，存档迁移提示
5. **实测范围** —— 测了什么，**以及没测什么**
6. **已知情况说明** —— 确认为上游机制或超出修复能力的项

### 硬性要求

**第 5 段必须同时写「测了什么」和「没测什么」。** 只写前者等于误导。

**第 6 段每一条必须先确认玩家真能看到。** 从代码或配置里读出来的内部状态，
玩家感觉不到的，不写。判断方法：先问「玩家在游戏里会看到什么」，答不出来就删掉。

**不要把往期已修的问题写进当期正文。** 写之前核对 CHANGELOG 的版本归属，
不要靠记忆。

**如果旧版本存在已知缺陷且仍挂在 Releases 列表上**，要在那个旧版本的正文里写明，
并指向修复版本。有人可能直接从列表里下载旧包。

### 禁止出现的内容

玩家向正文里不写：文件路径、函数名、JSON 键名、框架版本兼容区间、内部数据结构。

| 不要写 | 要写 |
|--------|------|
| `FloatButton.mount()` 硬编码 `sym_awareness.png` | 右下角智能助手图标裂开 |
| `addonPlugin` 声明 `^3.1.0` 覆盖不到 4.1.13 | （删掉，玩家感觉不到） |
| 内层运行时请求旧式 `blushN` 路径 | 可能弹红框提示图片加载失败，点 Clear 消掉 |
| Go+SQLite 与 Cloudflare Worker 自建源码 | 作者没提供公共服务器，需要自己搭 |

技术细节全部留给 CHANGELOG，正文末尾给出链接。

### 机器检查（强制）

`python tools/player_docs_check.py` 扫描 `docs/release-notes/*.md` 与 `玩家更新日志.md`，
命中禁词即失败。发版工作流在「读取 Release 正文」之后调用它，**任何一条命中都会终止发版**。
给检查器新增规则时，必须同时在 `tests/test_player_docs_check.py` 里补正例（必须拦住）
与反例（必须放行）。

```bash
python tools/player_docs_check.py                     # 检查全部玩家向文件
python tools/player_docs_check.py docs/release-notes/<tag>.md   # 只查一份
```

### AU 用词规则（2026-10-15）

**AU（AOKIUTAGE）是一整套大型美化体系：人物模型、服装模型、脸部模型都在里面。**
`【AUsDoL】facial expansion` 只是其中的脸部模型扩展（DLC）；提到它必须写「AU Face」
或「AU Face 脸部扩展」，**不允许简写成「AU」**——简写会让玩家以为 AU 只是一个脸部 mod。

| 不要写 | 要写 |
|--------|------|
| AU 改脸 / AU 面部 | AU Face 脸部扩展（首次出现写全，后文可写 AU Face） |
| AU 的美化素材 | AU 美化体系（人物 / 服装 / 脸部模型），或具体指名 AU Face |

### 禁词表（节选；唯一权威是 `tools/player_docs_check.py` 的规则表）

| 不要写 | 原因 | 要写 |
|--------|------|------|
| `sha256`、哈希串、`130,411,621 字节` | 内部校验信息 | 删掉，放技术档案 |
| `run 38536372032`、`GitHub Actions`、`workflow` | CI 编号与流水线术语 | 「自动构建」 |
| `commit`、7 位以上十六进制串 | 提交标识 | 用 tag 或日期指代 |
| `payload`、`manifest`、`fail-closed`、`needle`、`shim`、`boot.json` | 内部术语 | 玩家能懂的说法 |
| `tools/…`、`lyra/…`、`config/…`、`*.py`、`*.toml`、`*.json` | 仓库路径 | 删掉，或给技术档案链接 |
| `faceStyleSrcFn()`、`$facestyle` 这类源码符号 | 源码标识符 | 界面上的说法（换脸、脸型） |
| `accepted_upstream`、`visual_incomplete`、`A/B` | 内部判定状态 | 「上游机制」「尚未修复」「截图对比」 |
| `pageerror`、`logcat`、`FATAL`、`ANR` | 调试术语 | 「报错」「崩溃」 |

链接可以照常写：检查器只拦正文里的裸路径与术语，不拦 URL。

---

## 4. 验证词汇表

描述验证程度时直接复用 `config/mods.lock.json` 的 `status` 取值，不要另造：

| status | 含义 | 能说 | 不能说 |
|--------|------|------|--------|
| `runtime-validated-base` | 真机全栈零错误零警告 | 已实测通过 | — |
| `runtime-smoke-passed` | 抽样功能可用 | 抽查的功能正常 | 全部功能通过 |
| `runtime-mounted` | 挂载成功，未逐功能遍历 | 已装上并加载成功 | 测试通过 |
| `runtime-empty-state-passed` | 真机只覆盖空列表/空数据状态 | 空态通过 | 完整功能通过 |
| `required-runtime-validated` | 必选组件已在当前栈真机验证 | 当前栈已实测 | 所有组合都上机通过 |
| `enabled-actions-base-validated` | 已进入构建，Actions base 产物验证通过 | CI 产物通过 | 真机通过 |
| `...-pending-runtime` | 已启用但未真机验收 | 尚未上机验证 | 可用 |
| `disabled` | 当前矩阵明确禁用 | 已禁用 | 待验证 |
| 缺少 `status` | 只有版本/摘要记录，没有统一验证结论 | 版本已锁定 | 测试通过 |

**把 `runtime-mounted` 说成「测试通过」是不允许的。**

---

## 5. 每次发版必须同步的清单

- [ ] `CHANGELOG.md` 新增版本条目
- [ ] `docs/release-notes/<tag>.md` 新建（CI 靠它填 Release 正文，缺失会导致发版失败）
- [ ] `docs/technical/<tag>.md` 新建（技术档案：逐字节校验、工具输出、归因；只进仓库）
- [ ] `玩家更新日志.md` 追加该版本条目（只写玩家能感知的变化）
- [ ] `python tools/player_docs_check.py` 本地通过（云端发版工作流会再拦一次）
- [ ] `docs/CURRENT_PROJECT_STATE.md` 的核验日期与版本号
- [ ] `README.md` 的当前稳定版本
- [ ] `config/mods.lock.json` 的 `last_updated`
- [ ] 受影响的专题文档

`tests/test_public_distribution_boundary.py` 会断言 CHANGELOG 最新版本号有对应的
release-notes 文件，漏建会被测试拦下。
