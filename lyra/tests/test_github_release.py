#!/usr/bin/env python3
"""
测试 get_github_release_asset 函数

直接调用函数并打印结果，从真实 GitHub API 获取数据。
"""

from lyra.utils import get_github_release_asset


def main():
    print("=" * 70)
    print("测试 get_github_release_asset 函数")
    print("=" * 70)

    # 测试数据来自 build.toml 中的配置
    test_cases = [
        ("AOKIUTAGE/UTAGEsDOL3.0", "AUfemale.model", "mod"),
        ("AOKIUTAGE/UTAGEsDOL3.0", "AUmale.model", "mod"),
        ("AOKIUTAGE/UTAGEsDOL3.0", "AUandrogynous.model", "mod"),
    ]

    for repo, asset_pattern, tag in test_cases:
        print(f"\n--- {asset_pattern} ---")
        print(f"Repo: {repo}")
        print(f"Tag:  {tag}")

        result = get_github_release_asset(
            repo=repo,
            asset_pattern=asset_pattern,
            tag=tag,
        )

        if result:
            print(f"Name:    {result.name}")
            print(f"Version: {result.version}")
            print(f"URL:     {result.url}")
        else:
            print("未找到匹配的资源")

    print("\n" + "=" * 70)
    print("测试完成")
    print("=" * 70)


if __name__ == "__main__":
    main()
