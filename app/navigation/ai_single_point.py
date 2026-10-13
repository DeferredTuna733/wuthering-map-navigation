"""Screenshot-only AI guarded experiment toward one user-drawn waypoint."""
import json
import math
import queue
import threading
import time
from datetime import datetime
import tkinter as tk
from app import project_paths as paths
from app.navigation.single_point_test import Limits, StopTest, load_point,validate_point,run_single,foreground_process


def turn_response_ok(before, after, pixels):
    change = (after-before+180)%360-180
    expected = pixels/16
    return (change*expected > 0 and abs(change-expected) <= 5 and abs(change) <= 15)


class CoordinateGate:
    """Reject impossible candidates before consensus; never repair a sign."""
    def __init__(self, anchor=None):
        self.anchor=anchor
        self.previous=None

    def offer(self, point):
        from tools.monitor_ai_heading import consistent_coordinate_pair
        if point is None:return None
        if self.anchor is not None and (math.dist(point[:2],self.anchor[:2])>8 or abs(point[2]-self.anchor[2])>5):
            self.previous=None
            return None
        confirmed=consistent_coordinate_pair(self.previous,point)
        self.previous=point
        if confirmed:
            self.anchor=point
            return point
        return None


def trial_points(route,from_point=2,through_point=2):
    if not 2<=from_point<=through_point<=7:raise ValueError('本轮只支持第2～7点内的短路线')
    draft=json.loads(route.read_text(encoding='utf-8-sig'))
    points=draft.get('points',[])
    if len(points)<through_point:raise ValueError('路线目标点不存在')
    selected=points[from_point-2:through_point]
    for a,b in zip(selected,selected[1:]):validate_point(dict(draft,points=[a,b]),2)
    return [tuple(point) for point in selected]


def trial_limits(from_point,through_point):
    if from_point==2 and through_point>4:
        return Limits(max_steps=32,max_seconds=75)
    return Limits(max_steps=16 if through_point>4 else 8,
                  max_seconds=45 if through_point>4 else 25)


def execute(cancel, progress, through_point=2,from_point=2):
    import ctypes
    from ctypes import wintypes
    import cv2
    import mss
    import numpy as np
    import torch
    import pydirectinput
    from ultralytics import YOLO
    from app.navigation.ai_scan import predict_heading
    from app.navigation.coordinate_reader import get_ocr, inspect_crop
    from app.navigation.enhanced_coordinate import inspect_enhanced_crop,plausible
    from app.navigation.screen_region import resolve_region
    from app.navigation.position_anchor import load_anchor
    from app.navigation.minimap_position import RollingPositionTracker
    from app.navigation.terrain_relocalization import TerrainRelocalizer,ocr_seeds
    from app.navigation.position_fusion import fuse_coordinate
    from app.navigation.adaptive_turn import TurnModel,adaptive_turn
    from tools.monitor_ai_heading import consistent_coordinate_pair
    route_points=trial_points(paths.DRAFT_ROUTE,from_point,through_point)
    start,target=route_points[:2]
    torch.set_num_threads(4)
    config=json.loads((paths.ROOT/'config/navigation/scan_capture_station.json').read_text())
    geometry=json.loads((paths.ROOT/'config/navigation/ai_sector_geometry.json').read_text())
    region,circle=config['region'],config['circle']
    if geometry['region']==region and geometry['circle_center_xy']==circle['center_xy'] and geometry['circle_radius']==circle['radius']:
        circle=dict(circle,player_center_xy=geometry['player_center_xy'])
    anchor,reference=load_anchor(paths.ROOT/'data/navigation/position_anchor.json',region,circle)
    tracker=RollingPositionTracker(reference,circle,anchor['angle'],anchor['coordinate_xy'],anchor['affine'])
    relocalizer=TerrainRelocalizer(paths.OFFLINE_TILES/'6',anchor['affine'])
    turn_model=TurnModel()
    turn_cache=paths.ROOT/'data/navigation/adaptive_turn.json'
    turn_context=dict(region=region,circle=circle)
    if turn_cache.exists():
        try:
            cached=json.loads(turn_cache.read_text(encoding='utf-8'))
            if cached.get('schema')==1 and cached.get('context')==turn_context:
                turn_model=TurnModel(cached['gain'])
        except (OSError,ValueError,KeyError,TypeError):pass
    model_path=paths.ROOT/'models/navigation/camera_sector/v3.pt'
    model=YOLO(str(model_path));get_ocr()
    predict_heading(model,np.zeros((region['height'],region['width'],3),np.uint8),circle)
    for count in range(15,0,-1):
        progress.put(f'{count} 秒后开始：切回游戏、站定、关闭地图；F12 停止')
        if cancel.wait(1):return {'status':'cancelled','steps':0}
    folder=paths.ROOT/'outputs/navigation/ai_single_point_tests'/datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    folder.mkdir(parents=True)
    user=ctypes.WinDLL('user32')
    user.GetForegroundWindow.restype=wintypes.HWND
    handle=user.GetForegroundWindow()
    began=time.monotonic();evidence=[]
    limits=trial_limits(from_point,through_point)

    def guard():
        if cancel.is_set() or user.GetAsyncKeyState(0x7B)&0x8000:raise StopTest('emergency_key')
        if time.monotonic()-began>=limits.max_seconds:raise StopTest('time_limit')
        if foreground_process().casefold()!='client-win64-shipping.exe' or user.GetForegroundWindow()!=handle:
            raise StopTest('game_not_foreground')

    with mss.MSS() as cap:
        coord_region,_=resolve_region(cap.monitors)
        last_coordinate=None
        def heading():
            angles=[]
            for _ in range(2):
                guard()
                frame=cv2.cvtColor(np.asarray(cap.grab(region)),cv2.COLOR_BGRA2BGR)
                stamp=time.monotonic()
                result,_=predict_heading(model,frame,circle)
                result['terrain_position']=tracker.observe(frame,result['direction_deg'],stamp)
                guard()
                cv2.imwrite(str(folder/f'heading_{len(evidence):03d}.png'),frame)
                evidence.append(dict(kind='heading',**result))
                angle=result['direction_deg']
                if angle is None:raise StopTest('ai_heading_unresolved')
                angles.append(angle)
            if abs((angles[1]-angles[0]+180)%360-180)>5:raise StopTest('ai_heading_unstable')
            return angles[-1]

        def read():
            nonlocal last_coordinate
            gate=CoordinateGate(last_coordinate)
            for _ in range(6):
                guard()
                frame=cv2.cvtColor(np.asarray(cap.grab(region)),cv2.COLOR_BGRA2BGR)
                stamp=time.monotonic()
                heading_result,_=predict_heading(model,frame,circle);guard()
                angle=heading_result['direction_deg']
                if angle is None:raise StopTest('ai_heading_unresolved')
                position=tracker.observe(frame,angle,stamp)
                crop=np.asarray(cap.grab(coord_region))
                item=inspect_crop(crop,allow_separator_dot=True);guard()
                ocr_stamp=time.monotonic()
                anchor=last_coordinate if last_coordinate is not None else start
                if not plausible(item['coordinate'],anchor) and position['coordinate_xy'] is None:
                    original=item
                    item=inspect_enhanced_crop(crop,anchor);guard()
                    item['primary_diagnostic']=original
                    ocr_stamp=time.monotonic()
                if tracker.blocked and ocr_stamp-stamp<=.3:
                    seeds=ocr_seeds([item])
                    if seeds:
                        recovery=relocalizer.locate(frame,circle,seeds);guard()
                        item['relocalization']=recovery
                        if time.monotonic()-stamp<=.3 and tracker.restore(frame,angle,stamp,recovery):
                            position=dict(status='terrain_relocalized',coordinate_xy=tracker.xy.tolist())
                fused=fuse_coordinate(position,item,stamp,ocr_stamp)
                item.update(fused_coordinate=fused,terrain_position=position,
                            frame_monotonic=stamp,ocr_monotonic=ocr_stamp)
                cv2.imwrite(str(folder/f'position_{len(evidence):03d}.png'),frame)
                cv2.imwrite(str(folder/f'coordinate_{len(evidence):03d}.png'),crop)
                evidence.append(dict(kind='coordinate',**item))
                point=fused['coordinate']
                accepted=gate.offer(point)
                if accepted is not None:
                    last_coordinate=accepted
                    return accepted
                cancel.wait(.04)
            return None

        def down(key):
            heading();guard();pydirectinput.keyDown(key)

        def turn(x,y):
            response=adaptive_turn(x,heading,pydirectinput.moveRel,guard,cancel.wait,turn_model)
            evidence.extend(response.pop('observations'))
            evidence.append(dict(kind='adaptive_turn',**response))
            progress.put(f'转向在线校正：剩余误差 {response["residual"]:.1f}°，继续定位和推进')

        if through_point==2:
            report=run_single(start,target,read,down,pydirectinput.keyUp,turn,guard,
                              limits=limits,correct_sign=False)
        else:
            from app.navigation.short_route_test import run_short_route
            report=run_short_route(route_points,read,down,pydirectinput.keyUp,turn,guard,limits=limits,first_point=from_point)
    report.update(route=str(paths.DRAFT_ROUTE),point=through_point,from_point=from_point,model=str(model_path),
                  adaptive_turn_gain=turn_model.gain,adaptive_turn_samples=turn_model.samples,
                  evidence=evidence,game_memory_read=False,navigation_approved=False,
                  scope=f'Bounded experiment through point {through_point}; coordinate/image handedness remains provisional',
                  report_folder=str(folder))
    (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    if turn_model.samples:
        turn_cache.parent.mkdir(parents=True,exist_ok=True)
        temporary=turn_cache.with_suffix('.tmp')
        temporary.write_text(json.dumps(dict(schema=1,context=turn_context,gain=turn_model.gain,
                                             samples=turn_model.samples,navigation_approved=False,
                                             source_report=str(folder/'report.json')),ensure_ascii=False,indent=2),encoding='utf-8')
        temporary.replace(turn_cache)
    return report


def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--through-point',type=int,choices=range(2,8),default=2)
    parser.add_argument('--from-point',type=int,choices=range(2,8),default=2)
    args=parser.parse_args()
    import ctypes
    administrator=bool(ctypes.windll.shell32.IsUserAnAdmin())
    selected=trial_points(paths.DRAFT_ROUTE,args.from_point,args.through_point)
    start,target=selected[0],selected[-1]
    title='鸣潮 · AI 完整短路线验证' if args.from_point==2 and args.through_point==7 else ('鸣潮 · AI 在线校正短路线' if args.through_point>2 else '鸣潮 · AI 单点试走')
    root=tk.Tk();root.title(title+('（管理员）' if administrator else ''));root.geometry('530x300')
    messages=queue.Queue();results=queue.Queue();cancel=threading.Event();active=False
    limits=trial_limits(args.from_point,args.through_point)
    budget=f'{limits.max_steps} 步 / {limits.max_seconds:g} 秒'
    text=tk.StringVar(value=f'起点 {start}\n目标 {target}\n中心线两侧各 4 单位，超过 6 单位停止\n到达半径 4 单位；全程最多 {budget}\n继续第 {args.from_point}～{args.through_point} 点；F12 或停止按钮结束')
    tk.Label(root,textvariable=text,font=('Microsoft YaHei UI',12),wraplength=490,justify='left').pack(padx=20,pady=20)
    def start_test():
        nonlocal active
        if active:return
        if not administrator:
            text.set('当前游戏以管理员权限运行。请使用 AI单点试走.bat，以管理员权限启动试走程序后再开始。')
            return
        cancel.clear()
        active=True;start_button.config(state='disabled');text.set('准备 AI 和 OCR，随后开始 15 秒倒计时…')
        def worker():
            try:results.put(execute(cancel,messages,args.through_point,args.from_point))
            except Exception as exc:results.put(dict(status='setup_failed',error=str(exc)))
        threading.Thread(target=worker,daemon=True).start()
    start_button=tk.Button(root,text='开始在线校正试走' if args.through_point>2 else '开始单点试走',command=start_test,font=('Microsoft YaHei UI',11))
    start_button.pack(pady=6)
    tk.Button(root,text='停止',command=cancel.set).pack()
    def close():cancel.set();root.withdraw();root.after(500,poll_close)
    def poll_close():
        if active and results.empty():root.after(500,poll_close)
        else:root.destroy()
    root.protocol('WM_DELETE_WINDOW',close)
    def poll():
        nonlocal active
        try:
            while True:text.set(messages.get_nowait())
        except queue.Empty:pass
        if not results.empty():
            active=False
            result=results.get();text.set(f'试走结束：{result["status"]}\n步数：{result.get("steps",0)}\n'+result.get('report_folder',result.get('error','')))
            print(json.dumps({k:v for k,v in result.items() if k not in ('events','evidence')},ensure_ascii=False),flush=True)
        root.after(100,poll)
    root.after(100,poll);root.mainloop()


if __name__=='__main__':main()
