# DOL-X 测试入口

配置和构建逻辑的回归测试位于 `tests/`，浏览器及安卓验证工具位于 `tools/`。

```bash
python -m pytest tests -q
python tools/player_docs_check.py
```

运行受改动影响的检查，并按实际游戏、框架和模组版本验证。

- [测试指南](docs/TESTING_GUIDE.md)：操作步骤与判定标准。
- [自动化场景测试](docs/AUTOMATED_PASSAGE_SWEEP.md)：场景、战斗与环境检查。
- [自动玩家](docs/AUTOMATED_GAMEPLAY_EXPLORER.md)：界面操作、轨迹与失败重放。
- [测试目录](tests/README.md)：测试模块与运行方式。
- [当前项目状态](docs/CURRENT_PROJECT_STATE.md)：稳定版、候选和实际验证范围。

进入游戏、构建成功、抽查功能正常和完整验收通过分别记录。未测试的设备与功能明确标注，原始存档只通过副本参与测试。
