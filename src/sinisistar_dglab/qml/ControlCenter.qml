import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Window

ApplicationWindow {
    id: root
    width: 1440; height: 940; minimumWidth: 1140; minimumHeight: 780
    visible: true; color: Theme.bg; title: "SiNiSistar2 × DG-LAB · Control Center"
    property int pageIndex: 0
    property int previousPage: 0
    property int transitionDirection: 1
    onPageIndexChanged: { transitionDirection=pageIndex>=previousPage ? 1 : -1;previousPage=pageIndex;loadPage(); }
    function loadPage() {
        if(!pageLoader)return;
        if(pageLoader.item && typeof pageLoader.item.prepareToLeave==="function")pageLoader.item.prepareToLeave();
        pageLoader.sourceComponent=[overview,gamePluginPage,quickPage,simulationPage,waveforms,diagnostics,flowPage,cgPage,monsterPage][root.pageIndex];
    }
    Component.onCompleted: {loadPage();if(backend.tutorialState.autoShow)Qt.callLater(function(){tutorialDialog.open();});}
    property int selectedRule: 0
    property string notification: ""
    onClosing: close=>{
        if(backend.installState.busy && (backend.installState.phase==="install" || backend.monsterCacheState.busy)){
            close.accepted=false;root.notification="正在安装或生成本地预览，请等待完成后再关闭。";toastTimer.restart();
        } else backend.requestExit();
    }
    readonly property var s: backend.state
    readonly property var capProfile: backend.simulationSettings
    readonly property bool compactToolbar: root.width<1360
    function capText(route) {
        var a=number(capProfile[route+"_cap_a"]),b=number(capProfile[route+"_cap_b"]);
        return a===b ? a : a+"/"+b;
    }
    readonly property var pages: ["总览", "设备与游戏", "快速设置", "联动策略", "波形工作台", "事件检测器", "演出与流程", "CG 反馈", "怪物图鉴"]
    function number(v) { return v === null || v === undefined ? "—" : Math.round(v).toString() }
    function resource(v,m) { return number(v)+" / "+number(m) }
    function waveIndex(key) { for(var i=0;i<backend.waves.length;i++)if(backend.waves[i].key===key)return i;return 0; }
    function wavePoints(key) { return backend.waves[waveIndex(key)].points; }
    Connections { target: backend; function onToast(message) { root.notification=message; toastTimer.restart(); } }
    Connections { target: backend; function onHudSettingsRequested() { root.show();root.raise();root.requestActivate();hudDialog.open(); } }
    HudSettingsDialog { id: hudDialog }
    HotkeySettingsDialog { id: hotkeyDialog }
    SimulationSettingsDialog { id: simulationDialog }
    Connections { target: backend; function onTutorialRequested(){tutorialDialog.open();} }
    Connections { target: backend; function onTrainerRequested(){ root.show();root.raise();root.requestActivate();trainerDialog.open(); } }
    TrainerDialog { id: trainerDialog }
    EventDetectorWindow { ownerWindow: root }
    Timer { id: toastTimer; interval: 4500; onTriggered: root.notification="" }
    Shortcut { sequence: backend.hotkeySettings.sequence; enabled: !backend.emergencyHotkeyRegistered && !backend.hotkeySettings.capturing; onActivated: backend.emergencyStop() }
    Shortcut { sequence: "Ctrl+F11"; enabled: !backend.hudHotkeyRegistered && !backend.hotkeySettings.capturing; onActivated: backend.toggleHudAdjusting() }

    component Heading: RowLayout {
        property string title: ""
        property string detail: ""
        Layout.fillWidth: true; spacing: 12
        AppText { text: title; font.pixelSize: 17; font.weight: Font.DemiBold }
        Rectangle { Layout.fillWidth: true; height: 1; color: Theme.border }
        AppText { text: detail; font.pixelSize: 11; color: Theme.muted }
    }
    component Tag: Rectangle {
        property string label: ""
        property color ink: Theme.gold
        implicitWidth: tagText.implicitWidth+18; implicitHeight: 25
        color: Qt.rgba(ink.r,ink.g,ink.b,.07); border.color: Qt.rgba(ink.r,ink.g,ink.b,.3); radius: 3
        AppText { id: tagText; anchors.centerIn: parent; text: label; color: ink; font.pixelSize: 10 }
    }
    component Metric: Panel {
        property string label: ""
        property var amount: null
        property var maximum: null
        property color accent: Theme.gold
        Layout.fillWidth: true; Layout.preferredHeight: 116
        ColumnLayout { anchors.fill: parent; anchors.margins: 18; spacing: 8
            RowLayout { Layout.fillWidth: true; AppText { text: label; color: Theme.muted; font.pixelSize: 11 } Item { Layout.fillWidth: true } AppText { text: "◆"; color: accent; font.pixelSize: 9 } }
            RowLayout { AppText { text: root.number(amount); font.family: "Georgia"; font.pixelSize: 30; color: Theme.text } AppText { text: "/ "+root.number(maximum); color: Theme.muted; font.pixelSize: 13; Layout.alignment: Qt.AlignBottom; bottomPadding: 5 } }
            Rectangle { Layout.fillWidth: true; height: 3; radius: 2; color: Theme.border; Rectangle { width: maximum && amount!==null ? Math.max(0,Math.min(1,amount/maximum))*parent.width : 0; height: parent.height; color: accent; radius: 2 } }
        }
    }
    component ChannelCard: Panel {
        property int channelIndex: 0
        property color accent: channelIndex===0 ? Theme.gold : Theme.violet
        readonly property var channel: backend.channels[channelIndex]
        readonly property var wire: s.outputChannels[channel.key] || ({active:false})
        Layout.fillWidth: true; Layout.preferredHeight: 205
        ColumnLayout { anchors.fill: parent; anchors.margins: 20; spacing: 9
            RowLayout { Layout.fillWidth: true
                Rectangle { width: 31; height: 31; color: "transparent"; border.color: accent; radius: 4; AppText { anchors.centerIn: parent; text: channel.key; color: accent; font.family: "Georgia"; font.pixelSize: 18 } }
                ColumnLayout { spacing: 2; AppText { text: "通道 "+channel.key; font.pixelSize: 13 } AppText { text: s.connected ? "手机强度反馈" : "等待设备连接"; color: Theme.muted; font.pixelSize: 10 } }
                Item { Layout.fillWidth: true }
                AppText { text: root.number(channelIndex===0?s.strengthA:s.strengthB); font.family: "Georgia"; font.pixelSize: 29; color: accent }
                AppText { text: "/ "+channel.limit; color: Theme.muted }
            }
            WavePlot { Layout.fillWidth: true; Layout.fillHeight: true; points: channelIndex===0?s.traceA:s.traceB; lineColor: accent }
            RowLayout { Layout.fillWidth: true; AppText { text: "通道上限 "+channel.limit+" · 频率由策略决定"; color: Theme.muted; font.pixelSize: 11 } Item { Layout.fillWidth: true } AppText { text: wire.active ? "正在发送" : "无发送"; color: wire.active ? accent : Theme.muted; font.pixelSize: 10 } }
        }
    }
    component EventList: ListView {
        clip: true; spacing: 1; model: backend.events
        delegate: Rectangle {
            required property var modelData
            required property int index
            width: ListView.view.width; height: 39; color: index%2 ? "#171512" : "transparent"
            RowLayout { anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 12; spacing: 14
                AppText { text: modelData.time; color: Theme.muted; font.pixelSize: 11; font.family: "Consolas"; Layout.preferredWidth: 65 }
                AppText { text: "·"; color: modelData.tag==="候选" ? Theme.violet : Theme.gold; font.pixelSize: 21 }
                AppText { text: modelData.text; Layout.fillWidth: true; font.pixelSize: 11 }
                AppText { text: modelData.tag; color: Theme.muted; font.pixelSize: 10 }
            }
        }
        ScrollBar.vertical: ScrollBar {}
    }

    component NavItem: Rectangle {
        id: nav
        property int targetPage: 0
        property int displayIndex: targetPage+1
        readonly property bool selected: root.pageIndex===targetPage
        objectName: "navigation_"+targetPage
        width: 198; height: 48; radius: 4
        color: root.pageIndex===targetPage ? "#30271d" : navMouse.containsMouse ? "#211d18" : "transparent"
        Behavior on color { ColorAnimation { duration: 160 } }
        Rectangle { x: 0; anchors.verticalCenter: parent.verticalCenter; width: 2; height: nav.selected ? 24 : 8; color: Theme.gold; opacity: nav.selected ? 1 : 0
            Behavior on height { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
            Behavior on opacity { NumberAnimation { duration: 150 } }
        }
        Row { anchors.verticalCenter: parent.verticalCenter; x: nav.selected ? 22 : 18; spacing: 15
            Behavior on x { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
            AppText { text: ("0"+displayIndex).slice(-2); font.family: "Georgia"; font.pixelSize: 12; color: root.pageIndex===targetPage ? Theme.gold : "#70675b" }
            AppText { text: root.pages[targetPage]; font.pixelSize: 13; color: root.pageIndex===targetPage ? Theme.text : Theme.muted }
        }
        MouseArea { id: navMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: root.pageIndex=parent.targetPage }
    }

    Rectangle {
        id: sidebar; width: 224; anchors.top: parent.top; anchors.bottom: parent.bottom; color: Theme.sidebar
        Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: Theme.border }
        Image { anchors.bottom: parent.bottom; width: parent.width-1; height: 380; source: ""; fillMode: Image.PreserveAspectCrop; opacity: .25 }
        Rectangle { anchors.bottom: parent.bottom; width: parent.width-1; height: 410; gradient: Gradient { GradientStop { position: 0; color: Theme.sidebar } GradientStop { position: .35; color: "#00161412" } GradientStop { position: 1; color: "#d9161412" } } }
        Column { x: 24; y: 30; spacing: 10
            AppText { text: "S i N i S i s t a r ₂"; font.family: "Georgia"; font.pixelSize: 21; color: Theme.text }
            AppText { text: "D G – L A B   /   C O N T R O L"; font.pixelSize: 9; color: Theme.gold; font.letterSpacing: 1 }
        }
        Rectangle { x: 24; y: 106; width: 174; height: 1; color: Theme.border }
        Column { x: 13; y: 136; spacing: 6
            Repeater { model: [0,1,2,3,7,4]
                NavItem { required property int index; required property int modelData; targetPage: modelData; displayIndex: index+1 }
            }
        }
        Column { x: 13; anchors.bottom: sidebarFooter.top; anchors.bottomMargin: 24; spacing: 6
            Rectangle { objectName: "diagnosticNavSeparator"; x: 11; width: 174; height: 1; color: Theme.border }
            Item { width: 1; height: 9 }
            Repeater { model: [8,5,6]
                NavItem { required property int index; required property int modelData; targetPage: modelData; displayIndex: index+7 }
            }
        }
        Column { id: sidebarFooter; anchors.bottom: parent.bottom; anchors.bottomMargin: 30; x: 26; spacing: 12
            AppText { text: "✦   原生独立联动"; color: Theme.gold; font.pixelSize: 11 }
            AppText { text: "v0.6  ·  PULSE & OVC"; color: Theme.muted; font.pixelSize: 9 }
        }
    }
    Item {
        anchors.left: sidebar.right; anchors.right: parent.right; anchors.top: parent.top; anchors.bottom: parent.bottom
        Rectangle {
            id: topbar; width: parent.width; height: 82; color: Theme.bg
            Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.border }
            Column { anchors.left: parent.left; anchors.leftMargin: 28; anchors.right: topActions.left; anchors.rightMargin: 18; anchors.verticalCenter: parent.verticalCenter; spacing: 5
                AppText { objectName: "topPageTitle"; width: parent.width; text: root.pages[root.pageIndex]; font.pixelSize: 21; font.weight: Font.DemiBold }
                AppText { width: parent.width; text: ["游戏、事件与双通道，一处掌握。","安装游戏插件，扫码连接并分别启用 Pulse 与负鼠。","选择低、中、高预设，快速调整反馈与死亡惩罚强度。","配置联动策略；预览不发送，真实联动需分别启动。","雕刻每一次反馈的形状。","查看真实采集、候选判定和设备发送记录。","记录播放器身份、阶段标签和演出时间。","独立设置观看 CG 时的波形、循环队列与渐强方式。","按贴图浏览怪物、收藏目标，并对照动作素材。"][root.pageIndex]; color: Theme.muted; font.pixelSize: 11 }
            }
            Row { id: topActions; objectName: "topToolbar"; anchors.right: parent.right; anchors.rightMargin: 24; anchors.verticalCenter: parent.verticalCenter; spacing: 8
                GothicActionButton { objectName: "topHardLimits"; implicitWidth: capValues.implicitWidth+26; anchors.verticalCenter: parent.verticalCenter; topPadding: 4; bottomPadding: 4
                    Accessible.name: backend.translate("硬上限",backend.language)+" · Pulse "+root.capText("pulse")+" · OVC "+root.capText("vibration")
                    ToolTip.visible: hovered; ToolTip.text: backend.translate("在快速设置中调整硬上限",backend.language); onClicked: root.pageIndex=2
                    contentItem: Column { spacing: 1
                        AppText { text: "硬上限"; anchors.horizontalCenter: parent.horizontalCenter; color: Theme.muted; font.pixelSize: 9 }
                        Row { id: capValues; anchors.horizontalCenter: parent.horizontalCenter; spacing: 10
                            AppText { objectName: "topPulseCap"; text: "Pulse "+root.capText("pulse"); color: Theme.gold; font.pixelSize: 11 }
                            AppText { objectName: "topOvcCap"; visible: backend.connectionSettings.pulse_backend!=="v3"; text: "负鼠 "+root.capText("vibration"); color: Theme.violet; font.pixelSize: 11 }
                        }
                    }
                }
                GothicActionButton { objectName: "openTutorialButton"; text: root.compactToolbar ? "?" : "新手教程"; implicitWidth: root.compactToolbar ? 44 : backend.language==="en" ? 132 : 100; anchors.verticalCenter: parent.verticalCenter; onClicked: backend.openTutorial(); Accessible.name: backend.translate("新手教程",backend.language); ToolTip.visible: hovered; ToolTip.text: backend.translate("新手教程",backend.language) }
                Item { objectName: "topHudGroup"; anchors.verticalCenter: parent.verticalCenter; width: hudActions.implicitWidth+20; height: 44
                    HoverHandler { id: hudHover }
                    GothicActionFrame { anchors.fill: parent; hovered: hudHover.hovered }
                    Row { id: hudActions; anchors.centerIn: parent; spacing: 8
                        AppText { text: "HUD"; anchors.verticalCenter: parent.verticalCenter; color: Theme.gold; font.pixelSize: 12 }
                        AppSwitch { objectName: "topHudToggle"; anchors.verticalCenter: parent.verticalCenter; checked: !!backend.hudSettings.enabled; Accessible.name: "显示游戏 HUD"; onToggled: backend.setHudSetting('enabled',checked) }
                        Rectangle { width: 1; height: 22; color: Theme.border; anchors.verticalCenter: parent.verticalCenter }
                        GothicActionButton { objectName: "topHudSettings"; anchors.verticalCenter: parent.verticalCenter; text: root.compactToolbar ? "⋯" : "设置"; implicitWidth: root.compactToolbar ? 32 : backend.language==="en" ? 74 : 54; implicitHeight: 30; leftPadding: 6; rightPadding: 6; onClicked: backend.openHudSettings(); Accessible.name: backend.translate("HUD · 联动显示",backend.language); ToolTip.visible: hovered; ToolTip.text: backend.translate("HUD · 联动显示",backend.language) }
                    }
                }
                GothicActionButton { objectName: "topPulseControl"; anchors.verticalCenter: parent.verticalCenter; text: s.armed ? "暂停 Pulse" : "启动 Pulse"; enabled: s.armed || !!s.pulseSetup.canEnable; illuminated: s.armed; onClicked: backend.toggleArm() }
                GothicActionButton { objectName: "topEmergencyStop"; anchors.verticalCenter: parent.verticalCenter; text: "紧急归零"; danger: true; illuminated: s.emergency; onClicked: backend.emergencyStop() }
                GothicActionButton { id: settingsGear; objectName: "openAppSettings"; implicitWidth: 44; anchors.verticalCenter: parent.verticalCenter; leftPadding: 6; rightPadding: 6
                    Accessible.name: backend.translate("控制中心设置",backend.language); ToolTip.visible: hovered; ToolTip.text: backend.translate("控制中心设置",backend.language); onClicked: appSettings.open()
                    contentItem: Canvas { implicitWidth: 22; implicitHeight: 22
                        onPaint: {
                            var ctx=getContext("2d"),cx=width/2,cy=height/2;ctx.reset();ctx.strokeStyle=Theme.gold;ctx.lineWidth=1.5;ctx.lineJoin="round";ctx.beginPath();
                            for(var i=0;i<32;i++){var a=i*Math.PI/16,r=i%4<2 ? 10 : 7.6;var x=cx+Math.cos(a)*r,y=cy+Math.sin(a)*r;if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y);}
                            ctx.closePath();ctx.stroke();ctx.beginPath();ctx.arc(cx,cy,3.2,0,Math.PI*2);ctx.stroke();
                        }
                    }
                }
            }
        }
        Item {
            id: pageStage; anchors.left: parent.left; anchors.right: parent.right; anchors.top: topbar.bottom; anchors.bottom: tutorialDialog.visible ? tutorialDialog.top : footer.top; anchors.margins: 26; clip: true
            Loader {
                id: pageLoader; objectName: "animatedPageLoader"; anchors.fill: parent
                transform: Translate { id: pageShift; x: 0 }
                onLoaded: Qt.callLater(function(){if(tutorialDialog.visible){pageEntrance.stop();pageLoader.opacity=1;pageShift.x=0;pageGleam.opacity=0;}else pageEntrance.restart();})
            }
            Rectangle { id: pageGleam; objectName: "pageTransitionGleam"; anchors.top: parent.top; width: parent.width; height: 1; opacity: 0
                gradient: Gradient { orientation: Gradient.Horizontal; GradientStop { position: 0; color: "#00c3a777" } GradientStop { position: .45; color: Theme.gold } GradientStop { position: 1; color: "#00c3a777" } }
            }
            ParallelAnimation {
                id: pageEntrance; objectName: "pageEntranceAnimation"
                NumberAnimation { target: pageLoader; property: "opacity"; from: 0; to: 1; duration: 240; easing.type: Easing.OutCubic }
                NumberAnimation { target: pageShift; property: "x"; from: root.transitionDirection*18; to: 0; duration: 260; easing.type: Easing.OutCubic }
                NumberAnimation { target: pageGleam; property: "opacity"; from: .65; to: 0; duration: 360; easing.type: Easing.OutCubic }
            }
        }
        TutorialDialog {
            id: tutorialDialog; anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: footer.top
            anchors.leftMargin: 26; anchors.rightMargin: 26; anchors.bottomMargin: 12
            onNavigate: page=>{root.pageIndex=page;}
        }
        Rectangle {
            id: footer; height: 30; anchors.bottom: parent.bottom; width: parent.width; color: "#151310"
            RowLayout { anchors.fill: parent; anchors.leftMargin: 28; anchors.rightMargin: 28
                Rectangle { width: 5; height: 5; radius: 3; color: s.valid ? Theme.green : Theme.muted }
                AppText { text: s.sourceLabel+" · "+s.gameStatus; color: Theme.muted; font.pixelSize: 10 }
                Item { Layout.fillWidth: true }
                AppText { text: s.outputReason; color: s.emergency ? Theme.red : Theme.gold; font.pixelSize: 10 }
                AppText { text: "   /   急停："+backend.hotkeySettings.sequence; color: Theme.muted; font.pixelSize: 10 }
            }
        }
    }

    Popup {
        id: appSettings; objectName: "appSettingsMenu"; parent: Overlay.overlay
        x: parent.width-width-24; y: 72; width: 308; padding: 18
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside; modal: false
        background: Rectangle { radius: 6; color: Theme.panel; border.color: Theme.gold }
        contentItem: ColumnLayout { spacing: 14
            AppText { text: "控制中心设置"; color: Theme.gold; font.pixelSize: 16 }
            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.border }
            AppText { text: "界面语言"; color: Theme.muted; font.pixelSize: 11 }
            AppCombo { objectName: "languageChoice"; Layout.fillWidth: true; model: ["中文","日本語","English"]; currentIndex: ["zh-CN","ja","en"].indexOf(backend.language); onActivated: backend.setLanguage(["zh-CN","ja","en"][currentIndex]) }
            AppButton { objectName: "openHotkeySettings"; text: "急停快捷键"; Layout.fillWidth: true; onClicked: {appSettings.close();hotkeyDialog.open();} }
            AppText { text: backend.hotkeySettings.sequence; color: Theme.silver; font.pixelSize: 11 }
            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.border }
            AppButton { objectName: "openSimulationSettings"; text: "模拟与测试"; Layout.fillWidth: true; onClicked: {appSettings.close();simulationDialog.open();} }
        }
    }

    Component {
        id: overview
        ScrollView { id: ov; clip: true; contentWidth: availableWidth
            ColumnLayout { width: ov.availableWidth; spacing: 17
                Panel { Layout.fillWidth: true; Layout.preferredHeight: 207; clip: true
                    Image { anchors.right: parent.right; width: parent.width*.69; height: parent.height; source: ""; fillMode: Image.PreserveAspectCrop; opacity: .72 }
                    Rectangle { anchors.fill: parent; rotation: 0; gradient: Gradient { orientation: Gradient.Horizontal; GradientStop { position: 0; color: "#211c16" } GradientStop { position: .45; color: "#f0211c16" } GradientStop { position: 1; color: "#00211c16" } } }
                    Column { x: 26; y: 23; spacing: 10; z: 2
                        AppText { text: "THE CHAPEL  /  共感控制中心"; color: Theme.gold; font.pixelSize: 10; font.letterSpacing: 1.8 }
                        AppText { text: "SiNiSistar₂"; font.family: "Georgia"; font.pixelSize: 44; color: "#f3eddf" }
                        AppText { objectName: "overviewProtagonistName"; text: "莉莉娅"; color: "#d4c5ae"; font.pixelSize: 16; font.letterSpacing: 3 }
                        Row { spacing: 8; Tag { label: s.valid ? "游戏已连接" : "等待游戏"; ink: s.valid ? Theme.green : Theme.muted } Tag { label: s.deviceStatus; ink: s.connected ? Theme.green : Theme.gold } Tag { label: s.armed ? "反馈已就绪" : "输出已暂停"; ink: Theme.violet } }
                    }
                    LiliaWalk { anchors.right: parent.right; anchors.rightMargin: 28; anchors.bottom: parent.bottom; anchors.bottomMargin: 8; width: Math.max(170,Math.min(340,parent.width*.37)); height: 163; z: 1 }
                }
                RowLayout { spacing: 14; Layout.fillWidth: true
                    Metric { label: "生命  /  HP"; amount: s.hp; maximum: s.maxHp; accent: Theme.red }
                    Metric { label: "魔力  /  MP"; amount: s.mp; maximum: s.maxMp; accent: Theme.violet }
                    Metric { label: "服装耐久  /  DURABILITY"; amount: s.durability; maximum: s.maxDurability; accent: Theme.gold }
                    Panel { Layout.preferredWidth: 218; Layout.preferredHeight: 116
                        ColumnLayout { anchors.fill: parent; anchors.margins: 18; spacing: 8
                            AppText { text: "当前状态"; color: Theme.muted; font.pixelSize: 11 }
                            AppText { text: s.paused ? "游戏已暂停" : s.bound ? "正在被抓取" : s.gameStatus; color: Theme.gold; font.pixelSize: 20; font.family: "Microsoft YaHei UI" }
                            AppText { text: s.sourceLabel+" · "+s.scene; color: Theme.muted; font.pixelSize: 10; Layout.fillWidth: true }
                        }
                    }
                }
                Heading { title: backend.translate("双通道监视",backend.language); detail: "设备强度仅显示手机真实回传" }
                RowLayout { spacing: 14; Layout.fillWidth: true; ChannelCard { channelIndex: 0 } ChannelCard { channelIndex: 1 } }
                Heading { title: backend.translate("最近事件",backend.language); detail: "观察与输出分别记录" }
                Panel { Layout.fillWidth: true; Layout.preferredHeight: 116; EventList { anchors.fill: parent; anchors.margins: 4 } }
            }
        }
    }
    Component { id: quickPage; QuickSettingsPage { onOpenCg: root.pageIndex=7; onOpenAbnormals: {root.pageIndex=3;Qt.callLater(function(){if(pageLoader.item){pageLoader.item.groupIndex=1;pageLoader.item.selected=0;}});} } }
    Component { id: waveforms; WaveEditorPage { } }
    Component { id: diagnostics; EventDetectorPage { } }
    Component { id: simulationPage; SimulationPage { } }
    Component { id: flowPage; FlowPage { } }
    Component { id: gamePluginPage; GamePluginPage { onOpenPolicies: root.pageIndex=3 } }
    Component { id: cgPage; CgFeedbackPage { } }
    Component { id: monsterPage; MonsterCatalogPage { onOpenCg: root.pageIndex=7 } }
    Rectangle { visible: root.notification!==""; anchors.horizontalCenter: parent.horizontalCenter; anchors.bottom: parent.bottom; anchors.bottomMargin: 48; width: Math.min(700,toastText.implicitWidth+44); height: 45; radius: 6; color: Theme.raised; border.color: Theme.gold; z: 20; AppText { id: toastText; anchors.centerIn: parent; text: root.notification; color: Theme.text; font.pixelSize: 12 } }
}
