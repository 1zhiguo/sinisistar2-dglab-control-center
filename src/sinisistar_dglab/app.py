"""Native SiNiSistar2 control center. Device output starts paused."""
import argparse, ctypes, os, sys
from pathlib import Path

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offline',action='store_true');parser.add_argument('--screenshot',type=Path)
    parser.add_argument('--page',type=int,default=0,help='页面索引：0 总览 / 1 设备与游戏 / 2 快速设置 / 3 联动策略 / 4 波形 / 5 检测器 / 6 演出 / 7 CG 反馈 / 8 怪物图鉴');parser.add_argument('--size',default='1440x940')
    parser.add_argument('--settings-file',type=Path);parser.add_argument('--smoke-test',action='store_true')
    parser.add_argument('--show-hud',action='store_true');parser.add_argument('--hud-screenshot',type=Path)
    parser.add_argument('--live-preview',action='store_true',help='截图时读取当前插件；不会自动开启设备服务')
    parser.add_argument('--hud-tab',type=int,choices=(0,1),default=0);parser.add_argument('--hud-collapsed',action='store_true')
    parser.add_argument('--simulation-demo',choices=('grab_hp','abnormals','flow'))
    parser.add_argument('--simulate-live',action='store_true',help='启动实时只读模拟，保持设备服务关闭')
    parser.add_argument('--mock-app',action='store_true',help='启动回环模拟 APP；按自动启用设置运行')
    parser.add_argument('--gallery-mock',action='store_true',help='在主窗口打开图鉴反馈，连接四通道本机模拟 APP 并持续记录')
    parser.add_argument('--connect-v4',action='store_true',help='启动 DG-LAB 4 扫码服务；按自动启用设置运行')
    parser.add_argument('--connect-v3',action='store_true',help='启动 DG-LAB V3 扫码服务；按自动启用设置运行')
    parser.add_argument('--hud-adjust',action='store_true',help='以可拖动的桌面调整模式显示 HUD')
    parser.add_argument('--hud-settings',action='store_true',help='打开 HUD 显示设置')
    parser.add_argument('--capture-catalog',action='store_true',help='打开抓取/惩罚流程静态候选目录')
    parser.add_argument('--death-policy',action='store_true',help='打开死亡持续惩罚设置')
    parser.add_argument('--current-abnormals',action='store_true',help='打开事件检测器中的当前异常状态')
    parser.add_argument('--trainer',action='store_true',help='打开 HP / MP / 攻击力辅助面板；不会自动修改数值')
    parser.add_argument('--trainer-statuses',action='store_true',help='打开游戏辅助里的当前异常移除页')
    parser.add_argument('--abnormal-policy',action='store_true',help='打开中文异常筛选与批量启用设置')
    args=parser.parse_args();os.environ.setdefault('QT_QUICK_CONTROLS_STYLE','Basic')
    from PySide6.QtCore import QObject,QTimer,QUrl,qInstallMessageHandler,QAbstractNativeEventFilter
    from PySide6.QtGui import QGuiApplication,QFont,QIcon
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuick import QQuickItem
    from .backend import Backend,ROOT
    log=ROOT/'artifacts/ui/runtime.log';log.parent.mkdir(parents=True,exist_ok=True)
    def message(kind,context,text):
        with log.open('a',encoding='utf-8') as f:f.write(str(kind)+' '+text+'\n')
        if sys.stderr:
            try:print(text,file=sys.stderr,flush=True)
            except UnicodeEncodeError:pass
    qInstallMessageHandler(message)
    app=QGuiApplication(sys.argv[:1]);app.setApplicationName('SiNiSistar2 × DG-LAB');app.setOrganizationName('SiNiSistarDGLab');app.setFont(QFont('Microsoft YaHei UI',10))
    app.setWindowIcon(QIcon(str(Path(__file__).parent/'assets/portrait.png')))
    backend=Backend(offline=args.offline or bool(args.simulation_demo) or (bool(args.screenshot or args.hud_screenshot) and not args.live_preview) or args.smoke_test,settings=args.settings_file)
    if args.simulation_demo:backend.simulationSource(args.simulation_demo);backend.toggleSimulation()
    elif args.simulate_live:backend.toggleSimulation()
    if args.mock_app:backend.startMockPulse()
    if args.gallery_mock:backend.startMockBoth()
    if args.connect_v4:backend.setPulseBackend('v4');backend.startV4()
    if args.connect_v3:backend.setPulseBackend('v3');backend.startConnection()
    app.aboutToQuit.connect(backend.shutdown)
    backend.exitRequested.connect(lambda:app.exit(0))
    engine=QQmlApplicationEngine();engine.rootContext().setContextProperty('backend',backend);qml=Path(__file__).parent/'qml/ControlCenter.qml';engine.load(QUrl.fromLocalFile(str(qml)))
    if not engine.rootObjects():backend.shutdown();return 2
    window=engine.rootObjects()[0];window.setProperty('pageIndex',max(0,min(8,args.page)))
    if args.gallery_mock:
        window.setProperty('pageIndex',7)
        def select_gallery():
            pending=[window.contentItem()]
            while pending:
                item=pending.pop();pending.extend(item.childItems())
                if item.objectName()=='cgFeedbackPage':item.setProperty('scope','gallery');return
        QTimer.singleShot(100,select_gallery)
    if args.trainer or args.trainer_statuses:
        window.setProperty('pageIndex',1)
        def open_trainer():
            backend.openTrainer()
            dialog=window.findChild(QObject,'trainerDialog')
            if dialog and args.trainer_statuses:dialog.setProperty('tabIndex',1)
        QTimer.singleShot(80,open_trainer)
    if args.abnormal_policy:
        window.setProperty('pageIndex',3)
        def select_abnormal_policy():
            page=window.findChild(QObject,'feedbackPolicyPage')
            if page:page.setProperty('groupIndex',1)
        QTimer.singleShot(50,select_abnormal_policy)
    if args.capture_catalog:
        window.setProperty('pageIndex',6)
        def select_candidates():
            page=window.findChild(QObject,'captureFlowCatalog')
            if page:page.setProperty('catalogMode',1)
        QTimer.singleShot(50,select_candidates)
    if args.death_policy:
        window.setProperty('pageIndex',3)
        def select_death():
            page=window.findChild(QObject,'feedbackPolicyPage')
            if page:page.setProperty('selected',next(i for i,r in enumerate(backend.simulationEvents) if r['key']=='defeat_hold'))
        QTimer.singleShot(50,select_death)
    if args.current_abnormals:
        window.setProperty('pageIndex',5)
        def select_abnormals():
            for page in window.findChildren(QObject,'eventDetectorPage'):
                if not page.property('detached'):page.setProperty('mode',3)
        QTimer.singleShot(50,select_abnormals)
    w,h=map(int,args.size.lower().split('x'));window.setWidth(max(1140,w));window.setHeight(max(780,h))
    hotkey=None
    if sys.platform=='win32' and not (args.screenshot or args.hud_screenshot or args.smoke_test):
        from .hotkeys import GlobalHotkeys
        hotkey=GlobalHotkeys(app,backend);app.aboutToQuit.connect(hotkey.close)
    engine.load(QUrl.fromLocalFile(str(qml.with_name('Monitor.qml'))))
    if len(engine.rootObjects())<2:backend.shutdown();return 2
    monitor=engine.rootObjects()[1];monitor.setProperty('tab',args.hud_tab)
    if args.hud_collapsed:backend.setHudSetting('layout','compact')
    elif args.hud_tab==1:backend.setHudSetting('layout','expanded')
    if args.show_hud or args.hud_screenshot:backend.setHudSetting('enabled',True)
    if args.hud_adjust or args.hud_screenshot:backend.setHudAdjusting(True)
    from .hud_window import HudWindowController
    hud_controller=HudWindowController(backend,monitor);app.aboutToQuit.connect(hud_controller.shutdown)
    if args.hud_settings:backend.openHudSettings()
    target=args.hud_screenshot or args.screenshot
    if target:
        target.parent.mkdir(parents=True,exist_ok=True)
        def capture():
            capture_window=engine.rootObjects()[1] if args.hud_screenshot else window
            frame=capture_window.grabWindow();ok=not frame.isNull() and frame.save(str(target.resolve()));print(str(target.resolve()));app.exit(0 if ok else 3)
        QTimer.singleShot(7200 if args.simulation_demo else 4500 if window.property('pageIndex')==1 else 1100,capture)
    elif args.smoke_test:QTimer.singleShot(1200,app.quit)
    return app.exec()

if __name__=='__main__':raise SystemExit(main())
