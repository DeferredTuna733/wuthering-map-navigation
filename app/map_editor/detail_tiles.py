"""Main-map z5/z6 tile refinement in original z4 coordinates, asynchronous I/O."""
import io
import math
import time
from pathlib import Path
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, urlopen
from PIL import Image


def fetch_tile(z, x, y):
    url = f'https://wuthering.gg/tiles/{z}/{x}/{y}.png'
    with urlopen(Request(url, headers={'User-Agent':'Mozilla/5.0'}), timeout=8) as response:
        if response.geturl().split('/')[2] != 'wuthering.gg':
            raise ValueError('Unexpected tile redirect')
        data = response.read(2*1024*1024+1)
    if len(data)>2*1024*1024 or not data.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('Invalid PNG tile')
    return data


class DetailTiles:
    def __init__(self, root, seed=None, fetch=None, memory_tiles=192):
        self.root=Path(root);self.seed=Path(seed) if seed else None
        self.fetch=fetch;self.limit=memory_tiles
        self.pool=ThreadPoolExecutor(max_workers=4,thread_name_prefix='map-tiles')
        self.pending={};self.images=OrderedDict();self.retry={}
        self.revision=0;self.closed=False;self.errors=0
        self.wanted=set()

    def _load(self,key):
        z,x,y=key;path=self.root/str(z)/f'{x}_{y}.png'
        seed=self.seed/f'tiles_z{z}'/f'{x}_{y}.png' if self.seed else None
        for local in (path,seed):
            if local and local.exists():
                try:
                    with Image.open(local) as im:
                        im.load()
                        if im.size != (256,256):raise ValueError('Wrong tile size')
                        return im.convert('RGBA')
                except (OSError,ValueError):pass
        if self.fetch is None:
            raise FileNotFoundError(f'offline tile missing: z{z}/{x}/{y}')
        data=self.fetch(z,x,y)
        with Image.open(io.BytesIO(data)) as im:
            im.load()
            if im.size!=(256,256):raise ValueError('Wrong downloaded tile size')
            image=im.convert('RGBA')
        path.parent.mkdir(parents=True,exist_ok=True)
        temporary=path.with_suffix('.tmp');temporary.write_bytes(data);temporary.replace(path)
        return image

    def poll(self):
        changed=False
        for key,future in list(self.pending.items()):
            if not future.done():continue
            del self.pending[key]
            if future.cancelled():continue
            try:image=future.result()
            except Exception:
                self.errors+=1;self.retry[key]=time.monotonic()+30;continue
            self.images[key]=image;self.images.move_to_end(key)
            while len(self.images)>self.limit:self.images.popitem(last=False)
            self.revision+=1;changed=True
        return changed

    @staticmethod
    def visible_keys(size,scale,offset,z):
        factor=2**(z-4);span=256/factor
        x0=max(0,math.floor(-offset[0]/scale/span))
        y0=max(0,math.floor(-offset[1]/scale/span))
        x1=min(2**z-1,math.floor((size[0]-offset[0])/scale/span))
        y1=min(2**z-1,math.floor((size[1]-offset[1])/scale/span))
        return [(z,x,y) for y in range(y0,y1+1) for x in range(x0,x1+1)]

    def refine(self,frame,scale,offset,request=True):
        if self.closed or scale<=1:return frame
        z=5 if scale<=2 else 6
        keys=self.visible_keys(frame.size,scale,offset,z)
        self.wanted=set(keys)
        # Drop obsolete queued work before submitting the newest viewport.
        for key,future in list(self.pending.items()):
            if key not in self.wanted and future.cancel():del self.pending[key]
        if request:
            center=((frame.width/2-offset[0])/scale,(frame.height/2-offset[1])/scale)
            span=256/2**(z-4)
            keys.sort(key=lambda k:(k[1]*span-center[0])**2+(k[2]*span-center[1])**2)
            for key in keys:
                if len(self.pending)>=24:break
                if key not in self.images and key not in self.pending and self.retry.get(key,0)<=time.monotonic():
                    self.pending[key]=self.pool.submit(self._load,key)
        factor=2**(z-4);span=256/factor
        # Composite the available visible mosaic with one affine resample. Identical
        # screen transform for neighboring tiles avoids rounded edge gaps/overlaps.
        available=[key for key in keys if key in self.images]
        if not available:return frame
        x0=min(k[1] for k in keys);y0=min(k[2] for k in keys)
        x1=max(k[1] for k in keys);y1=max(k[2] for k in keys)
        mosaic=Image.new('RGBA',((x1-x0+1)*256,(y1-y0+1)*256))
        for key in available:
            self.images.move_to_end(key)
            tile=self.images[key]
            # Transparent pixels mean map ocean background, not arbitrary black.
            opaque=Image.new('RGBA',(256,256),(5,38,53,255));opaque.alpha_composite(tile)
            mosaic.paste(opaque,((key[1]-x0)*256,(key[2]-y0)*256))
        ox=offset[0]+x0*span*scale;oy=offset[1]+y0*span*scale
        detailed=mosaic.transform(frame.size,Image.Transform.AFFINE,
             (factor/scale,0,-ox*factor/scale,0,factor/scale,-oy*factor/scale),
             resample=Image.Resampling.BILINEAR)
        out=frame.convert('RGBA');out.alpha_composite(detailed)
        return out.convert('RGB')

    def close(self):
        self.closed=True
        self.pool.shutdown(wait=False,cancel_futures=True)
