# DoL-Commit2Mod 深度研究报告

**研究时间**: 2026-06-14  
**研究对象**: https://github.com/Lethivia/DoL-Commit2Mod  
**目标**: 理解实现原理，为 DOL-X 集成提供技术基础

---

## 执行摘要

DoL-Commit2Mod 是一个将 Git commit 转换为 DoL ModLoader mod.zip 的 Python 工具。核心功能包括：
1. Git diff 解析（提取新增/修改文件）
2. Twee 文件差异提取（生成 TweeReplacer 参数）
3. JS 文件差异提取（生成 ReplacePatcher 参数）
4. boot.json 自动生成
5. mod.zip 打包

**关键发现**: 实现相对简单（~500 行 Python），适合在 DOL-X 中重新实现。

---

## 1. 核心架构

### 1.1 主要类：`CommitToMod`

```python
class CommitToMod:
    def __init__(self, commit_id=None, mod_name="newmode", mod_version="1"):
        self.commit_id = commit_id
        self.mod_name = mod_name
        self.mod_version = mod_version
        self.twee_replacer_params = []      # Twee 文件替换参数
        self.replace_patcher_params = {"js": []}  # JS 文件替换参数
        self.new_files = []                 # 新增文件列表
        self.modified_files = []            # 修改文件列表
```

---

## 2. Git Diff 解析实现

### 2.1 获取变更文件列表

**关键命令**:
```bash
git diff-tree --no-commit-id --name-status -r <commit_id>
```

**输出示例**:
```
A    game/passages/new_passage.twee    # A = 新增
M    game/passages/old_passage.twee    # M = 修改
D    game/scripts/deprecated.js        # D = 删除（工具忽略）
```

**处理逻辑**:
```python
def get_commit_changes(self):
    result = subprocess.run(
        ["git", "diff-tree", "--no-commit-id", "--name-status", "-r", self.commit_id],
        capture_output=True, text=True, check=True
    )
    
    for line in result.stdout.splitlines():
        parts = line.split()
        change_type = parts[0]
        file_path = parts[1]
        
        if change_type == "D":
            continue  # 忽略删除
        elif change_type == "A":
            self.new_files.append(file_path)
        elif change_type in ["M", "R"]:
            self.modified_files.append(file_path)
```

**边界情况处理**:
- ✅ 删除的文件：直接忽略
- ⚠️ 二进制文件（图片）：会复制但不生成替换参数
- ⚠️ 重命名文件（R）：当作修改处理

---

### 2.2 复制新增文件

**关键命令**:
```bash
git show <commit_id>:<file_path>
```

**实现**:
```python
def copy_new_files(self):
    for file_path in self.new_files:
        dest_path = self.mod_dir / file_path
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 从 git 获取文件内容
        result = subprocess.run(
            ["git", "show", f"{self.commit_id}:{file_path}"],
            capture_output=True, check=True
        )
        
        with open(dest_path, "wb") as f:
            f.write(result.stdout)
```

**优点**: 不依赖工作区状态，直接从 git 对象数据库读取  
**缺点**: 无法处理子模块（submodule）

---

## 3. Twee 文件差异提取（核心功能）

### 3.1 获取文件 diff

**关键命令**:
```bash
git diff <commit~1> <commit> -- <file_path>
```

**输出示例**:
```diff
@@ -10,3 +10,5 @@
 <<set $money to 100>>
-You have $money dollars.
+You have $money dollars.
+<<link "Buy item">><<set $money -= 10>><</link>>
```

---

### 3.2 解析 diff 块

**正则表达式**:
```python
diff_blocks = re.findall(
    r'@@ -(\d+),\d+ \+(\d+),\d+ @@([\s\S]+?)(?=@@ |\Z)', 
    diff_content
)
```

**提取信息**:
- `old_line`: 原文件起始行号
- `new_line`: 新文件起始行号
- `block_content`: diff 内容

---

### 3.3 生成 TweeReplacer 参数

**关键逻辑**:
```python
def process_modified_twee(self, file_path):
    # 1. 获取段落名称（向上搜索 :: 开头的行）
    passage_name = self.get_passage_name(file_path, old_line)
    
    # 2. 分离添加/删除/上下文行
    for line in lines:
        if line.startswith("+"):
            added_lines.append(line[1:])
        elif line.startswith("-"):
            removed_lines.append(line[1:])
        else:
            context_lines.append(line[1:])
    
    # 3. 构建 findString 和 replace
    if added_lines and not removed_lines:
        # 纯新增
        find_string = "\n".join(context_before)
        replace = "\n".join(context_before + added_lines)
    elif removed_lines and not added_lines:
        # 纯删除
        find_string = "\n".join(context_before + removed_lines)
        replace = "\n".join(context_before)
    else:
        # 修改
        find_string = "\n".join(context_before + removed_lines)
        replace = "\n".join(context_before + added_lines)
    
    # 4. 添加到参数列表
    self.twee_replacer_params.append({
        "passage": passage_name,
        "findString": find_string,
        "replace": replace
    })
```

**段落名称识别**:
```python
def get_passage_name(self, file_path, line_number):
    # 从指定行向上搜索第一个 :: 开头的行
    for i in range(line_number, -1, -1):
        if lines[i].startswith("::"):
            passage_name = lines[i][2:].strip()
            # 去除 [widget] 标记
            passage_name = re.sub(r'\[widget\]', '', passage_name).strip()
            return passage_name
    return "Unknown Passage"
```

**示例输出**:
```json
{
  "passage": "Orphanage",
  "findString": "You have $money dollars.",
  "replace": "You have $money dollars.\n<<link \"Buy item\">><<set $money -= 10>><</link>>"
}
```

---

## 4. JS 文件差异提取

### 4.1 生成 ReplacePatcher 参数

**类似 Twee，但使用不同的键名**:
```python
def process_modified_js(self, file_path):
    # 解析 diff 块
    for old_line, new_line, block_content in diff_blocks:
        # 分离添加/删除/上下文行（逻辑同 Twee）
        
        # 构建 from 和 to
        if added_lines and not removed_lines:
            from_string = "\n".join(context_before)
            to_string = "\n".join(context_before + added_lines)
        # ... 其他情况
        
        # 添加到参数列表
        self.replace_patcher_params["js"].append({
            "filename": file_path,
            "from": from_string,
            "to": to_string
        })
```

**示例输出**:
```json
{
  "js": [
    {
      "filename": "game/scripts/main.js",
      "from": "function oldFunction() {",
      "to": "function newFunction() {\n  console.log('updated');"
    }
  ]
}
```

---

## 5. boot.json 生成

### 5.1 完整结构

```python
def generate_boot_json(self):
    boot_json = {
        "name": self.mod_name,
        "version": self.mod_version,
        "styleFileList": [],
        "scriptFileList": [],
        "additionFile": self.twee_file_list,  # 新增的 Twee 文件
        "TweeReplacer": {
            "params": self.twee_replacer_params
        },
        "ReplacePatcher": self.replace_patcher_params
    }
    
    with open(self.boot_json_path, "w", encoding="utf-8") as f:
        json.dump(boot_json, f, ensure_ascii=False, indent=2)
```

**关键字段**:
- `additionFile`: 新增的 Twee 文件路径列表
- `TweeReplacer.params`: Twee 文件替换规则数组
- `ReplacePatcher.js`: JS 文件替换规则数组

**缺失功能**:
- ❌ 不自动推断 `dependenceInfo`（依赖声明）
- ❌ 不支持 `styleFileList`（CSS 文件）
- ❌ 不支持 `scriptFileList_earlyload`（早期加载脚本）

---

## 6. mod.zip 打包

### 6.1 打包逻辑

```python
def create_zip(self):
    zip_path = self.output_dir / f"DoL-{self.mod_name}-{self.mod_version}.zip"
    
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        # 递归添加 mod 目录中的所有文件
        for root, dirs, files in os.walk(self.mod_dir):
            for file in files:
                file_path = Path(root) / file
                arcname = file_path.relative_to(self.mod_dir)
                zipf.write(file_path, arcname)
    
    print(f"MOD打包完成: {zip_path}")
```

**输出示例**:
```
output/
  DoL-newmode-1.zip
    boot.json
    game/
      passages/
        new_passage.twee
```

---

## 7. 边界情况与限制

### 7.1 已知限制

| 场景 | 当前行为 | 影响 |
|------|---------|------|
| 删除文件 | 忽略 | ⚠️ 无法生成"删除文件"的 mod |
| 二进制文件 | 复制但不生成替换参数 | ✅ 图片可正常包含 |
| 多个 passage 修改 | 生成多个 TweeReplacer 参数 | ✅ 正确处理 |
| 同一行多次修改 | 可能生成重复的替换规则 | ⚠️ 需手动去重 |
| 依赖推断 | 不支持 | ❌ 需手动添加 dependenceInfo |

---

### 7.2 错误处理

**当前实现**:
```python
try:
    result = subprocess.run([...], check=True)
except subprocess.CalledProcessError as e:
    print(f"错误: {e}")
    sys.exit(1)  # 直接退出
```

**问题**: 任何 git 命令失败都会导致整个程序终止，缺少优雅降级。

---

## 8. DOL-X 集成建议

### 8.1 重新实现 vs Fork

**推荐方案**: **重新实现**

**理由**:
1. 代码量不大（~500 行），重写成本可控
2. 可集成到 DOL-X 的 `tools/dev/` 架构
3. 统一代码风格（遵循 DOL-X 的 logging、路径管理）
4. 易于扩展（添加依赖推断、CSS 支持等）

---

### 8.2 改进点

**必须改进**:
1. **依赖推断**: 自动检测 mod 中使用的框架（如 maplebirch）
   ```python
   def infer_dependencies(self, twee_content):
       if "maplebirchFrameworks" in twee_content:
           return ["Simple Framework"]
       return []
   ```

2. **错误处理**: 优雅降级而非直接退出
   ```python
   try:
       result = subprocess.run([...], check=True)
   except subprocess.CalledProcessError as e:
       logger.warning(f"处理 {file_path} 失败: {e}")
       continue  # 跳过该文件，继续处理其他文件
   ```

3. **日志系统**: 使用 DOL-X 的 `logging` 模块
   ```python
   logger.info(f"新增文件: {len(self.new_files)}")
   logger.debug(f"Twee 替换参数: {self.twee_replacer_params}")
   ```

**可选改进**:
1. **CSS 支持**: 提取 CSS 文件差异
2. **测试模式**: 生成 mod 后自动触发构建和测试
3. **批量处理**: 支持一次测试多个 commit

---

### 8.3 集成到 main.py

**目标命令**:
```bash
python main.py dev commit-to-mod <hash> --repo <url> --auto-build --codes 57600
```

**实现结构**:
```
tools/dev/
  ├── commit_to_mod.py       # 核心转换逻辑
  ├── git_diff_parser.py     # Git diff 解析器
  └── dependency_inferrer.py # 依赖推断器
```

---

## 9. 技术债务与风险

### 9.1 上游同步风险

**问题**: DoL-Commit2Mod 可能更新实现细节

**缓解**: 
- DOL-X 重新实现后不依赖上游更新
- 定期检查上游是否有重大改进（每季度）

---

### 9.2 ModLoader 兼容性

**问题**: ModLoader 的 TweeReplacer/ReplacePatcher 格式可能变化

**缓解**:
- 在 DOL-X 测试套件中验证生成的 mod 能否正常加载
- 监控 ModLoader 更新日志

---

## 10. 下一步行动

### 10.1 立即可做（本周）

1. ✅ 完成 DoL-Commit2Mod 研究（本文档）
2. ⏳ 研究 MCH REMOTE_TEST（下一步）
3. ⏳ 决策实现策略

### 10.2 集成开发（2 周）

1. 创建 `tools/dev/commit_to_mod.py`
2. 实现核心转换逻辑
3. 添加依赖推断
4. 集成到 `main.py dev` 子命令
5. 编写单元测试

---

## 附录 A: 完整 boot.json 示例

```json
{
  "name": "Upstream-abc1234",
  "version": "1.0.0",
  "styleFileList": [],
  "scriptFileList": [],
  "additionFile": [
    "game/passages/new_passage.twee"
  ],
  "TweeReplacer": {
    "params": [
      {
        "passage": "Orphanage",
        "findString": "You have $money dollars.",
        "replace": "You have $money dollars.\n<<link \"Buy item\">><<set $money -= 10>><</link>>"
      }
    ]
  },
  "ReplacePatcher": {
    "js": [
      {
        "filename": "game/scripts/main.js",
        "from": "function oldFunction() {",
        "to": "function newFunction() {\n  console.log('updated');"
      }
    ]
  }
}
```

---

## 附录 B: 参考资料

- DoL-Commit2Mod GitHub: https://github.com/Lethivia/DoL-Commit2Mod
- ModLoader 文档: （需补充）
- DOL-X 路径管理: `lyra/paths.py`

---

**研究完成时间**: 2026-06-14  
**下一步**: 研究 MCH REMOTE_TEST 实现
