"""Anchored contrast fallback; text and signs must come from image OCR."""
import math
import cv2
import numpy as np
from app.navigation.coordinate_reader import get_ocr,parse_coordinate_text,requires_datetime


def plausible(point,anchor):
    return (point is not None and anchor is not None and
            math.dist(point[:2],anchor[:2])<=8 and
            (len(anchor)==2 or abs(point[2]-anchor[2])<=5))


def inspect_enhanced_crop(crop,anchor):
    require_datetime=requires_datetime(crop)
    color=cv2.cvtColor(crop,cv2.COLOR_BGRA2BGR) if crop.shape[2]==4 else crop
    gray=cv2.cvtColor(color,cv2.COLOR_BGR2GRAY).astype(np.float32)
    rows=[]
    images=[]
    for sigma in (2,4):
        residual=gray-cv2.GaussianBlur(gray,(0,0),sigma)
        image=np.clip(128+residual*5,0,255).astype(np.uint8)
        images.append((f'local_contrast_{sigma}',image))
    images.append(('gamma_2.5',np.round(255*(gray/255)**2.5).astype(np.uint8)))
    for name,image in images:
        image=cv2.resize(image,None,fx=4,fy=4,interpolation=cv2.INTER_CUBIC)
        result,_=get_ocr()(image,use_det=False,use_cls=False)
        text=''.join(v[0] for v in result or [])
        confidence=min((float(v[1]) for v in result or []),default=0)
        point,_=parse_coordinate_text(text,allow_separator_dot=True,require_datetime=require_datetime)
        if confidence<.8:point=None
        rows.append(dict(name=name,text=text,confidence=confidence,coordinate=point))
    accepted=[r for r in rows if plausible(r['coordinate'],anchor) and
              sum(v['coordinate']==r['coordinate'] for v in rows)>=2]
    chosen=accepted[0] if accepted else None
    return dict(coordinate=chosen['coordinate'] if chosen else None,
                text=chosen['text'] if chosen else rows[0]['text'],
                confidence=min(r['confidence'] for r in accepted) if accepted else min(r['confidence'] for r in rows),
                reason='enhanced_parsed' if chosen else 'enhanced_unresolved',variants=rows)
