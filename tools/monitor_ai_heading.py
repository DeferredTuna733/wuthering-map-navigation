"""Bounded screenshot-only AI monitor. No game memory or input injection."""
import argparse
import ctypes
from datetime import datetime
import json
import math
import time
import tkinter as tk
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np
from PIL import Image, ImageTk
from app import project_paths as paths
from app.navigation.ai_scan import predict_heading
from app.navigation.single_point_test import foreground_process


def consistent_coordinate_pair(first,second):
    if first is None or second is None:return False
    if len(first)!=3 or len(second)!=3:return False
    if not all(math.isfinite(v) for v in (*first,*second)):return False
    return math.dist(first[:2],second[:2])<=3 and abs(first[2]-second[2])<=2


def coordinate_continuity_ok(previous,current,elapsed):
    if current is None:return False
    if previous is None:return True
    if elapsed<0:return False
    limit=max(8,min(60,25*elapsed))
    return math.dist(previous[:2],current[:2])<=limit and abs(previous[2]-current[2])<=5


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seconds', type=int, default=60)
    parser.add_argument('--delay', type=int, default=15)
    parser.add_argument('--check-image', type=Path)
    parser.add_argument('--coordinates',action='store_true')
    parser.add_argument('--position-anchor', type=Path)
    parser.add_argument('--ocr-interval', type=float, default=0)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 60 or not 0 <= args.delay <= 60:
        parser.error('seconds 1..60; delay 0..60')
    if not math.isfinite(args.ocr_interval) or not 0 <= args.ocr_interval <= 30:
        parser.error('ocr-interval 0..30 seconds')
    import torch
    from ultralytics import YOLO
    torch.set_num_threads(4)
    config = json.loads((paths.ROOT/'config/navigation/scan_capture_station.json').read_text())
    region, circle = config['region'], config['circle']
    geometry_file=paths.ROOT/'config/navigation/ai_sector_geometry.json'
    if geometry_file.exists():
        geometry=json.loads(geometry_file.read_text(encoding='utf-8'))
        if (geometry['region']==region and geometry['circle_center_xy']==circle['center_xy']
                and geometry['circle_radius']==circle['radius']):
            circle=dict(circle,player_center_xy=geometry['player_center_xy'])
    anchor = anchor_image = None
    if args.position_anchor:
        from app.navigation.position_anchor import load_anchor
        from app.navigation.minimap_position import RollingPositionTracker
        anchor, anchor_image = load_anchor(args.position_anchor, region, circle)
        tracker=RollingPositionTracker(anchor_image,circle,anchor['angle'],anchor['coordinate_xy'],anchor['affine'],anchor['zoom'])
        from app.navigation.terrain_relocalization import TerrainRelocalizer,ocr_seeds
        from app.navigation.position_anchor import save_anchor
        relocalizer=TerrainRelocalizer(paths.OFFLINE_TILES/'6',anchor['affine'])
        executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='terrain-recovery')
    model_path = paths.ROOT/'models/navigation/camera_sector/experimental.pt'
    model = YOLO(str(model_path))
    # Warm up before starting the user's countdown.
    predict_heading(model, np.zeros((region['height'], region['width'], 3), np.uint8), circle)
    if args.check_image:
        result, _ = predict_heading(model, cv2.imread(str(args.check_image)), circle)
        print(json.dumps(result, ensure_ascii=False))
        return
    import mss
    folder = paths.ROOT/'outputs/navigation/ai_live_checks'/datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    folder.mkdir(parents=True)
    root = tk.Tk()
    root.title('鸣潮 · AI 视角只读监测')
    root.geometry('480x680+1200+300')
    status = tk.StringVar()
    detail = tk.StringVar(value='绿色：模型识别区域；红线：视角方向\n角度：右 0°、下 90°、左 180°、上 270°\n只截图，不控制角色；F12 或关闭窗口停止。')
    tk.Label(root, textvariable=status, font=('Microsoft YaHei UI', 13), wraplength=450).pack(pady=12)
    preview = tk.Label(root)
    preview.pack()
    tk.Label(root, textvariable=detail, justify='left', font=('Microsoft YaHei UI', 10)).pack(pady=12)
    user = ctypes.WinDLL('user32')
    user.GetForegroundWindow.restype = ctypes.c_void_p
    cap = mss.MSS()
    coordinate_region=None
    if args.coordinates:
        from app.navigation.coordinate_reader import get_ocr,inspect_crop
        from app.navigation.screen_region import resolve_region
        get_ocr()
        coordinate_region,_=resolve_region(cap.monitors)
    rows = []
    stream = (folder/'observations.jsonl').open('w', encoding='utf-8')
    countdown_end = time.monotonic()+args.delay
    wait_deadline = countdown_end+60
    started = None
    handle = None
    ended = False
    last_coordinate=None
    last_coordinate_time=None
    last_ocr_sample=None
    pending_relocalization=None
    last_relocalization_request=-float('inf')

    def finish(reason, close=False):
        nonlocal ended
        if not ended:
            ended = True
            cap.close()
            stream.close()
            if anchor is not None:
                executor.shutdown(wait=False,cancel_futures=True)
            accepted = sum(r['direction_deg'] is not None for r in rows)
            report = dict(status=reason, model=str(model_path), region=region, circle=circle,
                          samples=len(rows), accepted=accepted, observations=rows,
                          position_samples=sum(r.get('terrain_position',{}).get('coordinate_xy') is not None for r in rows),
                          terrain_relocalizations=0 if anchor is None else tracker.relocalizations,
                          navigation_approved=False, accuracy_verified=False,
                          movement_keys_sent=False, mouse_keys_sent=False, game_memory_read=False)
            (folder/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            status.set(f'已结束：{len(rows)} 帧，{accepted} 帧输出方向')
            detail.set(f'结果已保存\n{folder}\n实时准确率仍需人工对照，未启用自动导航。')
            print(f'只读监测结束：{reason}；报告：{folder}', flush=True)
        if close:
            root.destroy()

    def update():
        nonlocal started, handle, last_coordinate,last_coordinate_time,last_ocr_sample
        nonlocal pending_relocalization,last_relocalization_request
        if ended:
            return
        try:
            if user.GetAsyncKeyState(0x7B)&0x8000:
                finish('emergency_key'); return
            now = time.monotonic()
            if started is not None and now-started >= args.seconds:
                finish('duration_finished'); return
            if now < countdown_end:
                status.set(f'{math.ceil(countdown_end-now)} 秒后开始，请切回游戏')
            elif foreground_process().casefold() != 'client-win64-shipping.exe':
                status.set('等待游戏前台；切回游戏继续采样')
                if started is None and now > wait_deadline:
                    finish('game_foreground_wait_timeout'); return
            else:
                current = user.GetForegroundWindow()
                if handle is None:
                    handle = current
                if handle != current:
                    finish('game_window_changed'); return
                if started is None:
                    started = now
                shot = cap.grab(region)
                # Recheck focus before retaining or evaluating the capture.
                if user.GetForegroundWindow() != handle:
                    root.after(250, update); return
                frame = cv2.cvtColor(np.asarray(shot), cv2.COLOR_BGRA2BGR)
                frame_time=time.monotonic()
                index = len(rows)
                result, mask = predict_heading(model, frame, circle)
                result.update(coordinate=None,movement_delta_xy=None,ocr_sampled=False,
                              frame_monotonic=frame_time)
                if anchor is not None:
                    tracking_start=time.monotonic()
                    if pending_relocalization is not None and pending_relocalization[0].done():
                        future,reference,angle,stamp,source_index=pending_relocalization
                        pending_relocalization=None
                        try:
                            recovery=future.result()
                        except Exception as error:
                            recovery=dict(status='relocalization_error',error=str(error))
                        fresh=0<frame_time-stamp<=2
                        recovered=fresh and tracker.restore(reference,angle,stamp,recovery)
                        result.update(relocalization=recovery,relocalization_applied=recovered,
                                      relocalization_age_seconds=frame_time-stamp)
                        result['relocalization_rejection_reason']=None if recovered else (
                            'stale_reference_frame' if not fresh else recovery['status'])
                        if recovered:
                            save_anchor(folder/f'recovered_anchor_{index:03d}.json',reference,
                                        region=region,circle=circle,coordinate_xy=tracker.xy.tolist(),
                                        angle=angle,affine=tracker.affine.tolist(),
                                        source=dict(frame_index=source_index,terrain=recovery['source']))
                    position=tracker.observe(frame,result['direction_deg'],frame_time)
                    result.update(terrain_position=position,
                                  tracking_ms=(time.monotonic()-tracking_start)*1000,
                                  position_anchor=str(args.position_anchor))
                if coordinate_region is not None and (last_ocr_sample is None or now-last_ocr_sample>=args.ocr_interval):
                    last_ocr_sample=now
                    ocr_start=time.monotonic()
                    result['ocr_sampled']=True
                    first_crop=np.asarray(cap.grab(coordinate_region))
                    first_diagnostic=inspect_crop(first_crop,allow_separator_dot=True)
                    first=first_diagnostic['coordinate']
                    if user.GetForegroundWindow()!=handle:
                        root.after(250,update);return
                    second_crop=np.asarray(cap.grab(coordinate_region))
                    second_diagnostic=inspect_crop(second_crop,allow_separator_dot=True)
                    second=second_diagnostic['coordinate']
                    if user.GetForegroundWindow()!=handle:
                        root.after(250,update);return
                    # Each frame still requires agreement between two image variants.
                    # During manual walking, successive real coordinates may change.
                    consistent=consistent_coordinate_pair(first,second)
                    coordinate=second if consistent else None
                    coordinate_time=time.monotonic()
                    elapsed_since_coordinate=0 if last_coordinate_time is None else coordinate_time-last_coordinate_time
                    continuous=coordinate_continuity_ok(last_coordinate,coordinate,elapsed_since_coordinate)
                    raw_coordinate=coordinate
                    if not continuous:coordinate=None
                    cv2.imwrite(str(folder/f'coordinate_{index:03d}_first.png'),first_crop)
                    cv2.imwrite(str(folder/f'coordinate_{index:03d}_second.png'),second_crop)
                    result.update(coordinate=coordinate,ocr_readings=[first,second],
                                  ocr_diagnostics=[first_diagnostic,second_diagnostic],
                                  coordinate_pair_consistent=consistent,
                                  coordinate_raw=raw_coordinate,
                                  coordinate_continuity_ok=continuous,
                                  coordinate_rejection_reason='jump_or_sign_change' if consistent and not continuous else None,
                                  coordinate_region=coordinate_region,
                                  movement_delta_xy=None,movement_angle_game_xy_deg=None)
                    if coordinate is not None:
                        if last_coordinate is not None:
                            dx,dy=coordinate[0]-last_coordinate[0],coordinate[1]-last_coordinate[1]
                            result['movement_delta_xy']=[dx,dy]
                            if dx or dy:
                                result['movement_angle_game_xy_deg']=math.degrees(math.atan2(dy,dx))%360
                        last_coordinate=coordinate
                        last_coordinate_time=coordinate_time
                    # Game-coordinate movement angle and screen camera angle use
                    # different axes; do not silently treat them as equivalent.
                    result['camera_to_game_axes_verified']=False
                    result.update(ocr_ms=(time.monotonic()-ocr_start)*1000,
                                  coordinate_monotonic=coordinate_time)
                    if anchor is not None:
                        xy=result['terrain_position']['coordinate_xy']
                        difference=None if xy is None or raw_coordinate is None else math.dist(xy,raw_coordinate[:2])
                        result.update(position_ocr_difference=difference,
                                      position_source_comparison='unavailable' if difference is None else
                                      ('approximately_agree' if difference<=4 else 'disagree_no_correction'))
                        result['ocr_corroborates_tracking']=tracker.corroborate(coordinate,coordinate_time)
                        seeds=ocr_seeds([first_diagnostic,second_diagnostic])
                        if (pending_relocalization is None and seeds and result['direction_deg'] is not None
                                and coordinate_time-frame_time<=.3
                                and now-last_relocalization_request>=2
                                and (tracker.blocked or now-last_relocalization_request>=10)):
                            reference=frame.copy()
                            pending_relocalization=(executor.submit(relocalizer.locate,reference,circle,seeds),
                                                    reference,result['direction_deg'],frame_time,index)
                            last_relocalization_request=now
                            result['relocalization_requested']=True
                result.update(index=index, elapsed_seconds=time.monotonic()-started)
                rows.append(result)
                stream.write(json.dumps(result, ensure_ascii=False)+'\n'); stream.flush()
                cv2.imwrite(str(folder/f'frame_{index:03d}.png'), frame)
                overlay = frame.copy()
                if mask is not None:
                    selected = mask > .5
                    overlay[selected] = (.5*overlay[selected]+.5*np.array([0,255,0])).astype(np.uint8)
                angle = result['direction_deg']
                if angle is not None:
                    center = tuple(round(v) for v in circle.get('player_center_xy',circle['center_xy']))
                    endpoint = (round(center[0]+circle['radius']*.8*math.cos(math.radians(angle))),
                                round(center[1]+circle['radius']*.8*math.sin(math.radians(angle))))
                    cv2.arrowedLine(overlay, center, endpoint, (0,0,255), 2)
                cv2.imwrite(str(folder/f'overlay_{index:03d}.png'), overlay)
                rgb = cv2.cvtColor(overlay, cv2.COLOR_BGR2RGB)
                photo = ImageTk.PhotoImage(Image.fromarray(rgb).resize((400,400)))
                preview.configure(image=photo); preview.image = photo
                remaining = max(0, math.ceil(args.seconds-(time.monotonic()-started)))
                labels = {'sector_not_detected':'未检测到白色区域', 'mask_shape_unresolved':'区域形状检查未通过',
                          'multiple_sectors_detected':'检测到多个区域',
                          'sector_aperture_unresolved':'扇形开角检查未通过','low_model_support':'模型分数偏低，拒绝输出方向',
                          'player_anchor_not_supported':'角色锚点附近未检测到黄色箭头',
                          'no_valid_sector':'没有区域通过形状和分数检查'}
                message = f'视角方向：{angle:.0f}°' if angle is not None else labels.get(result['status'],result['status'])
                status.set(f'{message} · 剩余 {remaining} 秒 · 第 {index+1} 帧')
                if coordinate_region is not None:
                    status.set(status.get()+f'\nOCR：{result["coordinate"] if result["ocr_sampled"] else "本帧未采样"}')
                if anchor is not None:
                    xy=result['terrain_position']['coordinate_xy']
                    label=f'{xy[0]:.1f}, {xy[1]:.1f}' if xy is not None else '跟踪失效，需重新定位'
                    if xy is None and pending_relocalization is not None:label='正在验证地形，等待重新定位'
                    status.set(status.get()+f'\n地形 XY：{label}')
            root.after(250, update)
        except Exception as error:
            print(str(error), flush=True)
            finish(f'error: {error}')

    root.protocol('WM_DELETE_WINDOW', lambda: finish('window_closed', True))
    root.after(100, update)
    root.mainloop()


if __name__ == '__main__':
    main()
