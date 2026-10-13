"""Shared OCR parsing and short-sample consensus; no screen loop on import."""
import re
import time
import json
from datetime import datetime
import cv2
import numpy as np
from rapidocr_onnxruntime import RapidOCR
RANGE_XY = (-5000, 5000)
RANGE_Z = (-500, 600)
OCR_TRIES = 4

_ocr = None

def get_ocr():
    global _ocr
    if _ocr is None:
        _ocr = RapidOCR()
    return _ocr


# ============ OCR 读坐标（复用 read_coord.py 逻辑） ============
def parse_coordinate_text(text, allow_separator_dot=False, require_datetime=False):
    normalized = text.replace("−", "-").replace("—", "-").replace("，", ",")
    # Parse the complete date suffix before coordinates. A merged OCR string
    # such as "4" + "2026-10-12" must produce height 4, never 42.
    dates=list(re.finditer(r'20\d{2}[-/]\d{1,2}[-/]\d{1,2}',normalized))
    if dates:
        if len(dates)!=1:return None,'ambiguous_datetime'
        date=dates[0]
        suffix=normalized[date.end():].strip()
        try:
            datetime.strptime(date.group().replace('/','-'),'%Y-%m-%d')
            if suffix:
                # Observed game footer: HH:MM:SS+8 * HD. Keep unknown
                # trailing UI text rejected, while validating time and zone.
                clock=re.fullmatch(r'(\d{1,2}:\d{2}(?::\d{2})?)(?:\s*([+-])(\d{1,2})(?::(\d{2}))?)?(?:\s*\*\s*HD)?',suffix)
                if clock is None:return None,'datetime_suffix'
                value=clock.group(1)
                datetime.strptime(value,'%H:%M:%S' if value.count(':')==2 else '%H:%M')
                if clock.group(3) is not None:
                    hours=int(clock.group(3));minutes=int(clock.group(4) or 0)
                    if hours>14 or minutes>59 or (hours==14 and minutes):return None,'invalid_timezone'
        except ValueError:return None,'invalid_datetime'
        normalized=normalized[:date.start()].rstrip()
        # Observed OCR artifact at the coordinate/date boundary only.
        # The remaining prefix must still parse as a complete triple below.
        if allow_separator_dot and normalized.endswith('/'):
            normalized=normalized[:-1].rstrip()
    elif require_datetime:
        return None,'datetime_missing_or_truncated'
    # Opt-in for this game's integer coordinate row: OCR can confuse its
    # second comma with a period. Require an existing first comma and exactly
    # three signed integers; never repair digits or infer a missing sign.
    if allow_separator_dot and re.fullmatch(r'\s*-?\d+\s*,\s*-?\d+\s*\.\s*-?\d+\s*', normalized):
        normalized = normalized.replace('.', ',')
    # Require the whole crop to contain a coordinate triple, never select digits
    # embedded in unrelated UI text. No guessed/deleted digits or minus signs.
    match = re.fullmatch(r"\s*[(（]?\s*(-?\d+)\s*[,\s]+\s*(-?\d+)\s*[,\s]+\s*(-?\d+)\s*[)）]?\s*", normalized)
    if match is None:
        return None, "format"
    point = tuple(map(int, match.groups()))
    if not (RANGE_XY[0] <= point[0] <= RANGE_XY[1]
            and RANGE_XY[0] <= point[1] <= RANGE_XY[1]
            and RANGE_Z[0] <= point[2] <= RANGE_Z[1]):
        return None, "range"
    return point, "parsed"


def requires_datetime(crop):
    """Only full-line configured captures require a complete date delimiter."""
    from app.navigation.screen_region import REGION_FILE
    if not REGION_FILE.exists():return False
    data=json.loads(REGION_FILE.read_text(encoding='utf-8-sig'))
    return (data.get('content')=='coordinates_and_datetime'
            and crop.shape[1]==data['region']['width'])


def inspect_crop(crop, allow_separator_dot=False, require_datetime=None):
    """Recognize a preselected numeric row, with two independent image variants."""
    if crop is None or crop.size == 0:
        return {"coordinate": None, "text": "", "confidence": None, "reason": "empty_crop", "variants": []}
    color = cv2.cvtColor(crop, cv2.COLOR_BGRA2BGR) if crop.shape[2] == 4 else crop
    if require_datetime is None:require_datetime=requires_datetime(crop)
    gray = cv2.cvtColor(color, cv2.COLOR_BGR2GRAY)
    enlarged = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    variants = []
    for name, image in (("original", color), ("gray_enlarged", enlarged)):
        # Coordinates are already a cropped single row. Text detection is not
        # needed and was rejecting most low-contrast crops in the user's report.
        result, _ = get_ocr()(image, use_det=False, use_cls=False)
        text = "".join(item[0] for item in result or [])
        confidence = min((float(item[1]) for item in result or []), default=0.0)
        point, reason = parse_coordinate_text(text, allow_separator_dot=allow_separator_dot,
                                              require_datetime=require_datetime)
        if not text:
            reason = "no_text"
        elif confidence < 0.80:
            point, reason = None, "low_confidence"
        variants.append({"name": name, "text": text, "confidence": confidence,
                         "coordinate": point, "reason": reason})
    valid = [v["coordinate"] for v in variants if v["coordinate"] is not None]
    agreed = len(valid) == 2 and valid[0] == valid[1]
    reason = "parsed" if agreed else ("variant_disagreement" if valid else variants[0]["reason"])
    return {"coordinate": valid[0] if agreed else None, "text": variants[0]["text"],
            "confidence": min(v["confidence"] for v in variants), "reason": reason, "variants": variants,
            "datetime_required":require_datetime}


def read_once(sct, region):
    # region is the exact digit crop; screen_region resolves it consistently.
    return inspect_crop(np.asarray(sct.grab(region)))["coordinate"]


def fix_sign(new, old):
    """修正 OCR 偶尔丢负号的问题。"""
    if old is None or new is None:
        return new
    nx, ny, nz = new
    ox, oy, oz = old
    if ox < 0 and nx > 0 and abs(abs(nx) - abs(ox)) < 100:
        nx = -nx
    if oy < 0 and ny > 0 and abs(abs(ny) - abs(oy)) < 100:
        ny = -ny
    return (nx, ny, nz)


def consensus_read(sct, region, tries=OCR_TRIES, reader=None):
    """多读并做一致性筛选；异常跳变不返回，避免误驱动。"""
    reader = read_once if reader is None else reader
    readings = []
    previous = None
    for _ in range(max(1, tries)):
        current = reader(sct, region)
        if current:
            current = fix_sign(current, previous)
            readings.append(current)
            previous = current
        time.sleep(0.02)
    if not readings:
        return None
    # 找最大一致簇：静止/正常短采样时坐标变化应很小；Z误读(如1/14/15)会被排除。
    best = []
    for candidate in readings:
        cluster = [item for item in readings
                   if abs(item[0] - candidate[0]) <= 12
                   and abs(item[1] - candidate[1]) <= 12
                   and abs(item[2] - candidate[2]) <= 3]
        if len(cluster) > len(best):
            best = cluster
    if len(best) < 2:
        return None
    return tuple(int(round(sum(item[index] for item in best) / len(best))) for index in range(3))





def read_coord(sct, region, tries=OCR_TRIES):
    return consensus_read(sct, region, tries)
