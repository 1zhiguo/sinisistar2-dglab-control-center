"""Known builds and runtime interface attestations for channel-independent reads."""
from pathlib import Path
import hashlib,json,mmap,re,struct
PROFILES=json.loads((Path(__file__).parent/'assets/game-builds.json').read_text(encoding='utf-8'))['profiles']
FINGERPRINTS=frozenset(p['files']['GameAssembly.dll'] for p in PROFILES)
CONTRACT_PATH=Path(__file__).parent/'assets/runtime-interface-v1.json'
CONTRACT_SHA256=hashlib.sha256(CONTRACT_PATH.read_bytes()).hexdigest()
CONTRACT_ID='sinisistar2-observer-v1'

def compatible_snapshot(data):
    """Old audited plugins remain readable; new builds require the current probe."""
    fingerprint=data.get('fingerprint')
    if not isinstance(fingerprint,str) or not re.fullmatch('[0-9a-f]{64}',fingerprint):return False
    report=data.get('compatibility')
    if report is None:return fingerprint in FINGERPRINTS
    return bool(isinstance(report,dict) and report.get('schema')==1 and report.get('contract')==CONTRACT_ID
        and report.get('contract_sha256')==CONTRACT_SHA256 and report.get('status')=='compatible'
        and report.get('fingerprint')==fingerprint and report.get('errors')==[]
        and report.get('pid')==data.get('pid') and report.get('session')==data.get('session'))

def candidate_checks(paths):
    """Read-only loader preflight, not a claim that game interfaces passed.

    No supplied EXE/DLL is executed. The running plugin checks member signatures
    before any native detour; this only permits installing that observer.
    """
    errors=[]
    for name in ('SiNiSistar2.exe','GameAssembly.dll','UnityPlayer.dll'):
        path=paths[name]
        try:
            with path.open('rb') as file:
                header=file.read(64)
                if len(header)!=64 or header[:2]!=b'MZ':raise ValueError('不是 Windows PE 文件')
                offset=struct.unpack_from('<I',header,60)[0]
                if offset<64 or offset>min(path.stat().st_size-26,16*1024*1024):raise ValueError('PE 头无效')
                file.seek(offset);pe=file.read(26)
                if pe[:4]!=b'PE\0\0' or struct.unpack_from('<H',pe,4)[0]!=0x8664 or struct.unpack_from('<H',pe,24)[0]!=0x20b:raise ValueError('需要 Windows x64 构建')
        except (OSError,ValueError,struct.error) as error:errors.append(name+'：'+str(error))
    try:
        with paths['UnityPlayer.dll'].open('rb') as file,mmap.mmap(file.fileno(),0,access=mmap.ACCESS_READ) as data:
            if not re.search(rb'\b2022\.3\.62f\d+(?:c\d+)?\b',data):errors.append('Unity 引擎版本未适配，需要 2022.3.62')
        with paths['GameAssembly.dll'].open('rb') as file,mmap.mmap(file.fileno(),0,access=mmap.ACCESS_READ) as data:
            for export in (b'il2cpp_domain_get',b'il2cpp_class_from_name',b'il2cpp_field_get_type',b'il2cpp_method_get_return_type'):
                if data.find(export+b'\0')<0:errors.append('缺少 IL2CPP 接口：'+export.decode())
        with paths['SiNiSistar2_Data/il2cpp_data/Metadata/global-metadata.dat'].open('rb') as file:
            header=file.read(8)
            if len(header)!=8 or struct.unpack('<II',header)!=(0xfab11baf,31):errors.append('IL2CPP 元数据格式未适配，需要版本 31')
            with mmap.mmap(file.fileno(),0,access=mmap.ACCESS_READ) as data:
                for marker in (b'SiNiSistar2.Manager\0',b'ManagerList\0',b'Lelia\0',b'EventManager\0',b'GaTakePlayer\0'):
                    if data.find(marker)<0:errors.append('缺少游戏类型标识：'+marker[:-1].decode())
    except (OSError,ValueError) as error:errors.append('无法检查游戏运行文件：'+str(error))
    return errors
