"""Viewport-only renderer with lazy mipmaps and a byte-bounded frame cache."""
import math
from collections import OrderedDict
from PIL import Image


class MapViewportRenderer:
    def __init__(self, image, cache_bytes=24 * 1024 * 1024):
        self.original_size = image.size
        self.levels = [image]
        self.cache_bytes = max(0, int(cache_bytes))
        self.frames = OrderedDict()
        self.frame_bytes = 0
        self.last_key = None
        self.last_frame = None

    def _level(self, scale):
        level = 0
        while min(self.levels[level].size) > 256:
            last = self.levels[level]
            next_width = max(1, last.width // 2)
            if scale * self.original_size[0] / next_width > 1:
                break
            if level + 1 == len(self.levels):
                self.levels.append(last.resize((next_width, max(1, last.height // 2)),
                                               Image.Resampling.BOX))
            level += 1
        return self.levels[level]

    def render(self, viewport_size, scale, offset, quality='final'):
        width, height = map(int, viewport_size)
        if width <= 0 or height <= 0 or not math.isfinite(scale) or scale <= 0:
            raise ValueError('Invalid viewport or map scale')
        ox, oy = offset
        if not all(math.isfinite(v) for v in offset):
            raise ValueError('Invalid viewport offset')
        if quality not in ('preview', 'final'):
            raise ValueError('Unknown render quality')
        key = (width, height, scale, ox, oy, quality)
        if key in self.frames:
            self.frames.move_to_end(key)
            self.last_key, self.last_frame = key, self.frames[key]
            return self.last_frame
        image = self._level(scale)
        rx = image.width / self.original_size[0]
        ry = image.height / self.original_size[1]
        resample = Image.Resampling.NEAREST if quality == 'preview' else Image.Resampling.BILINEAR
        frame = image.transform((width, height), Image.Transform.AFFINE,
                                (rx/scale, 0, -ox*rx/scale, 0, ry/scale, -oy*ry/scale),
                                resample=resample, fillcolor=(16, 16, 16))
        size = width * height * len(frame.getbands())
        if size <= self.cache_bytes:
            while self.frames and self.frame_bytes + size > self.cache_bytes:
                _, removed = self.frames.popitem(last=False)
                self.frame_bytes -= removed.width * removed.height * len(removed.getbands())
            self.frames[key] = frame
            self.frame_bytes += size
        self.last_key, self.last_frame = key, frame
        return frame
