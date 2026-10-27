import QtQuick
import QtQuick.Layouts

ColumnLayout {
    id: root
    readonly property var settings: backend.simulationSettings.channel_feedback
    spacing: 10
    Repeater { model: ["pulse","vibration"]
        RowLayout {
            id: row; required property string modelData
            readonly property string route: modelData
            readonly property color ink: route==="pulse" ? Theme.gold : Theme.violet
            Layout.fillWidth: true; spacing: 10
            AppText { text: row.route==="pulse" ? "Pulse" : "负鼠"; color: row.ink; font.pixelSize: 12; Layout.preferredWidth: 50 }
            Repeater { model: ["A","B"]
                RowLayout { required property string modelData; Layout.fillWidth: true; spacing: 6
                    AppText { text: parent.modelData; color: row.ink; font.pixelSize: 13 }
                    AppCombo { objectName: "feedbackScope_"+row.route+parent.modelData; Layout.fillWidth: true
                        readonly property string channel: parent.modelData
                        readonly property var keys: ["damage","cg","both"]
                        model: ["受伤反馈","CG 反馈","受伤 + CG 反馈"]
                        currentIndex: keys.indexOf(root.settings[row.route][channel])
                        onActivated: backend.setChannelFeedback(row.route,channel,keys[currentIndex])
                    }
                }
            }
        }
    }
    AppText { Layout.fillWidth: true; text: "受伤侧包含 HP 下降、抓取、破衣及已启用的异常；CG 侧包含战败 CG 与普通零血惩罚。此处筛选来源，具体规则仍须启用并分配到对应通道。"; color: Theme.muted; font.pixelSize: 10; wrapMode: Text.Wrap; elide: Text.ElideNone }
}
