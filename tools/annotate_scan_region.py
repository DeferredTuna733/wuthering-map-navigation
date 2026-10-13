"""Let the user draw on a saved minimap; never captures or controls the game."""
import argparse
import json
from pathlib import Path
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageDraw, ImageTk


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('image', type=Path)
    args = parser.parse_args()
    source = args.image.resolve()
    original = Image.open(source).convert('RGB')
    root = tk.Tk()
    root.title('标出白色扫描区 — 按住左键画圈或箭头')
    root.attributes('-topmost', True)
    scale = min(3, (root.winfo_screenheight() - 220) / original.height,
                (root.winfo_screenwidth() - 100) / original.width)
    width, height = round(original.width * scale), round(original.height * scale)
    photo = ImageTk.PhotoImage(original.resize((width, height)))
    tk.Label(root, text='在这张截图上圈出白色扫描区。左键拖动画线；画好后点击保存。').pack(padx=12, pady=10)
    canvas = tk.Canvas(root, width=width, height=height, highlightthickness=0)
    canvas.pack(padx=12)
    canvas.create_image(0, 0, anchor='nw', image=photo)
    strokes = []
    active = []
    items = []

    def point(event):
        return (max(0, min(width - 1, event.x)), max(0, min(height - 1, event.y)))

    def begin(event):
        active.clear()
        active.append(point(event))

    def draw(event):
        if not active:
            return
        current = point(event)
        items.append(canvas.create_line(*active[-1], *current, fill='#ff3030', width=3,
                                        capstyle=tk.ROUND, joinstyle=tk.ROUND))
        active.append(current)

    def finish(event):
        if not active:
            return
        draw(event)
        strokes.append(list(active))
        active.clear()

    def clear():
        for item in items:
            canvas.delete(item)
        items.clear()
        strokes.clear()
        active.clear()

    def save(event=None):
        if not strokes:
            messagebox.showinfo('请先画线', '请先圈出白色扫描区，再保存。', parent=root)
            return
        points = [[(x * original.width / width, y * original.height / height)
                   for x, y in stroke] for stroke in strokes]
        output = source.parent / 'user_scan_annotation.png'
        overlay = original.copy()
        pen = ImageDraw.Draw(overlay)
        for stroke in points:
            pen.line(stroke, fill=(255, 48, 48), width=2)
        try:
            overlay.save(output)
            (source.parent / 'user_scan_annotation.json').write_text(json.dumps({
                'source_image': str(source), 'image_size': list(original.size),
                'strokes_image_xy': points}, ensure_ascii=False, indent=2), encoding='utf-8')
        except OSError as error:
            messagebox.showerror('保存失败', str(error), parent=root)
            return
        print(f'已保存：{output}', flush=True)
        root.destroy()

    canvas.bind('<ButtonPress-1>', begin)
    canvas.bind('<B1-Motion>', draw)
    canvas.bind('<ButtonRelease-1>', finish)
    buttons = tk.Frame(root)
    buttons.pack(pady=12)
    tk.Button(buttons, text='清空重画', command=clear).pack(side='left', padx=8)
    tk.Button(buttons, text='保存标注（Enter）', command=save).pack(side='left', padx=8)
    root.bind('<Return>', save)
    root.bind('<Escape>', lambda event: root.destroy())
    root.update_idletasks()
    root.geometry(f'+{max(0,(root.winfo_screenwidth()-root.winfo_reqwidth())//2)}'
                  f'+{max(0,(root.winfo_screenheight()-root.winfo_reqheight())//2)}')
    root.lift()
    root.after(100, root.focus_force)
    root.mainloop()


if __name__ == '__main__':
    main()
