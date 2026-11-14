# DOL-X 当前项目状态

**更新日期：2026-11-14**

## 稳定版

当前稳定版为 [v0.5.11.9-1.0.0a-1014](https://github.com/XFoxLG/DOL-X/releases/tag/v0.5.11.9-1.0.0a-1014)，提供基础版、AU-F、AU-M、AU-A 的 ZIP 与 APK。历史版本见 [Releases](https://github.com/XFoxLG/DOL-X/releases)。

| 组件 | 1014 版本 |
|---|---|
| 游戏 / 汉化 | 0.5.11.9 / 1.0.0a |
| 秋枫白桦框架 | 4.1.14 |
| 作弊拓展 | 1.20 |
| 更长遭遇战 / 言灵作弊集 | 1.0.1 / 1.0.1 |
| 旧版图片名称适配 | 1.0.3-plusV1.1 |
| 更多恋人 | 0.1.7.0 |

AU-F 在 MuMu 12（Android 12）上验证了换脸、桌宠、作弊菜单、存读档和开局流程；基础版、AU-M、AU-A 的历史发布仅有构建及打包内容检查。详细范围与已知问题见 [1014 说明](release-notes/v0.5.11.9-1.0.0a-1014.md)。

## 十一月候选

候选采用正式中文 `0.5.12.13-chs-1.0.1a`、MapleBirch `5.6.2`、原作者作弊拓展 `1.20.3.1`。三个 AU 版本采用 AU Face `1.2.16`，模型图片包分别为 F `0.9.3`、M `0.4.2`、A `0.1.1`。4.x 保留回退用途。

候选尚未完成安卓验收，当前稳定入口保持 1014。地点图像修复已加入兼容源码，尚待完整游戏确认；模拟器启动、读档与显示检查继续进行。

## 上游与来源

Lyra 的 [1004.1](https://github.com/DoL-Lyra/Lyra/releases/tag/v0.5.12.13-1.0.1a-1004.1) 为 0.5.12.13 预发布，提供 AU-F、AU-M、AU-A。同步核对包括默认分支、正式发行与预发布。

- [正式汉化](https://github.com/Eltirosto/Degrees-of-Lewdity-Chinese-Localization)
- [第三方资源说明](DISTRIBUTION_POLICY.md)
- [模组附件归档](https://github.com/XFoxLG/DOL-X-Mirrors)
- [上游同步策略](../UPSTREAM_FRIENDLY_STRATEGY.md)

## 0.5.11.9 验证记录

以下结论仅对应所列历史组合。

<a id="au-face-shim-ab-2026-10-13"></a>

### AU Face shim A/B（2026-10-13）

MapleBirch 4.1.14 与 AU Face 1.2.8 的取图兼容调整改变了解析路径。单参数调用保持一致；四个脸型变体的雀斑、泪痕及组合状态对照未观察到画布像素变化。

记录为 `ab_verdict = no_visual_change`、`defect_status = accepted_upstream`、`defect_visual_status = visual_incomplete`。社区图片映射与变体间相同素材解释了此次对照结果；这次调整未证明视觉修复。证据为画布与加载资源对照，不替代人工视觉审查。

<a id="story-graph-05119"></a>

### 0.5.11.9 剧情链接检查

`Estate Manor Approach Finish` 引用的 `Estate Manor Intro Entrance` 与 `Estate Manor Approach Defeat` 在对应原版源码中缺少定义。配置记录见 [剧情图已知问题](../config/accepted-upstream-graph-defects.toml)，源码与复测说明见 [自动玩家文档](AUTOMATED_GAMEPLAY_EXPLORER.md)。

构建、辅助场景扫描与实际游玩分别记录；历史结果不作为新候选的验收结果。
