import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Dialog {
    id: dialog
    objectName: "gameAssistanceDialog"
    parent: Overlay.overlay; anchors.centerIn: parent
    width: Math.min(690,parent.width-40); height: Math.min(640,parent.height-40)
    padding: 24; modal: true; closePolicy: Popup.CloseOnEscape
    readonly property var state: backend.saveImportState
    onOpened: backend.refreshSaveImport()
    background: Rectangle { color: Theme.panel; border.color: Theme.border; radius: 6 }
    contentItem: ColumnLayout { spacing: 16
        AppText { text: "游戏辅助与存档"; color: Theme.silver; font.pixelSize: 23 }
        ScrollView { id: view; Layout.fillWidth: true; Layout.fillHeight: true; clip: true; contentWidth: availableWidth
            ColumnLayout { width: view.availableWidth; spacing: 18
                AppText { text: "游戏辅助"; color: Theme.gold; font.pixelSize: 17 }
                AppText { Layout.fillWidth: true; text: "按需调整 HP、MP、辅助攻击倍率，或移除当前异常。"; color: Theme.muted; wrapMode: Text.Wrap; elide: Text.ElideNone }
                AppButton { objectName: "openGameTrainer"; text: "打开游戏辅助"; Layout.fillWidth: true; onClicked: {dialog.close();backend.openTrainer();} }
                Rectangle { Layout.fillWidth: true; height: 1; color: Theme.border }
                AppText { text: "全 CG 存档"; color: Theme.gold; font.pixelSize: 17 }
                AppText { Layout.fillWidth: true; text: "可选导入 Alicelel 提供的 1.3.1 通关存档。自动放入空槽位，合并图鉴解锁标记，保留已有存档和个人设置。"; color: Theme.muted; wrapMode: Text.Wrap; elide: Text.ElideNone }
                AppText { Layout.fillWidth: true; text: "请先保存并退出游戏；导入前自动备份。不会随插件安装自动导入。"; color: Theme.silver; wrapMode: Text.Wrap; elide: Text.ElideNone }
                AppButton { objectName: "importFullCgSave"; text: dialog.state.busy ? "处理中…" : "一键导入全 CG 存档"; Layout.fillWidth: true; enabled: !!dialog.state.available && !dialog.state.busy && !backend.installState.busy; onClicked: confirmImport.open() }
                RowLayout { Layout.fillWidth: true
                    AppButton { objectName: "restoreImportedSave"; text: "撤销最近一次导入"; Layout.fillWidth: true; enabled: !!dialog.state.canRestore && !dialog.state.busy && !backend.installState.busy; onClicked: confirmRestore.open() }
                    AppButton { objectName: "openSaveBackups"; text: "查看备份"; enabled: !!dialog.state.canRestore || !!dialog.state.backup; onClicked: backend.openSaveBackupFolder() }
                }
                AppText { Layout.fillWidth: true; text: "若导入后继续游玩导致存档变化，自动撤销会停止，请通过备份手动恢复。"; color: Theme.muted; font.pixelSize: 11; wrapMode: Text.Wrap; elide: Text.ElideNone }
                AppText { objectName: "saveImportResult"; Layout.fillWidth: true; text: dialog.state.error || dialog.state.message || ""; color: dialog.state.error ? Theme.red : Theme.gold; wrapMode: Text.Wrap; elide: Text.ElideNone }
                AppText { Layout.fillWidth: true; text: dialog.state.directory || ""; color: Theme.muted; font.pixelSize: 10; wrapMode: Text.WrapAnywhere; elide: Text.ElideNone }
            }
        }
        AppButton { text: "完成"; Layout.alignment: Qt.AlignRight; onClicked: dialog.close() }
    }
    Dialog {
        id: confirmImport; objectName: "confirmSaveImport"; parent: Overlay.overlay; anchors.centerIn: parent
        width: Math.min(540,parent.width-40); padding: 22; modal: true
        background: Rectangle { color: Theme.panel; border.color: Theme.gold; radius: 6 }
        contentItem: ColumnLayout { spacing: 16
            AppText { text: "导入全 CG 存档？"; color: Theme.gold; font.pixelSize: 20 }
            AppText { Layout.fillWidth: true; text: "将备份当前存档，添加一个通关槽位并合并图鉴解锁标记。现有角色槽位不被覆盖。请确认游戏已退出。"; wrapMode: Text.Wrap; elide: Text.ElideNone }
            RowLayout { Layout.alignment: Qt.AlignRight
                AppButton { text: "取消"; onClicked: confirmImport.close() }
                AppButton { objectName: "confirmImportSaveButton"; text: "备份并导入"; primary: true; onClicked: {confirmImport.close();backend.importFullCgSave();} }
            }
        }
    }
    Dialog {
        id: confirmRestore; parent: Overlay.overlay; anchors.centerIn: parent
        width: Math.min(540,parent.width-40); padding: 22; modal: true
        background: Rectangle { color: Theme.panel; border.color: Theme.gold; radius: 6 }
        contentItem: ColumnLayout { spacing: 16
            AppText { text: "撤销最近一次导入？"; color: Theme.gold; font.pixelSize: 20 }
            AppText { Layout.fillWidth: true; text: "恢复导入前的系统存档，并移除这次新增的通关槽位。仅在导入后存档未再变化时执行。"; wrapMode: Text.Wrap; elide: Text.ElideNone }
            RowLayout { Layout.alignment: Qt.AlignRight
                AppButton { text: "取消"; onClicked: confirmRestore.close() }
                AppButton { objectName: "confirmRestoreSaveButton"; text: "恢复备份"; onClicked: {confirmRestore.close();backend.restoreImportedSave();} }
            }
        }
    }
}
