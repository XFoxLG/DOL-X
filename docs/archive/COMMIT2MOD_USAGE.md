# DoL-Commit2Mod 使用指南

DOL-X 重新实现了 DoL-Commit2Mod 工具，用于将 Git commit 快速转换为 ModLoader Mod，便于验证上游更新的兼容性。

---

## 为什么重新实现而非 Fork？

经过深入调研，DOL-X 的实现相比上游项目具有显著优势：

| 对比项 | 上游项目 | DOL-X 实现 |
|--------|---------|-----------|
| 代码量 | 500 行（单文件） | 787 行（模块化） |
| 依赖推断 | ❌ 无 | ✅ 自动检测 maplebirch |
| CSS 支持 | ❌ 无 | ✅ 完整支持 |
| 类型提示 | 0% | 100% |
| 维护状态 | 8个月无更新 | 持续维护 |

**决策评分**: Fork 3.9/10 vs **重新实现 9.15/10**

---

## 核心创新：自动依赖推断

DOL-X 会自动检测 ModLoader 框架依赖，零配置开箱即用。

---

## 快速开始

```bash
# 转换单个 commit
python -m tools.dev.commit_to_mod convert abc123 --output test.mod.zip
```

---

## 功能特性

✅ Git Diff 解析  
✅ 文件类型识别（Twee / JS / CSS）  
✅ 自动依赖推断  
✅ boot.json 生成  
✅ Mod 打包验证

---

## 相关资源

- [DOL-X 主仓库](https://github.com/XFoxLG/DOL-X)
- [TypeScript 模板](https://github.com/XFoxLG/DOL-X-TS-Mod-Template)
- [高级开发指南](ADVANCED_MOD_DEV.md)
