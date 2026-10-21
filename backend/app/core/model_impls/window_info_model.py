import ctypes
from ctypes import wintypes
import pygetwindow as gw

from app.constant import GAME_TITLES
from app.core.custom_exception import WindowNotFoundException
from app.core.data_models.model_io import WindowInfoOutput
from app.core.interfaces.model_interface import ModelInterface


class WindowInfoModel(ModelInterface):
    @staticmethod
    def get_name():
        return 'window_info_model'

    def load(self):
        self.hwnd = None
        try:
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except (AttributeError, OSError):
            ctypes.windll.user32.SetProcessDPIAware()

    def predict(self, input_data):
        windows = [w for title in GAME_TITLES for w in gw.getWindowsWithTitle(title) if w.title == title]
        if len(windows) != 1 or windows[0].isMinimized:
            raise WindowNotFoundException('请打开唯一的星铁游戏窗口，并取消最小化')
        self.hwnd = windows[0]._hWnd
        rect, origin = wintypes.RECT(), wintypes.POINT(0, 0)
        user = ctypes.windll.user32
        if not user.GetClientRect(self.hwnd, ctypes.byref(rect)) or not user.ClientToScreen(self.hwnd, ctypes.byref(origin)):
            raise WindowNotFoundException('无法读取游戏客户区')
        return WindowInfoOutput(width=rect.right, height=rect.bottom, left=origin.x, top=origin.y)
