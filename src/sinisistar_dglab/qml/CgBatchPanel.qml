import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

ColumnLayout {
    id: page
    objectName: "cgBatchPanel"
    readonly property var batch: backend.cgBatch
    property bool followCurrent: true
    property string selected: ""
    property string pendingKey: ""
    property string pendingText: ""
    readonly property var chosen: batch.rows.find(r=>r.id===selected) || ({})
    readonly property var filtered: batch.rows.filter(function(r){
        var q=search.text.trim().toLowerCase();
        return (!q || [r.title,r.name,r.raw_enemy,r.note].join(" ").toLowerCase().indexOf(q)>=0)
            && (filter.currentIndex===0 || filter.currentIndex===1 && r.visits && !r.verdict || filter.currentIndex===2 && r.verdict==="no" || filter.currentIndex===3 && r.verdict==="yes");
    })
    function flushNote(){ if(pendingKey){noteSave.stop();var key=pendingKey,value=pendingText;pendingKey="";backend.noteCgBatch(key,value);} }
    function selectCase(key){flushNote();selected=key;notes.text=chosen.note || "";}
    function mark(value){flushNote();backend.markCgBatch(selected,value);}
    function synchronize(){
        if(followCurrent && batch.focus && batch.focus!==selected)selectCase(batch.focus);
        else if(!selected && batch.rows.length)selectCase(batch.rows[0].id);
    }
    onBatchChanged: synchronize()
    Component.onCompleted: {backend.beginCgBatch();synchronize();}
    Component.onDestruction: flushNote()
    Timer { id: noteSave; interval: 500; onTriggered: page.flushNote() }
    spacing: 16
    Panel { Layout.fillWidth: true; Layout.preferredHeight: header.implicitHeight+32
        ColumnLayout { id: header; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 16; spacing: 10
            RowLayout { Layout.fillWidth: true
                AppText { text: "CG 批量测试"; color: Theme.gold; font.pixelSize: 23; Layout.fillWidth: true }
                AppText { text: page.batch.status==="finished" ? "本轮已完成" : page.batch.recording ? "自动记录中" : "记录已暂停"; color: page.batch.recording ? Theme.green : Theme.muted; font.pixelSize: 12 }
                AppText { text: page.batch.error ? "保存失败" : page.batch.saved ? "已保存" : "正在保存"; color: page.batch.error ? Theme.red : Theme.muted; font.pixelSize: 11 }
            }
            AppText { Layout.fillWidth: true; text: "在游戏中打开 CG，这里自动识别。看过后选择有无反馈，再切换下一段。每次选择立即保存，可关闭后继续。"; color: Theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap; elide: Text.ElideNone }
            AppText { Layout.fillWidth: true; text: "已观察 "+page.batch.observed+" / 已发现 "+page.batch.known+" 段 · 有反馈 "+page.batch.yes+" · 无反馈 "+page.batch.no+" · 待标记 "+page.batch.unmarked; color: Theme.silver; font.pixelSize: 14; wrapMode: Text.Wrap; elide: Text.ElideNone }
            AppText { Layout.fillWidth: true; text: (backend.state.dualMockConnected ? "模拟 APP 已连接" : "尚未连接模拟 APP")+" · "+(backend.simulationSettings.cg_detection_mode==="playback_only" ? "无 HP 模式" : "混合模式"); color: Theme.muted; font.pixelSize: 11 }
            RowLayout { Layout.fillWidth: true
                AppText { text: "跟随当前 CG"; color: Theme.muted; font.pixelSize: 11 }
                AppSwitch { objectName: "cgBatchFollow"; checked: page.followCurrent; onToggled: {page.followCurrent=checked;page.synchronize();} }
                Item { Layout.fillWidth: true }
                AppButton { objectName: "cgBatchExport"; text: "导出当前记录"; onClicked: {page.flushNote();backend.exportCgBatch(false);} }
                AppButton { objectName: "cgBatchFinish"; text: "完成并导出"; primary: true; onClicked: {page.flushNote();backend.exportCgBatch(true);} }
            }
            AppText { visible: page.batch.error!==""; Layout.fillWidth: true; text: page.batch.error; color: Theme.red; wrapMode: Text.Wrap; elide: Text.ElideNone }
        }
    }
    Panel { objectName: "cgBatchCurrentCard"; Layout.fillWidth: true; Layout.preferredHeight: currentBody.implicitHeight+40
        ColumnLayout { id: currentBody; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 20; spacing: 12
            AppText { text: page.chosen.id ? page.chosen.current ? "当前 CG" : "选中的记录 / 最近片段" : "等待你打开 CG"; color: Theme.muted; font.pixelSize: 11 }
            AppText { objectName: "cgBatchCurrentTitle"; text: page.chosen.title || "进入游戏图鉴，选择任意 [1] / [2] / [3]"; color: Theme.silver; font.pixelSize: 24; Layout.fillWidth: true }
            AppText { objectName: "cgBatchCurrentTake"; text: page.chosen.id ? (page.chosen.name || "正在读取片段名…")+" · "+(page.chosen.kind || "等待播放字段") : "即使未触发输出，也可以标记无反馈。"; color: Theme.gold; font.pixelSize: 13; Layout.fillWidth: true }
            RowLayout { Layout.fillWidth: true; spacing: 16
                AppButton { id: yesButton; objectName: "cgBatchYes"; Layout.fillWidth: true; implicitHeight: 68; text: page.chosen.verdict==="yes" ? "✓ 已标记 · 有反馈" : "有反馈"; accent: Theme.green; primary: page.chosen.verdict==="yes"; tinted: true; enabled: !!page.chosen.visits && page.batch.status!=="finished" && page.batch.status!=="blocked"; onClicked: page.mark("yes")
                    contentItem: AppText { text: yesButton.text; color: yesButton.primary ? Theme.bg : Theme.green; font.pixelSize: 18; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                }
                AppButton { id: noButton; objectName: "cgBatchNo"; Layout.fillWidth: true; implicitHeight: 68; text: page.chosen.verdict==="no" ? "× 已标记 · 无反馈" : "无反馈"; accent: Theme.red; primary: page.chosen.verdict==="no"; tinted: true; enabled: !!page.chosen.visits && page.batch.status!=="finished" && page.batch.status!=="blocked"; onClicked: page.mark("no")
                    contentItem: AppText { text: noButton.text; color: noButton.primary ? Theme.bg : Theme.red; font.pixelSize: 18; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                }
            }
            RowLayout { Layout.fillWidth: true
                AppText { text: "你的标记："+(page.chosen.manual_label || "待标记"); color: page.chosen.verdict==="no" ? Theme.red : Theme.silver; font.pixelSize: 12; Layout.fillWidth: true }
                AppButton { objectName: "cgBatchUndo"; text: "撤销标记"; implicitHeight: 28; enabled: !!page.chosen.verdict && page.batch.status!=="finished"; onClicked: page.mark("") }
            }
            DisclosureHeader { id: details; objectName: "cgBatchDetails"; Layout.fillWidth: true; title: "备注与自动检测"; summary: "可选 · 不影响你的有无反馈标记" }
            ColumnLayout { visible: details.expanded; Layout.fillWidth: true; spacing: 9
                TextArea { id: notes; objectName: "cgBatchNote"; Layout.fillWidth: true; Layout.preferredHeight: 70; color: Theme.text; font.pixelSize: 12; wrapMode: TextEdit.Wrap; placeholderText: backend.translate("可选备注，例如只有 A 通道、反馈延迟或暂停异常",backend.language); enabled: !!page.chosen.visits && page.batch.status!=="finished"; background: Rectangle { color: Theme.raised; border.color: Theme.border; radius: 4 }
                    onTextChanged: if(activeFocus && page.selected){page.pendingKey=page.selected;page.pendingText=text;noteSave.restart();}
                }
                AppText { Layout.fillWidth: true; text: "自动检测："+(page.chosen.automatic || "等待数据"); color: Theme.gold; font.pixelSize: 12 }
                RowLayout { Layout.fillWidth: true
                    Repeater { model: ["pulseA","pulseB","vibrationA","vibrationB"]
                        Rectangle { required property string modelData; Layout.fillWidth: true; Layout.preferredHeight: 44; color: Theme.raised; border.color: modelData.indexOf("vibration")===0 ? Theme.violet : Theme.gold; radius: 4
                            AppText { anchors.centerIn: parent; text: (parent.modelData.indexOf("vibration")===0 ? "负鼠 " : "Pulse ")+parent.modelData.slice(-1)+" · "+((page.chosen.latest_counts || {})[parent.modelData] || 0)+" 包"; color: parent.border.color; font.pixelSize: 11 }
                        }
                    }
                }
                AppText { Layout.fillWidth: true; text: page.chosen.reason || "自动数据与人工选择分别保存。"; color: Theme.muted; font.pixelSize: 10; wrapMode: Text.Wrap; elide: Text.ElideNone }
            }
        }
    }
    RowLayout { Layout.fillWidth: true
        AppText { text: "本轮记录"; color: Theme.gold; font.pixelSize: 17 }
        Item { Layout.fillWidth: true }
        TextField { id: search; objectName: "cgBatchSearch"; Layout.preferredWidth: 230; color: Theme.text; font.pixelSize: 12; placeholderText: backend.translate("搜索怪物、片段或备注",backend.language); background: Rectangle { color: Theme.raised; border.color: Theme.border; radius: 4 } }
        AppCombo { id: filter; objectName: "cgBatchFilter"; Layout.preferredWidth: 130; model: ["全部","待标记","无反馈","有反馈"] }
    }
    Panel { Layout.fillWidth: true; Layout.preferredHeight: 350
        ListView { objectName: "cgBatchHistory"; anchors.fill: parent; anchors.margins: 8; clip: true; spacing: 5; model: page.filtered
            delegate: Rectangle {
                required property var modelData
                width: ListView.view.width; height: 67; radius: 4; color: modelData.id===page.selected ? "#30271d" : Theme.raised; border.color: modelData.id===page.selected ? Theme.gold : Theme.border
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: {page.followCurrent=false;page.selectCase(parent.modelData.id);} }
                ColumnLayout { anchors.fill: parent; anchors.margins: 10; spacing: 4
                    RowLayout { Layout.fillWidth: true
                        AppText { text: modelData.title+" · "+(modelData.name || "未打开"); Layout.fillWidth: true; color: Theme.silver; font.pixelSize: 12 }
                        AppText { text: modelData.manual_label; color: modelData.verdict==="no" ? Theme.red : modelData.verdict==="yes" ? Theme.green : Theme.muted; font.pixelSize: 12 }
                    }
                    AppText { Layout.fillWidth: true; text: modelData.note || modelData.automatic; color: Theme.muted; font.pixelSize: 10 }
                }
            }
            ScrollBar.vertical: ScrollBar {}
        }
    }
    RowLayout { Layout.fillWidth: true
        AppButton { objectName: "cgBatchPause"; text: page.batch.recording ? "暂停记录" : "继续记录"; enabled: page.batch.status!=="finished"; onClicked: {page.flushNote();backend.toggleCgBatch();} }
        AppButton { objectName: "cgBatchNew"; text: "新建一轮"; onClicked: {page.flushNote();backend.newCgBatch();page.selected="";} }
        AppButton { objectName: "cgBatchMock"; text: "连接模拟 APP"; onClicked: backend.startMockBoth() }
        Item { Layout.fillWidth: true }
        AppButton { objectName: "cgBatchOpenExports"; text: "打开导出文件夹"; onClicked: backend.openCgBatchFolder() }
    }
    AppText { Layout.fillWidth: true; text: "打开怪物后会补齐其余编号的待测清单。暂停记录不影响模拟输出；新建一轮保留旧记录，完成并导出会停止本机模拟。参考目录的配置数量不等于独立 CG 数量。"; color: Theme.muted; font.pixelSize: 10; wrapMode: Text.Wrap; elide: Text.ElideNone }
}
