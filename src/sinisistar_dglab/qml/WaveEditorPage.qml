import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

RowLayout {
    id: page
    objectName: "waveEditorPage"
    spacing: 18
    readonly property bool vibration: backend.editingRoute==="vibration"
    readonly property color accent: vibration ? Theme.violet : Theme.gold
    readonly property var catalog: vibration ? backend.vibrationWaves : backend.waves
    readonly property string currentKey: backend.selectedWave
    readonly property bool custom: currentKey.indexOf("custom_")===0 || currentKey.indexOf("vib_custom_")===0
    readonly property var currentWave: lookup(currentKey)
    readonly property int customCount: {var total=0;for(var i=0;i<catalog.length;i++)if(isCustom(catalog[i].key))total++;return total;}
    property int filter: 0
    property var history: []
    property int historyIndex: 0
    property var savedDraft: []
    property string pendingKey: ""
    property string pendingRoute: ""
    readonly property bool dirty: differs(backend.points,savedDraft)
    readonly property var filteredCatalog: {
        var result=[];var text=search.text.toLowerCase();
        for(var i=0;i<catalog.length;i++){
            var wave=catalog[i],mine=isCustom(wave.key);
            if((filter===1 && mine)||(filter===2 && !mine))continue;
            if(text && String(wave.name).toLowerCase().indexOf(text)<0)continue;
            result.push(wave);
        }return result;
    }
    function isCustom(key){return key.indexOf("custom_")===0 || key.indexOf("vib_custom_")===0;}
    function lookup(key){for(var i=0;i<catalog.length;i++)if(catalog[i].key===key)return catalog[i];return ({});}
    function differs(a,b){if(a.length!==b.length)return true;for(var i=0;i<a.length;i++)if(Math.abs(Number(a[i])-Number(b[i]))>.000001)return true;return false;}
    function resetHistory(){var p=backend.points.slice();savedDraft=p.slice();history=[p];historyIndex=0;}
    function commitStroke(){var p=backend.points.slice();if(history.length && !differs(p,history[historyIndex]))return;history=history.slice(0,historyIndex+1).concat([p]);historyIndex=history.length-1;}
    function applyPoints(points){backend.setWavePoints(points);commitStroke();}
    function undo(){if(historyIndex>0){historyIndex--;backend.setWavePoints(history[historyIndex]);}}
    function redo(){if(historyIndex+1<history.length){historyIndex++;backend.setWavePoints(history[historyIndex]);}}
    function finishSave(){savedDraft=backend.points.slice();}
    function requestSelect(key){if(key===currentKey)return;pendingKey=key;pendingRoute="";if(dirty)discardDialog.open();else applySelection();}
    function requestRoute(route){if(route===backend.editingRoute)return;pendingRoute=route;pendingKey="";if(dirty)discardDialog.open();else applySelection();}
    function applySelection(){if(pendingRoute)backend.editWaveRoute(pendingRoute);else if(pendingKey)backend.selectWave(pendingKey);pendingRoute="";pendingKey="";}
    function openCreate(blank){createDialog.blank=blank;newName.text=blank ? (vibration ? "我的负鼠波形" : "我的 Pulse 波形") : (currentWave.name || "我的波形")+" · 自定";createDialog.open();}
    function smooth(){var p=backend.points.slice();applyPoints(p.map(function(v,i){return (Number(p[Math.max(0,i-1)])+Number(v)+Number(p[Math.min(15,i+1)]))/3;}));}
    function normalize(){var p=backend.points.slice(),high=Math.max.apply(null,p);if(high>0)applyPoints(p.map(function(v){return Number(v)/high;}));}
    function template(kind){
        var p=[];for(var i=0;i<16;i++){
            var x=i/15;
            p.push(kind==="breath" ? Math.sin(x*Math.PI)*Math.sin(x*Math.PI) : kind==="steps" ? Math.floor(x*4)/4 : kind==="rise" ? x : kind==="beat" ? ([0,.25,1,.3,0,.12,.55,.2,0,0,0,.2,.8,.2,0,0][i]) : 0);
        }applyPoints(p);
    }
    onCurrentKeyChanged: Qt.callLater(resetHistory)
    Component.onCompleted: resetHistory()
    Shortcut { sequences: [StandardKey.Undo]; enabled: page.visible && page.historyIndex>0; onActivated: page.undo() }
    Shortcut { sequences: [StandardKey.Redo]; enabled: page.visible && page.historyIndex+1<page.history.length; onActivated: page.redo() }

    Panel {
        Layout.preferredWidth: 265; Layout.minimumWidth: 230; Layout.fillHeight: true
        ColumnLayout { anchors.fill: parent; anchors.margins: 17; spacing: 13
            RowLayout { Layout.fillWidth: true
                AppText { text: "波形藏室"; font.family: "Georgia"; font.pixelSize: 21; color: Theme.gold; Layout.fillWidth: true }
                AppText { text: page.filteredCatalog.length+" 首"; color: Theme.muted; font.pixelSize: 10 }
            }
            RowLayout { Layout.fillWidth: true; spacing: 6
                AppButton { Layout.fillWidth: true; implicitWidth: 90; objectName: "waveRoutePulse"; text: "Pulse"; primary: !page.vibration; onClicked: page.requestRoute("pulse") }
                AppButton { Layout.fillWidth: true; implicitWidth: 90; objectName: "waveRouteOvc"; text: "负鼠"; accent: Theme.violet; primary: page.vibration; onClicked: page.requestRoute("vibration") }
            }
            TextField { id: search; Layout.fillWidth: true; placeholderText: backend.translate(("寻找波形…"),backend.language); selectByMouse: true; color: Theme.text; padding: 11; font.pixelSize: 11
                background: Rectangle { radius: 4; color: Theme.bg; border.color: search.activeFocus ? page.accent : Theme.border }
            }
            AppCombo { Layout.fillWidth: true; model: ["全部波形","预设波形","我的波形"]; currentIndex: page.filter; onActivated: page.filter=currentIndex }
            ListView { id: library; Layout.fillWidth: true; Layout.fillHeight: true; model: page.filteredCatalog; clip: true; spacing: 8
                ScrollBar.vertical: ScrollBar { }
                delegate: Rectangle {
                    required property var modelData
                    width: library.width-9; height: 97; radius: 4
                    color: page.currentKey===modelData.key ? "#30281e" : Theme.bg
                    border.color: page.currentKey===modelData.key ? page.accent : "#302a22"
                    ColumnLayout { anchors.fill: parent; anchors.margins: 10; spacing: 3
                        RowLayout { Layout.fillWidth: true
                            AppText { Layout.fillWidth: true; text: modelData.name; color: page.currentKey===modelData.key ? page.accent : Theme.text; font.pixelSize: 11 }
                            AppText { text: page.isCustom(modelData.key) ? "自定" : modelData.key.indexOf("official_")===0 || modelData.key.indexOf("ovc_")===0 ? "官方" : "预设"; color: Theme.muted; font.pixelSize: 8 }
                        }
                        WavePlot { Layout.fillWidth: true; Layout.fillHeight: true; points: modelData.points; grid: false; lineColor: page.currentKey===modelData.key ? page.accent : "#82725b" }
                    }
                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: page.requestSelect(modelData.key) }
                }
                AppText { anchors.centerIn: parent; visible: library.count===0; text: "这里还没有波形"; color: Theme.muted; font.pixelSize: 11 }
            }
            AppButton { Layout.fillWidth: true; text: page.customCount>=20 ? "自定义波形已满（20）" : "+ 添加自定义波形"; enabled: page.customCount<20; primary: true; accent: page.accent; onClicked: page.openCreate(true) }
        }
    }

    ColumnLayout { Layout.fillWidth: true; Layout.fillHeight: true; spacing: 14
        RowLayout { Layout.fillWidth: true
            ColumnLayout { Layout.fillWidth: true; spacing: 5
                AppText { Layout.fillWidth: true; text: page.currentWave.name || "选择一首波形"; font.family: "Georgia"; font.pixelSize: 26; color: Theme.text }
                AppText { text: (page.vibration ? "负鼠" : "Pulse")+"  /  "+(page.custom ? "我的波形" : "预设草稿")+(page.dirty ? "  ·  尚未保存" : ""); color: page.dirty ? page.accent : Theme.muted; font.pixelSize: 11 }
            }
            AppButton { visible: page.custom; text: "重命名"; implicitWidth: 84; onClicked: {renameName.text=page.currentWave.name;renameDialog.open();} }
            AppButton { visible: page.custom; text: "删除"; danger: true; implicitWidth: 70; onClicked: deleteDialog.open() }
        }
        AppText { Layout.fillWidth: true; text: "按住画布连续拖绘，经过的节点会跟随笔迹；向左、向右都能一笔画完。"; color: Theme.muted; font.pixelSize: 11; wrapMode: Text.Wrap; elide: Text.ElideNone }
        Panel { Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 270
            color: "#14120f"; border.color: "#655139"
            ColumnLayout { anchors.fill: parent; anchors.margins: 16; spacing: 9
                RowLayout { Layout.fillWidth: true
                    AppText { text: "WAVE ATELIER"; font.pixelSize: 9; font.letterSpacing: 2; color: page.accent }
                    Item { Layout.fillWidth: true }
                    AppText { text: pad.cursorIndex>=0 && backend.points.length===16 ? "节点 "+(pad.cursorIndex+1)+"   ·   "+Math.round(Number(backend.points[pad.cursorIndex])*100)+"%" : "16 个控制节点"; font.pixelSize: 10; color: Theme.muted }
                }
                WaveDrawPad { id: pad; Layout.fillWidth: true; Layout.fillHeight: true; points: backend.points; ink: page.accent
                    onStrokeEdited: (x0,y0,x1,y1)=>backend.editWaveStroke(x0,y0,x1,y1)
                    onStrokeFinished: page.commitStroke()
                }
                RowLayout { Layout.fillWidth: true; spacing: 6
                    AppButton { text: "撤销"; implicitWidth: 64; implicitHeight: 32; enabled: page.historyIndex>0; onClicked: page.undo() }
                    AppButton { text: "重做"; implicitWidth: 64; implicitHeight: 32; enabled: page.historyIndex+1<page.history.length; onClicked: page.redo() }
                    Rectangle { width: 1; height: 20; color: Theme.border }
                    AppButton { text: "平滑"; implicitWidth: 64; implicitHeight: 32; onClicked: page.smooth() }
                    AppButton { text: "镜像"; implicitWidth: 64; implicitHeight: 32; onClicked: page.applyPoints(backend.points.slice().reverse()) }
                    AppButton { text: "铺满"; implicitWidth: 64; implicitHeight: 32; onClicked: page.normalize() }
                    AppButton { text: "清空"; implicitWidth: 64; implicitHeight: 32; onClicked: page.template("clear") }
                    Item { Layout.fillWidth: true }
                }
            }
        }
        RowLayout { Layout.fillWidth: true; spacing: 7
            AppText { text: "从形状开始"; color: Theme.muted; font.pixelSize: 10; Layout.rightMargin: 6 }
            AppButton { text: "呼吸"; implicitWidth: 72; implicitHeight: 32; onClicked: page.template("breath") }
            AppButton { text: "双拍"; implicitWidth: 72; implicitHeight: 32; onClicked: page.template("beat") }
            AppButton { text: "渐起"; implicitWidth: 72; implicitHeight: 32; onClicked: page.template("rise") }
            AppButton { text: "阶梯"; implicitWidth: 72; implicitHeight: 32; onClicked: page.template("steps") }
            Item { Layout.fillWidth: true }
            AppText { text: "Ctrl+Z / Ctrl+Y"; color: Theme.muted; font.pixelSize: 9 }
        }
        RowLayout { Layout.fillWidth: true; spacing: 10
            AppText { Layout.fillWidth: true; text: page.custom ? "保存后可在联动策略中选择这首波形。" : "喜欢当前节奏？另存一首属于自己的波形。"; color: Theme.muted; font.pixelSize: 11; wrapMode: Text.Wrap; elide: Text.ElideNone }
            AppButton { text: "另存为新波形"; enabled: page.customCount<20; onClicked: page.openCreate(false) }
            AppButton { visible: page.custom; text: "保存修改"; primary: true; accent: page.accent; enabled: page.dirty; onClicked: {backend.updateCustomWave();page.finishSave();} }
        }
        AppText { Layout.fillWidth: true; text: "画布只预览，不会发送。预设保持原样；自定义波形的强度、周期与频率在策略中设置。"; color: Theme.violet; font.pixelSize: 10; wrapMode: Text.Wrap; elide: Text.ElideNone }
    }

    component NameField: TextField { selectByMouse: true; maximumLength: 32; color: Theme.text; font.pixelSize: 13; padding: 13; background: Rectangle { color: Theme.bg; border.color: parent.activeFocus ? Theme.gold : Theme.border; radius: 4 } }
    component ChapelDialog: Dialog { parent: Overlay.overlay; anchors.centerIn: parent; width: Math.min(480,parent.width-40); modal: true; padding: 24; closePolicy: Popup.CloseOnEscape; background: Rectangle { color: Theme.panel; border.color: Theme.gold; radius: 5 } }
    ChapelDialog { id: createDialog; property bool blank: true; onOpened: newName.forceActiveFocus()
        contentItem: ColumnLayout { spacing: 17
            AppText { text: "添加自定义波形"; font.pixelSize: 22; color: Theme.gold }
            NameField { id: newName; Layout.fillWidth: true; placeholderText: backend.translate(("为新波形命名" ),backend.language)}
            AppCombo { Layout.fillWidth: true; model: ["使用当前草稿","从空白开始"]; currentIndex: createDialog.blank ? 1 : 0; onActivated: createDialog.blank=currentIndex===1 }
            AppText { Layout.fillWidth: true; text: "创建后即可连续拖绘，完成后保存修改。"; color: Theme.muted; font.pixelSize: 11; wrapMode: Text.Wrap }
            RowLayout { Layout.fillWidth: true; Item { Layout.fillWidth: true } AppButton { text: "取消"; onClicked: createDialog.close() } AppButton { text: "创建波形"; primary: true; accent: page.accent; enabled: newName.text.trim().length>0; onClicked: {backend.addCustomWave(newName.text,createDialog.blank);createDialog.close();Qt.callLater(page.resetHistory);} } }
        }
    }
    ChapelDialog { id: renameDialog; onOpened: renameName.forceActiveFocus()
        contentItem: ColumnLayout { spacing: 17
            AppText { text: "为波形改名"; font.pixelSize: 22; color: Theme.gold }
            NameField { id: renameName; Layout.fillWidth: true }
            RowLayout { Layout.fillWidth: true; Item { Layout.fillWidth: true } AppButton { text: "取消"; onClicked: renameDialog.close() } AppButton { text: "保存名称"; primary: true; accent: page.accent; enabled: renameName.text.trim().length>0; onClicked: {backend.renameCustomWave(renameName.text);renameDialog.close();} } }
        }
    }
    ChapelDialog { id: deleteDialog
        contentItem: ColumnLayout { spacing: 17
            AppText { text: "删除自定义波形"; font.pixelSize: 22; color: Theme.gold }
            AppText { Layout.fillWidth: true; text: "删除「"+(page.currentWave.name || "")+"」？预设波形不会受影响。"; color: Theme.text; wrapMode: Text.Wrap; elide: Text.ElideNone }
            RowLayout { Layout.fillWidth: true; Item { Layout.fillWidth: true } AppButton { text: "取消"; onClicked: deleteDialog.close() } AppButton { text: "删除波形"; danger: true; onClicked: {backend.deleteCustomWave();deleteDialog.close();} } }
        }
    }
    ChapelDialog { id: discardDialog
        contentItem: ColumnLayout { spacing: 17
            AppText { text: "草稿尚未保存"; font.pixelSize: 22; color: Theme.gold }
            AppText { Layout.fillWidth: true; text: "切换波形会放弃当前草稿。"; color: Theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap }
            RowLayout { Layout.fillWidth: true; AppButton { text: "继续编辑"; onClicked: discardDialog.close() } Item { Layout.fillWidth: true } AppButton { text: "放弃并切换"; primary: true; accent: page.accent; onClicked: {discardDialog.close();page.applySelection();} } }
        }
    }
}
