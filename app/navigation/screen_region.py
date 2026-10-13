"""Exact OCR crop shared by diagnostics, recorder and route runner."""
import json
from app import project_paths as paths

REGION_FILE = paths.ROOT / 'config/navigation/ocr_region.json'


def validate_region(region, desktop):
    keys=('left','top','width','height')
    if not isinstance(region,dict) or any(type(region.get(k)) is not int for k in keys):
        raise ValueError('坐标识别区域必须包含整数 left/top/width/height')
    if not 10 <= region['width'] <= 1000 or not 10 <= region['height'] <= 300:
        raise ValueError('请框选坐标及完整日期时间这一行，宽10～1000、高10～300像素')
    if (region['left'] < desktop['left'] or region['top'] < desktop['top'] or
            region['left']+region['width'] > desktop['left']+desktop['width'] or
            region['top']+region['height'] > desktop['top']+desktop['height']):
        raise ValueError('识别区域已超出当前屏幕，请重新设置')
    return {k:region[k] for k in keys}


def resolve_region(monitors, config_path=REGION_FILE):
    if config_path.exists():
        data=json.loads(config_path.read_text(encoding='utf-8-sig'))
        if data.get('schema') != 1:
            raise ValueError('识别区域配置版本无效，请重新设置')
        return validate_region(data.get('region'),monitors[0]), '用户设置区域'
    mon=monitors[1]
    crop={'left':mon.get('left',0)+10,'top':mon.get('top',0)+mon['height']-35,
          'width':175,'height':35}
    return validate_region(crop,monitors[0]), '默认主屏左下区域（未校准）'


def save_region(region, desktop, config_path=REGION_FILE, content=None):
    region=validate_region(region,desktop)
    config_path.parent.mkdir(parents=True,exist_ok=True)
    temporary=config_path.with_suffix('.tmp')
    data={'schema':1,'region':region,
          'note':'屏幕绝对像素；移动游戏窗口或改变分辨率后应重新设置。'}
    if content is not None:
        if content!='coordinates_and_datetime':raise ValueError('不支持的识别区域内容')
        data['content']=content
    temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.replace(config_path)
    return region
