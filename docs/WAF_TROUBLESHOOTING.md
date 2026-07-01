# WAF / BYOK 403 排查手册

> 适用：DOL-X 项目通过第三方中转（如 100xlabs.space）以 BYOK 方式调用模型，中转前有 Cloudflare WAF。
> 本文件**不会被自动注入**，仅在需要时被人或 AI 读取（tool-result 通道不触发 WAF），所以可以安全包含命令示例。

## 症状（如何识别这个问题）

- 报错形如：`BYOK request rejected` + `403`一大段 Cloudflare HTML（`Sorry, you have been blocked` / `Attention Required! | Cloudflare`）。
- 关键判据：**只有这个项目会触发，其它项目正常**；甚至**新会话只发“你好”也被拦**。
- 报错 metadata 里可见 `modelId`、`conversationId`，域名指向你的中转站。

## 根因（给人看的解释）

Cursor 每次请求会把**项目级 agent 指令**原样拼进请求体。这些“每次都被自动注入”的内容包括：
根目录 `AGENTS.md`、`.cursor/rules/` 下的规则、`.cursorrules`。

中转前的 Cloudflare WAF 会扫描请求体，按“字段位置 + 累计打分阈值”判定。当被注入的文本里集中出现
**命令/代码/标签类名**（shell 命令、`$(...)` 命令替换、`| grep -E "(...)"` 管道正则、`&&` 命令链、
`<<set $x>` 模板宏、`<script>`/`<html>`、长串 base64、类 SQL 字符串），分数超过阈值就在**到达模型之前**返回 403。

**为什么“读取文件却没事，自动注入就出事”**：读取文件走的是 tool-result 通道，内容被转义、加行号前缀、稀释在大量其它内容里，
落点/打分与“原样注入到指令字段”不同，通常不过阈值。这是基于现象的推断，非中转方规则原文。

**为什么 .cursorignore 修不了**：`.cursorignore` 只能挡“被当普通文件读取”的内容，**挡不住自动注入的 AGENTS.md**。
它的价值在第二层：开发中 agent 去读/搜 `tests/`、`tools/`、`.github/pwa/` 等含 payload 样本的文件时把它们挡在上下文外，降低开发期触发概率。

## AI 自查流程（agent 照此执行）

1. 确认症状：报错含 `BYOK request rejected` 且正文是 Cloudflare 403 页 → 判定为本问题。
2. 定位是否“自动注入内容”触发：让用户把 `AGENTS.md` 临时改名为 `AGENTS.md.bak`，新开会话发“你好”。
   - 能正常回复 → **就是 AGENTS.md 内容触发**，进入第 3 步。
   - 仍 403 → 不是它。改回名字，依次排查 `.cursor/rules/`、`.cursorrules`、以及当时打开的编辑器标签页（也会作为上下文发送）。
3. 修复（不丢信息）：把 `AGENTS.md` 里所有命令/代码块/标签类内容**移到** `docs/AGENTS_FULL.md`，
   `AGENTS.md` 改写为纯文本要点 + 一句“详见 docs/AGENTS_FULL.md”。
4. 验证：新开会话发“你好”，能正常回复即修复成功。同时确认 agent 能正确复述项目事实（DOL-X 是 Python 项目，
   不是 TypeScript——后者是另一个独立项目 DoL-XFox，勿混淆）。

## 预防规则（红线）

- 会被自动注入的文件（`AGENTS.md`、`.cursor/rules/`、`.cursorrules`）**只写纯文本**，禁止命令/代码块/标签/base64/类 SQL。
- 所有命令与代码示例放 `docs/`（如 `docs/AGENTS_FULL.md`），自动注入文件里只留“详见”指引。
- 改完务必“新会话发你好”验证。

## 30 秒定位法（速查）

把 `AGENTS.md` 改名 `.bak` → 新会话发“你好” → 能回就是它（挪代码块到 docs/ 再改回名）；
还拦就查 `.cursor/rules/` 与打开的标签页。

## 治本（可选，强烈建议备用）

中转 WAF 过度敏感属于环境问题，缓解只是“绕雷”。建议在 Settings → Models 备一个官方模型或
另一个不激进的中转作兜底；再遇到一时定位不到的 403，直接切换即可继续工作，不卡住项目。

## 历史记录

- 2026-06-25 首次发生并定位：根目录 `AGENTS.md` 被自动注入，其中 shell 命令/`$()`/`<<set $money>>` 等签名触发
  Cloudflare WAF 403。解决：将完整版归档为 `docs/AGENTS_FULL.md`，`AGENTS.md` 精简为纯文本。新会话“你好”恢复正常。