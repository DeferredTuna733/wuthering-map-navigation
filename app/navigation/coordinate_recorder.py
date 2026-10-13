"""Record game coordinates using the same reader as navigation; no game input."""
import argparse
import json
import time
from pathlib import Path
import mss
from app import project_paths as paths
from app.navigation.coordinate_reader import read_coord, fix_sign
from app.navigation.screen_region import resolve_region


def main():
    parser=argparse.ArgumentParser(description='只读录制游戏坐标，不控制游戏')
    parser.add_argument('--output',type=Path,default=paths.RECORDED_ROUTE)
    parser.add_argument('--overwrite',action='store_true')
    args=parser.parse_args()
    if args.output.exists() and not args.overwrite:
        parser.error('目标已存在；另选 --output，或明确使用 --overwrite')
    route=[];last=None
    print('开始只读录制，Ctrl+C停止并保存')
    with mss.MSS() as sct:
        region, _ = resolve_region(sct.monitors)
        try:
            while True:
                point=read_coord(sct,region)
                if point is not None:
                    point=fix_sign(point,last)
                    if point != last:
                        route.append(point);last=point;print(f'[{len(route)}] {point}',flush=True)
                time.sleep(.05)
        except KeyboardInterrupt:pass
    if not route:
        print('没有有效坐标，不创建空路线');return 1
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('w' if args.overwrite else 'x',encoding='utf-8') as stream:
        json.dump(route,stream,ensure_ascii=False,indent=2)
    print(f'已保存：{args.output}');return 0

if __name__=='__main__':raise SystemExit(main())
