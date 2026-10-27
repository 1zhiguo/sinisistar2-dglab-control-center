import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Dialog {
    id: dialog
    objectName: "hudSettingsDialog"
    parent: Overlay.overlay; anchors.centerIn: parent
    width: Math.min(650,parent.width-40); height: Math.min(690,parent.height-40); padding: 24
    modal: true; closePolicy: Popup.CloseOnEscape
    onOpened: backend.setHudAdjusting(true)
    onClosed: backend.setHudAdjusting(false)
    background: Rectangle { color: Theme.panel; border.color: Theme.gold; radius: 5 }
    component Option: RowLayout {
        property string field: ""
        property string label: ""
        Layout.fillWidth: true
        AppText { text: label; color: Theme.text; font.pixelSize: 12; Layout.fillWidth: true }
        AppSwitch { objectName: "hudOption_"+parent.field; accent: parent.field.indexOf("ovc_")===0 ? Theme.violet : Theme.gold; checked: !!backend.hudSettings[parent.field]; onToggled: backend.setHudSetting(parent.field,checked) }
    }
    component Position: RowLayout {
        property string field: "anchor"
        property string label: "显示位置"
        Layout.fillWidth: true
        AppText { text: parent.label; color: Theme.muted; Layout.preferredWidth: 118 }
        AppCombo { Layout.fillWidth: true; readonly property var keys: ["bottom_center","middle_right","bottom_right","top_right","bottom_left","middle_left","top_left","top_center","custom"]
            model: ["底部居中","右侧居中","右下","右上","左下","左侧居中","左上","顶部居中","自定义（拖动保存）"]
            currentIndex: keys.indexOf(backend.hudSettings[parent.field]); onActivated: backend.setHudSetting(parent.field,keys[currentIndex])
        }
    }
    contentItem: ColumnLayout { spacing: 14
        RowLayout { Layout.fillWidth: true
            AppText { text: "HUD · 联动显示"; font.pixelSize: 22; color: Theme.gold }
            Item { Layout.fillWidth: true }
            AppButton { text: "完成 / 锁定"; primary: true; onClicked: dialog.close() }
        }
        AppText { Layout.fillWidth: true; text: "郊狼 A/B 与负鼠 A/B 合在一条横向 HUD 中，默认位于游戏下方中央。拖动标题调整位置，锁定后不会挡住鼠标操作。"; color: Theme.muted; font.pixelSize: 11; wrapMode: Text.Wrap; elide: Text.ElideNone }
        ScrollView { id: settingsView; Layout.fillWidth: true; Layout.fillHeight: true; clip: true; contentWidth: availableWidth
            ColumnLayout { width: settingsView.availableWidth; spacing: 17
                Position { }
                Repeater { model: ["scale","opacity"]
                    RowLayout { required property string modelData; Layout.fillWidth: true
                        AppText { text: parent.modelData==="scale" ? "界面大小" : "背景不透明度"; color: Theme.muted; Layout.preferredWidth: 118 }
                        AppSlider { Layout.fillWidth: true; from: parent.modelData==="scale" ? 70 : 30; to: parent.modelData==="scale" ? 150 : 100; stepSize: 5; value: backend.hudSettings[parent.modelData]; onMoved: backend.setHudSetting(parent.modelData,value) }
                        AppText { text: backend.hudSettings[parent.modelData]+"%"; color: Theme.gold; Layout.preferredWidth: 48 }
                    }
                }
                Rectangle { Layout.fillWidth: true; height: 1; color: Theme.border }
                GridLayout { Layout.fillWidth: true; columns: 2; columnSpacing: 22; rowSpacing: 12
                    Option { field: "pulse_a"; label: "A 郊狼" }
                    Option { field: "pulse_b"; label: "B 郊狼" }
                    Option { field: "ovc_a"; label: "A 负鼠" }
                    Option { field: "ovc_b"; label: "B 负鼠" }
                    Option { field: "show_numbers"; label: "强度数字" }
                    Option { field: "show_waveforms"; label: "波形信号格与强度方块" }
                }
                Option { field: "hide_dialogue"; label: "对话演出时自动收起 HUD" }
                AppText { Layout.fillWidth: true; text: "死亡惩罚时继续显示联动状态。游戏资源和事件检测仍可在控制中心查看。"; color: Theme.violet; font.pixelSize: 11; wrapMode: Text.Wrap; elide: Text.ElideNone }
                Rectangle { Layout.fillWidth: true; height: 1; color: Theme.border }
                AppText { Layout.fillWidth: true; text: "Ctrl + F11：调整 / 锁定 HUD\n"+backend.hotkeySettings.sequence+"：紧急归零\n隐藏 HUD 不会停止联动；调整位置也不会改变输出策略。"; color: Theme.muted; font.pixelSize: 11; wrapMode: Text.Wrap; elide: Text.ElideNone; lineHeight: 1.6 }
                AppText { Layout.fillWidth: true; visible: !backend.hudHotkeyRegistered || !backend.emergencyHotkeyRegistered; text: "快捷键："+(backend.hudHotkeyRegistered ? "F11 已就绪" : "F11 使用窗口内快捷键")+" / "+backend.hotkeySettings.sequence+(backend.emergencyHotkeyRegistered ? " 已就绪" : " 不可用，请使用归零按钮"); color: Theme.red; font.pixelSize: 10; wrapMode: Text.Wrap; elide: Text.ElideNone }
            }
        }
        AppButton { text: "恢复默认显示与位置"; onClicked: backend.resetHudSettings() }
    }
}
