"""Validated game-coordinate editing without integer pixel rounding."""
import math
import re


def parse_xy(text):
    parts = re.split(r'[,，\s]+', text.strip())
    if len(parts) != 2:
        raise ValueError('请输入两个坐标，例如 -740, 1136')
    try:
        point = tuple(float(v) for v in parts)
    except ValueError:
        raise ValueError('X、Y 必须是数字') from None
    if not all(math.isfinite(v) and abs(v) <= 5000 for v in point):
        raise ValueError('坐标必须是 -5000～5000 之间的有限数字')
    return point


def game_to_pixel(transform, point, image_size):
    if transform is None:
        raise ValueError('地图坐标映射未就绪')
    a, b, c, d, e, f = transform
    determinant = a*e-b*d
    if not math.isfinite(determinant) or abs(determinant) < 1e-12:
        raise ValueError('地图坐标映射无法反算')
    x, y = point
    if not all(math.isfinite(v) and abs(v) <= 5000 for v in point):
        raise ValueError('路线包含无效坐标')
    px = (e*(x-c)-b*(y-f))/determinant
    py = (a*(y-f)-d*(x-c))/determinant
    if not (0 <= px < image_size[0] and 0 <= py < image_size[1]):
        raise ValueError('坐标不在当前本地地图范围内')
    return px, py


def import_points(data, transform, image_size):
    if not isinstance(data, dict) or data.get('source') != 'wuthering.gg':
        raise ValueError('请选择本工具导出的 wuthering.gg 路线 JSON')
    if data.get('image_size') != list(image_size) or data.get('pixel_to_game_affine') != list(transform):
        raise ValueError('路线所用地图或坐标映射与当前地图不同')
    points = data.get('points')
    if not isinstance(points, list) or not points or len(points) > 10000:
        raise ValueError('路线需包含 1～10000 个点')
    result = []
    for point in points:
        if not isinstance(point, list) or len(point) != 2 or any(type(v) not in (int, float) for v in point):
            raise ValueError('每个路线点必须是两个数字')
        result.append(game_to_pixel(transform, point, image_size))
    return result
