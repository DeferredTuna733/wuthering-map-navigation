# 鸣潮地图画线与视觉路线工具

Windows / Python 的实验性工具：在离线地图上画路线，通过屏幕 OCR 和小地图图像定位，沿用户指定的路线行走。只使用截图和键鼠输入，不读取游戏内存。

## 功能

- 离线地图缩放、拖动路线点、手动或 OCR 设置起点、路线 JSON 导入导出。
- 圆形小地图区域选择、后台快捷截图、白色视角扇形轮廓标注与训练工具。
- 白色扇形视觉识别、地形连续跟踪、大地图配准和坐标 OCR 融合。
- 以路线为中心线的容错控制；通过实际转角反馈学习鼠标响应比例，继续纠偏。
- F12 停止、前台窗口检查、坐标质量检查和步数/时间限制。

已在开发者环境中从起点一次走完一条 7 点短路线：25 步、49.2 秒，观测最大中心线偏离 1.31 游戏单位。该结果仅适用于这条测试路线；尚未验证全地图寻路、自动避障、战斗操作或复杂地形。

## 安装

使用 Windows 和 Python 3.11：

```powershell
python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt
venv\Scripts\python.exe -B -m app.map_editor.gui
```

Tkinter 随标准 Windows Python 安装提供。依赖列表不是固定环境锁文件；不同硬件的 PyTorch 安装方式可能不同。

## 首次配置

本仓库发布源码，不附带个人截图、训练样本、模型权重、地图图片或个人运行状态。`examples/config/navigation/` 只是开发环境的区域示例，必须按你的屏幕重新设置，不能直接当作有效标定。

1. 地图工具默认使用 `data/maps/wuthering_gg/huanglong_z4.png` 和同名 `.meta.json`；支持界面导入自己的地图。地图来自 wuthering.gg，其素材权限不由本项目许可证授予。地图下载与拼接代码位于 `tools/maps/`、`app/map_editor/map_assets.py`。请遵守素材提供方的使用条件。
2. 运行 `python -m app.navigation.region_selector`，选择包含三项坐标和完整日期时间的区域；运行 `python -m app.navigation.minimap_region_selector` 设置小地图区域。
3. 使用 `python -m tools.scan_capture_station` 采集及标注视角样本，训练工具为 `tools/train_scan_ai.py`。自动行走入口需要 `models/navigation/camera_sector/v3.pt`，本仓库未分发该权重。
4. 当前组合定位执行器还需要本机的视角几何配置与地形锚点 `data/navigation/position_anchor.json` 及其参考图片。锚点保存和验证接口见 `app/navigation/position_anchor.py`；完整初始化向导尚未实现，因此源码克隆后不能直接使用自动行走入口。
5. 画线工具导出 `data/routes/gg_route_draft.json`。自动行走按连续相邻点执行，目前每段长度需大于 3 且不超过 20 游戏单位。

## 运行与测试

```powershell
# 地图画线
venv\Scripts\python.exe -B -m app.map_editor.gui
# 坐标只读检查
venv\Scripts\python.exe -B run.py route --read-only --samples 10
# 已完成本机配置后，连续验证一条 7 点短路线
venv\Scripts\python.exe -B -m app.navigation.ai_single_point --from-point 2 --through-point 7
# 单元测试
venv\Scripts\python.exe -B -m unittest discover -s tests/unit -q
```

试走窗口由用户点击开始，倒计时期间切回游戏。F12 可停止。若游戏以管理员运行，试走程序也需匹配权限；根目录提供对应 `.bat` 启动文件。不要在未完成本机配置时运行试走。部分测试需要开发数据或本机配置，纯源码环境的相关测试可能无法通过。

## 许可证

源码按 GNU AGPL v3 发布，完整条款见 [LICENSE](LICENSE)。第三方依赖、地图素材和游戏内容各自遵循其原许可证与使用条件。本项目不是鸣潮或 wuthering.gg 的官方产品。
