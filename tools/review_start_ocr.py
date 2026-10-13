"""Offline study of full-width coordinate enhancements, retaining minus pixels."""
import json
from pathlib import Path
import cv2
import numpy as np
from app.navigation.coordinate_reader import get_ocr,parse_coordinate_text
from tools.review_coordinate_preprocessing import variants


def full_width_variants(color):
    gray=cv2.cvtColor(color[:,:,:3],cv2.COLOR_BGR2GRAY)
    roi=gray[4:min(25,len(gray)),:]
    padded=cv2.copyMakeBorder(roi,8,8,16,16,cv2.BORDER_CONSTANT,value=int(np.median(roi)))
    resized=cv2.resize(padded,None,fx=4,fy=4,interpolation=cv2.INTER_CUBIC)
    output={'full_padded':resized,'full_inverted':255-resized}
    output.update({k:v for k,v in variants(color).items() if k in ('clahe','neutral','top_hat')})
    for channel in range(3):
        output[f'channel_{channel}']=cv2.resize(color[:,:,channel],None,fx=4,fy=4,interpolation=cv2.INTER_CUBIC)
    for gamma in (.4,.7,1.5,2.5):
        adjusted=np.round(255*(gray/255)**gamma).astype(np.uint8)
        output[f'gamma_{gamma}']=cv2.resize(adjusted,None,fx=4,fy=4,interpolation=cv2.INTER_CUBIC)
    for sigma in (2,4,8):
        residual=gray.astype(np.float32)-cv2.GaussianBlur(gray.astype(np.float32),(0,0),sigma)
        adjusted=np.clip(128+residual*5,0,255).astype(np.uint8)
        output[f'local_{sigma}']=cv2.resize(adjusted,None,fx=4,fy=4,interpolation=cv2.INTER_CUBIC)
    output['nearest']=cv2.resize(gray,None,fx=5,fy=5,interpolation=cv2.INTER_NEAREST)
    return output


def main():
    ocr=get_ocr();rows=[]
    for session in ('20261011_224554_526776','20261011_233533_752626'):
        folder=Path('outputs/navigation/ai_single_point_tests')/session
        for file in sorted(folder.glob('coordinate_*.png')):
            row={'file':str(file),'variants':[]}
            for name,im in full_width_variants(cv2.imread(str(file))).items():
                result,_=ocr(im,use_det=False,use_cls=False)
                text=''.join(v[0] for v in result or [])
                score=min((float(v[1]) for v in result or []),default=0)
                point,_=parse_coordinate_text(text,allow_separator_dot=True)
                row['variants'].append(dict(name=name,text=text,score=score,coordinate=point if score>=.8 else None))
            rows.append(row)
    out=Path('outputs/navigation/ocr_enhancement');out.mkdir(exist_ok=True)
    (out/'trial_review.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    for row in rows:
        print(Path(row['file']).parent.name[-6:],Path(row['file']).name,[(v['name'],v['coordinate']) for v in row['variants']])


if __name__=='__main__':main()
