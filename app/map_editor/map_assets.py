"""Strict XYZ-independent stitching and provisional site/game mapping.
Mapping /10000 is measured against user samples, not a sub-unit guarantee.
"""
from pathlib import Path
import hashlib
from PIL import Image


def stitch_tiles(root, zoom, bounds):
    if isinstance(zoom,bool) or not isinstance(zoom,int) or not 2<=zoom<=6:
        raise ValueError('Unsupported main-map zoom')
    x0,y0,x1,y1=bounds
    if not all(isinstance(v,int) and not isinstance(v,bool) for v in bounds):
        raise ValueError('Tile bounds must be integers')
    if not (0<=x0<=x1<2**zoom and 0<=y0<=y1<2**zoom):
        raise ValueError('Tile bounds outside main map')
    canvas=Image.new('RGBA',((x1-x0+1)*256,(y1-y0+1)*256),(5,38,53,255))
    records=[]
    for y in range(y0,y1+1):
        for x in range(x0,x1+1):
            path=Path(root)/f'{x}_{y}.png'
            with Image.open(path) as tile:
                tile.load()
                if tile.size!=(256,256):
                    raise ValueError(f'Unexpected dimensions: {path}')
                canvas.alpha_composite(tile.convert('RGBA'),((x-x0)*256,(y-y0)*256))
            records.append({'x':x,'y':y,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    return canvas.convert('RGB'),records


def candidate_pixel_to_game_xy(px,py,zoom=4,origin_tile=(0,0)):
    from app.map_editor.geometry import global_pixel_to_site_xy
    x,y=global_pixel_to_site_xy(px+origin_tile[0]*256,py+origin_tile[1]*256,zoom)
    return x/10000,y/10000


def candidate_game_to_pixel_xy(x,y,zoom=4,origin_tile=(0,0)):
    from app.map_editor.geometry import site_xy_to_global_pixel
    px,py=site_xy_to_global_pixel(x*10000,y*10000,zoom)
    return px-origin_tile[0]*256,py-origin_tile[1]*256


def checked_metadata_affine(meta, image_size):
    """Recompute geometry instead of trusting arbitrary affine sidecar values."""
    if meta.get('source') != 'wuthering.gg' or meta.get('image_size') != list(image_size):
        raise ValueError('Map metadata does not match image')
    zoom=meta.get('z');origin=meta.get('origin_tile')
    if isinstance(zoom,bool) or not isinstance(zoom,int) or not 2<=zoom<=6:
        raise ValueError('Invalid map zoom')
    if not isinstance(origin,list) or len(origin)!=2 or not all(type(v) is int for v in origin):
        raise ValueError('Invalid tile origin')
    if not all(0<=v<2**zoom for v in origin) or meta.get('tile_size')!=256:
        raise ValueError('Invalid map geometry')
    if any(type(v) is not int or v<=0 or v%256 for v in image_size):
        raise ValueError('Invalid image dimensions')
    if origin[0]+image_size[0]//256>2**zoom or origin[1]+image_size[1]//256>2**zoom:
        raise ValueError('Map extends outside main region')
    scale=5950/(256*2**zoom)
    return (scale,0,origin[0]*256*scale-1700,0,scale,origin[1]*256*scale-1700)
