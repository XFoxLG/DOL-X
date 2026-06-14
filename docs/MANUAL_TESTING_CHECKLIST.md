# 手动测试清单

**适用场景**：新 mod 首次添加、重大版本更新、自动测试未覆盖的场景

---

## 基础功能测试（所有 mod）

### 加载验证
- [ ] 游戏正常启动，无白屏
- [ ] ModLoader 加载完成
- [ ] 目标 mod 出现在 Mod 列表
- [ ] Console 无 critical error（警告可接受）

### 核心交互
- [ ] 进入 Orphanage Intro
- [ ] Save/Load 功能正常
- [ ] 基本 UI 响应正常

---

## Mod 特定测试

### Cheat Mods（cheat/cheatExtended）
- [ ] Cheat 菜单可访问
- [ ] Stat 修改生效
- [ ] Time 控制正常
- [ ] 无与其他 mod 的 UI 冲突

### Content Mods（more_love/custom_spellbook）
- [ ] 新增内容可访问
- [ ] Passage 跳转正常
- [ ] 特有功能正常工作

### Framework Mods（maplebirch）
- [ ] 框架 API 可用（检查 console）
- [ ] 依赖此框架的 mod 正常工作
- [ ] 无 Simple Frameworks lookup 错误（或可接受）

### AU Variants
- [ ] AU character 正确显示
- [ ] AU-specific passages 可访问
- [ ] 无 gender-related 错误

---

## 兼容性测试

### Mod 组合
- [ ] 测试与现有 mod 的组合
- [ ] 检查是否有功能重复
- [ ] 检查是否有 UI 覆盖冲突

### 不同 Pack Types
- [ ] ZIP 正常工作
- [ ] APK（如果支持）正常工作

---

## 性能测试

### 加载时间
- [ ] 初始加载 <30 秒
- [ ] Passage 切换流畅

### 内存使用
- [ ] 无明显内存泄漏
- [ ] 长时间游玩稳定

---

## 回归测试

### 已知问题验证
- [ ] 检查 docs/KNOWN_ISSUES.md 中列出的问题
- [ ] 确认 workaround 仍有效

### 向后兼容
- [ ] 旧存档可以加载
- [ ] 旧功能未被破坏

---

## 测试报告模板

```markdown
## Mod 测试报告

**Mod**: [Mod 名称]
**版本**: [版本号]
**测试日期**: [日期]
**测试者**: [测试者]

### 测试结果

- 基础功能：✅/❌
- Mod 特定功能：✅/❌
- 兼容性：✅/❌
- 性能：✅/❌

### 发现的问题

1. [问题描述]
   - 严重程度：Critical/High/Medium/Low
   - 复现步骤：[步骤]
   - 预期行为：[预期]
   - 实际行为：[实际]

### 建议

- [ ] 可以合并到主线
- [ ] 需要修复后再合并
- [ ] 不建议添加此 mod
```

---

## 测试频率

- **首次添加 mod**：完整测试
- **Minor 版本更新**：基础功能 + Mod 特定
- **Major 版本更新**：完整测试
- **框架更新**：完整测试所有依赖 mod
- **游戏版本更新**：基础功能测试所有 mod
