"""Compare the same first minute, and audit the full five-minute mock run."""
from pathlib import Path
from datetime import datetime,timezone
import html,json,statistics,time
ROOT=Path(__file__).resolve().parents[1];out=ROOT/'artifacts/performance/v4-ui-fix-comparison';out.mkdir(exist_ok=True)
before_dir=ROOT/'artifacts/performance/controlled-before-60s';after_dir=ROOT/'artifacts/performance/controlled-after-300s'
before=json.loads((before_dir/'report.json').read_text(encoding='utf-8'));after=json.loads((after_dir/'report.json').read_text(encoding='utf-8'))
def minute(folder,report):
    samples=[s for s in json.loads((folder/'resources.json').read_text(encoding='utf-8')) if .1<=s['elapsed']<=60]
    cpu=[s['process']['cpu_one_core_percent'] for s in samples if 'cpu_one_core_percent' in s['process']]
    t0=report['marks'][0]['at'];frames=[t for t in json.loads((folder/'frames.json').read_text()) if t0<=t<=t0+60]
    blocks=[m for m in report['marks'] if m['kind']=='intentional_gui_block']
    gaps=[(b-a)*1000 for a,b in zip(frames,frames[1:]) if not any(m['at']-.05<=b and m['at']+.9>=a for m in blocks)]
    return dict(cpu_one_core_mean=statistics.mean(cpu),frame_gap_max_ms=max(gaps),frame_gaps_over_250ms=sum(g>250 for g in gaps),rendered_frames=len(frames),
        memory_private_mb_mean=statistics.mean(s['process']['private_mb'] for s in samples),
        board_power_mean_w=statistics.mean(s['board']['board_power_w'] for s in samples),samples=samples)
a=minute(before_dir,before);b=minute(after_dir,after)
valid_cpu=[r['process']['cpu_one_core_percent'] for r in json.loads((after_dir/'resources.json').read_text(encoding='utf-8')) if r['elapsed']>=.1 and 'cpu_one_core_percent' in r['process']]
after['cpu_one_core_mean']=statistics.mean(valid_cpu)
after['cpu_sampling_note']='The initial sub-millisecond CPU interval is excluded from both versions; Windows CPU ticks cannot resolve such a short interval.'
records=[json.loads(line) for line in (Path(after['mock_session'])/'commands.jsonl').read_text(encoding='utf-8').splitlines()]
# PresentMon/Qt use QPC; the transport retains its existing monotonic lease clock.
offset=time.monotonic()-time.perf_counter();safety={}
for stop,resume in (('pause','resume'),('emergency','emergency_resume')):
    s=next(m for m in after['marks'] if m['kind']==stop);e=next(m for m in after['marks'] if m['kind']==resume)
    inside=[r for r in records if s['at']+offset+.25<r['at']<e['at']+offset-.1 and r.get('m')=='device.op' and r.get('data',{}).get('t')==0]
    later={slot+str(channel):sum(r.get('m')=='device.op' and r.get('data',{}).get('s')==slot and r['data'].get('c')==channel and r['data'].get('t')==0 and e['at']+offset+.3<r['at']<e['at']+offset+2 for r in records) for slot in ('coyote','ovc') for channel in (0,1)}
    safety[stop]=dict(wave_packets_inside_stopped_window=len(inside),resumed_packets=later,passed=not inside and all(v>0 for v in later.values()))
thread=json.loads((ROOT/'artifacts/performance/fixed-v4-thread-cpu.json').read_text())
summary=dict(created_utc=datetime.now(timezone.utc).isoformat(),matched_first_60_seconds=dict(before={k:v for k,v in a.items() if k!='samples'},after={k:v for k,v in b.items() if k!='samples'}),
    cpu_reduction_percent=100*(1-b['cpu_one_core_mean']/a['cpu_one_core_mean']),
    full_300_second_run=after,stopped_window_audit=safety,fixed_idle_v4_thread=thread,hardware_connected=False,
    notes=['The old source was preserved before edits; both runs use the same preset, mock APP, QML pages, CG fixtures and first-minute actions.',
        'Five-minute frame and packet results exclude the five deliberately injected 700ms UI stalls from unexpected frame-gap statistics.',
        'Steady packet gaps exclude declared CG changes, Space pauses and emergency-stop windows; these transitions are tested separately.',
        'NVIDIA board watts include the game and all other apps. Different board power is not attributed solely to this change.',
        'Nonblocking stack snapshots and a short Windows thread CPU audit corroborate the earlier live capture; no physical-device continuity is claimed.'])
summary['continuity_passed']=after['passed'] and all(v['passed'] for v in safety.values())
summary['passed']=summary['continuity_passed'] and b['cpu_one_core_mean']<a['cpu_one_core_mean'] and after['frames_over_250ms']==0
(out/'comparison.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
def chart():
    lines=[]
    for name,data,color in [('修复前',a,'#d98278'),('修复后',b,'#a9bf9b')]:
        points=' '.join(f'{40+row["elapsed"]*14:.1f},{190-min(100,row["process"].get("cpu_one_core_percent",0))*1.6:.1f}' for row in data['samples'])
        lines.append(f'<polyline fill="none" stroke="{color}" stroke-width="1.6" points="{points}"/>')
    return '<svg viewBox="0 0 940 215"><path d="M40 20V190H880" fill="none" stroke="#665e52"/><text x="42" y="15">100% 单核 CPU</text><text x="835" y="208">60 秒</text>'+''.join(lines)+'</svg>'
rows=[]
for label,key,suffix in [('平均 CPU（100%=单核）','cpu_one_core_mean','%'),('最长非人为帧间隔','frame_gap_max_ms',' ms'),('超过 250 ms 的非人为长帧','frame_gaps_over_250ms',''),('私有内存均值','memory_private_mb_mean',' MB')]:
    rows.append(f'<tr><td>{label}</td><td>{a[key]:.2f}{suffix}</td><td>{b[key]:.2f}{suffix}</td></tr>')
body='<h1>V4 与前台性能修复 · 对比验证</h1><p>前 60 秒执行同一套自动操作；修复版额外持续验证至 300 秒。全部连接仅限 127.0.0.1。</p><table><tr><th>相同前一分钟</th><th>修复前</th><th>修复后</th></tr>'+''.join(rows)+'</table>'+chart()
body+='<h2>完整 5 分钟持续输出</h2><p>'+html.escape(json.dumps(dict(seconds=after['seconds'],streams=after['streams'],intentional_stalls=after['blocks'],safety=safety),ensure_ascii=False,indent=2)).replace('\n','<br>')+'</p>'
body+='<p>CPU 红色＝修复前，绿色＝修复后。功耗为整张显卡，包含游戏，不能按差值认定为控制中心单独节能。原始字段与日志见 comparison.json。</p>'
(out/'report.html').write_text('<!doctype html><meta charset="utf-8"><title>V4 Performance Comparison</title><style>body{background:#171410;color:#e9e0d0;font:15px system-ui;max-width:1040px;margin:32px auto}h1,h2{color:#c6a66d}table{border-collapse:collapse;width:100%}td,th{padding:12px;border:1px solid #514635;text-align:left}svg{width:100%;background:#211e18;margin:20px 0}text{fill:#b8ad9d;font:12px system-ui}p{line-height:1.7}</style>'+body,encoding='utf-8')
print(json.dumps(dict(passed=summary['passed'],before=summary['matched_first_60_seconds']['before'],after=summary['matched_first_60_seconds']['after'],reduction=summary['cpu_reduction_percent'],streams=after['streams'],frames_over_250ms=after['frames_over_250ms'],max_frame_ms=after['frame_gap_max_ms'],blocks=after['blocks'],safety=safety),ensure_ascii=False))
