# 会话状态 2026-07-14

承接 [`SESSION_STATUS_2026-07-03-cleanup.md`](SESSION_STATUS_2026-07-03-cleanup.md)。
本次是一轮文档正确性与玩家可读性的整理，没有改动构建逻辑或版本锁定。

## 一句话现状

把散落在配置注释、当前状态文档和工具活代码里的过时数值全部回源核对并改准（旧 build code
系列、cheat v1.17、NeoUI 禁用等口径），CHANGELOG 规范化为 Keep a Changelog 格式，
README 做了一轮面向玩家的全面优化。全程只改文档和文档性代码，测试 180 全过，已推送 vega。

## 本次做了什么（三个提交）

第一个提交：CHANGELOG 重构为 Keep a Changelog 1.1.0 格式。文件头加了诚实的版本号说明
（DOL-X 用复合格式，不是严格 SemVer）；合并了重复的 Unreleased 区块，把已随 0713 上线的
DOLI 集成、fork 清理等内容按真实日期归入发布条目；底部示例矩阵修正为真实的 15704320 系列。
历史发布条目按 Keep a Changelog 铁律原样保留（包括当时真实的 cheat v1.17）。

第二个提交：跨文件修正当前状态口径。回源核对 combinations.toml / features.toml /
mods.lock.json 后，把描述当前状态却写错的地方全部改准——tests、tools、AGENTS_FULL、
MOD_COMPATIBILITY_MATRIX、TESTING_GUIDE、README 里的旧 build code 统一到 15704320 系列；
tools/download_latest_build.py 里两处活代码默认值（不带参数时用的旧码）也修了，这是真 bug；
cheat extended 在描述当前锁定版本处 v1.17 改 v1.18；NeoUI 从"禁用/仅对比包"改为"07-05 起
全部内置"。带日期的历史日志原样保留。

第三个提交：README 面向玩家全面优化。目录拆成"玩家看这里 / 开发者看这里"两栏；新建
"包含哪些 Mod"表格章节，让 base 基础版内置的每个 mod 及其作用一目了然，下载表格加了跳转
链接；下载说明改成大白话（ZIP=电脑、APK=手机，4 个版本只差体型模型）；把开发黑话
（build code 数字、back-port、srcfn、feature bit、vega/B 线）从玩家正文移到末尾的开发者指南；
修了一个原本就坏的目录锚点。

## 关于别的模型做的审计报告

用户在另一会话用其它模型对本项目做了全项目审计，产物是 canvas + `DOL-X_FULL_AUDIT_2026-07-14.md`。
本次逐条回源核对了它引用的关键点，结论如下。

审计的 11 条发现里，10 条属实、非过度设计：锁文件 last_tested_sha256 全为 null、CI 构建前
不跑测试、build job 顶层持有 contents:write、upload overwrite:true、actions 用浮动版本标签、
requirements.txt 全是开放约束、verify_docs_structure.py 强制要求已被忽略的 AGENTS.md 且
Windows GBK 下会崩——这些都核实为真。但要点是：这是自用整合包，审计用的是企业级供应链标准，
这些 P0/P1 对自用项目属于加分项而非救命项，审计自己也判定 0713 不用撤回，不紧急。

审计的 Low-2（建议 pytest.ini 加 lyra/tests）经裏取り为误报，本次没照做：默认 pytest 和
显式 tests lyra/tests 收集的都是同样 180 个测试，且 lyra/tests/test_github_release.py 根本
不是 pytest 测试而是手动跑 GitHub API 的脚本（无 test_ 函数、收集 0 项），加进 testpaths
反而有害。这是本次避开的一个有害改动。

审计报告文件本身不提交 git：它是针对某个提交的一次性时间切片，会随代码变化过时，且是外部
模型产物、带 GBK 乱码。价值在于读一次决定做不做，读完使命完成。留在工作区当草稿或删除均可。

## 未做、留待将来的事

审计列出的真实工程债（锁文件哈希校验、CI 测试门禁、build job 最小权限、下载原子写入）都属实，
用户认可但判定不紧急，本次未动。将来若要做，应逐条讲清取舍和风险再动手，尤其改 build.yaml
有真实出包风险，不该顺手夹带。

## 当前口径（不变，仅重申）

vega 稳定线 build code 仍是 15704320 系列 4 个包（base + AU-F/M/A），全部内置 NeoUI 和 DOLI。
cheat extended 当前锁 v1.18（自建镜像，07-05 重打包）。maplebirch v3.1.14 不升。
next-4x 升级线状态见记忆 dual_line_status_20260708，本次未触及。

## 验证

本次每一步改动前后都跑了 `python -m pytest -q`，稳定 180 passed（markdown 文档改动本不影响
测试，但用于确认没误伤代码）。ReadLints 干净。两个工具改动后用 ast.parse 确认语法正常。
README 锚点全部核对与实际标题一致。三个提交均已推送 origin/vega。

## 提交记录（本次三个）

- restructure CHANGELOG to Keep a Changelog 1.1.0, fix stale build codes
- correct stale build codes and cheat/NeoUI status across current-state files
- restructure README for players, add explicit base mod list, de-jargon

## 一个操作纪律教训

第二个提交时用了 git add -A，意外把工作区里未跟踪的审计报告文件一起提交（变成 9 个文件）。
推送前发现并用 reset --soft + restore --staged 剥离，重新提交成干净的 8 个文件才推送。
教训：提交前先看 git status，只明确暂存本次相关文件，不用 git add -A 一把梭。
