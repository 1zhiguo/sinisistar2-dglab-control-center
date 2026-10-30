"""Generate the observer's member contract from a local Il2CppDumper dump.

Only member names, types and enum values are retained, never native addresses.
Run --check against another distribution to compare its API without running it.
"""
import argparse, json, re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
TARGET=ROOT/'src/sinisistar_dglab/assets/runtime-interface-v1.json'
MODIFIERS=re.compile(r'^(?:(?:public|private|protected|internal|static|readonly|const|sealed|virtual|override|abstract|extern|unsafe|new)\s+)+')

def split_types(text):
    parts=[]; start=depth=0
    for i,c in enumerate(text):
        if c in '<[':depth+=1
        if c in '>]':depth-=1
        if c==',' and depth==0:parts.append(text[start:i].strip());start=i+1
    if text[start:].strip():parts.append(text[start:].strip())
    return parts

def parse(path):
    result={}
    source=path.read_text(encoding='utf-8-sig').replace('\n{}\n','\n{\n}\n')
    for m in re.finditer(r'^// Namespace: ([^\r\n]*)\r?\n(?:(?!^// Namespace:).)*?^([^\r\n]+)// TypeDefIndex: \d+\r?\n\{(.*?)^\}',source,re.M|re.S):
        ns,decl,body=m.groups(); name=re.search(r'\b(class|struct|enum|interface) (.*?)(?:\s*:\s*|\s*$)',decl.strip())
        if not name:continue
        kind,full=name.groups(); args=re.search(r'<([^<>]+)>$',full)
        runtime=full[:args.start()]+'`'+str(len(split_types(args[1]))) if args else full
        row=dict(ns=ns,name=runtime,kind=kind,fields=[],methods=[],base=decl.split(' : ',1)[1].strip() if ' : ' in decl else '')
        for line in body.splitlines():
            text=line.strip()
            if '; // 0x' in text or kind=='enum' and ' = ' in text and text.endswith(';'):
                left=text.split(';',1)[0]; clean=MODIFIERS.sub('',left); declaration,separator,value=clean.partition(' = ')
                if ' ' in declaration:
                    typ,field=declaration.rsplit(' ',1);value=value if separator else None;item=dict(name=field,type=typ,static=bool(re.search(r'\b(?:static|const)\b',left)))
                    if kind=='enum' and field!='value__' and value is not None:
                        try:item['value']=int(value)
                        except ValueError:continue
                    row['fields'].append(item)
            elif text.endswith(' { }') and '(' in text:
                clean=MODIFIERS.sub('',text); mm=re.match(r'(.+?) ([^ ]+)\((.*)\) \{ \}',clean)
                if mm:
                    ret,meth,parameters=mm.groups(); pp=[]
                    for p in split_types(parameters):
                        p=p.split(' = ',1)[0]; pp.append(p.rsplit(' ',1)[0].replace('ref ','').replace('out ','')+('&' if p.startswith(('ref ','out ')) else ''))
                    row['methods'].append(dict(name=meth,returns=ret,parameters=pp,static='static ' in text))
        result[(ns,runtime)]=row
    for key,row in list(result.items()):
        if not key[0] and '.' in key[1]:
            outer=key[1].split('.',1)[0]; candidates=[k for k in result if k[1]==outer]
            if len(candidates)==1:
                result.pop(key);row['ns']=candidates[0][0];result[(row['ns'],row['name'])]=row
    return result

def generate(dump):
    types=parse(dump)
    sources='\n'.join(p.read_text(encoding='utf-8') for p in (ROOT/'observer').glob('*.cs') if p.name not in ('RuntimeInterface.cs','BuildCompatibility.cs'))
    strings=set(re.findall(r'"([^"\n]+)"',sources))
    roots=set(re.findall(r'api.Class\("([^"]*)","([^"]+)"\)|(?<!api\.)Class\("([^"]*)","([^"]+)"\)',sources))
    selected={(a or c,b or d) for a,b,c,d in roots}
    selected.update({('SiNiSistar2.Obj','GachaBind.ReleaseResponseParameter'),('SiNiSistar2.Obj','GachaBind.ReleaseReason'),('UnityEngine','AnimatorStateInfo')})
    for name in ('HierarchyEventPlayer','AnimatorTriggerLabel','AnimatorTriggerAsyncLabel'):
        matches=[k for k in types if k[1]==name]
        assert len(matches)==1,name
        selected.update(matches)
    calls={}
    for ns,klass,name,count,first in re.findall(r'Method\((?:api\.)?Class\("([^"]*)","([^"]+)"\),"([^"]+)",(\d+)(?:,"([^"]+)")?\)',sources):
        calls.setdefault((ns,klass),[]).append((name,int(count),first))
    calls.setdefault(('SiNiSistar2.Obj','GachaBind.ReleaseResponseParameter'),[]).append(('set_ReleaseReason',1,''))
    calls.setdefault(('SiNiSistar2.Obj','AbnormalList'),[]).extend((name,1,'AbnormalType') for name in ('DownAbnormal','RemoveAbnormal'))
    # Enum IDs are part of feedback semantics, not native memory offsets.
    enum_names=set(json.loads((ROOT/'src/sinisistar_dglab/assets/game-types.json').read_text()) if (ROOT/'src/sinisistar_dglab/assets/game-types.json').exists() else ['SceneID','AnimState','AbnormalType'])
    selected.update(k for k,v in types.items() if v['kind']=='enum' and k[1] in enum_names)
    def resolve(text,context):
        found=set()
        for token in re.findall(r'[\w.]+(?:<[^<>]+>)?',text):
            if token in ('T','TValue','System','object','bool','int','float','double','void','string'):continue
            generic=re.search(r'<([^<>]+)>$',token)
            lookup=token[:generic.start()]+'`'+str(len(split_types(generic[1]))) if generic else token
            candidates=[k for k in types if k[1]==lookup or '.'.join(k)==lookup]
            preferred=[k for k in candidates if k[0]==context]
            if not preferred and context.startswith('SiNiSistar2'):preferred=[k for k in candidates if k[0].startswith('SiNiSistar2')]
            if len(preferred)==1:found.update(preferred)
            elif len(candidates)==1:found.update(candidates)
        return found
    pending=list(selected); done=set(); output=[]
    while pending:
        key=pending.pop()
        if key in done:continue
        done.add(key)
        if key not in types:raise ValueError('Missing contract type: '+str(key))
        row=types[key]; fields=[f for f in row['fields'] if f['name'] in strings or row['kind']=='enum' and row['name']!='LocalizeID']
        selectors=calls.get(key,[])
        methods=[m for m in row['methods'] if (m['name'].startswith('get_') and m['name'] in strings and m['name'] not in ('get_time','get_duration')) or any(m['name']==n and len(m['parameters'])==c and (not first or m['parameters'][0].lower().endswith(first.lower())) for n,c,first in selectors)]
        for m in methods:
            same=[x for x in methods if x['name']==m['name'] and len(x['parameters'])==len(m['parameters'])]
            m['first_type_filter']=next((first for n,c,first in selectors if n==m['name'] and c==len(m['parameters']) and first),'')
            if len(same)>1 and not m['first_type_filter']:raise ValueError('Ambiguous method '+str(key)+m['name'])
        output.append(dict(ns=row['ns'],name=row['name'],kind=row['kind'],fields=fields,methods=methods))
        refs=resolve(row['base'],row['ns'])
        for f in fields:refs.update(resolve(f['type'],row['ns']))
        for m in methods:
            for parameter in [m['returns'],*m['parameters']]:refs.update(resolve(parameter,row['ns']))
        pending.extend(refs-done)
    aliases=dict(zip(('void','bool','int','uint','long','ulong','short','ushort','byte','sbyte','float','double','string','object','char'),('Void','Boolean','Int32','UInt32','Int64','UInt64','Int16','UInt16','Byte','SByte','Single','Double','String','Object','Char')))
    def qualify(text,context):
        if text.endswith(('[]','&')):
            suffix='[]' if text.endswith('[]') else '&';return qualify(text[:-len(suffix)],context)+suffix
        generic=text.find('<');base=text[:generic] if generic>=0 else text
        if base in aliases:return 'System.'+aliases[base]
        lookup=base+'`'+str(len(split_types(text[generic+1:-1]))) if generic>=0 else base
        candidates=[k for k in types if k[1]==lookup or '.'.join(k)==lookup];preferred=[k for k in candidates if k[0]==context]
        if not preferred and context.startswith('SiNiSistar2'):preferred=[k for k in candidates if k[0].startswith('SiNiSistar2')]
        if len(preferred)==1:target=preferred[0]
        elif len(candidates)==1:target=candidates[0]
        elif re.fullmatch(r'T\w*',base):return text
        else:raise ValueError('Ambiguous or missing member type: '+context+' '+text)
        name='.'.join(part for part in target if part).split('`')[0]
        return name+('<'+','.join(qualify(p,context) for p in split_types(text[generic+1:-1]))+'>' if generic>=0 else '')
    for row in output:
        for field in row['fields']:field['type']=qualify(field['type'],row['ns'])
        for method in row['methods']:
            method['returns']=qualify(method['returns'],row['ns'])
            method['parameters']=[qualify(p,row['ns']) for p in method['parameters']]
    output.sort(key=lambda r:(r['ns'],r['name']))
    exports=set(re.findall(r'"(il2cpp_\w+)"',sources))
    exports.update(('il2cpp_class_get_flags','il2cpp_class_is_enum','il2cpp_class_is_valuetype','il2cpp_field_get_flags','il2cpp_field_get_type','il2cpp_method_get_return_type','il2cpp_method_get_flags'))
    return dict(schema=1,contract='sinisistar2-observer-v1',exports=sorted(exports),types=output)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--dump',type=Path,default=ROOT/'.analysis/il2cpp-v1.3.1/dump.cs');parser.add_argument('--check',action='store_true');args=parser.parse_args()
    value=generate(args.dump)
    if args.check:
        assert value==json.loads(TARGET.read_text(encoding='utf-8')),'Interface differs from baseline'
    else:TARGET.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(types=len(value['types']),fields=sum(len(t['fields']) for t in value['types']),methods=sum(len(t['methods']) for t in value['types']))))

if __name__=='__main__':main()
