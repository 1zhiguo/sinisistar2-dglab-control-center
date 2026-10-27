import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

ScrollView {
    id: page
    signal openPolicies()
    clip: true; contentWidth: availableWidth
    readonly property var s: backend.state
    function number(v) { return v===null || v===undefined ? "—" : Math.round(v).toString(); }
    ColumnLayout { width: page.availableWidth; spacing: 18
        Panel { Layout.fillWidth: true; Layout.preferredHeight: start.implicitHeight+40
            ColumnLayout { id: start; anchors.fill: parent; anchors.margins: 20; spacing: 13
                RowLayout { Layout.fillWidth: true
                    AppText { text: "双路联动"; color: Theme.gold; font.pixelSize: 23 }
                    Item { Layout.fillWidth: true }
                    AppButton { text: "独立事件窗口"; onClicked: backend.openEventDetector() }
                    AppButton { text: "策略设置"; onClicked: page.openPolicies() }
                }
                RowLayout { Layout.fillWidth: true; spacing: 18
                    AppText { text: "PULSE"; color: Theme.gold; Layout.preferredWidth: 60 }
                    AppText { Layout.fillWidth: true; text: page.s.pulseStage+" · "+page.s.deviceStatus; color: Theme.muted; font.pixelSize: 12 }
                    AppButton { text: page.s.armed ? "暂停 Pulse" : "启动 Pulse"; primary: true; enabled: page.s.armed || page.s.feedbackKnown; onClicked: backend.toggleArm() }
                }
                RowLayout { Layout.fillWidth: true; spacing: 18
                    AppText { text: "负鼠"; color: Theme.violet; Layout.preferredWidth: 60 }
                    AppText { Layout.fillWidth: true; text: page.s.ovcStatus; color: Theme.muted; font.pixelSize: 12 }
                    AppButton { accent: Theme.violet; text: page.s.ovcArmed ? "暂停负鼠" : "启动负鼠"; primary: true; enabled: page.s.ovcArmed || page.s.ovcConnected; onClicked: backend.toggleOvcArm() }
                    AppButton { text: "紧急归零"; danger: true; onClicked: backend.emergencyStop() }
                }
                AppText { Layout.fillWidth: true; text: page.s.outputReason+"  /  "+page.s.ovcReason; color: Theme.muted; font.pixelSize: 11; wrapMode: Text.Wrap }
            }
        }
        GridLayout { Layout.fillWidth: true; columns: 2; columnSpacing: 18; rowSpacing: 18
            Repeater { model: [{route:"pulse",channel:"A"},{route:"pulse",channel:"B"},{route:"ovc",channel:"A"},{route:"ovc",channel:"B"}]
                Panel { id: card; required property var modelData
                    readonly property bool pulse: modelData.route==="pulse"
                    readonly property string channel: modelData.channel
                    readonly property var wire: (pulse ? page.s.outputChannels : page.s.ovcChannels)[channel] || ({active:false,strength:0})
                    readonly property bool enabledChannel: (pulse ? page.s.pulseChannels : page.s.ovcEnabledChannels)[channel]
                    readonly property color ink: pulse ? Theme.gold : Theme.violet
                    Layout.fillWidth: true; Layout.preferredHeight: 212
                    ColumnLayout { anchors.fill: parent; anchors.margins: 18; spacing: 10
                        RowLayout { Layout.fillWidth: true
                            AppText { text: (card.pulse ? "Pulse  " : "负鼠  ")+card.channel; color: card.ink; font.pixelSize: 21 }
                            Item { Layout.fillWidth: true }
                            AppButton { accent: card.pulse ? Theme.gold : Theme.violet; text: card.enabledChannel ? "暂停此通道" : "恢复此通道"; onClicked: card.pulse ? backend.setPulseChannelEnabled(card.channel,!card.enabledChannel) : backend.setOvcChannelEnabled(card.channel,!card.enabledChannel) }
                        }
                        RowLayout { Layout.fillWidth: true
                            AppText { text: "发送 "+page.number(card.wire.strength); font.pixelSize: 17; color: card.wire.active ? Theme.text : Theme.muted }
                            Item { Layout.fillWidth: true }
                            AppText { text: "APP "+page.number(card.pulse ? card.channel==="A" ? page.s.strengthA : page.s.strengthB : card.wire.reported); color: Theme.muted; font.pixelSize: 11 }
                        }
                        WavePlot { Layout.fillWidth: true; Layout.fillHeight: true; points: card.pulse ? card.channel==="A" ? page.s.traceA : page.s.traceB : card.wire.trace || []; lineColor: card.ink }
                        AppText { Layout.fillWidth: true; text: (card.pulse ? (backend.pulsePlan.selected["pulse"+card.channel] || []) : (backend.ovcPlan.selected["vibration"+card.channel] || [])).join(" + ") || (card.enabledChannel ? "等待联动" : "通道已暂停"); color: Theme.muted; font.pixelSize: 10 }
                    }
                }
            }
        }
        AppText { Layout.fillWidth: true; text: "负面异常默认 10 + 2 ×（种类数 − 1），正面 Buff 不参与。死亡惩罚使用自定义的 A/B 强度和所选波形，持续到复活；可在「快速设置」应用低、中、高预设。暂停、断线、失效心跳和急停均归零。负鼠强度 0–200、按 10 一档，与 Pulse 独立。"; color: Theme.muted; font.pixelSize: 11; wrapMode: Text.Wrap; elide: Text.ElideNone }
    }
}
