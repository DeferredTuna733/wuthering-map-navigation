"""Live local training window; reads logs without touching the trainer."""
import argparse
import csv
import json
import tkinter as tk
import yaml
from tkinter import ttk
from pathlib import Path


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run',type=Path,required=True);args=parser.parse_args()
    root=tk.Tk();root.title('鸣潮 · 白色视角 AI 训练进度');root.geometry('960x690')
    root.configure(bg='#f4f5f7')
    status=tk.StringVar(value='正在读取训练记录')
    detail=tk.StringVar();metrics=tk.StringVar()
    tk.Label(root,text='白色视角区域 · 小型 AI 训练',font=('Microsoft YaHei UI',20,'bold'),bg='#f4f5f7',fg='#162033').pack(anchor='w',padx=28,pady=(24,8))
    tk.Label(root,textvariable=status,font=('Microsoft YaHei UI',14),bg='#f4f5f7').pack(anchor='w',padx=28)
    training_args=yaml.safe_load((args.run/'fit/args.yaml').read_text(encoding='utf-8'))
    planned=int(training_args.get('epochs',100))
    counts=json.loads((args.run/'dataset/split.json').read_text(encoding='utf-8'))['counts']
    device=str(training_args.get('device','unknown'))
    progress=ttk.Progressbar(root,maximum=planned);progress.pack(fill='x',padx=28,pady=14)
    tk.Label(root,textvariable=detail,font=('Microsoft YaHei UI',10),bg='#f4f5f7',justify='left').pack(anchor='w',padx=28)
    chart=tk.Canvas(root,bg='white',highlightthickness=0,height=280);chart.pack(fill='both',expand=True,padx=28,pady=18)
    tk.Label(root,textvariable=metrics,font=('Microsoft YaHei UI',11),bg='#f4f5f7',justify='left').pack(anchor='w',padx=28)
    tk.Label(root,text='训练指标不是最终方向准确率；完成后用未参加训练的图片测量角度误差。\n窗口每 2 秒刷新；关闭此窗口不会中断训练。',font=('Microsoft YaHei UI',10),bg='#f4f5f7',fg='#526070',justify='left').pack(anchor='w',padx=28,pady=(12,22))
    def update():
        try:
            with (args.run/'fit/results.csv').open(encoding='utf-8-sig') as stream:
                rows=[{k.strip():v for k,v in r.items()} for r in csv.DictReader(stream)]
            if rows:
                last=rows[-1];epoch=int(last['epoch']);seconds=float(last['time'])
                complete=(args.run/'training_complete.json').exists()
                status.set(f'{"训练完成" if complete else "正在训练"}：第 {epoch} / {planned} 轮（可能提前停止）')
                progress['value']=epoch
                detail.set(f'设备：{device}   ·   已用时：{int(seconds//60)} 分 {int(seconds%60)} 秒\n数据：{counts["train"]} 张训练 / {counts["val"]} 张验证 / {counts["test"]} 张留出测试')
                note='CPU 完整验证' if device=='cpu' else '最终以 CPU 完整评估为准'
                metrics.set(f'分割损失：{float(last["train/seg_loss"]):.3f}（下降通常表示在学习）\n验证 mask mAP50：{float(last["metrics/mAP50(M)"]):.3f}  ·  {note}')
                chart.delete('all');w=max(chart.winfo_width(),300);h=max(chart.winfo_height(),200)
                left,right,top,bottom=65,w-20,42,h-45
                chart.create_text(left,18,anchor='w',text='训练损失曲线 · 越低越好',font=('Microsoft YaHei UI',12,'bold'))
                series=[('train/seg_loss','分割损失','#176b58'),('train/box_loss','边框损失','#6b778c')]
                ymax=max(float(r[key]) for r in rows for key,_,_ in series)*1.1
                for i in range(5):
                    y=bottom-(bottom-top)*i/4
                    chart.create_line(left,y,right,y,fill='#e5e8ec')
                    chart.create_text(left-8,y,anchor='e',text=f'{ymax*i/4:.1f}',fill='#526070')
                for index,(key,label,color) in enumerate(series):
                    points=[]
                    for r in rows:
                        points.extend((left+(right-left)*(int(r['epoch'])-1)/max(planned-1,1),bottom-(bottom-top)*float(r[key])/max(ymax,.01)))
                    if len(points)>=4:chart.create_line(*points,fill=color,width=2)
                    chart.create_text(right-160+index*90,18,text=label,fill=color)
                chart.create_text((left+right)/2,h-15,text='训练轮数（轮）',fill='#526070')
                for n in sorted(set((1,planned//4,planned//2,planned*3//4,planned))):chart.create_text(left+(right-left)*(n-1)/max(planned-1,1),bottom+14,text=str(n),fill='#526070')
                chart.create_text(18,(top+bottom)/2,text='损失值',angle=90,fill='#526070')
        except (OSError,ValueError,KeyError):
            status.set('训练记录正在更新，稍后自动刷新')
        root.after(2000,update)
    root.after(100,update);root.mainloop()


if __name__=='__main__':main()
