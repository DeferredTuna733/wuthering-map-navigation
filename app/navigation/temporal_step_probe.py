"""One short W probe using a matched stationary temporal reference, no steering."""
import argparse
import json
import math
import time
from datetime import datetime
from pathlib import Path
import cv2
from app import project_paths as paths
from app.navigation.scan_sequence import analyze_sequence
from app.navigation.single_point_test import StopTest


def load_reference():
    candidate=json.loads((paths.ROOT/'config/navigation/turning_candidate.json').read_text(encoding='utf-8'))
    report_path=Path(candidate.get('temporal_reference_report',candidate['observations'][-1]['report'])).resolve()
    if not report_path.is_relative_to((paths.ROOT/'outputs/navigation/fixed_turn_sequences').resolve()):
        raise ValueError('转向参考不在项目测试目录内')
    report=json.loads(report_path.read_text(encoding='utf-8'))
    if (report.get('status')!='temporal_estimates' or not report.get('stationary_coordinates_verified')
            or report.get('fixed_turn',{}).get('measurement_status')!='candidate_only'):
        raise ValueError('转向参考未通过原地采样检查')
    frames=[cv2.imread(str(p)) for p in sorted(report_path.parent.glob('frame_[0-9][0-9][0-9].png'))]
    if len(frames)!=40 or any(f is None for f in frames):raise ValueError('参考截图缺失')
    return frames,tuple(report['after_coordinate']),report_path


def match_heading(reference, current, center, radius):
    analysis=analyze_sequence(reference+current,center,radius)
    estimates=analysis.get('estimates',[])[len(reference):]
    values=[e['angle_deg'] for e in estimates if e['angle_deg'] is not None]
    if len(values)<6:return None,analysis
    angle=math.degrees(math.atan2(sum(math.sin(math.radians(a)) for a in values),
                                 sum(math.cos(math.radians(a)) for a in values)))%360
    if max(abs((a-angle+180)%360-180) for a in values)>6:return None,analysis
    return angle,analysis


def one_step(guard, down, up, seconds=.35, clock=time.monotonic, sleep=time.sleep):
    if not .1<=seconds<=.6:raise ValueError('短步时长须为0.1..0.6秒')
    guard()
    try:
        down()
        end=clock()+seconds
        while clock()<end:
            guard();sleep(min(.01,max(0,end-clock())))
    finally:
        up()


def main():
    parser=argparse.ArgumentParser(description='连续方向参考核验及一次短W，不进行鼠标转向')
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--execute',action='store_true')
    mode.add_argument('--read-only',action='store_true')
    parser.add_argument('--delay',type=int,default=15)
    parser.add_argument('--seconds',type=float,default=.35)
    args=parser.parse_args()
    if not 0<=args.delay<=60 or not .1<=args.seconds<=.6:parser.error('delay 0..60; seconds .1..0.6')
    reference,reference_coordinate,reference_path=load_reference()
    if not args.execute and not args.read_only:
        print(f'预检通过：40张连续参考，坐标{reference_coordinate}；未截图，未输入。');return 0
    import ctypes
    from ctypes import wintypes
    import mss,mss.tools,keyboard,numpy as np
    from app.navigation.minimap_heading import resolve_minimap_region
    from app.navigation.screen_region import resolve_region
    from app.navigation.coordinate_reader import get_ocr,read_coord
    from app.navigation.single_point_test import foreground_process
    if args.execute:import pydirectinput
    get_ocr()
    for n in range(args.delay,0,-1):
        print(f'{n}秒后核验方向；切回游戏，保持原地，不动鼠标，F12停止。',flush=True);time.sleep(1)
    folder=paths.ROOT/'outputs/navigation/temporal_step_probes'/datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    folder.mkdir(parents=True,exist_ok=False)
    user32=ctypes.WinDLL('user32',use_last_error=True)
    user32.GetForegroundWindow.restype=wintypes.HWND
    handle=None;movement_sent=False;before=after=None;before_heading=after_heading=None
    result={'reference_report':str(reference_path),'read_only':args.read_only}
    def guard():
        nonlocal handle
        if keyboard.is_pressed('f12'):raise StopTest('emergency_key')
        if foreground_process().casefold()!='client-win64-shipping.exe':raise StopTest('game_not_foreground')
        current=user32.GetForegroundWindow()
        if handle is None:handle=current
        if current!=handle:raise StopTest('window_changed')
    try:
        with mss.MSS() as cap:
            region,_=resolve_region(cap.monitors);mini,circle=resolve_minimap_region(cap.monitors)
            def coordinate(label):
                point=None
                for _ in range(4):
                    guard();point=read_coord(cap,region)
                    if point is not None:break
                    time.sleep(.15)
                guard();shot=cap.grab(region)
                mss.tools.to_png(shot.rgb,shot.size,output=str(folder/(label+'_coordinate.png')))
                return point
            def snapshots(label):
                frames=[]
                for index in range(8):
                    guard();shot=cap.grab(mini)
                    frames.append(cv2.cvtColor(np.asarray(shot),cv2.COLOR_BGRA2BGR))
                    mss.tools.to_png(shot.rgb,shot.size,output=str(folder/f'{label}_{index:02d}.png'))
                    end=time.monotonic()+.15
                    while time.monotonic()<end:guard();time.sleep(.02)
                return frames
            before=coordinate('before')
            if before!=reference_coordinate:raise StopTest('reference_coordinate_mismatch')
            current_frames=snapshots('before')
            before_heading,analysis=match_heading(reference,current_frames,circle['center_xy'],circle['radius'])
            (folder/'before_temporal_analysis.json').write_text(json.dumps(analysis,ensure_ascii=False,indent=2),encoding='utf-8')
            if before_heading is None:raise StopTest('temporal_heading_unresolved')
            # Recheck position immediately before allowing any movement.
            if coordinate('before_recheck')!=before:raise StopTest('coordinate_changed_during_heading_sample')
            if args.read_only:
                result['status']='reference_matched'
            else:
                def down():
                    nonlocal movement_sent
                    movement_sent=True;pydirectinput.keyDown('w')
                one_step(guard,down,lambda:pydirectinput.keyUp('w'),args.seconds)
                time.sleep(.15)
                after=coordinate('after')
                after_frames=snapshots('after')
                after_heading,analysis=match_heading(reference,after_frames,circle['center_xy'],circle['radius'])
                (folder/'after_temporal_analysis.json').write_text(json.dumps(analysis,ensure_ascii=False,indent=2),encoding='utf-8')
                if after is None:raise StopTest('after_ocr_failed')
                dx,dy,dz=[after[i]-before[i] for i in range(3)]
                result.update(coordinate_delta=[dx,dy,dz],coordinate_move_angle_deg=
                              math.degrees(math.atan2(dy,dx))%360 if dx or dy else None)
                if math.hypot(dx,dy)>8 or abs(dz)>5:raise StopTest('abnormal_displacement')
                result['status']='movement_observed' if dx or dy else 'no_coordinate_movement'
                result['heading_after_verified']=after_heading is not None
                result['warning']='One local sample only. Missing post-movement heading prevents full direction cross-validation.'
    except Exception as error:
        result.update(status=str(error) if isinstance(error,StopTest) else 'error',error=str(error))
    result.update(before_coordinate=before,after_coordinate=after,scan_before_deg=before_heading,
                  scan_after_deg=after_heading,movement_keys_sent=movement_sent,mouse_keys_sent=False,
                  step_seconds=args.seconds,navigation_approved=False)
    (folder/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'连续方向核验结束：{result["status"]}；记录：{folder}',flush=True)
    return 0 if result['status'] in ('reference_matched','movement_observed') else 1


if __name__=='__main__':raise SystemExit(main())
