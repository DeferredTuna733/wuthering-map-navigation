"""Pre-download wuthering.gg z5/z6 map tiles for offline use."""
import argparse, concurrent.futures, hashlib, json, os, tempfile, time
from pathlib import Path
from urllib.request import Request, urlopen
from PIL import Image
import io

from app.project_paths import OFFLINE_TILES
HOST='wuthering.gg'
def download_one(root,z,x,y,timeout=30):
    path=Path(root)/str(z)/f'{x}_{y}.png'; path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        try:
            with Image.open(path) as im:
                im.load()
                if im.size==(256,256): return 'cached',path.stat().st_size
        except Exception: pass
    url=f'https://{HOST}/tiles/{z}/{x}/{y}.png'
    request=Request(url,headers={'User-Agent':'WutheringDemo-OfflineMap/1.0'})
    with urlopen(request,timeout=timeout) as response:
        if response.geturl().split('/')[2] != HOST: raise ValueError('unexpected redirect')
        data=response.read(2*1024*1024+1)
    if len(data)>2*1024*1024 or not data.startswith(b'\x89PNG\r\n\x1a\n'): raise ValueError('invalid png')
    with Image.open(io.BytesIO(data)) as im:
        im.load()
        if im.size!=(256,256): raise ValueError(f'wrong size {im.size}')
    fd,tmp=tempfile.mkstemp(prefix=path.name+'.',suffix='.tmp',dir=path.parent)
    os.close(fd)
    try:
        Path(tmp).write_bytes(data);Path(tmp).replace(path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
    return 'downloaded',len(data)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=OFFLINE_TILES);ap.add_argument('--z',type=int,nargs='+',default=[5,6]);ap.add_argument('--workers',type=int,default=8);args=ap.parse_args()
    root=args.root;root.mkdir(parents=True,exist_ok=True); records=[]; failures=[];overall_start=time.monotonic()
    for z in args.z:
        if not 0<=z<=8: ap.error('z must be 0..8')
        keys=[(z,x,y) for y in range(2**z) for x in range(2**z)]
        done=0;start=time.monotonic()
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
            future={pool.submit(download_one,root,z,x,y):(z,x,y) for z,x,y in keys}
            for f in concurrent.futures.as_completed(future):
                key=future[f]
                try: status,size=f.result();records.append({'z':key[0],'x':key[1],'y':key[2],'status':status,'bytes':size})
                except Exception as e: failures.append({'z':key[0],'x':key[1],'y':key[2],'error':str(e)})
                done+=1
                if done%64==0 or done==len(keys): print(f'z{z}: {done}/{len(keys)} failures={len(failures)}',flush=True)
    records.sort(key=lambda r:(r['z'],r['y'],r['x']))
    manifest={'source':'https://wuthering.gg/tiles/{z}/{x}/{y}.png','tile_size':256,'levels':args.z,'expected':sum(4**z for z in args.z),'records':records,'failures':failures,'completed_at':time.strftime('%Y-%m-%d %H:%M:%S'),'elapsed_seconds':time.monotonic()-overall_start}
    (root/'offline_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'COMPLETE tiles={len(records)} failures={len(failures)} manifest={root/"offline_manifest.json"}')
    return 1 if failures else 0
if __name__=='__main__':raise SystemExit(main())
