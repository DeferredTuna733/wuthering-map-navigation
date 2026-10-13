"""Local polygon labels for a scan segmentation dataset; no game input."""
import argparse
import json
import math
from pathlib import Path
import cv2
import numpy as np
from app import project_paths as paths

DATA=paths.ROOT/'data/navigation/scan_segmentation'


def validate_polygon(points,size):
    w,h=size
    if len(points)<4:raise ValueError('至少点击四个点，沿区域轮廓标注。')
    if any(not (0<=x<w and 0<=y<h) for x,y in points):raise ValueError('标注超出图片。')
    contour=np.asarray(points,dtype=np.float32)
    if cv2.contourArea(contour)<w*h*.005:raise ValueError('区域太小，请沿完整视角区域轮廓标注。')
    def cross(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    edges=list(zip(points,points[1:]+points[:1]))
    for i,(a,b) in enumerate(edges):
        for j,(c,d) in enumerate(edges):
            if j<=i+1 or (i==0 and j==len(edges)-1):continue
            if cross(a,b,c)*cross(a,b,d)<0 and cross(c,d,a)*cross(c,d,b)<0:
                raise ValueError('轮廓交叉了，请撤销或重画。')
    return '0 '+' '.join(f'{v:.6f}' for x,y in points for v in (x/w,y/h))+'\n'


def prepare():
    import shutil
    DATA.mkdir(parents=True,exist_ok=True)
    for sub in ('images','labels','annotations','previews'):(DATA/sub).mkdir(exist_ok=True)
    manifest_path=DATA/'manifest.json'
    records=json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else []
    known={r['id'] for r in records}
    root=paths.ROOT/'outputs/navigation/fixed_turn_sequences'
    for folder in sorted(root.iterdir()):
        # Sparse samples; adjacent frames must never enter different splits.
        for index in (0,16,39):
            source=folder/f'frame_{index:03d}.png'
            identity=f'{folder.name}_{index:03d}'
            if identity in known or not source.exists():continue
            shutil.copy2(source,DATA/'images'/f'{identity}.png')
            records.append({'id':identity,'source':str(source),'group':folder.name,'status':'pending'})
    for folder in sorted((paths.ROOT/'outputs/navigation/temporal_step_probes').iterdir()):
        report_path=folder/'report.json'
        if not report_path.exists():continue
        report=json.loads(report_path.read_text(encoding='utf-8'))
        if report.get('status')!='movement_observed':continue
        for index in (0,3,7):
            source=folder/f'after_{index:02d}.png';identity=f'move_{folder.name}_{index:03d}'
            if identity in known or not source.exists():continue
            shutil.copy2(source,DATA/'images'/f'{identity}.png')
            records.append({'id':identity,'source':str(source),'group':folder.name,
                            'sample_kind':'post_movement','status':'pending'})
    manifest_path.write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'待标注 {sum(r["status"]=="pending" for r in records)} 张；已人工确认 {sum(r["status"]=="labeled" for r in records)} 张。')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--prepare',action='store_true');parser.add_argument('--session');parser.add_argument('--ids',nargs='+')
    parser.add_argument('--suggestions',type=Path);parser.add_argument('--edit',action='store_true');args=parser.parse_args()
    prepare()
    if args.prepare:return
    import tkinter as tk
    from tkinter import messagebox
    from PIL import Image,ImageTk,ImageDraw
    records=json.loads((DATA/'manifest.json').read_text(encoding='utf-8'))
    pending=sorted((r for r in records if (r['status']=='pending' or args.edit) and (not args.session or r['group']==args.session)
                    and (not args.ids or r['id'] in args.ids)),
                   key=lambda r:(r.get('sample_kind')=='post_movement',r['group']),reverse=True)
    if not pending:
        print('没有待标注图片；现有标注已保存。',flush=True)
        return
    suggestions=json.loads(args.suggestions.read_text(encoding='utf-8'))['images'] if args.suggestions else {}
    root=tk.Tk();root.title('AI 检测轮廓微调' if suggestions else '视角区域训练标注');root.attributes('-topmost',True)
    tk.Label(root,text='拖动红点修改；左键点边附近增加点；右键点红点删除；Ctrl+Z 撤销。\n可切换 AI 候选，或清空重画。沿真实白色扇形调整；看不清就跳过，不要猜。' if suggestions else
             '沿白色半透明视角区域轮廓逐点点击：两条侧边 + 外侧弧线。不要画矩形。\n边界上的图标不用挖洞；看不清就点“看不清，跳过”，不要猜。',font=('Microsoft YaHei',11)).pack(padx=12,pady=10)
    status=tk.StringVar();tk.Label(root,textvariable=status).pack()
    candidate_buttons=tk.Frame(root);candidate_buttons.pack()
    canvas=tk.Canvas(root,width=600,height=600,highlightthickness=0);canvas.pack(padx=12)
    state={'index':0,'points':[],'history':[],'drag':None,'editing':False,'from_ai':False};photo=None;original=None;scale=3
    def remember():state['history'].append((list(state['points']),state['editing'],state['from_ai']))
    def use_candidate(candidate):
        remember();state['points']=[tuple(p) for p in candidate['polygon_xy']]
        state['editing']=True;state['from_ai']=True;redraw()
    def redraw():
        canvas.delete('all');canvas.create_image(0,0,anchor='nw',image=photo)
        pts=state['points']
        if len(pts)>=3:canvas.create_polygon(*[v*scale for p in pts for v in p],fill='#4fc3ff',stipple='gray25',outline='#ff3030',width=2)
        elif len(pts)==2:canvas.create_line(*[v*scale for p in pts for v in p],fill='#ff3030',width=2)
        for x,y in pts:canvas.create_oval(x*scale-3,y*scale-3,x*scale+3,y*scale+3,fill='red')
    def load():
        nonlocal original,photo,scale
        if state['index']>=len(pending):
            messagebox.showinfo('完成','当前队列已处理完成。',parent=root);root.destroy();return
        record=pending[state['index']]
        original=Image.open(DATA/'images'/f'{record["id"]}.png').convert('RGB')
        fit=min(3,(root.winfo_screenheight()-240)/original.height,(root.winfo_screenwidth()-80)/original.width)
        width,height=round(original.width*fit),round(original.height*fit)
        scale=width/original.width
        photo=ImageTk.PhotoImage(original.resize((width,height)))
        canvas.configure(width=width,height=height)
        state.update(points=[],history=[],drag=None,editing=False,from_ai=False)
        for button in candidate_buttons.winfo_children():button.destroy()
        candidates=suggestions.get(record['id'],{}).get('candidates',[])
        for candidate in candidates:
            tk.Button(candidate_buttons,text=f'AI 候选 {candidate["number"]} · 分数 {candidate["score"]:.2f}',
                      command=lambda c=candidate:use_candidate(c)).pack(side='left',padx=4)
        old_annotation=DATA/'annotations'/f'{record["id"]}.json'
        if args.edit and old_annotation.exists():
            old=json.loads(old_annotation.read_text(encoding='utf-8'))
            state.update(points=[tuple(p) for p in old['polygon_xy']],editing=True)
        elif candidates:
            state.update(points=[tuple(p) for p in candidates[0]['polygon_xy']],editing=True,from_ai=True)
        status.set(f'{state["index"]+1}/{len(pending)}  {record["id"]}\nAI 轮廓仅为草稿；点保存后才成为人工确认标注。' if candidates else
                   f'{state["index"]+1}/{len(pending)}  来源：{record["group"]}');redraw()
    def click(event):
        if 0<=event.x<original.width*scale and 0<=event.y<original.height*scale:
            point=(event.x/scale,min(original.height-1,event.y/scale));pts=state['points']
            nearest=min(range(len(pts)),key=lambda i:math.dist(pts[i],point)) if pts else None
            if nearest is not None and math.dist(pts[nearest],point)*scale<=12:
                remember();state['drag']=nearest;return
            remember()
            if state['editing'] and len(pts)>=3:
                p=np.asarray(point);distances=[]
                for a,b in zip(pts,pts[1:]+pts[:1]):
                    a,b=np.asarray(a),np.asarray(b);v=b-a
                    t=np.clip(np.dot(p-a,v)/max(float(np.dot(v,v)),1e-8),0,1)
                    distances.append(float(np.linalg.norm(p-(a+t*v))))
                pts.insert(int(np.argmin(distances))+1,point)
            else:pts.append(point)
            redraw()
    def drag(event):
        if state['drag'] is not None:
            state['points'][state['drag']]=(max(0,min(original.width-1,event.x/scale)),max(0,min(original.height-1,event.y/scale)))
            redraw()
    def delete_point(event):
        pts=state['points'];point=(event.x/scale,event.y/scale)
        if pts:
            nearest=min(range(len(pts)),key=lambda i:math.dist(pts[i],point))
            if math.dist(pts[nearest],point)*scale<=12:
                remember();pts.pop(nearest);redraw()
    def undo():
        if state['history']:
            state['points'],state['editing'],state['from_ai']=state['history'].pop();state['drag']=None;redraw()
    def clear():remember();state.update(points=[],editing=False,from_ai=False,drag=None);redraw()
    def finish(skip=False):
        record=pending[state['index']];identity=record['id']
        try:
            if not skip:
                text=validate_polygon(state['points'],original.size)
                annotation={'id':identity,'group':record['group'],'image_size':list(original.size),
                            'polygon_xy':state['points'],'label_source':'human_corrected_ai_polygon' if state['from_ai'] else 'human_polygon','class':'camera_scan'}
                if state['from_ai']:annotation['suggestion_file']=str(args.suggestions)
                for key in ('region','circle'):
                    if key in record:annotation[key]=record[key]
                (DATA/'annotations'/f'{identity}.json').write_text(json.dumps(annotation,ensure_ascii=False,indent=2),encoding='utf-8')
                (DATA/'labels'/f'{identity}.txt').write_text(text,encoding='utf-8')
                overlay=original.copy();ImageDraw.Draw(overlay).line(state['points']+[state['points'][0]],fill='red',width=2)
                overlay.save(DATA/'previews'/f'{identity}.png')
            record['status']='unclear' if skip else 'labeled'
            current=json.loads((DATA/'manifest.json').read_text(encoding='utf-8'))
            for item in current:
                if item['id']==identity:item['status']=record['status']
            (DATA/'manifest.json').write_text(json.dumps(current,ensure_ascii=False,indent=2),encoding='utf-8')
        except (OSError,ValueError) as error:
            messagebox.showerror('未保存',str(error),parent=root);return
        state['index']+=1;load()
    canvas.bind('<Button-1>',click)
    canvas.bind('<B1-Motion>',drag)
    canvas.bind('<ButtonRelease-1>',lambda e:state.update(drag=None))
    canvas.bind('<Button-3>',delete_point)
    buttons=tk.Frame(root);buttons.pack(pady=10)
    for label,command in [('撤销一点',undo),('清空',clear),('保存并下一张',finish),('看不清，跳过',lambda:finish(True))]:
        tk.Button(buttons,text=label,command=command).pack(side='left',padx=6)
    root.bind('<BackSpace>',lambda e:undo());root.bind('<Return>',lambda e:finish())
    root.bind('<Control-z>',lambda e:undo())
    load();root.lift();root.after(100,root.focus_force);root.mainloop()


if __name__=='__main__':main()
