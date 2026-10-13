"""Bounded single-point experiment; never executes the rest of the route."""
import argparse
import ctypes
from ctypes import wintypes
from dataclasses import dataclass, asdict
from datetime import datetime
import json
import math
import os
from pathlib import Path
import time

from app import project_paths as paths
from app.navigation.coordinate_reader import fix_sign
from app.navigation.route_corridor import segment_position


@dataclass(frozen=True)
class Limits:
    max_seconds: float = 25
    max_steps: int = 8
    step_seconds: float = .35
    arrive_distance: float = 4
    corridor_width: float = 4
    corridor_stop_distance: float = 6
    start_radius: float = 8
    max_target_distance: float = 20
    max_step_distance: float = 8
    max_height_change: float = 5
    max_mouse_pixels: int = 120
    mouse_per_degree: float = 12.5  # Estimate only; experiments must verify sign/sensitivity.


class StopTest(Exception):
    pass


def load_point(route, point_number=2):
    """Do not silently filter/reorder the user's draft or fall back to another route."""
    data=json.loads(Path(route).read_text(encoding='utf-8-sig'))
    return validate_point(data,point_number)


def validate_point(data,point_number=2):
    """Validate a route document, including a bounded consecutive segment."""
    if not isinstance(data,dict) or data.get('source')!='wuthering.gg' or data.get('navigation_approved') is not False:
        raise ValueError('仅使用明确标记为待核验的 wuthering.gg 路线草稿')
    points=data.get('points')
    if not isinstance(points,list) or not 2<=point_number<=len(points):
        raise ValueError('目标编号须从2开始，且位于导出的路线内')
    selected=[]
    for index in (0,point_number-1):
        item=points[index]
        if not isinstance(item,list) or len(item)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>5000 for v in item):
            raise ValueError(f'标记点{index+1}不是有效二维坐标')
        selected.append(tuple(float(v) for v in item))
    if not 3 < math.dist(*selected) <= 20:
        raise ValueError('单点测试要求目标距路线起点大于3且不超过20单位')
    return selected[0],selected[1]


def run_single(start, target, read, key_down, key_up, move_mouse, guard,
               limits=Limits(), clock=time.monotonic, sleep=time.sleep, correct_sign=True):
    """All I/O injectable for tests. guard must verify focus and emergency key.
    Time budget is checked between OCR calls; a blocking OCR call cannot be interrupted.
    No speculative sign correction, no unknown target height set to zero.
    """
    began=clock();events=[];steps=0;held=False;stalled=0;worsened=0;status='stopped';last_read=None

    def check():
        guard()
        if clock()-began >= limits.max_seconds:raise StopTest('time_limit')

    def sample(retries=3):
        nonlocal last_read
        last_reason = 'ocr_failed'
        for attempt in range(max(1, retries)):
            check(); point=read(); check()
            if point is not None and len(point)==3 and all(type(v) in (int,float) and math.isfinite(v) for v in point):
                point=fix_sign(tuple(point), last_read) if correct_sign else tuple(point)
                last_read=point
                events.append({'event':'read','coordinate':point,'attempt':attempt+1,'elapsed':clock()-began})
                return point
            last_reason = 'ocr_failed'
            if attempt + 1 < retries:
                pause(.10)
        raise StopTest(last_reason)

    def pause(seconds):
        end=clock()+seconds
        while clock()<end:
            check();sleep(min(.01,max(0,end-clock())))

    try:
        initial=sample()
        confirmation=sample()
        if math.dist(initial[:2],confirmation[:2])>2 or abs(initial[2]-confirmation[2])>2:
            raise StopTest('initial_read_unstable')
        current=confirmation
        if math.dist(current[:2],start)>limits.start_radius:raise StopTest('not_near_route_start')
        if math.dist(current[:2],target)>limits.max_target_distance:raise StopTest('target_too_far')
        if segment_position(current,start,target)['segment_distance']>limits.corridor_stop_distance:
            raise StopTest('outside_route_corridor')
        while True:
            distance=math.dist(current[:2],target)
            if distance<=limits.arrive_distance:
                confirm=sample()
                if math.dist(confirm[:2],target)<=limits.arrive_distance and math.dist(confirm[:2],current[:2])<=2:
                    status='arrived';break
                raise StopTest('arrival_not_confirmed')
            if steps>=limits.max_steps:raise StopTest('step_limit')
            check();before=current
            # Every key down has an unconditional release, including exceptions/F12/focus loss.
            held=True
            try:
                key_down('w');pause(limits.step_seconds)
            finally:
                key_up('w');held=False
            steps+=1;pause(.12)
            current=sample(retries=3)
            travelled=math.dist(current[:2],before[:2])
            after_distance=math.dist(current[:2],target)
            events.append({'event':'step','number':steps,'before':before,'after':current,
                           'travelled':travelled,'distance_before':distance,'distance_after':after_distance})
            if travelled>limits.max_step_distance:raise StopTest('abnormal_displacement')
            if abs(current[2]-initial[2])>limits.max_height_change:raise StopTest('height_changed')
            deviation=segment_position(current,start,target)['segment_distance']
            events.append({'event':'corridor','distance_from_segment':deviation,
                           'within_preferred_width':deviation<=limits.corridor_width})
            if deviation>limits.corridor_stop_distance:raise StopTest('outside_route_corridor')
            stalled=stalled+1 if travelled<1 else 0
            worsened=worsened+1 if after_distance>distance+.5 else 0
            if stalled>=2:raise StopTest('stalled')
            if after_distance>distance+3 or worsened>=2:raise StopTest('moving_away')
            if travelled>=1 and after_distance>limits.arrive_distance:
                wanted=math.degrees(math.atan2(target[1]-current[1],target[0]-current[0]))
                actual=math.degrees(math.atan2(current[1]-before[1],current[0]-before[0]))
                delta=(wanted-actual+180)%360-180
                if abs(delta)>8:
                    pixels=round(max(-limits.max_mouse_pixels,min(limits.max_mouse_pixels,delta*limits.mouse_per_degree)))
                    check();move_mouse(pixels,0);check()
                    events.append({'event':'turn','angle_error':delta,'mouse_pixels':pixels,'sensitivity_verified':False})
                    pause(.08)
    except StopTest as exc:status=str(exc)
    except KeyboardInterrupt:status='interrupted'
    except Exception as exc:
        status='error';events.append({'event':'exception','type':type(exc).__name__,'message':str(exc)})
    finally:
        if held:key_up('w')
    return {'status':status,'start':start,'target':target,'steps':steps,'elapsed':clock()-began,
            'limits':asdict(limits),'events':events,'height_policy':'observe current height; no target height inferred',
            'warning':'Mouse sign/sensitivity unverified. Not obstacle avoidance, not full-route approval.'}


def foreground_process():
    if os.name!='nt':raise RuntimeError('单点执行仅支持Windows')
    import psutil
    user32=ctypes.WinDLL('user32',use_last_error=True)
    user32.GetForegroundWindow.restype=wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    pid=wintypes.DWORD()
    hwnd=user32.GetForegroundWindow()
    if not hwnd:raise StopTest('no_foreground_window')
    user32.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
    if not pid.value:raise StopTest('foreground_pid_missing')
    return psutil.Process(pid.value).name()


def main():
    parser=argparse.ArgumentParser(description='单个近距离目标测试；默认仅检查路线，不截图、不控制游戏')
    parser.add_argument('--route',type=Path,default=paths.DRAFT_ROUTE)
    parser.add_argument('--point',type=int,default=2,help='目标标记点编号，从1计数，默认点2')
    parser.add_argument('--execute',action='store_true',help='明确执行一次有界单点测试')
    parser.add_argument('--game-process',help='执行时必填：游戏的准确进程名，切换到其他进程立即停止')
    parser.add_argument('--delay',type=int,default=15)
    args=parser.parse_args()
    if not 0<=args.delay<=60:parser.error('倒计时需在0～60秒')
    try:start,target=load_point(args.route,args.point)
    except (ValueError,OSError) as exc:parser.error(str(exc))
    print(f'路线起点：{start}；仅测试标记点{args.point}：{target}')
    print(f'路线首点到目标：{math.dist(start,target):.2f}单位；最多{Limits().max_steps}步，每步{Limits().step_seconds:.2f}秒，转向上限{Limits().max_mouse_pixels}像素')
    if not args.execute:
        print('预检完成。未读取游戏画面、未按键；实际执行须指定 --execute 和准确 --game-process。')
        return 0
    if not args.game_process or '/' in args.game_process or '\\' in args.game_process or not args.game_process.lower().endswith('.exe'):
        parser.error('执行必须提供准确游戏进程名，例如通过任务管理器确认；不匹配窗口标题')
    import keyboard
    import pydirectinput
    import mss
    from app.navigation.screen_region import resolve_region
    from app.navigation.coordinate_reader import get_ocr,read_coord
    # Prepare OCR before countdown to avoid surprises in the test budget.
    get_ocr()
    for remaining in range(args.delay,0,-1):
        print(f'{remaining}秒后检查游戏焦点及起点；F12停止，请关闭游戏地图界面。',flush=True)
        time.sleep(1)
    def guard():
        if keyboard.is_pressed('f12'):raise StopTest('emergency_key')
        if foreground_process().casefold()!=args.game_process.casefold():raise StopTest('game_not_foreground')
    folder=paths.ROOT/'outputs/navigation/single_point_tests'/datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    folder.mkdir(parents=True,exist_ok=False)
    try:
        with mss.MSS() as capture:
            region,label=resolve_region(capture.monitors)
            report=run_single(start,target,lambda:read_coord(capture,region),pydirectinput.keyDown,pydirectinput.keyUp,
                              pydirectinput.moveRel,guard)
            report['input_method']='pydirectinput.keyDown/keyUp' 
            report.update(route=str(args.route),point=args.point,region=region,region_source=label,
                          required_game_process=args.game_process)
    except Exception as exc:
        report={'status':'setup_failed','steps':0,'error':str(exc)}
    (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'测试结果：{report["status"]}；记录：{folder}',flush=True)
    return 0 if report['status']=='arrived' else 1

if __name__=='__main__':raise SystemExit(main())
