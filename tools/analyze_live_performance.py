"""Summarize the read-only performance capture without conflating swapchains."""
import argparse,csv,html,json,statistics
from collections import defaultdict,Counter
from pathlib import Path

def percentile(values,q):
    values=sorted(values)
    return values[min(len(values)-1,int((len(values)-1)*q))] if values else None

def stats(values):
    return dict(mean=round(statistics.mean(values),3),p95=round(percentile(values,.95),3),max=round(max(values),3)) if values else {}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('directory',type=Path);a=parser.parse_args();root=a.directory
    meta=json.loads((root/'metadata.json').read_text());rows=[json.loads(line) for line in (root/'samples.jsonl').read_text(encoding='utf-8').splitlines()]
    summary=dict(metadata=meta,processes={},frame_streams=[],notes=[
        'CPU one-core %: 100% means one fully occupied logical CPU; it can exceed 100%.',
        'Board power/energy includes the game and every other GPU workload; it is not control-center-only energy.',
        'Qt renders on demand: low FPS in a static/hidden window is not independently proof of a stall.',
        'Each swapchain is analyzed separately; HUD and main-window presents must not be added as application FPS.'])
    timeline=[]
    for pid in meta['pids']:
        values=[(r,p) for r in rows for p in r['processes'] if p['pid']==pid]
        cpus=[p['cpu_one_core_percent'] for _,p in values if 'cpu_one_core_percent' in p]
        private=[p['private_mb'] for _,p in values if p.get('private_mb') is not None]
        engines=[r.get('gpu_engine_sum_percent',{}).get(str(pid),{}).get('3D',0) for r,_ in values]
        summary['processes'][str(pid)]=dict(cpu_one_core_percent=stats(cpus),gpu_3d_engine_sum_percent=stats(engines),private_mb=stats(private),
            first_private_mb=private[0] if private else None,last_private_mb=private[-1] if private else None,
            cpu_over_80_percent_seconds=.25*sum(v>=80 for v in cpus),
            top_cpu_samples=[dict(elapsed=round(r['elapsed'],2),utc=r['utc'],cpu=round(p.get('cpu_one_core_percent',0),2),context=r.get('context'))
                for r,p in sorted(values,key=lambda item:item[1].get('cpu_one_core_percent',0),reverse=True)[:8]])
    summary['board_power_w']=stats([r['board']['board_power_w'] for r in rows if 'board_power_w' in r['board']])
    if len(rows)>1 and all('board_energy_j_counter' in r['board'] for r in (rows[0],rows[-1])):
        summary['board_energy_wh_counter']=(rows[-1]['board']['board_energy_j_counter']-rows[0]['board']['board_energy_j_counter'])/3600
    # Stack profiles distinguish the Socket thread from UI and planner work.
    summary['stack_threads']={}
    for path in root.glob('stacks-*.json'):
        raw=json.loads(path.read_text());frames=raw['shared']['frames'];profiles=[]
        for profile in raw.get('profiles',[]):
            samples=profile.get('samples',[]);counts=Counter()
            for stack in samples:
                for index in set(stack):
                    frame=frames[index];counts[(frame.get('file',''),frame['name'],frame.get('line'))]+=1
            profiles.append(dict(name=profile.get('name'),samples=len(samples),top_frames=[dict(file=k[0],function=k[1],line=k[2],samples=v) for k,v in counts.most_common(12)]))
        summary['stack_threads'][path.stem]=profiles
    frame_path=root/'frames.csv'
    if frame_path.exists():
        groups=defaultdict(list)
        with frame_path.open(encoding='utf-8-sig',newline='') as stream:
            reader=csv.DictReader(stream);summary['frame_columns']=reader.fieldnames
            for r in reader:
                pid=r.get('ProcessID') or r.get('ProcessId')
                if pid not in {str(p) for p in meta['pids']}:continue
                groups[(pid,r.get('SwapChainAddress',''))].append(r)
        for (pid,swap),items in groups.items():
            time_key=next((k for k in ('CPUStartQPCTimeInMs','CPUStartTimeMs','CPUStartQPC','CPUStartTime','TimeInSeconds') if k in items[0]),None)
            metric=next((k for k in ('FrameTime','MsBetweenPresents','CPUFrameTime') if k in items[0]),None)
            times=[];durations=[];gpu_busy=[];cpu_busy=[]
            for item in items:
                try:
                    if time_key:times.append(float(item[time_key])*(1000 if time_key=='TimeInSeconds' else 1))
                    if metric:durations.append(float(item[metric]))
                    if item.get('GPUBusy') or item.get('MsGPUBusy'):gpu_busy.append(float(item.get('GPUBusy') or item['MsGPUBusy']))
                    if item.get('CPUBusy') or item.get('MsCPUBusy'):cpu_busy.append(float(item.get('CPUBusy') or item['MsCPUBusy']))
                except ValueError:pass
            gaps=[b-a for a,b in zip(times,times[1:]) if b>=a]
            grouped=Counter(int((t-times[0])/1000) for t in times) if times else Counter()
            summary['frame_streams'].append(dict(pid=int(pid),swapchain=swap,frames=len(items),time_column=time_key,metric_column=metric,
                frame_interval_ms=stats(durations or gaps),gpu_busy_ms=stats(gpu_busy),cpu_busy_ms=stats(cpu_busy),
                active_second_fps=stats(list(grouped.values())),mean_present_fps=round((len(times)-1)*1000/(times[-1]-times[0]),2) if len(times)>=30 and times[-1]-times[0]>=1000 else None,
                intervals_over_250ms=sum(v>250 for v in (durations or gaps)),
                longest_intervals_ms=sorted(durations or gaps,reverse=True)[:10]))
            if time_key=='CPUStartQPCTimeInMs' and metric:
                long=[]
                for item in items:
                    try:
                        duration=float(item[metric]);t=float(item[time_key])
                        if duration<100:continue
                        nearest=min(rows,key=lambda row:abs(row['qpc_ms']-t))
                        long.append(dict(frame_ms=duration,utc=nearest['utc'],resource_elapsed=nearest['elapsed'],
                            cpu={str(p['pid']):p.get('cpu_one_core_percent') for p in nearest['processes']},
                            board=nearest['board'],context=nearest['context']))
                    except ValueError:pass
                summary['frame_streams'][-1]['long_frame_contexts']=sorted(long,key=lambda row:row['frame_ms'],reverse=True)[:10]
    (root/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    with (root/'timeline.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(['utc','elapsed_seconds','pid','cpu_one_core_percent','cpu_total_percent','private_mb','gpu_3d_engine_sum_percent','board_watts'])
        for r in rows:
            for p in r['processes']:writer.writerow([r['utc'],r['elapsed'],p['pid'],p.get('cpu_one_core_percent'),p.get('cpu_total_percent'),p.get('private_mb'),r.get('gpu_engine_sum_percent',{}).get(str(p['pid']),{}).get('3D',0),r['board'].get('board_power_w')])
    def chart(title,series,ymax,unit):
        colors=['#d87f77','#c8aa75','#9a8bc5','#85b2ac'];svg=[]
        for idx,(name,points) in enumerate(series):
            poly=' '.join(f'{40+900*x/300:.1f},{190-160*min(y,ymax)/ymax:.1f}' for x,y in points)
            svg.append(f'<polyline fill="none" stroke="{colors[idx%4]}" stroke-width="1.4" points="{poly}"/>')
            svg.append(f'<text x="{45+idx*230}" y="222" fill="{colors[idx%4]}">{html.escape(name)}</text>')
        return f'<h2>{title}</h2><svg viewBox="0 0 980 235"><path d="M40 25V190H940" stroke="#665f53" fill="none"/><text x="42" y="20" fill="#b5ad9e">{ymax} {unit}</text><text x="890" y="207" fill="#b5ad9e">300 s</text>{"".join(svg)}</svg>'
    series=[]
    for pid in meta['pids']:
        pts=[(r['elapsed'],p.get('cpu_one_core_percent',0)) for r in rows for p in r['processes'] if p['pid']==pid]
        series.append((str(pid),pts))
    body=chart('CPU · 每个进程（100% = 一个逻辑核心）',series,200,'%')
    body+=chart('整张显卡功耗 · 包含游戏等全部负载',[('RTX 4090',[(r['elapsed'],r['board'].get('board_power_w',0)) for r in rows])],150,'W')
    body+='<h2>汇总</h2><pre>'+html.escape(json.dumps({k:v for k,v in summary.items() if k not in ('metadata','stack_threads','processes')},ensure_ascii=False,indent=2))+'</pre>'
    (root/'report.html').write_text('<!doctype html><meta charset="utf-8"><title>Control Center Performance</title><style>body{background:#151311;color:#e8dfce;font:15px system-ui;max-width:1100px;margin:32px auto}svg{width:100%;background:#211e19;border:1px solid #514635}text{font:12px system-ui}pre{white-space:pre-wrap}h2{color:#c8aa75}</style><h1>SiNiSistar2 · 5 分钟性能采集</h1><p>进程独立计量；功耗为整张显卡，不能等同于控制中心的单独耗电。</p>'+body,encoding='utf-8')
    print(json.dumps(dict(samples=len(rows),processes={k:{f:x for f,x in v.items() if f!='top_cpu_samples'} for k,v in summary['processes'].items()},board=summary['board_power_w'],frames=[{k:v for k,v in row.items() if k!='long_frame_contexts'} for row in summary['frame_streams']]),ensure_ascii=False))

if __name__=='__main__':main()
