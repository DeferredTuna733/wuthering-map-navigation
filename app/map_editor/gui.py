"""鸣潮地图画线工具：wuthering.gg 主地图/局部图、手动校准、路线草稿。
地图界面不操作游戏。wuthering.gg 路线保留为待核验草稿。
"""

import os
import re
import json
import math
import queue
import threading

import tkinter as tk
from tkinter import messagebox, simpledialog, filedialog, ttk

from PIL import Image, ImageTk
from app.map_editor.viewport_renderer import MapViewportRenderer
from app.map_editor.rounded_button import RoundedButton
from app.map_editor.route_coordinates import parse_xy, game_to_pixel, import_points

Image.MAX_IMAGE_PIXELS = None   # 地图拼图可达上亿像素，禁用 Pillow 解压炸弹保护

# ============ 配置 ============
from app import project_paths as paths
BASE_DIR = str(paths.ROOT)
MAPS_DIR = str(paths.MAPS)
ROUTES_DIR = str(paths.ROUTES)
# 游戏坐标合理范围（与 read_coord.py 一致）
COORD_RANGE = (-1500, 1500)

# 颜色（沿用 labelling.py 暗色风格）
BG        = "#f5f6f8"
PANEL     = "#ffffff"
PANEL_HL  = "#edf0f4"
FG        = "#20242b"
FG_DIM    = "#737b88"
ACCENT    = "#3478f6"
GREEN     = "#00e676"
RED       = "#ff5252"
YELLOW    = "#3478f6"
CALIB_COL = GREEN      # 校准点颜色
ROUTE_COL = "#ff6b75"        # 路线颜色


# ============ 几何：仿射变换 ============
def fit_affine(pts):
    """最小二乘仿射：gx = a*px + b*py + c, gy = d*px + e*py + f
    pts: [(px, py, gx, gy), ...]  至少 3 点
    返回 (params, residuals): params=(a,b,c,d,e,f), residuals=[rx, ry] 列表
    """
    import numpy as np
    A = np.array([[p[0], p[1], 1.0] for p in pts], dtype=float)
    gx = np.array([p[2] for p in pts], dtype=float)
    gy = np.array([p[3] for p in pts], dtype=float)
    ax, *_ = np.linalg.lstsq(A, gx, rcond=None)
    ay, *_ = np.linalg.lstsq(A, gy, rcond=None)
    a, b, c = float(ax[0]), float(ax[1]), float(ax[2])
    d, e, f = float(ay[0]), float(ay[1]), float(ay[2])

    rx = []
    ry = []
    for (px, py, gx_, gy_) in pts:
        rx.append(gx_ - (a * px + b * py + c))
        ry.append(gy_ - (d * px + e * py + f))
    return (a, b, c, d, e, f), (rx, ry)


def affine_apply(params, px, py):
    a, b, c, d, e, f = params
    return (a * px + b * py + c, d * px + e * py + f)


# ============ GUI ============
class MapDrawApp:
    def __init__(self, root):
        paths.ensure_runtime_dirs()
        self.root = root
        self.root.title("鸣潮路线工作台")
        self.root.configure(bg=BG)
        self.root.geometry("1240x820")
        self.root.minsize(1060, 780)

        # 状态
        self.map_img = None        # PIL Image（原图）
        self.tk_img = None
        self._viewport_renderer = None
        self._background_item = None
        self._render_job = None
        self._quality_job = None
        self._preview_pending = False
        self._background_view = None
        self._route_items = []
        self.selected_route_index = None
        self._detail_tiles = None
        self._detail_job = None
        self.img_w = 0
        self.img_h = 0
        self.scale = 1.0
        self.fit_scale = 1.0
        self.zoom = 1.0
        self.offset = (0.0, 0.0)
        self.map_meta = None

        self.mode = "draw"        # calib / draw
        self.calib_points = []     # [(px, py, gx, gy)]
        self.route_px = []         # [(px, py)] 图片像素
        self.transform = None      # (a,b,c,d,e,f) 或 None
        self.residuals = None

        # 拖动状态
        self._drag = None          # (start_x, start_y, start_ox, start_oy)
        self._moved = False
        self._point_drag = None
        self._history = []
        self._ocr_cancel = threading.Event()
        self._ocr_results = queue.Queue()
        self._ocr_busy = False
        self._ocr_job = None
        self._closed = False

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._close)

    # ---------- UI ----------
    def _build_ui(self):
        left = tk.Frame(self.root, bg=PANEL, width=340)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(12, 0), pady=12)
        left.pack_propagate(False)
        pad = {"padx": 18, "pady": 4}
        def label(text, size=10, color=FG_DIM):
            item = tk.Label(left, text=text, bg=PANEL, fg=color, anchor="w",
                            font=("Microsoft YaHei UI", size), justify="left")
            item.pack(fill=tk.X, **pad)
            return item
        def button(text, command, primary=False):
            item = RoundedButton(left, text, command, color=ACCENT if primary else PANEL_HL,
                                 foreground="white" if primary else FG)
            item.pack(fill=tk.X, **pad)
            return item
        label("路线工作台", 20, FG)
        label("本地地图 · 瑝珑", 10)
        label("起点坐标", 12, FG)
        label("手动输入第一个点坐标", 10)
        row = tk.Frame(left, bg=PANEL)
        row.pack(fill=tk.X, **pad)
        self.start_xy = tk.StringVar()
        self.start_entry = ttk.Entry(row, textvariable=self.start_xy, font=("Segoe UI", 12))
        self.start_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=6)
        self.start_entry.bind('<Return>', lambda e: self.on_set_start())
        self.btn_detect = RoundedButton(row, "自动检测", self.on_detect_start, width=96,
                                        color=ACCENT, foreground="white")
        self.btn_detect.pack(side=tk.RIGHT, padx=(8, 0))
        label("格式：-740, 1136", 9)
        button("设置起点并定位", self.on_set_start)
        self.ocr_status = label("自动检测会切回游戏读取屏幕坐标", 9)
        self.ocr_status.config(wraplength=300)
        self.var_mode = tk.StringVar(value="draw")
        self.lbl_calib = tk.Label(left, text="", bg=PANEL, fg=FG_DIM)
        self.btn_undo_calib = None
        self.lbl_route = label("路线点 · 0", 12, FG)
        style = ttk.Style(self.root)
        style.theme_use('clam')
        style.configure('Route.Treeview', background=PANEL, fieldbackground=PANEL,
                        foreground=FG, rowheight=32, borderwidth=0,
                        font=('Segoe UI', 10))
        style.configure('Route.Treeview.Heading', background=BG, foreground=FG_DIM,
                        relief='flat', font=('Microsoft YaHei UI', 9))
        style.map('Route.Treeview', background=[('selected', '#e7efff')],
                  foreground=[('selected', ACCENT)])
        style.configure('Route.Vertical.TScrollbar', background='#d5dbe4',
                        troughcolor=BG, borderwidth=0, arrowsize=11)
        points_panel = tk.Frame(left, bg=PANEL)
        points_panel.pack(fill=tk.BOTH, expand=True, **pad)
        self.route_list = ttk.Treeview(points_panel, columns=('number', 'x', 'y'),
                                      show='headings', height=6, selectmode='browse',
                                      style='Route.Treeview')
        for key, text, width in (('number', '点', 40), ('x', 'X', 110), ('y', 'Y', 110)):
            self.route_list.heading(key, text=text)
            self.route_list.column(key, width=width, minwidth=35, anchor='center')
        scroll = ttk.Scrollbar(points_panel, orient='vertical', command=self.route_list.yview,
                               style='Route.Vertical.TScrollbar')
        self.route_list.configure(yscrollcommand=scroll.set)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.route_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.route_list.bind('<<TreeviewSelect>>', self._on_route_list_select)
        self.route_list.bind('<Double-1>', self._center_selected_route_point)
        self.lbl_selected_route = label("拖动点调整位置 · 双击列表定位", 9)
        self.btn_undo_route = button("撤销上一步", self.undo_edit)
        self.btn_clear_route = button("清空路线", self.clear_route)
        row = tk.Frame(left, bg=PANEL)
        row.pack(fill=tk.X, **pad)
        RoundedButton(row, "导入路线", self.on_import, width=142).pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.btn_export = RoundedButton(row, "导出路线", self.on_export, width=142,
                                        color=ACCENT, foreground='white')
        self.btn_export.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(8, 0))
        self.status = label("就绪", 9)
        self.status.config(wraplength=300)
        canvas_frame = tk.Frame(self.root, bg=BG)
        canvas_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=12, pady=12)
        tk.Label(canvas_frame, text="点击添加点    ·    拖动点编辑    ·    拖动空白平移    ·    滚轮缩放",
                 bg=BG, fg=FG_DIM, font=('Microsoft YaHei UI', 10)).pack(anchor='w', pady=(0, 10))
        self.canvas = tk.Canvas(canvas_frame, bg='#102f3b', highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind('<ButtonPress-1>', self.on_press)
        self.canvas.bind('<B1-Motion>', self.on_drag)
        self.canvas.bind('<ButtonRelease-1>', self.on_release)
        self.canvas.bind('<Button-3>', self.on_right_click)
        self.canvas.bind('<MouseWheel>', self.on_wheel)
        self.canvas.bind('<Configure>', lambda e: self._on_canvas_resize())
        self.root.bind('<Control-z>', self._keyboard_undo)

    def _close(self):
        print('路线工作台：窗口关闭',flush=True)
        self._closed = True
        self._ocr_cancel.set()
        if self._ocr_job is not None:
            self.root.after_cancel(self._ocr_job)
        self._cancel_render_jobs()
        if self._detail_job is not None:
            self.root.after_cancel(self._detail_job)
        if self._detail_tiles is not None:
            self._detail_tiles.close()
        self.root.destroy()

    def _remember_route(self):
        self._history.append(list(self.route_px))
        self._history = self._history[-100:]

    def _sync_start(self):
        if self.route_px and self.transform is not None:
            x, y = affine_apply(self.transform, *self.route_px[0])
            self.start_xy.set(f'{x:.3f}, {y:.3f}')
        else:
            self.start_xy.set('')

    def _replace_route(self, points):
        self.route_px = list(points)
        self.selected_route_index = None
        self._redraw_overlay()
        self._refresh_route_list()
        self.lbl_route.config(text=f'路线点 · {len(self.route_px)}')
        self._sync_start()

    def undo_edit(self):
        if self._history:
            self._replace_route(self._history.pop())

    def _keyboard_undo(self, event):
        # Let text inputs keep their own editing shortcuts.
        if not isinstance(event.widget, (tk.Entry, ttk.Entry)):
            self.undo_edit()
            return 'break'

    def on_set_start(self):
        try:
            self._set_start_point(parse_xy(self.start_xy.get()))
        except ValueError as exc:
            self._set_status(str(exc))

    def _set_start_point(self, coordinate):
        point = game_to_pixel(self.transform, coordinate, (self.img_w, self.img_h))
        self._remember_route()
        points = list(self.route_px)
        if points:
            points[0] = point
        else:
            points.append(point)
        self._replace_route(points)
        self._select_route_point(0)
        # Show the surrounding roads rather than the whole region.
        self.zoom = min(40, max(self.zoom, 10))
        self.scale = self.fit_scale*self.zoom
        self._center_selected_route_point()
        self._set_status('起点已设置，可在地图上点击添加后续路线点')

    def on_import(self):
        if self._ocr_busy:
            self._set_status('请等待坐标检测结束再导入路线')
            return
        path = filedialog.askopenfilename(parent=self.root, title='导入路线',
                                          initialdir=ROUTES_DIR, filetypes=[('路线 JSON', '*.json')])
        if not path:
            return
        try:
            with open(path, encoding='utf-8-sig') as stream:
                points = import_points(json.load(stream), self.transform, (self.img_w, self.img_h))
            self._remember_route()
            self._replace_route(points)
            self._select_route_point(0)
            self._center_selected_route_point()
            self._set_status(f'已导入 {len(points)} 个点')
        except (ValueError, TypeError, OSError) as exc:
            self._set_status('导入失败：'+str(exc))

    def on_detect_start(self):
        if self._ocr_busy:
            return
        self._ocr_busy = True
        self._ocr_cancel.clear()
        self.btn_detect.config(state='disabled', text='检测中')
        self.ocr_status.config(text='正在切换到游戏，请站定并显示坐标；F12 取消')
        self._ocr_route_snapshot = list(self.route_px)
        self._ocr_text_snapshot = self.start_xy.get()
        def worker():
            try:
                from app.map_editor.start_detection import detect_start
                self._ocr_results.put(('ok', detect_start(self._ocr_cancel)))
            except Exception as exc:
                self._ocr_results.put(('error', str(exc)))
        threading.Thread(target=worker, daemon=True).start()
        self._ocr_job = self.root.after(100, self._poll_start_detection)

    def _poll_start_detection(self):
        self._ocr_job = None
        if self._closed:
            return
        try:
            status, value = self._ocr_results.get_nowait()
        except queue.Empty:
            self._ocr_job = self.root.after(100, self._poll_start_detection)
            return
        self._ocr_busy = False
        self.btn_detect.config(state='normal', text='自动检测')
        if status == 'ok' and (self.route_px != self._ocr_route_snapshot or self.start_xy.get() != self._ocr_text_snapshot):
            status, value = 'error', '检测期间路线已修改，请重新检测或手动设置起点'
        if status == 'ok':
            try:
                self._set_start_point(value[:2])
                self.ocr_status.config(text=f'检测坐标：{value[0]}, {value[1]}（高度 {value[2]}）\n请对照游戏读数，负号仍可能被 OCR 漏读')
            except ValueError as exc:
                self.ocr_status.config(text=str(exc))
        else:
            self.ocr_status.config(text=value)
        self.root.deiconify()
        self.root.lift()

    def _poll_detail(self):
        self._detail_job = None
        if self._detail_tiles is None:
            return
        changed = self._detail_tiles.poll()
        # Avoid disturbing an active zoom/drag preview; final render will pick it up.
        if changed and self._quality_job is None and not self._moved:
            self._background_view = None
            self._schedule_render()
        self._detail_job = self.root.after(150, self._poll_detail)

    def _set_status(self, text):
        self.status.config(text=text)

    # ---------- 画布 ----------
    def _fit_and_center(self):
        cw = max(20, self.canvas.winfo_width())
        ch = max(20, self.canvas.winfo_height())
        pad = 10
        self.fit_scale = min((cw - pad) / self.img_w,
                             (ch - pad) / self.img_h, 1.0)
        self.scale = self.fit_scale * self.zoom
        nw = self.img_w * self.scale
        nh = self.img_h * self.scale
        self.offset = ((cw - nw) / 2, (ch - nh) / 2)

    def _schedule_render(self, preview=False):
        self._preview_pending = self._preview_pending or preview
        if self._render_job is None:
            self._render_job = self.root.after(16, self._flush_render)
        if preview:
            if self._quality_job is not None:
                self.root.after_cancel(self._quality_job)
            self._quality_job = self.root.after(140, self._finish_quality)

    def _flush_render(self):
        self._render_job = None
        preview = self._preview_pending
        self._preview_pending = False
        self._render(preview=preview)

    def _finish_quality(self):
        if self._quality_job is not None:
            self.root.after_cancel(self._quality_job)
        self._quality_job = None
        self._preview_pending = False
        if self._render_job is not None:
            self.root.after_cancel(self._render_job)
            self._render_job = None
        self._render(preview=False)

    def _cancel_render_jobs(self):
        for name in ("_render_job", "_quality_job"):
            job = getattr(self, name)
            if job is not None:
                self.root.after_cancel(job)
                setattr(self, name, None)
        self._preview_pending = False

    def _move_cached_background(self):
        if self._background_view is None or self._background_item is None:
            return False
        cw, ch, scale, offset, margin = self._background_view
        if (cw, ch) != (self.canvas.winfo_width(), self.canvas.winfo_height()) or scale != self.scale:
            return False
        dx, dy = self.offset[0] - offset[0], self.offset[1] - offset[1]
        if abs(dx) > margin or abs(dy) > margin:
            return False
        self.canvas.coords(self._background_item, -margin + dx, -margin + dy)
        return True

    def _render(self, preview=False):
        if self.map_img is None or self._viewport_renderer is None:
            return
        if self._move_cached_background() and (preview or self._background_quality == "final"):
            self._update_overlay_positions()
            return
        cw, ch = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
        margin = 128  # Extra visible border allows panning without resampling.
        quality = "preview" if preview else "final"
        frame = self._viewport_renderer.render((cw + 2*margin, ch + 2*margin), self.scale,
                                               (self.offset[0]+margin, self.offset[1]+margin), quality)
        if self._detail_tiles is not None and not preview:
            frame = self._detail_tiles.refine(frame, self.scale,
                      (self.offset[0]+margin, self.offset[1]+margin))
        self.tk_img = ImageTk.PhotoImage(frame, master=self.canvas)
        if self._background_item is None:
            self._background_item = self.canvas.create_image(-margin, -margin, anchor=tk.NW,
                                                             image=self.tk_img, tags="map_background")
        else:
            self.canvas.itemconfigure(self._background_item, image=self.tk_img)
            self.canvas.coords(self._background_item, -margin, -margin)
        self._background_view = (cw, ch, self.scale, self.offset, margin)
        self._background_quality = quality
        self.canvas.tag_lower(self._background_item)
        self._update_overlay_positions()

    def _img_to_screen(self, px, py):
        ox, oy = self.offset
        return (ox + px * self.scale, oy + py * self.scale)

    def _screen_to_img(self, sx, sy):
        ox, oy = self.offset
        return ((sx - ox) / self.scale, (sy - oy) / self.scale)

    def _redraw_overlay(self):
        if self.map_img is None:
            return
        self.canvas.delete("calib")
        self.canvas.delete("route")
        # 校准点
        for i, (px, py, gx, gy) in enumerate(self.calib_points):
            sx, sy = self._img_to_screen(px, py)
            self.canvas.create_oval(sx - 6, sy - 6, sx + 6, sy + 6,
                                    outline=CALIB_COL, width=2, tags="calib")
            self.canvas.create_text(sx + 12, sy - 12,
                                    text=f"{i}:({gx:.0f},{gy:.0f})",
                                    fill=CALIB_COL, font=("Consolas", 9),
                                    anchor="w", tags="calib")
        self._route_items = []
        for index in range(len(self.route_px)):
            self._append_route_item(index)

    def _append_route_item(self, index):
        px, py = self.route_px[index]
        sx, sy = self._img_to_screen(px, py)
        line = None
        if index:
            previous = self._img_to_screen(*self.route_px[index-1])
            line = self.canvas.create_line(*previous, sx, sy, fill=ROUTE_COL, width=2, capstyle=tk.ROUND, joinstyle=tk.ROUND, tags="route")
        dot = self.canvas.create_oval(sx-3, sy-3, sx+3, sy+3,
                                      fill=ROUTE_COL, outline=ROUTE_COL, width=0, tags="route")
        self._route_items.append((line, dot))
        if index == self.selected_route_index:
            self.canvas.itemconfigure(dot, fill=YELLOW, outline=YELLOW, width=2)

    def _update_overlay_positions(self):
        # Reuse items on camera changes; rebuilding is reserved for calibration edits.
        if self.calib_points or len(self._route_items) != len(self.route_px):
            self._redraw_overlay()
            return
        for index, (line, dot) in enumerate(self._route_items):
            sx, sy = self._img_to_screen(*self.route_px[index])
            self.canvas.coords(dot, sx-3, sy-3, sx+3, sy+3)
            if line is not None:
                self.canvas.coords(line, *self._img_to_screen(*self.route_px[index-1]), sx, sy)

    def on_wheel(self, e, direction=0):
        if self.map_img is None:
            return
        up = direction > 0 if direction != 0 else e.delta > 0
        factor = 1.1 if up else 1 / 1.1
        new_zoom = max(0.1, min(self.zoom * factor, 40.0))
        if abs(new_zoom - self.zoom) < 1e-6:
            return
        old_s = self.scale
        new_s = self.fit_scale * new_zoom
        ox, oy = self.offset
        ix = (e.x - ox) / old_s
        iy = (e.y - oy) / old_s
        self.zoom = new_zoom
        self.scale = new_s
        self.offset = (e.x - ix * new_s, e.y - iy * new_s)
        self._schedule_render(preview=True)

    def on_press(self, e):
        self._drag = (e.x, e.y, self.offset[0], self.offset[1])
        self._moved = False
        self._point_drag = self._hit_route_point(e.x, e.y) if self.mode == 'draw' else None
        if self._point_drag is not None:
            self._select_route_point(self._point_drag)

    def on_drag(self, e):
        if self._drag is None:
            return
        sx, sy, ox, oy = self._drag
        dx, dy = e.x - sx, e.y - sy
        if abs(dx) > 3 or abs(dy) > 3:
            if not self._moved and getattr(self, '_point_drag', None) is not None:
                self._remember_route()
            self._moved = True
        if self._moved:
            if getattr(self, '_point_drag', None) is not None:
                ix, iy = self._screen_to_img(e.x, e.y)
                self.route_px[self._point_drag] = (max(0, min(self.img_w-1e-6, ix)),
                                                  max(0, min(self.img_h-1e-6, iy)))
                self._update_overlay_positions()
                self.route_list.item(str(self._point_drag), values=self._route_row(self._point_drag))
                self._sync_start()
                self._select_route_point(self._point_drag)
                return
            previous_offset = self.offset
            self.offset = (ox + dx, oy + dy)
            if self._move_cached_background():
                # Both layers move together at native Canvas speed.
                self.canvas.move("route", self.offset[0]-previous_offset[0], self.offset[1]-previous_offset[1])
                self.canvas.move("calib", self.offset[0]-previous_offset[0], self.offset[1]-previous_offset[1])
            self._schedule_render(preview=True)

    def on_release(self, e):
        if self._drag is None:
            return
        self._drag = None
        self._point_drag = None
        if self._moved:
            self._moved = False
            self._finish_quality()
            return
        # 单击
        if self.map_img is None:
            return
        ix, iy = self._screen_to_img(e.x, e.y)
        if not (0 <= ix < self.img_w and 0 <= iy < self.img_h):
            return
        hit = self._hit_route_point(e.x, e.y)
        if hit is not None:
            self._select_route_point(hit)
            return
        if self.mode == "calib":
            self._add_calib_point(int(ix), int(iy))
        else:
            self._add_route_point(int(ix), int(iy))

    def on_right_click(self, e):
        if self.mode == "calib":
            self.undo_calib()
        else:
            self.undo_edit()

    def _on_canvas_resize(self):
        if self.map_img is not None:
            if self.zoom == 1.0:
                self._fit_and_center()
            self._schedule_render()

    # ---------- 模式 ----------
    def _on_mode_change(self):
        self.mode = self.var_mode.get()
        self._set_status("模式: " + ("校准" if self.mode == "calib" else "画线")
                         + "   |  左键点击/添加, 右键撤销")

    # ---------- 校准 ----------
    def _add_calib_point(self, px, py):
        estimate = ""
        if self.transform is not None:
            gx, gy = affine_apply(self.transform, px, py)
            estimate = f"当前映射估算游戏坐标：X={gx:.2f}, Y={gy:.2f}\n"
        s = simpledialog.askstring(
            "手动校准：输入实际游戏坐标",
            f"图片像素位置：({px}, {py})【不是游戏坐标】\n"
            + estimate
            + "仅需校准时填写该处实际游戏 X,Y。\n"
            + "查看现有映射请取消，再使用画路线模式。\n"
            + "不要把其他地图网址坐标当作游戏坐标。",
            parent=self.root)
        if not s:
            return
        nums = re.findall(r"-?\d+(?:\.\d+)?", s.replace("，", ",").replace("（", "(").replace("）", ")"))
        if len(nums) < 2:
            messagebox.showwarning("提示", "请按格式输入 x,y（两个数字）", parent=self.root)
            return
        gx, gy = float(nums[0]), float(nums[1])
        if not (COORD_RANGE[0] <= gx <= COORD_RANGE[1]
                and COORD_RANGE[0] <= gy <= COORD_RANGE[1]):
            messagebox.showwarning("提示", f"坐标超出合理范围 {COORD_RANGE}，请检查", parent=self.root)
            return
        self.calib_points.append((px, py, gx, gy))
        self._recompute_transform()
        self._redraw_overlay()

    def undo_calib(self):
        if self.calib_points:
            self.calib_points.pop()
            self._recompute_transform()
            self._redraw_overlay()

    def _recompute_transform(self):
        n = len(self.calib_points)
        self.transform = None
        self.residuals = None
        if n < 3:
            self._refresh_route_list()
            self.lbl_calib.config(
                text=f"校准点: {n} 个（至少 3 个）\n未拟合")
            return
        params, (rx, ry) = fit_affine(self.calib_points)
        self.transform = params
        self.residuals = (rx, ry)
        self._refresh_route_list()
        rmse = math.sqrt(sum(a * a for a in rx) + sum(b * b for b in ry)) / n
        self.lbl_calib.config(
            text=f"校准点: {n} 个\n仿射已拟合, 均方残差: {rmse:.2f}")
        self._set_status(f"校准完成: 残差 {rmse:.2f}，可以画线了")

    def _route_row(self, index):
        if self.transform is None:
            return (index + 1, "未校准", "未校准")
        gx, gy = affine_apply(self.transform, *self.route_px[index])
        return (index + 1, f"{gx:.2f}", f"{gy:.2f}")

    def _refresh_route_list(self):
        rows = self.route_list.get_children()
        if rows:
            self.route_list.delete(*rows)
        for index in range(len(self.route_px)):
            self.route_list.insert("", "end", iid=str(index), values=self._route_row(index))
        if self.selected_route_index is not None:
            self._select_route_point(self.selected_route_index)

    def _hit_route_point(self, sx, sy):
        nearest = None
        best = 10.0 ** 2  # Selection tolerance is screen pixels, independent of zoom.
        for index, point in enumerate(self.route_px):
            x, y = self._img_to_screen(*point)
            distance = (x-sx)**2 + (y-sy)**2
            if distance <= best:
                nearest, best = index, distance
        return nearest

    def _select_route_point(self, index):
        previous = self.selected_route_index
        if previous is not None and previous < len(self._route_items):
            self.canvas.itemconfigure(self._route_items[previous][1], fill=ROUTE_COL, outline=ROUTE_COL, width=0)
        if index is None or not 0 <= index < len(self.route_px):
            self.selected_route_index = None
            self.route_list.selection_remove(*self.route_list.selection())
            self.lbl_selected_route.config(text="点击已标记点或列表查看坐标", fg=FG_DIM)
            return
        self.selected_route_index = index
        if index < len(self._route_items):
            self.canvas.itemconfigure(self._route_items[index][1], fill=YELLOW, outline=YELLOW, width=2)
        self.route_list.selection_set(str(index))
        self.route_list.see(str(index))
        number, gx, gy = self._route_row(index)
        self.lbl_selected_route.config(text=f"标记点 {number}：X={gx}  Y={gy}", fg=YELLOW)
        self._set_status(f"已选标记点 {number}\n映射 X={gx}, Y={gy}\n双击列表可定位；二维底图不提供 Z")

    def _on_route_list_select(self, event=None):
        selected = self.route_list.selection()
        if selected:
            index = int(selected[0])
            if index != self.selected_route_index:
                self._select_route_point(index)

    def _center_selected_route_point(self, event=None):
        if self.selected_route_index is None:
            return
        px, py = self.route_px[self.selected_route_index]
        self.offset = (self.canvas.winfo_width()/2 - px*self.scale,
                       self.canvas.winfo_height()/2 - py*self.scale)
        self._schedule_render()

    # ---------- 画线 ----------
    def _add_route_point(self, px, py):
        if self.transform is None:
            messagebox.showwarning("提示", "请先完成校准（至少 3 个点）",
                                   parent=self.root)
            return
        if self.route_px and self.route_px[-1] == (px, py):
            return
        self._remember_route()
        self.route_px.append((px, py))
        self.lbl_route.config(text=f"路线点: {len(self.route_px)} 个")
        gx, gy = affine_apply(self.transform, px, py)
        self._set_status(f"图片像素: ({px}, {py})\n映射估算 X={gx:.2f}, Y={gy:.2f}\n二维底图不提供高度 Z")
        index = len(self.route_px)-1
        self._append_route_item(index)
        self.route_list.insert("", "end", iid=str(index), values=self._route_row(index))
        self._select_route_point(index)
        self._sync_start()

    def undo_route(self):
        if self.route_px:
            index = len(self.route_px)-1
            self.route_px.pop()
            self.route_list.delete(str(index))
            line, dot = self._route_items.pop()
            if line is not None:
                self.canvas.delete(line)
            self.canvas.delete(dot)
            self.lbl_route.config(text=f"路线点: {len(self.route_px)} 个")
            if self.selected_route_index == index:
                self._select_route_point(len(self.route_px)-1 if self.route_px else None)

    def clear_route(self):
        if self.route_px and messagebox.askyesno("确认", "清空所有路线点？",
                                                 parent=self.root):
            self._remember_route()
            self.route_px.clear()
            self.canvas.delete("route")
            self._route_items.clear()
            self._select_route_point(None)
            self._refresh_route_list()
            self.lbl_route.config(text="路线点: 0 个")
            self._sync_start()

    # ---------- 地图加载 ----------
    def on_load_gg(self):
        path = os.path.join(MAPS_DIR, "wuthering_gg", "huanglong_z4.png")
        try:
            with open(os.path.splitext(path)[0] + ".meta.json", encoding="utf-8-sig") as stream:
                meta = json.load(stream)
            with Image.open(path) as source:
                img = source.convert("RGB")
            self._load_map_image(img, meta, "wuthering.gg 瑝珑")
        except (OSError, ValueError, TypeError) as exc:
            messagebox.showerror("加载失败", str(exc), parent=self.root)

    def on_load_local(self):
        path = filedialog.askopenfilename(
            title="选择地图图片", parent=self.root,
            filetypes=[("图片", "*.png *.jpg *.jpeg *.webp"), ("所有", "*.*")])
        if not path:
            return
        try:
            meta_path = os.path.splitext(path)[0] + ".meta.json"
            meta = None
            if os.path.exists(meta_path):
                with open(meta_path, "r", encoding="utf-8-sig") as stream:
                    meta = json.load(stream)
            with Image.open(path) as source:
                img = source.convert("RGB")
            self._load_map_image(img, meta, os.path.basename(path))
        except (OSError, ValueError, TypeError) as exc:
            messagebox.showerror("加载失败", str(exc), parent=self.root)

    def _load_map_image(self, img, meta, name):
        self._cancel_render_jobs()
        if self._detail_job is not None:
            self.root.after_cancel(self._detail_job)
            self._detail_job = None
        if self._detail_tiles is not None:
            self._detail_tiles.close()
            self._detail_tiles = None
        if (isinstance(meta, dict) and meta.get("source") == "wuthering.gg"
                and meta.get("z") == 4 and meta.get("origin_tile") == [0, 0]
                and img.size == (4096, 4096)):
            from app.map_editor.detail_tiles import DetailTiles
            self._detail_tiles = DetailTiles(os.path.join(MAPS_DIR, "wuthering_gg", "tile_cache"),
                                  str(paths.RESEARCH / "wuthering_gg"), fetch=None)
            self._detail_job = self.root.after(150, self._poll_detail)
        self._background_view = None
        # Switching maps must not retain a previous map's calibration or route.
        self.calib_points = []
        self.route_px = []
        self.selected_route_index = None
        self._refresh_route_list()
        self.lbl_selected_route.config(text="点击已标记点或列表查看坐标", fg=FG_DIM)
        self.canvas.delete("route")
        self.canvas.delete("calib")
        self._route_items = []
        self.transform = None
        self.residuals = None
        self.lbl_route.config(text="路线点: 0 个")
        self.lbl_calib.config(text="校准点: 0 个（至少 3 个）\n未拟合")
        if isinstance(meta, dict) and meta.get("source") == "wuthering.gg":
            from app.map_editor.map_assets import checked_metadata_affine
            self.transform = checked_metadata_affine(meta, img.size)
            self.lbl_calib.config(text="wuthering.gg 坐标映射已接入\n样本支持约1～3单位；非全图精度保证")
        self.btn_export.config(text="导出路线")
        self.map_img = img
        self._viewport_renderer = MapViewportRenderer(img)
        self.map_meta = meta
        self.img_w, self.img_h = img.size
        self._history.clear()
        self._sync_start()
        self.zoom = 1.0
        self._fit_and_center()
        self._render()
        info = meta or {}
        self._set_status(f"已加载: {name}\n尺寸 {self.img_w}x{self.img_h}"
                         + (f"  z={info.get('z')} 缺瓦片={info.get('missing')}"
                            if info else ""))

    # ---------- 导出 ----------
    def on_export(self):
        # Provisional GG mapping must not silently become an executable route.
        if isinstance(self.map_meta, dict) and self.map_meta.get("source") == "wuthering.gg":
            if self.transform is None or not self.route_px:
                messagebox.showwarning("提示", "请先在地图上画出路线", parent=self.root)
                return
            points = [list(affine_apply(self.transform, x, y)) for x, y in self.route_px]
            if not all(math.isfinite(v) for point in points for v in point):
                messagebox.showerror("导出失败", "路线包含无效坐标", parent=self.root)
                return
            path = filedialog.asksaveasfilename(parent=self.root, title="保存待核验路线草稿",
                initialdir=ROUTES_DIR, initialfile="gg_route_draft.json", defaultextension=".json",
                filetypes=[("JSON", "*.json")])
            if not path:
                return
            protected = {os.path.normcase(os.path.abspath(os.path.join(ROUTES_DIR, name)))
                         for name in ("waypoints.json", "recorded_path.json")}
            if os.path.normcase(os.path.abspath(path)) in protected:
                messagebox.showwarning("保护寻路文件", "请另选草稿文件名，不覆盖 waypoints.json 或 path.json", parent=self.root)
                return
            draft = {"source": "wuthering.gg", "navigation_approved": False,
                     "coordinate_status": "sample_supported_not_global_accuracy_guarantee",
                     "points": [[round(v, 3) for v in point] for point in points],
                     "height": None, "image_size": [self.img_w, self.img_h],
                     "pixel_to_game_affine": list(self.transform),
                     "warning": "仅用于坐标核对；不是可执行寻路路线。二维地图无法推断高度。"}
            with open(path, "w", encoding="utf-8") as stream:
                json.dump(draft, stream, ensure_ascii=False, indent=2)
            self._set_status("已保存待核验路线草稿：" + path)
            return
        if self.transform is None:
            messagebox.showwarning("提示", "请先完成校准", parent=self.root)
            return
        if not self.route_px:
            messagebox.showwarning("提示", "还没有画路线", parent=self.root)
            return

        waypoints = []
        for px, py in self.route_px:
            gx, gy = affine_apply(self.transform, px, py)
            waypoints.append([round(gx, 2), round(gy, 2)])

        bad = [w for w in waypoints
               if not (COORD_RANGE[0] <= w[0] <= COORD_RANGE[1]
                       and COORD_RANGE[0] <= w[1] <= COORD_RANGE[1])]
        if bad:
            messagebox.showwarning(
                "坐标超范围", f"有 {len(bad)} 个点超出游戏坐标范围 {COORD_RANGE}\n"
                "请检查校准是否正确", parent=self.root)
            return

        path = str(paths.WAYPOINT_ROUTE)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(waypoints, f, ensure_ascii=False, indent=2)
        self._set_status(f"已导出 {len(waypoints)} 个点 → {path}")
        messagebox.showinfo("导出成功",
                            f"{len(waypoints)} 个点已保存到:\n{path}",
                            parent=self.root)


def main():
    import argparse
    parser=argparse.ArgumentParser(description='鸣潮路线工作台')
    parser.add_argument('--start',help='预填并定位路线起点，例如 --start=-589,1053')
    args=parser.parse_args()
    start=None
    if args.start:
        try:start=parse_xy(args.start)
        except ValueError as exc:parser.error(str(exc))
    root = tk.Tk()
    app = MapDrawApp(root)
    # 启动时加载当前采用的 wuthering.gg 主地图。
    default_png = os.path.join(MAPS_DIR, "wuthering_gg", "huanglong_z4.png")
    if os.path.exists(default_png):
        meta = None
        meta_path = os.path.splitext(default_png)[0] + ".meta.json"
        if os.path.exists(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
            except Exception:
                meta = None
        try:
            img = Image.open(default_png).convert("RGB")
            app._load_map_image(img, meta, os.path.basename(default_png))
        except Exception as e:
            app._set_status(f"自动加载默认地图失败: {e}")
    if start is not None:
        def apply_start():
            root.update_idletasks()
            if app.map_img is not None:app._fit_and_center()
            try:app._set_start_point(start)
            except ValueError as exc:app._set_status(str(exc))
            print(f'路线工作台已启动：起点 {app.start_xy.get()}',flush=True)
        root.after(150,apply_start)
    root.mainloop()


if __name__ == "__main__":
    main()
