"""Build a self-contained, clean Windows x64 release; never archive the workspace."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,importlib.metadata as metadata,json,os,shutil,subprocess,sys,time,zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from sinisistar_dglab import __version__
from sinisistar_dglab.install_manager import PINNED_PAYLOAD

APP_NAME='SiNiSistar2-x-DGlab'

def digest(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def remove_build_path(path,app):
    path=path.resolve();assert path.is_relative_to(app.resolve()) and path!=app.resolve()
    if path.is_dir():shutil.rmtree(path)
    elif path.is_file():path.unlink()

def build():
    name=f'{APP_NAME}-{__version__}-windows-x64';release=ROOT/'release';release.mkdir(exist_ok=True)
    archive=release/(name+'.zip')
    if archive.exists():raise RuntimeError('Refusing to overwrite an existing release ZIP')
    work=ROOT/'build'/f'release-{__version__}-{time.time_ns()}';work.mkdir(parents=True)
    (release/'current-build.json').write_text(json.dumps({'work':str(work)},indent=2),encoding='utf-8')
    for filename,expected in PINNED_PAYLOAD.items():
        if digest(ROOT/'installer_payload'/filename)!=expected:raise RuntimeError('Installer payload mismatch: '+filename)
    trainer=json.loads((ROOT/'installer_payload/trainer-manifest.json').read_text(encoding='utf-8'))
    assert digest(ROOT/'installer_payload'/trainer['file'])==trainer['sha256']
    from sinisistar_dglab.save_import import PAYLOAD,PAYLOAD_SHA256
    if digest(PAYLOAD)!=PAYLOAD_SHA256:raise RuntimeError('Optional save payload mismatch')
    version_file=work/'version-info.txt'
    numeric_version=tuple(map(int,__version__.split('.')))+(0,)
    version_file.write_text(f"""VSVersionInfo(ffi=FixedFileInfo(filevers={numeric_version},prodvers={numeric_version},mask=0x3f,flags=0x0,OS=0x40004,fileType=0x1,subtype=0x0,date=(0,0)),kids=[StringFileInfo([StringTable('040904B0',[StringStruct('CompanyName','1zhiguo'),StringStruct('FileDescription','SiNiSistar2 x DG-LAB Control Center'),StringStruct('FileVersion','{__version__}'),StringStruct('InternalName','SiNiSistar2-x-DGlab'),StringStruct('OriginalFilename','SiNiSistar2-x-DGlab.exe'),StringStruct('ProductName','SiNiSistar2 x DG-LAB'),StringStruct('ProductVersion','{__version__}')])]),VarFileInfo([VarStruct('Translation',[1033,1200])])])""",encoding='utf-8')
    command=[sys.executable,'-m','PyInstaller','--noconfirm','--windowed','--onedir','--name',APP_NAME,
        '--icon',str(ROOT/'src/sinisistar_dglab/assets/app-icon.ico'),'--version-file',str(version_file),
        '--distpath',str(work/'dist'),'--workpath',str(work/'work'),'--specpath',str(work),'--paths',str(ROOT/'src'),
        '--add-data',str(ROOT/'src/sinisistar_dglab/qml')+';sinisistar_dglab/qml',
        '--add-data',str(ROOT/'src/sinisistar_dglab/assets')+';sinisistar_dglab/assets',
        '--collect-submodules','websockets','--collect-submodules','qrcode.image']
    for module in ('PyQt5','PyQt6','PySide2','tkinter','matplotlib','numpy'):command+=['--exclude-module',module]
    command+=[str(ROOT/'tools/frozen_entry.py')]
    subprocess.run(command,check=True,cwd=ROOT)
    app=work/'dist'/APP_NAME;assert (app/(APP_NAME+'.exe')).is_file()
    if digest(app/'_internal/sinisistar_dglab/assets/optional-saves/full-cg.zip')!=PAYLOAD_SHA256:
        raise RuntimeError('Optional save payload missing from frozen application')
    pruning=[]
    def prune(path):
        if path.exists():
            size=sum(p.stat().st_size for p in path.rglob('*') if p.is_file()) if path.is_dir() else path.stat().st_size
            pruning.append(dict(path=path.relative_to(app).as_posix(),bytes=size));remove_build_path(path,app)
    for relative in ('_internal/PySide6/Qt6WebEngineCore.dll','_internal/PySide6/Qt6WebEngineQuick.dll',
        '_internal/PySide6/Qt6WebEngineQuickDelegatesQml.dll','_internal/PySide6/Qt6WebView.dll','_internal/PySide6/Qt6WebViewQuick.dll',
        '_internal/PySide6/Qt6Pdf.dll','_internal/PySide6/Qt6PdfQuick.dll','_internal/PySide6/qml/QtWebEngine',
        '_internal/PySide6/qml/QtWebView','_internal/PySide6/qml/QtQuick/Pdf','_internal/PySide6/QtWebEngineProcess.exe',
        '_internal/icuuc.dll','_internal/icudt78.dll'):
        prune(app/relative)
    # QML collection also pulls unrelated 3D, media, maps and non-Basic styles.
    # Keep Quick/Dialogs, native folder dialogs and the software renderer.
    qt=app/'_internal/PySide6'
    for module in ('Qt3D','QtCharts','QtDataVisualization','QtGraphs','QtLocation','QtMultimedia',
                   'QtPositioning','QtQuick3D','QtRemoteObjects','QtScxml','QtSensors','QtTest',
                   'QtTextToSpeech','QtWebChannel','QtWebSockets'):
        prune(qt/'qml'/module)
    for module in ('Scene2D','Scene3D','VirtualKeyboard','LocalStorage','Timeline','tooling'):
        prune(qt/'qml/QtQuick'/module)
    for style in ('FluentWinUI3','Fusion','Imagine','Material','Universal','Windows','iOS','macOS'):
        prune(qt/'qml/QtQuick/Controls'/style)
    families=('Qt63D','Qt6Quick3D','Qt6Charts','Qt6DataVisualization','Qt6Graphs','Qt6Multimedia',
              'Qt6Positioning','Qt6Location','Qt6RemoteObjects','Qt6Scxml','Qt6Sensors','Qt6TextToSpeech',
              'Qt6VirtualKeyboard','Qt6WebChannel','Qt6WebSockets','Qt6QuickControls2FluentWinUI3',
              'Qt6QuickControls2Fusion','Qt6QuickControls2Imagine','Qt6QuickControls2Material','Qt6QuickControls2Universal')
    for path in list(qt.glob('*.dll')):
        if path.name.startswith(families):prune(path)
    for filename in ('VCRUNTIME140.dll','VCRUNTIME140_1.dll','MSVCP140.dll','MSVCP140_1.dll','MSVCP140_2.dll'):
        source=app/'_internal/PySide6'/filename
        if source.is_file():shutil.copy2(source,app/'_internal'/filename)
    shutil.copytree(ROOT/'installer_payload',app/'installer_payload')
    release_notes=release/f'RELEASE_NOTES-{__version__}.md'
    if release_notes.is_file():shutil.copy2(release_notes,app/'RELEASE_NOTES.md')
    for filename in ('LICENSE','THIRD_PARTY_NOTICES.md'):shutil.copy2(ROOT/filename,app/filename)
    versions={}
    for package in ('PySide6','PySide6_Essentials','PySide6_Addons','shiboken6','websockets','qrcode','Pillow','PyInstaller'):
        dist=metadata.distribution(package);versions[package]=dist.version
        for entry in dist.files or ():
            if any(word in Path(str(entry)).name.upper() for word in ('LICENSE','COPYING','NOTICE','AUTHORS')):
                source=Path(dist.locate_file(entry))
                if source.is_file() and source.stat().st_size<2_000_000:
                    destination=app/'third-party-licenses'/package/str(entry).replace('..','_');destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,destination)
    py_license=Path(sys.base_prefix)/'LICENSE.txt'
    if py_license.is_file():
        destination=app/'third-party-licenses/Python/LICENSE.txt';destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(py_license,destination)
    guide=f'''SiNiSistar2 × DG-LAB {__version__} · Windows x64 · 游玩测试版

解压整个文件夹，双击 {APP_NAME}.exe；无需安装 Python。
1. 选择包含 SiNiSistar2.exe 的游戏目录，退出游戏后安装插件，再启动游戏。
2. 选择 V3 / V4，与手机连接同一局域网，再使用对应 DG-LAB APP 扫码。
3. 设备就绪后启用 Pulse；未插负鼠配件时无法启用对应通道。
4. 选择低 / 中 / 高预设，确认硬上限；修改策略后需要重新启用输出。
5. 打开 HUD，并通过 HUD 设置调整位置。

同值 HP 演出反馈与图鉴反馈默认开启。设备输出仍需启用；新配置的 A/B 通道默认同时参与受伤与 CG。
若负鼠连接后 CG 不震动，请在 CG 页查看「本通道反馈范围」，仅受伤不会参与 CG。旧配置保留原有选择。

Ctrl+F12：全局急停（可在右上角齿轮中自定义）；Ctrl+F11：调整 / 锁定 HUD。
日常界面已隐藏模拟、批量测试和无 HP 消融入口。
支持已核验的 SiNiSistar2 v1.3.1，以及 Steam Lite v1.3.1／Lite＋官方补丁；观察插件 0.8.0，独立辅助插件 0.2.2。
Steam 两种模式已验证启动与插件心跳，游戏事件与设备联动仍待实测。官方游戏补丁不包含在本程序包中。
其他渠道构建可在安装后启动游戏，通过接口检查再尝试联动；不再仅凭游戏文件哈希拒绝。
接口或钩子检查失败会停止读取，并在「设备与游戏」显示原因。DLsite 版尚待对方实测，接口通过不等于所有 CG 已验证。
检查报告：游戏目录/BepInEx/plugins/SiNiSistarDGLab/telemetry/compatibility.json。
未知构建的辅助修改与一键存档导入暂不开放；安装资源本身仍严格校验 SHA256。
游戏反馈使用共享动画识别与 HP / 抓取兜底；图鉴使用独立播放信号。
支持 EventPlayer、已声明 Animator 和有效片段会话；并非所有实战分支均已实测。
退出时归零并关闭设备服务。配置和日志保存在本文件夹的 artifacts/ 下。
发布包使用干净默认配置，不包含游戏或开发者的个人存档、连接信息。
程序未签名。请保持整个文件夹完整，不要只复制 EXE。

Extract the ENTIRE folder and run {APP_NAME}.exe. No separate Python installation is needed.
Select your game folder, install the plugin with the game closed, then start the game.
Pair the matching V3/V4 APP on the same LAN, enable Pulse, choose a preset and position the HUD.
Global emergency stop: Ctrl+F12. HUD adjustment: Ctrl+F11. Settings: the top-right gear.
Gallery playback uses independent EventPlayer, declared Animator and valid take-session signals.
Steam Lite v1.3.1, with or without the official patch, has passed startup/observer-heartbeat checks. Gameplay feedback still requires testing. The game patch is not bundled.
Other channel builds may install the observer and attempt feedback after startup interface checks pass. DLsite compatibility is awaiting external testing; passing the API checks does not prove all CG behavior.
Failed interface/hook checks stop the reader. The game-side telemetry/compatibility.json report lists failures. Optional helper/save import remain restricted to audited builds.
Development and batch-testing controls are hidden in the normal interface.
Settings/logs stay in artifacts/ beside this EXE. No game or developer's personal saves are included. Unsigned build.
Same-HP and gallery rules default to on. Enable device output separately. Damage-only channel scope excludes CG and gallery feedback.

フォルダー全体を解凍して {APP_NAME}.exe を起動します。Pythonの別途導入は不要です。
ゲーム終了中にプラグインを導入し、V3/V4 APPで接続、Pulse有効化、プリセット選択、HUD配置の順に設定します。
緊急停止：Ctrl+F12。HUD調整：Ctrl+F11。開発用・一括テストの画面は通常表示しません。
図鑑はEventPlayer、登録済みAnimator、有効なクリップ情報で判定します。設定・ログはartifacts/に保存します。
別の配布版は導入後のインターフェース確認に通過すると連動を試せます。DLsite版は実機テスト待ちです。確認失敗時は読み取りを停止します。
HP同値通知と図鑑の反応は初期状態で有効です。デバイス出力は別途有効にしてください。「被ダメージのみ」のチャンネルはCGに反応しません。

Website: https://sinisistar2-dglab.web.app/
Source: https://github.com/1zhiguo/sinisistar2-dglab-control-center
'''
    (app/'START_HERE.txt').write_text(guide,encoding='utf-8-sig')
    source_files=[]
    for folder in ('src','tests','tools','observer','trainer'):
        for p in (ROOT/folder).rglob('*'):
            relative=p.relative_to(ROOT)
            if not p.is_file() or any(part in {'__pycache__','bin','obj','monster-previews'} for part in relative.parts):continue
            if p.suffix not in {'.py','.qml','.json','.js','.cs','.ps1','.gz'}:continue
            if p.name in {'publish_public_source.py','prepare_public_source.py','update_game_hub.py'}:continue
            source_files.append(p)
    source_files+=[ROOT/'LICENSE',ROOT/'THIRD_PARTY_NOTICES.md',ROOT/'requirements-native.txt',ROOT/'requirements-build.txt']
    with zipfile.ZipFile(app/f'SOURCE-{__version__}.zip','x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(set(source_files)):z.write(p,p.relative_to(ROOT).as_posix())
    (app/'BUILD_INFO.json').write_text(json.dumps({'version':__version__,'platform':'windows-x64','built_utc':datetime.now(timezone.utc).isoformat(),
        'dependencies':versions,'observer_version':'0.8.0','helper_version':'0.2.2','source_sha256':{p.relative_to(ROOT).as_posix():digest(p) for p in source_files},
        'game_included':False,'personal_settings_included':False,'signed':False,
        'optional_save_payload':{'file':'sinisistar_dglab/assets/optional-saves/full-cg.zip','sha256':PAYLOAD_SHA256,'automatic_import':False},
        'developer_ui_default':False,'qt_pruning':pruning,'removed_bytes':sum(p['bytes'] for p in pruning)},ensure_ascii=False,indent=2),encoding='utf-8')
    qa=work/'qa';qa.mkdir();env={**os.environ,'PYTHONPATH':'','PYTHONHOME':'','QT_QPA_PLATFORM':'windows',
        'PATH':os.pathsep.join([str(Path(os.environ['SystemRoot'])/'System32'),os.environ['SystemRoot']])}
    for page in range(9):
        shot=qa/f'packaged-page-{page}.png'
        result=subprocess.run([str(app/(APP_NAME+'.exe')),'--offline','--page',str(page),'--settings-file',str(qa/'settings.json'),'--screenshot',str(shot)],cwd=qa,env=env,timeout=45)
        if result.returncode or not shot.is_file():raise RuntimeError(f'Packaged page {page} failed: {result.returncode}')
    log=app/'artifacts/ui/runtime.log'
    if log.is_file():
        errors=[line for line in log.read_text(encoding='utf-8').splitlines() if any(x in line for x in ('ReferenceError','TypeError','is not a type','Cannot assign','Unable to assign','Cannot open:','Binding loop'))]
        if errors:raise RuntimeError('Packaged QML errors: '+repr(errors[:8]))
    remove_build_path(app/'artifacts',app)
    banned={'GameAssembly.dll','UnityPlayer.dll','global-metadata.dat','settings.json','events.jsonl','latest.json','File01','SystemSpare'}
    for p in app.rglob('*'):
        if p.is_file() and (p.name in banned or p.suffix in {'.lnk','.log'}):raise RuntimeError('Unexpected release file: '+p.name)
    hashes={p.relative_to(app).as_posix():digest(p) for p in sorted(app.rglob('*')) if p.is_file()}
    (app/'PACKAGE_MANIFEST.json').write_text(json.dumps({'version':__version__,'files':hashes},indent=2),encoding='utf-8')
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(app.rglob('*')):
            if p.is_file():z.write(p,name+'/'+p.relative_to(app).as_posix())
    info={'version':__version__,'archive':str(archive),'sha256':digest(archive),'bytes':archive.stat().st_size,'app_directory':str(app),'qa_directory':str(qa),
        'file_count':len(hashes)+1,'packaged_pages_tested':list(range(9)),'personal_settings_included':False,'game_included':False,'signed':False}
    (release/(archive.name+'.sha256')).write_text(info['sha256']+'  '+archive.name+'\n',encoding='ascii')
    (release/f'release-{__version__}.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(info,ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':build()
