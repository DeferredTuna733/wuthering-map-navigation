"""Known-coordinate captures and deliberately wrong seeds; offline only."""
import json
import cv2
from app import project_paths as paths
from tools.review_minimap_relocalization import register


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
    rows=[]
    for file,coordinate,circle in captures:
        frame=cv2.imread(str(file))
        for dx,dy in ((0,0),(30,0),(100,0),(0,100),(500,500)):
            seed=[coordinate[0]+dx,coordinate[1]+dy,coordinate[2]]
            result,_=register(frame,seed,circle,atlas,meta)
            result.update(source=str(file),seed_offset=[dx,dy],expected='candidate' if dx==dy==0 else 'reject')
            rows.append(result)
            print(file.name,dx,dy,result['status'],result.get('matches'),result.get('heldout_supported'))
    summary=dict(scope='Three nearby recorded locations and deliberately wrong coordinate seeds; not global map validation',navigation_approved=False,
        correct_seed_accepted=sum(r['expected']=='candidate' and r['status']=='terrain_registration_candidate' for r in rows),
        wrong_seed_accepted=sum(r['expected']=='reject' and r['status']=='terrain_registration_candidate' for r in rows),samples=rows)
    (paths.ROOT/'outputs/navigation/geometry_review/relocalization_regression.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print('SUMMARY',summary['correct_seed_accepted'],summary['wrong_seed_accepted'])


if __name__=='__main__':main()
