"""
配置管理模块

集中管理 MOD 代码定义。
"""

from enum import IntFlag


class ModCode(IntFlag):
    """MOD代码位标志定义"""

    BESC = 1  # BEEESSS社区精灵合集
    CHEAT = 2  # 作弊功能
    CSD = 4  # CSD
    SIDEVIEW_BJ = 8  # BJ特写
    SIDEVIEW_KR = 16  # KR特写
    SIDEVIEW_HIKARI = 32  # Hikari特写
    WAX = 64  # WAX美化
    SUSATO = 128  # Susato模型
    UCB = 256  # 通用战斗美化
    SIDEVIEW_GOOSE = 512  # Goose特写
    AU_FEMALE = 1024  # AU女性
    AU_MALE = 2048  # AU男性
    AU_ANDROGYNOUS = 4096  # AU双性
    MORE_LOVE = 8192  # 更多恋人
    CUSTOM_SPELLBOOK = 16384  # 自定义魔法书
    CHEAT_EXTENDED_MAPLEBIRCH = 32768  # cheatExtended + maplebirch
    CUSTOM_HAIR = 65536  # 自定义染发
    MAE_PICVARY = 131072  # NPC侧边栏头像
    MAPLEBIRCH_EXPANSION = 262144  # maplebirch扩展包
    GUIDE_TO_ME = 524288  # 控制NPC嘴部
    BUNNY_TRANSFORMATION = 1048576  # 变身兔兔
    NEOUI_PATCH = 2097152  # NeoUI Patch
    NPC_SOCIAL_ICON = 4194304  # NPC社交栏头像
    DOLI = 8388608  # D.O.L.I（AI 对话/战斗文本增强，需玩家自填 API key）

    @classmethod
    def from_string(cls, code_str: str) -> tuple["ModCode", bool]:
        """
        从字符串解析MOD代码

        Args:
            code_str: MOD代码字符串，可以是数字或 "polyfill-数字" 格式

        Returns:
            (ModCode, is_polyfill) 元组
        """
        is_polyfill = False
        if code_str.startswith("polyfill-"):
            is_polyfill = True
            code_str = code_str.split("-")[1]

        return cls(int(code_str)), is_polyfill

    def get_suffix(self) -> str:
        """获取基于MOD代码的文件名后缀"""
        suffix_parts = []

        if self & ModCode.BESC:
            suffix_parts.append("besc")
        if self & ModCode.SUSATO:
            suffix_parts.append("susato")
        if self & ModCode.SIDEVIEW_BJ:
            suffix_parts.append("sideviewbj")
        if self & ModCode.SIDEVIEW_KR:
            suffix_parts.append("sideviewkr")
        if self & ModCode.SIDEVIEW_HIKARI:
            suffix_parts.append("hikari")
        if self & ModCode.SIDEVIEW_GOOSE:
            suffix_parts.append("goose")
        if self & ModCode.AU_FEMALE:
            suffix_parts.append("au-f")
        if self & ModCode.AU_MALE:
            suffix_parts.append("au-m")
        if self & ModCode.AU_ANDROGYNOUS:
            suffix_parts.append("au-a")
        if self & ModCode.UCB:
            suffix_parts.append("ucb")
        if self & ModCode.MORE_LOVE:
            suffix_parts.append("more-love")
        if self & ModCode.CUSTOM_SPELLBOOK:
            suffix_parts.append("custom-spellbook")
        if self & ModCode.CHEAT_EXTENDED_MAPLEBIRCH:
            suffix_parts.append("cheat-extended-maplebirch")
        if self & ModCode.CUSTOM_HAIR:
            suffix_parts.append("custom-hair")
        if self & ModCode.MAE_PICVARY:
            suffix_parts.append("mae-picvary")
        if self & ModCode.MAPLEBIRCH_EXPANSION:
            suffix_parts.append("expansion")
        if self & ModCode.GUIDE_TO_ME:
            suffix_parts.append("guide-to-me")
        if self & ModCode.BUNNY_TRANSFORMATION:
            suffix_parts.append("bunny-transformation")
        if self & ModCode.NEOUI_PATCH:
            suffix_parts.append("neoui-patch")
        if self & ModCode.NPC_SOCIAL_ICON:
            suffix_parts.append("npc-social-icon")
        if self & ModCode.DOLI:
            suffix_parts.append("doli")

        return "-".join(suffix_parts) if suffix_parts else ""

    def get_short_suffix(self) -> str:
        """获取精简文件名后缀。

        当前稳定矩阵的 4 个包仅在体型资源上有差异（其余必选 mod 完全相同），
        因此文件名只需保留区分体型的短标识，避免把公共 mod 全部铺开导致名称
        冗长。具体含义由下载说明页承载。

        - 含 AU 女性 -> au-f
        - 含 AU 男性 -> au-m
        - 含 AU 双性 -> au-a
        - 不含任何 AU -> base
        """
        if self & ModCode.AU_FEMALE:
            return "au-f"
        if self & ModCode.AU_MALE:
            return "au-m"
        if self & ModCode.AU_ANDROGYNOUS:
            return "au-a"
        return "base"


def get_build_matrix() -> list[str]:
    """
    获取构建矩阵（用于GitHub Actions）

    动态计算有效的MOD组合代码列表。
    """
    from .combo import get_default_build_codes

    return get_default_build_codes()
