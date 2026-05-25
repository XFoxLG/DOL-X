"""
MOD组合计算模块

根据配置文件中的规则计算有效的MOD组合，用于批量构建和生成下载页面。
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import logging

from .config_loader import (
    Feature,
    CombinationsConfig,
    get_config_loader,
)

logger = logging.getLogger(__name__)


@dataclass
class ModCombination:
    """MOD组合"""

    code: int
    binary: str = ""
    display_name: str = ""
    is_recommended: bool = False
    is_polyfill: bool = False

    def __post_init__(self):
        if not self.binary:
            self.binary = format(self.code, "013b")

    def __lt__(self, other):
        return self.code < other.code

    def __eq__(self, other):
        if isinstance(other, ModCombination):
            return self.code == other.code and self.is_polyfill == other.is_polyfill
        return False

    def __hash__(self):
        return hash((self.code, self.is_polyfill))


class CombinationCalculator:
    """MOD组合计算器（配置驱动）"""

    def __init__(self, config_dir: Optional[Path] = None):
        """
        初始化计算器

        Args:
            config_dir: 配置目录路径，默认使用项目的 config 目录
        """
        self.loader = get_config_loader(config_dir)
        self._feature_map: dict[str, Feature] = {}
        self._bit_to_feature: dict[int, Feature] = {}
        self._build_feature_maps()

    def _build_feature_maps(self):
        """构建功能映射"""
        for feature in self.loader.features:
            self._feature_map[feature.id] = feature
            self._bit_to_feature[feature.bit] = feature

    @property
    def features(self) -> list[Feature]:
        """获取所有功能"""
        return self.loader.features

    @property
    def combinations_config(self) -> CombinationsConfig:
        """获取组合配置"""
        return self.loader.combinations

    @property
    def num_bits(self) -> int:
        """计算需要的位数"""
        if not self.features:
            return 13
        max_bit = max(f.bit for f in self.features)
        return max_bit.bit_length()

    def _has_feature(self, value: int, feature_id: str) -> bool:
        """检查组合中是否包含指定功能"""
        feature = self._feature_map.get(feature_id)
        if feature is None:
            return False
        return bool(value & feature.bit)

    def _has_bit(self, value: int, bit: int) -> bool:
        """检查指定位是否为1"""
        return bool(value & bit)

    def _check_dependencies(self, value: int) -> bool:
        """
        检查依赖关系

        Returns:
            True 如果所有依赖都满足，False 否则
        """
        for feature in self.features:
            if not self._has_bit(value, feature.bit):
                continue

            # 检查此功能的所有依赖
            for dep_id in feature.depends_on:
                if not self._has_feature(value, dep_id):
                    return False

        return True

    def _check_conflicts(self, value: int) -> bool:
        """
        检查冲突关系

        Returns:
            True 如果没有冲突，False 否则
        """
        for feature in self.features:
            if not self._has_bit(value, feature.bit):
                continue

            # 检查此功能的所有冲突
            for conflict_id in feature.conflicts_with:
                if self._has_feature(value, conflict_id):
                    return False

        return True

    def _should_skip(self, value: int) -> bool:
        """检查是否应该跳过此组合"""
        # 跳过 0
        if value == 0:
            return True

        # 检查必选功能
        for feature in self.features:
            if feature.required and not self._has_bit(value, feature.bit):
                return True

        # 检查跳过的功能
        for feature in self.features:
            if feature.skip and self._has_bit(value, feature.bit):
                return True

        # 检查依赖关系
        if not self._check_dependencies(value):
            return True

        # 检查冲突关系
        if not self._check_conflicts(value):
            return True

        # 检查黑名单
        if value in self.combinations_config.blacklist:
            return True

        return False

    def _get_display_name(self, code: int) -> str:
        """获取组合的显示名称"""
        if self.combinations_config.base_code and code == self.combinations_config.base_code:
            return "基础"

        # 仅包含作弊CSD的基础版本
        cheat_feature = self._feature_map.get("cheat_csd")
        if cheat_feature and code == cheat_feature.bit:
            return "基础"

        parts = []

        # 按位值从低到高排序，使得基础功能（如 BESC）排在前面
        sorted_features = sorted(self.features, key=lambda f: f.bit)

        for feature in sorted_features:
            if self._has_bit(code, feature.bit):
                # 跳过作弊CSD的显示（它始终存在）
                if feature.required:
                    continue
                if feature.name:
                    parts.append(feature.name)

        return "+".join(parts) if parts else "基础"

    def calculate(self, include_polyfill: bool = True) -> list[ModCombination]:
        """
        计算所有有效的MOD组合

        Args:
            include_polyfill: 是否包含polyfill版本

        Returns:
            有效组合列表
        """
        combinations = []
        config = self.combinations_config

        # 自用/精简构建可通过 build_codes 显式指定最终产物，避免
        # 自动组合规则在新增 feature 后生成不需要的版本。
        if config.build_codes:
            return self._calculate_explicit(include_polyfill=include_polyfill)

        # 遍历所有可能的组合
        max_value = 2**self.num_bits
        for i in range(max_value):
            if not self._should_skip(i):
                comb = ModCombination(
                    code=i,
                    display_name=self._get_display_name(i),
                    is_recommended=i in config.recommended,
                )
                combinations.append(comb)

        # 添加白名单
        existing_codes = {c.code for c in combinations}
        for code in config.whitelist:
            if code not in existing_codes:
                comb = ModCombination(
                    code=code,
                    display_name=self._get_display_name(code),
                    is_recommended=code in config.recommended,
                )
                combinations.append(comb)

        # 排序：推荐的放前面，然后按code排序
        combinations.sort(key=lambda x: (-x.is_recommended, x.code))

        # 添加polyfill版本
        if include_polyfill and config.polyfill_enabled:
            polyfill_comb = ModCombination(
                code=config.polyfill_code,
                display_name=self._get_display_name(config.polyfill_code) + "(兼容版)",
                is_recommended=False,
                is_polyfill=True,
            )
            combinations.insert(0, polyfill_comb)

        return combinations

    def _calculate_explicit(self, include_polyfill: bool = True) -> list[ModCombination]:
        """根据 combinations.toml 的 build_codes 生成精确构建列表。"""
        config = self.combinations_config
        combinations: list[ModCombination] = []
        seen: set[tuple[int, bool]] = set()

        for raw_code in config.build_codes:
            code_str = str(raw_code)
            is_polyfill = code_str.startswith("polyfill-")

            if is_polyfill:
                if not include_polyfill or not config.polyfill_enabled:
                    continue
                code_str = code_str[len("polyfill-") :]

            code = int(code_str)
            key = (code, is_polyfill)
            if key in seen:
                continue
            seen.add(key)

            display_name = self._get_display_name(code)
            if is_polyfill:
                display_name += "(兼容版)"

            combinations.append(
                ModCombination(
                    code=code,
                    display_name=display_name,
                    is_recommended=code in config.recommended,
                    is_polyfill=is_polyfill,
                )
            )

        return combinations

    def get_build_codes(self, include_polyfill: bool = True) -> list[str]:
        """
        获取用于构建的code列表（字符串格式）

        Args:
            include_polyfill: 是否包含polyfill版本

        Returns:
            code字符串列表，polyfill格式为 "polyfill-N"
        """
        combinations = self.calculate(include_polyfill=include_polyfill)
        codes = []

        for comb in combinations:
            if comb.is_polyfill:
                codes.append(f"polyfill-{comb.code}")
            else:
                codes.append(str(comb.code))

        return codes

    def to_string(self, include_polyfill: bool = False) -> str:
        """生成组合详情字符串（用于组合对照）

        Args:
            include_polyfill: 是否包含 polyfill 版本，默认不包含

        Returns:
            格式化的组合对照字符串
        """
        combinations = self.calculate(include_polyfill=False)  # 组合对照不包含 polyfill
        lines = []

        for comb in combinations:
            # 对于推荐版本，在显示名称上添加星号标记
            display_name = comb.display_name
            if comb.is_recommended:
                display_name = f"***{display_name}(推荐)***"

            rec = 1 if comb.is_recommended else 0
            # 格式：二进制: 0b11, 十进制: 3, 功能: ***BESC(推荐)***, 推荐： 1
            lines.append(
                f"二进制: {comb.binary:>15}, 十进制: {comb.code:>5}, "
                f"功能: {display_name}, 推荐： {rec}"
            )

        # 添加code列表
        sorted_combinations = sorted(combinations, key=lambda c: c.code)
        codes = [c.code for c in sorted_combinations]
        lines.append(f"{codes}")

        return "\n".join(lines)


def get_default_combinations(config_dir: Optional[Path] = None) -> list[ModCombination]:
    """获取默认的MOD组合列表"""
    calculator = CombinationCalculator(config_dir)
    return calculator.calculate()


def get_default_build_codes(config_dir: Optional[Path] = None) -> list[str]:
    """获取默认的构建code列表"""
    calculator = CombinationCalculator(config_dir)
    return calculator.get_build_codes()
