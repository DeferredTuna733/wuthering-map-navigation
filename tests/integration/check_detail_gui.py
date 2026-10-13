"""Bounded hidden integration smoke test; exits without game interaction."""
import json
from pathlib import Path
from time import monotonic
import tkinter as tk
from PIL import Image
from app.map_editor.gui import MapDrawApp

root=tk.Tk();root.withdraw();app=MapDrawApp(root)
root.update_idletasks()
from app.project_paths import MAPS
folder=MAPS/'wuthering_gg'
app._load_map_image(Image.open(folder/'huanglong_z4.png').convert('RGB'),
                    json.loads((folder/'huanglong_z4.meta.json').read_text(encoding='utf-8')),'detail smoke')
# Force a previously uncached view away from the three research patches.
app.scale=4;app.offset=(-2300,-1900);app._background_view=None
app._render();start=monotonic();success=False

def tick():
    global success
    if app._detail_tiles.revision:
        success=True
        before=app._screen_to_img(20,20)
        app._background_view=None;app._render()
        assert before==app._screen_to_img(20,20)
        app._add_route_point(855,1886);app.undo_route()
        print('DETAIL_OK', 'tiles',app._detail_tiles.revision,'errors',app._detail_tiles.errors,flush=True)
        app._close()
    elif monotonic()-start>35:
        print('DETAIL_TIMEOUT', 'errors',app._detail_tiles.errors,flush=True);app._close()
    else:root.after(100,tick)
root.after(100,tick);root.mainloop()
if not success:raise SystemExit(1)
