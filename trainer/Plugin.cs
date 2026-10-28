// GPL-3.0-only. Optional, explicit-command gameplay helper; no device access.
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text.Json;
using System.Threading;
using BepInEx;
using BepInEx.Unity.IL2CPP;
using BepInEx.Unity.IL2CPP.Hook;

namespace SiNiSistarTrainer;

[BepInPlugin("local.sinisistar.dglab.trainer", "SiNiSistar2 Gameplay Helper", "0.2.2")]
public sealed class Plugin : BasePlugin
{
    const string Fingerprint="b869493305bbe587598c8709e7fe271f00d79d37803c6a8241946d6a6297499d";
    internal static Plugin? Current;
    readonly string session=Guid.NewGuid().ToString("N");
    readonly ConcurrentQueue<Command> commands=new();
    readonly ConcurrentQueue<Dictionary<string,object?>> replies=new();
    readonly Dictionary<string,int> offsets=new();
    readonly Dictionary<string,Dictionary<string,object?>> completed=new();
    readonly Dictionary<string,PendingRemoval> removals=new();
    // InfertilityBlessing enum in the fingerprinted v1.3.1 build.
    const int PositiveBlessing=825765986;
    Native api=null!;
    IntPtr managers;
    string directory="";
    Thread? worker;
    volatile bool stopping;
    volatile Dictionary<string,object?>? latest;
    INativeDetour? attackHook;
    AttackSettings? attackSettings;
    GetDamage? getDamageCallback,getDamageOriginal;
    double multiplier=1.0,lastSample;
    int failures;
    long sample;
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int GetDamage(IntPtr self,IntPtr method);
    sealed record Command(string Id,string Session,int Pid,long Player,string Attribute,string Mode,double Value,DateTimeOffset Expires);
    sealed record PendingRemoval(Command Command,Dictionary<string,object?> Reply,int[] Types,double Deadline);

    string gameFingerprint=Fingerprint;
    string buildProfile="";
    public override void Load()
    {
        if(!SiNiSistarCompatibility.BuildCompatibility.Validate(Paths.GameRootPath,out gameFingerprint,out buildProfile))
        {Log.LogError("Unsupported game/metadata pair; helper disabled.");return;}
        api=new Native();managers=api.Class("SiNiSistar2.Manager","ManagerList");
        directory=Path.Combine(Paths.PluginPath,"SiNiSistarTrainer","ipc");Directory.CreateDirectory(directory);
        try{
            attackSettings=new AttackSettings(Config,Path.Combine(directory,"changes.jsonl"));
            Volatile.Write(ref multiplier,attackSettings.Value);
            // EnhanceAttack is the player's upgrade power table; enemy damage
            // parameters and their Power getter are deliberately untouched.
            var method=api.Method(api.Class("SiNiSistar2.Obj","EnhanceAttack"),"GetDamage",0);
            getDamageCallback=(self,info)=>{
                int original=getDamageOriginal!(self,info);
                double factor=Volatile.Read(ref multiplier);
                return AttackSettings.Damage(original,factor);
            };
            attackHook=INativeDetour.CreateAndApply(Marshal.ReadIntPtr(method),getDamageCallback,out getDamageOriginal);
        }catch(Exception e){Log.LogWarning("Attack helper unavailable: "+e.Message);}
        Current=this;AddComponent<TrainerBehaviour>();
        worker=new Thread(Work){IsBackground=true,Name="SiNiSistarTrainerIPC"};worker.Start();
        Log.LogInfo($"Gameplay helper loaded. HP/MP change only on explicit fresh commands; saved extra attack multiplier: {multiplier}x. Game attack upgrades are untouched.");
    }

    IntPtr P(IntPtr obj,string field)=>obj==IntPtr.Zero?IntPtr.Zero:Marshal.ReadIntPtr(obj,Offset(obj,field));
    bool B(IntPtr obj,string field)=>obj!=IntPtr.Zero&&Marshal.ReadByte(obj,Offset(obj,field))!=0;
    int I(IntPtr obj,string field)=>obj==IntPtr.Zero?0:Marshal.ReadInt32(obj,Offset(obj,field));
    int Offset(IntPtr obj,string field){
        var klass=Marshal.ReadIntPtr(obj);var key=klass.ToInt64()+":"+field;
        if(!offsets.TryGetValue(key,out int value)){
            var f=api.Field(klass,field);if(f==IntPtr.Zero)throw new MissingFieldException(field);
            offsets[key]=value=api.FieldOffset(f);
        }return value;
    }
    Dictionary<string,object?> Resource(IntPtr obj)=>new(){["current"]=api.IntProperty(obj,"get_Current"),["max"]=api.IntProperty(obj,"get_Max")};
    List<Dictionary<string,object?>> Abnormals(IntPtr list){
        var result=new List<Dictionary<string,object?>>();var array=P(list,"<AddedArray>k__BackingField");
        if(array==IntPtr.Zero)return result;
        int count=(int)Math.Clamp(Marshal.ReadInt64(array,24),0,256);
        for(int i=0;i<count;i++){
            var item=Marshal.ReadIntPtr(array,32+i*IntPtr.Size);if(item==IntPtr.Zero)continue;
            int level=I(P(item,"<LevelRp>k__BackingField"),"latestValue");
            if(level>0)result.Add(new(){["type_raw"]=I(item,"m_AbnormalType"),["level"]=level});
        }return result;
    }
    static double Clock()=>Stopwatch.GetTimestamp()/(double)Stopwatch.Frequency;
    internal void Tick()
    {
        if(stopping||Clock()-lastSample<.1)return;lastSample=Clock();
        try{
            api.StaticGet(api.Field(managers,"<Instance>k__BackingField"),out var root);
            var ps=P(root,"m_PlayerStatusManager");var om=P(root,"m_ObjectManager");var seq=P(root,"m_Sequence");
            var player=P(P(om,"m_LeliaRp"),"value");var hp=P(ps,"<HP>k__BackingField");var mp=P(ps,"<MP>k__BackingField");
            var ev=P(root,"m_EventManager");
            var abnormalList=P(ps,"<AbnormalList>k__BackingField");
            var valid=player!=IntPtr.Zero&&ps!=IntPtr.Zero&&hp!=IntPtr.Zero&&mp!=IntPtr.Zero
                &&B(player,"<IsSetupEnd>k__BackingField")&&P(player,"<HP>k__BackingField")==hp
                &&!B(P(seq,"<ChangeSceneProc>k__BackingField"),"<IsActive>k__BackingField");
            var canEdit=valid&&!B(ev,"<IsEventPlaying>k__BackingField");
            // Mutations execute on Unity's main thread, including when paused.
            for(int i=0;i<4&&commands.TryDequeue(out var command);i++)Apply(command,player,hp,mp,abnormalList,canEdit);
            ConfirmRemovals(player,abnormalList,valid);
            latest=new(){["schema"]=1,["source"]="bepinex-trainer",["version"]="0.2.2",["fingerprint"]=gameFingerprint,["build_profile"]=buildProfile,
                ["session"]=session,["pid"]=Environment.ProcessId,["player"]=player.ToInt64(),["sample_id"]=++sample,
                ["utc"]=DateTimeOffset.UtcNow.ToString("O"),["valid"]=valid,["can_edit"]=canEdit,
                ["hp"]=hp==IntPtr.Zero?null:Resource(hp),["mp"]=mp==IntPtr.Zero?null:Resource(mp),
                ["attack_multiplier"]=Volatile.Read(ref multiplier),["attack_available"]=attackHook!=null,
                ["attack_persistent"]=attackSettings!=null&&attackHook!=null,
                ["attack_level"]=ps==IntPtr.Zero?null:api.IntProperty(ps,"get_AttackLv"),
                ["status_removal_available"]=abnormalList!=IntPtr.Zero,["abnormals"]=Abnormals(abnormalList)};
        }catch(Exception e){if(++failures<=5)Log.LogWarning("Helper sample: "+e.Message);}
    }
    void Apply(Command c,IntPtr player,IntPtr hp,IntPtr mp,IntPtr abnormalList,bool canEdit)
    {
        if(completed.TryGetValue(c.Id,out var prior)){replies.Enqueue(prior);return;}
        if(removals.ContainsKey(c.Id))return;
        var reply=new Dictionary<string,object?>{["id"]=c.Id,["session"]=session,["pid"]=Environment.ProcessId,
            ["player"]=player.ToInt64(),["attribute"]=c.Attribute,["utc"]=DateTimeOffset.UtcNow.ToString("O"),["ok"]=false};
        try{
            if(c.Session!=session||c.Pid!=Environment.ProcessId||c.Player!=player.ToInt64())throw new InvalidOperationException("玩家已变化，请重新读取后再操作");
            if(c.Expires<DateTimeOffset.UtcNow||c.Expires>DateTimeOffset.UtcNow.AddSeconds(6))throw new InvalidOperationException("修改请求已过期");
            if(!canEdit)throw new InvalidOperationException("请进入可操作存档，等待加载或演出结束");
            if(!double.IsFinite(c.Value))throw new InvalidOperationException("修改参数无效");
            if(c.Attribute is "abnormal" or "abnormals"){
                if(abnormalList==IntPtr.Zero)throw new InvalidOperationException("异常列表未就绪");
                var active=Abnormals(abnormalList).Select(r=>Convert.ToInt32(r["type_raw"])).Distinct().ToArray();
                int[] targets;
                if(c.Attribute=="abnormal"&&c.Mode=="remove"&&c.Value==Math.Truncate(c.Value)&&c.Value>=int.MinValue&&c.Value<=int.MaxValue)
                    targets=active.Where(t=>t==(int)c.Value).ToArray();
                else if(c.Attribute=="abnormals"&&c.Mode=="clear_negative"&&c.Value==0)
                    targets=active.Where(t=>t!=PositiveBlessing).ToArray();
                else throw new InvalidOperationException("异常解除参数无效");
                if(removals.Count>=32)throw new InvalidOperationException("请等待先前的状态解除完成");
                foreach(int type in targets)api.RemoveAbnormal(abnormalList,type);
                reply["before"]=targets.Length;
                removals[c.Id]=new(c,reply,targets,Clock()+1.0);
                return;
            }else if(c.Attribute=="attack"){
                if(c.Mode is not ("add" or "set" or "reset"))throw new InvalidOperationException("修改参数无效");
                if(attackHook==null)throw new InvalidOperationException("攻击力辅助尚未就绪");
                if(Math.Abs(c.Value)>10)throw new InvalidOperationException("攻击力倍率范围为 0–10 倍");
                double before=Volatile.Read(ref multiplier);
                double after=Math.Round(Math.Clamp(c.Mode=="reset"?1:c.Mode=="add"?before+c.Value:c.Value,0,10),2);
                attackSettings!.Set(after);
                Volatile.Write(ref multiplier,after);reply["before"]=before;reply["after"]=Volatile.Read(ref multiplier);
            }else if(c.Attribute is "hp" or "mp"){
                if(c.Mode is not ("add" or "set")||c.Value!=Math.Truncate(c.Value)||Math.Abs(c.Value)>10000000)throw new InvalidOperationException("HP / MP 需要整数");
                var target=c.Attribute=="hp"?hp:mp;
                int before=api.IntProperty(target,"get_Current")??throw new InvalidOperationException("资源未就绪");
                int max=api.IntProperty(target,"get_Max")??throw new InvalidOperationException("上限未就绪");
                int after=(int)Math.Clamp(c.Mode=="add"?before+c.Value:c.Value,0,max);
                api.SetCurrent(target,after);
                reply["before"]=before;reply["after"]=api.IntProperty(target,"get_Current");reply["max"]=max;
                if(Convert.ToInt32(reply["after"])!=after)throw new InvalidOperationException("游戏未确认目标数值");
            }else throw new InvalidOperationException("不支持的属性");
            reply["ok"]=true;
        }catch(Exception e){reply["error"]=e.Message;}
        Complete(c.Id,reply);
    }
    void Complete(string id,Dictionary<string,object?> reply){
        if(completed.Count>256)completed.Clear();completed[id]=reply;replies.Enqueue(reply);
    }
    void ConfirmRemovals(IntPtr player,IntPtr list,bool valid){
        foreach(var pair in removals.ToArray()){
            var p=pair.Value;var reply=p.Reply;
            if(!valid||player.ToInt64()!=p.Command.Player){reply["error"]="玩家已变化，请检查当前状态";}
            else{
                var active=Abnormals(list).Select(r=>Convert.ToInt32(r["type_raw"])).ToHashSet();
                var remaining=p.Types.Where(active.Contains).ToArray();
                if(remaining.Length>0&&Clock()<p.Deadline)continue;
                reply["after"]=remaining.Length;reply["removed_types"]=p.Types.Where(t=>!active.Contains(t)).ToArray();
                reply["ok"]=remaining.Length==0;
                if(remaining.Length>0)reply["error"]="部分状态仍存在或被重新施加，请查看当前列表";
            }
            removals.Remove(pair.Key);Complete(pair.Key,reply);
        }
    }
    void Atomic(string name,object value){
        var file=Path.Combine(directory,name);var temp=file+".tmp";
        File.WriteAllText(temp,JsonSerializer.Serialize(value));File.Move(temp,file,true);
    }
    void Work()
    {
        string lastId="";long written=0;
        while(!stopping){
            try{
                var data=latest;
                if(data!=null&&Convert.ToInt64(data["sample_id"])!=written){Atomic("latest.json",data);written=Convert.ToInt64(data["sample_id"]);}
                while(replies.TryDequeue(out var reply)){
                    Atomic("result.json",reply);
                    File.AppendAllText(Path.Combine(directory,"changes.jsonl"),JsonSerializer.Serialize(reply)+Environment.NewLine);
                }
                var path=Path.Combine(directory,"command.json");
                if(File.Exists(path)&&new FileInfo(path).Length<4096){
                    using var doc=JsonDocument.Parse(File.ReadAllText(path));var r=doc.RootElement;
                    string id=r.GetProperty("id").GetString()??"";
                    if(id!=lastId&&Guid.TryParseExact(id,"N",out _)&&commands.Count<8){
                        var c=new Command(id,r.GetProperty("session").GetString()??"",r.GetProperty("pid").GetInt32(),r.GetProperty("player").GetInt64(),
                            r.GetProperty("attribute").GetString()??"",r.GetProperty("mode").GetString()??"",r.GetProperty("value").GetDouble(),r.GetProperty("expires_utc").GetDateTimeOffset());
                        commands.Enqueue(c);lastId=id;
                    }
                }
            }catch(Exception e){if(++failures<=5)Log.LogWarning("Helper IPC: "+e.Message);}
            Thread.Sleep(50);
        }
    }
    public override bool Unload(){
        stopping=true;Current=null;worker?.Join(1000);attackHook?.Dispose();return true;
    }
}

public sealed class TrainerBehaviour : UnityEngine.MonoBehaviour
{
    public TrainerBehaviour(IntPtr pointer):base(pointer){}
    public void Update()=>Plugin.Current?.Tick();
}
