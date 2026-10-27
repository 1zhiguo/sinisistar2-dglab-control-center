"""DG-LAB V3 pairing and bounded, revocable feedback output.

APP-facing messages follow the official V3 protocol and the Ricca bridge:
https://github.com/dungeonlab-open/dglab-websocket-server#v3-protocol
The integrated controller is local to this service; remote sockets are APPs.
Pairing confirms an APP Socket connection, not Bluetooth hardware presence.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
import ctypes
from ctypes import wintypes
import ipaddress
import json
import math
import queue
import re
import socket
import sys
import threading
import time
import uuid

import websockets

DEFAULT_PORT = 10002
ZERO_COMMANDS = ("strength-1+2+0", "strength-2+2+0", "clear-1", "clear-2")
_FEEDBACK = re.compile(r"strength-(\d{1,3})\+(\d{1,3})\+(\d{1,3})\+(\d{1,3})\Z")
OUTPUT_LEASE_SECONDS = .6
FRAME_SECONDS = .1
PLAN_LEASE_SECONDS = .25

def stream_frame(samples,frequencies,strength):
    """Encode four absolute plan samples against the final channel strength."""
    if len(samples)!=4 or len(frequencies)!=4 or strength<=0:raise ValueError('Invalid stream frame')
    freq=''.join(f'{frequency_byte(hz):02X}' for hz in frequencies)
    amp=''.join(f'{max(0,min(100,round(min(strength,value)/strength*100))):02X}' for value in samples)
    return freq+amp


def frequency_byte(hertz: float) -> int:
    """Convert UI Hz to the V3 period encoding, not a literal Hz byte.

    https://github.com/dungeonlab-open/dglab-bluetooth-protocol/blob/main/coyote/README.md
    https://github.com/dungeonlab-open/dglab-bluetooth-protocol/blob/main/coyote/v3/README.md
    """
    frequency = float(hertz)
    if not math.isfinite(frequency) or not 1 <= frequency <= 100:
        raise ValueError("Frequency must be 1..100 Hz")
    period = max(10, min(1000, int(round(1000 / frequency))))
    if period <= 100:
        return period
    if period <= 600:
        return (period - 100) // 5 + 100
    return (period - 600) // 10 + 200


def envelope_frame(points: tuple[float, ...], frequency: int, index: int, duration: float) -> str:
    """Four interpolated 25ms samples form one 100ms V3 frame."""
    amplitudes = []
    for quarter in range(4):
        elapsed = (index * 4 + quarter) * .025
        if elapsed >= duration:
            amplitudes.append(0)
            continue
        location = min(1., elapsed / max(.025, duration - .025)) * (len(points) - 1)
        lower = int(location)
        fraction = location - lower
        value = points[lower] * (1 - fraction) + points[min(lower + 1, len(points) - 1)] * fraction
        amplitudes.append(max(0, min(100, int(round(value * 100)))))
    return f"{frequency:02X}" * 4 + "".join(f"{amplitude:02X}" for amplitude in amplitudes)


def discover_lan_ips() -> list[str]:
    """Read active IPv4 interfaces, preferring physical adapters on Windows."""
    rows: list[tuple[bool, str]] = []
    if sys.platform == "win32":
        try:
            class Address(ctypes.Structure):
                _fields_ = [("address", ctypes.c_void_p), ("length", ctypes.c_int)]

            class Unicast(ctypes.Structure):
                pass

            Unicast._fields_ = [("header", ctypes.c_ulonglong), ("next", ctypes.POINTER(Unicast)), ("socket", Address)]

            class Adapter(ctypes.Structure):
                pass

            Adapter._fields_ = [
                ("header", ctypes.c_ulonglong), ("next", ctypes.POINTER(Adapter)),
                ("name", ctypes.c_char_p), ("unicast", ctypes.POINTER(Unicast)),
                ("anycast", ctypes.c_void_p), ("multicast", ctypes.c_void_p), ("dns", ctypes.c_void_p),
                ("suffix", wintypes.LPWSTR), ("description", wintypes.LPWSTR), ("friendly", wintypes.LPWSTR),
                ("physical", ctypes.c_ubyte * 8), ("physical_length", wintypes.ULONG),
                ("flags", wintypes.ULONG), ("mtu", wintypes.ULONG), ("type", wintypes.ULONG),
                ("status", wintypes.ULONG),
            ]
            api = ctypes.WinDLL("iphlpapi", use_last_error=True)
            api.GetAdaptersAddresses.argtypes = [wintypes.ULONG, wintypes.ULONG, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(wintypes.ULONG)]
            api.GetAdaptersAddresses.restype = wintypes.ULONG
            size = wintypes.ULONG(16384)
            for _ in range(3):
                buffer = ctypes.create_string_buffer(size.value)
                result = api.GetAdaptersAddresses(2, 0, None, buffer, ctypes.byref(size))
                if result == 111:
                    continue
                if result:
                    break
                adapter = ctypes.cast(buffer, ctypes.POINTER(Adapter))
                while adapter:
                    value = adapter.contents
                    name = (value.friendly or value.description or "").casefold()
                    virtual = any(token in name for token in ("vpn", "tun", "tap", "wireguard", "tailscale", "zerotier", "virtual", "vmware", "vethernet"))
                    address = value.unicast if value.status == 1 else None
                    while address:
                        item = address.contents
                        if item.socket.address and item.socket.length >= 8:
                            raw = ctypes.string_at(item.socket.address, 8)
                            if int.from_bytes(raw[:2], "little") == 2:
                                rows.append((virtual, str(ipaddress.IPv4Address(raw[4:8]))))
                        address = item.next
                    adapter = value.next
                break
        except (OSError, ValueError, AttributeError):
            rows = []
    if not rows:
        try:
            rows = [(False, record[4][0]) for record in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)]
        except OSError:
            pass
    result = []
    for _, value in sorted(rows, key=lambda row: row[0]):
        try:
            address = ipaddress.IPv4Address(value)
        except ipaddress.AddressValueError:
            continue
        if not (address.is_loopback or address.is_link_local or address.is_unspecified) and value not in result:
            result.append(value)
    return result or ["127.0.0.1"]


class ConnectionService:
    """Own a background local WebSocket server and one APP pairing.

    ``snapshot()`` and ``events`` are thread-safe. Nonzero output requires a
    short-lived permission lease and known APP limits. Feedback values remain
    unknown until the APP reports them; commands never fabricate hardware ACKs.
    """

    def __init__(self, *, port: int = DEFAULT_PORT, lan_ip: str = "", host: str = "0.0.0.0", heartbeat_seconds: float = 25.0,
                 output_lease_seconds: float = OUTPUT_LEASE_SECONDS):
        if not 0 <= int(port) <= 65535:
            raise ValueError("Invalid WebSocket port")
        self.events: queue.Queue[dict] = queue.Queue()
        self._lock = threading.RLock()
        self._requested_port = int(port)
        self._host = host
        self._heartbeat_seconds = max(.05, float(heartbeat_seconds))
        self._output_lease_seconds = max(.1, min(OUTPUT_LEASE_SECONDS, float(output_lease_seconds)))
        ips = discover_lan_ips()
        if lan_ip:
            address = str(ipaddress.IPv4Address(lan_ip))
            if address not in ips:
                ips.insert(0, address)
        else:
            address = ips[0]
        self._state = {
            "server_ready": False, "connected": False, "qr_url": "", "lan_ip": address,
            "port": self._requested_port, "controller_id": "", "target_id": "",
            "strength_a": None, "strength_b": None, "limit_a": None, "limit_b": None,
            "feedback_known": False, "error": "", "available_ips": ips,
            "output_allowed": False, "output_active": False, "output_channel": "",
            "output_strength": 0, "output_reason": "等待游戏状态", "output_deadline": None,
            "output_channels":{c:{"active":False,"strength":0,"deadline":None} for c in ('A','B')},
            "local_only":host in ('127.0.0.1','::1','localhost'),
        }
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_event: asyncio.Event | None = None
        self._server = None
        self._clients: dict[str, object] = {}
        self._paired_id = ""
        self._stopping = False
        self._permission_allowed = False
        self._permission_at = 0.
        self._output_epoch = 0
        self._desired_channels = {c:None for c in ('A','B')}
        self._channel_epochs = {c:0 for c in ('A','B')}
        self._wire = {c:self._empty_wire() for c in ('A','B')}
        self._frame_serial=0
        self._baseline_epoch=-1
        self._hard_limits = {"A": 100, "B": 100}
        self._command_lock = None
        self._zeroed_epoch = -1

    def snapshot(self) -> dict:
        with self._lock:
            return deepcopy(self._state)

    @staticmethod
    def _empty_wire():return dict(active=False,strength=0,next_at=0.,last_seq=-1,epoch=-1)

    def _invalidate_locked(self):
        self._output_epoch+=1
        for c in ('A','B'):self._desired_channels[c]=None;self._channel_epochs[c]+=1

    def _channel_state(self,reason=None):
        with self._lock:
            channels={c:dict(active=w['active'],strength=w['strength'],deadline=(self._desired_channels[c] or {}).get('expires_at')) for c,w in self._wire.items()}
            active=''.join(c for c in ('A','B') if channels[c]['active'])
            values=dict(output_channels=channels,output_active=bool(active),output_channel=active,output_strength=max(w['strength'] for w in self._wire.values()),
                        output_deadline=max((x['deadline'] or 0 for x in channels.values()),default=0) or None)
            if reason is not None:values['output_reason']=reason
            self._state.update(values)

    def _change(self, event: str, **values) -> None:
        with self._lock:
            self._state.update(values)
            self.events.put({"event": event, **deepcopy(values)})

    def _qr(self) -> str:
        state = self._state
        return ("https://www.dungeon-lab.com/app-download.php#DGLAB-SOCKET#"
                f"ws://{state['lan_ip']}:{state['port']}/{state['controller_id']}")

    def set_lan_ip(self, address: str) -> bool:
        try:
            address = str(ipaddress.IPv4Address(address))
        except ipaddress.AddressValueError:
            return False
        with self._lock:
            if address not in self._state["available_ips"]:
                return False
            self._state["lan_ip"] = address
            url = self._qr() if self._state["server_ready"] else ""
            self._change("address", lan_ip=address, qr_url=url)
        return True

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stopping = False
            self._permission_allowed = False
            self._permission_at = 0.
            self._invalidate_locked()
            self._wire={c:self._empty_wire() for c in ('A','B')};self._baseline_epoch=-1
            self._state.update(server_ready=False, connected=False, error="", qr_url="", controller_id=str(uuid.uuid4()), target_id="", feedback_known=False,
                               strength_a=None, strength_b=None, limit_a=None, limit_b=None,
                               output_allowed=False, output_active=False, output_channel="", output_strength=0,
                               output_reason="等待游戏状态", output_deadline=None)
            self._channel_state()
            self._thread = threading.Thread(target=self._thread_main, name="SiNiSistarDGLabSocket", daemon=True)
            self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stopping = True
        with self._lock:
            self._permission_allowed = False
            self._invalidate_locked()
        loop, event = self._loop, self._stop_event
        if loop is not None and event is not None and loop.is_running():
            loop.call_soon_threadsafe(event.set)
        thread = self._thread
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout)

    def emergency_zero(self) -> bool:
        self.set_output_permission(False, "紧急归零", _force_zero=True)
        loop = self._loop
        if not self.snapshot()["connected"] or loop is None or not loop.is_running():
            return False
        return True

    def _permission_valid_locked(self, now=None) -> bool:
        return bool(self._permission_allowed and not self._stopping and self._state["connected"]
                    and self._state["feedback_known"] and
                    (time.monotonic() if now is None else now) - self._permission_at <= self._output_lease_seconds)

    def set_output_permission(self, allowed: bool, reason: str = "", *, hard_limits=None, _force_zero=False) -> bool:
        """Refresh a <=600ms lease, or synchronously invalidate queued work."""
        with self._lock:
            if hard_limits is not None:
                for channel in ("A", "B"):
                    if channel in hard_limits:
                        try:
                            self._hard_limits[channel] = max(0, min(100, int(hard_limits[channel])))
                        except (ValueError, TypeError, OverflowError):
                            self._hard_limits[channel] = 0
            permitted = bool(allowed and self._state["connected"] and self._state["feedback_known"] and not self._stopping)
            was_allowed = self._permission_allowed
            if permitted:
                if not was_allowed:self._output_epoch+=1
                self._permission_at = time.monotonic()
                self._permission_allowed = True
                if not was_allowed or (not self._state["output_active"] and self._state["output_reason"] != (reason or "受伤反馈就绪")):
                    self._change("output_permission", output_allowed=True, output_reason=reason or "受伤反馈就绪")
                return True
            self._permission_allowed = False
            needs_zero = was_allowed or any(self._desired_channels.values()) or any(w['active'] for w in self._wire.values()) or _force_zero
            if needs_zero:
                self._invalidate_locked()
            epoch = self._output_epoch
            why = reason or "输出条件未满足"
            if was_allowed or self._state["output_reason"] != why:
                self._change("output_permission", output_allowed=False, output_reason=why)
        if needs_zero:
            loop = self._loop
            if loop is not None and loop.is_running():
                try:
                    asyncio.run_coroutine_threadsafe(self._cancel_output(epoch, why), loop)
                except RuntimeError:
                    pass
        return False

    def play_feedback(self, channel: str, strength: int, duration: float, points, frequency: int, hard_limit: int) -> bool:
        """Legacy one-shot API; replacement is limited to the chosen channel."""
        try:
            if channel not in ("A", "B") or isinstance(strength, bool):
                return False
            duration = float(duration)
            strength, hard_limit = int(strength), int(hard_limit)
            if not math.isfinite(duration) or not .1 <= duration <= 5 or not 0 < strength <= 100 or not 0 <= hard_limit <= 100:
                return False
            values = tuple(float(value) for value in points)
            if not 2 <= len(values) <= 16 or not all(math.isfinite(value) and 0 <= value <= 1 for value in values):
                return False
            encoded_frequency = frequency_byte(frequency)
        except (ValueError, TypeError, OverflowError):
            return False
        with self._lock:
            if not self._permission_valid_locked():
                return False
            cap = min(hard_limit, self._hard_limits[channel], self._state["limit_a" if channel == "A" else "limit_b"], 100)
            if cap <= 0:
                return False
            now=time.monotonic();self._channel_epochs[channel]+=1;self._frame_serial+=1
            self._desired_channels[channel] = {"epoch": self._output_epoch, "channel_epoch":self._channel_epochs[channel],"seq":self._frame_serial,"channel": channel, "strength": min(strength, cap),
                                      "duration": duration, "points": values, "frequency": encoded_frequency,
                                      "frequency_hz": float(frequency), "hard_limit": hard_limit,
                                      "target_id": self._paired_id,"kind":"legacy","start_at":now,"expires_at":now+duration}
        return True

    def submit_plan(self,channels,*,generated_at):
        """Atomically replace A/B latest frames. No frame history is retained."""
        try:
            now=time.monotonic();generated_at=float(generated_at)
            if not math.isfinite(generated_at) or not 0<=now-generated_at<PLAN_LEASE_SECONDS:raise ValueError('Stale plan')
            if not isinstance(channels,dict) or set(channels)!= {'A','B'}:raise ValueError('Both channels are required')
            clean={}
            for c,r in channels.items():
                if r is None:clean[c]=None;continue
                peak=float(r['peak']);samples=tuple(float(x) for x in r['samples']);freq=tuple(float(x) for x in r['frequencies'])
                if not math.isfinite(peak) or not 0<peak<=100 or len(samples)!=4 or len(freq)!=4:raise ValueError('Invalid frame')
                if not all(math.isfinite(x) and 0<=x<=peak+1e-6 for x in samples):raise ValueError('Invalid amplitudes')
                for hz in freq:frequency_byte(hz)
                clean[c]=dict(kind='stream',peak=peak,samples=samples,frequencies=freq,expires_at=generated_at+PLAN_LEASE_SECONDS)
        except (ValueError,TypeError,KeyError,OverflowError):
            self.set_output_permission(False,'输出计划无效');return False
        with self._lock:
            if not self._permission_valid_locked():return False
            for c,r in clean.items():
                previous=self._desired_channels[c]
                if r is None:
                    if previous is not None:self._channel_epochs[c]+=1
                    self._desired_channels[c]=None;continue
                if previous is None or previous.get('kind')!='stream':self._channel_epochs[c]+=1
                self._frame_serial+=1
                r.update(epoch=self._output_epoch,channel_epoch=self._channel_epochs[c],seq=self._frame_serial,channel=c,target_id=self._paired_id)
                self._desired_channels[c]=r
        return True

    def stop_channel(self,channel):
        if channel not in ('A','B'):return False
        with self._lock:
            self._desired_channels[channel]=None;self._channel_epochs[channel]+=1
        return True

    def _thread_main(self) -> None:
        try:
            asyncio.run(self._run())
        except Exception as exc:
            if not self._stopping:
                self._change("error", error=f"DG-LAB 服务异常：{exc}")
        finally:
            self._loop = self._stop_event = self._server = None
            self._paired_id = ""
            self._clients.clear()
            with self._lock:self._wire={c:self._empty_wire() for c in ('A','B')};self._invalidate_locked();self._channel_state()
            self._change("stopped", server_ready=False, connected=False, qr_url="", target_id="", feedback_known=False,
                         strength_a=None, strength_b=None, limit_a=None, limit_b=None,
                         output_allowed=False, output_active=False, output_channel="", output_strength=0,
                         output_deadline=None, output_reason="服务已停止")

    async def _run(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._stop_event = asyncio.Event()
        self._command_lock = asyncio.Lock()
        try:
            self._server = await websockets.serve(self._handler, self._host, self._requested_port,
                                                   ping_interval=20, ping_timeout=20, close_timeout=1,
                                                   max_size=2048, max_queue=16)
        except OSError as exc:
            self._change("error", error=f"无法监听 DG-LAB 端口 {self._requested_port}：{exc}")
            return
        with self._lock:
            self._state["port"] = self._server.sockets[0].getsockname()[1]
            self._state["server_ready"] = True
            self._change("ready", qr_url=self._qr(), server_ready=True, port=self._state["port"])
        heartbeat = asyncio.create_task(self._heartbeat())
        output = asyncio.create_task(self._output_loop())
        if self._stopping:
            self._stop_event.set()
        stop_wait = asyncio.create_task(self._stop_event.wait())
        try:
            done, _ = await asyncio.wait((stop_wait, output), return_when=asyncio.FIRST_COMPLETED)
            if output in done and not self._stopping:
                error = output.exception()
                raise RuntimeError(f"Output worker stopped: {error or 'unexpected exit'}")
        finally:
            stop_wait.cancel()
            output.cancel()
            await asyncio.gather(output, stop_wait, return_exceptions=True)
            try:
                async with self._command_lock:
                    await asyncio.wait_for(self._zero(), timeout=.5)
            except (asyncio.TimeoutError, websockets.ConnectionClosed):
                pass
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)
            self._server.close()
            await self._server.wait_closed()

    async def _send(self, socket, packet: dict) -> None:
        await socket.send(json.dumps(packet, separators=(",", ":")))

    async def _reply(self, socket, kind: str, first: str, second: str, message: str) -> None:
        await self._send(socket, {"type": kind, "clientId": first, "targetId": second, "message": message})

    async def _handler(self, websocket) -> None:
        connection_id = str(uuid.uuid4())
        self._clients[connection_id] = websocket
        try:
            await self._reply(websocket, "bind", connection_id, "", "targetId")
            async for raw in websocket:
                try:
                    packet = json.loads(raw)
                    if not isinstance(packet, dict):
                        raise ValueError
                except (ValueError, TypeError, UnicodeDecodeError):
                    await self._reply(websocket, "error", connection_id, "", "403")
                    continue
                kind = packet.get("type")
                if kind == "heartbeat":
                    continue
                first, second = packet.get("clientId"), packet.get("targetId")
                controller = self.snapshot()["controller_id"]
                if kind == "bind":
                    if first != controller or second != connection_id or packet.get("message") not in ("DGLAB", "targetId"):
                        await self._reply(websocket, "bind", str(first or ""), str(second or ""), "401")
                    elif self._paired_id and self._paired_id != connection_id:
                        await self._reply(websocket, "bind", first, second, "400")
                    else:
                        newly_connected = self._paired_id != connection_id
                        self._paired_id = connection_id
                        await self._reply(websocket, "bind", controller, connection_id, "200")
                        if newly_connected:
                            with self._lock:
                                self._permission_allowed = False
                                self._invalidate_locked();self._wire={c:self._empty_wire() for c in ('A','B')};self._baseline_epoch=-1;self._channel_state()
                            self._change("connected", connected=True, target_id=connection_id, feedback_known=False,
                                         strength_a=None, strength_b=None, limit_a=None, limit_b=None, error="",
                                         output_allowed=False, output_active=False, output_strength=0,
                                         output_channel="", output_deadline=None, output_reason="等待游戏状态")
                elif kind == "msg":
                    if connection_id != self._paired_id or first != controller or second != connection_id:
                        await self._reply(websocket, "error", str(first or ""), str(second or ""), "402")
                        continue
                    feedback = packet.get("message")
                    if not isinstance(feedback, str):
                        continue
                    match = _FEEDBACK.fullmatch(feedback)
                    if match:
                        values = [int(value) for value in match.groups()]
                        if all(0 <= value <= 200 for value in values):
                            self._change("feedback", strength_a=values[0], strength_b=values[1], limit_a=values[2], limit_b=values[3], feedback_known=True)
                    elif feedback.startswith("feedback-") and len(feedback) < 40:
                        self.events.put({"event": "app_feedback", "message": feedback})
                    # No remote controller commands or pulses are forwarded.
        except websockets.ConnectionClosed:
            pass
        finally:
            self._clients.pop(connection_id, None)
            if connection_id == self._paired_id:
                self._paired_id = ""
                with self._lock:
                    self._permission_allowed = False
                    self._invalidate_locked();self._wire={c:self._empty_wire() for c in ('A','B')};self._baseline_epoch=-1;self._channel_state()
                self._change("disconnected", connected=False, target_id="", feedback_known=False,
                             strength_a=None, strength_b=None, limit_a=None, limit_b=None,
                             output_allowed=False, output_active=False, output_strength=0, output_channel="",
                             output_deadline=None, output_reason="APP 已断开")

    async def _zero(self) -> None:
        target_id=self._paired_id;websocket=self._clients.get(target_id)
        if not target_id or websocket is None:return
        try:
            for command in ZERO_COMMANDS:
                if target_id!=self._paired_id:return
                await asyncio.wait_for(self._reply(websocket,"msg",self.snapshot()["controller_id"],target_id,command),timeout=.15)
                self.events.put(dict(event="command_sent",command=command,epoch=self._output_epoch))
            with self._lock:
                previous=[c for c,w in self._wire.items() if w["active"]]
                self._wire={c:self._empty_wire() for c in ("A","B")}
                self._zeroed_epoch=self._output_epoch;self._channel_state()
            for c in previous:self.events.put(dict(event="feedback_end",channel=c,reason="归零"))
            self.events.put(dict(event="zero_sent"))
        except (websockets.ConnectionClosed,asyncio.TimeoutError):
            self.events.put(dict(event="zero_failed"))

    def _channel_cap(self,channel):
        with self._lock:
            device=self._state["limit_a" if channel=="A" else "limit_b"]
            return min(100,self._hard_limits[channel],device if device is not None else 0)

    def _frame_valid(self,frame):
        if frame is None:return False
        with self._lock:
            current=self._desired_channels[frame["channel"]]
            return bool(self._permission_valid_locked() and frame["epoch"]==self._output_epoch
                        and frame["channel_epoch"]==self._channel_epochs[frame["channel"]]
                        and current and current["seq"]==frame["seq"]
                        and frame["target_id"]==self._paired_id and time.monotonic()<frame["expires_at"])

    async def _frame_command(self,frame,command,strength):
        async def guarded():
            # Recheck inside the scheduled send task: pause/configuration may
            # invalidate the frame after it was selected by the network worker.
            if not self._frame_valid(frame) or strength>self._channel_cap(frame["channel"]):return False
            socket=self._clients.get(frame["target_id"])
            if socket is None:return False
            await self._reply(socket,"msg",self.snapshot()["controller_id"],frame["target_id"],command)
            return True
        try:
            sent=await asyncio.wait_for(guarded(),timeout=.15)
            if sent:
                self._zeroed_epoch=-1
                self.events.put(dict(event="command_sent",command=command,channel=frame["channel"],epoch=frame["epoch"],sequence=frame["seq"]))
            return sent
        except (websockets.ConnectionClosed,asyncio.TimeoutError):
            self.set_output_permission(False,"APP 写入失败");return False

    async def _zero_channel(self,channel,reason):
        target=self._paired_id;socket=self._clients.get(target)
        if not target or socket is None:return
        code="1" if channel=="A" else "2"
        try:
            for command in (f"strength-{code}+2+0",f"clear-{code}"):
                if target!=self._paired_id:return
                await asyncio.wait_for(self._reply(socket,"msg",self.snapshot()["controller_id"],target,command),timeout=.15)
                self.events.put(dict(event="command_sent",command=command,channel=channel,epoch=self._output_epoch))
            with self._lock:
                if target==self._paired_id:self._wire[channel]=self._empty_wire();self._channel_state()
            self.events.put(dict(event="feedback_end",channel=channel,reason=reason))
        except (websockets.ConnectionClosed,asyncio.TimeoutError):
            self.set_output_permission(False,"通道归零失败")

    async def _cancel_output(self,epoch,reason):
        if self._command_lock is None:return
        async with self._command_lock:
            with self._lock:
                if epoch!=self._output_epoch:return
            if self._zeroed_epoch!=epoch:await self._zero()
            self._channel_state(reason)
            self.events.put(dict(event="output_stopped",reason=reason))

    async def _output_loop(self):
        """Independent channels, latest-only frames, no catch-up or repetition."""
        while not self._stopping:
            now=time.monotonic()
            with self._lock:
                expired=self._permission_allowed and now-self._permission_at>self._output_lease_seconds
            if expired:self.set_output_permission(False,"输出更新超时")
            async with self._command_lock:
                with self._lock:
                    epoch=self._output_epoch;allowed=self._permission_valid_locked()
                if allowed and self._baseline_epoch!=epoch:
                    await self._zero()
                    with self._lock:
                        if epoch==self._output_epoch:self._baseline_epoch=epoch
                elif not allowed and any(w['active'] for w in self._wire.values()):
                    await self._zero()
                for channel in ("A","B"):
                    with self._lock:
                        frame=deepcopy(self._desired_channels[channel]);wire=deepcopy(self._wire[channel])
                    if not self._frame_valid(frame):
                        if frame and time.monotonic()>=frame["expires_at"]:
                            with self._lock:
                                current=self._desired_channels[channel]
                                if current and current["seq"]==frame["seq"]:
                                    self._desired_channels[channel]=None;self._channel_epochs[channel]+=1
                        if wire["active"]:await self._zero_channel(channel,"计划结束 / 失效")
                        continue
                    cap=self._channel_cap(channel)
                    if cap<=0:
                        if wire["active"]:await self._zero_channel(channel,"通道上限为零")
                        continue
                    generation=(frame["epoch"],frame["channel_epoch"])
                    if wire["active"] and wire["epoch"]!=generation:
                        await self._zero_channel(channel,"通道反馈替换");wire=self._empty_wire()
                    code="1" if channel=="A" else "2"
                    # Device/app cap decreases take effect even between frames.
                    if wire["active"] and wire["strength"]>cap:
                        if await self._frame_command(frame,f"strength-{code}+2+{cap}",cap):
                            with self._lock:self._wire[channel]["strength"]=cap;self._channel_state()
                            wire["strength"]=cap
                    now=time.monotonic()
                    if now<wire["next_at"]:continue
                    if frame["kind"]=="stream":
                        if wire["last_seq"]==frame["seq"]:continue
                        strength=min(cap,math.ceil(frame["peak"]))
                        encoded=stream_frame(frame["samples"],frame["frequencies"],strength)
                        index=-1
                    else:
                        index=int((now-frame["start_at"])/FRAME_SECONDS)
                        if wire["last_seq"]==frame["seq"] and wire.get("legacy_index",-1)>=index:continue
                        strength=min(cap,frame["strength"],frame["hard_limit"])
                        encoded=envelope_frame(frame["points"],frame["frequency"],index,frame["duration"])
                    was_active=wire["active"]
                    if strength!=wire["strength"]:
                        if not await self._frame_command(frame,f"strength-{code}+2+{strength}",strength):continue
                        with self._lock:
                            self._wire[channel].update(active=True,strength=strength,epoch=generation)
                            self._channel_state()
                    command=f"pulse-{channel}:"+json.dumps([encoded],separators=(",",":"))
                    if await self._frame_command(frame,command,strength):
                        with self._lock:
                            self._wire[channel].update(active=True,strength=strength,epoch=generation,last_seq=frame["seq"],
                                                       next_at=time.monotonic()+FRAME_SECONDS,legacy_index=index)
                            self._channel_state("Pulse 持续计划")
                        if not was_active:self.events.put(dict(event="feedback_started",channel=channel,strength=strength))
            await asyncio.sleep(.01)

    async def _heartbeat(self) -> None:
        while True:
            await asyncio.sleep(self._heartbeat_seconds)
            for connection_id, websocket in list(self._clients.items()):
                target = self.snapshot()["controller_id"] if connection_id == self._paired_id else ""
                try:
                    await self._reply(websocket, "heartbeat", connection_id, target, "200")
                except websockets.ConnectionClosed:
                    pass
