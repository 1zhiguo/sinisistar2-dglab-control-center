// GPL-3.0-only. Read active event receivers and the Animator states they reference.
// No new native detours, animation calls, scene searches or game-value writes.
using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.InteropServices;

namespace SiNiSistarDGLab;

public sealed partial class Plugin
{
    sealed class SharedCgActor
    {
        internal IntPtr Animator;
        internal int Layer;
        internal readonly HashSet<string> States=new();
        internal readonly HashSet<string> Labels=new();
    }
    readonly List<SharedCgActor> sharedCgActors=new();
    (int Scene,long Player,long Receiver,long Array,int Count) sharedCgKey;
    uint sharedCgReceiverHandle;
    double sharedCgReadAt;
    bool sharedCgTruncated;

    IEnumerable<IntPtr> CgList(IntPtr list,int maximum=256)
    {
        if(list==IntPtr.Zero)yield break;
        int size=I(list,"_size");var array=P(list,"_items");
        if(size<0||size>4096||array==IntPtr.Zero)yield break;
        long length=Marshal.ReadInt64(array,24);
        if(length<size||length>16384)yield break;
        for(int i=0;i<Math.Min(size,maximum);i++){
            var value=Marshal.ReadIntPtr(array,32+i*8);if(value!=IntPtr.Zero)yield return value;
        }
    }

    void ReleaseSharedCgObservation()
    {
        sharedCgActors.Clear();api.Release(sharedCgReceiverHandle);sharedCgReceiverHandle=0;
        sharedCgKey=default;sharedCgReadAt=0;sharedCgTruncated=false;
    }

    List<Dictionary<string,object?>> ReadSharedCgAnimators(IntPtr current,int scene,bool playing,
        Dictionary<string,object?> observation)
    {
        var result=new List<Dictionary<string,object?>>();
        observation["shared_animation_schema"]=1;
        if(!playing||current==IntPtr.Zero||api.ObjectName(current)!="HierarchyEventPlayer"){
            ReleaseSharedCgObservation();return result;
        }
        var receiver=P(current,"m_Receiver");
        if(receiver==IntPtr.Zero){ReleaseSharedCgObservation();observation["shared_animation_status"]="awaiting-event-receiver";return result;}
        var labels=P(receiver,"<LabelEvents>k__BackingField");
        if(labels==IntPtr.Zero){ReleaseSharedCgObservation();observation["shared_animation_status"]="awaiting-receiver-labels";return result;}
        var key=(scene,current.ToInt64(),receiver.ToInt64(),P(labels,"_items").ToInt64(),I(labels,"_size"));
        if(key!=sharedCgKey||Clock()-sharedCgReadAt>2){
            ReleaseSharedCgObservation();sharedCgKey=key;sharedCgReceiverHandle=api.Hold(receiver);sharedCgReadAt=Clock();
            sharedCgTruncated=key.Item5>256;
            var actors=new Dictionary<(long,int),SharedCgActor>();
            foreach(var label in CgList(labels)){
                var type=api.ObjectName(label);
                if(type is not ("AnimatorTriggerLabel" or "AnimatorTriggerAsyncLabel"))continue;
                foreach(var parameter in CgArray(P(label,"m_Parameters"),128)){
                    var animator=P(parameter,"m_Animator");var state=api.String(P(parameter,"m_PlayName"));
                    if(animator==IntPtr.Zero||state.Length==0)continue; // No guessed search-target resolution.
                    int layer=I(parameter,"m_LayerIndex");if(layer< -1||layer>=4)continue;
                    var identity=(animator.ToInt64(),layer);
                    if(!actors.TryGetValue(identity,out var actor)){
                        if(actors.Count>=16){sharedCgTruncated=true;continue;}
                        actor=new(){Animator=animator,Layer=layer};actors.Add(identity,actor);
                    }
                    actor.States.Add(state);
                    if(actor.Labels.Count<16)actor.Labels.Add(Convert.ToString(api.ComponentIdentity(label)["path"])??"");
                }
            }
            sharedCgActors.AddRange(actors.Values);
        }
        var errors=new List<string>();
        foreach(var actor in sharedCgActors){
            try{
                var row=api.ReadCgAnimator(actor.Animator,actor.States.ToArray(),actor.Layer<0?null:actor.Layer);
                row["source"]="active_event_receiver";row["owner_event_object"]=current.ToInt64();
                row["receiver_object"]=receiver.ToInt64();row["action_labels"]=actor.Labels.ToArray();
                result.Add(row);
            }catch(Exception error){if(errors.Count<4)errors.Add(error.Message);}
        }
        observation["shared_animation_status"]="read-active-event-receiver";
        observation["shared_animation_errors"]=errors;observation["shared_animation_truncated"]=sharedCgTruncated;
        return result;
    }
}
