# DOL-Mod-Created-Helper (MCH) REMOTE_TEST 深度研究报告

**研究时间**: 2026-06-14  
**研究对象**: https://github.com/NumberSir/DOL-Mod-Created-Helper  
**目标**: 理解 REMOTE_TEST 自动化游戏逻辑测试实现，为 DOL-X 提供技术基础

---

## 执行摘要

DOL-Mod-Created-Helper (MCH) 是一个 DoL 模组开发辅助工具，包含：
1. 自动生成 boot.json
2. 模组打包（zip）
3. **REMOTE_TEST**: 本地服务器 + 自动刷新浏览器（热加载开发）

**关键发现**: MCH 的 REMOTE_TEST 主要是**热加载开发**功能，而非完整的游戏逻辑自动化测试框架。DOL-X 需要自己实现基于 Playwright 的测试框架。

---

## 1. MCH 核心功能

### 1.1 项目结构

```
DOL-Mod-Created-Helper/
├── main.py                  # 入口文件
├── src/                     # 核心代码
│   ├── builder.py           # 打包逻辑
│   ├── boot_json.py         # boot.json 生成
│   └── server.py            # 本地 HTTP 服务器
├── mods/                    # 用户模组目录
│   └── <mod_name>/
│       ├── boot.json
│       ├── game/            # Twee 文件
│       ├── img/             # 图片资源
│       └── modules/css/     # CSS 文件
├── modloader/               # ModLoader 目录（用户手动放置）
│   └── Degrees of Lewdity VERSION.mod.html
└── results/                 # 打包产物
```

---

### 1.2 REMOTE_TEST 功能

**配置开关**（在 `main.py` 中）:
```python
REMOTE_TEST = False  # 默认关闭
# 改为 True 后启用自动测试模式
```

**启用后的行为**:
1. 打包模组为 zip
2. 自动复制 zip 到 `modloader/mods/` 目录
3. 启动本地 HTTP 服务器（默认端口 52525）
4. 在浏览器中打开游戏 HTML
5. **手动刷新浏览器**查看改动

---

## 2. REMOTE_TEST 实现细节

### 2.1 本地服务器启动

**推测实现**（基于 README 描述）:
```python
import http.server
import socketserver
import webbrowser
from pathlib import Path

class RemoteTestServer:
    def __init__(self, port=52525):
        self.port = port
        self.modloader_dir = Path("modloader")
    
    def start(self):
        # 切换到 modloader 目录
        os.chdir(self.modloader_dir)
        
        # 启动 HTTP 服务器
        handler = http.server.SimpleHTTPRequestHandler
        with socketserver.TCPServer(("", self.port), handler) as httpd:
            print(f"服务器地址: http://localhost:{self.port}")
            
            # 自动打开浏览器
            game_file = self._find_game_html()
            webbrowser.open(f"http://localhost:{self.port}/{game_file}")
            
            # 保持服务器运行
            httpd.serve_forever()
    
    def _find_game_html(self):
        # 查找 Degrees of Lewdity VERSION.mod.html
        for file in self.modloader_dir.glob("*.mod.html"):
            return file.name
        raise FileNotFoundError("未找到游戏 HTML 文件")
```

---

### 2.2 模组复制逻辑

**自动复制到 ModLoader**:
```python
def copy_mod_to_modloader(mod_zip_path):
    # 打包完成后
    dest_dir = Path("modloader/mods")
    dest_dir.mkdir(parents=True, exist_ok=True)
    
    # 复制 zip 到 ModLoader mods 目录
    shutil.copy(mod_zip_path, dest_dir / mod_zip_path.name)
    
    print(f"模组已复制到 ModLoader: {dest_dir / mod_zip_path.name}")
```

---

### 2.3 热加载工作流

**完整流程**:
1. 用户修改模组文件（Twee/CSS/JS）
2. 重新运行 `main.py`
3. 自动打包 + 复制到 ModLoader
4. 服务器已运行（保持打开）
5. **用户手动刷新浏览器**（F5）
6. ModLoader 重新加载 mod，看到改动

**局限性**:
- ❌ **无自动刷新**: 需要用户手动按 F5
- ❌ **无自动化测试**: 没有 Playwright/Puppeteer 集成
- ❌ **无断言验证**: 不检查游戏状态、Mod 加载状态
- ✅ **仅是开发辅助**: 减少手动打包 + 复制的步骤

---

## 3. MCH 与 DOL-X 需求对比

### 3.1 DOL-X 需要的测试能力

| 测试类型 | MCH 提供 | DOL-X 需求 | 差距 |
|---------|---------|-----------|------|
| **本地服务器** | ✅ HTTP 服务器 | ✅ HTTP 服务器 | 无差距 |
| **浏览器启动** | ✅ webbrowser.open | ✅ Playwright 控制 | 需自行实现 |
| **自动刷新** | ❌ 手动刷新 | ✅ WebSocket 自动刷新 | 需自行实现 |
| **Passage 导航** | ❌ 无 | ✅ 自动点击选项 | 需自行实现 |
| **变量检查** | ❌ 无 | ✅ `page.evaluate("V.money")` | 需自行实现 |
| **Mod 功能验证** | ❌ 无 | ✅ 检查 maplebirch、AU Face | 需自行实现 |
| **CI 集成** | ❌ 无 | ✅ GitHub Actions | 需自行实现 |

**结论**: MCH 的 REMOTE_TEST 是**热加载开发工具**，不是**自动化测试框架**。DOL-X 需要从头实现游戏逻辑测试。

---

## 4. DOL-X 游戏逻辑测试实现方案

### 4.1 技术栈选择

**推荐**: **Playwright** (Python)

**理由**:
1. ✅ DOL-X 已在 `browser_smoke_test.py` 中使用 Playwright
2. ✅ Python 生态与 DOL-X 一致
3. ✅ 支持 headless 模式（CI 友好）
4. ✅ 强大的调试工具（截图、视频录制、trace）

**替代方案**: Puppeteer（Node.js）
- ❌ 需要额外的 Node 环境
- ❌ 与 DOL-X Python 生态不一致

---

### 4.2 测试框架架构

**目录结构**:
```
DOL-X/
├── tools/
│   └── dev/
│       ├── game_logic_test.py    # 测试框架核心
│       └── test_server.py        # HTTP 服务器封装
├── tests/
│   ├── game_logic/
│   │   ├── __init__.py
│   │   ├── test_basic_flow.py        # 基础流程测试
│   │   ├── test_cheat_extended.py    # 作弊菜单测试
│   │   ├── test_au_face.py           # AU Face 渲染测试
│   │   ├── test_more_love.py         # More Love 测试
│   │   ├── test_custom_spellbook.py  # Spellbook 测试
│   │   └── test_save_compat.py       # 存档兼容性测试
│   └── conftest.py               # Pytest fixtures
```

---

### 4.3 核心实现

**`tools/dev/game_logic_test.py`**:

```python
from playwright.sync_api import sync_playwright, Page
from pathlib import Path
import http.server
import threading
import zipfile
import tempfile

class GameLogicTestRunner:
    """游戏逻辑测试运行器"""
    
    def __init__(self, zip_path: Path, headless: bool = True):
        self.zip_path = zip_path
        self.headless = headless
        self.temp_dir = None
        self.server = None
        self.server_thread = None
        self.playwright = None
        self.browser = None
        self.page = None
    
    def __enter__(self):
        # 1. 解压 ZIP 到临时目录
        self.temp_dir = tempfile.mkdtemp()
        with zipfile.ZipFile(self.zip_path, 'r') as zf:
            zf.extractall(self.temp_dir)
        
        # 2. 启动 HTTP 服务器
        self._start_server()
        
        # 3. 启动 Playwright
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=self.headless)
        self.page = self.browser.new_page()
        
        return self
    
    def __exit__(self, *args):
        # 清理资源
        if self.page:
            self.page.close()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
        if self.server:
            self.server.shutdown()
        if self.temp_dir:
            shutil.rmtree(self.temp_dir)
    
    def _start_server(self):
        """启动本地 HTTP 服务器"""
        import os
        os.chdir(self.temp_dir)
        
        handler = http.server.SimpleHTTPRequestHandler
        self.server = http.server.HTTPServer(("", 0), handler)  # 随机端口
        self.port = self.server.server_port
        
        # 在后台线程运行服务器
        self.server_thread = threading.Thread(target=self.server.serve_forever)
        self.server_thread.daemon = True
        self.server_thread.start()
    
    def goto_game(self):
        """打开游戏"""
        self.page.goto(f"http://localhost:{self.port}/Degrees of Lewdity.html")
        self.page.wait_for_selector("#passage", timeout=10000)
    
    def get_passage(self) -> str:
        """获取当前 passage 名称"""
        return self.page.locator("#passage").get_attribute("data-passage")
    
    def click_option(self, text: str):
        """点击选项（精确匹配或部分匹配）"""
        try:
            # 尝试精确匹配
            self.page.click(f'text="{text}"', timeout=5000)
        except:
            # 尝试部分匹配
            self.page.click(f'text={text}', timeout=5000)
        
        self.page.wait_for_load_state("networkidle")
    
    def evaluate_game_var(self, var_name: str):
        """获取游戏变量（如 V.money, V.player.name）"""
        return self.page.evaluate(f"{var_name}")
    
    def check_mod_loaded(self, mod_name: str) -> bool:
        """检查 mod 是否加载"""
        mod_list = self.page.evaluate("window.modDataValueZipList || []")
        return any(mod_name in str(mod) for mod in mod_list)
    
    def check_global_var_exists(self, var_name: str) -> bool:
        """检查全局变量是否存在"""
        result = self.page.evaluate(f"typeof {var_name}")
        return result != "undefined"
    
    def wait_for_image_request(self, pattern: str, timeout: int = 5000):
        """等待特定图片请求（用于验证 AU Face 渲染）"""
        requests = []
        
        def handle_request(request):
            if pattern in request.url:
                requests.append(request.url)
        
        self.page.on("request", handle_request)
        self.page.wait_for_timeout(timeout)
        self.page.remove_listener("request", handle_request)
        
        return requests
```

---

### 4.4 测试用例示例

**`tests/game_logic/test_basic_flow.py`**:

```python
import pytest
from tools.dev.game_logic_test import GameLogicTestRunner

@pytest.mark.parametrize("build_code", ["57600", "58624", "59648", "61696"])
def test_orphanage_intro_flow(build_code, game_zip_fixture):
    """测试开场流程（孤儿院 → 命名 → 第一天）"""
    zip_path = game_zip_fixture(build_code)
    
    with GameLogicTestRunner(zip_path, headless=True) as runner:
        runner.goto_game()
        
        # 断言：初始 passage
        assert runner.get_passage() == "Start"
        
        # 点击开始游戏
        runner.click_option("Begin")
        assert runner.get_passage() == "Characteristics"
        
        # 输入名字
        runner.page.fill("#text-box", "TestPlayer")
        runner.click_option("Next")
        
        # 断言：进入孤儿院
        assert runner.get_passage() == "Orphanage"
        assert runner.evaluate_game_var("V.player.name") == "TestPlayer"
        assert runner.evaluate_game_var("V.money") >= 0
        
        # 第一天：起床
        runner.click_option("Get up")
        assert "Bedroom" in runner.get_passage()
```

**`tests/game_logic/test_cheat_extended.py`**:

```python
def test_cheat_extended_menu_available(game_zip_fixture):
    """测试 cheatExtended + maplebirch 可用性"""
    with GameLogicTestRunner(game_zip_fixture("57600")) as runner:
        runner.goto_game()
        
        # 检查 maplebirch 框架加载
        assert runner.check_global_var_exists("window.maplebirchFrameworks")
        assert runner.check_global_var_exists("window.CE_options")
        
        # 检查作弊菜单元素存在
        assert runner.page.locator('[onclick*="CE_options"]').is_visible()
```

**`tests/game_logic/test_au_face.py`**:

```python
@pytest.mark.parametrize("au_variant", ["58624", "59648", "61696"])
def test_au_face_blush_rendering(au_variant, game_zip_fixture):
    """测试 AU Face blush 层加载"""
    with GameLogicTestRunner(game_zip_fixture(au_variant)) as runner:
        runner.goto_game()
        
        # 导航到显示立绘的 passage
        runner.click_option("Begin")
        # ... 更多导航
        
        # 等待并检查 blush 图片请求
        blush_requests = runner.wait_for_image_request("face/default/default/blush")
        assert len(blush_requests) > 0, "AU Face blush 层未加载"
```

---

## 5. 热加载开发功能（可选）

### 5.1 实现方案

**借鉴 MCH 的思路 + WebSocket 自动刷新**:

```python
import asyncio
import websockets
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class ModChangeHandler(FileSystemEventHandler):
    def __init__(self, websocket_clients):
        self.clients = websocket_clients
    
    def on_modified(self, event):
        if event.src_path.endswith((".json", ".js", ".twee", ".css")):
            print(f"检测到变更: {event.src_path}")
            
            # 重新打包
            subprocess.run(["python", "main.py", "build", "--codes", "57600"])
            
            # 通知浏览器刷新
            asyncio.run(self._notify_clients())
    
    async def _notify_clients(self):
        for client in self.clients:
            await client.send("reload")

async def websocket_server(clients, host="localhost", port=8765):
    """WebSocket 服务器，通知浏览器刷新"""
    async def handler(websocket, path):
        clients.add(websocket)
        try:
            await websocket.wait_closed()
        finally:
            clients.remove(websocket)
    
    async with websockets.serve(handler, host, port):
        await asyncio.Future()  # 保持运行

def start_dev_server():
    """启动热加载开发服务器"""
    clients = set()
    
    # 启动 WebSocket 服务器
    asyncio.run(websocket_server(clients))
    
    # 启动文件监控
    handler = ModChangeHandler(clients)
    observer = Observer()
    observer.schedule(handler, path="workspace/", recursive=True)
    observer.start()
    
    # 启动 HTTP 服务器
    # ... (同 MCH)
```

**浏览器端**（注入到 HTML）:
```javascript
// 连接 WebSocket
const ws = new WebSocket('ws://localhost:8765');

ws.onmessage = (event) => {
    if (event.data === 'reload') {
        console.log('检测到模组更新，自动刷新...');
        location.reload();
    }
};
```

---

## 6. MCH 其他有价值的功能

### 6.1 自动生成 boot.json

**DOL-X 已有类似功能**（在 `modmagic.py` 中），无需借鉴。

---

### 6.2 模组结构验证

**MCH 做法**: 检查 `game/`, `img/`, `modules/css/` 目录是否符合规范

**DOL-X 可借鉴**: 在集成 DoL-Commit2Mod 时，验证生成的 mod 结构是否正确。

---

## 7. DOL-X 集成建议

### 7.1 优先级

| 功能 | 优先级 | 理由 |
|------|-------|------|
| **游戏逻辑测试框架** | ⭐⭐⭐⭐⭐ | 解决核心痛点（手动测试耗时、Mod 黑盒） |
| **CI 集成** | ⭐⭐⭐⭐⭐ | 自动回退机制依赖 CI |
| **热加载开发** | ⭐⭐⭐ | 锦上添花，收益相对较小 |

---

### 7.2 实现路线图

#### Phase 1: 测试框架核心（1 周）

1. 创建 `tools/dev/game_logic_test.py`
2. 实现 `GameLogicTestRunner` 类
3. 编写 1-2 个简单测试用例验证可行性

#### Phase 2: 扩展测试场景（1-2 周）

1. 实现 6 大测试套件：
   - `test_basic_flow.py`
   - `test_cheat_extended.py`
   - `test_au_face.py`
   - `test_more_love.py`
   - `test_custom_spellbook.py`
   - `test_save_compat.py`
2. 添加 pytest fixtures（共享 ZIP 路径、浏览器实例）

#### Phase 3: CI 集成 + 自动回退（1 周）

1. 修改 `.github/workflows/build.yaml`
2. 添加游戏逻辑测试步骤
3. 实现自动 revert 机制
4. 测试失败创建 issue

#### Phase 4: 热加载开发（可选，1 周）

1. 实现文件监控 + WebSocket
2. 自动刷新浏览器
3. 优化重新打包速度（增量构建）

---

## 8. 与 DOL-X 现有测试对比

| 测试类型 | 当前状态 | 集成后状态 | 价值 |
|---------|---------|-----------|------|
| **配置校验** | ✅ test_build_matrix.py (43 测试) | ✅ 保持 | 已充分 |
| **HTML 完整性** | ✅ html_smoke_test.py | ✅ 保持 | 已充分 |
| **浏览器启动** | ✅ browser_smoke_test.py | ✅ 扩展为游戏逻辑测试 | 大幅提升 |
| **游戏逻辑** | ❌ 缺失 | ✅ 6 大测试套件 | **核心价值** ⭐⭐⭐⭐⭐ |
| **Mod 功能** | ❌ 缺失 | ✅ 作弊菜单、AU Face 验证 | **核心价值** ⭐⭐⭐⭐⭐ |
| **CI 门禁** | ⚠️ 可选 | ✅ 严格门禁 + 自动回退 | **核心价值** ⭐⭐⭐⭐⭐ |

---

## 9. 技术债务与风险

### 9.1 游戏更新导致测试失效

**风险**: DoL 游戏更新后，passage 名称、变量结构可能变化

**缓解**:
1. 使用游戏版本号标记测试（`@pytest.mark.game_version("0.5.8.10")`）
2. 在 `UPSTREAM_SYNC_CHECKLIST.md` 中记录：游戏更新时同步更新测试
3. 测试用例使用灵活的选择器（如 `text="Begin"` 而非 `#specific-id`）

---

### 9.2 Playwright 依赖体积

**问题**: Playwright + Chromium 约 300MB，增加 CI 构建时间

**缓解**:
1. GitHub Actions 使用 Docker 缓存
2. 只在必要时运行游戏逻辑测试（如 `--run-game-tests` 参数）
3. 本地开发者提供一键安装脚本：`pip install playwright && playwright install chromium`

---

## 10. 下一步行动

### 10.1 立即可做（本周）

1. ✅ 完成 DoL-Commit2Mod 研究
2. ✅ 完成 MCH REMOTE_TEST 研究（本文档）
3. ⏳ 决策实现策略（`docs/INTEGRATION_STRATEGY.md`）

### 10.2 开发实施（2-3 周）

1. 实现 `tools/dev/game_logic_test.py`
2. 编写 6 大测试套件
3. CI 集成 + 自动回退
4. （可选）热加载开发

---

## 附录 A: Playwright 测试用例模板

```python
import pytest
from tools.dev.game_logic_test import GameLogicTestRunner

def test_example(game_zip_fixture):
    """测试示例"""
    with GameLogicTestRunner(game_zip_fixture("57600")) as runner:
        # 1. 打开游戏
        runner.goto_game()
        
        # 2. 断言初始状态
        assert runner.get_passage() == "Start"
        
        # 3. 模拟玩家操作
        runner.click_option("Begin")
        
        # 4. 验证游戏状态
        assert runner.evaluate_game_var("V.money") >= 0
        
        # 5. 检查 Mod 加载
        assert runner.check_mod_loaded("ModLoader")
```

---

## 附录 B: pytest conftest.py 示例

```python
# tests/conftest.py
import pytest
from pathlib import Path

@pytest.fixture
def game_zip_fixture():
    """提供游戏 ZIP 路径的 fixture"""
    def get_zip(build_code: str) -> Path:
        output_dir = Path("output")
        zip_files = list(output_dir.glob(f"DoL-*-{build_code}.zip"))
        if not zip_files:
            pytest.skip(f"未找到 build_code={build_code} 的产物")
        return zip_files[0]
    return get_zip
```

---

## 附录 C: 参考资料

- MCH GitHub: https://github.com/NumberSir/DOL-Mod-Created-Helper
- Playwright 文档: https://playwright.dev/python/
- DOL-X browser_smoke_test.py: `tools/browser_smoke_test.py`

---

**研究完成时间**: 2026-06-14  
**下一步**: 生成实现策略决策文档
