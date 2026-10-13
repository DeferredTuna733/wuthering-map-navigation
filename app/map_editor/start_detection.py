"""User-triggered screen OCR; no game memory, movement, or sign guessing."""
import ctypes
from ctypes import wintypes
import time


def detect_start(cancel):
    import mss
    import numpy as np
    import psutil
    from app.navigation.coordinate_reader import get_ocr, inspect_crop
    from app.navigation.screen_region import resolve_region
    user = ctypes.WinDLL('user32', use_last_error=True)
    user.GetForegroundWindow.restype = wintypes.HWND
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.IsWindowVisible.argtypes = [wintypes.HWND]
    user.SetForegroundWindow.argtypes = [wintypes.HWND]
    user.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    candidates = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @callback_type
    def visit(hwnd, param):
        if user.IsWindowVisible(hwnd):
            pid = wintypes.DWORD()
            user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            try:
                if psutil.Process(pid.value).name().casefold() == 'client-win64-shipping.exe':
                    candidates.append(hwnd)
            except psutil.Error:
                pass
        return True

    user.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user.EnumWindows(visit, 0)
    if len(candidates) != 1:
        raise ValueError('未找到唯一游戏窗口，请先启动游戏')
    handle = candidates[0]
    # Windows may deny foreground activation. Never capture a different app.
    user.ShowWindow(handle, 9)
    user.SetForegroundWindow(handle)
    get_ocr()
    deadline = time.monotonic()+12
    with mss.MSS() as cap:
        region, _ = resolve_region(cap.monitors)
        previous = None
        while time.monotonic() < deadline and not cancel.is_set():
            if user.GetAsyncKeyState(0x7B) & 0x8000:
                raise ValueError('检测已取消')
            if user.GetForegroundWindow() != handle:
                cancel.wait(.2)
                continue
            crop = np.asarray(cap.grab(region))
            diagnostic = inspect_crop(crop)
            if user.GetForegroundWindow() != handle:
                previous = None
                continue
            point = diagnostic['coordinate']
            if point is not None and point == previous:
                return point
            previous = point
            cancel.wait(.15)
    raise ValueError('未得到稳定坐标。请关闭游戏地图、站定并显示坐标后重试；可手动输入')
