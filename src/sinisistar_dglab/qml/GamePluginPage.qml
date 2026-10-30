import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Dialogs as NativeDialogs

ScrollView {
    id: page
    objectName: "gamePluginPage"
    signal openPolicies()
    clip: true; contentWidth: availableWidth
    readonly property var state: backend.installState || ({})
    readonly property var s: backend.state
    readonly property var v4: backend.v4State
    readonly property color gameInk: Theme.gold
    readonly property color connectionInk: Theme.gold
    readonly property color pulseInk: Theme.gold
    readonly property color ovcInk: Theme.gold
    readonly property var settings: backend.connectionSettings
    property string protocol: settings.pulse_backend==="v3" ? "v3" : "v4"
    readonly property bool canInstall: !!state.selectedPath && state.valid && state.payloadReady && !state.gameRunning && !state.busy
    readonly property bool ready: protocol==="v4" ? !!v4.server_ready : settings.pulse_backend==="v3" && !!s.serverReady
    readonly property bool paired: protocol==="v4" ? !!v4.app_connected : settings.pulse_backend==="v3" && !!s.connected
    readonly property bool localTest: protocol==="v4" ? !!v4.local_only : !!s.pulseLocalTest
    readonly property string qrUrl: !ready || localTest ? "" : protocol==="v4" ? v4.qr_url || "" : s.qrUrl || ""
    readonly property string address: ready ? (protocol==="v4" ? v4.lan_ip+":"+v4.port : s.ip+":"+s.port) : settings.lan_ip || "启动时自动选择电脑地址"
    function gameStatus(){return state.error || (state.busy ? state.message : state.pluginOnline ? "观察插件在线 · 正在读取游戏" : state.gameRunning ? "游戏已运行 · 等待观察插件" : state.installedVersion ? "BepInEx 与观察插件已安装" : state.valid ? "游戏目录已核验 · 可以安装" : "请选择游戏目录");}
    function socketStatus(){return protocol==="v4" ? v4.error || (s.dualMockConnected ? "双路模拟 APP 已配对" : v4.app_connected ? "APP 已连接 · 正在识别设备" : ready ? "等待 DG-LAB 4 APP 扫码" : "点击下方按钮，准备扫码连接") : s.deviceError || (s.connected && settings.pulse_backend==="v3" ? "V3 APP 已配对" : ready ? "等待 DG-LAB 3 APP 扫码" : "点击下方按钮，准备扫码连接");}
    function reason(code){return ({"bluetooth-not-connected":"APP 蓝牙尚未连接","channel-muted":"通道已静音","accessory-not-inserted":"负鼠配件未插入","missing-device-state":"等待设备状态","unsupported-device":"暂不支持该设备","unsupported-waveformat":"暂不支持该波形格式"})[code] || code || "通道可用";}
    function openGuide(index: int) {
        var files=["step1_socket.png","step2_initialize.png","step3_connect_server.png","step4_camera_scan.png"];
        if(index>=0 && index<files.length){guideImage.source="../assets/connection-guide/"+files[index];guideDialog.open();}
    }
    Component.onCompleted: if(!backend.gameCandidates.length && !state.busy)backend.scanGameDirectories()
    component Badge: Rectangle {
        property string label: ""
        property color ink: Theme.gold
        implicitWidth: text.implicitWidth+16; implicitHeight: 23; radius: 3
        color: Qt.rgba(ink.r,ink.g,ink.b,.08); border.color: Qt.rgba(ink.r,ink.g,ink.b,.25)
        AppText { id: text; anchors.centerIn: parent; text: parent.label; color: parent.ink; font.pixelSize: 10 }
    }
    component SetupCard: ReadyPanel {
        property color ink: page.connectionInk
        readyColor: ink
        color: Qt.rgba(ink.r,ink.g,ink.b,.045)
        border.color: Qt.rgba(ink.r,ink.g,ink.b,ready ? .85 : .3)
    }
    component DeviceCard: SetupCard {
        id: card
        property bool pulse: true
        readonly property string role: pulse ? "pulse" : "ovc"
        readonly property var selected: (pulse ? page.v4.coyote : page.v4.ovc) || ({})
        readonly property var choices: [{clientId:"",slotId:"",label:"不选择设备"}].concat(backend.v4Devices.filter(function(d){return d.type===(card.pulse ? "COYOTE_030" : "OVC_1");}).map(function(d){return {clientId:d.clientId,slotId:d.slotId,label:(d.name || d.type)+" · "+d.slotId};}))
        readonly property bool v3: pulse && page.settings.pulse_backend==="v3"
        readonly property bool connected: pulse ? page.s.connected : page.s.ovcConnected
        readonly property bool armed: pulse ? page.s.armed : page.s.ovcArmed
        readonly property var setup: (pulse ? page.s.pulseSetup : page.s.ovcSetup) || ({channels:[]})
        readonly property var enabledChannels: pulse ? page.s.pulseChannels : page.s.ovcEnabledChannels
        readonly property bool channelsReady: v3 ? !!page.s.feedbackKnown && (!!enabledChannels.A || !!enabledChannels.B) : (!!enabledChannels.A && selectedItem.channelAReason==="") || (!!enabledChannels.B && selectedItem.channelBReason==="")
        readonly property var selectedItem: backend.v4Devices.find(function(d){return d.clientId===card.selected.selected_client_id && d.slotId===card.selected.selected_slot_id;}) || ({})
        objectName: pulse ? "setupPulseReadyCard" : "setupOvcReadyCard"
        ready: connected && armed && channelsReady && !!setup.canEnable && !page.s.emergency
        ink: pulse ? page.pulseInk : page.ovcInk
        function selectionIndex(){for(var i=1;i<choices.length;i++)if(choices[i].clientId===selected.selected_client_id && choices[i].slotId===selected.selected_slot_id)return i;return 0;}
        Layout.fillWidth: true; Layout.preferredWidth: 1; Layout.alignment: Qt.AlignTop; Layout.preferredHeight: Math.max(207,cardBody.implicitHeight+36)
        ColumnLayout { id: cardBody; anchors.fill: parent; anchors.margins: 18; spacing: 12
            RowLayout { Layout.fillWidth: true
                AppText { text: card.pulse ? "郊狼 Pulse" : "负鼠震动"; color: card.ink; font.pixelSize: 19; Layout.fillWidth: true }
                Badge { label: card.armed ? "已启用" : card.setup.autoPending ? "等待就绪" : "已暂停"; ink: card.armed ? card.ink : Theme.muted }
            }
            AppCombo { accent: card.ink; objectName: card.pulse ? "pulseDeviceChoice" : "ovcDeviceChoice"; Layout.fillWidth: true; visible: !card.v3; model: card.choices; textRole: "label"; currentIndex: card.selectionIndex(); onActivated: {
                    var choice=card.choices[currentIndex];
                    if(card.pulse && currentIndex>0)backend.setPulseBackend("v4");
                    backend.selectV4Device(card.role,choice.clientId,choice.slotId);
                }
            }
            AppText { visible: card.v3; text: card.connected ? "DG-LAB V3 · 手机 APP" : "等待 V3 APP 扫码"; color: Theme.text; font.pixelSize: 13 }
            AppText { objectName: "setupReason_"+card.role; Layout.fillWidth: true; text: card.setup.reason || (card.armed ? "已启用 · 等待实时游戏事件" : "设备已就绪，可以启用输出"); color: card.setup.appError ? Theme.red : Theme.muted; font.pixelSize: 11; wrapMode: Text.Wrap; elide: Text.ElideNone }
            AppText { visible: !!card.setup.appError; Layout.fillWidth: true; text: card.setup.appErrorHint || ""; color: card.ink; font.pixelSize: 11; wrapMode: Text.Wrap; elide: Text.ElideNone }
            Repeater { model: card.setup.showChannels ? card.setup.channels || [] : []
                AppText { required property var modelData; objectName: "setupChannelHint_"+card.role+modelData.channel; Layout.fillWidth: true;
                    text: modelData.channel+" · "+modelData.title+(modelData.rawStatus!==undefined && modelData.rawStatus!==null ? " · APP 状态 "+modelData.rawStatus : "")+(modelData.hint ? "\n"+modelData.hint : "");
                    color: modelData.code ? (card.ink) : Theme.muted; font.pixelSize: 10; wrapMode: Text.Wrap; elide: Text.ElideNone }
            }
            Item { Layout.fillHeight: true }
            DisclosureHeader { id: channelDetails; accent: card.ink; objectName: "setupChannels_"+card.role; Layout.fillWidth: true; title: backend.translate("A/B 通道控制",backend.language); summary: "展开后分别暂停或恢复通道" }
            RowLayout { visible: channelDetails.expanded; Layout.fillWidth: true; spacing: 14
                Repeater { model: ["A","B"]
                    RowLayout { required property string modelData; spacing: 8
                        AppText { text: parent.modelData; color: Theme.muted; font.pixelSize: 11 }
                        AppSwitch { objectName: "setupChannel_"+card.role+parent.modelData; accent: card.ink; checked: (card.pulse ? page.s.pulseChannels : page.s.ovcEnabledChannels)[parent.modelData]; onToggled: card.pulse ? backend.setPulseChannelEnabled(parent.modelData,checked) : backend.setOvcChannelEnabled(parent.modelData,checked) }
                    }
                }
                Item { Layout.fillWidth: true }
            }
            RowLayout { Layout.fillWidth: true; spacing: 8
                AppButton { tinted: true; accent: card.ink; text: "调整联动策略"; Layout.fillWidth: true; onClicked: page.openPolicies() }
                AppButton { tinted: true; accent: card.ink; objectName: card.pulse ? "setupArmPulse" : "setupArmOvc"; text: card.armed ? "暂停输出" : card.setup.buttonLabel || (card.pulse ? "启用 Pulse" : "启用负鼠"); Layout.fillWidth: true; primary: true; enabled: card.armed || !!card.setup.canEnable; onClicked: card.pulse ? backend.toggleArm() : backend.toggleOvcArm() }
            }
            RowLayout { visible: !!card.setup.reason; Layout.fillWidth: true; spacing: 8
                AppButton { tinted: true; accent: card.ink; text: "为什么不能启用？"; objectName: "explainDevice_"+card.role; Layout.fillWidth: true; onClicked: backend.explainOutputUnavailable(card.role) }
                AppButton { tinted: true; accent: card.ink; text: "重新同步并启用"; objectName: "retryDevice_"+card.role; visible: !card.v3 && !!page.v4.app_connected; Layout.fillWidth: true; onClicked: backend.retryDevice(card.role) }
            }
        }
    }
    ColumnLayout { width: page.availableWidth; spacing: 16
        GridLayout { id: topCards; Layout.fillWidth: true; columns: width<760 ? 1 : 2; columnSpacing: 16; rowSpacing: 16
            readonly property real commonHeight: Math.max(gameBody.implicitHeight,connectBody.implicitHeight)+36
            SetupCard { objectName: "setupGameReadyCard"; ink: page.gameInk; ready: !!page.state.gameRunning || !!page.state.pluginOnline; Layout.fillWidth: true; Layout.preferredWidth: 1.1; Layout.preferredHeight: topCards.commonHeight
                ColumnLayout { id: gameBody; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 18; spacing: 12
                    RowLayout { Layout.fillWidth: true
                        AppText { text: "1 · 游戏插件"; color: page.gameInk; font.pixelSize: 19; Layout.fillWidth: true }
                        Badge { label: page.state.pluginOnline ? "已在线" : page.state.installedVersion ? "已安装" : "自动部署"; ink: page.state.pluginOnline ? page.gameInk : Theme.muted }
                    }
                    AppText { Layout.fillWidth: true; text: page.gameStatus(); color: page.state.error ? Theme.red : page.state.pluginOnline ? page.gameInk : Theme.muted; font.pixelSize: 11; wrapMode: Text.Wrap; elide: Text.ElideNone }
                    AppText { Layout.fillWidth: true; text: "选择包含 SiNiSistar2.exe 的 WIN 文件夹，也支持选择上层解压目录。"; color: Theme.muted; font.pixelSize: 11; wrapMode: Text.Wrap; elide: Text.ElideNone }
                    TextField { Layout.fillWidth: true; readOnly: true; selectByMouse: true; text: page.state.selectedPath || backend.translate("正在查找附近的游戏…",backend.language); color: Theme.text; font.pixelSize: 11; padding: 10; background: Rectangle { radius: 4; color: Theme.bg; border.color: Theme.border } }
                    RowLayout { Layout.fillWidth: true; spacing: 8
                        AppButton { tinted: true; accent: page.gameInk; text: "选择目录"; Layout.fillWidth: true; enabled: !page.state.busy; onClicked: folderPicker.open() }
                        AppButton { tinted: true; accent: page.gameInk; objectName: "installGamePluginButton"; text: "安装 / 修复环境"; Layout.fillWidth: true; enabled: page.canInstall; onClicked: backend.installGamePlugin() }
                    }
                    AppButton { tinted: true; accent: page.gameInk; objectName: "installAndLaunchGameButton"; text: page.state.busy ? page.state.phase==="install" ? "正在安装…" : "正在检查…" : page.state.gameRunning ? "游戏已运行" : "一键安装并启动游戏"; Layout.fillWidth: true; implicitHeight: 43; primary: true; enabled: page.canInstall; onClicked: backend.installAndLaunchGame() }
                    ProgressBar { id: installProgress; visible: page.state.busy && page.state.phase==="install"; Layout.fillWidth: true; from: 0; to: 100; value: Number(page.state.progress || 0); implicitHeight: 4; background: Rectangle { color: Theme.border; radius: 2 } contentItem: Item { Rectangle { width: installProgress.visualPosition*parent.width; height: parent.height; color: page.gameInk; radius: 2 } } }
                    AppText { objectName: "gameMonsterCacheStatus"; Layout.fillWidth: true; text: backend.monsterCacheState.error ? "图鉴预览未就绪："+backend.monsterCacheState.error : backend.monsterCacheState.message; color: backend.monsterCacheState.error ? Theme.red : backend.monsterCacheState.ready ? page.gameInk : Theme.muted; font.pixelSize: 10; wrapMode: Text.Wrap; elide: Text.ElideNone }
                    AppText { Layout.fillWidth: true; text: page.state.interfaceMessage || (page.state.compatibilityMode==="runtime-interface" ? "其他渠道构建 · 安装后启动游戏，自动检查接口" : page.state.busy ? page.state.message : "支持已核验的 v1.3.1／Steam Lite（含官方补丁）"); color: page.state.interfaceError ? Theme.red : Theme.muted; font.pixelSize: 10; wrapMode: Text.Wrap; elide: Text.ElideNone }
                }
            }
            SetupCard { objectName: "setupConnectionReadyCard"; ink: page.connectionInk; ready: page.paired; Layout.fillWidth: true; Layout.preferredWidth: 1; Layout.preferredHeight: topCards.commonHeight
                ColumnLayout { id: connectBody; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 18; spacing: 12
                    AppText { text: "2 · 扫码连接"; color: Theme.gold; font.pixelSize: 19 }
                    AppCombo { objectName: "connectionProtocolChoice"; Layout.fillWidth: true; model: ["V3 · DG-LAB 3","V4 · DG-LAB 4"]; currentIndex: page.protocol==="v3" ? 0 : 1; onActivated: {page.protocol=currentIndex===0 ? "v3" : "v4";backend.setPulseBackend(page.protocol);} }
                    RowLayout { Layout.fillWidth: true; spacing: 14
                        ColumnLayout { Layout.fillWidth: true; spacing: 10
                            AppText { Layout.fillWidth: true; text: page.socketStatus(); color: page.ready ? Theme.gold : Theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap; elide: Text.ElideNone }
                            AppText { Layout.fillWidth: true; text: "手机与电脑连接同一局域网。发现郊狼 / 负鼠后自动选择，并在通道就绪后启用；被屏蔽的通道需在 APP 中手动打开。"; color: Theme.muted; font.pixelSize: 11; wrapMode: Text.Wrap; elide: Text.ElideNone }
                            AppText { Layout.fillWidth: true; text: page.address; color: page.connectionInk; font.pixelSize: 11; wrapMode: Text.WrapAnywhere; elide: Text.ElideNone }
                        }
                        Rectangle { Layout.preferredWidth: page.width<1000 ? 150 : 174; Layout.preferredHeight: width; color: page.qrUrl ? "white" : Theme.raised; border.color: Qt.rgba(page.connectionInk.r,page.connectionInk.g,page.connectionInk.b,.35); radius: 4
                            Image { anchors.fill: parent; anchors.margins: 7; source: backend.qrImage(page.qrUrl); fillMode: Image.PreserveAspectFit; visible: !!page.qrUrl }
                            AppText { anchors.centerIn: parent; width: parent.width-20; horizontalAlignment: Text.AlignHCenter; text: page.ready && page.localTest ? "本机模拟 APP\n无需扫码" : "启动连接服务\n后显示二维码"; color: Theme.muted; font.pixelSize: 11; wrapMode: Text.Wrap; visible: !page.qrUrl }
                        }
                    }
                    RowLayout { Layout.fillWidth: true; spacing: 8
                        AppButton { tinted: true; accent: page.connectionInk; objectName: "startSetupConnection"; text: page.ready ? "连接服务已就绪" : "启动扫码连接"; Layout.fillWidth: true; primary: true; enabled: !page.ready; onClicked: {backend.setPulseBackend(page.protocol);backend.startConnection();} }
                        AppButton { tinted: true; accent: page.connectionInk; objectName: "connectionHelpButton"; text: "连接不上？"; Layout.fillWidth: true; onClicked: networkHeader.expanded=!networkHeader.expanded }
                    }
                }
            }
        }
        GridLayout { objectName: "setupDeviceCards"; Layout.fillWidth: true; columns: page.protocol==="v3" || width<760 ? 1 : 2; columnSpacing: 16; rowSpacing: 16
            DeviceCard { pulse: true }
            DeviceCard { pulse: false; visible: page.protocol==="v4" }
        }
        Panel { objectName: "v3ConnectionGuide"; visible: page.protocol==="v3"; Layout.fillWidth: true; Layout.preferredHeight: guideBody.implicitHeight+32
            ColumnLayout { id: guideBody; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 16; spacing: 12
                AppText { text: "DG-LAB 3 · 连接向导"; color: Theme.gold; font.pixelSize: 17 }
                RowLayout { Layout.fillWidth: true; spacing: 10
                    Repeater { model: [{file:"step1_socket.png",title: backend.translate("打开 SOCKET",backend.language)},{file:"step2_initialize.png",title: backend.translate("完成初始化",backend.language)},{file:"step3_connect_server.png",title: backend.translate("连接服务器",backend.language)},{file:"step4_camera_scan.png",title: backend.translate("扫描电脑二维码",backend.language)}]
                        Rectangle { required property var modelData; required property int index; Layout.fillWidth: true; Layout.preferredHeight: page.width<1000 ? 220 : 270; color: Theme.raised; border.color: Theme.border; radius: 4
                            Image { readonly property int loadStatus: status; anchors.fill: parent; anchors.margins: 10; anchors.bottomMargin: 35; source: page.protocol==="v3" ? "../assets/connection-guide/"+parent.modelData.file : ""; fillMode: Image.PreserveAspectFit; smooth: true }
                            Badge { x: 8; y: 8; label: String(parent.index+1) }
                            AppText { anchors.bottom: parent.bottom; anchors.bottomMargin: 10; anchors.horizontalCenter: parent.horizontalCenter; text: parent.modelData.title; color: Theme.text; font.pixelSize: 10 }
                            MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: page.openGuide(parent.index) }
                        }
                    }
                }
            }
        }
        Panel { Layout.fillWidth: true; Layout.preferredHeight: networkBody.implicitHeight+24
            ColumnLayout { id: networkBody; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 12; spacing: 12
                DisclosureHeader { id: networkHeader; objectName: "connectionHelpDisclosure"; Layout.fillWidth: true; title: backend.translate("连接排查与高级设置",backend.language); summary: "局域网地址、端口、V3 + V4 混合连接、通道上限" }
                ColumnLayout { visible: networkHeader.expanded; Layout.fillWidth: true; spacing: 12
                    RowLayout { Layout.fillWidth: true
                        AppText { text: "发现设备后自动选择并启用"; color: Theme.text; Layout.fillWidth: true }
                        AppSwitch { objectName: "autoEnableDevices"; checked: page.settings.auto_enable; onToggled: backend.setConnectionSetting("auto_enable",checked) }
                    }
                    AppText { Layout.fillWidth: true; text: "确认手机与电脑连接同一网络，并允许 Python 通过系统防火墙。V3 使用 DG-LAB 3 APP 的 SOCKET；V4 使用 DG-LAB 4 APP 的扫码连接。修改地址或端口后，点击重启连接。"; color: Theme.muted; font.pixelSize: 11; wrapMode: Text.Wrap; elide: Text.ElideNone }
                    RowLayout { Layout.fillWidth: true; spacing: 10
                        AppText { text: "电脑地址"; color: Theme.muted; font.pixelSize: 11 }
                        TextField { Layout.fillWidth: true; text: page.settings.lan_ip; placeholderText: backend.translate(("自动选择"),backend.language); color: Theme.text; onEditingFinished: backend.setConnectionSetting("lan_ip",text); background: Rectangle { color: Theme.bg; border.color: Theme.border; radius: 3 } }
                        AppButton { text: "查找地址"; onClicked: backend.refreshNetwork() }
                    }
                    Flow { Layout.fillWidth: true; spacing: 6
                        Repeater { model: page.settings.ips || []
                            AppButton { required property string modelData; text: modelData; onClicked: backend.selectIp(modelData) }
                        }
                    }
                    RowLayout { Layout.fillWidth: true; spacing: 10
                        Repeater { model: ["v3_port","v4_port"]
                            RowLayout { required property string modelData; spacing: 8
                                AppText { text: parent.modelData==="v3_port" ? "V3 端口" : "V4 端口"; color: Theme.muted; font.pixelSize: 11 }
                                TextField { implicitWidth: 90; text: page.settings[parent.modelData]; color: Theme.text; validator: IntValidator { bottom:1024; top:65535 } onEditingFinished: backend.setConnectionSetting(parent.modelData,Number(text)); background: Rectangle { color: Theme.bg; border.color: Theme.border; radius: 3 } }
                            }
                        }
                        AppButton { text: "重启连接"; onClicked: {backend.stopConnection();backend.setPulseBackend(page.protocol);backend.startConnection();} }
                        AppButton { text: "复制地址"; enabled: page.ready; onClicked: page.protocol==="v4" ? backend.copyV4Connection() : backend.copyConnection() }
                    }
                    RowLayout { Layout.fillWidth: true; spacing: 10
                        AppButton { tinted: true; accent: page.ovcInk; text: "单独开启 V4 负鼠连接"; onClicked: backend.startV4() }
                        AppButton { text: "断开全部"; danger: true; onClicked: backend.stopConnection() }
                    }
                    AppText { text: "独立通道上限 · 修改后输出暂停"; color: Theme.gold; font.pixelSize: 13 }
                    Repeater { model: [{pulse:true,channel:"A",index:0},{pulse:true,channel:"B",index:1},{pulse:false,channel:"A",index:0},{pulse:false,channel:"B",index:1}]
                        RowLayout { required property var modelData; Layout.fillWidth: true; spacing: 10
                            AppText { text: (parent.modelData.pulse ? "Pulse " : "负鼠 ")+parent.modelData.channel; color: parent.modelData.pulse ? page.pulseInk : page.ovcInk; font.pixelSize: 11; Layout.preferredWidth: 70 }
                            AppSlider { objectName: "setupLimit_"+(parent.modelData.pulse ? "pulse" : "ovc")+parent.modelData.channel; accent: parent.modelData.pulse ? page.pulseInk : page.ovcInk; Layout.fillWidth: true; to: parent.modelData.pulse ? 100 : 200; stepSize: parent.modelData.pulse ? 1 : 10; value: parent.modelData.pulse ? backend.channels[parent.modelData.index].limit : backend.ovcLimits[parent.modelData.channel]; onMoved: parent.modelData.pulse ? backend.setChannel(parent.modelData.index,"limit",value) : backend.setOvcLimit(parent.modelData.channel,value) }
                            AppText { text: parent.modelData.pulse ? backend.channels[parent.modelData.index].limit : backend.ovcLimits[parent.modelData.channel]; color: parent.modelData.pulse ? page.pulseInk : page.ovcInk; Layout.preferredWidth: 30 }
                        }
                    }
                }
            }
        }
        Panel { Layout.fillWidth: true; Layout.preferredHeight: folderBody.implicitHeight+24
            ColumnLayout { id: folderBody; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 12; spacing: 12
                DisclosureHeader { id: folderHeader; accent: page.gameInk; objectName: "gameDirectoryDisclosure"; Layout.fillWidth: true; title: backend.translate("游戏目录与安装详情",backend.language); summary: "附近找到 "+backend.gameCandidates.length+" 个目录 · 安装日志与重新检查" }
                ColumnLayout { visible: folderHeader.expanded; Layout.fillWidth: true; spacing: 10
                    RowLayout { Layout.fillWidth: true
                        AppButton { tinted: true; accent: page.gameInk; text: "查找附近游戏"; enabled: !page.state.busy; onClicked: backend.scanGameDirectories() }
                        AppButton { tinted: true; accent: page.gameInk; text: "重新检查"; enabled: !!page.state.selectedPath && !page.state.busy; onClicked: backend.chooseGameDirectory(page.state.selectedPath) }
                        Item { Layout.fillWidth: true }
                    }
                    Repeater { model: backend.gameCandidates
                        RowLayout { required property var modelData; Layout.fillWidth: true
                            AppText { Layout.fillWidth: true; text: parent.modelData.path; color: Theme.muted; font.pixelSize: 11; wrapMode: Text.WrapAnywhere; elide: Text.ElideNone }
                            AppButton { tinted: true; accent: page.gameInk; text: page.state.selectedPath===parent.modelData.path ? "已选择" : "选择"; enabled: !page.state.busy && page.state.selectedPath!==parent.modelData.path; onClicked: backend.chooseGameDirectory(parent.modelData.path) }
                        }
                    }
                    AppText { Layout.fillWidth: true; text: page.state.message || "选择目录后核验游戏版本。"; color: Theme.muted; font.pixelSize: 11; wrapMode: Text.Wrap; elide: Text.ElideNone }
                    AppText { Layout.fillWidth: true; text: "安装成功后由游戏启动加载插件。修复环境前请退出游戏；观察插件在线才表示加载成功。"; color: Theme.muted; font.pixelSize: 10; wrapMode: Text.Wrap; elide: Text.ElideNone }
                }
            }
        }
    }
    NativeDialogs.FolderDialog { id: folderPicker; title: backend.translate("选择 SiNiSistar2 游戏目录",backend.language); onAccepted: backend.chooseGameDirectory(selectedFolder.toString()) }
    Dialog { id: guideDialog; objectName: "connectionGuideDialog"; parent: Overlay.overlay; anchors.centerIn: parent; width: Math.min(800,parent.width-50); height: Math.min(900,parent.height-50); modal: true; padding: 15; standardButtons: Dialog.Close; background: Rectangle { color: Theme.panel; border.color: Theme.gold; radius: 5 }
        contentItem: Image { id: guideImage; fillMode: Image.PreserveAspectFit; smooth: true }
    }
}
