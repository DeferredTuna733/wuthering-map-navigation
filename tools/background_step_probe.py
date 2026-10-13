"""One guarded short W step; inspect background compensation, never steer."""
import argparse
import ctypes
from ctypes import wintypes
import json
import math
import time
from datetime import datetime
import cv2
import numpy as np
from app import project_paths as paths
from app.navigation.temporal_step_probe import one_step
from app.navigation.single_point_test import foreground_process,StopTest
from app.navigation.moving_scan import estimate_moving_heading
from tools.check_background_heading import load_model,summarize


def displacement(before,after):
    if before is None or after is None:raise StopTest('coordinate_unresolved')
    delta=[after[i]-before[i] for i in range(3)]
    if math.hypot(*delta[:2])>8 or abs(delta[2])>5:raise StopTest('abnormal_displacement')
    return delta


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');parser.add_argument('--delay',type=int,default=15);args=parser.parse_args()
    if not 0<=args.delay<=60:parser.error('delay 0..60')
    reference_file,model,background,reference=load_model()
    if not args.execute:print('预检通过：一次W 0.2秒，无鼠标转向；未截图、未输入。');return
    import mss
    from PIL import Image
    import pydirectinput
    from app.navigation.coordinate_reader import get_ocr,read_coord
    from app.navigation.screen_region import resolve_region
    get_ocr()
    user=ctypes.WinDLL('user32');user.GetForegroundWindow.restype=wintypes.HWND
    handle=None;movement_sent=False
    def emergency():
        if user.GetAsyncKeyState(0x7B)&0x8000:raise StopTest('emergency_key')
    def guard():
        nonlocal handle
        emergency()
        if foreground_process().casefold()!='client-win64-shipping.exe':raise StopTest('game_not_foreground')
        hwnd=user.GetForegroundWindow()
        if handle is None:handle=hwnd
        if hwnd!=handle:raise StopTest('window_changed')
    for remaining in range(args.delay,0,-1):
        emergency();print(f'{remaining}秒后核验并短按W 0.2秒；切回游戏，不操作键鼠，F12停止。',flush=True);time.sleep(1)
    folder=paths.ROOT/'outputs/navigation/background_step_probes'/datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    folder.mkdir(parents=True,exist_ok=False);before=after=None;before_heading=after_heading=None;result={}
    region=model['region'];circle=model['circle']
    try:
        with mss.MSS() as cap:
            ocr_region,_=resolve_region(cap.monitors)
            def coordinate(label):
                point=None
                for _ in range(4):
                    guard();point=read_coord(cap,ocr_region)
                    if point is not None:break
                    time.sleep(.15)
                guard();shot=cap.grab(ocr_region);Image.frombytes('RGB',shot.size,shot.rgb).save(folder/f'{label}_coordinate.png')
                return point
            def headings(label):
                observations=[]
                for index in range(8):
                    guard();shot=cap.grab(region);image=Image.frombytes('RGB',shot.size,shot.rgb)
                    file=folder/f'{label}_{index:02d}.png';image.save(file)
                    frame=cv2.cvtColor(np.asarray(image),cv2.COLOR_RGB2BGR)
                    observation=estimate_moving_heading(reference,background,frame,circle['center_xy'],circle['radius'])
                    observation['image']=str(file);observations.append(observation);guard();time.sleep(.15)
                summary=summarize(observations);summary['observations']=observations;return summary
            before=coordinate('before')
            if before is None:raise StopTest('before_coordinate_unresolved')
            before_heading=headings('before')
            if before_heading['status']!='stable_candidate':raise StopTest('before_heading_unresolved')
            if coordinate('before_recheck')!=before:raise StopTest('coordinate_changed_before_step')
            def down():
                nonlocal movement_sent
                movement_sent=True;pydirectinput.keyDown('w')
            one_step(guard,down,lambda:pydirectinput.keyUp('w'),.2)
            time.sleep(.15);after=coordinate('after');after_heading=headings('after')
            delta=displacement(before,after)
            result.update(status='movement_observed' if delta[0] or delta[1] else 'no_coordinate_movement',coordinate_delta=delta)
    except Exception as error:result.update(status=str(error) if isinstance(error,StopTest) else 'error',error=str(error))
    result.update(reference_report=str(reference_file),before_coordinate=before,after_coordinate=after,
        before_heading=before_heading,after_heading=after_heading,region=region,circle=circle,
        step_seconds=.2,movement_keys_sent=movement_sent,mouse_keys_sent=False,
        navigation_approved=False,accuracy_verified=False)
    (folder/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    if all((folder/f'after_{i:02d}.png').exists() for i in (0,3,7)):
        import shutil
        from tools.scan_labeler import DATA,prepare
        prepare();manifest=DATA/'manifest.json';records=json.loads(manifest.read_text(encoding='utf-8'));group='backgroundstep_'+folder.name
        for i in (0,3,7):
            identity=f'{group}_{i:03d}';source=folder/f'after_{i:02d}.png';shutil.copy2(source,DATA/'images'/f'{identity}.png')
            records.append({'id':identity,'group':group,'source':str(source),'sample_kind':'background_step',
                            'region':region,'circle':circle,'status':'pending'})
        manifest.write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'单步核验：{result["status"]}；报告：{folder}',flush=True)


if __name__=='__main__':main()
