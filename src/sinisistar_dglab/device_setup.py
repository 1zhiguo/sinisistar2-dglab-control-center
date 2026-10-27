"""User-facing device diagnostics. Protocol facts follow dglab-kit README_CN."""
import math

HINTS={
 'bluetooth-not-connected':('蓝牙未连接','请在 DG-LAB APP 中连接控制器，并保持 APP 在线。'),
 'channel-muted':('通道已静音','请在 DG-LAB APP 中手动解除该通道静音。'),
 'channel-blocked':('通道已屏蔽','请在 DG-LAB APP 中手动打开被屏蔽的通道。'),
 'channel-fault':('APP 报告输出损坏','请检查设备连接，并在 DG-LAB APP 中处理故障；程序不会自动解除。'),
 'channel-fault-or-blocked':('通道故障或屏蔽','请查看 DG-LAB APP 的通道提示，解除屏蔽或处理故障。'),
 'accessory-not-inserted':('未插入振动配件','请将振动配件插入负鼠对应的 A/B 接口。'),
 'missing-device-state':('状态尚未同步','请等待 APP 上报完整设备状态；持续无更新可重新同步。'),
 'unsupported-device':('设备类型暂不支持','请选择郊狼 COYOTE_030 或负鼠 OVC_1。'),
 'unsupported-waveformat':('旧版郊狼波形格式不支持','此 V4 路线支持 COYOTE_030；旧版设备请使用对应的兼容方案。'),
 'software-channel-off':('本通道已关闭','在下方 A/B 通道控制中打开所需通道。'),
 'software-limit-zero':('软件上限为零','请调整快速设置及该通道的软件上限。'),
 'app-limit-zero':('APP 上限为零','请在 DG-LAB APP 中为该通道设置可用的强度上限。'),
 'ovc-limit-too-low':('负鼠上限不足 10','负鼠按 10 一档输出，请检查软件与 APP 上限。'),
}
RPC_HINTS={
 'duplicate_request_id':'APP 报告请求编号重复，请重新同步设备。',
 'invalid_params':'APP 拒绝参数，请检查 APP 版本及连接配置。',
 'slot_not_found':'APP 已找不到该设备，请重新连接控制器并同步设备。',
 'invalid_operate':'APP 不支持本次操作或波形，请更新 APP 并检查设备类型。',
 'method_not_found':'APP 不支持本次接口，请检查 APP 版本。',
 'internal_error':'APP 内部处理失败，请查看 APP 提示并重新同步。',
 'cancelled':'APP 已取消输出任务，请检查蓝牙、通道屏蔽和 APP 当前状态后重新同步。',
}

def app_error_hint(error):
    return next((hint for code,hint in RPC_HINTS.items() if code in str(error)),
                '请查看 DG-LAB APP 的错误提示；检查蓝牙与通道状态后重新同步。') if error else ''

def setup_status(role,snapshot,*,enabled,caps,device=None,emergency=False,pending=False,simulating=False,live_source=True,offline=False):
    s=snapshot or {};device=device or {};v4=s.get('protocol')=='v4';rows=[];usable=[]
    props=device.get('props') or {}
    for c in 'AB':
        code=s.get('channel_'+c.lower()+'_reason','') if v4 and s.get('selected_slot_id') else ''
        app_cap=s.get('limit_'+c.lower());software_cap=caps[c]
        if not code and not enabled[c]:code='software-channel-off'
        if not code and software_cap<=0:code='software-limit-zero'
        known=type(app_cap) in (int,float) and math.isfinite(app_cap)
        if not code and not known:code='missing-device-state'
        if not code and app_cap<=0:code='app-limit-zero'
        if not code and role=='ovc' and min(app_cap,software_cap)<10:code='ovc-limit-too-low'
        title,hint=HINTS.get(code,('通道可用',''))
        raw=props.get('channel'+c+'Status')
        if not code and device.get('type')=='COYOTE_030':
            title={0:'就绪 · 无输出或输出较低',1:'就绪 · APP 尚未检测到回路',2:'就绪 · 输出正常'}.get(raw,title)
            if raw==1:hint='如预期应有输出，请对照 DG-LAB APP 检查连接；这不是通道屏蔽。'
        rows.append(dict(channel=c,code=code,title=title,hint=hint,rawStatus=raw))
        if not code:usable.append(c)
    error=s.get('error') or ''
    if offline:reason='离线预览不会启用设备。'
    elif emergency:reason='急停已锁定，请先解除急停，再手动启用。'
    elif pending:reason='请等待游戏辅助修改完成后，再手动启用。'
    elif simulating or not live_source:reason='请退出样例模拟并选择实时游戏数据源。'
    elif error:reason='DG-LAB APP / 连接错误：'+str(error)
    elif not s.get('server_ready'):reason='负鼠尚未接入，无法启用。请先启动扫码连接，并在 APP 中连接负鼠控制器。' if role=='ovc' else '请先启动扫码连接服务。'
    elif not v4 and not s.get('connected'):reason='请使用 DG-LAB 3 APP 扫码配对。'
    elif v4 and not s.get('selected_slot_id'):reason='未接入负鼠设备，无法启用。请在 DG-LAB APP 中连接负鼠控制器，并将振动配件插入 A 或 B 口。' if role=='ovc' else '等待 APP 发现对应设备；请在 APP 中连接控制器。'
    elif role=='ovc' and all(r['code']=='accessory-not-inserted' for r in rows):reason='负鼠控制器已连接，但未接入振动配件，无法启用。请至少将一个振动配件插入 A 或 B 接口。'
    elif not usable:reason='；'.join(c['channel']+'：'+c['title']+'。'+c['hint'] for c in rows)
    elif s.get('readiness_failed'):reason='设备同步或归零确认失败，请查看 APP 提示后重新同步。'
    elif not s.get('connected'):reason='正在同步设备并确认归零，请稍候。' if v4 else '请使用 DG-LAB 3 APP 扫码配对。'
    elif not s.get('feedback_known'):reason='等待 APP 强度与上限回报，请保持 APP 在线。'
    else:reason=''
    button='启用 Pulse' if role=='pulse' else '启用负鼠'
    if role=='ovc' and reason:
        if not s.get('selected_slot_id') or all(r['code']=='bluetooth-not-connected' for r in rows):button='未接入设备'
        elif all(r['code']=='accessory-not-inserted' for r in rows):button='未接入振动配件'
    return dict(canEnable=not bool(reason),reason=reason,buttonLabel=button,channels=rows,usableChannels=''.join(usable),showChannels=bool(s.get('selected_slot_id') or s.get('connected')),
                appError=str(error),appErrorHint=app_error_hint(error))
