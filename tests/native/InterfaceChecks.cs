// Exercises the same validator embedded in the observer, without loading a game.
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using SiNiSistarCompatibility;
using C=SiNiSistarCompatibility.RuntimeInterface;

sealed class FakeMetadata:C.IMetadata
{
    internal readonly Dictionary<string,IntPtr> Types=new();
    internal readonly HashSet<string> Exports=new();
    internal readonly Dictionary<IntPtr,string> Kinds=new();
    internal readonly Dictionary<(IntPtr,string),C.FieldShape> Fields=new();
    internal readonly Dictionary<(IntPtr,string),List<C.MethodShape>> MethodsByName=new();
    internal FakeMetadata(byte[] bytes)
    {
        using var document=JsonDocument.Parse(bytes);long id=1;
        foreach(var export in document.RootElement.GetProperty("exports").EnumerateArray())Exports.Add(export.GetString()!);
        foreach(var t in document.RootElement.GetProperty("types").EnumerateArray()){
            var klass=new IntPtr(id++);Types[t.GetProperty("ns").GetString()+"|"+t.GetProperty("name").GetString()]=klass;
            Kinds[klass]=t.GetProperty("kind").GetString()!;
            foreach(var f in t.GetProperty("fields").EnumerateArray())Fields[(klass,f.GetProperty("name").GetString()!)]=new(f.GetProperty("type").GetString()!,f.GetProperty("static").GetBoolean(),f.TryGetProperty("value",out var value)?value.GetInt32():null);
            foreach(var m in t.GetProperty("methods").EnumerateArray()){
                var key=(klass,m.GetProperty("name").GetString()!);if(!MethodsByName.ContainsKey(key))MethodsByName[key]=new();
                MethodsByName[key].Add(new(key.Item2,m.GetProperty("returns").GetString()!,m.GetProperty("parameters").EnumerateArray().Select(x=>x.GetString()!).ToArray(),m.GetProperty("static").GetBoolean(),new IntPtr(id++)));
            }
        }
    }
    public IntPtr Class(string ns,string name)=>Types.GetValueOrDefault(ns+"|"+name);
    public bool HasExport(string name)=>Exports.Contains(name);
    public string ClassKind(IntPtr klass)=>Kinds[klass];
    public C.FieldShape? Field(IntPtr type,string name,bool constant)=>Fields.GetValueOrDefault((type,name));
    public IEnumerable<C.MethodShape> Methods(IntPtr type,string name)=>MethodsByName.GetValueOrDefault((type,name))??Enumerable.Empty<C.MethodShape>();
}
static class InterfaceChecks
{
    static void Main()
    {
        var bytes=C.ContractBytes();int checks=0;
        void Pass(bool ok,string label){checks++;if(!ok)throw new Exception(label);}
        var baseline=new FakeMetadata(bytes);var good=C.Check(baseline,bytes);Pass(good.Compatible,"baseline");Pass(good.Fields>600&&good.MethodCount>=38,"contract coverage");
        foreach(var (label,change) in new (string,Action<FakeMetadata>)[]{
            ("required IL2CPP export",m=>m.Exports.Remove("il2cpp_runtime_invoke")),
            ("missing class",m=>m.Types.Remove("SiNiSistar2.Obj|Lelia")),
            ("value type ABI",m=>m.Kinds[m.Types["SiNiSistar2.Obj|Lelia"]]="struct"),
            ("field missing",m=>m.Fields.Remove((m.Types["SiNiSistar2.Manager|ManagerList"],"m_Sequence"))),
            ("field type",m=>{var key=(m.Types["SiNiSistar2.Manager|ManagerList"],"m_Sequence");m.Fields[key]=m.Fields[key] with {Type="int"};}),
            ("field static",m=>{var key=(m.Types["SiNiSistar2.Manager|ManagerList"],"m_Sequence");m.Fields[key]=m.Fields[key] with {Static=true};}),
            ("enum value",m=>{var key=m.Fields.Keys.First(k=>m.Fields[k].Constant!=null);m.Fields[key]=m.Fields[key] with {Constant=m.Fields[key].Constant+1};}),
            ("method missing",m=>m.MethodsByName.Remove((m.Types["SiNiSistar2.Obj|ObjectManager"],"Update"))),
            ("return ABI",m=>{var key=(m.Types["SiNiSistar2.Obj|ObjectManager"],"Update");m.MethodsByName[key][0]=m.MethodsByName[key][0] with {Returns="int"};}),
            ("parameter ABI",m=>{var key=(m.Types["SiNiSistar2.UI|RedAlert"],"ShowGameOver");m.MethodsByName[key][0]=m.MethodsByName[key][0] with {Parameters=new[]{"int"}};}),
            ("static ABI",m=>{var key=(m.Types["SiNiSistar2.Obj|ObjectManager"],"Update");m.MethodsByName[key][0]=m.MethodsByName[key][0] with {Static=true};}),
            ("ambiguous overload",m=>{var key=(m.Types["SiNiSistar2.Obj|ObjectManager"],"Update");m.MethodsByName[key].Add(m.MethodsByName[key][0]);})
        }){
            var mutated=new FakeMetadata(bytes);change(mutated);var result=C.Check(mutated,bytes);Pass(!result.Compatible&&result.Errors.Count>0,label);
        }
        Pass(C.Shape("System.Collections.Generic.List`1<SiNiSistar2.EventLabel.LabelEvent>")==C.Shape("System.Collections.Generic.List<SiNiSistar2.EventLabel.LabelEvent>"),"generic normalization");
        Pass(C.Shape("Other.Channel.HP")!=C.Shape("SiNiSistar2.Obj.HP"),"namespace is part of type identity");
        Pass(C.Shape("System.Int32&")!=C.Shape("System.Int32"),"ref is distinct");
        Pass(C.Shape("System.Boolean")!=C.Shape("System.Int32"),"bool is distinct");
        Console.WriteLine(JsonSerializer.Serialize(new{passed=true,checks,types=good.Types,fields=good.Fields,methods=good.MethodCount,contract_sha256=good.Digest}));
    }
}
