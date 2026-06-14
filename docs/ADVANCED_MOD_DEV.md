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
