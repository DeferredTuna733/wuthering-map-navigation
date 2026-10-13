"""Read-only camera-turn capture and temporal scan-sector analysis."""
import argparse
import json
import math
import time
from datetime import datetime
import cv2
import numpy as np
from app import project_paths as paths


def scheduled_turn(index, pixels, move, guard, events, direction=1):
    """One bounded turn in twelve chunks; injectable for input-free tests."""
    if type(pixels) is not int or not 20<=pixels<=240:
        raise ValueError('pixels must be 20..240')
    if type(direction) is not int or direction not in (-1,1):
        raise ValueError('direction must be -1 or 1')
    if not 8<=index<20:return
    chunk=index-8
    amount=direction*(round((chunk+1)*pixels/12)-round(chunk*pixels/12))
    guard()
    event={'frame':index,'relative_x':amount,'relative_y':0,'completed':False}
    events.append(event)
    move(amount,0)
    event['completed']=True
    guard()


def summarize_fixed_turn(analysis, events):
    """Report a candidate sensitivity, never mark automatic calibration verified."""
    result={'calibration_verified':False,'relative_units_completed':sum(
        e['relative_x'] for e in events if e['completed'])}
    estimates=analysis.get('estimates',[])
    before=[e['angle_deg'] for e in estimates[:8] if e['angle_deg'] is not None]
    after=[e['angle_deg'] for e in estimates[-8:] if e['angle_deg'] is not None]
    if len(before)<6 or len(after)<6:
        return dict(result,measurement_status='insufficient_heading_samples')
    def average(angles):
        return math.degrees(math.atan2(sum(math.sin(math.radians(a)) for a in angles),
                                      sum(math.cos(math.radians(a)) for a in angles)))%360
    start,end=average(before),average(after)
    spread=max(abs((a-end+180)%360-180) for a in after)
    delta=(end-start+180)%360-180
    result.update(scan_before_deg=start,scan_after_deg=end,scan_change_deg=delta)
    if spread>6 or not 6<=abs(delta)<=120 or result['relative_units_completed']==0:
        return dict(result,measurement_status='insufficient_or_unstable_rotation')
    return dict(result,measurement_status='candidate_only',
                relative_units_per_degree=abs(result['relative_units_completed'])/abs(delta))


def analyze_sequence(frames, center, radius):
    """Temporal estimates for a stationary map, never navigation calibration.

    Remove the static angular background and global illumination change. Reject
    map displacement, inadequate view change, and competing moving sectors.
    """
    if len(frames)<8 or any(f.shape!=frames[0].shape for f in frames):
        return {'status':'insufficient_frames','estimates':[]}
    cx,cy=center
    yy,xx=np.indices(frames[0].shape[:2])
    ring=(np.hypot(xx-cx,yy-cy)>.25*radius)&(np.hypot(xx-cx,yy-cy)<.85*radius)
    window=cv2.createHanningWindow((frames[0].shape[1],frames[0].shape[0]),cv2.CV_32F)
    first=cv2.cvtColor(frames[0],cv2.COLOR_BGR2GRAY).astype(np.float32)
    reference=cv2.Laplacian(first,cv2.CV_32F)*ring
    profiles=[]
    angles=np.arange(360)
    radians=np.deg2rad(angles)
    radii=np.linspace(.30*radius,.82*radius,40)
    map_x=(cx+np.cos(radians)[:,None]*radii).astype(np.float32)
    map_y=(cy+np.sin(radians)[:,None]*radii).astype(np.float32)
    shifts=[]
    for frame in frames:
        gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY).astype(np.float32)
        # OpenCV applies the window in place; preserve the shared reference.
        shift,response=cv2.phaseCorrelate(reference.copy(),cv2.Laplacian(gray,cv2.CV_32F)*ring,window.copy())
        shifts.append({'shift_xy':list(shift),'response':response})
        if response<.15 or math.hypot(*shift)>2:
            return {'status':'map_alignment_failed','alignment':shifts,'estimates':[]}
        # Static icons cancel temporally. A saturation mask would change when
        # the translucent overlay passes over them and create artificial motion.
        # The central yellow arrow is excluded by the inner sampling radius.
        polar=cv2.remap(gray-float(np.median(gray[ring])),map_x,map_y,cv2.INTER_LINEAR)
        profile=np.median(polar,axis=1)
        profiles.append(np.asarray(profile))
    profiles=np.asarray(profiles)
    # Fit disappearance of the initial sector AND appearance of the new one.
    # A temporal median alone erases the initial scan when most frames are still.
    difference=profiles-profiles[0]
    difference-=np.median(difference,axis=1)[:,None]
    variation=float(np.percentile(np.std(difference,axis=0),90))
    if variation<1:
        return {'status':'insufficient_view_change','variation':variation,'estimates':[]}
    directions=np.arange(0,360,3)
    templates=(np.abs((angles[None,:]-directions[:,None]+180)%360-180)<33).astype(float)
    energy=np.sum(difference*difference,axis=1)
    hypotheses=[]
    for initial in range(len(directions)):
        model=templates-templates[initial]
        norm=np.sum(model*model,axis=1)
        dot=difference@model.T
        amplitudes=np.clip(dot/np.maximum(norm,1),0,80)
        costs=energy[:,None]-2*amplitudes*dot+amplitudes*amplitudes*norm
        selected=np.argmin(costs,axis=1)
        errors=costs[np.arange(len(profiles)),selected]
        hypotheses.append((float(errors.sum()),initial,selected,
                           amplitudes[np.arange(len(profiles)),selected],errors))
    hypotheses.sort(key=lambda h:h[0])
    cost,initial,selected,amplitudes,errors=hypotheses[0]
    initial_angle=float(directions[initial])
    competitors=[h[0] for h in hypotheses
                  if abs((float(directions[h[1]])-initial_angle+180)%360-180)>15]
    competitor=min(competitors,default=cost)
    explained=1-cost/max(float(energy.sum()),1)
    if explained<.55 or competitor<cost*1.20:
        return {'status':'scan_ambiguous','variation':variation,'alignment':shifts,
                'explained_fraction':explained,'estimates':[]}
    estimates=[]
    for index,(choice,amplitude,error) in enumerate(zip(selected,amplitudes,errors)):
        quiet=math.sqrt(float(energy[index])/360)<2
        valid=quiet or (amplitude>=3 and error/max(float(energy[index]),1)<.55)
        angle=initial_angle if quiet else float(directions[choice])
        estimates.append({'angle_deg':angle if valid else None,
                          'overlay_amplitude':float(amplitude),
                          'model_residual_fraction':float(error/max(float(energy[index]),1)),
                          'initial_context':quiet})
    if variation<2:
        # Weak overlays need stronger evidence than the ordinary model fit.
        values=[e['angle_deg'] for e in estimates]
        valid=[a for a in values if a is not None]
        endpoints=values[:8]+values[-8:]
        delta=(valid[-1]-valid[0]+180)%360-180 if valid else 0
        increments=[(b-a+180)%360-180 for a,b in zip(valid,valid[1:])]
        coherent=(len(valid)>=len(values)*.9 and all(a is not None for a in endpoints)
                  and max(abs((a-values[0]+180)%360-180) for a in values[:8])<=3
                  and max(abs((a-values[-1]+180)%360-180) for a in values[-8:])<=3
                  and 9<=abs(delta)<=45
                  and all(-3<=step*(1 if delta>0 else -1)<=9 for step in increments))
        if explained<.70 or not coherent:
            return {'status':'weak_scan_unverified','variation':variation,'alignment':shifts,
                    'explained_fraction':explained,'estimates':[]}
    return {'status':'temporal_estimates','variation':variation,'alignment':shifts,
            'weak_signal':variation<2,
            'initial_direction_deg':initial_angle,'explained_fraction':explained,
            'estimates':estimates,'warning':'Diagnostic model estimates only; not verified navigation directions.'}


def main():
    parser=argparse.ArgumentParser(description='连续只读小地图采样，用户手动原地转视角')
    parser.add_argument('--capture',action='store_true')
    parser.add_argument('--execute',action='store_true',help='固定量相对右转，不按移动键')
    parser.add_argument('--pixels',type=int,default=120)
    parser.add_argument('--direction',choices=('right','left'),default='right')
    parser.add_argument('--delay',type=int,default=5)
    parser.add_argument('--seconds',type=int,default=10)
    args=parser.parse_args()
    if not 0<=args.delay<=60 or not 4<=args.seconds<=20:parser.error('delay 0..60; seconds 4..20')
    if args.capture and args.execute:parser.error('--capture与--execute不能同时使用')
    if not 20<=args.pixels<=240:parser.error('pixels 20..240')
    if args.execute and args.seconds!=10:parser.error('固定转向采样使用10秒')
    if not args.capture and not args.execute:
        print('预检：连续只读采样，不发送键鼠输入；--capture开始采样。');return
    import mss
    import mss.tools
    import keyboard
    from app.navigation.minimap_heading import resolve_minimap_region
    from app.navigation.screen_region import resolve_region
    from app.navigation.coordinate_reader import get_ocr,read_coord
    from app.navigation.single_point_test import foreground_process,StopTest
    import ctypes
    from ctypes import wintypes
    user32=ctypes.WinDLL('user32',use_last_error=True)
    user32.GetForegroundWindow.restype=wintypes.HWND
    window_handle=None
    if args.execute:
        import pydirectinput
    get_ocr()
    for n in range(args.delay,0,-1):
        instruction=('程序固定'+('右转' if args.direction=='right' else '左转')+'，请勿手动移动鼠标或按移动键') if args.execute else '原地缓慢转视角，不按移动键'
        print(f'{n}秒后开始，请切回游戏；{instruction}。',flush=True)
        time.sleep(1)
    folder=paths.ROOT/'outputs/navigation'/('fixed_turn_sequences' if args.execute else 'scan_sequences')/datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    folder.mkdir(parents=True,exist_ok=False)
    frames=[];timestamps=[];before=after=None;diagnostic=None;input_events=[]
    def guard():
        nonlocal window_handle
        if keyboard.is_pressed('f12'):raise StopTest('emergency_key')
        if foreground_process().casefold()!='client-win64-shipping.exe':raise StopTest('game_not_foreground')
        current=user32.GetForegroundWindow()
        if window_handle is None:window_handle=current
        if current!=window_handle:raise StopTest('window_changed')
    try:
        with mss.MSS() as cap:
            mini,circle=resolve_minimap_region(cap.monitors)
            region,_=resolve_region(cap.monitors)
            guard();before=read_coord(cap,region)
            ocr_shot=cap.grab(region)
            mss.tools.to_png(ocr_shot.rgb,ocr_shot.size,output=str(folder/'before_coordinate.png'))
            if before is None:raise StopTest('initial_ocr_failed')
            began=time.monotonic()
            for index in range(args.seconds*4):
                if args.execute:
                    scheduled_turn(index,args.pixels,
                        lambda x,y:pydirectinput.moveRel(x,y,relative=True,_pause=False),guard,input_events,
                        direction=1 if args.direction=='right' else -1)
                guard();shot=cap.grab(mini)
                frames.append(cv2.cvtColor(np.asarray(shot),cv2.COLOR_BGRA2BGR))
                timestamps.append(time.monotonic()-began)
                mss.tools.to_png(shot.rgb,shot.size,output=str(folder/f'frame_{index:03d}.png'))
                end=began+(index+1)*.25
                while time.monotonic()<end:guard();time.sleep(.02)
            guard();after=read_coord(cap,region)
            ocr_shot=cap.grab(region)
            mss.tools.to_png(ocr_shot.rgb,ocr_shot.size,output=str(folder/'after_coordinate.png'))
            diagnostic=analyze_sequence(frames,circle['center_xy'],circle['radius'])
            if after is None:raise StopTest('final_ocr_failed')
            if before!=after:raise StopTest('coordinate_changed')
            result=diagnostic
    except Exception as error:
        result={'status':str(error) if isinstance(error,StopTest) else 'error','error':str(error)}
    result.update(before_coordinate=before,after_coordinate=after,frame_count=len(frames),
                  timestamps=timestamps,movement_keys_sent=False,mouse_keys_sent=bool(input_events),
                  input_events=input_events,input_direction=args.direction if args.execute else None)
    result['stationary_coordinates_verified']=before is not None and before==after
    if diagnostic is not None and result is not diagnostic:
        result['unverified_diagnostic']=diagnostic
    if args.execute:
        result['fixed_turn']=summarize_fixed_turn(result,input_events) if result['stationary_coordinates_verified'] else {
            'calibration_verified':False,'measurement_status':'stationary_coordinates_unverified'}
    (folder/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'采样结束：{result["status"]}；记录：{folder}',flush=True)


if __name__=='__main__':main()
