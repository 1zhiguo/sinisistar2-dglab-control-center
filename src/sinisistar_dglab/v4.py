"""DG-LAB 4 hub with separate, latest-only Coyote and OVC output routes.

Wire negotiation/readiness/zero barriers are adapted from the user's Ricca
GPL-3.0 transport. Output authorization is not shared with the reference app.
One descriptor is four 25ms samples; no long or catch-up queue is produced.
"""
from __future__ import annotations

import asyncio,json,math,queue,threading,time
from copy import deepcopy
from ._v4_hub import DGLabV4Hub
from ._v4_protocol import channel_block_reason,channel_intensity_limit,protocol_strength,FRAME_MS,LEASE_MS
from .dglab import frequency_byte,OUTPUT_LEASE_SECONDS,PLAN_LEASE_SECONDS

ROLES={'pulse':'coyote','coyote':'coyote','vibration':'ovc','ovc':'ovc'}

class V4RouteService:
    """ConnectionService-compatible facade for one explicitly selected slot."""
    def __init__(self,owner,role):
        self.owner=owner;self.role=role;self.events=queue.Queue();self._lock=threading.RLock()
        self._allowed=False;self._permission_at=0.;self._epoch=0;self._serial=0
        self._desired={c:None for c in 'AB'};self._hard_limits={c:0 for c in 'AB'}
        self._wire={c:dict(active=False,strength=0,deadline=None) for c in 'AB'}
        self._reason='输出已暂停'
        self._error=''
        self._rpc_error=''
        self._selection_epoch_requested=0
        self._wake_event=None;self._wake_scheduled=False;self._loop_passes=0

    def wake_output(self):
        """Coalesce cross-thread notifications; never queue a waveform here."""
        route=self.route
        with self._lock:
            if self._wake_event is None or self._wake_scheduled or not route._loop or not route._loop.is_running():return
            self._wake_scheduled=True
        def wake():
            with self._lock:self._wake_scheduled=False;event=self._wake_event
            if event:event.set()
        route._loop.call_soon_threadsafe(wake)

    @property
    def route(self):return self.owner._hub.channel(self.role)

    def snapshot(self):
        route=self.route;device=route._selected_device();props=device.get('props') or {};state=device.get('slotState') or {}
        with self._lock:channels=deepcopy(self._wire);reason=self._reason
        selecting=route._selection_epoch<self._selection_epoch_requested
        connected=bool(route.connected and route._baseline_ready and not selecting)
        if not connected:
            for value in channels.values():value.update(active=False,strength=0,deadline=None)
        limit=lambda c:channel_intensity_limit(device,c)
        known=connected and all(type(limit(c)) in (int,float) and math.isfinite(limit(c)) for c in 'AB')
        strengths={c:props.get('intensity'+c) for c in 'AB'}
        return dict(server_ready=route.server_ready,connected=connected,feedback_known=known,
                    controller_id=route.controller_id,target_id=route.target_id,port=route.port,lan_ip=route.lan_ip,
                    qr_url=route.qr_url,available_ips=list(route.available_lan_ips),local_only=self.owner.local_only,
                    strength_a=strengths['A'],strength_b=strengths['B'],limit_a=limit('A'),limit_b=limit('B'),
                    output_channels=channels,output_active=any(x['active'] for x in channels.values()),
                    output_channel=''.join(c for c in 'AB' if channels[c]['active']),output_strength=max(x['strength'] for x in channels.values()),
                    output_deadline=max((x['deadline'] or 0 for x in channels.values()),default=0),output_reason=reason,
                    protocol='v4',device_type=route.device_type,selected_client_id=route.selected_client_id,
                    selected_slot_id=route.selected_slot_id,channel_a_reason=channel_block_reason(device,'A'),
                    channel_b_reason=channel_block_reason(device,'B'),readiness_failed=route._readiness_failure_latched and not selecting,selection_pending=selecting,
                    limit_source='device-range' if device.get('type')=='OVC_1' else 'app',
                    error=self._rpc_error or self._error or self.owner._error,output_loop_passes=self._loop_passes)

    def _invalidate(self,reason='输出已暂停'):
        with self._lock:
            self._allowed=False;self._epoch+=1;self._desired={c:None for c in 'AB'};self._reason=reason
        route=self.route
        if route._loop and route._loop.is_running():
            # Advance the underlying RPC generation as well as the planner
            # epoch; a late cancellation from the old lease cannot cancel a
            # freshly resumed electrical stream.
            route._loop.call_soon_threadsafe(route._request_emergency_in_loop)
        self.wake_output()

    def set_output_permission(self,allowed,reason='',hard_limits=None):
        maximum=200 if self.role=='ovc' else 100
        if hard_limits is not None:
            try:
                clean={c:max(0,min(maximum,float(hard_limits[c]))) for c in 'AB'}
                if not all(math.isfinite(v) for v in clean.values()):raise ValueError('Nonfinite cap')
            except (KeyError,TypeError,ValueError,OverflowError):allowed=False;clean={c:0 for c in 'AB'}
            with self._lock:self._hard_limits=clean
        route=self.route
        accepted=bool(allowed and route.connected and route._baseline_ready and not route._paused and
                      not route._global_emergency_stop.is_set() and not route._route_zero_pending())
        if not accepted:
            if self._allowed:self._invalidate(reason)
            else:
                with self._lock:self._reason=reason or '等待设备就绪'
            return False
        with self._lock:self._allowed=True;self._permission_at=time.monotonic();self._reason=reason
        # Only this worker uses the protocol's auto-enabled guard; never call
        # Ricca's repeating waveform queue/update API.
        route._auto_enabled=True
        # submit_plan supplies the wake for renewed permission. An initial
        # grant alone has no descriptor to send.
        return True

    def submit_plan(self,frames,generated_at=None):
        now=time.monotonic();generated_at=now if generated_at is None else generated_at
        maximum=200 if self.role=='ovc' else 100
        try:
            if set(frames)!=set('AB') or not math.isfinite(generated_at) or not 0<=now-generated_at<PLAN_LEASE_SECONDS:raise ValueError('Expired plan')
            clean={}
            for c in 'AB':
                value=frames[c]
                if value is None:clean[c]=None;continue
                peak=float(value['peak']);samples=tuple(float(v) for v in value['samples']);freq=tuple(float(v) for v in value['frequencies'])
                if not math.isfinite(peak) or not 0<peak<=maximum or len(samples)!=4 or len(freq)!=4:raise ValueError('Invalid frame')
                if not all(math.isfinite(v) and 0<=v<=peak for v in samples):raise ValueError('Invalid samples')
                for hz in freq:frequency_byte(hz)
                clean[c]=dict(peak=peak,samples=samples,frequencies=freq,expires_at=generated_at+PLAN_LEASE_SECONDS)
        except (KeyError,TypeError,ValueError,OverflowError):self._invalidate('无效或过期波形');return False
        with self._lock:
            if not self._allowed or now-self._permission_at>=OUTPUT_LEASE_SECONDS:return False
            route=self.route
            for c,value in clean.items():
                if value is not None:
                    self._serial+=1;value.update(seq=self._serial,epoch=self._epoch,selection=route._selection_epoch,
                                                generation=route._generation,client=route.selected_client_id,slot=route.selected_slot_id)
            self._desired=clean
        self.wake_output()
        return True

    def stop_channel(self,channel):
        if channel not in 'AB' or len(channel)!=1:return
        with self._lock:self._desired[channel]=None
        self.wake_output()
        route=self.route
        if route._loop and route._loop.is_running() and route.selected_slot_id:
            route._loop.call_soon_threadsafe(route._start_channel_zero,route.selected_client_id,route.selected_slot_id,1 if channel=='B' else 0)

    def emergency_zero(self):
        self._invalidate('紧急归零');self.route.emergency_stop()

    def latch_emergency_stop(self):
        self._invalidate('急停已锁定');self.route.latch_global_emergency_stop()

    def clear_emergency_stop(self):
        self._invalidate('正在解除急停');self.route.clear_global_emergency_stop()

    def stop(self):
        self._invalidate('设备已断开');self.route.stop()

    def _valid(self,frame,channel,now):
        route=self.route
        with self._lock:
            current=self._desired[channel]
            return bool(frame and current and current['seq']==frame['seq'] and frame['epoch']==self._epoch and self._allowed
                        and 0<=now-self._permission_at<OUTPUT_LEASE_SECONDS and now<frame['expires_at']
                        and route.connected and route._baseline_ready and route._auto_enabled and not route._paused
                        and not route._global_emergency_stop.is_set() and frame['selection']==route._selection_epoch
                        and frame['generation']==route._generation and frame['client']==route.selected_client_id
                        and frame['slot']==route.selected_slot_id and not channel_block_reason(route._selected_device(),channel))

    def _strength(self,frame,channel):
        route=self.route;device=route._selected_device();maximum=channel_intensity_limit(device,channel)
        if type(maximum) not in (int,float) or not math.isfinite(maximum):return 0
        with self._lock:cap=min(self._hard_limits[channel],maximum)
        requested=frame['peak'] if self.role=='ovc' else math.ceil(frame['peak'])
        return protocol_strength(requested,cap,route.device_type)

    def _encode(self,frame):
        frequency='0A'*4 if self.role=='ovc' else ''.join(f'{frequency_byte(hz):02X}' for hz in frame['frequencies'])
        # Preserve shape when a device cap or OVC quantization lowers strength.
        amplitude=''.join(f'{max(0,min(100,round(value/frame["peak"]*100))):02X}' for value in frame['samples'])
        return frequency+amplitude

    async def _output_loop(self,route):
        self._wake_event=asyncio.Event()
        last_seq={c:-1 for c in 'AB'};last_send={c:0. for c in 'AB'};active={c:False for c in 'AB'}
        while True:
            self._wake_event.clear();now=time.monotonic();self._loop_passes+=1
            for req_id,pending in list(route._pending.items()):
                if pending['deadline']<now:
                    route._finish_pending(req_id,error=TimeoutError('V4 response timed out'))
                    if pending['method']=='device.op' and not pending['safety']:
                        route._resync_after_timeout()
                        self._invalidate('APP 输出确认超时');route._request_emergency_in_loop()
                        self._error='V4 APP 输出任务确认超时';self.events.put(dict(event='error',error=self._error,recoverable=True))
            with self._lock:
                expired=self._allowed and now-self._permission_at>=OUTPUT_LEASE_SECONDS
            if expired:self._invalidate('输出授权已过期')
            for channel in 'AB':
                # Submitted descriptors are immutable and replaced atomically.
                with self._lock:frame=self._desired[channel]
                code=1 if channel=='B' else 0
                valid=self._valid(frame,channel,now)
                strength=self._strength(frame,channel) if valid else 0
                if not valid or strength<=0:
                    if active[channel]:route._start_channel_zero(route.selected_client_id,route.selected_slot_id,code)
                    active[channel]=False
                    with self._lock:self._wire[channel]=dict(active=False,strength=0,deadline=None)
                    continue
                if route._channel_zero_pending(route.selected_client_id,route.selected_slot_id,code):continue
                try:
                    if not self._valid(frame,channel,time.monotonic()):continue
                    guard=lambda:self._valid(frame,channel,time.monotonic()) and strength<=self._strength(frame,channel)
                    with self._lock:previous=self._wire[channel]['strength']
                    if active[channel] and previous>strength:
                        changed=await route._rpc('device.op',dict(s=frame['slot'],t=4,c=code,p=1,d=LEASE_MS,v=strength,im=True),guard=guard)
                        if changed is not False:
                            with self._lock:self._wire[channel]['strength']=strength
                    if last_seq[channel]==frame['seq'] or now-last_send[channel]<FRAME_MS/1000:continue
                    sent=await route._rpc('device.op',dict(s=frame['slot'],t=4,c=code,p=1,d=LEASE_MS,v=strength,im=True),guard=guard)
                    if sent is False:continue
                    active[channel]=True  # Includes a revoked half-written pair.
                    if not self._valid(frame,channel,time.monotonic()):continue
                    encoded=self._encode(frame)
                    sent=await route._rpc('device.op',dict(s=frame['slot'],t=0,c=code,p=1,d=FRAME_MS,v=[encoded],im=True),guard=guard)
                    if sent is False:continue
                    last_seq[channel]=frame['seq'];last_send[channel]=time.monotonic();active[channel]=True
                    with self._lock:self._wire[channel]=dict(active=True,strength=strength,deadline=frame['expires_at'])
                    self.events.put(dict(event='command_sent',command='pulse-'+channel+':'+json.dumps([encoded]),channel=channel,protocol='v4',role=self.role,strength=strength))
                except Exception as error:
                    self._invalidate('V4 输出链路异常');route._request_emergency_in_loop()
                    self._error=str(error)[:240];self.events.put(dict(event='error',error=self._error,recoverable=route._resync_required));break
            # Idle routes need no poll. Wake on new plans/status, or the next
            # frame/lease/RPC deadline. The 20ms floor avoids Windows asyncio
            # repeatedly servicing timers inside its 15.6ms clock look-ahead.
            now=time.monotonic();deadlines=[now+.25]
            with self._lock:
                if self._allowed:deadlines.append(self._permission_at+OUTPUT_LEASE_SECONDS)
                for c,frame in self._desired.items():
                    if frame and frame['expires_at']>now:
                        deadlines.append(frame['expires_at'])
                        if frame['seq']!=last_seq[c] and self._valid(frame,c,now):deadlines.append(last_send[c]+FRAME_MS/1000)
            deadlines.extend(p['deadline'] for p in list(route._pending.values()))
            delay=max(.02,min(deadlines)-now)
            try:await asyncio.wait_for(self._wake_event.wait(),delay)
            except asyncio.TimeoutError:pass

class V4ConnectionService:
    """Shared V4 APP Socket with explicit independent Coyote/OVC slot selection."""
    def __init__(self,*,port=9998,host='0.0.0.0',lan_ip=''):
        self.host=host;self.local_only=host in ('127.0.0.1','::1','localhost');self.events=queue.Queue();self._wire_events=queue.Queue();self._error=''
        self._hub=DGLabV4Hub(self._wire_events,port=port,lan_ip=lan_ip);self._hub.host=host
        if self.local_only:self._hub.lan_ip=lan_ip or '127.0.0.1'
        self._routes={role:V4RouteService(self,role) for role in ('coyote','ovc')}
        for role,adapter in self._routes.items():self._hub.channel(role).stream_adapter=adapter

    def channel(self,role):return self._routes[ROLES[role]]
    def start(self):self._hub.start()
    def stop(self):
        for route in self._routes.values():route._invalidate('服务已停止')
        self._hub.stop()
    def emergency_zero(self):
        for route in self._routes.values():route.emergency_zero()
    def select_device(self,role,client_id,slot_id):
        adapter=self.channel(role);adapter._invalidate('等待新设备基线');adapter._error='';adapter._rpc_error=''
        adapter._selection_epoch_requested=adapter.route._selection_epoch+1
        accepted=self._hub.select_device(ROLES[role],client_id,slot_id)
        if not accepted:adapter._selection_epoch_requested=adapter.route._selection_epoch
        return accepted
    def set_lan_ip(self,address):return self._hub.set_lan_ip(address)
    def refresh_lan_ips(self):self._hub.refresh_lan_ips()
    def devices_snapshot(self):return self._hub.devices_snapshot()
    def snapshot(self):
        # Bound a GUI read even if an APP is continuously publishing patches.
        for _ in range(256):
            try:
                _,event=self._wire_events.get_nowait();role=event.get('role')
                if event['event'] in ('error','server_error'):
                    message=event.get('detail') or event.get('error') or event.get('reason') or 'V4 连接异常'
                    if role in self._routes:
                        self._routes[role]._error=message
                        if event.get('rpc_error'):self._routes[role]._rpc_error='DG-LAB APP：'+event['rpc_error']
                    else:self._error=message
                elif event['event']=='connected' and role in self._routes:self._routes[role]._error=self._routes[role]._rpc_error=''
                self.events.put(deepcopy(event))
                if role in self._routes:self._routes[role].events.put(deepcopy(event))
            except queue.Empty:break
        hub=self._hub
        return dict(server_ready=hub.server_ready,app_connected=hub.app_connected,connected=any(r.route.connected for r in self._routes.values()),
                    protocol='v4',controller_id=hub.controller_id,port=hub.port,lan_ip=hub.lan_ip,available_ips=list(hub.available_lan_ips),
                    qr_url=hub.qr_url,local_only=self.local_only,devices=hub.devices_snapshot(),error=self._error,
                    coyote=self.channel('coyote').snapshot(),ovc=self.channel('ovc').snapshot())
