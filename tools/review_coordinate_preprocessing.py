"""Replay saved OCR crops with candidate preprocessing; no live capture or input."""
import json
from pathlib import Path
import cv2
import numpy as np
from app import project_paths as paths
from app.navigation.coordinate_reader import get_ocr,parse_coordinate_text


def variants(crop):
    color=crop[:,:,:3]
    gray=cv2.cvtColor(color,cv2.COLOR_BGR2GRAY)
    hi=cv2.resize(gray,None,fx=4,fy=4,interpolation=cv2.INTER_CUBIC)
    clahe=cv2.createCLAHE(clipLimit=2,tileGridSize=(8,2)).apply(hi)
    neutral=np.min(color.astype(np.float32),axis=2)-.7*np.ptp(color.astype(np.float32),axis=2)
    neutral=cv2.normalize(neutral,None,0,255,cv2.NORM_MINMAX).astype(np.uint8)
    neutral=cv2.resize(neutral,None,fx=4,fy=4,interpolation=cv2.INTER_CUBIC)
    top=cv2.morphologyEx(hi,cv2.MORPH_TOPHAT,np.ones((17,33),np.uint8))
    top=cv2.normalize(top,None,0,255,cv2.NORM_MINMAX)
    roi=gray[4:25,26:170]
    padded=cv2.copyMakeBorder(roi,6,6,10,10,cv2.BORDER_CONSTANT,value=int(np.median(roi)))
    padded=cv2.resize(padded,None,fx=4,fy=4,interpolation=cv2.INTER_CUBIC)
    return dict(clahe=clahe,neutral=neutral,top_hat=top,trimmed=padded,inverted_trimmed=255-padded)


def main():
    folder=paths.ROOT/'outputs/navigation/ai_live_checks/20261011_213421_059879'
    rows=[];ocr=get_ocr()
    for f in sorted(folder.glob('coordinate_*_*.png')):
        row=dict(file=f.name,variants=[])
        for name,image in variants(cv2.imread(str(f),cv2.IMREAD_UNCHANGED)).items():
            result,_=ocr(image,use_det=False,use_cls=False)
            text=''.join(item[0] for item in result or [])
            score=min((float(item[1]) for item in result or []),default=0)
            coordinate,reason=parse_coordinate_text(text)
            row['variants'].append(dict(name=name,text=text,score=score,coordinate=coordinate if score>=.8 else None,reason=reason))
        rows.append(row)
    result=dict(scope='Preprocessing diagnostic, not independently labeled accuracy',samples=rows)
    (folder/'coordinate_preprocessing_review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    for name in ('clahe','neutral','top_hat','trimmed','inverted_trimmed'):
        items=[r for row in rows for r in row['variants'] if r['name']==name]
        print(name,'parsed',sum(r['coordinate'] is not None for r in items),'negative_x',sum(r['coordinate'] is not None and r['coordinate'][0]<0 for r in items))
    for n in (0,20,25):
        print('EXAMPLE',rows[n*2])


if __name__=='__main__':main()
