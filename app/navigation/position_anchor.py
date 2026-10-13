"""Versioned, image-verified development anchor; never implies current location."""
import hashlib
import json
from pathlib import Path
import cv2
import numpy as np


def save_anchor(path, image, *, region, circle, coordinate_xy, angle, affine, source):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    image_path = path.with_suffix('.png')
    if not cv2.imwrite(str(image_path), image):
        raise ValueError('Cannot save anchor image')
    data = dict(version=1, image=image_path.name,
                image_sha256=hashlib.sha256(image_path.read_bytes()).hexdigest(),
                region=region, circle=circle, coordinate_xy=coordinate_xy,
                angle=angle, affine=affine, zoom=6, source=source,
                navigation_approved=False)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def load_anchor(path, region, circle):
    path = Path(path)
    data = json.loads(path.read_text(encoding='utf-8'))
    if data['version'] != 1 or data['region'] != region or data['circle'] != circle:
        raise ValueError('Anchor capture configuration changed; recalibration required')
    image_path = path.parent / data['image']
    if image_path.resolve().parent != path.parent.resolve():
        raise ValueError('Invalid anchor image path')
    if hashlib.sha256(image_path.read_bytes()).hexdigest() != data['image_sha256']:
        raise ValueError('Anchor image checksum mismatch')
    image = cv2.imread(str(image_path))
    affine = np.asarray(data['affine'], dtype=float)
    xy = np.asarray(data['coordinate_xy'], dtype=float)
    if (image is None or image.shape[:2] != (region['height'], region['width'])
            or affine.shape != (2, 3) or xy.shape != (2,)
            or not np.isfinite(affine).all() or not np.isfinite(xy).all()
            or not np.isfinite(data['angle']) or data['zoom'] != 6
            or abs(np.linalg.det(affine[:, :2])) < 1e-8):
        raise ValueError('Invalid anchor calibration')
    return data, image
