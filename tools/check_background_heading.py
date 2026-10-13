"""Fresh read-only heading checks against a saved sweep background."""
import argparse
import ctypes
import json
import math
import time
from datetime import datetime
import cv2
import numpy as np
from app import project_paths as paths
from app.navigation.moving_scan import estimate_moving_heading
from app.navigation.robust_scan import estimate_robust_heading
from app.navigation.rolling_background import RollingBackground
from tools.scan_labeler import DATA,prepare


def summarize(observations):
    angles=[r['direction_deg'] for r in observations if r.get('direction_deg') is not None]
    result={'status':'insufficient_heading_samples','direction_deg':None,'accepted':len(angles),
            'total':len(observations),'navigation_approved':False,'accuracy_verified':False}
    if len(angles)<6:return result
    angle=math.degrees(math.atan2(sum(math.sin(math.radians(a)) for a in angles),
                                sum(math.cos(math.radians(a)) for a in angles)))%360
    spread=max(abs((a-angle+180)%360-180) for a in angles)
    result['spread_deg']=spread
    if spread>6:return dict(result,status='unstable_heading')
    return dict(result,status='stable_candidate',direction_deg=angle)


def load_model():
    reports=sorted((paths.ROOT/'outputs/navigation/sweep_backgrounds').glob('*/report.json'),reverse=True)
    if not reports:raise ValueError('No sweep background has been built')
    file=reports[0];report=json.loads(file.read_text(encoding='utf-8'))
    config=json.loads((paths.ROOT/'config/navigation/scan_capture_station.json').read_text(encoding='utf-8'))
    if report['region']!=config['region'] or report['circle']!=config['circle']:
        raise ValueError('截图区域已变化，需要重新建立对应背景参考')
    if report.get('model',{}).get('status')!='sweep_background_candidate':raise ValueError('背景参考状态无效')
    background=np.load(file.parent/'background.npy',allow_pickle=False)
    reference=cv2.imread(str(file.parent/'reference.png'))
    region=report['region']
    if reference is None or background.shape!=(region['height'],region['width']):raise ValueError('背景参考尺寸无效')
    return file,report,background,reference


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--capture',action='store_true');parser.add_argument('--robust',action='store_true');parser.add_argument('--rolling',action='store_true');parser.add_argument('--alignment-limit',type=float,default=4);parser.add_argument('--delay',type=int,default=15);args=parser.parse_args()
    if not 0<=args.delay<=60:parser.error('delay must be 0..60')
    if not 0<args.alignment_limit<=12:parser.error('alignment-limit must be greater than 0 and at most 12')
    if not args.robust and args.alignment_limit!=4:parser.error('experimental alignment-limit requires --robust')
    if args.rolling and (not args.robust or args.alignment_limit!=12):parser.error('--rolling requires --robust --alignment-limit 12')
    file,model,background,reference=load_model()
    if not args.capture:print(f'只读预检通过：{file}；未截图、未发送输入。');return
    import mss
    from PIL import Image
    key=ctypes.WinDLL('user32').GetAsyncKeyState
    def check():
        if key(0x7B)&0x8000:raise RuntimeError('F12停止采样')
    for remaining in range(args.delay,0,-1):
        check();print(f'{remaining}秒后只读采样：切回游戏，保持位置、视角不动；F12停止。',flush=True);time.sleep(1)
    folder=paths.ROOT/'outputs/navigation/background_heading_checks'/datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    folder.mkdir(parents=True,exist_ok=False);observations=[];result={};region=model['region'];circle=model['circle']
    rolling=RollingBackground(reference,background,circle['center_xy'],circle['radius']) if args.rolling else None
    try:
        with mss.MSS() as cap:
            for index in range(8):
                check();shot=cap.grab(region);image=Image.frombytes('RGB',shot.size,shot.rgb)
                target=folder/f'frame_{index:02d}.png';image.save(target)
                frame=cv2.cvtColor(np.asarray(image),cv2.COLOR_RGB2BGR)
                if rolling is not None:
                    observation=rolling.observe(frame)
                    observation['fixed_reference_comparison']=estimate_robust_heading(reference,background,frame,circle['center_xy'],circle['radius'],alignment_limit=args.alignment_limit)
                elif args.robust:
                    observation=estimate_robust_heading(reference,background,frame,circle['center_xy'],circle['radius'],alignment_limit=args.alignment_limit)
                else:
                    observation=estimate_moving_heading(reference,background,frame,circle['center_xy'],circle['radius'])
                observation['image']=str(target);observations.append(observation)
                time.sleep(.15)
        result=summarize(observations)
        if rolling is not None:
            # Diagnostic snapshots only; never load these automatically on a
            # later run or replace the original sweep background.
            np.save(folder/'rolling_background.npy',rolling.background,allow_pickle=False)
            np.save(folder/'rolling_valid.npy',rolling.valid,allow_pickle=False)
            cv2.imwrite(str(folder/'rolling_reference.png'),rolling.reference)
            result['rolling_updates']=rolling.updates
            result['rolling_travel_pixels']=rolling.travel
        # Keep independent human ground truth for three fresh images.
        prepare();manifest=DATA/'manifest.json';records=json.loads(manifest.read_text(encoding='utf-8'))
        import shutil
        group='backgroundcheck_'+folder.name
        for index in (0,3,7):
            identity=f'{group}_{index:03d}';target=DATA/'images'/f'{identity}.png'
            shutil.copy2(folder/f'frame_{index:02d}.png',target)
            records.append({'id':identity,'group':group,'source':str(folder/f'frame_{index:02d}.png'),
                'sample_kind':'fresh_background_check','region':region,'circle':circle,'status':'pending'})
        manifest.write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    except Exception as error:result={'status':'error','error':str(error)}
    result.update(rolling_scope='current_capture_only' if args.rolling else None,alignment_limit_pixels=args.alignment_limit,method='rolling_radial_profile' if args.rolling else ('robust_radial_profile' if args.robust else 'pixelwise_sector'),reference_report=str(file),observations=observations,region=region,circle=circle,
                  navigation_approved=False,accuracy_verified=False,movement_keys_sent=False,mouse_keys_sent=False)
    (folder/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'只读核验：{result["status"]}；报告：{folder}',flush=True)


if __name__=='__main__':main()
