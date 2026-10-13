"""Audit human sector geometry against an independent yellow-glyph rotation fit."""
import json
import math
from pathlib import Path
import cv2
import numpy as np
from app import project_paths as paths
from tools.evaluate_scan_labels import polygon_heading


def glyph(frame):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (18,85,175), (42,255,255))
    yy,xx = np.indices(mask.shape)
    mask[np.hypot(xx-100,yy-100)>26] = 0
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    if n < 2: raise ValueError('No yellow glyph')
    idx = 1+np.argmax(stats[1:,4])
    ys,xs = np.where(labels==idx)
    if len(xs)<25: raise ValueError('Insufficient glyph')
    return np.column_stack((xs,ys)).astype(float)[::2]


def rotation_fit(a,b):
    c0=(a.mean(axis=0)+b.mean(axis=0))/2
    fits=[]
    for angle in np.linspace(-np.pi,np.pi,25):
        R=np.array([[np.cos(angle),-np.sin(angle)],[np.sin(angle),np.cos(angle)]])
        t=c0-R@c0
        for _ in range(60):
            pred=a@R.T+t
            d=np.sum((pred[:,None,:]-b[None,:,:])**2,axis=2)
            nearest=b[d.argmin(axis=1)]
            ca,cb=a.mean(axis=0),nearest.mean(axis=0)
            U,_,Vt=np.linalg.svd((a-ca).T@(nearest-cb))
            newR=Vt.T@U.T
            if np.linalg.det(newR)<0:
                Vt[-1]*=-1;newR=Vt.T@U.T
            newt=cb-newR@ca
            change=np.linalg.norm(newR-R)+np.linalg.norm(newt-t)
            R,t=newR,newt
            if change<1e-7: break
        d=np.sum(((a@R.T+t)[:,None,:]-b[None,:,:])**2,axis=2)
        fits.append((float(np.sqrt(np.mean(np.r_[d.min(axis=0),d.min(axis=1)]))),R,t))
    rms,R,t=min(fits,key=lambda f:f[0])
    rotation=float(np.degrees(np.arctan2(R[1,0],R[0,0])))
    if abs(np.linalg.det(np.eye(2)-R))<.1: return None
    center=np.linalg.solve(np.eye(2)-R,t)
    return dict(center_xy=center.tolist(),rotation_deg=rotation,rms_pixels=rms)


def stats(values):
    a=np.asarray(values)
    return dict(count=len(a),median=float(np.median(a)),mean=float(np.mean(a)),
                p05=float(np.percentile(a,5)),p95=float(np.percentile(a,95)),
                minimum=float(a.min()),maximum=float(a.max())) if len(a) else None


def main():
    data=paths.ROOT/'data/navigation/scan_segmentation'
    manifest=json.loads((data/'manifest.json').read_text(encoding='utf-8'))
    rows=[];invalid=[]
    for r in manifest:
        if r['status']!='labeled': continue
        annotation=json.loads((data/'annotations'/f'{r["id"]}.json').read_text(encoding='utf-8'))
        w,h=annotation['image_size']
        center=r.get('circle',dict(center_xy=[w/2,h/2]))['center_xy']
        points=annotation['polygon_xy']
        apex=min(points,key=lambda p:math.dist(p,center))
        try:
            heading,opening=polygon_heading(points,center)
        except ValueError as e:
            invalid.append(dict(id=r['id'],reason=str(e)));continue
        rows.append(dict(id=r['id'],group=r['group'],apex_xy=apex,
                         normalized_apex_200=(np.array(apex)*200/np.array([w,h])).tolist(),
                         center_error_pixels=math.dist(apex,center),heading_deg=heading,aperture_deg=opening))
    live=paths.ROOT/'outputs/navigation/ai_live_checks/20261011_210442_349840'
    original=json.loads((live/'report.json').read_text(encoding='utf-8'))
    reference=glyph(cv2.imread(str(live/'frame_000.png')))
    fits=[]
    for n in (89,95,115,135,157,196):
        fit=rotation_fit(reference,glyph(cv2.imread(str(live/f'frame_{n:03d}.png'))))
        if fit: fit.update(index=n);fits.append(fit)
    qualified=[f for f in fits if f['rms_pixels']<1.5 and math.dist(f['center_xy'],[100,100])<8]
    rotation_center=np.median([f['center_xy'] for f in qualified],axis=0).tolist() if qualified else None
    group='ai_live_20261011_210442_349840'
    new=[r for r in rows if r['group']==group]
    predictions={r['index']:r for r in original['observations']}
    for r in new:
        p=predictions[int(r['id'].rsplit('_',1)[1])]
        r['old_model_status']=p['status'];r['old_model_direction_deg']=p['direction_deg']
        r['old_model_error_deg']=None if p['direction_deg'] is None else abs((p['direction_deg']-r['heading_deg']+180)%360-180)
    result=dict(navigation_approved=False,scope='Manual labels, with annotation uncertainty; independent glyph fits use screenshots only.',
                historical_anchor_space='Old (800.339,480.463) anchor was full game map, not this minimap crop; cannot compare raw coordinates directly.',
                labeled=len(rows),invalid=invalid,
                aperture_all=stats([r['aperture_deg'] for r in rows]),
                aperture_live=stats([r['aperture_deg'] for r in new]),
                center_error_all=stats([r['center_error_pixels'] for r in rows]),
                rotation_fits=fits,rotation_center_median_xy=rotation_center,
                live_apex_to_rotation_center=stats([math.dist(r['apex_xy'],rotation_center) for r in new]) if rotation_center else None,
                live_status_counts={s:sum(r['status']==s for r in manifest if r['group']==group) for s in ('labeled','unclear','pending')},
                live_labels=new,samples=rows)
    out=paths.ROOT/'outputs/navigation/geometry_review/sector_geometry_audit.json'
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('samples','live_labels','rotation_fits')},ensure_ascii=False))
    print('LIVE ERRORS',[(r['id'].rsplit('_',1)[1],r['old_model_status'],r['old_model_error_deg']) for r in new])


if __name__=='__main__': main()
