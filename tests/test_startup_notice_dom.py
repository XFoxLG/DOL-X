"""真实 DOM 回归：checkbox-gated 启动确认框必须先勾选再点确认。

CI run 37544629870：Maplebirch 框架欢迎框的 "I Understand" 按钮在未勾选
"我已阅读并理解上述说明" 时是惰性的，bootstrap 把 19 分钟预算全烧在重复
点击上。这里的两个用例用真实 Chromium 驱动 ``_startup_interaction_script``：
Maplebirch 表单能一次点掉；skipKeys 生效后重复按钮被跳过。

Playwright/Chromium 不可用时跳过（本地开发机允许没有浏览器）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tools import browser_smoke_test as bst
from tools import passage_sweep as ps

NOTICE_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { font-family: sans-serif; }
  #notice { border: 1px solid #999; padding: 12px; }
</style>
</head>
<body>
<div id="notice">
  <p>Maplebirch Framework provides loading, extension, and compatibility support for Degrees of Lewdity mods.</p>
  <div class="text-align-center">
    <label><input type="checkbox" id="checkbox--maplebirchnoticeverify"> I have read and understood the notice above</label><br>
    <div class="m-2"><button id="notice-confirm">I Understand</button></div>
  </div>
</div>
<script>
document.getElementById('notice-confirm').addEventListener('click', () => {
  const box = document.getElementById('checkbox--maplebirchnoticeverify');
  if (box && box.checked) {
    window.__accepted = true;
    document.getElementById('notice').remove();
  } else {
    window.__rejected = (window.__rejected || 0) + 1;
  }
});
</script>
</body>
</html>
"""

PLAIN_CONFIRM_HTML = """<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body>
<div id="startup-actions"><button id="plain-confirm">I Understand</button></div>
<script>
document.getElementById('plain-confirm').addEventListener('click', () => {
  window.__clicks = (window.__clicks || 0) + 1;
});
</script>
</body>
</html>
"""


def _startup_options(**extra: Any) -> dict[str, Any]:
    options: dict[str, Any] = {
        "password": None,
        "modalSelectors": list(bst.MODAL_BLOCKER_SELECTORS),
        "confirmLabels": list(bst.STARTUP_CONFIRM_LABELS),
        "consentLabels": list(bst.STARTUP_CONSENT_LABELS),
    }
    options.update(extra)
    return options


def _launch_page(playwright: Any, path: Path) -> Any:
    try:
        # 复用 sweep 的浏览器选择顺序（bundled Chromium → Chrome → Edge）。
        browser = ps._launch_browser(playwright, headless=True)
    except (Exception, SystemExit) as exc:  # noqa: BLE001 - environment dependent
        pytest.skip(f"playwright chromium unavailable: {exc}")
    page = browser.new_page()
    page.goto(path.as_uri())
    return browser, page


def test_framework_notice_ticks_checkbox_before_confirm(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    page_path = tmp_path / "notice.html"
    page_path.write_text(NOTICE_HTML, encoding="utf-8")

    with sync_api.sync_playwright() as playwright:
        browser, page = _launch_page(playwright, page_path)
        try:
            action = page.evaluate(
                bst._startup_interaction_script(), _startup_options()
            )
            assert action["action"] == "accept_framework_notice"
            assert action["clicked"] is True
            assert action["checkbox_checked"] is True
            assert action["button_text"] == "I Understand"
            assert page.evaluate("() => window.__accepted === true") is True
            assert page.evaluate("() => window.__rejected || 0") == 0
            assert page.evaluate("() => document.getElementById('notice') === null") is True
        finally:
            browser.close()


def test_skip_keys_block_repeated_page_confirm(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    page_path = tmp_path / "plain.html"
    page_path.write_text(PLAIN_CONFIRM_HTML, encoding="utf-8")

    with sync_api.sync_playwright() as playwright:
        browser, page = _launch_page(playwright, page_path)
        try:
            first = page.evaluate(
                bst._startup_interaction_script(), _startup_options()
            )
            assert first["action"] == "click_startup_control"
            assert first["clicked"] is True
            assert page.evaluate("() => window.__clicks") == 1

            skipped = page.evaluate(
                bst._startup_interaction_script(),
                _startup_options(skipKeys=["I Understand"]),
            )
            assert skipped["clicked"] is False
            assert skipped["reason"] == "all_candidates_skipped"
            assert page.evaluate("() => window.__clicks") == 1
        finally:
            browser.close()
