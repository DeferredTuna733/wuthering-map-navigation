"""Offline, bounded translation review; never sends input or approves navigation."""
import json
import math
from pathlib import Path
import cv2
import numpy as np
from app.navigation.temporal_step_probe import load_reference, match_heading


def compensate_translation(reference, frames, center, radius, limit=4):
    """Align small map translations for diagnostics, including the shifted overlay.

    The scan overlay is screen anchored, so warping it introduces an error. This
    approximation is deliberately excluded from live heading acceptance.
    """
    yy,xx=np.indices(reference.shape[:2])
    ring=(np.hypot(xx-center[0],yy-center[1])>.25*radius)&(np.hypot(xx-center[0],yy-center[1])<.85*radius)
    window=cv2.createHanningWindow((reference.shape[1],reference.shape[0]),cv2.CV_32F)
    edge=cv2.Laplacian(cv2.cvtColor(reference,cv2.COLOR_BGR2GRAY).astype(np.float32),cv2.CV_32F)*ring
    corrected=[]; measurements=[]
    for frame in frames:
        gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY).astype(np.float32)
        shift,response=cv2.phaseCorrelate(edge.copy(),cv2.Laplacian(gray,cv2.CV_32F)*ring,window.copy())
        measurements.append({'shift_xy':list(shift),'response':response})
        if response<.5 or math.hypot(*shift)>limit:
            return None,measurements
        transform=np.float32([[1,0,-shift[0]],[0,1,-shift[1]]])
        corrected.append(cv2.warpAffine(frame,transform,(frame.shape[1],frame.shape[0]),borderMode=cv2.BORDER_REFLECT))
    return corrected,measurements


def review(folder):
    folder=Path(folder)
    recorded=json.loads((folder/'report.json').read_text(encoding='utf-8'))
    reference_path=Path(recorded['reference_report'])
    reference=[cv2.imread(str(p)) for p in sorted(reference_path.parent.glob('frame_*.png'))]
    if len(reference)!=40 or any(f is None for f in reference):raise ValueError('Recorded reference missing')
    frames=[cv2.imread(str(p)) for p in sorted(folder.glob('after_[0-9][0-9].png'))]
    if len(frames)!=8 or any(f is None for f in frames):raise ValueError('Expected eight after frames')
    corrected,alignment=compensate_translation(reference[0],frames,(100,100),100)
    angle,analysis=match_heading(reference,corrected,(100,100),100) if corrected is not None else (None,{})
    result={'status':'offline_candidate' if angle is not None else 'unresolved',
            'candidate_heading_deg':angle,'alignment':alignment,'analysis':analysis,
            'navigation_approved':False,'live_matching_changed':False,
            'limitation':'Whole-frame translation also shifts the screen-anchored scan overlay; candidate only.'}
    (folder/'translation_review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('analysis','alignment')},ensure_ascii=False))


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('folder')
    review(parser.parse_args().folder)
