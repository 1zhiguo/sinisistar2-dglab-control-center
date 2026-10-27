// GPL-3.0-only. Native metadata access shared in design with the observer.
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
namespace SiNiSistarTrainer;

sealed class Native
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

    internal void SetCurrent(IntPtr obj,int value){
        CallValues(obj,"SetCurrentValue",value,true);
    }
    internal void RemoveAbnormal(IntPtr obj,int type){
        // Explicitly select the enum overload, never the AbnormalData pointer overload.
        var method=Method(Marshal.ReadIntPtr(obj),"RemoveAbnormal",1,"AbnormalType");
        var value=Marshal.AllocHGlobal(4);var args=Marshal.AllocHGlobal(IntPtr.Size);
        try{
            Marshal.WriteInt32(value,type);Marshal.WriteIntPtr(args,value);
            Export<RuntimeInvoke>("il2cpp_runtime_invoke")(method,obj,args,out var error);
            if(error!=IntPtr.Zero)throw new InvalidOperationException("游戏拒绝解除该异常状态");
        }finally{Marshal.FreeHGlobal(args);Marshal.FreeHGlobal(value);}
    }
    void CallValues(IntPtr obj,string name,int value,bool silence){
        var klass=Marshal.ReadIntPtr(obj);IntPtr method=IntPtr.Zero;
        while(klass!=IntPtr.Zero){try{method=Method(klass,name,2);break;}catch(MissingMethodException){klass=parent(klass);}}
        if(method==IntPtr.Zero)throw new MissingMethodException(name);
        var values=Marshal.AllocHGlobal(8);var args=Marshal.AllocHGlobal(IntPtr.Size*2);
        try{
            Marshal.WriteInt32(values,value);Marshal.WriteByte(values,4,silence?(byte)1:(byte)0);
            Marshal.WriteIntPtr(args,values);Marshal.WriteIntPtr(args,IntPtr.Size,IntPtr.Add(values,4));
            Export<RuntimeInvoke>("il2cpp_runtime_invoke")(method,obj,args,out var error);
            if(error!=IntPtr.Zero)throw new InvalidOperationException("Game rejected the resource change");
        }finally{Marshal.FreeHGlobal(args);Marshal.FreeHGlobal(values);}
    }
}
