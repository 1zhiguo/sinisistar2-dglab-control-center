# GPL-3.0-only. Read-only viewport/DPI primitives adapted from the user-provided Stellar Blade HUD.
"""Place the display-only HUD over the foreground game's client area.

This module queries window bounds only. It never activates a window or changes
the game's display mode. Win32 coordinates are physical pixels; Qt window
geometry uses the target screen's logical coordinates.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import sys

from PySide6.QtCore import QObject, QRect, QTimer
from PySide6.QtGui import QGuiApplication
from .hud_settings import sanitize_hud

def hud_geometry(client,width,height,settings,flow=False,route='pulse'):
    p=sanitize_hud(settings);margin=20
    width=max(1,min(width,client.width()));height=max(1,min(height,client.height()))
    anchor=p['anchor']
    if anchor=='auto':anchor='bottom_center'
    if anchor=='custom':
        left=(client.width()-width)*p['x']/100;top=(client.height()-height)*p['y']/100
    else:
        vertical,horizontal=anchor.split('_')
        left=margin if horizontal=='left' else client.width()-width-margin if horizontal=='right' else (client.width()-width)/2
        top=margin if vertical=='top' else (client.height()-height)/2 if vertical=='middle' else client.height()-height-margin
    return QRect(client.x()+round(max(0,min(client.width()-width,left))),client.y()+round(max(0,min(client.height()-height,top))),width,height)

def hud_dialogue_hidden(state,settings):
    """Only a fresh non-death conversation hides the output HUD."""
    if not sanitize_hud(settings)['hide_dialogue'] or not state.get('pluginFresh'):return False
    flow=state.get('flow') or {}
    death=((state.get('valid') and type(state.get('hp')) is int and state['hp']==0)
           or (flow.get('playing') is True and flow.get('defeat_confirmed') is True)
           or state.get('penaltyClassification') in ('recoverable_penalty','regional_defeat','one_hp_penalty','struggle_penalty','scripted_go'))
    if death:return False
    return bool(state.get('hudDialogueActive') or state.get('dialoguePending') or state.get('eventPlaying') or flow.get('playing'))


@dataclass(frozen=True)
class GameViewport:
    x: int
    y: int
    width: int
    height: int
    monitor_x: int = 0
    monitor_y: int = 0
    monitor_name: str = ""
    monitor_width: int = 0
    monitor_height: int = 0


def screen_for_viewport(viewport: GameViewport, screens):
    """Match Win32 device names, then physical bounds for EDID-named screens."""
    for screen in screens:
        if viewport.monitor_name and screen.name().casefold() == viewport.monitor_name.casefold():
            return screen
    for screen in screens:
        bounds, dpr = screen.geometry(), screen.devicePixelRatio()
        dimensions_match = (abs(bounds.width() * dpr - viewport.monitor_width) <= 2
                            and abs(bounds.height() * dpr - viewport.monitor_height) <= 2)
        origin_match = any(abs(bounds.x() * scale - viewport.monitor_x) <= 2
                           and abs(bounds.y() * scale - viewport.monitor_y) <= 2
                           for scale in (1.0, dpr))
        if dimensions_match and origin_match:
            return screen
    return None


def logical_client_rect(viewport: GameViewport, screen) -> QRect:
    dpr = max(.1, float(screen.devicePixelRatio()))
    bounds = screen.geometry()
    return QRect(round(bounds.x() + (viewport.x - viewport.monitor_x) / dpr),
                 round(bounds.y() + (viewport.y - viewport.monitor_y) / dpr),
                 max(1, round(viewport.width / dpr)),
                 max(1, round(viewport.height / dpr)))


class ForegroundGameWindow:
    """Read the exact foreground PID's client bounds without changing focus."""

    def __init__(self):
        self.api = ctypes.WinDLL("user32", use_last_error=True) if sys.platform == "win32" else None
        if self.api is None:
            return
        api = self.api
        api.GetForegroundWindow.argtypes = []
        api.GetForegroundWindow.restype = wintypes.HWND
        api.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        api.GetWindowThreadProcessId.restype = wintypes.DWORD
        for name in ("IsWindowVisible", "IsIconic"):
            getattr(api, name).argtypes = [wintypes.HWND]
            getattr(api, name).restype = wintypes.BOOL
        api.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        api.GetClientRect.restype = wintypes.BOOL
        api.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
        api.ClientToScreen.restype = wintypes.BOOL
        api.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        api.MonitorFromWindow.restype = wintypes.HANDLE
        api.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
        api.GetMonitorInfoW.restype = wintypes.BOOL
        api.SetThreadDpiAwarenessContext.argtypes = [wintypes.HANDLE]
        api.SetThreadDpiAwarenessContext.restype = wintypes.HANDLE

    def __call__(self, process_id: int) -> GameViewport | None:
        if self.api is None or process_id <= 0:
            return None
        api = self.api
        handle = api.GetForegroundWindow()
        if not handle:
            return None
        owner = wintypes.DWORD()
        api.GetWindowThreadProcessId(handle, ctypes.byref(owner))
        if owner.value != process_id or not api.IsWindowVisible(handle) or api.IsIconic(handle):
            return None

        class MonitorInfo(ctypes.Structure):
            _fields_ = [("size", wintypes.DWORD), ("monitor", wintypes.RECT),
                        ("work", wintypes.RECT), ("flags", wintypes.DWORD),
                        ("device", wintypes.WCHAR * 32)]

        previous_dpi = api.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
        try:
            bounds, origin = wintypes.RECT(), wintypes.POINT(0, 0)
            monitor = MonitorInfo()
            monitor.size = ctypes.sizeof(monitor)
            if not api.GetClientRect(handle, ctypes.byref(bounds)) or not api.ClientToScreen(handle, ctypes.byref(origin)):
                return None
            if bounds.right < 64 or bounds.bottom < 64:
                return None
            if not api.GetMonitorInfoW(api.MonitorFromWindow(handle, 2), ctypes.byref(monitor)):
                return None
            return GameViewport(origin.x, origin.y, bounds.right, bounds.bottom,
                                monitor.monitor.left, monitor.monitor.top, monitor.device,
                                monitor.monitor.right - monitor.monitor.left,
                                monitor.monitor.bottom - monitor.monitor.top)
        finally:
            if previous_dpi:
                api.SetThreadDpiAwarenessContext(previous_dpi)

class HudWindowController(QObject):
    """Keep the single combined output strip inside the foreground game."""
    def __init__(self,backend,window,*,viewport_reader=None):
        super().__init__(window);self.backend=backend;self.window=window
        self.panels={'strip':window}
        self.reader=viewport_reader or ForegroundGameWindow();self.last=None;self.pid=0
        self.timer=QTimer(self);self.timer.setInterval(100);self.timer.timeout.connect(self.tick);self.timer.start()
    def tick(self):
        state=self.backend.state;adjust=self.backend.hudAdjusting
        options=self.backend.hudSettings
        if not state['hud'] or not any(options[k] for k in ('pulse_a','pulse_b','ovc_a','ovc_b')) or (not adjust and hud_dialogue_hidden(state,options)):
            for panel in self.panels.values():panel.setVisible(False)
            return
        pid=state['gamePid'] if state['pluginFresh'] else 0
        if pid!=self.pid:self.pid=pid;self.last=None
        viewport=self.reader(pid) if pid>0 else None
        if viewport:self.last=viewport
        elif not adjust:
            for panel in self.panels.values():panel.setVisible(False)
            return
        else:viewport=self.last
        screens=QGuiApplication.screens()
        screen=screen_for_viewport(viewport,screens) if viewport else self.window.screen() or QGuiApplication.primaryScreen()
        if screen is None:screen=QGuiApplication.primaryScreen()
        if screen is None:
            for panel in self.panels.values():panel.setVisible(False)
            return
        client=logical_client_rect(viewport,screen) if viewport else screen.availableGeometry()
        for route,panel in self.panels.items():
            panel.setScreen(screen)
            panel.setProperty('hudOriginX',client.x());panel.setProperty('hudOriginY',client.y())
            panel.setProperty('hudClientWidth',client.width());panel.setProperty('hudClientHeight',client.height())
            scale=options['scale']/100
            width=max(1,float(panel.property('naturalWidth') or 480)*scale)
            height=max(1,float(panel.property('naturalHeight') or 120)*scale)
            fit=min(1.,max(.01,(client.width()-32)/width),max(.01,(client.height()-32)/height))
            panel.setProperty('fitScale',fit)
            if not panel.property('hudDragging'):
                rect=hud_geometry(client,round(width*fit),round(height*fit),options,route=route)
                if rect!=panel.geometry():panel.setGeometry(rect)
            panel.setVisible(True)
    def shutdown(self):
        self.timer.stop()
        for panel in self.panels.values():panel.setVisible(False)

