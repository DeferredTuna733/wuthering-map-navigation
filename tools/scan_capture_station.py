"""User-triggered ROI capture and polygon labeling in one local application."""
import ctypes
from ctypes import wintypes
import json
import math
import queue
import threading
import time
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import messagebox,ttk
from PIL import Image,ImageTk
import mss
from app import project_paths as paths
from tools.scan_labeler import DATA,prepare,validate_polygon

CONFIG=paths.ROOT/'config/navigation/scan_capture_station.json'
RUNTIME_LOG=paths.ROOT/'outputs/navigation/scan_capture_station_runtime.jsonl'


class KeyEdges:
    """Passive polling fallback; holding a key must not produce extra captures."""
    def __init__(self):self.held={}
    def update(self,pressed):
        events=[name for name,down in pressed.items() if down and not self.held.get(name,False)]
        self.held=pressed.copy();return events


def runtime_event(event,**details):
    RUNTIME_LOG.parent.mkdir(parents=True,exist_ok=True)
    with RUNTIME_LOG.open('a',encoding='utf-8') as file:
        file.write(json.dumps({'time':datetime.now().isoformat(),'event':event,**details},ensure_ascii=False)+'\n')


class CircleSelection:
    """Keep create/move gestures distinct for their entire mouse drag."""
    def __init__(self,width,height):
        self.width=width;self.height=height;self.center=None;self.radius=0;self.mode=None;self.anchor=None
    def begin(self,x,y):
        inside=self.center is not None and math.dist((x,y),self.center)<=self.radius
        self.mode='move' if inside else 'create';self.anchor=(x,y)
        if not inside:self.center=(x,y);self.radius=0
    def drag(self,x,y):
        if self.mode=='create':self.resize(math.dist((x,y),self.anchor))
        elif self.mode=='move':
            dx=x-self.anchor[0];dy=y-self.anchor[1];cx,cy=self.center;r=self.radius
            self.center=(min(self.width-r,max(r,cx+dx)),min(self.height-r,max(r,cy+dy)))
            self.anchor=(x,y)
    def resize(self,radius):
        if self.center is None:return
        cx,cy=self.center;limit=max(0,min(cx,cy,self.width-cx,self.height-cy))
        self.radius=max(0,min(radius,limit))
    def end(self):self.mode=None;self.anchor=None


def mapped_circle(center,radius,original,display,desktop):
    sx=original[0]/display[0];sy=original[1]/display[1]
    cx,cy=center[0]*sx,center[1]*sy;r=radius*min(sx,sy);diameter=round(2*r)
    x0=round(cx-diameter/2);y0=round(cy-diameter/2)
    if diameter<40 or x0<0 or y0<0 or x0+diameter>original[0] or y0+diameter>original[1]:
        raise ValueError('请选择直径至少40像素且完整位于屏幕内的圆。')
    region={'left':desktop['left']+x0,'top':desktop['top']+y0,'width':diameter,'height':diameter}
    return region,{'center_xy':[cx-x0,cy-y0],'radius':min(r,diameter/2)}


def mapped_region(a,b,original,display,desktop):
    width,height=original;dw,dh=display
    x0=round(min(a[0],b[0])*width/dw);x1=round(max(a[0],b[0])*width/dw)
    y0=round(min(a[1],b[1])*height/dh);y1=round(max(a[1],b[1])*height/dh)
    if not (0<=x0<x1<=width and 0<=y0<y1<=height) or min(x1-x0,y1-y0)<40:
        raise ValueError('请框选至少40×40像素、包含完整小地图的区域。')
    return {'left':desktop['left']+x0,'top':desktop['top']+y0,'width':x1-x0,'height':y1-y0}


class Hotkeys:
    def __init__(self,events,capture,finish):
        self.events=events;self.keys=(capture,finish);self.ready=threading.Event();self.error=None;self.thread_id=None
        self.thread=threading.Thread(target=self.run,daemon=True)
    def start(self):
        self.thread.start()
        if not self.ready.wait(3):raise RuntimeError('快捷键注册超时')
        if self.error:raise RuntimeError(self.error)
    def run(self):
        user=ctypes.WinDLL('user32',use_last_error=True);kernel=ctypes.WinDLL('kernel32')
        user.GetMessageW.argtypes=[ctypes.POINTER(wintypes.MSG),wintypes.HWND,wintypes.UINT,wintypes.UINT]
        user.RegisterHotKey.argtypes=[wintypes.HWND,ctypes.c_int,wintypes.UINT,wintypes.UINT]
        user.PostThreadMessageW.argtypes=[wintypes.DWORD,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
        self.thread_id=kernel.GetCurrentThreadId();registered=[]
        try:
            for identity,key in enumerate(self.keys,1):
                if not user.RegisterHotKey(None,identity,0x4000,0x70+int(key[1:])-1):
                    raise RuntimeError(f'{key}被其他程序占用，请更换快捷键。')
                registered.append(identity)
            self.ready.set();msg=wintypes.MSG()
            while True:
                result=user.GetMessageW(ctypes.byref(msg),None,0,0)
                if result<=0:break
                if msg.message==0x312:self.events.put('capture' if msg.wParam==1 else 'finish')
        except Exception as error:self.error=str(error);self.ready.set()
        finally:
            for identity in registered:user.UnregisterHotKey(None,identity)
    def stop(self):
        if self.thread_id:ctypes.WinDLL('user32').PostThreadMessageW(self.thread_id,0x12,0,0)
        if self.thread.is_alive():self.thread.join(timeout=2)


def main():
    prepare();root=tk.Tk();root.title('小地图采集与轮廓标注');root.attributes('-topmost',True)
    config=json.loads(CONFIG.read_text(encoding='utf-8')) if CONFIG.exists() else {}
    region=config.get('region');circle=config.get('circle');events=queue.Queue();hook=None;active=False;label_window=None
    key_edges=KeyEdges();last_actions={};poll_keys=ctypes.WinDLL('user32')
    poll_keys.GetAsyncKeyState.argtypes=[ctypes.c_int];poll_keys.GetAsyncKeyState.restype=ctypes.c_short
    session='capture_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f');count=0
    status=tk.StringVar(value='先选择截图区域，再开始后台采集。')
    capture_key=tk.StringVar(value=config.get('capture_key','F8'));finish_key=tk.StringVar(value=config.get('finish_key','F9'))
    immediate=tk.BooleanVar(value=config.get('immediate',False))
    tk.Label(root,text='小地图采集与轮廓标注',font=('Microsoft YaHei',15)).pack(padx=24,pady=12)
    tk.Label(root,text='选圆形小地图后回到游戏。截图键保存裁剪图片；结束键打开批量标注。\n空白处左键拖动创建圆；滚轮调半径；圆内左键拖动移动。').pack(padx=20)
    row=tk.Frame(root);row.pack(pady=10)
    for text,var in [('截图键',capture_key),('结束采集键',finish_key)]:
        tk.Label(row,text=text).pack(side='left',padx=6)
        ttk.Combobox(row,textvariable=var,values=['F6','F7','F8','F9','F10','F11'],state='readonly',width=5).pack(side='left')
    tk.Checkbutton(root,text='截图后立即标注（浮窗；保存后继续采集）',variable=immediate).pack()
    tk.Label(root,textvariable=status,wraplength=500).pack(padx=20,pady=12)
    def choose():
        nonlocal active
        active=False
        if hook:hook.stop()
        root.withdraw()
        def safe_pick():
            try:pick()
            except Exception as error:
                root.deiconify();messagebox.showerror('截图失败',str(error),parent=root)
        root.after(5000,safe_pick)
    def pick():
        nonlocal region,circle
        with mss.MSS() as cap:
            desktop=dict(cap.monitors[0]);shot=cap.grab(desktop);original=Image.frombytes('RGB',shot.size,shot.rgb)
        win=tk.Toplevel(root);win.title('圆形小地图：空白拖动创建，滚轮调半径，圆内拖动移动');win.attributes('-topmost',True)
        fit=min(.9*win.winfo_screenwidth()/original.width,.8*win.winfo_screenheight()/original.height,1)
        display=original.resize((round(original.width*fit),round(original.height*fit)));photo=ImageTk.PhotoImage(display)
        canvas=tk.Canvas(win,width=display.width,height=display.height,highlightthickness=0);canvas.pack();canvas.create_image(0,0,anchor='nw',image=photo);canvas.image=photo
        selection=CircleSelection(display.width,display.height);item=None
        def redraw():
            nonlocal item
            if item is not None:canvas.delete(item)
            if selection.center is None:return
            cx,cy=selection.center;r=selection.radius
            item=canvas.create_oval(cx-r,cy-r,cx+r,cy+r,outline='red',width=3)
        def begin(e):
            selection.begin(e.x,e.y);redraw()
        def drag(e):
            selection.drag(e.x,e.y);redraw()
        def release(e):drag(e);selection.end()
        def wheel(e):
            steps=e.delta/120 if getattr(e,'delta',0) else (1 if e.num==4 else -1)
            selection.resize(selection.radius+steps*4);redraw()
        def save(e=None):
            nonlocal region,circle
            try:
                if selection.center is None:raise ValueError('请在空白处左键拖动创建圆。')
                region,circle=mapped_circle(selection.center,selection.radius,original.size,display.size,desktop)
            except ValueError as error:messagebox.showerror('区域无效',str(error),parent=win);return
            win.destroy();root.deiconify();status.set(f'已选圆形区域：直径{region["width"]}像素；点击“开始后台采集”。')
        canvas.bind('<ButtonPress-1>',begin);canvas.bind('<B1-Motion>',drag);canvas.bind('<ButtonRelease-1>',release)
        canvas.bind('<MouseWheel>',wheel);canvas.bind('<Button-4>',wheel);canvas.bind('<Button-5>',wheel)
        tk.Label(win,text='空白处左键拖动创建圆；滚轮调整半径；圆内左键拖动移动；Enter保存，Esc取消').pack(fill='x')
        tk.Button(win,text='保存圆形区域（Enter）',command=save).pack(fill='x')
        win.bind('<Return>',save);win.bind('<Escape>',lambda e:(win.destroy(),root.deiconify()));win.lift();win.focus_force()
    def start():
        nonlocal hook,active
        if active:root.iconify();return
        if not region or not circle:messagebox.showinfo('先选择圆形区域','点击选择圆形区域，5秒内切回游戏。',parent=root);return
        if capture_key.get()==finish_key.get():messagebox.showerror('快捷键重复','截图键和结束键必须不同。',parent=root);return
        try:
            hook=Hotkeys(events,capture_key.get(),finish_key.get());hook.start()
            CONFIG.parent.mkdir(parents=True,exist_ok=True)
            CONFIG.write_text(json.dumps({'region':region,'circle':circle,'capture_key':capture_key.get(),'finish_key':finish_key.get(),'immediate':immediate.get()},ensure_ascii=False,indent=2),encoding='utf-8')
        except Exception as error:
            if hook:hook.stop()
            messagebox.showerror('启动失败',str(error),parent=root);return
        active=True;key_edges.held={};last_actions.clear()
        root.title(f'采集中：{capture_key.get()}截图 / {finish_key.get()}结束 — {count}张')
        status.set(f'正在采集：{capture_key.get()}截图，{finish_key.get()}结束；已采集{count}张。\n窗口最小化到任务栏，可随时点击恢复。')
        runtime_event('capture_started',session=session,region=region,capture_key=capture_key.get(),finish_key=finish_key.get())
        root.iconify()
    def capture():
        nonlocal count
        if not active or label_window is not None:
            runtime_event('capture_ignored',reason='inactive_or_labeling');return
        with mss.MSS() as cap:
            desktop=cap.monitors[0]
            if region['left']<desktop['left'] or region['top']<desktop['top'] or region['left']+region['width']>desktop['left']+desktop['width'] or region['top']+region['height']>desktop['top']+desktop['height']:
                raise ValueError('区域超出当前屏幕，请重新选择。')
            shot=cap.grab(region);image=Image.frombytes('RGB',shot.size,shot.rgb)
        identity=f'{session}_{count:04d}';target=DATA/'images'/f'{identity}.png';image.save(target)
        manifest=DATA/'manifest.json';records=json.loads(manifest.read_text(encoding='utf-8'))
        record={'id':identity,'source':str(target),'group':session,'sample_kind':'hotkey_capture','region':region.copy(),'circle':circle.copy(),'status':'pending'}
        records.append(record);temp=manifest.with_suffix('.tmp');temp.write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(manifest)
        count+=1;status.set(f'已采集 {count} 张；{finish_key.get()}结束并标注。')
        root.title(f'采集中：{capture_key.get()}截图 / {finish_key.get()}结束 — {count}张')
        runtime_event('image_saved',session=session,path=str(target),count=count)
        import winsound
        winsound.MessageBeep(winsound.MB_OK)
        if immediate.get():annotate(image,record)
    def annotate(image,record):
        nonlocal label_window
        from PIL import ImageDraw
        win=tk.Toplevel(root);label_window=win;win.title('标注白色透明视角区域');win.attributes('-topmost',True)
        scale=min(3,(win.winfo_screenheight()-180)/image.height,(win.winfo_screenwidth()-80)/image.width)
        photo=ImageTk.PhotoImage(image.resize((round(image.width*scale),round(image.height*scale))))
        tk.Label(win,text='沿两条侧边和外弧逐点点击。Enter保存，Backspace撤销；Esc留待批量标注。').pack(padx=8,pady=8)
        canvas=tk.Canvas(win,width=round(image.width*scale),height=round(image.height*scale),highlightthickness=0);canvas.pack();canvas.image=photo;points=[]
        def redraw():
            canvas.delete('all');canvas.create_image(0,0,anchor='nw',image=photo)
            if len(points)>=3:canvas.create_polygon(*[v*scale for p in points for v in p],fill='#4fc3ff',stipple='gray25',outline='red')
        def click(e):
            if 0<=e.x<image.width*scale and 0<=e.y<image.height*scale:points.append((e.x/scale,min(image.height-1,e.y/scale)));redraw()
        def close():
            nonlocal label_window
            win.destroy();label_window=None
        def save(e=None):
            try:
                text=validate_polygon(points,image.size);identity=record['id']
                annotation={'id':identity,'group':session,'image_size':list(image.size),'polygon_xy':points,'region':region.copy(),'circle':circle.copy(),'label_source':'human_polygon','class':'camera_scan'}
                (DATA/'annotations'/f'{identity}.json').write_text(json.dumps(annotation,ensure_ascii=False,indent=2),encoding='utf-8')
                (DATA/'labels'/f'{identity}.txt').write_text(text,encoding='utf-8')
                preview=image.copy();ImageDraw.Draw(preview).line(points+[points[0]],fill='red',width=2);preview.save(DATA/'previews'/f'{identity}.png')
                manifest=DATA/'manifest.json';records=json.loads(manifest.read_text(encoding='utf-8'))
                next(r for r in records if r['id']==identity)['status']='labeled'
                manifest.write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
            except (OSError,ValueError) as error:messagebox.showerror('未保存',str(error),parent=win);return
            close()
        def undo(e=None):
            if points:points.pop();redraw()
        canvas.bind('<Button-1>',click);win.bind('<Return>',save);win.bind('<BackSpace>',undo);win.bind('<Escape>',lambda e:close());win.protocol('WM_DELETE_WINDOW',close)
        tk.Button(win,text='保存并回到后台（Enter）',command=save).pack(fill='x');redraw();win.lift();win.focus_force()
    def finish():
        nonlocal active
        if label_window is not None:return False
        active=False
        if hook:hook.stop()
        runtime_event('capture_finished',session=session,count=count)
        if count==0:
            root.deiconify();root.title('小地图采集与轮廓标注')
            status.set('本次未保存图片。请重新开始采集后按截图键；任务栏可以恢复窗口。')
            return False
        root.destroy()
        import sys
        from tools.scan_labeler import main as label_main
        sys.argv=['scan_labeler','--session',session] if count else ['scan_labeler']
        label_main()
        return True
    def poll():
        try:
            if active:
                pressed={'capture':bool(poll_keys.GetAsyncKeyState(0x70+int(capture_key.get()[1:])-1)&0x8000),
                         'finish':bool(poll_keys.GetAsyncKeyState(0x70+int(finish_key.get()[1:])-1)&0x8000)}
                for event in key_edges.update(pressed):events.put(event)
            while not events.empty():
                event=events.get_nowait()
                now=time.monotonic()
                if now-last_actions.get(event,-100)<.35:continue
                last_actions[event]=now;runtime_event('hotkey_received',action=event)
                if event=='finish':
                    if finish():return
                    continue
                if event=='capture':capture()
        except Exception as error:
            runtime_event('capture_error',error=str(error))
            root.deiconify();messagebox.showerror('采集失败',str(error),parent=root)
        if root.winfo_exists():root.after(80,poll)
    def pause():
        nonlocal active
        active=False
        if hook:hook.stop()
        root.deiconify();root.title('小地图采集与轮廓标注');status.set(f'采集已暂停；已保存{count}张。可继续采集或结束标注。')
        runtime_event('capture_paused',count=count)
    def close():
        if hook:hook.stop()
        root.destroy()
    tk.Button(root,text='选择圆形小地图（5秒后截屏，请切回游戏）',command=choose).pack(fill='x',padx=20,pady=5)
    tk.Button(root,text='开始后台采集',command=start).pack(fill='x',padx=20,pady=5)
    tk.Button(root,text='暂停采集 / 恢复窗口',command=pause).pack(fill='x',padx=20,pady=5)
    tk.Button(root,text='结束采集并标注本批截图',command=finish).pack(fill='x',padx=20,pady=5)
    root.protocol('WM_DELETE_WINDOW',close);root.after(80,poll);root.mainloop()


if __name__=='__main__':
    try:main()
    except Exception:
        import traceback
        log=paths.ROOT/'outputs/navigation/scan_capture_station_error.log';log.parent.mkdir(parents=True,exist_ok=True);log.write_text(traceback.format_exc(),encoding='utf-8');raise
