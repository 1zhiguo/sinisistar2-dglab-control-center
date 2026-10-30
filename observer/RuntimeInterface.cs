// GPL-3.0-only. Metadata-only ABI checks; never calls game methods or installs hooks.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.RegularExpressions;
namespace SiNiSistarCompatibility;

internal static class RuntimeInterface
{
    internal const string Contract="sinisistar2-observer-v1";
    internal record FieldShape(string Type,bool Static,int? Constant);
    internal record MethodShape(string Name,string Returns,string[] Parameters,bool Static,IntPtr Method);
    internal interface IMetadata
    {
        bool HasExport(string name);
        IntPtr Class(string ns,string name);
        string ClassKind(IntPtr klass);
        FieldShape? Field(IntPtr klass,string name,bool constant);
        IEnumerable<MethodShape> Methods(IntPtr klass,string name);
    }
    internal sealed class Report
    {
        internal readonly List<string> Errors=new();
        internal readonly HashSet<IntPtr> Methods=new();
        internal int Types,Fields,MethodCount;
        internal string Digest="";
        internal bool Compatible=>Errors.Count==0;
        internal Dictionary<string,object?> Data(string fingerprint)=>new(){
            ["schema"]=1,["contract"]=Contract,["contract_sha256"]=Digest,["status"]=Compatible?"compatible":"incompatible",
            ["fingerprint"]=fingerprint,["types_checked"]=Types,["fields_checked"]=Fields,["methods_checked"]=MethodCount,["errors"]=Errors};
    }
    internal static byte[] ContractBytes()
    {
        using var stream=Assembly.GetExecutingAssembly().GetManifestResourceStream("runtime-interface-v1.json")??throw new FileNotFoundException("Embedded interface contract missing");
        using var memory=new MemoryStream();stream.CopyTo(memory);return memory.ToArray();
    }
    internal static string Shape(string type)
    {
        type=type.Replace('/','.');
        type=Regex.Replace(type,@"`\d+","");
        var aliases=new Dictionary<string,string>{{"void","Void"},{"bool","Boolean"},{"int","Int32"},{"uint","UInt32"},{"long","Int64"},{"ulong","UInt64"},{"short","Int16"},{"ushort","UInt16"},{"byte","Byte"},{"sbyte","SByte"},{"float","Single"},{"double","Double"},{"string","String"},{"object","Object"},{"char","Char"}};
        return Regex.Replace(Regex.Replace(type,@"\s+",""),@"\b\w+\b",m=>aliases.TryGetValue(m.Value,out var value)?"System."+value:m.Value);
    }
    internal static Report Check(IMetadata api,byte[]? bytes=null)
    {
        bytes??=ContractBytes();var report=new Report{Digest=Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant()};
        using var document=JsonDocument.Parse(bytes);
        if(IntPtr.Size!=8)report.Errors.Add("ABI: x64 runtime required");
        foreach(var symbol in document.RootElement.GetProperty("exports").EnumerateArray())
            if(!api.HasExport(symbol.GetString()!))report.Errors.Add("IL2CPP export missing: "+symbol.GetString());
        if(report.Errors.Count>0)return report;
        foreach(var type in document.RootElement.GetProperty("types").EnumerateArray())
        {
            string ns=type.GetProperty("ns").GetString()!,name=type.GetProperty("name").GetString()!,label=ns+"."+name;
            IntPtr klass;
            try{klass=api.Class(ns,name);if(klass==IntPtr.Zero)throw new TypeLoadException(label);if(api.ClassKind(klass)!=type.GetProperty("kind").GetString())throw new TypeLoadException("class/value/interface kind changed");report.Types++;}
            catch(Exception error){report.Errors.Add("type: "+label+" ("+error.Message+")");continue;}
            foreach(var field in type.GetProperty("fields").EnumerateArray())
            {
                string member=field.GetProperty("name").GetString()!;
                try{
                    bool constant=field.TryGetProperty("value",out var expectedValue);var actual=api.Field(klass,member,constant);
                    if(actual==null)throw new MissingFieldException("missing");
                    if(Shape(actual.Type)!=Shape(field.GetProperty("type").GetString()!)||actual.Static!=field.GetProperty("static").GetBoolean())throw new InvalidOperationException("field type/static changed: "+actual.Type);
                    if(constant&&actual.Constant!=expectedValue.GetInt32())throw new InvalidOperationException("enum value changed");
                    report.Fields++;
                }catch(Exception error){report.Errors.Add("field: "+label+"."+member+" ("+error.Message+")");}
            }
            foreach(var method in type.GetProperty("methods").EnumerateArray())
            {
                string member=method.GetProperty("name").GetString()!;
                try{
                    var parameters=method.GetProperty("parameters").EnumerateArray().Select(x=>Shape(x.GetString()!)).ToArray();
                    var first=method.GetProperty("first_type_filter").GetString()!;
                    var candidates=api.Methods(klass,member).Where(m=>m.Parameters.Length==parameters.Length&&(first.Length==0||m.Parameters.Length>0&&Shape(m.Parameters[0]).Split('.').Last()==Shape(first).Split('.').Last())).ToArray();
                    if(candidates.Length!=1)throw new MissingMethodException("missing or ambiguous overload");
                    var actual=candidates[0];
                    if(actual.Static!=method.GetProperty("static").GetBoolean()||Shape(actual.Returns)!=Shape(method.GetProperty("returns").GetString()!)||!actual.Parameters.Select(Shape).SequenceEqual(parameters))throw new InvalidOperationException("return/parameter/static signature changed");
                    report.Methods.Add(actual.Method);report.MethodCount++;
                }catch(Exception error){report.Errors.Add("method: "+label+"."+member+" ("+error.Message+")");}
            }
        }
        return report;
    }

    internal sealed class NativeMetadata:IMetadata
    {
        readonly IntPtr module=NativeLibrary.Load("GameAssembly.dll");
        readonly Dictionary<string,Delegate> exports=new();
        [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr NoArg();
        [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr One(IntPtr value);
        [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Assemblies(IntPtr domain,out nuint count);
        [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr ClassLookup(IntPtr image,[MarshalAs(UnmanagedType.LPStr)]string ns,[MarshalAs(UnmanagedType.LPStr)]string name);
        [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Named(IntPtr klass,[MarshalAs(UnmanagedType.LPStr)]string name);
        [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Iterator(IntPtr klass,ref IntPtr iterator);
        [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Flags(IntPtr value);
        [UnmanagedFunctionPointer(CallingConvention.Cdecl)] [return:MarshalAs(UnmanagedType.I1)] delegate bool Predicate(IntPtr value);
        [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint MethodFlags(IntPtr method,out uint implementation);
        [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Parameter(IntPtr method,uint index);
        [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate void StaticRead(IntPtr field,out int value);
        T Export<T>(string name) where T:Delegate
        {if(!exports.TryGetValue(name,out var value))exports[name]=value=Marshal.GetDelegateForFunctionPointer<T>(NativeLibrary.GetExport(module,name));return (T)value;}
        string Text(IntPtr value)=>Marshal.PtrToStringAnsi(value)??"";
        string TypeName(IntPtr type)=>Text(Export<One>("il2cpp_type_get_name")(type));
        public bool HasExport(string name)=>NativeLibrary.TryGetExport(module,name,out var value)&&value!=IntPtr.Zero;
        public IntPtr Class(string ns,string name)
        {
            var parts=name.Split('.');var list=Export<Assemblies>("il2cpp_domain_get_assemblies")(Export<NoArg>("il2cpp_domain_get")(),out var count);
            for(int i=0;i<(int)count;i++){
                var klass=Export<ClassLookup>("il2cpp_class_from_name")(Export<One>("il2cpp_assembly_get_image")(Marshal.ReadIntPtr(list,i*IntPtr.Size)),ns,parts[0]);
                if(klass==IntPtr.Zero)continue;
                for(int n=1;n<parts.Length&&klass!=IntPtr.Zero;n++){
                    IntPtr iter=IntPtr.Zero,item;var found=IntPtr.Zero;
                    while((item=Export<Iterator>("il2cpp_class_get_nested_types")(klass,ref iter))!=IntPtr.Zero)if(Text(Export<One>("il2cpp_class_get_name")(item))==parts[n]){found=item;break;}
                    klass=found;
                }
                if(klass!=IntPtr.Zero)return klass;
            }
            return IntPtr.Zero;
        }
        public FieldShape? Field(IntPtr klass,string name,bool constant)
        {
            var field=Export<Named>("il2cpp_class_get_field_from_name")(klass,name);if(field==IntPtr.Zero)return null;
            uint flags=Export<Flags>("il2cpp_field_get_flags")(field);int? value=null;
            if(constant){if((flags&0x40)==0)throw new InvalidOperationException("not a literal enum constant");Export<StaticRead>("il2cpp_field_static_get_value")(field,out var number);value=number;}
            return new(TypeName(Export<One>("il2cpp_field_get_type")(field)),(flags&0x10)!=0,value);
        }
        public string ClassKind(IntPtr klass)=>Export<Predicate>("il2cpp_class_is_enum")(klass)?"enum":Export<Predicate>("il2cpp_class_is_valuetype")(klass)?"struct":(Export<Flags>("il2cpp_class_get_flags")(klass)&0x20)!=0?"interface":"class";
        public IEnumerable<MethodShape> Methods(IntPtr klass,string name)
        {
            IntPtr iter=IntPtr.Zero,method;
            while((method=Export<Iterator>("il2cpp_class_get_methods")(klass,ref iter))!=IntPtr.Zero){
                if(Text(Export<One>("il2cpp_method_get_name")(method))!=name)continue;
                uint count=Export<Flags>("il2cpp_method_get_param_count")(method);var parameters=new string[count];
                for(uint i=0;i<count;i++)parameters[i]=TypeName(Export<Parameter>("il2cpp_method_get_param")(method,i));
                uint flags=Export<MethodFlags>("il2cpp_method_get_flags")(method,out _);
                yield return new(name,TypeName(Export<One>("il2cpp_method_get_return_type")(method)),parameters,(flags&0x10)!=0,method);
            }
        }
    }
}
