"""Five-minute read-only Windows/PresentMon/NVML capture of existing processes.

No injection, device commands, settings writes, or application restart. CPU is
reported both per logical core and as a fraction of total logical capacity.
GPU watts/energy refer to the entire board, never a per-process estimate.
"""
import argparse,ctypes as C,json,os,re,subprocess,time
from ctypes import wintypes as W
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RUNTIME=ROOT/'tools/profiling-runtime'
HIDDEN=dict(creationflags=subprocess.CREATE_NO_WINDOW)

def stamp():return datetime.now(timezone.utc).isoformat()

def source_name(path):
    try:return str(path.relative_to(ROOT))
    except ValueError:return str(path)

class Memory(C.Structure):
    _fields_=[('cb',W.DWORD),('faults',W.DWORD)]+[(n,C.c_size_t) for n in
        ('peak_ws','ws','peak_paged','paged','peak_nonpaged','nonpaged','pagefile','peak_pagefile','private')]

class Io(C.Structure):
    _fields_=[(n,C.c_ulonglong) for n in ('read_ops','write_ops','other_ops','read_bytes','write_bytes','other_bytes')]

class Process:
    def __init__(self,pid):
        self.pid=pid;self.last=None;self.k=C.WinDLL('kernel32',use_last_error=True);self.p=C.WinDLL('psapi');self.u=C.WinDLL('user32')
        self.k.OpenProcess.restype=W.HANDLE;self.k.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD]
        self.k.GetProcessTimes.argtypes=[W.HANDLE]+[C.POINTER(W.FILETIME)]*4
        self.k.GetProcessIoCounters.argtypes=[W.HANDLE,C.POINTER(Io)]
        self.k.GetProcessHandleCount.argtypes=[W.HANDLE,C.POINTER(W.DWORD)]
        self.k.CloseHandle.argtypes=[W.HANDLE]
        self.p.GetProcessMemoryInfo.argtypes=[W.HANDLE,C.POINTER(Memory),W.DWORD]
        self.u.GetGuiResources.argtypes=[W.HANDLE,W.DWORD]
        self.handle=self.k.OpenProcess(0x410,False,pid)
        if not self.handle:raise OSError(C.get_last_error(),'OpenProcess',pid)
    def sample(self,now):
        files=[W.FILETIME() for _ in range(4)]
        if not self.k.GetProcessTimes(self.handle,*[C.byref(f) for f in files]):return dict(pid=self.pid,error='process unavailable')
        cpu=sum((f.dwHighDateTime<<32)|f.dwLowDateTime for f in files[2:])/1e7
        m=Memory();m.cb=C.sizeof(m);ok=self.p.GetProcessMemoryInfo(self.handle,C.byref(m),m.cb)
        io=Io();self.k.GetProcessIoCounters(self.handle,C.byref(io));handles=W.DWORD();self.k.GetProcessHandleCount(self.handle,C.byref(handles))
        row=dict(pid=self.pid,cpu_seconds=cpu,working_set_mb=m.ws/1048576 if ok else None,private_mb=m.private/1048576 if ok else None,
            handles=handles.value,gdi_objects=self.u.GetGuiResources(self.handle,0),user_objects=self.u.GetGuiResources(self.handle,1),
            io_read_bytes=io.read_bytes,io_write_bytes=io.write_bytes)
        if self.last:
            elapsed=now-self.last[0];row['sample_interval_seconds']=elapsed
            # GetProcessTimes is quantized. A sub-millisecond first interval
            # can turn one 15.6ms CPU tick into a fictitious multi-core spike.
            if elapsed>=.1:
                row['cpu_one_core_percent']=100*(cpu-self.last[1])/elapsed
                row['cpu_total_percent']=row['cpu_one_core_percent']/(os.cpu_count() or 1)
                row['io_read_bps']=(io.read_bytes-self.last[2])/elapsed;row['io_write_bps']=(io.write_bytes-self.last[3])/elapsed
        self.last=(now,cpu,io.read_bytes,io.write_bytes);return row
    def close(self):self.k.CloseHandle(self.handle)

class PdhValueUnion(C.Union):_fields_=[('doubleValue',C.c_double),('longValue',W.LONG),('largeValue',C.c_longlong)]
class PdhValue(C.Structure):_fields_=[('status',W.DWORD),('value',PdhValueUnion)]
class PdhItem(C.Structure):_fields_=[('name',W.LPWSTR),('value',PdhValue)]

class GpuCounters:
    def __init__(self):
        self.lib=C.WinDLL('pdh');self.query=W.HANDLE();self.counter=W.HANDLE()
        self.lib.PdhOpenQueryW.argtypes=[W.LPCWSTR,C.c_size_t,C.POINTER(W.HANDLE)]
        self.lib.PdhAddEnglishCounterW.argtypes=[W.HANDLE,W.LPCWSTR,C.c_size_t,C.POINTER(W.HANDLE)]
        self.lib.PdhCollectQueryData.argtypes=[W.HANDLE]
        self.lib.PdhGetFormattedCounterArrayW.argtypes=[W.HANDLE,W.DWORD,C.POINTER(W.DWORD),C.POINTER(W.DWORD),C.c_void_p]
        self.lib.PdhCloseQuery.argtypes=[W.HANDLE]
        if self.lib.PdhOpenQueryW(None,0,C.byref(self.query)):raise RuntimeError('PdhOpenQuery')
        if self.lib.PdhAddEnglishCounterW(self.query,r'\GPU Engine(*)\Utilization Percentage',0,C.byref(self.counter)):raise RuntimeError('GPU Engine counter unavailable')
        self.lib.PdhCollectQueryData(self.query)
    def sample(self,pids):
        self.lib.PdhCollectQueryData(self.query);size=W.DWORD();count=W.DWORD();flags=0x200|0x8000
        self.lib.PdhGetFormattedCounterArrayW(self.counter,flags,C.byref(size),C.byref(count),None)
        if not size.value:return {}
        buf=C.create_string_buffer(size.value)
        if self.lib.PdhGetFormattedCounterArrayW(self.counter,flags,C.byref(size),C.byref(count),buf):return {}
        rows=C.cast(buf,C.POINTER(PdhItem));result={}
        for i in range(count.value):
            item=rows[i];match=re.search(r'pid_(\d+)_.*engtype_(.+)',item.name or '')
            if not match or int(match[1]) not in pids or item.value.status not in (0,1):continue
            per=result.setdefault(match[1],{});engine=match[2];per[engine]=per.get(engine,0)+item.value.value.doubleValue
        return result
    def close(self):self.lib.PdhCloseQuery(self.query)

class Util(C.Structure):_fields_=[('gpu',C.c_uint),('memory',C.c_uint)]
class Nvml:
    def __init__(self):
        self.lib=C.WinDLL('nvml.dll');self.handle=C.c_void_p()
        if self.lib.nvmlInit_v2():raise RuntimeError('NVML init failed')
        self.lib.nvmlDeviceGetHandleByIndex_v2.argtypes=[C.c_uint,C.POINTER(C.c_void_p)]
        if self.lib.nvmlDeviceGetHandleByIndex_v2(0,C.byref(self.handle)):raise RuntimeError('NVML GPU unavailable')
        for name in ('nvmlDeviceGetPowerUsage','nvmlDeviceGetUtilizationRates','nvmlDeviceGetTotalEnergyConsumption'):
            fn=getattr(self.lib,name);fn.argtypes=[C.c_void_p,C.c_void_p]
    def sample(self):
        power=C.c_uint();energy=C.c_ulonglong();util=Util();row={}
        if not self.lib.nvmlDeviceGetPowerUsage(self.handle,C.byref(power)):row['board_power_w']=power.value/1000
        if not self.lib.nvmlDeviceGetUtilizationRates(self.handle,C.byref(util)):row.update(gpu_percent=util.gpu,memory_controller_percent=util.memory)
        if not self.lib.nvmlDeviceGetTotalEnergyConsumption(self.handle,C.byref(energy)):row['board_energy_j_counter']=energy.value/1000
        return row
    def close(self):self.lib.nvmlShutdown()

def context():
    result={}
    for key,base in (('normal',ROOT/'artifacts'),('cg_batch',ROOT/'artifacts/cg-ablation')):
        try:
            d=json.loads((base/'connection-diagnostics.json').read_text(encoding='utf-8'))
            game=d.get('game') or {};play=d.get('cgPlayback') or {};gallery=d.get('galleryPlayback') or {}
            result[key]=dict(diagnostic_utc=d.get('utc'),mode=d.get('cgDetectionMode'),worker=d.get('outputWorker'),
                pulse_reason=d.get('pulseReason'),ovc_reason=d.get('ovcReason'),pulse_armed=d.get('pulseArmed'),ovc_armed=d.get('ovcArmed'),
                scene=game.get('scene'),paused=game.get('paused'),gallery=gallery,cg=play,
                routes={role:{k:(d.get(role) or {}).get(k) for k in ('connected','feedback_known','local_only','port','protocol','error','channel_a_reason','channel_b_reason','output_loop_passes')} for role in ('pulse','ovc')},
                channels={role:(d.get(role) or {}).get('output_channels') for role in ('pulse','ovc')})
        except (OSError,ValueError):pass
    return result

class RuntimeJournal:
    """Tail existing game/APP journals without injecting or changing output."""
    def __init__(self,directory):
        self.directory=directory;self.sources={};self.configs={};self.scan_at=0.;self.rows=0
        self.stream=(directory/'runtime-events.jsonl').open('w',encoding='utf-8')
        self.scan(initial=True)
    def scan(self,initial=False):
        paths=[ROOT/'artifacts/ui/runtime.log',ROOT/'artifacts/events.jsonl',ROOT/'artifacts/cg-ablation/events.jsonl']
        configs=[ROOT/'artifacts/settings.json',ROOT/'artifacts/cg-ablation/settings.json']
        for base in (ROOT/'artifacts',ROOT/'artifacts/cg-ablation'):
            for folder in sorted((base/'mock-sessions').glob('*'),key=lambda p:p.name,reverse=True)[:2]:
                try:
                    if not json.loads((folder/'summary.json').read_text(encoding='utf-8')).get('running'):continue
                except (OSError,ValueError):continue
                paths.extend(folder/n for n in ('commands.jsonl','pipeline.jsonl'))
                configs.append(folder/'preset.json')
        for config in configs[:2]:
            try:
                game=Path(json.loads(config.read_text(encoding='utf-8'))['game_directory'])
                paths.append(game/'BepInEx/plugins/SiNiSistarDGLab/telemetry/events.jsonl')
            except (OSError,ValueError,KeyError):pass
        for path in paths:
            if path in self.sources or not path.exists():continue
            # Skip prior sessions; a newly created APP journal belongs to this run.
            self.sources[path]=dict(offset=path.stat().st_size if initial else 0,partial=b'')
        for path in configs:
            try:
                modified=path.stat().st_mtime_ns
                if self.configs.get(path)==modified:continue
                content=json.loads(path.read_text(encoding='utf-8'));self.configs[path]=modified
                self.stream.write(json.dumps(dict(capture_utc=stamp(),kind='profile_snapshot',source=source_name(path),data=content),ensure_ascii=False)+'\n')
            except (OSError,ValueError):pass
        (self.directory/'runtime-sources.json').write_text(json.dumps([source_name(p) for p in self.sources],ensure_ascii=False,indent=2),encoding='utf-8')
    def record(self,elapsed):
        now=time.perf_counter()
        if now>=self.scan_at:self.scan();self.scan_at=now+1
        for path,state in list(self.sources.items()):
            try:
                if path.stat().st_size<state['offset']:state.update(offset=0,partial=b'')
                with path.open('rb') as f:f.seek(state['offset']);buf=f.read(1024*1024);state['offset']=f.tell()
                if not buf:continue
                lines=(state['partial']+buf).split(b'\n');state['partial']=lines.pop()
                for line in lines:
                    if not line.strip():continue
                    try:data=json.loads(line)
                    except (ValueError,UnicodeDecodeError):data=dict(text=line.decode('utf-8',errors='replace'))
                    self.stream.write(json.dumps(dict(capture_utc=stamp(),elapsed=elapsed,source=source_name(path),data=data),ensure_ascii=False)+'\n');self.rows+=1
            except OSError:continue
        self.stream.flush()
    def close(self):self.stream.close()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--pid',type=int,action='append',required=True);parser.add_argument('--seconds',type=float,default=300)
    parser.add_argument('--out',type=Path,required=True);parser.add_argument('--probe',action='store_true');parser.add_argument('--external-frames',action='store_true');parser.add_argument('--runtime-journal',action='store_true');parser.add_argument('--game-pid',type=int,default=20672);args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    processes=[Process(pid) for pid in args.pid];gpu=GpuCounters();nvml=Nvml()
    if args.probe:
        for p in processes:p.sample(time.perf_counter())
        time.sleep(.3);print(json.dumps(dict(processes=[p.sample(time.perf_counter()) for p in processes],gpu=gpu.sample(args.pid),board=nvml.sample())))
        for p in processes:p.close()
        gpu.close();nvml.close();return
    children=[];files=[];start=time.perf_counter();qpc_start=time.perf_counter_ns();errors=[];journal=RuntimeJournal(args.out) if args.runtime_journal else None
    try:
        if not args.external_frames:
            stdout=(args.out/'presentmon.log').open('w');files.append(stdout)
            children.append(subprocess.Popen([str(RUNTIME/'PresentMon-2.6.0-x64.exe'),'--process_name','pythonw.exe','--process_name','SiNiSistar2.exe',
                '--timed',str(int(args.seconds)),'--terminate_after_timed','--no_console_stats','--no_track_input','--qpc_time_ms',
                '--session_name','SiNiSistarPerf-'+args.out.name,'--output_file',str(args.out/'frames.csv')],stdout=stdout,stderr=subprocess.STDOUT,**HIDDEN))
        for pid in args.pid:
            if pid==args.game_pid:continue
            f=(args.out/f'py-spy-{pid}.log').open('w');files.append(f)
            children.append(subprocess.Popen([str(RUNTIME/'py-spy.exe'),'record','--pid',str(pid),'--duration',str(int(args.seconds)),
                '--rate','25','--nonblocking','--threads','--format','speedscope','--output',str(args.out/f'stacks-{pid}.json')],stdout=f,stderr=subprocess.STDOUT,**HIDDEN))
        meta=dict(started_utc=stamp(),duration_seconds=args.seconds,pids=args.pid,logical_cpu_count=os.cpu_count(),qpc_start_ns=qpc_start,
            sample_period_seconds=.25,stack_rate_hz=25,stack_nonblocking=True,frame_capture='PresentMon 2.6.0 ETW',gpu_power_scope='entire NVIDIA board including game and other apps',
            cpu_power_w_available=False,physical_device_commands_sent=False,children=[p.pid for p in children])
        (args.out/'metadata.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
        end=start+args.seconds;next_sample=start;next_context=0;last_context={};n=0;previous_power=None;energy=0
        with (args.out/'samples.jsonl').open('w',encoding='utf-8') as stream:
            while time.perf_counter()<end:
                now=time.perf_counter()
                if now<next_sample:time.sleep(min(next_sample-now,.05));continue
                if now>=next_context:last_context=context();next_context=now+1
                board=nvml.sample();power=board.get('board_power_w')
                if previous_power is not None and power is not None:energy+=(power+previous_power[1])/2*(now-previous_power[0])
                if power is not None:previous_power=(now,power)
                row=dict(utc=stamp(),elapsed=now-start,qpc_ms=now*1000,processes=[p.sample(now) for p in processes],
                    gpu_engine_sum_percent=gpu.sample(args.pid),board=board,context=last_context)
                stream.write(json.dumps(row,ensure_ascii=False)+'\n');stream.flush();n+=1
                if journal:journal.record(now-start)
                (args.out/'status.json').write_text(json.dumps(dict(running=True,elapsed=round(now-start,1),samples=n,energy_wh=energy/3600,runtime_rows=journal.rows if journal else 0)),encoding='utf-8')
                next_sample=max(next_sample+.25,time.perf_counter())
        for p in children:
            try:p.wait(timeout=12)
            except subprocess.TimeoutExpired:errors.append('Profiler child did not finish: '+str(p.pid));p.terminate();p.wait(timeout=3)
        meta.update(finished_utc=stamp(),sample_seconds=time.perf_counter()-start,samples=n,board_energy_wh_integrated=energy/3600,errors=errors,exit_codes=[p.returncode for p in children])
        if journal:journal.record(time.perf_counter()-start);meta['runtime_rows']=journal.rows
        (args.out/'metadata.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
        (args.out/'status.json').write_text(json.dumps(dict(running=False,samples=n,energy_wh=energy/3600)),encoding='utf-8')
    finally:
        for p in processes:p.close()
        gpu.close();nvml.close()
        if journal:journal.close()
        for f in files:f.close()

if __name__=='__main__':main()
