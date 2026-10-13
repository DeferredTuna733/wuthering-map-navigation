"""Small keyboard-accessible rounded Canvas button, no extra UI dependency."""
import tkinter as tk


class RoundedButton(tk.Canvas):
    def __init__(self, parent, text, command, color='#e9ebef', foreground='#20242b', **kwargs):
        super().__init__(parent, height=38, bg=parent.cget('bg'), highlightthickness=0,
                         takefocus=True, cursor='hand2', **kwargs)
        self.text, self.command, self.color, self.foreground = text, command, color, foreground
        self.disabled = False
        self.bind('<Configure>', self._paint)
        self.bind('<ButtonRelease-1>', self._invoke)
        self.bind('<Return>', self._invoke)
        self.bind('<space>', self._invoke)
        self.bind('<FocusIn>', self._paint)
        self.bind('<FocusOut>', self._paint)

    def _invoke(self, event=None):
        if not self.disabled:
            self.focus_set()
            self.command()

    def _paint(self, event=None):
        self.delete('all')
        w, h, r = max(28, self.winfo_width()), self.winfo_height(), 12
        color = '#eceef1' if self.disabled else self.color
        points = [r, 2, w-r, 2, w-2, 2, w-2, r, w-2, h-r, w-2, h-2,
                  w-r, h-2, r, h-2, 2, h-2, 2, h-r, 2, r, 2, 2]
        self.create_polygon(points, smooth=True, splinesteps=24, fill=color,
                            outline='#aeb7c5' if self.focus_get() == self else color)
        self.create_text(w/2, h/2, text=self.text, fill='#9298a2' if self.disabled else self.foreground,
                         font=('Microsoft YaHei UI', 10))

    def config(self, cnf=None, **kwargs):
        if 'text' in kwargs:
            self.text = kwargs.pop('text')
        if 'state' in kwargs:
            self.disabled = kwargs.pop('state') == 'disabled'
        result = super().config(cnf, **kwargs)
        self._paint()
        return result

    configure = config
