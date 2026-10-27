import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

ColumnLayout {
    id: page
    objectName: "eventDetectorPage"
    property bool leaving: false
    function prepareToLeave(){ leaving=true; }
    property bool detached: false
    property bool suspended: false
    property int mode: 0
    property bool frozen: false
    property var frozenEvents: []
    property var frozenCatalog: []
    property var frozenLogs: []
    readonly property var s: suspended ? ({gameStatus:"",reader:"",scene:"",sourceLabel:"",error:"",flow:({}),galleryPlayback:({controls:({})}),cgPlayback:({}),observerVersion:"",pluginStatus:""}) : backend.state
    readonly property bool currentPlayer: !suspended && !!s.pluginFresh && !!s.valid
    readonly property var currentAbnormals: currentPlayer ? s.abnormals || [] : []
    readonly property var eventRows: suspended ? [] : frozen ? frozenEvents : backend.monitorEvents
    readonly property var catalogRows: suspended ? [] : frozen ? frozenCatalog : backend.eventCatalog
    readonly property var logRows: suspended ? [] : frozen ? frozenLogs : backend.events
    readonly property var rows: mode===3 ? currentAbnormals : mode===0 ? eventRows : mode===1 ? catalogRows : logRows
    readonly property var filteredRows: {
        if(page.leaving || page.suspended)return [];
        var result=[],query=search.text.trim().toLowerCase();
        for(var i=0;i<rows.length;i++){
            var row=rows[i],source=String(mode===1 ? row.source : row.tag || "");
            if(mode===0 && ((historyMode.currentIndex===1 && row.history)||(historyMode.currentIndex===2 && !row.history)))continue;
            if(mode!==3){
                if(sourceMode.currentIndex===1 && source.indexOf("回调")<0)continue;
                if(sourceMode.currentIndex===2 && source.indexOf("状态边沿")<0)continue;
                if(sourceMode.currentIndex===3 && source.indexOf("组合判定")<0)continue;
                if(sourceMode.currentIndex===4 && String(row.key).indexOf("enemy_")!==0)continue;
                if(sourceMode.currentIndex===5 && !["flow_","same_hp_","struggle_","one_hp_","scripted_go","gallery_"].some(function(prefix){return String(row.key).indexOf(prefix)===0;}))continue;
            }
            var content=[row.label || "",row.name || row.title || "",row.key || "",row.text || row.detail || "",source,row.status || "",row.raw || ""].join(" ").toLowerCase();
            if(query && content.indexOf(query)<0)continue;
            result.push(row);
        }return result;
    }
    function freezeDisplay(){
        if(!frozen){frozenEvents=backend.monitorEvents.slice();frozenCatalog=backend.eventCatalog.slice();frozenLogs=backend.events.slice();}
        frozen=!frozen;
    }
    function number(value){return value===null || value===undefined ? "—" : Number(value).toFixed(0);}
    function levelText(row){return "Lv."+number(row.level)+(Number(row.max_level)>0 ? " / "+number(row.max_level) : "");}
    function timerText(row){return row.timer===null || row.timer===undefined || !isFinite(Number(row.timer)) ? "计时未提供" : Number(row.timer)<0 ? "无倒计时" : "本级计时 "+Number(row.timer).toFixed(1)+" s"+(s.paused ? " · 已暂停" : "");}
    function routeText(row){return row.positive ? "正面 Buff · 不参与联动" : !row.configured ? "尚未配置联动" : Number(row.level)<=0 ? "等级未生效" : (row.pulse_participates ? "Pulse "+row.pulse_channels : "Pulse 关闭")+"  ·  "+(row.ovc_participates ? "负鼠 "+row.ovc_channels : "负鼠关闭");}
    function titleFor(row){return mode===3 ? row.label : mode===1 ? row.name : row.title || (row.tag==="系统" ? "控制中心" : row.tag==="设备" ? "设备连接" : row.key || "记录");}
    function bodyFor(row){return mode===3 ? routeText(row)+(row.remove_on_scene_change ? "\n切换场景时移除" : "") : mode===1 ? row.detail : row.text || "";}
    component Pill: Rectangle {
        property string label: ""
        property color ink: Theme.gold
        implicitWidth: pillText.implicitWidth+16; implicitHeight: 24; radius: 3
        color: Qt.rgba(ink.r,ink.g,ink.b,.08); border.color: Qt.rgba(ink.r,ink.g,ink.b,.25)
        AppText { id: pillText; anchors.centerIn: parent; text: parent.label; color: parent.ink; font.pixelSize: 9 }
    }
    component Stat: ColumnLayout {
        property string caption: ""
        property string value: ""
        Layout.fillWidth: true; spacing: 5
        AppText { text: parent.caption; color: Theme.muted; font.pixelSize: 10 }
        AppText { Layout.fillWidth: true; text: parent.value; color: Theme.text; font.pixelSize: 14 }
    }
    spacing: 14
    RowLayout { Layout.fillWidth: true; spacing: 12
        ColumnLayout { Layout.fillWidth: true; spacing: 4
            AppText { text: "事件检测器"; font.pixelSize: 24; color: Theme.gold }
            AppText { text: "观察动作、异常与流程证据，方便对照游戏实测。"; color: Theme.muted; font.pixelSize: 11 }
        }
        AppButton { visible: !page.detached; text: "在副屏打开"; primary: true; onClicked: backend.openEventDetector() }
        AppButton { text: "记录目录"; onClicked: backend.openFolder() }
        AppButton { text: "导出记录"; onClicked: backend.exportEvents() }
    }
    Panel { Layout.fillWidth: true; Layout.preferredHeight: 112
        ColumnLayout { anchors.fill: parent; anchors.margins: 17; spacing: 12
            RowLayout { Layout.fillWidth: true; spacing: 10
                Rectangle { width: 6; height: 6; radius: 3; color: page.s.pluginFresh ? Theme.green : Theme.muted }
                AppText { text: page.s.gameStatus; color: page.s.pluginFresh ? Theme.green : Theme.muted; font.pixelSize: 11 }
                AppText { Layout.fillWidth: true; text: page.s.scene; color: Theme.muted; font.pixelSize: 10 }
                Pill { label: page.s.pluginFresh ? "观察插件 "+page.s.observerVersion+" · "+page.s.hookCount+" 个入口" : "等待游戏数据"; ink: page.s.pluginFresh ? Theme.gold : Theme.muted }
            }
            RowLayout { Layout.fillWidth: true; spacing: 25
                Stat { caption: "HP / MP"; value: page.number(page.s.hp)+" / "+page.number(page.s.mp) }
                Stat { caption: "当前异常 / Pulse / 负鼠"; value: page.currentPlayer ? page.currentAbnormals.length+" / "+page.s.pulseAbnormalCount+" / "+page.s.ovcAbnormalCount : "— / — / —" }
                Stat { caption: "抓取来源"; value: page.s.bound ? page.s.binder : "未被抓取" }
                Stat { caption: "演出状态"; value: (page.s.galleryPlayback || {}).inGallery ? page.s.galleryPlayback.label : page.s.nonDamageLabel || page.s.penaltyLabel || (page.s.flow.playing ? page.s.flow.name || page.s.flow.type || "播放中" : page.s.hp===0 && page.s.bound ? "怪物内部零血流程" : "无演出") }
            }
        }
    }
    Panel { visible: !!(page.s.galleryPlayback || {}).inGallery; Layout.fillWidth: true; Layout.preferredHeight: galleryBody.implicitHeight+24
        ColumnLayout { id: galleryBody; anchors.fill: parent; anchors.margins: 12; spacing: 6
            AppText { Layout.fillWidth: true; text: "图鉴回放 · "+(page.s.galleryPlayback || {}).label+((page.s.galleryPlayback || {}).name ? " · "+page.s.galleryPlayback.name : ""); color: Theme.violet; font.pixelSize: 12 }
            AppText { Layout.fillWidth: true; visible: !!(page.s.galleryPlayback || {}).dedicatedAvailable; text: page.s.galleryPlayback.selectionActive ? "选择：怪物 #"+page.s.galleryPlayback.enemyId+" · 片段 ["+page.s.galleryPlayback.selectedIndexRaw+"] · 已载入："+(page.s.galleryPlayback.takeName || "等待载入")+" · "+page.s.galleryPlayback.playType : "图鉴列表 / 预览页 · 未选择 CG 片段"; color: Theme.gold; font.pixelSize: 11; wrapMode: Text.Wrap; elide: Text.ElideNone }
            AppText { Layout.fillWidth: true; text: (page.s.galleryPlayback || {}).controlLabel || "等待图鉴字段"; color: Theme.muted; font.pixelSize: 11 }
            AppText { Layout.fillWidth: true; visible: !!(page.s.galleryPlayback || {}).dedicatedAvailable; text: "慢放 "+(page.s.galleryPlayback.controls.slow ? "开启" : "关闭")+" · DevMode "+(page.s.galleryPlayback.controls.dev_mode ? "开启" : "关闭")+" · 隐藏界面 "+(page.s.galleryPlayback.controls.ui_hidden ? "开启" : "关闭"); color: Theme.muted; font.pixelSize: 10 }
            AppText { Layout.fillWidth: true; text: "图鉴规则在「CG 反馈 → 图鉴独立反馈」中设置。选择按钮与实际载入片段分开记录，Space 停止与演出内部等待分开识别。"; color: Theme.muted; font.pixelSize: 10; wrapMode: Text.Wrap; elide: Text.ElideNone }
        }
    }
    Panel { Layout.fillWidth: true; Layout.preferredHeight: 52
        RowLayout { anchors.fill: parent; anchors.margins: 10; spacing: 10
            AppText { text: "当前异常"; color: Theme.gold; font.pixelSize: 11 }
            Flickable { Layout.fillWidth: true; Layout.fillHeight: true; clip: true; contentWidth: statusChips.width; contentHeight: height; flickableDirection: Flickable.HorizontalFlick; boundsBehavior: Flickable.StopAtBounds
                Row { id: statusChips; anchors.verticalCenter: parent.verticalCenter; spacing: 7
                    Repeater { model: page.currentAbnormals
                        Pill { required property var modelData; label: modelData.label+"  Lv."+page.number(modelData.level)+(modelData.positive ? " · 正面" : ""); ink: modelData.positive ? Theme.green : Theme.violet }
                    }
                }
                AppText { anchors.verticalCenter: parent.verticalCenter; visible: page.currentAbnormals.length===0; text: page.currentPlayer ? "当前未检测到异常状态" : "等待有效玩家状态"; color: Theme.muted; font.pixelSize: 11 }
            }
            AppButton { objectName: "openCurrentAbnormals"; text: "查看详情"; onClicked: page.mode=3 }
        }
    }
    RowLayout { objectName: "tutorialEventTabs"; Layout.fillWidth: true; spacing: 8
        AppButton { objectName: "currentAbnormalTab"; text: "当前异常  "+page.currentAbnormals.length; primary: page.mode===3; onClicked: page.mode=3 }
        AppButton { text: "事件流  "+page.eventRows.length; primary: page.mode===0; onClicked: page.mode=0 }
        AppButton { text: "可读事件  "+page.catalogRows.length; primary: page.mode===1; onClicked: page.mode=1 }
        AppButton { text: "运行记录"; primary: page.mode===2; onClicked: page.mode=2 }
        Item { Layout.fillWidth: true }
        AppText { text: page.filteredRows.length+" 条"; color: Theme.muted; font.pixelSize: 10 }
        AppButton { visible: page.mode!==3; text: page.frozen ? "继续刷新" : "冻结显示"; primary: page.frozen; onClicked: page.freezeDisplay() }
    }
    RowLayout { Layout.fillWidth: true; spacing: 10
        TextField { id: search; Layout.fillWidth: true; placeholderText: backend.translate((page.mode===3 ? "搜索当前状态名称、类型或 ID…" : "搜索事件、敌人、异常或流程…"),backend.language); selectByMouse: true; color: Theme.text; padding: 11; font.pixelSize: 12
            background: Rectangle { radius: 4; color: Theme.panel; border.color: search.activeFocus ? Theme.gold : Theme.border }
        }
        AppCombo { id: sourceMode; visible: page.mode!==3; implicitWidth: 166; model: ["全部来源","全部回调","状态边沿","组合判定","敌人伤害 / 击杀","演出 / 流程"] }
        AppCombo { id: historyMode; visible: page.mode===0; implicitWidth: 154; model: ["包含历史记录","只看新事件","只看历史"] }
    }
    RowLayout { visible: page.frozen && page.mode!==3; Layout.fillWidth: true
        Pill { label: "显示已冻结"; ink: Theme.violet }
        AppText { text: "采集继续，便于停下来查看和复制。"; color: Theme.muted; font.pixelSize: 10; Layout.fillWidth: true }
    }
    Panel { Layout.fillWidth: true; Layout.fillHeight: true; color: "#15120f"
        ListView { id: listing; anchors.fill: parent; anchors.margins: 12; clip: true; spacing: 8; model: page.filteredRows; boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { }
            delegate: Rectangle {
                required property var modelData
                width: listing.width-12; height: body.implicitHeight+26; radius: 4
                color: "#211c17"; border.color: modelData.history ? "#30291f" : "#44372a"
                ColumnLayout { id: body; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 13; spacing: 8
                    RowLayout { Layout.fillWidth: true; spacing: 9
                        AppText { Layout.fillWidth: true; text: page.titleFor(modelData); color: modelData.key==="enemy_kill" ? Theme.green : Theme.text; font.pixelSize: 13 }
                        Pill { label: page.mode===3 ? modelData.positive ? "正面 Buff" : "状态" : page.mode===1 ? modelData.source : modelData.tag || "观察"; ink: page.mode===3 && modelData.positive ? Theme.green : modelData.history ? Theme.muted : Theme.gold }
                        Pill { visible: page.mode===0 && !!modelData.history; label: "会话历史"; ink: Theme.muted }
                        AppText { visible: page.mode===0 || page.mode===2; text: modelData.time || ""; color: Theme.muted; font.pixelSize: 10 }
                    }
                    RowLayout { visible: page.mode===3; Layout.fillWidth: true; spacing: 10
                        Pill { label: page.levelText(modelData); ink: Theme.violet }
                        Pill { label: page.timerText(modelData); ink: Theme.muted }
                        Item { Layout.fillWidth: true }
                    }
                    TextEdit { Layout.fillWidth: true; Layout.preferredHeight: contentHeight; text: page.bodyFor(modelData); readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap; color: Theme.muted; selectionColor: "#725c39"; selectedTextColor: Theme.text; font.family: "Microsoft YaHei UI"; font.pixelSize: 12 }
                    RowLayout { Layout.fillWidth: true
                        AppText { Layout.fillWidth: true; text: page.mode===3 ? "类型 "+modelData.name+" · ID "+(modelData.raw===undefined || modelData.raw===null ? "—" : modelData.raw) : page.mode===1 ? modelData.status : modelData.key; color: page.mode===1 && modelData.count>0 ? Theme.green : Theme.muted; font.pixelSize: 10 }
                        AppText { visible: page.mode===0 && Number(modelData.rawCount)>1; text: "相邻重复已合并 · "+modelData.rawCount+" 条原始记录"; color: Theme.gold; font.pixelSize: 10 }
                    }
                }
            }
        }
        Column { anchors.centerIn: parent; width: Math.min(430,parent.width-50); spacing: 12; visible: page.filteredRows.length===0
            AppText { anchors.horizontalCenter: parent.horizontalCenter; text: search.text ? "没有匹配的记录" : page.mode===3 ? page.currentPlayer ? "当前没有异常状态" : "等待有效玩家状态" : page.mode===0 ? "等待新的游戏事件" : "暂无记录"; color: Theme.gold; font.pixelSize: 17 }
            AppText { width: parent.width; horizontalAlignment: Text.AlignHCenter; text: search.text ? "试试其他关键词或来源。" : page.mode===3 ? "进入存档后实时显示。正面 Buff 也会列出，并标记为不参与联动。" : "进入存档并操作游戏，事件会出现在这里。"; color: Theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap }
        }
    }
    RowLayout { Layout.fillWidth: true
        AppText { Layout.fillWidth: true; text: page.mode===3 ? "策略参与不等于正在发送；暂停、关闭输出或死亡惩罚优先时，实际输出以设备与游戏页为准。负数计时表示无倒计时；状态仍可能随流程或复活移除。" : page.mode===1 ? "“待触发”表示尚无本次实机证据；不以安装成功代替覆盖验证。" : "事件记录用于观察；历史记录不会触发输出。"; color: Theme.muted; font.pixelSize: 10; wrapMode: Text.Wrap; elide: Text.ElideNone }
        AppText { text: page.mode===3 ? "LIVE STATUS" : page.frozen ? "FROZEN" : "OBSERVING"; color: page.mode!==3 && page.frozen ? Theme.violet : Theme.gold; font.pixelSize: 9; font.letterSpacing: 1.5 }
    }
}
