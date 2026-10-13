"""Offline photometric experiment; registration alone is not a clean background."""
import json
import cv2
import numpy as np
from app import project_paths as paths
from app.navigation.robust_scan import fit_profile
from tools.review_minimap_relocalization import register


def photometric_review(frame,patch,registration,circle):
    affine=np.asarray(registration['affine'],np.float32)
    yy,xx=np.indices(frame.shape[:2]);center=circle['center_xy'];radius=circle['radius']
    map_x=affine[0,0]*xx+affine[0,1]*yy+affine[0,2]
    map_y=affine[1,0]*xx+affine[1,1]*yy+affine[1,2]
    aligned=cv2.remap(patch,map_x.astype(np.float32),map_y.astype(np.float32),cv2.INTER_LINEAR)
    source=cv2.cvtColor(aligned,cv2.COLOR_BGR2GRAY).astype(np.float32)
    gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY).astype(np.float32)
    distance=np.hypot(xx-center[0],yy-center[1]);ring=(distance>.30*radius)&(distance<.82*radius)
    y=gray[ring];design=np.column_stack((aligned[ring].astype(np.float32),np.ones(len(y))))
    keep=np.ones(len(y),bool)
    for _ in range(10):
        coefficients=np.linalg.lstsq(design[keep],y[keep],rcond=None)[0]
        residual=y-design@coefficients
        keep=np.abs(residual)<=np.percentile(np.abs(residual),70)
    predicted=aligned.astype(np.float32)@coefficients[:3]+coefficients[3]
    difference=gray-predicted
    angles=np.deg2rad(np.arange(360))[:,None];bands=[]
    for low,high in ((.30,.82),(.30,.56),(.56,.82)):
        radii=np.linspace(low*radius,high*radius,40)[None,:]
        polar=cv2.remap(difference,(center[0]+np.cos(angles)*radii).astype(np.float32),
                       (center[1]+np.sin(angles)*radii).astype(np.float32),cv2.INTER_LINEAR)
        bands.append(fit_profile(np.median(polar,axis=1)))
    full=bands[0];accepted=np.isfinite(coefficients).all() and full['amplitude']>=3 and full['explained_fraction']>=.70 and full['competitor_cost_ratio']>=1.4
    for band in bands[1:]:
        accepted &= band['amplitude']>=3 and band['explained_fraction']>=.55 and band['competitor_cost_ratio']>=1.2 and abs((band['direction_deg']-full['direction_deg']+180)%360-180)<=6
    return dict(status='atlas_heading_candidate' if accepted else 'atlas_background_unresolved',
        direction_deg=full['direction_deg'] if accepted else None,brightness_coefficients_bgr=coefficients.tolist(),
        radial_bands=bands,navigation_approved=False,confidence_calibrated=False),aligned,difference


def main():
    meta=json.loads((paths.ROOT/'data/maps/wuthering_gg/jinzhou_z6.meta.json').read_text(encoding='utf-8'))
    atlas=cv2.imread(str(paths.ROOT/'data/maps/wuthering_gg/jinzhou_z6.png'))
    step=paths.ROOT/'outputs/navigation/background_step_probes/20261011_191447_327563'
    report=json.loads((step/'report.json').read_text(encoding='utf-8'))
    captures=[(step/'before_00.png',report['before_coordinate'],report['circle']),
              (step/'after_00.png',report['after_coordinate'],report['circle'])]
    latest=paths.ROOT/'outputs/navigation/continuous_checks/20261011_201309_697343'
    current=json.loads((latest/'report.json').read_text(encoding='utf-8'))
    captures.append((latest/'frame_000.png',current['observations'][0]['coordinate'],current['circle']))
    folder=paths.ROOT/'outputs/navigation/geometry_review/atlas_background';folder.mkdir(exist_ok=True)
    rows=[]
    for index,(file,coordinate,circle) in enumerate(captures):
        frame=cv2.imread(str(file));registration,patch=register(frame,coordinate,circle,atlas,meta)
        if registration['status']=='terrain_registration_candidate':
            result,aligned,residual=photometric_review(frame,patch,registration,circle)
            cv2.imwrite(str(folder/f'aligned_{index}.png'),aligned)
            cv2.imwrite(str(folder/f'residual_{index}.png'),np.clip(residual+128,0,255).astype(np.uint8))
        else:result=dict(status='registration_unresolved',direction_deg=None)
        result.update(source=str(file),coordinate=coordinate,registration=registration)
        rows.append(result)
        print(index,result['status'],result['direction_deg'],[(b['direction_deg'],round(b['explained_fraction'],3)) for b in result.get('radial_bands',[])])
    summary=dict(scope='Three development images; brightness model experiment only',live_matching_changed=False,navigation_approved=False,observations=rows)
    (folder/'report.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')


if __name__=='__main__':main()
