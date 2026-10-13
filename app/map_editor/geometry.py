"""Wuthering.gg main-map geometry from public MapView config (2026-10-09).
Coordinates here are SITE DATA UNITS, not verified game/OCR coordinates.
No navigation export is permitted by this module.
"""
import math

MAP_SIZE = 5950.0
MAP_START_X = 1700.0
MAP_START_Y = 1700.0
DATA_UNITS = 10000.0
TILE_SIZE = 256


def _numbers(*values):
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
        raise ValueError('coordinates must be finite numbers')


def site_xy_to_leaflet(x, y):
    _numbers(x,y)
    lng = (MAP_START_X + x/DATA_UNITS)/MAP_SIZE*256
    lat = -(MAP_START_Y + y/DATA_UNITS)/MAP_SIZE*256
    return lat,lng


def leaflet_to_site_xy(lat, lng):
    _numbers(lat,lng)
    return ((lng/256*MAP_SIZE-MAP_START_X)*DATA_UNITS,
            (-lat/256*MAP_SIZE-MAP_START_Y)*DATA_UNITS)


def site_xy_to_global_pixel(x,y,zoom):
    if isinstance(zoom,bool) or not isinstance(zoom,int) or not 2 <= zoom <= 6:
        raise ValueError('main map zoom must be 2..6')
    lat,lng = site_xy_to_leaflet(x,y)
    return lng*2**zoom,-lat*2**zoom


def global_pixel_to_site_xy(px,py,zoom):
    _numbers(px,py)
    if isinstance(zoom,bool) or not isinstance(zoom,int) or not 2 <= zoom <= 6:
        raise ValueError('main map zoom must be 2..6')
    return leaflet_to_site_xy(-py/2**zoom,px/2**zoom)


def site_xy_to_tile(x,y,zoom):
    px,py=site_xy_to_global_pixel(x,y,zoom)
    tx,ty=math.floor(px/TILE_SIZE),math.floor(py/TILE_SIZE)
    return tx,ty,px-tx*TILE_SIZE,py-ty*TILE_SIZE
