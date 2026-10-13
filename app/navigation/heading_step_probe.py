"""One short W-step cross-check: coordinate displacement vs white scan heading."""
import argparse,ctypes,json,math,time
from ctypes import wintypes
from datetime import datetime
from app import project_paths as paths
from app.navigation.single_point_test import StopTest,foreground_process
from app.navigation.minimap_heading import detect_scan_heading,resolve_minimap_region
from app.navigation.coordinate_reader import get_ocr,read_coord
from app.navigation.screen_region import resolve_region

def main():
 p=argparse.ArgumentParser(description='一次短W方向交叉验证，不进行鼠标修正')
 p.add_argument('--execute',action='store_true');p.add_argument('--game-process',default='Client-Win64-Shipping.exe');p.add_argument('--delay',type=int,default=15);p.add_argument('--seconds',type=float,default=.35)
 p.add_argument('--read-only',action='store_true',help='只保存小地图与识别结果，不发送键鼠输入')
 a=p.parse_args()
 if a.read_only and a.execute:p.error('--read-only不能与--execute同时使用')
 if not a.execute and not a.read_only:print('预检完成：需要--execute才会按一次W');return 0
 if not 0<=a.delay<=60 or not .1<=a.seconds<=.6:p.error('delay 0..60, seconds .1..0.6')
 import keyboard,pydirectinput,mss,mss.tools,numpy as np
 get_ocr()
 for n in range(a.delay,0,-1):print(f'{n}秒后'+('只读小地图采样，不发送键鼠输入' if a.read_only else '进行一次W短步')+'；请保持游戏前台，F12停止',flush=True);time.sleep(1)
 folder=paths.ROOT/('outputs/navigation/heading_readings' if a.read_only else 'outputs/navigation/heading_step_probes')/datetime.now().strftime('%Y%m%d_%H%M%S_%f');folder.mkdir(parents=True,exist_ok=False)
 user32=ctypes.WinDLL('user32',use_last_error=True);user32.GetForegroundWindow.restype=wintypes.HWND;handle=None
 def guard():
  nonlocal handle
  if keyboard.is_pressed('f12'):raise StopTest('emergency_key')
  if foreground_process().casefold()!=a.game_process.casefold():raise StopTest('game_not_foreground')
  current=user32.GetForegroundWindow()
  if handle is None:handle=current
  if current!=handle:raise StopTest('window_changed')
 movement_sent=False
 try:
  with mss.MSS() as cap:
   ocr_region,_=resolve_region(cap.monitors);mini, circle=resolve_minimap_region(cap.monitors)
   def sample(label,retries=1):
    guard()
    coord=None
    for attempt in range(retries):
     guard()
     coord=read_coord(cap,ocr_region)
     if coord is not None:break
     time.sleep(.15)
    shot=cap.grab(mini)
    crop=np.asarray(shot)
    heading=detect_scan_heading(crop,center=circle['center_xy'],radius=circle['radius'])
    mss.tools.to_png(shot.rgb,shot.size,output=str(folder/(label+'.png')))
    (folder/(label+'_heading.json')).write_text(json.dumps(heading.__dict__,ensure_ascii=False,indent=2),encoding='utf-8')
    return coord,heading
   before,b_heading=sample('01_before',retries=4)
   if a.read_only:
    result={'status':'sample_saved','before_coordinate':before,'heading':b_heading.__dict__,'movement_keys_sent':False,'mouse_keys_sent':False}
    (folder/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'只读采样完成；记录：{folder}',flush=True)
    return 0
   if before is None or b_heading.angle_deg is None:raise StopTest('initial_sample_failed')
   guard();movement_sent=True
   try:
    pydirectinput.keyDown('w')
    end=time.monotonic()+a.seconds
    while time.monotonic()<end:guard();time.sleep(.01)
   finally:pydirectinput.keyUp('w')
   time.sleep(.15);after,a_heading=sample('02_after',retries=4)
   scan_change=((a_heading.angle_deg-b_heading.angle_deg+180)%360)-180 if a_heading.angle_deg is not None else None
   if after is None:
    raise StopTest('after_ocr_failed')
   if a_heading.angle_deg is None:raise StopTest('after_heading_failed')
   dx=after[0]-before[0];dy=after[1]-before[1];move_angle=math.degrees(math.atan2(dy,dx))%360 if dx or dy else None
   result={'status':'observed','before_coordinate':before,'after_coordinate':after,'coordinate_delta':[dx,dy,after[2]-before[2]],'coordinate_move_angle_deg':move_angle,'scan_before_deg':b_heading.angle_deg,'scan_after_deg':a_heading.angle_deg,'scan_change_deg':scan_change,'step_seconds':a.seconds,'movement_keys_sent':'W once','mouse_keys_sent':False,'warning':'This is one stationary-context sample; do not infer global mapping from it.'}
 except StopTest as exc:
  result={'status':str(exc),'movement_keys_sent':movement_sent,'mouse_keys_sent':False}
  if 'before' in locals():
   result.update(before_coordinate=before,scan_before_deg=getattr(b_heading,'angle_deg',None))
  if 'after' in locals():
   result.update(after_coordinate=after,scan_after_deg=getattr(a_heading,'angle_deg',None))
  if 'b_heading' in locals() and 'a_heading' in locals() and a_heading.angle_deg is not None:
   result['scan_change_deg']=((a_heading.angle_deg-b_heading.angle_deg+180)%360)-180
 except Exception as exc:result={'status':'error','error':str(exc),'movement_keys_sent':movement_sent,'mouse_keys_sent':False}
 (folder/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(f'方向交叉验证结束：{result["status"]}；记录：{folder}',flush=True);return 0 if result['status']=='observed' else 1
if __name__=='__main__':raise SystemExit(main())
