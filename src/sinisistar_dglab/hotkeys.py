"""Windows global shortcuts, transactional replacement and Qt key recording."""
import ctypes,sys
from ctypes import wintypes
from PySide6.QtCore import QObject,QAbstractNativeEventFilter,QEvent,Qt,QKeyCombination
from PySide6.QtGui import QKeySequence

DEFAULT={'sequence':'Ctrl+F12','modifiers':2,'vk':123}
MOD_KEYS={int(Qt.Key_Shift),int(Qt.Key_Control),int(Qt.Key_Alt),int(Qt.Key_Meta),int(Qt.Key_AltGr)}
SPECIAL={int(Qt.Key_Backspace):8,int(Qt.Key_Tab):9,int(Qt.Key_Return):13,int(Qt.Key_Enter):13,int(Qt.Key_Escape):27,
    int(Qt.Key_Space):32,int(Qt.Key_PageUp):33,int(Qt.Key_PageDown):34,int(Qt.Key_End):35,int(Qt.Key_Home):36,
    int(Qt.Key_Left):37,int(Qt.Key_Up):38,int(Qt.Key_Right):39,int(Qt.Key_Down):40,int(Qt.Key_Insert):45,int(Qt.Key_Delete):46,
    int(Qt.Key_Pause):19,int(Qt.Key_Print):44,int(Qt.Key_ScrollLock):145,int(Qt.Key_CapsLock):20,
    43:187,61:187,45:189,44:188,46:190,47:191,59:186,39:222,91:219,93:221,92:220,96:192}

def shortcut(key,modifiers=0,native_vk=0):
    key=int(key);mods=int(getattr(modifiers,"value",modifiers))
    if key in MOD_KEYS:raise ValueError('请同时按下一个非修饰键')
    if mods & Qt.MetaModifier.value:win_mod=8
    else:win_mod=0
    for qt,win in ((Qt.ControlModifier,2),(Qt.ShiftModifier,4),(Qt.AltModifier,1)):
        if mods & qt.value:win_mod|=win
    vk=int(native_vk) or (112+key-int(Qt.Key_F1) if int(Qt.Key_F1)<=key<=int(Qt.Key_F24) else key if 48<=key<=90 else SPECIAL.get(key,0))
    if not 1<=vk<=254:raise ValueError('此按键不支持全局快捷键')
    if mods & Qt.KeypadModifier.value and not native_vk and 48<=key<=57:vk=96+key-48
    sequence=QKeySequence(QKeyCombination(Qt.KeyboardModifier(mods),Qt.Key(key))).toString(QKeySequence.PortableText)
    if not sequence:raise ValueError('无法识别这个按键')
    return dict(sequence=sequence,modifiers=win_mod,vk=vk)

def normalize_shortcut(raw):
    if not isinstance(raw,dict):return dict(DEFAULT)
    sequence=raw.get('sequence');mods=raw.get('modifiers');vk=raw.get('vk')
    if not isinstance(sequence,str) or not sequence or type(mods)is not int or mods & ~15 or type(vk)is not int or not 1<=vk<=254:return dict(DEFAULT)
    parsed=QKeySequence.fromString(sequence,QKeySequence.PortableText)
    if parsed.count()!=1 or parsed.isEmpty():return dict(DEFAULT)
    return dict(sequence=sequence,modifiers=mods,vk=vk)

class WindowsApi:
    def __init__(self):self.user=ctypes.WinDLL('user32',use_last_error=True)
    def register(self,ident,mods,vk):
        if self.user.RegisterHotKey(None,ident,mods|0x4000,vk):return ''
        code=ctypes.get_last_error();return str(code)+' · '+ctypes.FormatError(code).strip()
    def unregister(self,ident):self.user.UnregisterHotKey(None,ident)

class NativeFilter(QAbstractNativeEventFilter):
    def __init__(self,owner):super().__init__();self.owner=owner
    def nativeEventFilter(self,event_type,message):
        if event_type not in (b'windows_generic_MSG',b'windows_dispatcher_MSG'):return False,0
        msg=wintypes.MSG.from_address(int(message))
        return self.owner.dispatch(msg.message,int(msg.wParam)),0

class GlobalHotkeys(QObject):
    def __init__(self,app,backend,api=None,install=True):
        super().__init__();self.app=app;self.backend=backend;self.api=api or WindowsApi();self.active=dict(backend._emergency_shortcut)
        self.ident=7162;self.registered=False;self.hud_registered=False;self._hud_suspended=False;self.capturing=False;self.candidate=None;self.error='';self.closed=False
        self.native=NativeFilter(self);self.installed=install
        if install:app.installNativeEventFilter(self.native);app.installEventFilter(self)
        self.error=self.api.register(self.ident,self.active['modifiers'],self.active['vk']);self.registered=not self.error
        self.hud_registered=not self.api.register(7163,2,122)
        backend._hotkey_manager=self;self.notify()
    def notify(self):
        self.backend._emergency_hotkey_registered=self.registered;self.backend._hud_hotkey_registered=self.hud_registered
        self.backend.hotkeyChanged.emit();self.backend.hudChanged.emit()
    def snapshot(self):return dict(sequence=self.active['sequence'],registered=self.registered,capturing=self.capturing,candidate=self.candidate or {},error=self.error)
    def begin(self):
        if self.closed:return
        if self.registered:self.api.unregister(self.ident);self.registered=False
        if self.hud_registered:self.api.unregister(7163);self.hud_registered=False;self._hud_suspended=True
        self.capturing=True;self.candidate=None;self.error='';self.notify()
    def cancel(self):
        if self.closed:return
        self.capturing=False
        if not self.registered:
            self.error=self.api.register(self.ident,self.active['modifiers'],self.active['vk']);self.registered=not self.error
        if self._hud_suspended:
            self.hud_registered=not self.api.register(7163,2,122);self._hud_suspended=False
        self.notify()
    def record(self,key,modifiers,native_vk=0):
        if self.closed:return
        if int(key) in MOD_KEYS:return
        try:self.candidate=shortcut(key,modifiers,native_vk)
        except ValueError as e:self.error=str(e);self.notify();return
        self.cancel()
    def eventFilter(self,obj,event):
        if self.capturing and event.type()==QEvent.KeyPress:
            if not event.isAutoRepeat():self.record(event.key(),event.modifiers().value,event.nativeVirtualKey())
            return True
        return False
    def apply(self,value=None):
        if self.closed:return False
        self.cancel();candidate=value or self.candidate
        if not candidate:self.error='请先录入快捷键';self.notify();return False
        if candidate['modifiers']==2 and candidate['vk']==122:self.error='Ctrl+F11 已用于调整 HUD';self.notify();return False
        if candidate==self.active and self.registered:self.error='';self.notify();return True
        new_id=7164 if self.ident==7162 else 7162
        error=self.api.register(new_id,candidate['modifiers'],candidate['vk'])
        if error:self.error='快捷键不可用，请重新录入：'+error;self.notify();return False
        if self.registered:self.api.unregister(self.ident)
        self.ident=new_id;self.active=dict(candidate);self.registered=True;self.error='';self.candidate=None
        self.backend._emergency_shortcut=dict(candidate);self.backend.save();self.notify();return True
    def dispatch(self,message,ident):
        if message!=0x312:return False
        if ident==self.ident and self.registered and not self.capturing:self.backend.emergencyStop();return True
        if ident==7163 and self.hud_registered:self.backend.toggleHudAdjusting();return True
        return False
    def close(self):
        if self.closed:return
        self.closed=True
        if self.registered:self.api.unregister(self.ident)
        if self.hud_registered:self.api.unregister(7163)
        if self.installed:self.app.removeNativeEventFilter(self.native);self.app.removeEventFilter(self)
        self.registered=False;self.hud_registered=False;self.notify()
