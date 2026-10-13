"""Bounded manual-movement observer. Never injects keyboard or mouse input."""
import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime
import json
import time
from pathlib import Path
import cv2
import numpy as np
from app import project_paths as paths
from app.navigation.navigation_observer import NavigationObserver
from app.navigation.rolling_background import RollingBackground
from app.navigation.single_point_test import foreground_process, StopTest
from tools.check_background_heading import load_model


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--capture',action='store_true')
    parser.add_argument('--delay',type=int,default=15)
    parser.add_argument('--seconds',type=int,default=20)
    parser.add_argument('--rolling-state',type=Path)
    args=parser.parse_args()
    if not 0<=args.delay<=60 or not 1<=args.seconds<=60:
        parser.error('delay 0..60; seconds 1..60')
    file,model,background,reference=load_model()
    circle=model['circle'];region=model['region']
    provenance=dict(reference_report=str(file),region=region,circle=circle)
    rolling=(RollingBackground.load(args.rolling_state,provenance,background.shape,circle['center_xy'],circle['radius'])
             if args.rolling_state else RollingBackground(reference,background,circle['center_xy'],circle['radius']))
    if not args.capture:
        print('连续只读预检通过；未截图、未发送输入。')
        return
    import mss
    from PIL import Image
    from app.navigation.coordinate_reader import get_ocr,read_coord
    from app.navigation.screen_region import resolve_region
    get_ocr()
    user=ctypes.WinDLL('user32');user.GetForegroundWindow.restype=wintypes.HWND
    handle=None;last_process=None
    def emergency():
        if user.GetAsyncKeyState(0x7B)&0x8000:raise StopTest('emergency_key')
    def guard():
        nonlocal handle,last_process
        emergency()
        last_process=foreground_process()
        if last_process.casefold()!='client-win64-shipping.exe':raise StopTest('game_not_foreground')
        current=user.GetForegroundWindow()
        if handle is None:handle=current
        if current!=handle:raise StopTest('window_changed')
    for remaining in range(args.delay,0,-1):
        emergency()
        print(f'{remaining}秒后只读监测；切回游戏，F12停止。',flush=True)
        time.sleep(1)
    folder=paths.ROOT/'outputs/navigation/continuous_checks'/datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    folder.mkdir(parents=True,exist_ok=False)
    observer=NavigationObserver(rolling);rows=[];status='duration_finished'
    started=None
    try:
        print('等待游戏进入前台（最多60秒）；请切回游戏，先站着不动。',flush=True)
        ready_deadline=time.monotonic()+60
        while True:
            emergency();last_process=foreground_process()
            if last_process.casefold()=='client-win64-shipping.exe':
                guard();break
            if time.monotonic()>=ready_deadline:raise StopTest('game_foreground_wait_timeout')
            time.sleep(.25)
        started=time.monotonic()
        print('已检测到游戏，开始只读监测。',flush=True)
        with mss.MSS() as cap, (folder/'observations.jsonl').open('w',encoding='utf-8') as stream:
            ocr_region,_=resolve_region(cap.monitors)
            while time.monotonic()-started < args.seconds:
                guard()
                # Two matching readings reject a single transient OCR result.
                first=read_coord(cap,ocr_region);guard()
                second=read_coord(cap,ocr_region);guard()
                coordinate=first if first is not None and first==second else None
                index=len(rows)
                shot=cap.grab(ocr_region)
                Image.frombytes('RGB',shot.size,shot.rgb).save(folder/f'coordinate_{index:03d}.png')
                shot=cap.grab(region);image=Image.frombytes('RGB',shot.size,shot.rgb)
                image.save(folder/f'frame_{index:03d}.png');guard()
                row=observer.observe(cv2.cvtColor(np.asarray(image),cv2.COLOR_RGB2BGR),coordinate)
                row.update(elapsed_seconds=time.monotonic()-started,ocr_readings=[first,second])
                rows.append(row);stream.write(json.dumps(row,ensure_ascii=False)+'\n');stream.flush()
                print(f'{index}: {row["status"]} 坐标={coordinate} 方向={row["direction_deg"]}',flush=True)
                if row['status']!='observed_candidate':
                    status=row['status'];break
                time.sleep(.25)
    except Exception as error:
        status=str(error) if isinstance(error,StopTest) else 'error'
        rows.append({'status':status,'error':str(error)})
    if status=='duration_finished' and observer.samples>=6:
        rolling.save(folder/'rolling_state',provenance)
    report=dict(status=status,reference_report=str(file),region=region,circle=circle,
        resumed_state=str(args.rolling_state) if args.rolling_state else None,
        last_foreground_process=last_process,game_detected=started is not None,
        observations=rows,accepted=observer.samples,rolling_updates=rolling.updates,
        rolling_travel_pixels=rolling.travel,requested_seconds=args.seconds,
        navigation_approved=False,accuracy_verified=False,movement_keys_sent=False,mouse_keys_sent=False)
    (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'只读监测结束：{status}；报告：{folder}',flush=True)


if __name__=='__main__':main()
