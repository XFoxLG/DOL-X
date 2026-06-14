# ModLoader Metadata Extension Proposal

## 当前 boot.json 支持

ModLoader 已支持声明式依赖 `dependenceInfo`：

```json
{
  "name": "cheat extended",
  "version": "1.18",
  "dependenceInfo": [
    {"modName": "ModLoader", "version": "^2.0.0"}
  ]
}
```

## 提议扩展（为未来 Resolver 准备）

### 1. 版本范围约束（semver）

当前 `dependenceInfo` 仅支持简单版本字符串。提议支持 semver 范围：

```json
{
  "dependenceInfo": [
    {
      "modName": "maplebirch",
      "version": ">=3.1.13 <4.0.0"
    }
  ]
}
```

**收益**：
- 明确兼容性范围，避免破坏性更新
- Resolver 可自动选择满足约束的版本

**成本**：
- 需引入 semver parser（如 `packaging` 库）
- Mod 作者需维护版本兼容性矩阵

### 2. 可选依赖

```json
{
  "optionalDependencies": [
    {"modName": "BeautySelectorAddon", "version": "*"}
  ]
}
```

**收益**：
- 区分必需依赖和增强功能依赖
- Resolver 可构建"最小"/"完整"两种组合

**成本**：
- 增加配置复杂度
- 需要明确定义"可选"的语义（缺失时降级？还是禁用特性？）

### 3. 兼容性声明

```json
{
  "compatibility": {
    "DOL": ">=0.5.2.0",
    "conflicts": ["oldCheatMod", "incompatibleFramework"]
  }
}
```

**收益**：
- 早期检测不兼容组合
- Resolver 可在构建期拒绝冲突

**成本**：
- 需要维护全局 Mod 名称注册表
- 冲突检测逻辑复杂（传递冲突？版本相关冲突？）

## 实施决策标准

**触发条件**（满足任一即考虑实施）：
1. 组合数 >20（当前 4）
2. 社区冲突报告 >10 个
3. 手动维护白名单成为瓶颈（每周 >2 次 `combinations.toml` 编辑）

**实施顺序**：
1. **Phase 1**：版本范围约束（最高收益，相对简单）
2. **Phase 2**：兼容性声明（解决实际痛点）
3. **Phase 3**：可选依赖（语义复杂，优先级低）

## 当前不实施的理由

根据 `TECHNICAL_FEASIBILITY_ASSESSMENT_REPORT.md`：
- 当前组合数仅 4，静态白名单足够
- 测试矩阵扩展成本 (×5-10) 远高于当前收益
- Profile 层已提供用户友好的场景抽象
- Resolver 适用于组合爆炸场景，当前不适用

## 参考资料

- [NPM package.json](https://docs.npmjs.com/cli/v9/configuring-npm/package-json#dependencies)
- [Cargo.toml dependencies](https://doc.rust-lang.org/cargo/reference/specifying-dependencies.html)
- [ModLoader dependenceInfo](https://github.com/DoL-Lyra/sugarcube-2-ModLoader)
