"""Mouse-only relative-input probe. No movement keys or automatic calibration."""
import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime
import json
import time
import numpy as np
from app import project_paths as paths
from app.navigation.single_point_test import StopTest, foreground_process
from app.navigation.minimap_heading import detect_scan_heading,resolve_minimap_region


def run_probe(move, guard, snapshot, pixels=120, clock=time.monotonic, sleep=time.sleep):
    if type(pixels) is not int or not 20 <= pixels <= 240:
        raise ValueError('Probe pixels must be 20..240')
    began=clock();events=[];status='observations_saved'
    def check():
        guard()
        if clock()-began>20:raise StopTest('time_limit')
    def wait(seconds):
        end=clock()+seconds
        while clock()<end:
            check();sleep(min(.02,max(0,end-clock())))
    def capture(label):
        check();snapshot(label);check()
        events.append({'event':'screenshot','label':label,'elapsed':clock()-began})
    try:
        capture('01_before')
        for label,direction in [('02_right',1),('03_left',-1)]:
            for offset in range(0,pixels,10):
                check();amount=direction*min(10,pixels-offset)
                move(amount,0)
                events.append({'event':'relative_mouse','x':amount,'y':0,'elapsed':clock()-began})
                wait(.02)
            wait(2)
            capture(label)
    except StopTest as exc:status=str(exc)
    except KeyboardInterrupt:status='interrupted'
    except Exception as exc:
        status='error';events.append({'event':'error','type':type(exc).__name__,'message':str(exc)})
    return {'status':status,'pixels_per_direction':pixels,'events':events,'elapsed':clock()-began,
            'movement_keys_sent':False,'input_mode':'pydirectinput.moveRel(relative=True)',
            'calibration_verified':False,
            'warning':'Opposite mouse inputs do not guarantee original view restoration. Screenshots test response, not degrees/pixel. No input after focus loss/F12.'}


def main():
    parser=argparse.ArgumentParser(description='仅鼠标转向探测；默认预检，不操作游戏')
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--game-process',default='Client-Win64-Shipping.exe')
    parser.add_argument('--delay',type=int,default=15)
    parser.add_argument('--pixels',type=int,default=120)
    args=parser.parse_args()
    if not 0<=args.delay<=60 or not 20<=args.pixels<=240:parser.error('delay 0..60, pixels 20..240')
    print(f'只转视角：相对右移{args.pixels}，暂停2秒，相对左移{args.pixels}，不按W。',flush=True)
    if not args.execute:
        print('预检完成，没有截图或发送输入。');return 0
    import keyboard
    import pydirectinput
    import mss
    import mss.tools
    from app.navigation.coordinate_reader import get_ocr,read_coord
    from app.navigation.screen_region import resolve_region
    get_ocr()  # initialization before countdown
    for seconds in range(args.delay,0,-1):
        print(f'{seconds}秒后开始；切回游戏主世界，不要手动移动鼠标；F12停止。',flush=True)
        time.sleep(1)
    folder=paths.ROOT/'outputs/navigation/turning_probes'/datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    folder.mkdir(parents=True,exist_ok=False)
    user32=ctypes.WinDLL('user32',use_last_error=True)
    user32.GetForegroundWindow.restype=wintypes.HWND
    user32.GetClientRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
    user32.ClientToScreen.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.POINT)]
    handle=None
    def guard():
        nonlocal handle
        if keyboard.is_pressed('f12'):raise StopTest('emergency_key')
        if foreground_process().casefold()!=args.game_process.casefold():raise StopTest('game_not_foreground')
        current=user32.GetForegroundWindow()
        if handle is None:handle=current
        if current!=handle:raise StopTest('window_changed')
    positions={}
    try:
        with mss.MSS() as capture:
            region,_=resolve_region(capture.monitors)
            minimap,minimap_circle=resolve_minimap_region(capture.monitors)
            def snapshot(label):
                guard()
                rect=wintypes.RECT();point=wintypes.POINT(0,0)
                if not user32.GetClientRect(handle,ctypes.byref(rect)) or not user32.ClientToScreen(handle,ctypes.byref(point)):
                    raise StopTest('window_rect_failed')
                if rect.right<=0 or rect.bottom<=0:raise StopTest('invalid_window_size')
                shot=capture.grab({'left':point.x,'top':point.y,'width':rect.right,'height':rect.bottom})
                guard()
                mss.tools.to_png(shot.rgb,shot.size,output=str(folder/(label+'.png')))
                positions[label]=read_coord(capture,region)
                crop=np.asarray(capture.grab(minimap))
                heading=detect_scan_heading(crop,center=minimap_circle['center_xy'],radius=minimap_circle['radius'])
                report_heading=heading.__dict__
                (folder/(label+'_heading.json')).write_text(json.dumps(report_heading,ensure_ascii=False,indent=2),encoding='utf-8')
                guard()
            report=run_probe(lambda x,y:pydirectinput.moveRel(x,y,relative=True,_pause=False),
                             guard,snapshot,args.pixels)
            report.update(coordinates=positions,required_game_process=args.game_process)
    except (Exception,KeyboardInterrupt) as exc:
        report={'status':'setup_failed','error':str(exc),'movement_keys_sent':False,'calibration_verified':False}
    (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'转向探测结束：{report["status"]}；记录：{folder}',flush=True)
    return 0 if report['status']=='observations_saved' else 1

if __name__=='__main__':raise SystemExit(main())
