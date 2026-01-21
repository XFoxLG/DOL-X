# DoL-Lyra 构建系统文档

## 目录

- [简介](#简介)
- [快速开始](#快速开始)
- [功能特性](#功能特性)
- [环境准备](#环境准备)
- [构建命令](#构建命令)
  - [main.py - 统一构建入口](#mainpy---统一构建入口)
- [MOD 代码说明](#mod-代码说明)
- [配置文件](#配置文件)
- [并行构建](#并行构建)
- [高级用法](#高级用法)
- [故障排查](#故障排查)
- [开发指南](#开发指南)

---

## 简介

DoL-Lyra 构建系统 v2.0 是一个完全重构的自动化构建工具，专为 CI/CD 环境设计，用于生成 Degrees of Lewdity 游戏的各种 MOD 组合包。

### 核心特性

- **完整的 CI 流程**：prepare → warmup → build → page 四阶段构建
- **资源预热机制**：避免并行构建时的资源冲突
- **配置驱动**：所有组合和规则通过 TOML 配置管理
- **多种 MOD 组合**：13 种不同的 MOD 可自由组合
- **双平台支持**：ZIP（PC/Web）和 APK（Android）
- **并行构建**：多核 CPU 加速，2-6 倍性能提升
- **版本管理**：统一的版本信息记录和追踪

### 架构概览

```
lyra/
├── paths.py          # 路径管理（集中管理所有构建路径）
├── version.py        # 版本信息管理
├── config.py         # MOD 代码定义
├── config_loader.py  # 配置文件加载
├── downloader.py     # 资源下载（游戏文件、额外mod）
├── warmup.py         # 资源预热（DoL+图包、AU变体）
├── prepare.py        # 游戏预处理（APK反编译、mod注入）
├── build.py          # 核心构建逻辑（ZipBuilder, ApkBuilder）
├── parallel.py       # 并行构建管理
├── combo.py          # MOD 组合计算
├── gen_page.py       # 下载页面生成
└── utils.py          # 工具函数

config/
├── build.toml        # 构建配置（URL、路径、APK替换规则）
├── features.toml     # MOD 功能定义
└── combinations.toml # MOD 组合规则

main.py               # 统一命令行入口
```

---

## 快速开始

### CI/CD 完整流程（推荐）

```bash
# 1. 准备游戏资源（下载游戏文件、额外mod、生成基包）
python main.py prepare --tag v0.5.7.9-5.0.2a-0112

# 2. 预热美化资源（下载并解压所有DoL+图包、AU变体）
python main.py warmup

# 3. 并行构建所有组合（使用8个进程）
python main.py build --tag v0.5.7.9-5.0.2a-0112 --jobs 8

# 4. 生成下载页面
python main.py page --tag v0.5.7.9-5.0.2a-0112 -o index.md

# 5. 查看输出
ls output/
```

### 开发/测试流程

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 准备环境（一次性）
python main.py prepare --tag v0.5.7.9-5.0.2a-0112
python main.py warmup

# 3. 构建特定组合（快速测试）
# 使用已有基包，无需重新下载
python main.py build --tag v0.5.7.9-5.0.2a-0112 zip  # 仅ZIP
python main.py build --tag v0.5.7.9-5.0.2a-0112 apk  # 仅APK
```

---

## 功能特性

### 1. 四阶段 CI 流程

**Phase 1: prepare - 准备游戏资源**

- 从汉化仓库下载游戏文件（ZIP、APK）
- 下载额外 MOD（作弊、CSD、ModLoader GUI、i18n）
- 下载构建工具（apktool、uber-apk-signer）
- 反编译 APK 并应用配置修改
- 生成 ZIP 基包和 APK 解包目录
- 注入额外 MOD 到基包
- 记录所有版本信息到 `versions.json`

**Phase 2: warmup - 预热美化资源**

- 下载并解压所有 DoL+ 图包（BESC、Hikari、Goose、UCB）
- 下载并解压所有 AU 变体（Female、Male、Androgynous）
- 避免并行构建时的资源下载冲突
- 追加版本信息到 `versions.json`

**Phase 3: build - 并行构建**

- 从基包复用预处理结果
- 从预热目录复用美化资源
- 并行构建所有 MOD 组合
- 支持 ZIP 和 APK 双平台
- 支持 polyfill 版本

**Phase 4: page - 生成下载页面**

- 读取 `versions.json` 获取完整版本信息
- 生成 Markdown 下载表格
- 包含所有 MOD 组合的下载链接

### 2. 资源预热机制

通过 warmup 阶段串行下载所有美化资源，解决并行构建中的问题：

- **问题**：多个构建任务同时下载同一资源导致文件损坏
- **解决**：提前下载并解压到固定位置
- **构建阶段**：直接复制预热的资源，无需下载

支持的资源：

- DoL+ 图包：dolp、b3s、kaervek、dolp_b3s、b3s_hikfem、goosefem 等
- AU 变体：female、male、androgynous

### 3. 配置驱动的组合管理

所有 MOD 组合通过 `config/combinations.toml` 定义：

```toml
[rules]
# 推荐组合（优先显示）
recommended = [3, 35, 259, 514]

# 必须包含的 MOD
must_include = [2]  # 作弊

# 互斥组（不能同时启用）
[[rules.exclusive_groups]]
mods = [1024, 2048, 4096]  # AU三个变体互斥
```

优势：

- 无需修改代码即可调整组合
- 支持依赖关系和互斥规则
- 自动生成有效组合列表

### 4. 统一的版本管理

通过 `VersionRegistry` 记录所有组件版本：

```json
{
  "汉化仓库": {
    "version": "v0.5.7.9-chs-5.0.2a",
    "source": "Eltirosto/Degrees-of-Lewdity-Chinese-Localization"
  },
  "DoL+": {
    "version": "abc123def",
    "source": "gitgud.io/Frostberg/degrees-of-lewdity-plus"
  }
}
```

用途：

- 下载页面显示版本信息
- 问题追溯和调试
- 版本一致性检查

### 5. 并行构建优化

- **进程池并行**：使用 `ProcessPoolExecutor`
- **独立工作目录**：`extract/{pack_type}/{mod_code}/`
- **资源复用**：基包和预热资源
- **异常隔离**：单个任务失败不影响其他任务
- **性能提升**：2-6 倍加速（取决于 CPU 核心数）

## 环境准备

### 系统要求

- **操作系统**：Linux / macOS / Windows (WSL)
- **Python**：3.8+
- **Java**：17+（APK 构建需要）

### 安装步骤

```bash
# 1. 克隆仓库
git clone https://github.com/DoL-Lyra/Lyra.git
cd Lyra

# 2. 安装 Python 依赖
pip install -r requirements.txt

# 3. 验证 Java 环境（APK 构建需要）
java -version
# 应显示 Java 17 或更高版本

# 4. 测试命令
python main.py --help
```

### 目录结构说明

```
项目根目录/
├── main.py              # 统一命令行入口
├── lyra/                # 核心模块
├── config/              # 配置文件
├── workspace/           # 工作目录（自动创建）
│   ├── base/           # 基包存放目录
│   ├── prepare_package/# 预处理目录
│   ├── extract/        # 构建临时目录
│   ├── dolp/           # DoL+ 图包缓存
│   ├── au/             # AU 变体缓存
│   ├── temp/           # 临时文件
│   └── versions.json   # 版本信息
└── output/             # 最终输出目录
```

---

## 构建命令

### main.py - 统一构建入口

DoL-Lyra v2.0 使用统一的命令行入口，所有操作通过子命令执行。

#### 基本语法

```bash
python main.py <command> [options]
```

#### 可用命令

| 命令 | 说明 | 用途 |
|------|------|------|
| `prepare` | 准备游戏资源 | 下载游戏文件、额外mod、生成基包 |
| `warmup` | 预热美化资源 | 下载并解压DoL+图包和AU变体 |
| `build` | 并行构建 | 构建所有或指定类型的MOD组合 |
| `page` | 生成下载页面 | 生成Markdown下载表格 |
| `matrix` | 生成构建矩阵 | 生成GitHub Actions矩阵JSON |
| `check` | 检查更新 | 检查汉化仓库是否有新版本 |

---

### 1. prepare - 准备游戏资源

**用途**：CI 流程第一步，下载所有游戏资源并生成基包。

```bash
python main.py prepare --tag <version_tag> [options]
```

**参数**：

```bash
--tag TAG           # 版本标签（必需），格式: v0.5.7.9-5.0.2a-0112
--workspace DIR     # 工作目录（默认: .）
-v, --verbose       # 详细日志
```

**示例**：

```bash
# 准备指定版本的资源
python main.py prepare --tag v0.5.7.9-5.0.2a-0112

# 使用自定义工作目录
python main.py prepare --tag v0.5.7.9-5.0.2a-0112 --workspace /data/lyra

# 详细日志模式
python main.py prepare --tag v0.5.7.9-5.0.2a-0112 -v
```

**输出**：

```
workspace/
├── base/
│   ├── base.zip              # ZIP基包（已注入额外mod）
│   ├── base-polyfill.zip     # Polyfill ZIP基包
│   └── names.json            # 基包文件名映射
├── prepare_package/
│   ├── apk/                  # 已解包的正常版APK（已注入mod）
│   └── apk-polyfill/         # 已解包的polyfill APK
└── versions.json             # 版本信息记录
```

**功能细节**：

1. 从汉化仓库下载：
   - DoL 游戏 ZIP（正常版和polyfill版）
   - DoL 游戏 APK
   - 原始图片包（用于验证）
2. 从额外仓库下载：
   - 作弊 MOD
   - CSD MOD
   - ModLoader GUI
3. 下载构建工具：
   - apktool.jar
   - uber-apk-signer.jar
4. 预处理：
   - 反编译 APK
   - 应用配置替换（包名、版本号等）
   - 注入额外 MOD 到 ZIP 和 APK
   - 重新打包 ZIP 基包

---

### 2. warmup - 预热美化资源

**用途**：CI 流程第二步，提前下载并解压所有美化资源。

```bash
python main.py warmup [options]
```

**参数**：

```bash
--workspace DIR     # 工作目录（默认: .）
-v, --verbose       # 详细日志
```

**示例**：

```bash
# 预热所有美化资源
python main.py warmup

# 使用自定义工作目录
python main.py warmup --workspace /data/lyra -v
```

**输出**：

```
workspace/
├── dolp/                    # DoL+ 图包目录
│   ├── dolp/
│   ├── b3s/
│   ├── kaervek/
│   ├── dolp_b3s/
│   ├── b3s_hikfem/
│   ├── b3s_hikfemsubs/
│   ├── goosefem/
│   ├── goosefemsubs/
│   └── mysterious/
├── au/                      # AU 变体目录
│   ├── AUfemale/
│   ├── AUmale/
│   └── AUandrogynous/
└── versions.json            # 追加版本信息
```

**功能细节**：

1. DoL+ 图包：
   - 从 GitGud 下载 tar.gz
   - 解压到 `workspace/dolp/{pack_name}/`
   - 覆盖已存在的目录
2. AU 变体：
   - 从 GitHub 下载 zip
   - 解压到 `workspace/au/AU{variant}/`
3. 版本记录：
   - 记录 DoL+ 的 commit hash
   - 记录 AU 变体的 release tag

**为什么需要 warmup？**

- **问题**：并行构建时，多个进程同时下载同一资源导致文件损坏
- **解决**：提前串行下载，构建时直接复制
- **性能**：下载一次，复用多次

---

### 3. build - 并行构建

**用途**：CI 流程第三步，并行构建所有 MOD 组合。

```bash
python main.py build [pack_type] --tag <version_tag> [options]
```

**参数**：

```bash
pack_type           # 可选：zip 或 apk（不指定则两种都构建）
--tag TAG           # 版本标签（必需）
--jobs N, -j N      # 并发进程数（默认: min(cpu_count, 8)）
--workspace DIR     # 工作目录（默认: .）
-v, --verbose       # 详细日志
```

**示例**：

```bash
# 构建所有组合（ZIP和APK），使用8个进程
python main.py build --tag v0.5.7.9-5.0.2a-0112 --jobs 8

# 仅构建ZIP
python main.py build zip --tag v0.5.7.9-5.0.2a-0112

# 仅构建APK，使用4个进程
python main.py build apk --tag v0.5.7.9-5.0.2a-0112 -j 4

# 使用自动选择的并发数
python main.py build --tag v0.5.7.9-5.0.2a-0112 -v
```

**输出**：

```
output/
├── DoL-0.5.7.9-chs-5.0.2a-lyra-besc-cheat-0112.zip
├── DoL-0.5.7.9-chs-5.0.2a-lyra-besc-cheat-hikari-0112.zip
├── DoL-0.5.7.9-chs-5.0.2a-lyra-besc-cheat-hikari-ucb-0112.zip
├── DoL-0.5.7.9-chs-5.0.2a-lyra-besc-cheat-0112.apk
├── DoL-0.5.7.9-chs-5.0.2a-lyra-besc-cheat-hikari-0112.apk
└── ...（50+ 个文件）
```

**功能细节**：

1. 从配置生成组合列表
2. 为每个组合创建独立任务
3. 使用进程池并行执行
4. 每个任务：
   - 从基包复制到独立工作目录
   - 从预热目录复制美化资源
   - 应用 MOD 特定的修改
   - 打包为 ZIP 或重编译签名为 APK
   - 移动到 output 目录

**并发配置建议**：

| 内存 | CPU核心 | 推荐 -j | 说明 |
|------|---------|---------|------|
| 4GB | 4核 | 2 | 保守配置 |
| 8GB | 8核 | 4-6 | 标准配置 |
| 16GB | 16核 | 8-12 | 高性能配置 |
| 32GB+ | 32核+ | 16+ | 服务器配置 |

---

### 4. page - 生成下载页面

**用途**：CI 流程第四步，生成带下载链接的 Markdown 表格。

```bash
python main.py page --tag <version_tag> [options]
```

**参数**：

```bash
--tag TAG           # 版本标签（必需）
-o, --output FILE   # 输出文件（可选，默认打印到标准输出）
--workspace DIR     # 工作目录（默认: .）
--github-owner STR  # GitHub用户名（默认: DoL-Lyra）
--github-repo STR   # GitHub仓库名（默认: Lyra）
-v, --verbose       # 详细日志
```

**示例**：

```bash
# 生成下载页面到文件
python main.py page --tag v0.5.7.9-5.0.2a-0112 -o download.md

# 打印到标准输出
python main.py page --tag v0.5.7.9-5.0.2a-0112

# 自定义GitHub仓库
python main.py page --tag v0.5.7.9-5.0.2a-0112 \
  --github-owner sakarie9 \
  --github-repo DoL-Lyra \
  -o index.md
```

**输出示例**：

```markdown
# DoL-Lyra 下载页面

版本: v0.5.7.9-5.0.2a-0112

## 版本信息

- 汉化仓库: v0.5.7.9-chs-5.0.2a
- DoL+: abc123def
- AU Female: v1.0.0

## 下载链接

| MOD组合 | ZIP | APK |
|---------|-----|-----|
| BESC+作弊 | [下载](链接) | [下载](链接) |
| BESC+作弊+Hikari | [下载](链接) | [下载](链接) |
```

---

### 5. matrix - 生成构建矩阵

**用途**：为 GitHub Actions 生成构建矩阵 JSON。

```bash
python main.py matrix
```

**输出**：

```json
{
  "include": [
    {"pack_type": "zip", "code": "3"},
    {"pack_type": "zip", "code": "35"},
    {"pack_type": "apk", "code": "3"}
  ]
}
```

---

### 6. check - 检查更新

**用途**：检查汉化仓库是否有新的 release。

```bash
python main.py check [--tag TAG]
```

**示例**：

```bash
# 检查最新版本
python main.py check

# 检查指定版本
python main.py check --tag v0.5.7.9-5.0.2a
```

**输出**：

- 退出码 0：有新版本
- 退出码 1：已是最新版本

---

## MOD 代码说明

### 代码表

| MOD 名称 | 位值 | 说明 |
|---------|------|------|
| BESC | 1 | BEEESSS 社区精灵合集 |
| 作弊 | 2 | 作弊功能模块 |
| CSD | 4 | CSD 功能 |
| Sideview-BJ | 8 | BJ 特写 |
| Sideview-KR | 16 | KR 特写 |
| Sideview-Hikari | 32 | Hikari 特写 |
| WAX | 64 | WAX 美化 |
| Susato | 128 | Susato 模型 |
| UCB | 256 | 通用战斗美化 |
| Sideview-Goose | 512 | Goose 特写 |
| AU-Female | 1024 | AU 女性变体 |
| AU-Male | 2048 | AU 男性变体 |
| AU-Androgynous | 4096 | AU 双性变体 |

### 代码计算

MOD 代码通过**位运算（按位或）**计算：

```python
# 示例 1：BESC + 作弊
code = 1 | 2 = 3

# 示例 2：BESC + 作弊 + Hikari
code = 1 | 2 | 32 = 35

# 示例 3：BESC + 作弊 + Hikari + UCB
code = 1 | 2 | 32 | 256 = 291

# 示例 4：作弊 + Hikari + AU Female
code = 2 | 32 | 1024 = 1058
```

### 常用组合

| 代码 | 组合名称 | 包含的MOD |
|------|---------|----------|
| 3 | BESC+作弊 | BESC, 作弊 |
| 7 | BESC+作弊+CSD | BESC, 作弊, CSD |
| 35 | BESC+作弊+Hikari | BESC, 作弊, Hikari特写 |
| 259 | BESC+作弊+UCB | BESC, 作弊, UCB |
| 291 | BESC+作弊+Hikari+UCB | BESC, 作弊, Hikari特写, UCB |
| 1058 | 作弊+Hikari+AU女性 | 作弊, Hikari特写, AU女性 |
| 2082 | 作弊+Hikari+AU男性 | 作弊, Hikari特写, AU男性 |
| 4130 | 作弊+Hikari+AU双性 | 作弊, Hikari特写, AU双性 |

### Polyfill 版本

Polyfill 版本使用特殊的 JavaScript 兼容性补丁，适用于某些旧设备。

在配置中通过 `is_polyfill` 标志区分：

- 正常版：`code = 3`
- Polyfill 版：`code = 3, is_polyfill = True`

### 查看所有组合

```bash
# 列出所有有效组合
python -c "from lyra.combo import CombinationCalculator; \
calc = CombinationCalculator(); \
for combo in calc.get_combinations(): \
    print(f'{combo.code}: {combo.display_name}')"
```

---

## 配置文件

所有配置文件位于 `config/` 目录，使用 TOML 格式。

### config/build.toml

**用途**：构建过程配置

```toml
[paths]
workspace = "workspace"           # 工作目录
output = "output"                 # 输出目录
base_dir = "base"                # 基包目录
prepare_package_dir = "prepare_package"  # 预处理目录

[urls]
# 构建工具
apktool = "https://github.com/.../apktool_2.12.0.jar"
uber_apk_signer = "https://github.com/.../uber-apk-signer-1.3.0.jar"

# DoL+ 图包（GitGud）
dolp_base = "https://gitgud.io/Frostberg/degrees-of-lewdity-plus/-/archive/master/degrees-of-lewdity-plus-master.tar.gz"

# AU 变体（GitHub）
au_female = "https://github.com/.../AUfemale.imgpack.zip"
au_male = "https://github.com/.../AUmale.imgpack.zip"
au_androgynous = "https://github.com/.../AUandrogynous.imgpack.zip"

[github]
owner = "DoL-Lyra"
repo = "Lyra"

# APK 配置替换规则
[[apk.replacements]]
file = "AndroidManifest.xml"
pattern = '"com.vrelnir.dol"'
replacement = '"com.vrelnir.dol.lyra"'
description = "修改包名"

[[apk.replacements]]
file = "apktool.yml"
pattern = 'versionName: .*'
replacement = 'versionName: "{version}"'
description = "更新版本号"
```

**字段说明**：

- `paths`: 目录配置
- `urls`: 资源下载地址
- `github`: GitHub 仓库信息
- `apk.replacements`: APK 文本替换规则
  - `file`: 要修改的文件路径（相对于 APK 解包目录）
  - `pattern`: 正则表达式匹配模式
  - `replacement`: 替换文本（支持 `{version}` 占位符）

---

### config/features.toml

**用途**：MOD 功能定义

```toml
[[feature]]
id = "besc"                    # 内部ID
name = "BESC"                  # 显示名称
bit = 1                        # 位标志值
display_name = "BESC"          # 下载页面显示名
description = "BEEESSS社区精灵合集"

[[feature]]
id = "cheat"
name = "作弊"
bit = 2
display_name = "作弊"
description = "作弊功能"

[[feature]]
id = "au_female"
name = "AU Female"
bit = 1024
display_name = "AU女性"
description = "AU女性身体变体"
```

**字段说明**：

- `id`: 唯一标识符，用于代码引用
- `name`: 功能名称
- `bit`: 位标志值（必须是 2 的幂）
- `display_name`: 用户界面显示名称
- `description`: 功能描述

**添加新 MOD**：

1. 在此文件添加新的 `[[feature]]` 块
2. 选择一个未使用的 `bit` 值（下一个 2 的幂）
3. 在 `combinations.toml` 中添加组合规则
4. 在代码中实现对应的构建逻辑

---

### config/combinations.toml

**用途**：定义有效的 MOD 组合和规则

```toml
[rules]
# 推荐组合（优先显示）
recommended = [3, 35, 259, 291, 1058, 2082, 4130]

# 必须包含的 MOD（通常是作弊）
must_include = [2]

# 互斥组（不能同时启用）
[[rules.exclusive_groups]]
mods = [1024, 2048, 4096]  # AU 三个变体互斥
reason = "AU变体互斥"

[[rules.exclusive_groups]]
mods = [8, 16, 32, 512]    # Sideview 互斥
reason = "Sideview特写互斥"

# 依赖关系
[[rules.dependencies]]
feature = "ucb"            # UCB 需要 BESC
requires = ["besc"]
```

**规则说明**：

1. **recommended**: 推荐组合列表，优先显示
2. **must_include**: 所有组合必须包含的 MOD
3. **exclusive_groups**: 互斥规则
   - `mods`: 互斥的 MOD 位值列表
   - `reason`: 互斥原因说明
4. **dependencies**: 依赖规则
   - `feature`: 需要依赖的 MOD ID
   - `requires`: 依赖的 MOD ID 列表

**组合生成逻辑**：

```python
# 伪代码
for code in range(1, 2^num_features):
    if not contains_all(code, must_include):
        continue  # 跳过不包含必须MOD的组合
    
    if violates_exclusive_groups(code):
        continue  # 跳过违反互斥规则的组合
    
    if not satisfies_dependencies(code):
        continue  # 跳过不满足依赖的组合
    
    yield code  # 有效组合
```

---

## 并行构建

### 工作原理

DoL-Lyra v2.0 使用 Python `ProcessPoolExecutor` 实现真正的多进程并行：

```
主进程
 ├─ 工作进程 1: 构建 zip/3
 ├─ 工作进程 2: 构建 zip/35
 ├─ 工作进程 3: 构建 apk/3
 ├─ 工作进程 4: 构建 apk/35
 └─ ...
```

每个工作进程完全独立，拥有：

- 独立的工作目录
- 独立的内存空间
- 独立的资源副本

### 并发安全设计

#### 1. 三级目录隔离

```
workspace/
├── extract/
│   ├── zip/              # ZIP 构建专用
│   │   ├── 3/           # MOD代码 3
│   │   │   └── game/    # 游戏文件
│   │   ├── 35/          # MOD代码 35
│   │   └── 291/
│   └── apk/              # APK 构建专用
│       ├── 3/
│       ├── 35/
│       └── 291/
```

**好处**：

- 不同包类型互不干扰（zip vs apk）
- 不同 MOD 代码互不干扰（3 vs 35）
- 支持同时构建同一代码的不同变体

#### 2. 资源预热 + 复制策略

**传统方式（问题）**：

```python
# 每个进程都下载（会冲突）
download_dolp_pack("b3s")
extract_to("workspace/dolp/b3s")
copy_to_game()
```

**新方式（解决）**：

```python
# Phase 1: warmup - 主进程串行下载
download_dolp_pack("b3s")
extract_to("workspace/dolp/b3s")  # 固定位置

# Phase 2: build - 工作进程并行复制
copy_from("workspace/dolp/b3s")  # 只读，并发安全
copy_to_game()
```

**资源来源**：

- 基包：`workspace/base/base.zip`
- DoL+ 图包：`workspace/dolp/{pack_name}/`
- AU 变体：`workspace/au/AU{variant}/`

#### 3. 临时文件命名

APK 构建需要临时文件，使用 MOD 代码作为唯一标识：

```python
# 每个 MOD 代码独立的临时文件
tmp_apk = workspace / f"tmp_{mod_code}.apk"
signed_dir = workspace / "signed" / str(mod_code)
```

### 最佳实践

1. **首次构建**：使用较低并发数（-j 2），观察是否有错误
2. **后续构建**：根据硬件逐步提高并发数
3. **CI 环境**：固定并发数，避免随机失败
4. **开发调试**：使用 -j 1（顺序执行），便于调试

---

## 高级用法

### 1. 自定义 MOD 组合

#### 添加新组合

编辑 [config/combinations.toml](config/combinations.toml)：

```toml
[rules]
# 添加到推荐组合
recommended = [3, 35, 259, 291, 1058, 2082, 4130, 1059]  # 新增 1059
```

#### 修改组合规则

```toml
# 修改必须包含的 MOD（例如不强制作弊）
must_include = []

# 添加新的互斥规则
[[rules.exclusive_groups]]
mods = [8, 16]  # BJ 和 KR 互斥
reason = "Sideview 样式冲突"
```

#### 验证组合

```bash
# 列出所有有效组合
python -c "
from lyra.combo import CombinationCalculator
calc = CombinationCalculator()
combos = calc.get_combinations()
print(f'总共 {len(combos)} 个组合')
for combo in combos[:10]:
    print(f'  {combo.code}: {combo.display_name}')
"
```

---

### 2. 自定义资源 URL

当官方资源下载缓慢或失效时，可以使用镜像。

编辑 [config/build.toml](config/build.toml)：

```toml
[urls]
# 使用自己的镜像
dolp_base = "https://your-cdn.com/dolp-master.tar.gz"
au_female = "https://your-mirror.com/AUfemale.zip"

# 或使用代理加速
dolp_base = "https://ghproxy.com/https://gitgud.io/Frostberg/degrees-of-lewdity-plus/-/archive/master/degrees-of-lewdity-plus-master.tar.gz"
```

---

### 3. 修改 APK 包名和版本

#### 修改包名

编辑 [config/build.toml](config/build.toml)：

```toml
[[apk.replacements]]
file = "AndroidManifest.xml"
pattern = '"com.vrelnir.dol"'
replacement = '"com.yourname.dol"'  # 自定义包名
```

#### 修改版本显示

```toml
[[apk.replacements]]
file = "apktool.yml"
pattern = 'versionName: .*'
replacement = 'versionName: "Lyra {version}"'  # 自定义版本格式
```

**变量替换**：

- `{version}`: 完整版本号（如 v0.5.7.9-5.0.2a-0112）
- `{dol_ver}`: DoL 版本号
- `{chs_ver}`: 汉化版本号
- `{date}`: 日期

---

### 4. 添加新的 MOD

#### Step 1: 定义 MOD 功能

编辑 [config/features.toml](config/features.toml)：

```toml
[[feature]]
id = "new_mod"                    # 唯一ID
name = "NewMod"                   # 功能名称
bit = 8192                        # 下一个2的幂
display_name = "新MOD"            # 显示名称
description = "新MOD功能说明"     # 描述
```

**选择位值**：

- 当前最大值：4096（AU-Androgynous）
- 下一个可用：8192
- 之后：16384, 32768, ...

#### Step 2: 更新枚举（可选）

如果需要在代码中引用，编辑 [lyra/config.py](lyra/config.py)：

```python
class ModCode(IntFlag):
    # ... existing codes ...
    NEW_MOD = 8192
```

#### Step 3: 实现构建逻辑

在 [lyra/build.py](lyra/build.py) 的 Builder 类中添加处理：

```python
def _apply_new_mod(self):
    """应用新 MOD"""
    if not self.task.mod_code & ModCode.NEW_MOD:
        return
    
    logger.info("应用新 MOD...")
    
    # 下载资源（如果需要）
    resource_path = self.paths.temp_dir / "new_mod.zip"
    if not resource_path.exists():
        download_file(
            "https://example.com/new_mod.zip",
            resource_path
        )
    
    # 解压到游戏目录
    extract_zip(resource_path, self.game_dir / "mods/new_mod")
    
    logger.info("新 MOD 应用完成")
```

在 `build()` 方法中调用：

```python
def build(self) -> BuildResult:
    # ... existing code ...
    self._apply_besc()
    self._apply_new_mod()  # 添加这行
    # ... existing code ...
```

#### Step 4: 更新组合规则

编辑 [config/combinations.toml](config/combinations.toml)：

```toml
[rules]
# 添加包含新 MOD 的推荐组合
recommended = [3, 35, 8195]  # 8195 = 2 + 32 + 8192

# 如果与其他 MOD 互斥
[[rules.exclusive_groups]]
mods = [1024, 8192]  # 新 MOD 与 AU Female 互斥
reason = "资源冲突"

# 如果有依赖
[[rules.dependencies]]
feature = "new_mod"
requires = ["besc"]  # 新 MOD 需要 BESC
```

#### Step 5: 测试

```bash
# 重新加载配置
python -c "from lyra.combo import CombinationCalculator; print(CombinationCalculator().features)"

# 构建包含新 MOD 的组合
python main.py build --tag vX.X.X-X.X.X-XXXX -v

# 验证输出
ls output/*new_mod*
```

---

### 5. 自定义下载页面模板

#### 修改表格格式

编辑 [lyra/gen_page.py](lyra/gen_page.py) 中的 `_generate_table()` 方法：

```python
# 添加自定义列
table.headers = ["MOD组合", "说明", "ZIP", "APK", "大小"]

# 添加数据
for combo in combinations:
    row = [
        combo.display_name,
        combo.description,  # 新增说明列
        zip_link,
        apk_link,
        file_size,  # 新增大小列
    ]
    table.value_matrix.append(row)
```

#### 添加版本信息展示

```python
def _generate_version_section(self) -> str:
    """生成版本信息区域"""
    lines = ["## 版本信息\n"]
    
    for info in self.config.version_info:
        lines.append(f"- **{info.name}**: {info.version}")
        if info.source:
            lines.append(f"  - 来源: {info.source}")
    
    return "\n".join(lines)
```

---

### 6. CI/CD 集成

#### GitHub Actions 工作流

创建 `.github/workflows/build.yml`：

```yaml
name: Build Release

on:
  push:
    tags:
      - 'v*'

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      
      - name: Install dependencies
        run: pip install -r requirements.txt
      
      - name: Prepare resources
        run: python main.py prepare --tag ${{ github.ref_name }}
      
      - name: Warmup assets
        run: python main.py warmup
      
      - name: Build all
        run: python main.py build --tag ${{ github.ref_name }} -j 4
      
      - name: Generate page
        run: python main.py page --tag ${{ github.ref_name }} -o index.md
      
      - name: Upload artifacts
        uses: actions/upload-artifact@v3
        with:
          name: releases
          path: output/*
```

#### 自动发布

```yaml
      - name: Create Release
        uses: softprops/action-gh-release@v1
        with:
          files: output/*
          body_path: index.md
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

---

### 7. 本地开发技巧

#### 快速测试单个组合

```bash
# 1. 准备环境（一次性）
python main.py prepare --tag v0.5.7.9-5.0.2a-0112
python main.py warmup

# 2. 快速构建测试
# 修改代码后，无需重新 prepare/warmup
python main.py build zip --tag v0.5.7.9-5.0.2a-0112

# 3. 检查输出
unzip -l output/DoL-*.zip | head -20
```

#### 使用 Python REPL 调试

```bash
python
>>> from lyra.build import BuildTask, build_single
>>> from lyra.paths import BuildPaths
>>> from lyra.version import LyraVersion
>>> 
>>> task = BuildTask(
...     pack_type="zip",
...     mod_code=3,
...     version=LyraVersion.from_tag("v0.5.7.9-5.0.2a-0112")
... )
>>> result = build_single(task)
>>> print(result.success, result.error)
```

#### 清理临时文件

```bash
# 清理构建临时目录
rm -rf workspace/extract/

# 清理所有缓存（重新开始）
rm -rf workspace/
rm -rf output/

# 保留预热资源（节省下载时间）
rm -rf workspace/extract/
rm -rf workspace/base/
rm -rf workspace/prepare_package/
# 保留 workspace/dolp/ 和 workspace/au/
```

---

## 故障排查

### 常见问题

#### 1. Java 相关错误

**症状**：

```
java: command not found
或
Error: A JNI error has occurred
```

**解决**：

```bash
# 检查 Java 版本
java -version

# Ubuntu/Debian 安装
sudo apt update
sudo apt install openjdk-17-jdk

# macOS 安装
brew install openjdk@17

# 配置环境变量（如果需要）
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
export PATH=$JAVA_HOME/bin:$PATH
```

---

#### 2. 内存不足（OOM）

**症状**：

```
[工作进程3] Killed
MemoryError
或进程被系统强制终止
```

**原因**：并发构建消耗内存过多

**解决方案**：

```bash
# 方法 1: 减少并发数
python main.py build --tag TAG -j 2

# 方法 2: 仅构建 ZIP（更省内存）
python main.py build zip --tag TAG -j 4

# 方法 3: 增加系统 swap
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# 方法 4: 清理内存缓存（Linux）
sudo sync
sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches'
```

---

#### 3. APK 签名失败

**症状**：

```
uber-apk-signer returned non-zero exit status
或
jarsigner error: java.util.zip.ZipException
```

**原因**：

- uber-apk-signer.jar 损坏或下载不完整
- APK 文件损坏
- Java 版本不兼容

**解决**：

```bash
# 重新下载签名工具
rm workspace/uber-apk-signer.jar
python main.py prepare --tag TAG

# 检查 Java 版本（需要 17+）
java -version

# 手动测试签名
java -jar workspace/uber-apk-signer.jar \
  --apks workspace/tmp_3.apk \
  --out workspace/test_signed/
```

---

#### 4. 资源下载失败

**症状**：

```
Failed to download https://...
或
requests.exceptions.ConnectionError
或
Read timed out
```

**解决方案**：

```bash
# 方法 1: 重试（网络临时问题）
python main.py prepare --tag TAG

# 方法 2: 使用代理
export HTTP_PROXY=http://proxy:port
export HTTPS_PROXY=http://proxy:port
python main.py prepare --tag TAG

# 方法 3: 手动下载资源
# 查看 config/build.toml 获取 URL
wget https://gitgud.io/.../dolp-master.tar.gz -O workspace/temp/dolp.tar.gz

# 方法 4: 使用镜像（修改 config/build.toml）
[urls]
dolp_base = "https://ghproxy.com/https://gitgud.io/..."
```

---

#### 5. 汉化仓库 Release 不存在

**症状**：

```
GitHub API returned 404: Not Found
或
无法获取汉化仓库release信息
```

**原因**：指定的版本 tag 在汉化仓库中不存在

**解决**：

```bash
# 检查可用的 release
curl -s https://api.github.com/repos/Eltirosto/Degrees-of-Lewdity-Chinese-Localization/releases | jq '.[].tag_name'

# 使用最新 release
python main.py prepare --tag latest

# 或使用正确的版本号
python main.py prepare --tag v0.5.7.9-5.0.2a-0112
```

---

#### 6. Polyfill 文件缺失

**症状**：

```
FileNotFoundError: workspace/base/base-polyfill.zip
```

**原因**：汉化仓库 release 中没有 polyfill 版本

**解决**：

```bash
# 检查 release assets
curl -s https://api.github.com/repos/Eltirosto/Degrees-of-Lewdity-Chinese-Localization/releases/latest | \
  jq '.assets[].name'

# 如果确实没有 polyfill：
# 1. 等待汉化仓库更新
# 2. 或仅构建正常版本
python main.py build zip --tag TAG  # 不包含 polyfill
```

---

#### 7. 并行构建部分失败

**症状**：

```
Success: 48 tasks
Failed: 4 tasks
  - zip/3: Error message
  - apk/35: Error message
```

**调试步骤**：

```bash
# 1. 查看详细日志
python main.py build --tag TAG -j 8 -v 2>&1 | tee build.log

# 2. 搜索错误信息
grep -A 5 -i error build.log
grep -A 5 -i failed build.log

# 3. 单独重试失败的组合（使用配置驱动构建）
# 注意：v2.0 不再支持单独构建单个代码
# 可以通过修改 combinations.toml 临时只包含失败的组合
```

---

#### 8. 目录权限错误

**症状**：

```
PermissionError: [Errno 13] Permission denied: 'workspace/...'
```

**解决**：

```bash
# 检查目录权限
ls -la workspace/

# 修复权限
chmod -R u+rwX workspace/
chmod -R u+rwX output/

# 如果使用 sudo 运行过（不推荐），清理后重新运行
sudo rm -rf workspace/ output/
python main.py prepare --tag TAG
```

---

### 调试技巧

#### 1. 启用详细日志

```bash
# 所有命令都支持 -v 参数
python main.py prepare --tag TAG -v
python main.py warmup -v
python main.py build --tag TAG -v
python main.py page --tag TAG -v
```

**日志级别**：

- 无 `-v`: INFO（默认）
- `-v`: DEBUG（详细信息）

#### 2. 使用 Python 调试器

```bash
# 使用 pdb 调试
python -m pdb main.py prepare --tag TAG

# 使用 ipdb（更友好）
pip install ipdb
python -m ipdb main.py build --tag TAG
```

#### 3. 检查临时文件

```bash
# 查看工作目录结构
tree -L 3 workspace/

# 检查基包
ls -lh workspace/base/
unzip -l workspace/base/base.zip | head -20

# 检查 APK 解包内容
ls -lh workspace/prepare_package/apk/

# 检查预热资源
ls -lh workspace/dolp/
ls -lh workspace/au/

# 检查构建临时目录
ls -lh workspace/extract/zip/
ls -lh workspace/extract/apk/
```

#### 4. 验证配置加载

```bash
# 测试配置解析
python -c "
from lyra.config_loader import get_config_loader
loader = get_config_loader()
print('Features:', len(loader.features))
print('Combinations:', len(loader.combinations.rules.recommended))
print('Build config:', loader.build_config.output_dir)
"

# 列出所有有效组合
python -c "
from lyra.combo import CombinationCalculator
calc = CombinationCalculator()
combos = calc.get_combinations()
print(f'Total: {len(combos)} combinations')
for c in combos[:5]:
    print(f'  {c.code}: {c.display_name}')
"
```

#### 5. 单步调试构建流程

```python
# 在 Python REPL 中
from pathlib import Path
from lyra.build import BuildTask, ZipBuilder
from lyra.paths import BuildPaths
from lyra.version import LyraVersion

# 初始化
paths = BuildPaths()
version = LyraVersion.from_tag("v0.5.7.9-5.0.2a-0112")
task = BuildTask(pack_type="zip", mod_code=3, version=version, paths=paths)

# 创建构建器
builder = ZipBuilder(task)

# 单步执行
builder._copy_from_base()        # 复制基包
builder._apply_besc()            # 应用 BESC
builder._apply_cheat()           # 应用作弊
# ... 根据需要调用其他方法

# 检查结果
print(f"Game dir: {builder.game_dir}")
print(f"Output: {builder.output_path}")
```

---

### 环境检查清单

使用前确保满足以下条件：

```bash
# Python 版本
python --version  # >= 3.8

# Java 版本（APK 构建需要）
java -version     # >= 17

# 网络连接
ping -c 3 github.com
ping -c 3 gitgud.io

# Python 依赖
pip list | grep -E '(requests|tomli|pytablewriter)'
```

---

### 获取帮助

如果问题仍未解决：

1. **查看日志**：`python main.py <command> -v 2>&1 | tee debug.log`
2. **提交 Issue**：<https://github.com/DoL-Lyra/Lyra/issues>
   - 附上完整的错误信息
   - 附上 `debug.log`
   - 说明操作系统和环境
3. **社区讨论**：查看已有的 Issues 和 Discussions

---

## 开发指南

### 项目结构

```
DoL-Lyra/
├── main.py                    # 统一命令行入口
├── requirements.txt           # Python 依赖
├── README.md                  # 项目说明
├── BUILD.md                   # 本文档
├── LICENSE                    # 许可证
│
├── lyra/                      # 核心模块
│   ├── __init__.py           # 模块初始化，版本信息
│   ├── __main__.py           # 作为模块运行入口
│   ├── paths.py              # 路径管理
│   ├── version.py            # 版本信息管理
│   ├── config.py             # MOD 代码定义
│   ├── config_loader.py      # 配置文件加载
│   ├── downloader.py         # 资源下载
│   ├── warmup.py             # 资源预热
│   ├── prepare.py            # 游戏预处理
│   ├── build.py              # 构建器（ZipBuilder, ApkBuilder）
│   ├── parallel.py           # 并行构建管理
│   ├── combo.py              # MOD 组合计算
│   ├── gen_page.py           # 下载页面生成
│   └── utils.py              # 工具函数
│
├── config/                    # 配置文件
│   ├── build.toml            # 构建配置
│   ├── features.toml         # MOD 功能定义
│   └── combinations.toml     # MOD 组合规则
│
├── tests/                     # 测试
│   ├── __init__.py
│   ├── test_config.py        # 配置加载测试
│   ├── test_utils.py         # 工具函数测试
│   ├── test_parallel.py      # 并行构建测试
│   └── test_download_gen.py  # 下载和生成测试
│
└── scripts/                   # 辅助脚本
    ├── __init__.py
    └── modmagic.py           # MOD 工具
```

### 核心模块说明

#### 1. paths.py - 路径管理

**职责**：集中管理所有构建路径

**关键类**：

```python
@dataclass
class BuildPaths:
    """路径管理器"""
    workspace: Path = Path(".")
    
    @property
    def base_dir(self) -> Path:
        """基包目录"""
        return self.workspace / "base"
    
    @property
    def output_dir(self) -> Path:
        """输出目录"""
        return Path("output")
    
    # ... 更多路径属性
```

**设计思路**：

- 所有路径计算集中在一处
- 避免硬编码路径字符串
- 支持自定义工作目录

---

#### 2. version.py - 版本信息管理

**职责**：统一管理版本信息

**关键类**：

```python
@dataclass
class LyraVersion:
    """Lyra 版本信息"""
    dol_ver: str    # DoL 版本号
    chs_ver: str    # 汉化版本号
    date: str       # 日期
    
    @classmethod
    def from_tag(cls, tag: str) -> "LyraVersion":
        """从 tag 解析版本"""
        # v0.5.7.9-5.0.2a-0112 -> LyraVersion(...)

@dataclass
class VersionInfo:
    """单个组件的版本信息"""
    name: str       # 组件名称
    version: str    # 版本号
    source: str     # 来源

class VersionRegistry:
    """版本信息注册表"""
    def add(self, info: VersionInfo):
        """添加版本信息"""
    
    def save(self, path: Path):
        """保存到 JSON"""
    
    @classmethod
    def load(cls, path: Path) -> "VersionRegistry":
        """从 JSON 加载"""
```

---

#### 3. downloader.py - 资源下载

**职责**：从各种来源下载资源

**关键类**：

```python
class Downloader:
    """资源下载器"""
    
    def download_from_chs_repo(self, version: Optional[LyraVersion]) -> dict:
        """从汉化仓库下载游戏文件"""
        # 返回: {"zip": Path, "apk": Path, ...}
    
    def download_extra_mods(self) -> dict:
        """下载额外 MOD"""
        # 返回: {"cheat": Path, "csd": Path, ...}
    
    def download_apktool(self) -> Path:
        """下载 apktool"""
    
    def download_apksign(self) -> Path:
        """下载签名工具"""
```

---

#### 4. warmup.py - 资源预热

**职责**：提前下载并解压美化资源

**关键类**：

```python
class ResourceWarmer:
    """资源预热器"""
    
    def warmup_all(self) -> VersionRegistry:
        """预热所有资源"""
        self._warmup_dolp_packs()
        self._warmup_au_packs()
        return self.registry
    
    def _warmup_dolp_packs(self):
        """预热 DoL+ 图包"""
    
    def _warmup_au_packs(self):
        """预热 AU 变体"""
```

---

#### 5. build.py - 核心构建逻辑

**职责**：实现 ZIP 和 APK 构建

**关键类**：

```python
@dataclass
class BuildTask:
    """构建任务定义"""
    pack_type: str       # zip 或 apk
    mod_code: int        # MOD 代码
    is_polyfill: bool    # 是否 polyfill
    version: LyraVersion
    paths: BuildPaths

class BaseBuilder(ABC):
    """构建器基类"""
    
    @abstractmethod
    def build(self) -> BuildResult:
        """执行构建"""

class ZipBuilder(BaseBuilder):
    """ZIP 构建器"""
    
    def build(self) -> BuildResult:
        self._copy_from_base()
        self._apply_mods()
        self._create_archive()

class ApkBuilder(BaseBuilder):
    """APK 构建器"""
    
    def build(self) -> BuildResult:
        self._copy_from_base()
        self._apply_mods()
        self._recompile()
        self._sign()

def build_single(task: BuildTask) -> BuildResult:
    """构建单个任务（进程入口）"""
```

---

#### 6. parallel.py - 并行构建管理

**职责**：协调多进程并行构建

**关键类**：

```python
@dataclass
class ParallelBuildConfig:
    """并行构建配置"""
    pack_types: list[str]
    version: LyraVersion
    max_workers: int
    include_polyfill: bool

class ParallelBuilder:
    """并行构建管理器"""
    
    def build_all(self) -> tuple[int, int]:
        """并行构建所有组合"""
        # 返回: (成功数, 失败数)

def build_all_parallel(...) -> tuple[int, int]:
    """便捷函数：并行构建"""
```

---

#### 7. combo.py - MOD 组合计算

**职责**：根据配置计算有效组合

**关键类**：

```python
@dataclass
class ModCombination:
    """MOD 组合"""
    code: int               # MOD 代码
    binary: str            # 二进制表示
    display_name: str      # 显示名称
    is_recommended: bool   # 是否推荐

class CombinationCalculator:
    """组合计算器"""
    
    def get_combinations(self) -> list[ModCombination]:
        """获取所有有效组合"""
    
    def _check_dependencies(self, code: int) -> bool:
        """检查依赖关系"""
    
    def _check_exclusive_groups(self, code: int) -> bool:
        """检查互斥规则"""
```

---

### 代码风格

#### Python 代码规范

遵循 **PEP 8** 和项目约定：

```python
# 1. 导入顺序
import logging          # 标准库
from pathlib import Path

import requests         # 第三方库

from .config import ModCode    # 本地模块
from .utils import extract_zip

# 2. 类型注解
def download_file(url: str, dest: Path) -> bool:
    """下载文件"""
    ...

# 3. 文档字符串（Google 风格）
def build_single(task: BuildTask) -> BuildResult:
    """
    构建单个任务
    
    Args:
        task: 构建任务定义
    
    Returns:
        构建结果
    
    Raises:
        RuntimeError: 构建失败时
    """
    ...

# 4. 日志使用
logger = logging.getLogger(__name__)
logger.info("开始构建...")
logger.debug(f"Task: {task}")
logger.error(f"失败: {error}")

# 5. 异常处理
try:
    result = dangerous_operation()
except SpecificError as e:
    logger.error(f"操作失败: {e}")
    raise RuntimeError("无法继续") from e
```

#### 命名约定

```python
# 模块名：小写+下划线
# config_loader.py, gen_page.py

# 类名：大驼峰
class BuildPaths:
class ZipBuilder:

# 函数/方法：小写+下划线
def download_file():
def _apply_besc():  # 私有方法前缀 _

# 常量：大写+下划线
MAX_WORKERS = 8
DEFAULT_TIMEOUT = 30

# 变量：小写+下划线
mod_code = 3
output_path = Path("output")
```

---

### 测试

#### 运行测试

```bash
# 安装测试依赖
pip install pytest pytest-cov

# 运行所有测试
pytest tests/

# 运行特定测试文件
pytest tests/test_config.py

# 带覆盖率
pytest --cov=lyra tests/

# 详细输出
pytest -v tests/
```

#### 编写测试

```python
# tests/test_example.py
import pytest
from pathlib import Path
from lyra.paths import BuildPaths

def test_build_paths_default():
    """测试默认路径"""
    paths = BuildPaths()
    assert paths.workspace == Path(".")
    assert paths.output_dir == Path("output")

def test_build_paths_custom():
    """测试自定义工作目录"""
    paths = BuildPaths(workspace=Path("/custom"))
    assert paths.base_dir == Path("/custom/base")

@pytest.fixture
def temp_workspace(tmp_path):
    """临时工作目录 fixture"""
    return BuildPaths(workspace=tmp_path)

def test_with_fixture(temp_workspace):
    """使用 fixture 的测试"""
    temp_workspace.ensure_dirs()
    assert temp_workspace.base_dir.exists()
```

---

### 贡献流程

#### 1. Fork 和克隆

```bash
# Fork 仓库到你的账号
# 然后克隆
git clone https://github.com/YOUR_USERNAME/Lyra.git
cd Lyra

# 添加上游仓库
git remote add upstream https://github.com/DoL-Lyra/Lyra.git
```

#### 2. 创建功能分支

```bash
# 同步最新代码
git checkout main
git pull upstream main

# 创建功能分支
git checkout -b feature/add-new-mod
```

#### 3. 开发和测试

```bash
# 进行修改
# ...

# 运行测试
pytest tests/

# 检查代码风格（可选）
pip install black isort
black lyra/
isort lyra/
```

#### 4. 提交更改

```bash
# 添加文件
git add lyra/new_file.py config/features.toml

# 提交（使用清晰的提交信息）
git commit -m "feat: 添加新 MOD 支持

- 在 features.toml 添加 NewMod 定义
- 实现 NewMod 构建逻辑
- 添加单元测试
"
```

**提交信息约定**：

```
<type>(<scope>): <subject>

<body>

<footer>
```

类型：

- `feat`: 新功能
- `fix`: 修复 bug
- `docs`: 文档更新
- `style`: 代码格式（不影响功能）
- `refactor`: 重构
- `test`: 添加测试
- `chore`: 构建/工具配置

示例：

```
feat(build): 添加新 MOD 支持

实现了 NewMod 的构建逻辑，包括：
- 资源下载和解压
- 文件复制到游戏目录
- 配置文件生成

Closes #123
```

#### 5. 推送和创建 PR

```bash
# 推送到你的 fork
git push origin feature/add-new-mod

# 在 GitHub 上创建 Pull Request
# 填写 PR 描述，说明改动内容
```

#### 6. 代码审查

- 等待维护者审查
- 根据反馈进行修改
- 保持分支更新

```bash
# 同步上游更改
git fetch upstream
git rebase upstream/main

# 强制推送（如果已 push 过）
git push origin feature/add-new-mod --force-with-lease
```

---

### 发布流程

#### 1. 更新版本号

```python
# lyra/__init__.py
__version__ = "2.1.0"
```

#### 2. 更新 CHANGELOG

```markdown
# CHANGELOG.md

## [2.1.0] - 2026-01-21

### Added
- 新增 NewMod 支持
- 添加自动清理临时文件功能

### Changed
- 优化并行构建性能
- 更新依赖版本

### Fixed
- 修复 APK 签名失败问题
```

#### 3. 创建 Tag

```bash
# 创建 annotated tag
git tag -a v2.1.0 -m "Release v2.1.0

主要更新：
- 新增 NewMod 支持
- 优化并行构建性能
- 修复若干 bug
"

# 推送 tag
git push upstream v2.1.0
```

#### 4. GitHub Actions 自动发布

Tag 推送后，GitHub Actions 会自动：

1. 运行测试
2. 执行完整构建
3. 创建 GitHub Release
4. 上传构建产物
5. 生成下载页面

---

### 最佳实践

1. **模块化设计**：每个模块职责单一
2. **配置驱动**：避免硬编码，使用配置文件
3. **类型注解**：所有公开函数添加类型注解
4. **错误处理**：明确的异常类型和错误信息
5. **日志记录**：关键步骤添加日志
6. **测试覆盖**：新功能必须有测试
7. **文档同步**：代码变更同步更新文档

---

## 许可证

本项目基于 **GPL-3.0** 协议开源。

---

## 相关链接

- **GitHub 仓库**：<https://github.com/DoL-Lyra/Lyra>
- **下载站**：<https://dol-lyra.github.io/hub/>
- **汉化仓库**：<https://github.com/Eltirosto/Degrees-of-Lewdity-Chinese-Localization>
- **问题反馈**：<https://github.com/DoL-Lyra/Lyra/issues>
- **讨论区**：<https://github.com/DoL-Lyra/Lyra/discussions>

---

## 贡献者

感谢所有为本项目做出贡献的开发者！

[![Contributors](https://contrib.rocks/image?repo=DoL-Lyra/Lyra)](https://github.com/DoL-Lyra/Lyra/graphs/contributors)

---

## 更新日志

### v2.0.0 (2026-01-21)

**重大重构**：

- 完全重写构建系统架构
- 引入四阶段 CI 流程（prepare → warmup → build → page）
- 实现资源预热机制，解决并行构建冲突
- 配置驱动的 MOD 组合管理
- 统一版本信息管理
- 优化并行构建性能

**API 变更**：

- 移除 `build.py` 和 `scripts/ci.py`
- 统一使用 `main.py` 作为入口
- 新增 `warmup` 命令
- 修改 `build` 命令参数

**详情**：参见 CHANGELOG.md

---

如有问题或建议，欢迎提交 Issue 或 Pull Request！
