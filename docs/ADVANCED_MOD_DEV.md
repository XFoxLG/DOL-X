# 高级 Mod 开发指南

本文档介绍 DOL-X 项目的高级 Mod 开发技术和工具。

---

## TypeScript Mod 开发

DOL-X 提供官方 TypeScript 开发模板，支持现代化工具链：

- **仓库**: https://github.com/XFoxLG/DOL-X-TS-Mod-Template
- **构建工具**: Rspack（Rust 实现的高速 Webpack）
- **开发体验**: 热重载 + 类型安全

### 快速开始

```bash
# Clone 模板
gh repo clone XFoxLG/DOL-X-TS-Mod-Template my-ts-mod
cd my-ts-mod

# 安装依赖
pnpm install

# 启动开发服务器
pnpm dev  # http://localhost:5678
```

### 功能特性

- **自动 boot.json 生成**: 从 package.json 自动提取 name 和 version
- **多 scriptFileList 分类**: 支持 preload / earlyload / inject_early 等多种加载时机
- **材质替换**: originImage/ 目录下自动处理图片替换
- **Mod 加密**: 通过 config/crypto.ts 配置加密选项
- **完整的 TypeScript 类型检查**: 开发时即发现类型错误

### 项目结构

```
my-ts-mod/
├── src/
│   ├── scriptFileList/          # 普通脚本
│   ├── scriptFileList_preload/  # 预加载脚本
│   ├── styleFileList/           # CSS 样式
│   ├── tweeFileList/            # Twee 场景
│   ├── imgFileList/             # 图片资源
│   └── addonPlugin/             # 插件配置
├── config/
│   └── crypto.ts                # 加密配置
├── originImage/                 # 材质替换源
├── rspack.config.ts             # 构建配置
└── package.json                 # 项目配置
```

### 构建和打包

```bash
# 开发模式（热重载）
pnpm dev

# 生产构建
pnpm build

# 输出位于 dist/ 目录
```

### 与 Python 工具链的关系

- **Python 工具**（tools/add_mod.py 等）: 用于管理已发布的 Mod
- **TypeScript 模板**: 用于开发复杂的新 Mod
- **DoL-Commit2Mod**: 用于快速验证上游 commit

三者互补，服务不同场景。

---

## Mod 开发最佳实践

### boot.json 规范化

使用 `normalize_boot_json.py` 工具确保 boot.json 符合规范：

```bash
# 检查 boot.json
python tools/normalize_boot_json.py mods/my-mod/boot.json --check

# 自动修复
python tools/normalize_boot_json.py mods/my-mod/boot.json --auto-fix
```

该工具会：
- 自动补全文件列表
- 强制使用 `/` 路径分隔符
- 验证文件存在性
- 排序并去重

### 依赖管理

如果你的 Mod 依赖 ModLoader 框架（如 maplebirch），在 boot.json 中明确声明：

```json
{
  "dependenceInfo": [
    {
      "modName": "ModLoader",
      "version": "^2.0.0"
    }
  ]
}
```

DOL-X 的 Commit2Mod 工具会自动检测并添加框架依赖。

---

## Python 工具链 - Mod 开发助手

DOL-X 提供 3 个 Python 工具简化 Mod 开发流程：

### 1. dev_mod.py - 开发监视器

**作用**: 自动化 Mod 开发流程，监视文件变化并自动打包

**使用场景**: 频繁修改 Mod 代码，避免手动打包

```bash
# 监视 Mod 目录
python tools/dev_mod.py watch workspace/dev_mods/my-mod

# 启用测试模式（自动复制到 ModLoader）
python tools/dev_mod.py watch my-mod --test-mode --modloader-dir /path/to/ModLoader

# 手动打包（不监视）
python tools/dev_mod.py build my-mod
```

**工作流程**:
1. 修改 Mod 代码（.twee, .js, .css）
2. 工具自动检测变更
3. 自动更新 boot.json
4. 自动打包为 .mod.zip
5. [可选] 自动复制到 ModLoader 测试目录

**依赖**: `pip install watchdog`

**状态**: 框架版本，核心功能待完善

---

### 2. plugin_wizard.py - 插件配置向导

**作用**: 交互式生成复杂的 boot.json 插件配置

**使用场景**: 配置 ModLoader 插件（TweeReplacer、ImageLoaderHook 等）

```bash
# 交互式选择插件类型
python tools/plugin_wizard.py

# 直接指定插件类型
python tools/plugin_wizard.py --plugin TweeReplacer

# 合并到现有 boot.json
python tools/plugin_wizard.py --plugin TweeReplacer --output my-mod/boot.json --merge
```

**支持的插件**:
- **TweeReplacer**: 替换 Twee passage 中的文本
- **ReplacePatch**: 游戏运行时替换内容
- **ImageLoaderHook**: 替换图片资源

**示例 - TweeReplacer**:
```bash
$ python tools/plugin_wizard.py --plugin TweeReplacer
Passage 名称: Start
查找字符串: 旧文本
替换字符串: 新文本
✅ 配置已保存到: boot.json
```

生成的配置：
```json
{
  "addonPlugin": [{
    "modName": "ModUtils",
    "addonName": "TweeReplacer",
    "params": [{
      "passage": "Start",
      "findString": "旧文本",
      "replaceString": "新文本"
    }]
  }]
}
```

**状态**: TweeReplacer 已实现，其他插件待完善

---

### 3. normalize_boot_json.py - boot.json 规范化

**作用**: 自动补全文件列表、规范化路径、验证文件存在性

**使用场景**: 确保 boot.json 符合 ModLoader 规范

```bash
# 检查 boot.json
python tools/normalize_boot_json.py mods/my-mod/boot.json --check

# 自动修复
python tools/normalize_boot_json.py mods/my-mod/boot.json --auto-fix

# 批量处理
python tools/normalize_boot_json.py mods/*/boot.json --check
```

**功能**:
- 自动扫描并补全 scriptFileList / tweeFileList / imgFileList / styleFileList
- 强制使用 `/` 路径分隔符（Windows 兼容）
- 验证文件存在性
- 排序并去重

**状态**: 完整实现，可立即使用

---

## 完整的 Mod 开发工作流

### 场景 1: 从零开始开发 Mod

```bash
# 1. 使用 TypeScript 模板（推荐）
gh repo clone XFoxLG/DOL-X-TS-Mod-Template my-mod
cd my-mod
pnpm install
pnpm dev

# 2. 或使用 Python 监视器（简单场景）
mkdir -p workspace/dev_mods/my-mod
cd workspace/dev_mods/my-mod
# 手动创建 boot.json, game/, modules/css/ 等
python tools/dev_mod.py watch . --test-mode
```

### 场景 2: 配置插件

```bash
# 使用向导生成配置
cd my-mod
python tools/plugin_wizard.py --plugin TweeReplacer --merge

# 或手动编辑 boot.json 后规范化
python tools/normalize_boot_json.py boot.json --auto-fix
```

### 场景 3: 发布 Mod

```bash
# 1. 规范化 boot.json
python tools/normalize_boot_json.py boot.json --auto-fix

# 2. 手动打包（如果不用 TypeScript 模板）
python tools/dev_mod.py build .

# 3. 上传到 GitHub Releases
```

---

## 工具对比

| 工具 | 场景 | 复杂度 | 状态 |
|------|------|--------|------|
| **TypeScript 模板** | 复杂 Mod，需要类型检查 | 高 | ✅ 完整 |
| **dev_mod.py** | 简单 Mod，快速迭代 | 中 | ⚠️ 框架 |
| **plugin_wizard.py** | 配置插件 | 低 | ⚠️ 部分实现 |
| **normalize_boot_json.py** | 规范化配置 | 低 | ✅ 完整 |

---

## Python 工具链 - Mod 开发助手

DOL-X 提供 3 个 Python 工具简化 Mod 开发流程：

### 1. dev_mod.py - 开发监视器

**作用**: 自动化 Mod 开发流程，监视文件变化并自动打包

**使用场景**: 频繁修改 Mod 代码，避免手动打包

```bash
# 监视 Mod 目录
python tools/dev_mod.py watch workspace/dev_mods/my-mod

# 启用测试模式（自动复制到 ModLoader）
python tools/dev_mod.py watch my-mod --test-mode --modloader-dir /path/to/ModLoader

# 手动打包（不监视）
python tools/dev_mod.py build my-mod
```

**工作流程**:
1. 修改 Mod 代码（.twee, .js, .css）
2. 工具自动检测变更
3. 自动更新 boot.json
4. 自动打包为 .mod.zip
5. [可选] 自动复制到 ModLoader 测试目录

**依赖**: `pip install watchdog`

**状态**: 框架版本，核心功能待完善

---

### 2. plugin_wizard.py - 插件配置向导

**作用**: 交互式生成复杂的 boot.json 插件配置

**使用场景**: 配置 ModLoader 插件（TweeReplacer、ImageLoaderHook 等）

```bash
# 交互式选择插件类型
python tools/plugin_wizard.py

# 直接指定插件类型
python tools/plugin_wizard.py --plugin TweeReplacer

# 合并到现有 boot.json
python tools/plugin_wizard.py --plugin TweeReplacer --output my-mod/boot.json --merge
```

**支持的插件**:
- **TweeReplacer**: 替换 Twee passage 中的文本
- **ReplacePatch**: 游戏运行时替换内容
- **ImageLoaderHook**: 替换图片资源

**示例 - TweeReplacer**:
```bash
$ python tools/plugin_wizard.py --plugin TweeReplacer
Passage 名称: Start
查找字符串: 旧文本
替换字符串: 新文本
✅ 配置已保存到: boot.json
```

生成的配置：
```json
{
  "addonPlugin": [{
    "modName": "ModUtils",
    "addonName": "TweeReplacer",
    "params": [{
      "passage": "Start",
      "findString": "旧文本",
      "replaceString": "新文本"
    }]
  }]
}
```

**状态**: TweeReplacer 已实现，其他插件待完善

---

### 3. normalize_boot_json.py - boot.json 规范化

**作用**: 自动补全文件列表、规范化路径、验证文件存在性

**使用场景**: 确保 boot.json 符合 ModLoader 规范

```bash
# 检查 boot.json
python tools/normalize_boot_json.py mods/my-mod/boot.json --check

# 自动修复
python tools/normalize_boot_json.py mods/my-mod/boot.json --auto-fix

# 批量处理
python tools/normalize_boot_json.py mods/*/boot.json --check
```

**功能**:
- 自动扫描并补全 scriptFileList / tweeFileList / imgFileList / styleFileList
- 强制使用 `/` 路径分隔符（Windows 兼容）
- 验证文件存在性
- 排序并去重

**状态**: 完整实现，可立即使用

---

## 完整的 Mod 开发工作流

### 场景 1: 从零开始开发 Mod

```bash
# 1. 使用 TypeScript 模板（推荐）
gh repo clone XFoxLG/DOL-X-TS-Mod-Template my-mod
cd my-mod
pnpm install
pnpm dev

# 2. 或使用 Python 监视器（简单场景）
mkdir -p workspace/dev_mods/my-mod
cd workspace/dev_mods/my-mod
# 手动创建 boot.json, game/, modules/css/ 等
python tools/dev_mod.py watch . --test-mode
```

### 场景 2: 配置插件

```bash
# 使用向导生成配置
cd my-mod
python tools/plugin_wizard.py --plugin TweeReplacer --merge

# 或手动编辑 boot.json 后规范化
python tools/normalize_boot_json.py boot.json --auto-fix
```

### 场景 3: 发布 Mod

```bash
# 1. 规范化 boot.json
python tools/normalize_boot_json.py boot.json --auto-fix

# 2. 手动打包（如果不用 TypeScript 模板）
python tools/dev_mod.py build .

# 3. 上传到 GitHub Releases
```

---

## 工具对比

| 工具 | 场景 | 复杂度 | 状态 |
|------|------|--------|------|
| **TypeScript 模板** | 复杂 Mod，需要类型检查 | 高 | ✅ 完整 |
| **dev_mod.py** | 简单 Mod，快速迭代 | 中 | ⚠️ 框架 |
| **plugin_wizard.py** | 配置插件 | 低 | ⚠️ 部分实现 |
| **normalize_boot_json.py** | 规范化配置 | 低 | ✅ 完整 |

---

## 调试技巧

### 浏览器开发者工具

1. 启动开发服务器: `pnpm dev`
2. 打开浏览器: http://localhost:5678
3. 按 F12 打开开发者工具
4. 在 Console 中查看 Mod 加载日志

### 常见问题

**Q: boot.json 文件列表不完整？**
A: 使用 `python tools/normalize_boot_json.py --auto-fix` 自动补全

**Q: 材质替换不生效？**
A: 检查 originImage/ 目录结构是否正确，路径必须与游戏原始路径一致

**Q: TypeScript 编译错误？**
A: 检查 tsconfig.json 配置，确保类型定义正确

---

## 相关资源

- [DOL-X 主仓库](https://github.com/XFoxLG/DOL-X)
- [TypeScript 模板](https://github.com/XFoxLG/DOL-X-TS-Mod-Template)
- [ModLoader 文档](MODLOADER_OVERVIEW.md)
- [Commit2Mod 使用指南](COMMIT2MOD_USAGE.md)
