// GPL-3.0-only. Observational BepInEx IL2CPP plugin; never changes game values.
using System;
using System.Collections.Generic;
using System.Collections.Concurrent;
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

namespace SiNiSistarDGLab;

[BepInPlugin("local.sinisistar.dglab.observer", "SiNiSistar2 DG-LAB Observer", "0.8.0")]
public sealed partial class Plugin : BasePlugin
{
    const string Fingerprint="b869493305bbe587598c8709e7fe271f00d79d37803c6a8241946d6a6297499d";
    readonly List<INativeDetour> hooks=new();
    readonly List<Delegate> callbacks=new();
    readonly HashSet<string> installedHooks=new();
    readonly List<string> failedHooks=new();
    readonly ConcurrentQueue<Dictionary<string,object?>> events=new();
    readonly string session=Guid.NewGuid().ToString("N");
    volatile bool stopping;
    Thread? writer;
    Native api=null!;
    string directory="";
    long serial, sample;
    double lastSample;
    IntPtr managerClass, releaseClass, enemyClass, player, playerAbnormal;
    uint playerHandle, abnormalHandle;
    volatile Dictionary<string,object?>? latest;
    readonly Dictionary<string,int> offsets=new();
    readonly JsonSerializerOptions json=new(){WriteIndented=false};
    int readFailures;
    IntPtr eventManager,flowPlayer,labelPlayer,defeatPlayer;
    int flowScene=-1,flowRun,labelScene=-1,labelBudget;
    bool flowWasPlaying;
    double flowElapsed,lastFlowSample,flowStarted,lastLabelAt,lastDefeatAt,labelBudgetAt;
    string lastLabel="",lastLabelType="";
    long damageSerial, lifeSerial;
    readonly Dictionary<long,EnemyLife> enemyLives=new();
    [ThreadStatic] static DamageObservation? activeDamage;
    sealed class EnemyLife
    {
        internal long Id,HpObject;
        internal int Scene;
        internal FatalHit? Fatal;
    }
    sealed class FatalHit
    {
        internal long DamageId;
        internal int BeforeHp;
        internal bool FromPlayer;
        internal string Sender="";
        internal double Time;
    }
    sealed class DamageObservation
    {
        internal DamageObservation? Parent;
        internal IntPtr Enemy;
        internal uint Hold;
        internal EnemyLife Life=null!;
        internal long DamageId;
        internal int BeforeHp,BeforeState,Scene;
        internal bool FromPlayer;
        internal string Sender="",EnemyName="";
        internal int? DeathHp;
    }

    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate void V0(IntPtr self,IntPtr method);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate void V1(IntPtr self,IntPtr arg,IntPtr method);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate void VI(IntPtr self,int value,IntPtr method);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate void VB(IntPtr self,[MarshalAs(UnmanagedType.I1)]bool value,IntPtr method);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate void BindStart(IntPtr self,IntPtr binder,IntPtr parameter,[MarshalAs(UnmanagedType.I1)]bool swap,IntPtr method);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate void AbnormalAdd(IntPtr self,int type,int level,IntPtr damage,IntPtr method);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate void VBB(IntPtr self,[MarshalAs(UnmanagedType.I1)]bool a,[MarshalAs(UnmanagedType.I1)]bool b,IntPtr method);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate void V2(IntPtr self,IntPtr a,IntPtr b,IntPtr method);

    string gameFingerprint=Fingerprint;
    string buildProfile="";
    SiNiSistarCompatibility.RuntimeInterface.Report? compatibility;
    Dictionary<string,object?> compatibilityData=new();
    public override void Load()
    {
        directory=Config.Bind("Bridge","Directory",Path.Combine(Paths.PluginPath,"SiNiSistarDGLab","telemetry"),"Local observer IPC directory. No device connection.").Value;
        Directory.CreateDirectory(directory);
        try{
            bool known=SiNiSistarCompatibility.BuildCompatibility.Validate(Paths.GameRootPath,out gameFingerprint,out buildProfile);
            compatibility=SiNiSistarCompatibility.RuntimeInterface.Check(new SiNiSistarCompatibility.RuntimeInterface.NativeMetadata());
            compatibilityData=compatibility.Data(gameFingerprint);
            compatibilityData["known_build"]=known;
            compatibilityData["session"]=session;compatibilityData["pid"]=Environment.ProcessId;
            compatibilityData["utc"]=DateTimeOffset.UtcNow.ToString("O");
            WriteCompatibility();
            if(!compatibility.Compatible){Log.LogError("Game interface incompatible; no hooks installed: "+string.Join("; ",compatibility.Errors.Take(8)));return;}
            if(!known)buildProfile="interface-compatible";
            api=new Native();managerClass=api.Class("SiNiSistar2.Manager","ManagerList");enemyClass=api.Class("SiNiSistar2.Obj","EnemyObject");
            releaseClass=api.Nested(api.Class("SiNiSistar2.Obj","GachaBind"),"ReleaseResponseParameter");
        }catch(Exception error){
            compatibilityData=new(){["schema"]=1,["status"]="incompatible",["errors"]=new[]{error.Message},["pid"]=Environment.ProcessId,["session"]=session,["utc"]=DateTimeOffset.UtcNow.ToString("O")};
            WriteCompatibility();Log.LogError("Game interface probe failed; no hooks installed: "+error.Message);return;
        }
        Log.LogInfo("Game interface compatible: "+buildProfile);
        // All callbacks call the original exactly once, without modifying arguments or results.
        Install("ObjectManager.Update",()=>{
            V0 original=null!;V0 callback=(self,method)=>{original(self,method);Guard(Snapshot);};
            Attach(api.Method(api.Class("SiNiSistar2.Obj","ObjectManager"),"Update",0),callback,out original);
        });
        Install("Lelia.OnDamageHappen",()=>{
            V1 original=null!;V1 callback=(self,arg,method)=>{
                Guard(()=>{if(self==player)Emit("damage_callback",new(){["before_hp"]=I(arg,"m_BeforeHp"),["remain_hp"]=I(arg,"m_RemainHP"),["spend_hp"]=I(arg,"m_SpendHp"),["spend_mp"]=I(arg,"m_SpendMp"),["remain_mp"]=I(arg,"m_RemainMP"),["scene_id"]=Scene});});
                original(self,arg,method);
            };
            Attach(api.Method(api.Class("SiNiSistar2.Obj","Lelia"),"OnDamageHappen",1),callback,out original);
        });
        Install("DamageManager.UpdateDamageOne",()=>{
            V1 original=null!;V1 callback=(self,stack,method)=>{
                DamageObservation? observed=null;
                Guard(()=>observed=BeginEnemyDamage(stack));
                var parent=activeDamage;
                if(observed!=null){observed.Parent=parent;activeDamage=observed;}
                try{original(self,stack,method);}
                finally{
                    if(observed!=null){Guard(()=>EndEnemyDamage(observed));activeDamage=parent;api.Release(observed.Hold);}
                }
            };
            Attach(api.Method(api.Class("SiNiSistar2.Damage","DamageManager"),"UpdateDamageOne",1,"DamageStack"),callback,out original);
        });
        Install("EnemyDead.DiedButExists",()=>{
            V0 original=null!;V0 callback=(self,method)=>{
                Dictionary<string,object?>? before=null;Guard(()=>before=BeforeEnemyDeath(self));
                original(self,method);Guard(()=>AfterEnemyDeath(self,before,false));
            };
            Attach(api.Method(api.Class("SiNiSistar2.Obj","EnemyDead"),"DiedButExists",0),callback,out original);
        });
        Install("EnemyDead.DeathOfExistence",()=>{
            VBB original=null!;VBB callback=(self,notDefeat,sustainActive,method)=>{
                Dictionary<string,object?>? before=null;Guard(()=>before=BeforeEnemyDeath(self));
                original(self,notDefeat,sustainActive,method);Guard(()=>AfterEnemyDeath(self,before,notDefeat));
            };
            Attach(api.Method(api.Class("SiNiSistar2.Obj","EnemyDead"),"DeathOfExistence",2),callback,out original);
        });
        Install("EnemyDead.ResumeAlive",()=>{
            V0 original=null!;V0 callback=(self,method)=>{
                original(self,method);Guard(()=>{
                    var enemy=P(self,"<EnemyObject>k__BackingField");
                    if(enemy!=IntPtr.Zero)enemyLives.Remove(enemy.ToInt64());
                });
            };
            Attach(api.Method(api.Class("SiNiSistar2.Obj","EnemyDead"),"ResumeAlive",0),callback,out original);
        });
        Install("GachaBind.ReleaseResponseParameter.set_ReleaseReason",()=>{
            VI original=null!;VI callback=(self,value,method)=>{
                original(self,value,method);
                Guard(()=>{if(self!=IntPtr.Zero&&Marshal.ReadIntPtr(self)==releaseClass)Emit("release_reason_callback",new(){["reason_raw"]=value,["reason"]=Reason(value),["response_object"]=self.ToInt64().ToString("X"),["is_player_response"]=self==P(P(player,"m_GachaBind"),"m_ReleaseResponseParameter")});});
            };
            Attach(api.Method(releaseClass,"set_ReleaseReason",1),callback,out original);
        });
        Install("Bind.StartBind",()=>{
            BindStart original=null!;BindStart callback=(self,binder,param,swap,method)=>{
                original(self,binder,param,swap,method);
                Guard(()=>{if(self==P(player,"m_Bind"))Emit("bind_start_callback",new(){["binder"]=api.ObjectName(binder),["swap"]=swap});});
            };
            Attach(api.Method(api.Class("SiNiSistar2.Obj","Bind"),"StartBind",3),callback,out original);
        });
        Install("Bind.ReleaseBind",()=>{
            V0 original=null!;V0 callback=(self,method)=>{
                Guard(()=>{if(self==P(player,"m_Bind"))Emit("bind_release_callback",new(){["binder"]=api.ObjectName(P(self,"<Binder>k__BackingField")),["hp"]=Parameter(P(player,"<HP>k__BackingField"))});});
                original(self,method);
            };
            Attach(api.Method(api.Class("SiNiSistar2.Obj","Bind"),"ReleaseBind",0),callback,out original);
        });
        Install("RedAlert.ShowGameOver(bool)",()=>{
            VB original=null!;VB callback=(self,value,method)=>{Guard(()=>{MarkDefeat();Emit("show_gameover_callback",new(){["immediate"]=value});});original(self,value,method);};
            Attach(api.Method(api.Class("SiNiSistar2.UI","RedAlert"),"ShowGameOver",1),callback,out original);
        });
        Install("GameOverLabel.ExecutionOne",()=>{
            V1 original=null!;V1 callback=(self,arg,method)=>{Guard(()=>{MarkDefeat();Emit("gameover_label_callback",new(){["display_type"]=I(arg,"m_GameOverDisplayType"),["hp_control_type"]=I(arg,"m_HpControlType"),["has_retry_time"]=B(arg,"m_HasRetryTime"),["retry_time"]=F(arg,"m_RestartTime"),["label"]=api.String(P(arg,"m_Label"))});});original(self,arg,method);};
            Attach(api.Method(api.Class("SiNiSistar2.EventLabel.GameOver","GameOverLabel"),"ExecutionOne",1),callback,out original);
        });
        Install("AbnormalList.AddAbnormal(enum)",()=>{
            AbnormalAdd original=null!;AbnormalAdd callback=(self,type,level,damage,method)=>{original(self,type,level,damage,method);Guard(()=>{if(self==playerAbnormal)Emit("abnormal_add_callback",new(){["type_raw"]=type,["requested_level"]=level});});};
            Attach(api.Method(api.Class("SiNiSistar2.Obj","AbnormalList"),"AddAbnormal",3,"AbnormalType"),callback,out original);
        });
        foreach(var name in new[]{"DownAbnormal","RemoveAbnormal"})
        {
            var captured=name;
            Install("AbnormalList."+name+"(enum)",()=>{
                VI original=null!;VI callback=(self,type,method)=>{original(self,type,method);Guard(()=>{if(self==playerAbnormal)Emit(captured=="DownAbnormal"?"abnormal_down_callback":"abnormal_remove_callback",new(){["type_raw"]=type});});};
                Attach(api.Method(api.Class("SiNiSistar2.Obj","AbnormalList"),name,1,"AbnormalType"),callback,out original);
            });
        }
        Install("EventManager.PlayEvent",()=>{
            V2 original=null!;V2 callback=(self,trigger,eventPlayer,method)=>{
                Guard(()=>{lastLabel="";lastLabelType="";Emit("flow_request_callback",new(){["name"]=api.ObjectLabel(eventPlayer),["type"]=api.ObjectName(eventPlayer),["trigger"]=api.ObjectLabel(trigger),["scene_id"]=Scene});});
                original(self,trigger,eventPlayer,method);
            };
            Attach(api.Method(api.Class("SiNiSistar2.Event","EventManager"),"PlayEvent",2),callback,out original);
        });
        Install("EventManager.StopEvent",()=>{
            V0 original=null!;V0 callback=(self,method)=>{Guard(()=>Emit("flow_stop_callback",new(){["name"]=api.ObjectLabel(P(self,"<CurrentEventPlayer>k__BackingField")),["scene_id"]=Scene}));original(self,method);};
            Attach(api.Method(api.Class("SiNiSistar2.Event","EventManager"),"StopEvent",0),callback,out original);
        });
        Install("EventReceiver.CallEvent",()=>{
            V1 original=null!;V1 callback=(self,label,method)=>{Guard(()=>ObserveLabel(self,label));original(self,label,method);};
            Attach(api.Method(api.Class("","EventReceiver"),"CallEvent",1,"String"),callback,out original);
        });
        Install("LabelEvent.LabelEvent_Execution",()=>{
            V1 original=null!;V1 callback=(self,label,method)=>{Guard(()=>ObserveLabel(self,label));original(self,label,method);};
            Attach(api.Method(api.Class("SiNiSistar2.EventLabel","LabelEvent"),"LabelEvent_Execution",1,"String"),callback,out original);
        });
        InstallCgObservation();
        if(failedHooks.Count>0||!installedHooks.Contains("ObjectManager.Update")){
            compatibilityData["status"]="incompatible";compatibilityData["errors"]=failedHooks.Count>0?failedHooks.ToArray():new[]{"Core ObjectManager.Update hook could not be installed"};WriteCompatibility();
            for(int i=hooks.Count-1;i>=0;i--)hooks[i].Dispose();hooks.Clear();return;
        }
        writer=new Thread(WriteLoop){IsBackground=true,Name="SiNiSistarDGLab IPC"};writer.Start();
        Emit("observer_loaded",new(){["hook_count"]=hooks.Count,["version"]="0.8.0",["compatibility"]=compatibilityData,["combat_hooks"]=CombatHooks(),["flow_hooks"]=FlowHooks(),["game_build"]=buildProfile});
        Log.LogInfo($"Observer loaded: {hooks.Count} hooks. Local IPC: {directory}. No DG-LAB output.");
    }

    void Attach<T>(IntPtr method,T callback,out T original) where T:Delegate
    { if(method==IntPtr.Zero||compatibility?.Methods.Contains(method)!=true||Marshal.ReadIntPtr(method)==IntPtr.Zero)throw new InvalidOperationException("Native hook signature was not validated");hooks.Add(INativeDetour.CreateAndApply(Marshal.ReadIntPtr(method),callback,out original));callbacks.Add(callback); }
    void WriteCompatibility()
    {var path=Path.Combine(directory,"compatibility.json");File.WriteAllText(path+".tmp",JsonSerializer.Serialize(compatibilityData,json));File.Move(path+".tmp",path,true);}
    void Install(string name,Action action)
    {try{action();installedHooks.Add(name);Emit("hook_installed",new(){["hook"]=name});}catch(Exception e){failedHooks.Add(name+": "+e.Message);Log.LogWarning(name+": "+e.Message);Emit("hook_failed",new(){["hook"]=name,["error"]=e.Message});}}
    void Guard(Action action)
    {try{action();}catch(Exception e){if(++readFailures<=5)Log.LogWarning("Observer read: "+e.Message);}}
    static string Reason(int x)=>x switch{0=>"BeforeRelease",1=>"IsDead",2=>"SuccessRelease",3=>"CancelToken",4=>"BeforeBind",5=>"OtherRelease",6=>"ForceRelease",7=>"FromBind",8=>"ReplaceBind",9=>"SimpleRelease",10=>"CommonDeadRelease",_=>"Unknown"};
    void Emit(string kind,Dictionary<string,object?> data)
    {if(events.Count>=10000)return;data["event_type"]=kind;data["sequence"]=Interlocked.Increment(ref serial);data["session"]=session;data["utc"]=DateTimeOffset.UtcNow.ToString("O");data["pid"]=Environment.ProcessId;data["player"]=player.ToInt64();events.Enqueue(data);}
    IntPtr Field(IntPtr obj,string name)
    {if(obj==IntPtr.Zero)return IntPtr.Zero;return api.Field(Marshal.ReadIntPtr(obj),name);}
    int Offset(IntPtr obj,string name)
    {
        var klass=Marshal.ReadIntPtr(obj);var key=klass.ToInt64()+":"+name;
        if(!offsets.TryGetValue(key,out var offset)){var f=api.Field(klass,name);if(f==IntPtr.Zero)throw new MissingFieldException(api.ClassName(klass),name);offset=api.FieldOffset(f);offsets[key]=offset;}return offset;
    }
    IntPtr P(IntPtr obj,string name)=>obj==IntPtr.Zero?IntPtr.Zero:Marshal.ReadIntPtr(obj,Offset(obj,name));
    int I(IntPtr obj,string name)=>obj==IntPtr.Zero?0:Marshal.ReadInt32(obj,Offset(obj,name));
    bool B(IntPtr obj,string name)=>obj!=IntPtr.Zero&&Marshal.ReadByte(obj,Offset(obj,name))!=0;
    float F(IntPtr obj,string name)=>obj==IntPtr.Zero?0:BitConverter.Int32BitsToSingle(Marshal.ReadInt32(obj,Offset(obj,name)));
    int RP(IntPtr obj)=>obj==IntPtr.Zero?0:Marshal.ReadInt32(obj,Offset(obj,"latestValue"));
    bool RB(IntPtr obj)=>obj!=IntPtr.Zero&&Marshal.ReadByte(obj,Offset(obj,"latestValue"))!=0;
    Dictionary<string,object?>? Parameter(IntPtr obj)=>obj==IntPtr.Zero?null:new(){["current"]=RP(P(obj,"<CurrentProperty>k__BackingField")),["max"]=RP(P(obj,"<MaxProperty>k__BackingField"))};

    static double Clock()=>Stopwatch.GetTimestamp()/(double)Stopwatch.Frequency;
    int Scene=>latest!=null&&latest.TryGetValue("scene_id",out var value)?Convert.ToInt32(value):-1;
    bool CombatReady=>player!=IntPtr.Zero&&latest!=null&&latest.TryGetValue("valid",out var valid)&&valid is true&&Clock()-lastSample<.6;
    Dictionary<string,object?> CombatHooks()=>new(){
        ["damage"]=installedHooks.Contains("DamageManager.UpdateDamageOne"),
        ["death_exists"]=installedHooks.Contains("EnemyDead.DiedButExists"),
        ["death_remove"]=installedHooks.Contains("EnemyDead.DeathOfExistence"),
        ["resume"]=installedHooks.Contains("EnemyDead.ResumeAlive")};
    Dictionary<string,object?> FlowHooks()=>new(){["request"]=installedHooks.Contains("EventManager.PlayEvent"),["stop"]=installedHooks.Contains("EventManager.StopEvent"),
        ["receiver_label"]=installedHooks.Contains("EventReceiver.CallEvent"),["execution_label"]=installedHooks.Contains("LabelEvent.LabelEvent_Execution")};
    void MarkDefeat(){defeatPlayer=P(eventManager,"<CurrentEventPlayer>k__BackingField");lastDefeatAt=Clock();}
    void ObserveLabel(IntPtr receiver,IntPtr text)
    {
        if(eventManager==IntPtr.Zero||!B(eventManager,"<IsEventPlaying>k__BackingField"))return;
        var label=api.String(text);if(label.Length==0)return;
        var now=Clock();var type=api.ObjectName(receiver);
        if(label==lastLabel&&type==lastLabelType&&now-lastLabelAt<.05)return;
        if(now-labelBudgetAt>=1){labelBudgetAt=now;labelBudget=0;}
        if(++labelBudget>40)return;
        lastLabel=label;lastLabelType=type;lastLabelAt=now;labelScene=Scene;labelPlayer=P(eventManager,"<CurrentEventPlayer>k__BackingField");
        Emit("flow_label_callback",new(){["label"]=label,["label_type"]=type,["scene_id"]=Scene});
    }
    Dictionary<string,object?> ReadFlow(IntPtr ev,IntPtr ui,int scene,bool loading)
    {
        var now=Clock();var current=P(ev,"<CurrentEventPlayer>k__BackingField");var playing=B(ev,"<IsEventPlaying>k__BackingField");
        var paused=B(ev,"<EventPause>k__BackingField")||RB(P(ui,"<IsPauseProp>k__BackingField"));
        if(playing&&(!flowWasPlaying||flowPlayer!=current||flowScene!=scene)){
            flowRun++;flowElapsed=0;flowStarted=now;
            if(labelScene!=scene||labelPlayer!=current||now-lastLabelAt>.25){lastLabel="";lastLabelType="";}
        }else if(playing&&!paused&&flowWasPlaying)flowElapsed+=Math.Clamp(now-lastFlowSample,0,1);
        flowPlayer=current;flowScene=scene;flowWasPlaying=playing;lastFlowSample=now;
        var name=playing?api.ObjectLabel(current):"";var type=api.ObjectName(current);
        var trigger=P(ev,"<CurrentBootEventTrigger>k__BackingField");var group=api.ObjectLabel(P(trigger,"<ParentGroup>k__BackingField"));
        var key=name.Length==0?"":JsonSerializer.Serialize(new object[]{scene,group,name,type});
        double? position=null,duration=null;var director=P(ev,"m_EventPlayableDirector");
        if(director!=IntPtr.Zero&&B(ev,"<IsPlayingPlayableDirector>k__BackingField")){
            // Optional Timeline getters can be stripped. Never discard core
            // playback identity when either optional query is unavailable.
            try{position=api.DoubleProperty(director,"get_time");}catch{}
            try{duration=api.DoubleProperty(director,"get_duration");}catch{}
        }
        return new(){["valid"]=!loading&&playing&&current!=IntPtr.Zero&&name.Length>0,["key"]=key,["name"]=name,["type"]=type,["group"]=group,
            ["playing"]=playing,["paused"]=paused,["run"]=flowRun,["elapsed"]=flowElapsed,["timeline_time"]=position,["timeline_duration"]=duration,
            ["label"]=playing?lastLabel:"",["label_type"]=playing?lastLabelType:"",["event_value"]=api.String(P(ev,"<EventStringValue>k__BackingField")),
            ["next_name"]=api.ObjectLabel(P(ev,"<NextEventPlayer>k__BackingField")),["restart_confirmed"]=B(ev,"<IsRestartConfirmed>k__BackingField"),
            ["boss_battle"]=RB(P(ev,"<IsBossBattleProp>k__BackingField")),["defeat_confirmed"]=playing&&defeatPlayer==current&&lastDefeatAt>=flowStarted-.25};
    }
    int EnemyHp(IntPtr enemy)=>RP(P(P(enemy,"<HP>k__BackingField"),"<CurrentProperty>k__BackingField"));
    int DeadState(IntPtr dead)=>dead==IntPtr.Zero?-1:RP(P(dead,"<StateProp>k__BackingField"));
    EnemyLife LifeOf(IntPtr enemy)
    {
        var address=enemy.ToInt64();var hp=P(enemy,"<HP>k__BackingField").ToInt64();var scene=Scene;
        if(!enemyLives.TryGetValue(address,out var life)||life.Scene!=scene||life.HpObject!=hp){
            if(enemyLives.Count>4096)enemyLives.Clear();
            life=new(){Id=++lifeSerial,HpObject=hp,Scene=scene};enemyLives[address]=life;
        }
        return life;
    }
    DamageObservation? BeginEnemyDamage(IntPtr stack)
    {
        if(!CombatReady||stack==IntPtr.Zero||I(stack,"m_DamageTargetType")!=1)return null;
        var enemy=P(stack,"m_Receiver");
        if(!api.IsA(enemy,enemyClass)||B(enemy,"<IsGalleryObject>k__BackingField")||!B(enemy,"<IsSetupEnd>k__BackingField"))return null;
        var hp=EnemyHp(enemy);var state=DeadState(P(enemy,"m_EnemyDead"));
        if(hp<=0||state!=0)return null;
        var sender=P(stack,"m_Sender");var collider=P(stack,"m_SenderCollider");var owner=P(collider,"<OwnerObject>k__BackingField");
        var life=LifeOf(enemy);life.Fatal=null;
        var observed=new DamageObservation{Enemy=enemy,Life=life,DamageId=++damageSerial,BeforeHp=hp,BeforeState=state,Scene=Scene,
            FromPlayer=sender==player||owner==player,Sender=api.ObjectName(sender),EnemyName=api.ObjectName(enemy)};
        observed.Hold=api.Hold(enemy);return observed;
    }
    void EndEnemyDamage(DamageObservation seen)
    {
        // This method surrounds applied damage, not merely collision/attack startup.
        if(seen.Scene!=Scene)return;
        var hpObject=P(seen.Enemy,"<HP>k__BackingField");
        var after=hpObject!=IntPtr.Zero?EnemyHp(seen.Enemy):seen.DeathHp??seen.BeforeHp;
        if(after<0||after>=seen.BeforeHp)return;
        var state=DeadState(P(seen.Enemy,"m_EnemyDead"));
        Emit("enemy_damage_callback",new(){["damage_id"]=seen.DamageId,["enemy_object"]=seen.Enemy.ToInt64(),["enemy_life"]=seen.Life.Id,
            ["enemy_class"]=seen.EnemyName,["scene_id"]=seen.Scene,["sender_class"]=seen.Sender,["source_is_player"]=seen.FromPlayer,
            ["before_hp"]=seen.BeforeHp,["remain_hp"]=after,["actual_damage"]=seen.BeforeHp-after,["dead_state_before"]=seen.BeforeState,["dead_state_after"]=state});
        if(after==0)seen.Life.Fatal=new(){DamageId=seen.DamageId,BeforeHp=seen.BeforeHp,FromPlayer=seen.FromPlayer,Sender=seen.Sender,Time=Clock()};
    }
    Dictionary<string,object?>? BeforeEnemyDeath(IntPtr dead)
    {
        if(!CombatReady)return null;
        var enemy=P(dead,"<EnemyObject>k__BackingField");
        if(!api.IsA(enemy,enemyClass)||B(enemy,"<IsGalleryObject>k__BackingField"))return null;
        var life=LifeOf(enemy);
        var data=new Dictionary<string,object?>{["enemy_object"]=enemy.ToInt64(),["enemy_life"]=life.Id,["enemy_class"]=api.ObjectName(enemy),
            ["scene_id"]=Scene,["dead_state_before"]=DeadState(dead),["hp_current"]=EnemyHp(enemy),["source_is_player"]=false};
        DamageObservation? source=activeDamage;
        while(source!=null&&(source.Enemy!=enemy||source.Scene!=Scene))source=source.Parent;
        if(source!=null){
            source.DeathHp=EnemyHp(enemy);
            data["damage_id"]=source.DamageId;data["source_is_player"]=source.FromPlayer;data["sender_class"]=source.Sender;
            data["fatal_before_hp"]=source.BeforeHp;data["fatal_after_hp"]=source.DeathHp;data["attribution"]="active_damage";
        }else if(life.Fatal is FatalHit fatal&&Clock()-fatal.Time<=5&&EnemyHp(enemy)==0){
            data["damage_id"]=fatal.DamageId;data["source_is_player"]=fatal.FromPlayer;data["sender_class"]=fatal.Sender;
            data["fatal_before_hp"]=fatal.BeforeHp;data["fatal_after_hp"]=0;data["attribution"]="same_life_fatal_damage";
        }else data["attribution"]="unconfirmed";
        return data;
    }
    void AfterEnemyDeath(IntPtr dead,Dictionary<string,object?>? data,bool notDefeat)
    {
        if(data==null)return;
        var before=Convert.ToInt32(data["dead_state_before"]);var after=DeadState(dead);
        // DiedButExists -> DeathOfExistence is one death, not two kills.
        if(before!=0||after is not (1 or 2))return;
        data["dead_state_after"]=after;data["not_defeat"]=notDefeat||B(dead,"<IsNotDefeat>k__BackingField");
        Emit("enemy_death_callback",data);
    }

    Dictionary<string,object?> ReadGallery(IntPtr root)
    {
        // Direct manager/UI fields only: no scene scanning or game mutations.
        var manager=P(root,"m_Gallery");var active=api.BoolProperty(manager,"get_IsActive")??false;
        var row=new Dictionary<string,object?>{["available"]=manager!=IntPtr.Zero,["active"]=active,["source"]="GalleryManager/ButtonGuideUI"};
        if(!active)return row;
        var ui=P(manager,"<GalleryUI>k__BackingField");var guide=P(ui,"m_ButtonGuideUI");
        var take=ResolveGalleryTake(manager,out var takeSource);
        var data=P(take,"<PlayingTakeData>k__BackingField");var enemy=P(guide,"<EnemyData>k__BackingField");
        var array=P(enemy,"m_AnimationTakeArray");var count=array==IntPtr.Zero?0:Math.Clamp(Marshal.ReadInt64(array,24),0,256);
        row["guide_available"]=guide!=IntPtr.Zero;row["guide_open"]=api.BoolProperty(guide,"get_IsOpen");
        row["ui_open"]=api.BoolProperty(ui,"get_IsOpen");row["changing"]=B(manager,"<IsChangingGalleryTake>k__BackingField")||B(guide,"<IsLoadScene>k__BackingField")||B(guide,"<IsUnLoadScene>k__BackingField");
        row["ui_paused"]=B(P(guide,"m_IsUIPauseProp"),"value");row["slow"]=B(P(guide,"m_IsUISlowProp"),"value");
        row["dev_mode"]=B(P(guide,"m_IsDevelopModeProp"),"value");row["ui_hidden"]=B(P(guide,"m_IsUIOffProp"),"value");
        row["selected_index_raw"]=I(guide,"<CurrentActiveIndex>k__BackingField");row["take_count"]=count;
        row["enemy_id"]=api.IntProperty(enemy,"get_GalleryEnemyID");row["enemy_name_id"]=I(enemy,"m_LocalizeID_Name");
        row["target_scene_id"]=I(guide,"<CurrentSceneID>k__BackingField");row["take_selected"]=take!=IntPtr.Zero&&data!=IntPtr.Zero;
        row["take_player"]=take.ToInt64();row["take_data"]=data.ToInt64();row["take_player_type"]=api.ObjectName(take);
        row["take_source"]=takeSource;
        row["take_name"]=api.String(P(data,"m_TakeName"));row["play_type_raw"]=I(data,"m_PlayType");
        row["animator_loop"]=B(data,"m_IsAnimatorLoop");row["combat_event"]=B(data,"m_IsCombatEvent");
        row["like_game_scene"]=B(data,"m_LikeGameSceneMode");row["accept_hp0"]=B(manager,"<AcceptHP0>k__BackingField");
        // A destroyed/unavailable global EventPlayer must not suppress gallery
        // take/session fields. Populate them on the same resolved take here.
        PopulateGalleryPlayback(row,manager,take,data);
        return row;
    }
    void Snapshot()
    {
        var now=Stopwatch.GetTimestamp()/(double)Stopwatch.Frequency;if(now-lastSample<.1)return;lastSample=now;
        var field=api.Field(managerClass,"<Instance>k__BackingField");api.StaticGet(field,out var root);
        if(root==IntPtr.Zero)return;
        var ps=P(root,"m_PlayerStatusManager");var om=P(root,"m_ObjectManager");var ui=P(root,"m_UIList");var seq=P(root,"m_Sequence");var ev=P(root,"m_EventManager");eventManager=ev;
        var leliaRp=P(om,"m_LeliaRp");var nextPlayer=P(leliaRp,"value");var nextAbnormal=P(ps,"<AbnormalList>k__BackingField");
        if(nextPlayer!=player){var hold=api.Hold(nextPlayer);api.Release(playerHandle);playerHandle=hold;player=nextPlayer;}
        if(nextAbnormal!=playerAbnormal){var hold=api.Hold(nextAbnormal);api.Release(abnormalHandle);abnormalHandle=hold;playerAbnormal=nextAbnormal;}
        var hp=P(ps,"<HP>k__BackingField");var dress=P(ps,"<DressCondition>k__BackingField");var change=P(seq,"<ChangeSceneProc>k__BackingField");var bind=P(player,"m_Bind");var gb=P(player,"m_GachaBind");var gs=P(gb,"<GachaSystem>k__BackingField");var gparam=P(gs,"m_Parameter");
        var scene=I(seq,"<ActvieSceneID>k__BackingField");var loading=B(change,"<IsActive>k__BackingField");
        var valid=player!=IntPtr.Zero&&!loading&&B(player,"<IsSetupEnd>k__BackingField")&&P(player,"<HP>k__BackingField")==hp;
        var abnormal=new List<Dictionary<string,object?>>();var array=P(playerAbnormal,"<AddedArray>k__BackingField");
        if(array!=IntPtr.Zero)
        {
            var count=Math.Min(64,(int)Marshal.ReadInt64(array,24));
            for(var i=0;i<count;i++){var a=Marshal.ReadIntPtr(array,32+i*8);if(a!=IntPtr.Zero){
                var row=new Dictionary<string,object?>{["type_raw"]=I(a,"m_AbnormalType"),["level"]=RP(P(a,"<LevelRp>k__BackingField"))};
                Guard(()=>{row["name_id"]=api.IntProperty(a,"get_AbnormalNameID");row["max_level"]=api.IntProperty(a,"get_MaxLevel");
                    var timer=F(a,"<DeleteTimer>k__BackingField");var configured=F(a,"m_DeleteTime");
                    row["delete_timer"]=float.IsFinite(timer)?timer:null;row["delete_time"]=float.IsFinite(configured)?configured:null;
                    row["remove_on_scene_change"]=B(a,"m_RemoveWhenChangeScene");});abnormal.Add(row);
            }}
        }
        var data=new Dictionary<string,object?>{
            ["schema"]=1,["source"]="bepinex",["fingerprint"]=gameFingerprint,["build_profile"]=buildProfile,["compatibility"]=compatibilityData,["session"]=session,["pid"]=Environment.ProcessId,["sample_id"]=++sample,["utc"]=DateTimeOffset.UtcNow.ToString("O"),["valid"]=valid,["player"]=player.ToInt64(),["scene_id"]=scene,["loading"]=loading,["observer_version"]="0.8.0",["combat_hooks"]=CombatHooks(),["flow_hooks"]=FlowHooks(),
            ["hp"]=Parameter(hp),["mp"]=Parameter(P(ps,"<MP>k__BackingField")),["durability"]=Parameter(P(ps,"<Durability>k__BackingField")),["paused"]=RB(P(ui,"<IsPauseProp>k__BackingField")),
            ["event_playing"]=B(ev,"<IsEventPlaying>k__BackingField"),["event_paused"]=B(ev,"<EventPause>k__BackingField"),["broken"]=RB(P(dress,"<IsBrokenRp>k__BackingField")),["bound"]=false,
            ["binder"]=api.ObjectName(P(bind,"<BinderEnemy>k__BackingField")),["abnormals"]=abnormal,["hook_count"]=hooks.Count};
        // ReactiveProperty<T>.value is read separately from ReadOnlyReactiveProperty<T>.latestValue.
        var boundRp=P(bind,"m_IsBoundRP");data["bound"]=boundRp!=IntPtr.Zero&&B(boundRp,"value");
        var la=P(player,"<LeliaAnimation>k__BackingField");data["anim_raw"]=I(la,"<CurrentAnimState>k__BackingField");
        var active=P(gs,"m_IsActive");var difficulty=RP(P(ps,"<GameDifficultyRP>k__BackingField"));var threshold=difficulty==2&&B(gparam,"m_HardOverwrite")?F(gparam,"m_SuccessValueHard"):F(gparam,"m_SuccessValue");
        data["gacha"]=gs==IntPtr.Zero?null:new Dictionary<string,object?>{["active"]=active!=IntPtr.Zero&&B(active,"value"),["value"]=F(gs,"<CurrentValue>k__BackingField"),["threshold"]=threshold};
        var tm=P(root,"m_TimeManager");var rates=P(tm,"<TimeRateArray>k__BackingField");
        if(rates!=IntPtr.Zero&&Marshal.ReadInt64(rates,24)>1){var setting=Marshal.ReadIntPtr(rates,40);var prop=P(setting,"<ScaleProp>k__BackingField");data["time_scale"]=F(prop,"latestValue");}
        Guard(()=>data["flow"]=ReadFlow(ev,ui,scene,loading));
        try{data["gallery"]=ReadGallery(root);}catch(Exception e){data["gallery"]=new Dictionary<string,object?>{["available"]=false,["error"]=e.Message};}
        try{data["cg_playback"]=ReadCgObservation(root,ev,scene,data);}catch(Exception e){data["cg_playback"]=new Dictionary<string,object?>{["available"]=false,["error"]=e.Message};}
        latest=data;
    }
    void WriteLoop()
    {
        var path=Path.Combine(directory,"latest.json");var eventPath=Path.Combine(directory,"events.jsonl");long written=0;
        while(!stopping)
        {
            try
            {
                var state=latest;
                if(state!=null&&Convert.ToInt64(state["sample_id"])!=written){var temp=path+".tmp";File.WriteAllText(temp,JsonSerializer.Serialize(state,json));File.Move(temp,path,true);written=Convert.ToInt64(state["sample_id"]);}
                using(var file=new StreamWriter(eventPath,true)){while(events.TryDequeue(out var e))file.WriteLine(JsonSerializer.Serialize(e,json));}
            }
            catch(Exception e){if(++readFailures<=5)Log.LogWarning("IPC: "+e.Message);}
            Thread.Sleep(50);
        }
    }
    public override bool Unload(){stopping=true;writer?.Join(1000);for(var i=hooks.Count-1;i>=0;i--)hooks[i].Dispose();if(api!=null){ReleaseCgObservation();api.Release(playerHandle);api.Release(abnormalHandle);}return true;}
}

internal sealed partial class Native
{
    readonly IntPtr module;
    readonly Dictionary<string,Delegate> exportCache=new();
    readonly Dictionary<string,IntPtr> accessors=new();
    IntPtr objectNameGetter;
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr RuntimeInvoke(IntPtr method,IntPtr self,IntPtr args,out IntPtr exception);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr NoArg();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Assemblies(IntPtr domain,out nuint size);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr One(IntPtr a);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Named(IntPtr a,[MarshalAs(UnmanagedType.LPStr)]string name);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr ClassLookup(IntPtr image,[MarshalAs(UnmanagedType.LPStr)]string ns,[MarshalAs(UnmanagedType.LPStr)]string name);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Iterator(IntPtr a,ref IntPtr iterator);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Count(IntPtr a);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Parameter(IntPtr method,uint index);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint GetOffset(IntPtr field);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] internal delegate void StaticRead(IntPtr field,out IntPtr value);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint NewHandle(IntPtr obj,[MarshalAs(UnmanagedType.I1)]bool pinned);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate void FreeHandle(uint handle);
    readonly NewHandle newHandle;readonly FreeHandle freeHandle;
    internal uint Hold(IntPtr obj)=>obj==IntPtr.Zero?0:newHandle(obj,false);
    internal void Release(uint handle){if(handle!=0)freeHandle(handle);}
    readonly NoArg domain;readonly Assemblies assemblies;readonly One image,parent,className,methodName,typeName;readonly ClassLookup lookup;readonly Named getField;readonly Iterator nested,methods;readonly Count paramCount;readonly Parameter param;readonly GetOffset fieldOffset;
    internal readonly StaticRead StaticGet;
    T Export<T>(string name)where T:Delegate{
        if(exportCache.TryGetValue(name,out var cached))return (T)cached;
        var value=Marshal.GetDelegateForFunctionPointer<T>(NativeLibrary.GetExport(module,name));exportCache[name]=value;return value;
    }
    internal Native(){module=NativeLibrary.Load("GameAssembly.dll");newHandle=Export<NewHandle>("il2cpp_gchandle_new");freeHandle=Export<FreeHandle>("il2cpp_gchandle_free");domain=Export<NoArg>("il2cpp_domain_get");assemblies=Export<Assemblies>("il2cpp_domain_get_assemblies");image=Export<One>("il2cpp_assembly_get_image");lookup=Export<ClassLookup>("il2cpp_class_from_name");parent=Export<One>("il2cpp_class_get_parent");className=Export<One>("il2cpp_class_get_name");getField=Export<Named>("il2cpp_class_get_field_from_name");nested=Export<Iterator>("il2cpp_class_get_nested_types");methods=Export<Iterator>("il2cpp_class_get_methods");methodName=Export<One>("il2cpp_method_get_name");paramCount=Export<Count>("il2cpp_method_get_param_count");param=Export<Parameter>("il2cpp_method_get_param");typeName=Export<One>("il2cpp_type_get_name");fieldOffset=Export<GetOffset>("il2cpp_field_get_offset");StaticGet=Export<StaticRead>("il2cpp_field_static_get_value");}
    internal string ClassName(IntPtr k)=>k==IntPtr.Zero?"":Marshal.PtrToStringAnsi(className(k))??"";
    internal string ObjectName(IntPtr o)=>o==IntPtr.Zero?"":ClassName(Marshal.ReadIntPtr(o));
    internal string String(IntPtr value){
        if(value==IntPtr.Zero)return "";
        var count=(int)Math.Min(Export<Count>("il2cpp_string_length")(value),180);
        return count==0?"":Marshal.PtrToStringUni(Export<One>("il2cpp_string_chars")(value),count)??"";
    }
    IntPtr Invoke(IntPtr self,IntPtr method){
        var result=Export<RuntimeInvoke>("il2cpp_runtime_invoke")(method,self,IntPtr.Zero,out var exception);
        if(exception!=IntPtr.Zero)throw new InvalidOperationException("Read-only property threw an IL2CPP exception");return result;
    }
    IntPtr PropertyMethod(IntPtr obj,string name){
        var klass=Marshal.ReadIntPtr(obj);var key=klass.ToInt64()+":"+name;
        if(!accessors.TryGetValue(key,out var method)){
            var search=klass;
            while(search!=IntPtr.Zero){try{method=Method(search,name,0);break;}catch(MissingMethodException){search=parent(search);}}
            if(method==IntPtr.Zero)throw new MissingMethodException(ClassName(klass),name);accessors[key]=method;
        }return method;
    }
    internal string ObjectLabel(IntPtr obj){
        if(obj==IntPtr.Zero)return "";
        try{
            if(objectNameGetter==IntPtr.Zero)objectNameGetter=Method(Class("UnityEngine","Object"),"get_name",0);
            return String(Invoke(obj,objectNameGetter));
        }catch{return "";}
    }
    internal int? IntProperty(IntPtr obj,string name){
        if(obj==IntPtr.Zero)return null;var box=Invoke(obj,PropertyMethod(obj,name));
        return box==IntPtr.Zero?null:Marshal.ReadInt32(Export<One>("il2cpp_object_unbox")(box));
    }
    internal bool? BoolProperty(IntPtr obj,string name){
        if(obj==IntPtr.Zero)return null;var box=Invoke(obj,PropertyMethod(obj,name));
        return box==IntPtr.Zero?null:Marshal.ReadByte(Export<One>("il2cpp_object_unbox")(box))!=0;
    }
    internal double? DoubleProperty(IntPtr obj,string name){
        if(obj==IntPtr.Zero)return null;var box=Invoke(obj,PropertyMethod(obj,name));if(box==IntPtr.Zero)return null;
        var value=BitConverter.Int64BitsToDouble(Marshal.ReadInt64(Export<One>("il2cpp_object_unbox")(box)));
        return double.IsFinite(value)&&value>=0&&value<=864000?value:null;
    }
    internal bool IsA(IntPtr o,IntPtr expected){var k=o==IntPtr.Zero?IntPtr.Zero:Marshal.ReadIntPtr(o);while(k!=IntPtr.Zero){if(k==expected)return true;k=parent(k);}return false;}
    internal IntPtr Class(string ns,string name){var list=assemblies(domain(),out var count);for(var i=0;i<(int)count;i++){var c=lookup(image(Marshal.ReadIntPtr(list,i*8)),ns,name);if(c!=IntPtr.Zero)return c;}throw new TypeLoadException(ns+"."+name);}
    internal IntPtr Nested(IntPtr klass,string name){IntPtr iter=IntPtr.Zero,c;while((c=nested(klass,ref iter))!=IntPtr.Zero)if(ClassName(c)==name)return c;throw new TypeLoadException(name);}
    internal IntPtr Field(IntPtr klass,string name){while(klass!=IntPtr.Zero){var f=getField(klass,name);if(f!=IntPtr.Zero)return f;klass=parent(klass);}return IntPtr.Zero;}
    internal int FieldOffset(IntPtr f)=>(int)fieldOffset(f);
    internal IntPtr Method(IntPtr klass,string name,uint count,string? firstType=null){IntPtr iter=IntPtr.Zero,m;while((m=methods(klass,ref iter))!=IntPtr.Zero)if(Marshal.PtrToStringAnsi(methodName(m))==name&&paramCount(m)==count&&(firstType==null||(Marshal.PtrToStringAnsi(typeName(param(m,0)))??"").EndsWith(firstType)))return m;throw new MissingMethodException(ClassName(klass),name);}
}
