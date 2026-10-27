// GPL-3.0-only. Read declared CG references and their live playback state.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Runtime.InteropServices;

namespace SiNiSistarDGLab;

public sealed partial class Plugin
{
    sealed class CgTakeRef
    {
        internal IntPtr Object,Array;
        internal uint Hold;
        internal readonly List<CgAnimatorRef> Animators=new();
    }
    sealed class CgAnimatorRef
    {
        internal IntPtr Animator;
        internal string Take="";
        internal string[] Queue=Array.Empty<string>();
    }
    readonly Dictionary<long,CgTakeRef> cgTakes=new();
    int cgPathScene=-1;
    IntPtr ResolveGalleryTake(IntPtr manager,out string source)
    {
        var ui=P(manager,"<GalleryUI>k__BackingField");var guide=P(ui,"m_ButtonGuideUI");
        var selected=P(guide,"<TakePlayer>k__BackingField");var current=P(manager,"<CurrentTakePlayer>k__BackingField");
        // Enemy/Animator takes can belong solely to the button guide. Both
        // basic gallery fields and extended playback reads must use one owner.
        if(selected!=IntPtr.Zero&&(api.BoolProperty(guide,"get_IsOpen") is true||current==IntPtr.Zero)){
            source="button_guide";return selected;
        }
        source=current!=IntPtr.Zero?"manager":"none";return current;
    }
    void InstallCgObservation()
    {
        Install("GaTakePlayer.Awake",()=>{
            V0 original=null!;V0 callback=(self,method)=>{original(self,method);Guard(()=>RegisterCgTake(self));};
            Attach(api.Method(api.Class("SiNiSistar2.Manager.Gallery","GaTakePlayer"),"Awake",0),callback,out original);
        });
        Install("GaTakePlayer.OnDestroy",()=>{
            V0 original=null!;V0 callback=(self,method)=>{Guard(()=>RemoveCgTake(self));original(self,method);};
            Attach(api.Method(api.Class("SiNiSistar2.Manager.Gallery","GaTakePlayer"),"OnDestroy",0),callback,out original);
        });
    }
    IEnumerable<IntPtr> CgArray(IntPtr array,int maximum=256)
    {
        if(array==IntPtr.Zero)yield break;
        long count=Marshal.ReadInt64(array,24);if(count<0||count>maximum)yield break;
        for(int i=0;i<count;i++){var item=Marshal.ReadIntPtr(array,32+i*8);if(item!=IntPtr.Zero)yield return item;}
    }
    void RegisterCgTake(IntPtr obj)
    {
        if(obj==IntPtr.Zero)return;
        if(!cgTakes.TryGetValue(obj.ToInt64(),out var entry)){
            if(cgTakes.Count>=64)return;
            entry=new(){Object=obj,Hold=api.Hold(obj)};cgTakes[obj.ToInt64()]=entry;
        }
        var array=P(obj,"m_TakeDataArray");if(array==entry.Array)return;
        entry.Array=array;entry.Animators.Clear();
        foreach(var data in CgArray(array)){
            var animator=P(data,"m_Animator");if(animator==IntPtr.Zero||I(data,"m_PlayType")!=0)continue;
            entry.Animators.Add(new(){Animator=animator,Take=api.String(P(data,"m_TakeName")),
                Queue=CgArray(P(data,"m_QueueArray"),128).Select(api.String).Where(s=>s.Length>0).ToArray()});
        }
    }
    void RemoveCgTake(IntPtr obj){if(cgTakes.Remove(obj.ToInt64(),out var entry))api.Release(entry.Hold);api.ClearCgPaths();}
    void ReleaseCgObservation(){foreach(var entry in cgTakes.Values)api.Release(entry.Hold);cgTakes.Clear();ReleaseSharedCgObservation();}
    void PopulateGalleryPlayback(Dictionary<string,object?> g,IntPtr gallery,IntPtr take,IntPtr data)
    {
        if(take==IntPtr.Zero||data==IntPtr.Zero)return;
        try{g["owner_path"]=api.ComponentIdentity(take)["path"];}
        catch(Exception e){g["owner_error"]=e.Message;}
        try{g["take_object_active"]=api.BoolProperty(take,"get_isActiveAndEnabled");}
        catch(Exception e){g["take_object_active"]=false;g["active_error"]=e.Message;}
        var token=P(gallery,"<TakeTokenSource>k__BackingField");
        try{g["take_token_active"]=token!=IntPtr.Zero&&api.BoolProperty(token,"get_IsCancellationRequested") is false;}
        catch(Exception e){g["take_token_active"]=false;g["token_error"]=e.Message;}
        if(I(data,"m_PlayType")==0){
            try{g["animator"]=api.ReadCgAnimator(P(data,"m_Animator"),CgArray(P(data,"m_QueueArray"),128).Select(api.String).ToArray());}
            catch(Exception e){g["animator"]=new Dictionary<string,object?>{["available"]=false,["error"]=e.Message};}
        }
    }
    Dictionary<string,object?> ReadCgObservation(IntPtr root,IntPtr manager,int scene,Dictionary<string,object?> snapshot)
    {
        var started=Clock();if(scene!=cgPathScene){cgPathScene=scene;api.ClearCgPaths();}
        var result=new Dictionary<string,object?>{["schema"]=1,["available"]=true,["source"]="declared CG references",["hp_used"]=false,
            ["take_hook"]=installedHooks.Contains("GaTakePlayer.Awake"),["catalog_take_owners"]=cgTakes.Count};
        var current=P(manager,"<CurrentEventPlayer>k__BackingField");
        Dictionary<string,object?> eventRow;
        try{
            eventRow=api.ComponentIdentity(current);
            eventRow["playing"]=current!=IntPtr.Zero&&B(current,"<IsPlaying>k__BackingField")&&B(manager,"<IsEventPlaying>k__BackingField");
        }catch(Exception e){eventRow=new(){["playing"]=false,["error"]=e.Message};}
        result["event"]=eventRow;
        try{result["shared_animators"]=ReadSharedCgAnimators(current,scene,eventRow.TryGetValue("playing",out var playing)&&playing is true,result);}
        catch(Exception error){ReleaseSharedCgObservation();result["shared_animators"]=Array.Empty<object>();result["shared_animation_error"]=error.Message;}
        var gallery=P(root,"m_Gallery");var galleryTake=ResolveGalleryTake(gallery,out var takeSource);
        if(galleryTake!=IntPtr.Zero){try{RegisterCgTake(galleryTake);}catch(Exception e){result["take_registry_error"]=e.Message;}}
        var active=new List<Dictionary<string,object?>>();var errors=new List<string>();int checkedCount=0;
        var declared=new List<CgAnimatorRef>();
        foreach(var owner in cgTakes.Values.ToArray()){
            try{RegisterCgTake(owner.Object);declared.AddRange(owner.Animators);}
            catch(Exception e){if(errors.Count<4)errors.Add(e.Message);}
        }
        foreach(var group in declared.GroupBy(entry=>entry.Animator).Take(128)){
                checkedCount++;
                var animator=group.Key;
                try{
                    if(api.BoolProperty(animator,"get_isActiveAndEnabled") is not true)continue;
                    var row=api.ReadCgAnimator(animator,group.SelectMany(e=>e.Queue).Distinct().ToArray());row["take_names"]=group.Select(e=>e.Take).Distinct().ToArray();active.Add(row);
                }catch(Exception e){if(errors.Count<4)errors.Add(e.Message);}
        }
        result["animators"]=active;result["animator_errors"]=errors;result["truncated"]=declared.Select(e=>e.Animator).Distinct().Count()>128;
        result["read_ms"]=Math.Round((Clock()-started)*1000,3);return result;
    }
}

internal sealed partial class Native
{
    IntPtr cgStateMethod,cgHashMethod;
    readonly Dictionary<long,string> cgPaths=new();
    readonly Dictionary<string,int> cgHashes=new();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Utf8String([MarshalAs(UnmanagedType.LPUTF8Str)]string value);
    internal void ClearCgPaths()=>cgPaths.Clear();
    internal IntPtr ObjectProperty(IntPtr obj,string name)=>obj==IntPtr.Zero?IntPtr.Zero:Invoke(obj,PropertyMethod(obj,name));
    internal Dictionary<string,object?> ComponentIdentity(IntPtr obj)
    {
        var path="";
        if(obj!=IntPtr.Zero&&!cgPaths.TryGetValue(obj.ToInt64(),out path!)){
            var transform=ObjectProperty(obj,"get_transform");var names=new List<string>();var seen=new HashSet<long>();
            while(transform!=IntPtr.Zero&&names.Count<40&&seen.Add(transform.ToInt64())){
                names.Add(ObjectLabel(transform));transform=ObjectProperty(transform,"get_parent");
            }
            names.Reverse();path=string.Join("/",names);if(cgPaths.Count<2048)cgPaths[obj.ToInt64()]=path;
        }
        return new(){["object"]=obj.ToInt64(),["type"]=ObjectName(obj),["path"]=path};
    }
    IntPtr InvokeArguments(IntPtr obj,IntPtr method,IntPtr[] arguments)
    {
        var memory=Marshal.AllocHGlobal(arguments.Length*IntPtr.Size);
        try{
            Marshal.Copy(arguments,0,memory,arguments.Length);
            var value=Export<RuntimeInvoke>("il2cpp_runtime_invoke")(method,obj,memory,out var exception);
            if(exception!=IntPtr.Zero)throw new InvalidOperationException("Read-only CG query threw an IL2CPP exception");return value;
        }finally{Marshal.FreeHGlobal(memory);}
    }
    IntPtr AnimatorState(IntPtr animator,int layer)
    {
        var memory=Marshal.AllocHGlobal(4);
        try{if(cgStateMethod==IntPtr.Zero)cgStateMethod=Method(Class("UnityEngine","Animator"),"GetCurrentAnimatorStateInfo",1);Marshal.WriteInt32(memory,layer);return InvokeArguments(animator,cgStateMethod,new[]{memory});}
        finally{Marshal.FreeHGlobal(memory);}
    }
    int AnimatorHash(string name)
    {
        if(cgHashes.TryGetValue(name,out var hash))return hash;
        var text=Export<Utf8String>("il2cpp_string_new")(name);
        if(cgHashMethod==IntPtr.Zero)cgHashMethod=Method(Class("UnityEngine","Animator"),"StringToHash",1);
        var hold=Hold(text);IntPtr value;
        try{value=InvokeArguments(IntPtr.Zero,cgHashMethod,new[]{text});}finally{Release(hold);}
        if(value==IntPtr.Zero)throw new InvalidOperationException("Animator hash unavailable");
        var boxedHold=Hold(value);
        try{hash=Marshal.ReadInt32(Export<One>("il2cpp_object_unbox")(value));}
        finally{Release(boxedHold);}
        if(cgHashes.Count<4096)cgHashes[name]=hash;return hash;
    }
    internal Dictionary<string,object?> ReadCgAnimator(IntPtr animator,string[] names,int? onlyLayer=null)
    {
        if(animator==IntPtr.Zero)return new(){["available"]=false,["error"]="No declared animator"};
        var row=ComponentIdentity(animator);var enabled=BoolProperty(animator,"get_isActiveAndEnabled") is true;
        row["available"]=true;row["active"]=enabled;row["controller"]=ObjectLabel(ObjectProperty(animator,"get_runtimeAnimatorController"));
        row["declared_queue"]=names;var matches=new List<string>();row["matched_names"]=matches;
        if(!enabled)return row;
        int count=Math.Clamp(IntProperty(animator,"get_layerCount")??0,0,4);
        for(int layer=onlyLayer??0;layer<count&&(!onlyLayer.HasValue||layer==onlyLayer.Value);layer++){
            var box=AnimatorState(animator,layer);if(box==IntPtr.Zero)continue;
            var stateHold=Hold(box);
            try{
            if(ObjectName(box)!="AnimatorStateInfo")throw new InvalidOperationException("Unexpected Animator state value type");
            var klass=Marshal.ReadIntPtr(box);var raw=Export<One>("il2cpp_object_unbox")(box);
            var firstField=Field(klass,"m_Name");if(raw==IntPtr.Zero||firstField==IntPtr.Zero)throw new MissingFieldException("AnimatorStateInfo.m_Name");
            int first=FieldOffset(firstField);
            int Integer(string name){var field=Field(klass,name);if(field==IntPtr.Zero)throw new MissingFieldException("AnimatorStateInfo."+name);
                int offset=FieldOffset(field)-first;if(offset<0||offset>128)throw new InvalidOperationException("Unexpected Animator state layout");return Marshal.ReadInt32(raw,offset);}
            float Single(string name)=>BitConverter.Int32BitsToSingle(Integer(name));
            int shortHash=Integer("m_Name"),fullHash=Integer("m_FullPath"),pathHash=Integer("m_Path");
            var found=names.Where(n=>{int hash=AnimatorHash(n);return hash!=0&&(hash==shortHash||hash==fullHash||hash==pathHash);}).ToArray();
            if(layer==0||found.Length>0){
                row["short_hash"]=shortHash;row["full_hash"]=fullHash;row["layer"]=layer;
                float time=Single("m_NormalizedTime"),length=Single("m_Length");
                row["normalized_time"]=float.IsFinite(time)?time:null;row["length"]=float.IsFinite(length)?length:null;
            }
            matches.AddRange(found);
            }finally{Release(stateHold);}
        }
        return row;
    }
}
