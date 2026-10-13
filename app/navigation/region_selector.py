"""Static screenshot ROI picker; captures screen after countdown, no game input."""
import argparse
import time
import traceback
from app import project_paths as paths
import tkinter as tk
from tkinter import messagebox
import mss
from PIL import Image, ImageTk
from app.navigation.screen_region import save_region


def show_picker(image, desktop, auto_close_ms=None):
    root=tk.Tk();root.title('坐标区域设置：框选坐标及右侧完整日期时间；Enter保存，Esc取消')
    root.withdraw()
    root.attributes('-topmost',True)
    fit=min(1,root.winfo_screenwidth()*.9/image.width,root.winfo_screenheight()*.8/image.height)
    display=image.resize((round(image.width*fit),round(image.height*fit)))
    photo=ImageTk.PhotoImage(display)
    canvas=tk.Canvas(root,width=display.width,height=display.height,highlightthickness=0)
    canvas.pack();canvas.create_image(0,0,anchor='nw',image=photo)
    state={'start':None,'region':None,'item':None}
    def begin(event):
        state['start']=(event.x,event.y)
        state['region']=None
        if state['item'] is not None:canvas.delete(state['item'])
        state['item']=canvas.create_rectangle(event.x,event.y,event.x,event.y,outline='red',width=2)
    def drag(event):
        if state['start'] is None:return
        canvas.coords(state['item'],*state['start'],event.x,event.y)
    def end(event):
        if state['start'] is None:return
        ax,ay=state['start'];bx,by=event.x,event.y
        # Use actual resized dimensions, not nominal scale, to avoid rounding drift.
        x0=max(0,round(min(ax,bx)*image.width/display.width))
        y0=max(0,round(min(ay,by)*image.height/display.height))
        x1=min(image.width,round(max(ax,bx)*image.width/display.width))
        y1=min(image.height,round(max(ay,by)*image.height/display.height))
        state['region']={'left':desktop['left']+x0,'top':desktop['top']+y0,
                         'width':x1-x0,'height':y1-y0}
    def save(event=None):
        if state['region'] is None:return
        try:
            region=save_region(state['region'],desktop,content='coordinates_and_datetime')
        except ValueError as exc:
            messagebox.showerror('区域无效',str(exc),parent=root);return
        print(f'已保存识别区域：{region}',flush=True);root.destroy()
    canvas.bind('<ButtonPress-1>',begin);canvas.bind('<B1-Motion>',drag);canvas.bind('<ButtonRelease-1>',end)
    root.bind('<Return>',save);root.bind('<Escape>',lambda event:root.destroy())
    tk.Button(root,text='保存坐标识别区域（Enter）',command=save).pack(fill='x')
    root.update_idletasks()
    width,height=root.winfo_reqwidth(),root.winfo_reqheight()
    root.geometry(f'+{max(0,(root.winfo_screenwidth()-width)//2)}+{max(0,(root.winfo_screenheight()-height)//2)}')
    root.deiconify()
    root.lift()
    root.after(100,root.focus_force)
    if auto_close_ms is not None:
        root.after(auto_close_ms,root.destroy)
    print('区域选择窗口已显示；若游戏为独占全屏，请Alt+Tab切到此窗口。',flush=True)
    root.mainloop()

def main():
    parser=argparse.ArgumentParser(description='框选游戏坐标与右侧完整日期时间这一行')
    parser.add_argument('--delay',type=int,default=5)
    parser.add_argument('--smoke-test',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args()
    if not 0<=args.delay<=60:parser.error('delay must be 0..60')
    if args.smoke_test:
        show_picker(Image.new('RGB',(800,600)),{'left':0,'top':0,'width':800,'height':600},200)
        return
    try:
        print('【坐标区域设置】截图后会打开一个独立选择窗口，不是在游戏里画框。',flush=True)
        for remaining in range(args.delay,0,-1):
            print(f'{remaining}秒后截图，请切回游戏并显示坐标',flush=True)
            time.sleep(1)
        print('正在截取屏幕…',flush=True)
        with mss.MSS() as capture:
            desktop=dict(capture.monitors[0])
            shot=capture.grab(desktop)
            image=Image.frombytes('RGB',shot.size,shot.rgb)
        print(f'截图完成：{image.width}×{image.height}，正在打开选择窗口…',flush=True)
        show_picker(image,desktop)
    except Exception:
        paths.LOGS.mkdir(parents=True,exist_ok=True)
        error=traceback.format_exc()
        log=paths.LOGS/'ocr_region_setup_error.log'
        log.write_text(error,encoding='utf-8')
        print(error,flush=True)
        print(f'设置失败，错误记录：{log}',flush=True)
        try:
            root=tk.Tk();root.withdraw();root.attributes('-topmost',True)
            messagebox.showerror('坐标区域设置失败',f'截图或窗口启动失败。\n错误记录：{log}',parent=root)
            root.destroy()
        except Exception:pass
        return 1
    return 0

if __name__=='__main__':raise SystemExit(main())
