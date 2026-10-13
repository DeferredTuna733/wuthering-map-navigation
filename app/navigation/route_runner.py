"""
walk_to_target.py —— 鸣潮自动寻路

目标点来源（优先第一个，缺失则回退）：
  1. data/routes/gg_route_draft.json 地图路线草稿
  2. data/routes/waypoints.json 手动校准路线
  3. data/routes/recorded_path.json 新坐标录制程序生成的路线

思路：
  1. 读当前坐标 (cx, cy)
  2. 算到目标 (tx, ty) 的距离和方向
  3. 按 W 走一小步（约 0.4 秒）
  4. 再读坐标，测量实际移动向量
  5. 实际移动方向 vs 目标方向 -> 角度差
  6. 用 pydirectinput.moveRel 修视角
  7. 循环，直到距离 < ARRIVE_DIST

启动：管理员权限运行（否则游戏内键鼠无效）
  python -m app.navigation.route_runner（默认只检查）
  python -m app.navigation.route_runner --read-only（只读）
  python -m app.navigation.route_runner --execute（执行，需要明确准备好）

紧急停止：F12  或  Ctrl+C
"""

import re
import os
import json
import time
import math
import argparse
from datetime import datetime
from app.navigation.screen_region import resolve_region
import mss
import cv2
import numpy as np
import pydirectinput
import keyboard

# ============ 配置 ============
STEP_DURATION = 0.4         # 每次 W 持续时间（秒）
ARRIVE_DIST = 5.0           # 距离阈值（小于此值视为到达）
MAX_ITER_PER_TARGET = 200  # 每个目标点最大迭代次数
MOUSE_PER_DEG = 12.5        # 鼠标灵敏度（像素/度，估算值，待标定）
ANGLE_THRESHOLD = 8.0       # 角度差超过此值才修正
OCR_TRIES = 4               # OCR 多读几次取最近一次有效值
STARTUP_DELAY = 15.0         # 启动后等几秒切到游戏窗口
EMERGENCY_KEY = "f12"       # 紧急停止键
# 目标点来源统一由project_paths定义；旧根目录path.json已归档，不再自动使用。

# OCR 坐标合理性范围（沿用 read_coord.py 的判断）
RANGE_XY = (-5000, 5000)
RANGE_Z = (-500, 600)
# 路径点过滤：与前一点水平距离超过此值视为 OCR 噪声点丢弃
JUMP_MAX_DIST = 200
JUMP_MAX_Z = 150

from app import project_paths as paths
from app.navigation.coordinate_reader import read_once, fix_sign


def read_coord(sct, region, tries=OCR_TRIES):
    # Keep calls patchable for movement tests, delegate consensus to shared reader.
    from app.navigation.coordinate_reader import consensus_read
    return consensus_read(sct, region, tries, reader=read_once)


# ============ 路径点加载与清洗 ============
def load_targets():
    """优先读取 wuthering.gg 草稿；再读取旧 waypoints/path 格式。"""
    candidates = [
        (str(paths.DRAFT_ROUTE), "gg_route_draft.json"),
        (str(paths.WAYPOINT_ROUTE), "waypoints.json"),
        (str(paths.RECORDED_ROUTE), "recorded_path.json"),
    ]
    for path, name in candidates:
        if not os.path.exists(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if name == "gg_route_draft.json":
            if not isinstance(raw, dict) or not isinstance(raw.get("points"), list):
                continue
            if raw.get("source") != "wuthering.gg" or raw.get("navigation_approved") is not False:
                print("拒绝读取未标记为待核验的路线草稿")
                continue
            raw = raw["points"]
        elif isinstance(raw, dict):
            continue
        targets = []
        last = None
        for p in raw:
            if not (isinstance(p, (list, tuple)) and len(p) >= 2):
                continue
            x, y = p[0], p[1]
            try:
                x, y = float(x), float(y)
            except (TypeError, ValueError):
                continue
            if not (math.isfinite(x) and math.isfinite(y)):
                continue
            if not (RANGE_XY[0] <= x <= RANGE_XY[1] and RANGE_XY[0] <= y <= RANGE_XY[1]):
                continue
            z = p[2] if len(p) >= 3 else None
            if z is not None:
                try: z = float(z)
                except (TypeError, ValueError): z = None
            # 地图草稿没有高度；保留 None，不伪造 z=0。
            # waypoints.json 是地图画线工具手工画的，相邻点距离天然合理，无需跳变过滤
            if name == "recorded_path.json":
                if last is not None:
                    d = math.hypot(x - last[0], y - last[1])
                    dz = abs(z - last[2]) if z is not None and last[2] is not None else 0
                    if d > JUMP_MAX_DIST or dz > JUMP_MAX_Z:
                        continue
            targets.append((float(x), float(y), z))
            last = (float(x), float(y), z)
        if targets:
            return targets, name
    return [], None


# ============ 几何 ============
def angle_deg(dx, dy):
    """向量 (dx, dy) 的方向角（度），atan2(dy, dx)。"""
    if dx == 0 and dy == 0:
        return None
    return math.degrees(math.atan2(dy, dx))


def norm_angle_diff(a, b):
    """归一到 [-180, 180]。"""
    d = (a - b + 180) % 360 - 180
    return d


# ============ 主循环 ============
def walk_to_target(sct, region, target, target_idx, total):
    tx, ty, _ = target
    read_failures = 0
    stalled_steps = 0
    for it in range(MAX_ITER_PER_TARGET):
        if keyboard.is_pressed(EMERGENCY_KEY):
            raise KeyboardInterrupt("用户按下紧急停止键")

        cur = read_coord(sct, region)
        if not cur:
            read_failures += 1
            print(f"  [{it}] 读坐标失败，重试")
            if read_failures >= 3:
                print("连续无法读取坐标，停止路线")
                return False
            time.sleep(0.1)
            continue
        read_failures = 0
        cx, cy, cz = cur
        dist = math.hypot(tx - cx, ty - cy)
        print(f"  [{it}] 当前=({cx},{cy},{cz}) 距离={dist:.1f}")
        if dist < ARRIVE_DIST:
            print("  到达")
            return True

        # 走一步
        before = cur
        keyboard.press("w")
        try:
            deadline = time.monotonic() + STEP_DURATION
            while time.monotonic() < deadline:
                if keyboard.is_pressed(EMERGENCY_KEY):
                    raise KeyboardInterrupt("用户按下紧急停止键")
                time.sleep(0.01)
        finally:
            keyboard.release("w")
        # 等坐标稳定后读
        time.sleep(0.12)
        after = read_coord(sct, region)

        if not after:
            print("  走后读坐标失败，停止路线")
            return False

        dx = after[0] - before[0]
        dy = after[1] - before[1]
        step = math.hypot(dx, dy)
        if step < 1:
            stalled_steps += 1
            print("  似乎没动（可能撞墙/掉线）")
            if stalled_steps >= 3:
                return False
            continue
        stalled_steps = 0
        if step > 50:
            print("坐标变化异常，停止路线")
            return False

        target_ang = angle_deg(tx - before[0], ty - before[1])
        actual_ang = angle_deg(dx, dy)
        diff = norm_angle_diff(target_ang, actual_ang)
        print(
            f"  移动=({dx},{dy}) 步长={step:.1f} "
            f"目标角={target_ang:.1f}° 实际角={actual_ang:.1f}° 差={diff:.1f}°"
        )

        # 视角修正：
        #   diff > 0 表示目标在当前移动方向的右侧（视角需右转 -> 鼠标右移 +x）
        #   diff < 0 表示在左侧（视角左转 -> 鼠标左移 -x）
        #   鼠标右移 px 数 = diff * MOUSE_PER_DEG（待标定）
        if abs(diff) > ANGLE_THRESHOLD:
            move_x = int(diff * MOUSE_PER_DEG)
            if move_x != 0:
                pydirectinput.moveRel(move_x, 0)
                time.sleep(0.08)
    print(f"  ⚠ 达到最大迭代 {MAX_ITER_PER_TARGET}，放弃此目标")
    return False


def read_only_loop(samples=20, interval=0.25, delay=0, diagnostics=False):
    """Read-only game pixels; optional evidence is separate from route files."""
    from app.navigation.coordinate_reader import consensus_read, inspect_crop
    for remaining in range(delay, 0, -1):
        print(f"{remaining} 秒后读取，请切回游戏、保持角色静止并显示坐标…", flush=True)
        time.sleep(1)
    records = []
    folder = None
    if diagnostics:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        folder = paths.ROOT / "outputs/navigation/ocr_checks" / stamp
        folder.mkdir(parents=True, exist_ok=False)
    good = 0
    region = None
    try:
        with mss.MSS() as sct:
            region, label = resolve_region(sct.monitors)
            print(f"读取区域：{region}，{label}", flush=True)
            for index in range(samples):
                evidence = []
                if diagnostics:
                    def reader(capture, crop_region):
                        crop = np.asarray(capture.grab(crop_region))
                        item = inspect_crop(crop)
                        evidence.append(item)
                        if len(evidence) == 1 and (index < 3 or index % 5 == 0):
                            file = folder / f"crop_{index + 1:03d}.png"
                            success, encoded = cv2.imencode(".png", crop)
                            if not success:
                                raise OSError("无法保存OCR区域截图")
                            file.write_bytes(encoded.tobytes())
                        return item["coordinate"]
                    current = consensus_read(sct, region, reader=reader)
                else:
                    current = read_coord(sct, region)
                if current is not None:
                    good += 1
                    print(f"[{index + 1}/{samples}] 坐标={current}", flush=True)
                else:
                    print(f"[{index + 1}/{samples}] 未得到一致坐标", flush=True)
                records.append({"sample": index + 1, "coordinate": current, "raw_reads": evidence})
                time.sleep(interval)
    except KeyboardInterrupt:
        print("只读采集已中止", flush=True)
    finally:
        if folder is not None:
            report = {"region": region, "requested": samples, "collected": len(records),
                      "consensus_count": good, "samples": records,
                      "warning": "一致性和识别次数不代表坐标准确；请对照实际游戏显示。",
                      "game_input_performed": False}
            (folder / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"诊断资料已保存：{folder}", flush=True)
    print(f"只读采集完成：一致结果 {good}/{len(records)}，未操作键鼠、未改动路线文件", flush=True)
    return 0 if good else 1


def main():
    parser = argparse.ArgumentParser(description="鸣潮路线执行器")
    parser.add_argument("--execute", action="store_true", help="明确允许控制游戏；默认仅检查路线")
    parser.add_argument("--read-only", action="store_true", help="只读OCR坐标，不控制游戏")
    parser.add_argument("--samples", type=int, default=20, help="只读测试样本数")
    parser.add_argument("--delay", type=int, default=15, help="只读采样前倒计时秒数")
    parser.add_argument("--diagnostics", action="store_true", help="保存识别区域截图和原始OCR文本")
    args = parser.parse_args()
    if args.read_only and args.execute:
        parser.error("只读测试和执行模式不能同时指定")
    if not 0 <= args.delay <= 60:
        parser.error("--delay 必须在0到60之间")
    if args.read_only:
        if not 1 <= args.samples <= 1000:
            parser.error("--samples 必须在1到1000之间")
        return read_only_loop(args.samples, delay=args.delay, diagnostics=args.diagnostics)
    targets, source = load_targets()
    if not targets:
        print("没有可用路线；请导出到 data/routes/gg_route_draft.json，或使用新录制程序。")
        return
    print(f"加载 {len(targets)} 个目标点（来源: {source}）")
    if not args.execute:
        print("安全检查模式：不会控制游戏。若确认要执行，请使用 --execute")
        for i, target in enumerate(targets, 1):
            print(f"  {i}: ({target[0]:.3f}, {target[1]:.3f}, z={target[2] if target[2] is not None else '未提供'})")
        return
    print(f"紧急停止：按 {EMERGENCY_KEY.upper()}  或 Ctrl+C")
    for remaining in range(args.delay, 0, -1):
        print(f"{remaining} 秒后开始，请切到游戏窗口……", flush=True)
        time.sleep(1)

    with mss.MSS() as sct:
        region, _ = resolve_region(sct.monitors)

        success, failed = 0, 0
        for i, t in enumerate(targets):
            print(f"\n=== 目标 {i + 1}/{len(targets)}: {t} ===")
            try:
                if walk_to_target(sct, region, t, i, len(targets)):
                    success += 1
                else:
                    failed += 1
                    print("目标失败，停止整条路线，不跳到下一个目标")
                    break
            except KeyboardInterrupt:
                print("\n用户中止")
                break
        print(f"\n完成：成功 {success} 个，失败 {failed} 个")


if __name__ == "__main__":
    raise SystemExit(main())
