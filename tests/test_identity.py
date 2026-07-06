"""
自用整合包标识配置测试

验证 XFox 改名只影响构建产物名和 APK 用户可见信息。
"""

import pytest

from lyra.build import BuildTask, ZipBuilder
from lyra.config_loader import load_build_config
from lyra.gen_page import DownloadPageConfig
from lyra.version import LyraVersion


@pytest.mark.config
class TestIdentity:
    """自用整合包标识配置测试"""

    def test_identity_config_is_xfox(self):
        """验证构建标识配置为 XFox"""
        build_config = load_build_config()

        assert build_config.identity_name == "XFox"
        assert build_config.identity_apk_name == "DoL XFox"
        assert build_config.identity_package == "com.vrelnir.dol.xfox"

    def test_apk_replacements_use_xfox(self):
        """验证 APK 名称和包名替换为 XFox"""
        build_config = load_build_config()
        replacements = {
            (rule.file, rule.pattern): rule.replacement
            for rule in build_config.apk_replacements
        }

        assert replacements[("AndroidManifest.xml", '"com.vrelnir.dol"')] == (
            '"com.vrelnir.dol.xfox"'
        )
        assert replacements[("AndroidManifest.xml", '"com.vrelnir.dol_debug"')] == (
            '"com.vrelnir.dol.xfox"'
        )
        assert replacements[
            ("AndroidManifest.xml", '"com.vrelnir.dol.androidx-startup"')
        ] == '"com.vrelnir.dol.xfox.androidx-startup"'
        assert replacements[
            ("AndroidManifest.xml", '"com.vrelnir.dol_debug.androidx-startup"')
        ] == '"com.vrelnir.dol.xfox.androidx-startup"'
        assert replacements[("res/values/strings.xml", "DoL")] == "DoL XFox"
        assert replacements[("res/values/strings.xml", "Degrees of Lewdity")] == (
            "DoL XFox"
        )

    def test_output_name_uses_xfox_identity(self):
        """验证产物文件名使用 XFox 标识"""
        task = BuildTask(
            pack_type="zip",
            mod_code=1282,
            version=LyraVersion(dol_ver="0.5.8.10", chs_ver="3.1.3a", date="0401"),
        )
        output_name = ZipBuilder(task).get_output_name()

        assert output_name == "DoL-0.5.8.10-XFox-3.1.3a-au-f-0401.zip"
        assert "-Lyra-" not in output_name

    def test_download_page_filename_uses_xfox_identity(self):
        """验证下载页链接文件名与构建产物 identity 保持一致"""
        config = DownloadPageConfig(
            version="v0.5.8.10-3.1.3a-0401",
            github_owner="XFoxLG",
            github_repo="DOL-X",
        )

        filename = config.get_filename(1282, "zip")

        assert filename == "DoL-0.5.8.10-XFox-3.1.3a-au-f-0401.zip"
        assert "-Lyra-" not in filename
