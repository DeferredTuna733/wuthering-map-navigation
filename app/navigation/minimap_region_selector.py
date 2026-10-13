"""Interactive circular minimap selector: drag to create, drag inside to move, wheel to resize."""
import argparse,json,time,traceback
import tkinter as tk
import mss
from PIL import Image,ImageTk
from app import project_paths as paths
FILE=paths.ROOT/'config/navigation/minimap_region.json'

def valid(region,desktop):
 if not 120<=region['width']<=1000 or not 120<=region['height']<=1000:raise ValueError('圆形小地图直径需在120到1000之间')
 if region['left']<desktop['left'] or region['top']<desktop['top'] or region['left']+region['width']>desktop['left']+desktop['width'] or region['top']+region['height']>desktop['top']+desktop['height']:raise ValueError('圆形区域超出屏幕')
 return region

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--delay',type=int,default=5);args=ap.parse_args()
 if not 0<=args.delay<=60:ap.error('delay 0..60')
 for n in range(args.delay,0,-1):print(f'{n}秒后截图，请切回游戏并打开小地图',flush=True);time.sleep(1)
 try:
  with mss.MSS() as cap:
   desktop=dict(cap.monitors[0]);shot=cap.grab(desktop);image=Image.frombytes('RGB',shot.size,shot.rgb)
  root=tk.Tk();root.title('圆形小地图设置：拖动移动，滚轮调整大小，Enter保存，Esc取消');root.attributes('-topmost',True);root.withdraw()
  fit=min(1,root.winfo_screenwidth()*.9/image.width,root.winfo_screenheight()*.8/image.height);display=image.resize((round(image.width*fit),round(image.height*fit)));photo=ImageTk.PhotoImage(display);canvas=tk.Canvas(root,width=display.width,height=display.height,highlightthickness=0);canvas.pack();canvas.create_image(0,0,anchor='nw',image=photo)
  state={'center':None,'radius':None,'start':None,'dragging':False,'item':None,'last':None}
  def draw():
   if state['item'] is not None:canvas.delete(state['item'])
   if state['center'] is None:return
   cx,cy=state['center'];r=state['radius'];state['item']=canvas.create_oval(cx-r,cy-r,cx+r,cy+r,outline='#ff3b30',width=3);canvas.tag_raise(state['item'])
  def begin(e):
   if state['center'] is not None:
    cx,cy=state['center'];inside=(e.x-cx)**2+(e.y-cy)**2<=state['radius']**2
    if inside:state['dragging']=True;state['last']=(e.x,e.y);return
   state['center']=(e.x,e.y);state['radius']=1;state['dragging']=True;state['last']=(e.x,e.y);draw()
  def drag(e):
   if not state['dragging']:return
   if state['center'] is not None and state['last'] is not None and state['radius']>2:
    dx=e.x-state['last'][0];dy=e.y-state['last'][1]
    # If the current gesture started inside an existing circle, move it.
    if (state['center'][0]-state['last'][0])**2+(state['center'][1]-state['last'][1])**2<=state['radius']**2:
     state['center']=(state['center'][0]+dx,state['center'][1]+dy);state['last']=(e.x,e.y);draw();return
   cx,cy=state['center'];state['radius']=max(60,min(min(display.width,display.height)/2,((e.x-cx)**2+(e.y-cy)**2)**.5));draw()
  def end(e):state['dragging']=False;state['last']=None
  def wheel(e):
   if state['center'] is None:return
   state['radius']=max(60,min(min(display.width,display.height)/2,state['radius']+(10 if e.delta>0 else -10)));draw()
  def save(e=None):
   if state['center'] is None:return
   cx,cy=state['center'];r=state['radius'];x0=round((cx-r)*image.width/display.width);y0=round((cy-r)*image.height/display.height);diam=round(2*r*image.width/display.width)
   region={'left':desktop['left']+x0,'top':desktop['top']+y0,'width':diam,'height':diam};valid(region,desktop)
   config={'schema':1,'region':region,'circle':{'center_xy':[diam/2,diam/2],'radius':diam/2},'note':'交互式圆形区域；圆外像素不参与小地图扫描方向识别'}
   FILE.parent.mkdir(parents=True,exist_ok=True);tmp=FILE.with_suffix('.tmp');tmp.write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(FILE);print(f'已保存圆形小地图：{config}',flush=True);root.destroy()
  canvas.bind('<ButtonPress-1>',begin);canvas.bind('<B1-Motion>',drag);canvas.bind('<ButtonRelease-1>',end);canvas.bind('<MouseWheel>',wheel);canvas.bind('<Button-4>',lambda e:wheel(type('E',(),{'delta':120})()));canvas.bind('<Button-5>',lambda e:wheel(type('E',(),{'delta':-120})()));root.bind('<Return>',save);root.bind('<Escape>',lambda e:root.destroy());tk.Label(root,text='第一次拖动创建圆；圆内拖动移动；滚轮调整大小；Enter保存',anchor='w').pack(fill='x');tk.Button(root,text='保存圆形区域（Enter）',command=save).pack(fill='x');root.update_idletasks();root.geometry(f'+{max(0,(root.winfo_screenwidth()-root.winfo_width())//2)}+{max(0,(root.winfo_screenheight()-root.winfo_height())//2)}');root.deiconify();root.lift();root.focus_force();root.mainloop()
 except Exception:
  paths.LOGS.mkdir(parents=True,exist_ok=True);log=paths.LOGS/'minimap_region_setup_error.log';log.write_text(traceback.format_exc(),encoding='utf-8');print(f'设置失败：{log}',flush=True);return 1
 return 0
if __name__=='__main__':raise SystemExit(main())
