import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Dialog {
    id: dialog; objectName: "hotkeySettingsDialog"
    parent: Overlay.overlay; anchors.centerIn: parent; modal: true
    width: Math.min(650,parent ? parent.width-48 : 650); padding: 22
    readonly property var state: backend.hotkeySettings
    onClosed: backend.cancelHotkeyCapture()
    background: Rectangle { color: Theme.panel; border.color: Theme.gold; radius: 7 }
    contentItem: ColumnLayout { spacing: 15
        RowLayout { Layout.fillWidth: true
            AppText { text: "全局急停快捷键"; color: Theme.gold; font.pixelSize: 21; Layout.fillWidth: true }
            AppButton { objectName: "hotkeyClose"; text: "×"; implicitWidth: 32; onClicked: dialog.close() }
        }
        AppText { Layout.fillWidth: true; text: "当前快捷键："+dialog.state.sequence; color: Theme.silver; font.pixelSize: 15 }
        AppText { Layout.fillWidth: true; text: dialog.state.capturing ? "正在录入，请按单键或组合键…" : dialog.state.registered ? "全局快捷键已就绪，游戏在前台也有效。" : "全局快捷键未就绪，请查看错误或使用紧急归零按钮。"; color: dialog.state.registered ? Theme.green : Theme.violet; wrapMode: Text.Wrap; elide: Text.ElideNone }
        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 66; color: Theme.bg; border.color: dialog.state.capturing ? Theme.gold : Theme.border; radius: 5
            AppText { anchors.centerIn: parent; text: dialog.state.candidate.sequence || (dialog.state.capturing ? "等待按键…" : "点击录入后按键"); font.pixelSize: 20; color: Theme.gold }
        }
        AppText { Layout.fillWidth: true; text: "支持单键、功能键和 Ctrl / Alt / Shift 组合。录入时暂停旧急停键，保存成功后生效；注册冲突时保留旧设置。"; color: Theme.muted; font.pixelSize: 11; wrapMode: Text.Wrap; elide: Text.ElideNone }
        AppText { Layout.fillWidth: true; text: dialog.state.error || ""; visible: !!dialog.state.error; color: Theme.red; wrapMode: Text.Wrap; elide: Text.ElideNone }
        RowLayout { Layout.fillWidth: true
            AppButton { objectName: "hotkeyRecord"; text: dialog.state.capturing ? "取消录入" : "录入快捷键"; onClicked: dialog.state.capturing ? backend.cancelHotkeyCapture() : backend.beginHotkeyCapture() }
            AppButton { objectName: "hotkeyReset"; text: "恢复 Ctrl+F12"; onClicked: backend.resetEmergencyHotkey() }
            Item { Layout.fillWidth: true }
            AppButton { objectName: "hotkeySave"; text: "保存快捷键"; primary: true; enabled: !!dialog.state.candidate.sequence && !dialog.state.capturing; onClicked: backend.saveEmergencyHotkey() }
        }
        AppText { Layout.fillWidth: true; text: "急停会归零并锁定 Pulse 与负鼠。解除锁定后，输出仍保持暂停。"; color: Theme.muted; font.pixelSize: 11; wrapMode: Text.Wrap; elide: Text.ElideNone }
    }
}
