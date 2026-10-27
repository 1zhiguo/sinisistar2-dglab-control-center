import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

ColumnLayout {
    id: editor
    property var rule: ({})
    property string group: "rules"
    property int ruleIndex: 0
    readonly property bool hold: group!=="rules" || rule.key==="grab_hold" || rule.key==="defeat_hold" || rule.key==="event_hold"
    readonly property bool excluded: !!rule.feedback_excluded
    function save(field,value) { backend.setSimulationRule(group,ruleIndex,field,value); }
    spacing: 13
    component ValueRow: RowLayout {
        id: field
        property string label: ""
        property color accent: Theme.gold
        property real amount: 0
        property real maximum: 100
        property real minimum: 0
        property real step: 1
        signal edited(real value)
        Layout.fillWidth: true; spacing: 10
        AppText { text: field.label; color: Theme.muted; font.pixelSize: 11; Layout.preferredWidth: 106 }
        AppSlider { accent: field.accent; Layout.fillWidth: true; from: field.minimum; to: field.maximum; stepSize: field.step; value: field.amount; onMoved: field.edited(value) }
        AppText { text: Number(field.amount).toFixed(field.step<1 ? 1 : 0); color: field.accent; font.pixelSize: 11; Layout.preferredWidth: 37 }
    }
    RowLayout { Layout.fillWidth: true
        AppText { text: editor.rule.name || "请选择规则"; font.pixelSize: 19; Layout.fillWidth: true; wrapMode: Text.Wrap; elide: Text.ElideNone }
        AppSwitch { enabled: !editor.excluded; checked: !!editor.rule.enabled; onToggled: editor.save("enabled",checked) }
    }
    AppText { Layout.fillWidth: true; text: editor.excluded ? "正面 Buff · 不参与联动" : editor.rule.key==="defeat_hold" ? "普通零血惩罚；CG 默认沿用此参数，可在「CG 反馈」独立设置波形、队列与渐强。固定时长同一流程只计一次" : editor.rule.key==="break" ? "单次反馈 · 仅完整 → 破损时触发，到时结束；持续破损或服装恢复不重复触发" : editor.hold ? "持续反馈 · 状态或流程结束时停止" : "单次反馈 · 由新的游戏事件触发"; font.pixelSize: 11; color: Theme.violet; wrapMode: Text.Wrap; elide: Text.ElideNone }
    AppText { visible: editor.group==="abnormals"; Layout.fillWidth: true; text: (editor.rule.category_label || "")+" · "+(editor.rule.translation_source==="internal" ? "内部类型译名，机制待实机对照" : "游戏中文名称"); color: Theme.muted; font.pixelSize: 10; wrapMode: Text.Wrap }
    RowLayout { visible: editor.rule.key==="defeat_hold"; Layout.fillWidth: true
        AppText { text: "结束方式"; color: Theme.muted; font.pixelSize: 11; Layout.preferredWidth: 106 }
        AppCombo { objectName: "ruleDeathMode"; Layout.fillWidth: true; model: ["持续到复活 / CG 结束","固定时长"]; currentIndex: editor.rule.death_mode==="timed" ? 1 : 0; onActivated: editor.save("death_mode",currentIndex===1 ? "timed" : "until_end") }
    }
    ValueRow { visible: editor.rule.key==="defeat_hold" && editor.rule.death_mode==="timed"; objectName: "ruleDeathSeconds"; label: "惩罚总时长 / 秒"; minimum: .1; maximum: 120; step: .1; amount: editor.rule.death_seconds || 3; onEdited: value=>editor.save("death_seconds",value) }
    ValueRow { visible: !editor.hold; objectName: "ruleFeedbackDuration"; label: "反馈时长 / 秒"; minimum: .1; maximum: 30; step: .1; amount: editor.rule.duration || .8; onEdited: value=>editor.save("duration",value) }
    RowLayout { Layout.fillWidth: true; spacing: 16
        Repeater { model: ["pulse","vibration"]
            delegate: Panel {
                id: routePanel
                objectName: "ruleRoute_"+route
                required property string modelData
                enabled: !editor.excluded && !(editor.group==="abnormals" && route==="vibration"); opacity: enabled ? 1 : .45
                readonly property string route: modelData
                readonly property color accent: route==="vibration" ? Theme.violet : Theme.gold
                readonly property var catalog: route==="pulse" ? backend.waves : backend.vibrationWaves
                function value(name,fallback) { var v=editor.rule[route+"_"+name]; return v===undefined ? fallback : v; }
                function update(name,value) { editor.save(route+"_"+name,value); }
                function waveIndex() { for(var i=0;i<catalog.length;i++)if(catalog[i].key===value("wave",""))return i;return 0; }
                function peak(channel){var v=value("strength_"+channel,null);return v===null ? value("strength",0) : v;}
                function start(channel){var v=channel ? value("start_strength_"+channel,null) : null;if(v===null)v=value("start_strength",null);var high=channel ? peak(channel) : value("strength",0);return v===null ? high : Math.min(high,v);}
                Layout.fillWidth: true; Layout.preferredHeight: routeColumn.implicitHeight+32
                ColumnLayout { id: routeColumn; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 16; spacing: 13
                    RowLayout { Layout.fillWidth: true
                        AppText { text: routePanel.route==="pulse" ? "PULSE" : "负鼠"; color: routePanel.route==="pulse" ? Theme.gold : Theme.violet; font.pixelSize: 14 }
                        Item { Layout.fillWidth: true }
                        AppSwitch { objectName: "ruleRouteToggle_"+routePanel.route; accent: routePanel.accent; checked: routePanel.value("enabled",false); onToggled: routePanel.update("enabled",checked) }
                    }
                    ValueRow { accent: routePanel.accent; visible: editor.group!=="abnormals" && editor.rule.key!=="defeat_hold" && editor.rule.key!=="grab_hold"; label: "反馈强度"; maximum: routePanel.route==="pulse" ? 100 : 200; step: routePanel.route==="pulse" ? 1 : 10; amount: routePanel.value("strength",0); onEdited: value=>routePanel.update("strength",value) }
                    AppText { visible: editor.group==="abnormals"; Layout.fillWidth: true; text: routePanel.route==="pulse" ? "每种固定 10 · 等级不加成" : "强度 0 · 异常不参与负鼠反馈"; color: routePanel.accent; font.pixelSize: 13; wrapMode: Text.Wrap }
                    StrengthRange { visible: editor.rule.key==="grab_hold"; Layout.fillWidth: true; maximum: routePanel.route==="pulse" ? 100 : 200; step: routePanel.route==="pulse" ? 1 : 10; low: routePanel.start(""); high: routePanel.value("strength",0); accent: routePanel.route==="pulse" ? Theme.gold : Theme.violet; identifier: "rule_grab_"+routePanel.route; onEdited: (low,high)=>backend.setRuleStrengthRange(editor.ruleIndex,routePanel.route,"",low,high) }
                    Repeater { model: editor.rule.key==="defeat_hold" ? ["a","b"] : []
                        ColumnLayout { required property string modelData; Layout.fillWidth: true; spacing: 4
                            AppText { text: "死亡惩罚 "+parent.modelData.toUpperCase(); color: Theme.muted; font.pixelSize: 10 }
                            StrengthRange { Layout.fillWidth: true; maximum: routePanel.route==="pulse" ? 100 : 200; step: routePanel.route==="pulse" ? 1 : 10; low: routePanel.start(parent.modelData); high: routePanel.peak(parent.modelData); accent: routePanel.route==="pulse" ? Theme.gold : Theme.violet; identifier: "rule_death_"+routePanel.route+"_"+parent.modelData; onEdited: (low,high)=>backend.setRuleStrengthRange(editor.ruleIndex,routePanel.route,parent.modelData,low,high) }
                        }
                    }
                    DisclosureHeader { id: routeDetails; accent: routePanel.accent; objectName: "ruleDetails_"+routePanel.route; Layout.fillWidth: true; title: backend.translate("通道与波形",backend.language); summary: routePanel.value("channel","A")+" · "+routePanel.catalog[routePanel.waveIndex()].name }
                    ColumnLayout { visible: routeDetails.expanded; Layout.fillWidth: true; spacing: 12
                        ValueRow { accent: routePanel.accent; visible: editor.rule.key==="grab_hold" || editor.rule.key==="defeat_hold"; label: "上升用时 / 秒"; minimum: .1; maximum: 120; step: .1; amount: routePanel.value("ramp_seconds",10); onEdited: value=>routePanel.update("ramp_seconds",value) }
                        AppText { text: "输出通道"; color: Theme.muted; font.pixelSize: 10 }
                        AppCombo { accent: routePanel.accent; Layout.fillWidth: true; readonly property var keys: ["A","B","AB"]; model: ["仅 A","仅 B","A + B"]; currentIndex: Math.max(0,keys.indexOf(routePanel.value("channel","A"))); onActivated: routePanel.update("channel",keys[currentIndex]) }
                        AppText { text: "波形"; color: Theme.muted; font.pixelSize: 10 }
                        WaveChoice { objectName: "ruleWave_"+routePanel.route; accent: routePanel.accent; period: routePanel.value("period",2); Layout.fillWidth: true; model: routePanel.catalog; textRole: "name"; currentIndex: routePanel.waveIndex(); onActivated: routePanel.update("wave",routePanel.catalog[currentIndex].key) }
                        ValueRow { accent: routePanel.accent; label: "波形周期 / 秒"; minimum: .1; maximum: 20; step: .1; amount: routePanel.value("period",2); onEdited: value=>routePanel.update("period",value) }
                        ValueRow { accent: routePanel.accent; visible: routePanel.route==="pulse" && !routePanel.catalog[routePanel.waveIndex()].frames; label: "频率 / Hz"; minimum: 1; amount: editor.rule.pulse_frequency || 30; onEdited: value=>editor.save("pulse_frequency",value) }
                        AppText { visible: routePanel.route==="pulse" && !!routePanel.catalog[routePanel.waveIndex()].frames; Layout.fillWidth: true; text: "预设保留帧内频率 · 原始周期 "+Number(routePanel.catalog[routePanel.waveIndex()].native_period || 0).toFixed(1)+" s"; color: Theme.muted; font.pixelSize: 10; wrapMode: Text.Wrap }
                        ValueRow { accent: routePanel.accent; visible: !editor.hold; label: "每损失 1 点加成"; maximum: 5; step: .1; amount: routePanel.value("gain",0); onEdited: value=>routePanel.update("gain",value) }
                        WavePlot { Layout.fillWidth: true; Layout.preferredHeight: 65; points: routePanel.catalog[routePanel.waveIndex()].points; lineColor: routePanel.route==="pulse" ? Theme.gold : Theme.violet }
                    }
                }
            }
        }
    }
    DisclosureHeader { id: timingHeader; objectName: "ruleTimingDisclosure"; Layout.fillWidth: true; title: backend.translate("时序与优先级",backend.language); summary: editor.rule.key==="defeat_hold" && editor.rule.death_mode==="timed" ? "定时 "+editor.rule.death_seconds+" 秒 · 优先级 "+editor.rule.priority : editor.hold ? "持续反馈 · 优先级 "+(editor.rule.priority || 0) : "持续 "+(editor.rule.duration || .8)+" 秒 · 冷却 "+(editor.rule.cooldown || 0)+" 秒" }
    ColumnLayout { visible: timingHeader.expanded; Layout.fillWidth: true; spacing: 12
        ValueRow { label: "优先级"; amount: editor.rule.priority || 0; onEdited: value=>editor.save("priority",value) }
        ValueRow { visible: !editor.hold; label: "冷却间隔 / 秒"; maximum: 10; step: .1; amount: editor.rule.cooldown || 0; onEdited: value=>editor.save("cooldown",value) }
        ColumnLayout { visible: editor.group==="flows"; Layout.fillWidth: true; spacing: 8
            AppText { text: "阶段标签（留空为整段演出）"; color: Theme.muted; font.pixelSize: 11 }
            TextField { Layout.fillWidth: true; text: editor.rule.label || ""; color: Theme.text; placeholderText: backend.translate(("精确匹配实际标签"),backend.language); onEditingFinished: editor.save("label",text); background: Rectangle { color: Theme.raised; border.color: Theme.border; radius: 4 } }
            ValueRow { label: "起始时间 / 秒"; maximum: 600; step: .1; amount: editor.rule.start || 0; onEdited: value=>editor.save("start",value) }
            ValueRow { label: "结束时间 / 秒"; maximum: 600; step: .1; amount: editor.rule.end || 0; onEdited: value=>editor.save("end",value) }
            AppText { text: "结束为 0 表示不限时。"; font.pixelSize: 10; color: Theme.muted }
        }
    }
}
