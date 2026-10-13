"""Fuse a fresh terrain XY with independently parsed height; no sign editing."""
import math


def fuse_coordinate(position, diagnostic, frame_time, ocr_time):
    xy=position.get('coordinate_xy')
    point=diagnostic.get('coordinate')
    output=dict(coordinate=None,status='position_unresolved',source=None)
    if not 0<=ocr_time-frame_time<=.3:return dict(output,status='unsynchronized_capture')
    if xy is None:
        if point is not None:return dict(output,coordinate=point,status='coordinate_candidate',source='strict_ocr')
        return output
    if len(xy)!=2 or not all(math.isfinite(v) for v in xy):return output
    # Two OCR variants must independently supply the same height. If only a
    # sign is missed, the already registered map supplies signed XY; OCR is
    # retained unchanged in the diagnostic rather than repaired.
    variants=diagnostic.get('variants',[])
    heights=[]
    for variant in variants:
        candidate=variant.get('coordinate')
        if candidate is None or variant.get('confidence',0)<.8:continue
        if len(candidate)!=3 or not all(math.isfinite(v) for v in candidate):continue
        magnitude_error=math.dist([abs(v) for v in candidate[:2]],[abs(v) for v in xy])
        if magnitude_error<=4:heights.append(candidate[2])
    if len(heights)<2 or len(set(heights))!=1:return dict(output,status='height_or_position_unresolved')
    if point is not None and math.dist(point[:2],xy)>4:
        if math.dist([abs(v) for v in point[:2]],[abs(v) for v in xy])>4:
            return dict(output,status='position_sources_conflict')
        if any(a*b<0 and abs(b)<4 for a,b in zip(point[:2],xy)):
            return dict(output,status='sign_near_zero_axis')
    return dict(output,coordinate=(*xy,heights[0]),status='coordinate_candidate',source='terrain_xy_ocr_height')
