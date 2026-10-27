import QtQuick
import QtQuick.Layouts

Panel {
    id: card; objectName: "mockValidationPanel"
    readonly property var m: backend.mockValidation
    Layout.fillWidth: true; Layout.preferredHeight: body.implicitHeight+24
    ColumnLayout { id: body; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 12; spacing: 8
        RowLayout { Layout.fillWidth: true
            AppText { text: "本机模拟 APP · 使用当前预设"; color: Theme.gold; font.pixelSize: 16; Layout.fillWidth: true }
            AppButton { objectName: "mainMockStart"; visible: !card.m.active; text: "连接四通道并记录"; primary: true; onClicked: backend.startMockBoth() }
            AppButton { objectName: "mainMockResume"; visible: card.m.active; text: "继续模拟输出"; enabled: !!card.m.connected; onClicked: backend.resumeMockBoth() }
            AppButton { objectName: "mainMockStop"; visible: card.m.active; text: "停止并保存"; danger: true; onClicked: backend.stopMockBoth() }
        }
        AppText { Layout.fillWidth: true; text: card.m.status+(card.m.active ? " · Pulse A/B "+(card.m.pulsesA || 0)+" / "+(card.m.pulsesB || 0)+" 帧 · 负鼠 A/B "+(card.m.ovcPulsesA || 0)+" / "+(card.m.ovcPulsesB || 0)+" 帧" : ""); color: Theme.silver; font.pixelSize: 11; wrapMode: Text.Wrap; elide: Text.ElideNone }
        AppText { Layout.fillWidth: true; text: card.m.active ? "当前窗口的预设直接驱动发送层，仅连接本机模拟 APP。修改策略后输出暂停，按「继续模拟输出」恢复；关闭窗口时归零并保存。" : "曲线预览只计算波形；连接模拟 APP 才能核对真实发送、暂停与归零。无实体设备连接。"; color: Theme.muted; font.pixelSize: 10; wrapMode: Text.Wrap; elide: Text.ElideNone }
        AppText { visible: card.m.active && card.m.notes.length>0; Layout.fillWidth: true; text: card.m.notes.join(" · "); color: Theme.violet; font.pixelSize: 10; wrapMode: Text.Wrap; elide: Text.ElideNone }
        AppText { visible: !!card.m.error; Layout.fillWidth: true; text: card.m.error || ""; color: Theme.red; font.pixelSize: 11 }
        AppButton { objectName: "mainMockRecords"; visible: !!card.m.path; text: "打开本次记录"; onClicked: backend.openMockRecords() }
    }
}
