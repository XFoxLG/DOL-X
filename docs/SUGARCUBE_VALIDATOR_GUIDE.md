# SugarCube 静态验证器使用指南

## 概述

SugarCube 静态验证器是一个用于检测 Degrees of Lewdity HTML 构建产物中潜在问题的工具。它可以在构建后快速发现断链、语法错误等问题，无需启动浏览器。

## 功能

- ✅ **Passage 链接完整性检查** - 检测指向不存在 passage 的断链
- ✅ **Macro 语法验证** - 检测未闭合的 macro（如 `<<if>>` 缺少 `<</if>>`）
- ✅ **统计信息** - 报告 passage 数量、链接数量、错误数量
- ✅ **ZIP 支持** - 直接验证 ZIP 包中的 HTML 文件
- ✅ **JSON 报告** - 生成结构化的验证报告

## 安装

无需额外安装，验证器已包含在 DOL-X 项目中。

## 基本用法

### 1. 验证单个 HTML 文件

```bash
python tools/sugarcube_validator.py output/game.html
```

**输出示例**：
```
✓ PASS output/game.html
  Passages: 1234, Links: 5678
  Errors: 0, Warnings: 0
```

### 2. 验证多个文件

```bash
python tools/sugarcube_validator.py output/*.html
```

### 3. 验证 ZIP 包

```bash
python tools/sugarcube_validator.py output/*.zip
```

### 4. 生成 JSON 报告

```bash
python tools/sugarcube_validator.py output/*.html --output validation-report.json
```

### 5. 构建失败时退出（用于 CI）

```bash
python tools/sugarcube_validator.py output/*.html --fail-on-errors
```

**返回状态码**：
- `0` - 所有验证通过
- `1` - 发现错误

### 6. 严格模式（将 warning 视为错误）

```bash
python tools/sugarcube_validator.py output/*.html --strict
```

## 检测的问题类型

### 错误（Errors）

这些问题会导致游戏运行时出错：

| 错误类型 | 描述 | 示例 |
|---------|------|------|
| `broken_link` | 链接指向不存在的 passage | `[[Go to Missing]]` |
| `unclosed_macro` | Macro 未正确闭合 | `<<if $x>>` 缺少 `<</if>>` |
| `no_passages` | HTML 文件中没有任何 passage | - |
| `file_read_error` | 无法读取文件 | - |

### 警告（Warnings）

这些问题可能不影响游戏运行，但需要注意：

| 警告类型 | 描述 |
|---------|------|
| `unexpected_close_macro` | 闭合 macro 没有对应的开始标签 |
| `mismatched_macro` | Macro 不匹配（如 `<<if>>` 对应 `<</for>>`）|

## 报告格式

### JSON 报告结构

```json
{
  "total_targets": 1,
  "successful": 1,
  "failed": 0,
  "results": [
    {
      "target": "output/game.html",
      "success": true,
      "passage_count": 1234,
      "link_count": 5678,
      "error_count": 0,
      "warning_count": 0,
      "stats": {
        "total_passages": 1234,
        "total_links": 5678,
        "broken_links": 0,
        "unclosed_macros": 0
      },
      "issues": []
    }
  ]
}
```

### 问题（Issue）结构

```json
{
  "severity": "error",
  "kind": "broken_link",
  "message": "链接指向不存在的 passage: 'MissingPassage'",
  "passage": "Start",
  "line": null,
  "context": "MissingPassage"
}
```

## 集成到 CI

### GitHub Actions 示例

```yaml
- name: Validate SugarCube HTML
  run: |
    python tools/sugarcube_validator.py \
      output/*.html \
      --output validation-report.json \
      --fail-on-errors
  
- name: Upload validation report
  if: always()
  uses: actions/upload-artifact@v4
  with:
    name: validation-report
    path: validation-report.json
```

## 支持的 SugarCube 语法

### 链接格式

- `[[Passage]]` - 简单链接
- `[[Text|Passage]]` - 带文本的链接
- `<<link "Text" "Passage">>` - Link macro
- `<<button "Text" "Passage">>` - Button macro

### Macro 配对

验证器检测以下需要闭合的 macro：

| 开始 Macro | 闭合 Macro |
|-----------|-----------|
| `<<if>>` | `<</if>>` |
| `<<for>>` | `<</for>>` |
| `<<switch>>` | `<</switch>>` |
| `<<capture>>` | `<</capture>>` |
| `<<nobr>>` | `<</nobr>>` |
| `<<silently>>` | `<</silently>>` |
| `<<widget>>` | `<</widget>>` |

## 限制

### 当前不支持

- ❌ 动态链接验证（如 `<<link "Go" $targetPassage>>`）
- ❌ JavaScript 变量检查
- ❌ 条件链接验证
- ❌ Widget 参数验证

### 假阴性（False Negatives）

验证器可能无法检测：
- 运行时动态生成的链接
- 通过 JavaScript 创建的 passage
- Mod 注入的内容

### 假阳性（False Positives）

验证器可能误报：
- 通过 Mod 动态添加的 passage
- 特殊命名的 passage（包含特殊字符）

**解决方法**: 对于已知的假阳性，可以使用白名单机制（未来功能）。

## 性能

- **速度**: 约 100-200个 passage/秒
- **内存**: < 100MB（典型 HTML 文件）
- **适用场景**: 构建后验证（不适合实时编辑器）

## 故障排除

### 问题：报告大量断链

**可能原因**：
1. Mod 动态添加的 passage 未被识别
2. 条件渲染的链接被误判

**解决**：
- 检查 ModLoader 日志
- 使用浏览器验证实际游戏
- 考虑使用 `--output` 生成详细报告分析

### 问题：Macro 未闭合警告

**可能原因**：
1. 正则表达式未匹配特殊语法
2. HTML 编码问题

**解决**：
- 检查 HTML 源码中的实际 macro 格式
- 报告 Issue 以改进正则表达式

## 贡献

如果发现验证器的 bug 或需要新功能，请：

1. 在 GitHub 创建 Issue
2. 提供示例 HTML 片段
3. 描述预期行为

## 更新日志

### v1.0.0 (2026-06-24)

- ✅ 初始版本
- ✅ Passage 断链检测
- ✅ Macro 语法验证
- ✅ ZIP 文件支持
- ✅ JSON 报告生成
- ✅ 9个单元测试覆盖

---

**相关文档**：
- [Phase 1 测试系统指南](PHASE1_TESTING_GUIDE.md)
- [手动测试清单](MANUAL_TESTING_CHECKLIST.md)
- [AGENTS.md](AGENTS.md)
