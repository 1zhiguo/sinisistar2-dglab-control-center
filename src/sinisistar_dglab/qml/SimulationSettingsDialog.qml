import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Dialog {
    id: dialog; objectName: "simulationSettingsDialog"
    parent: Overlay.overlay; anchors.centerIn: parent; modal: true
    width: Math.min(1040,parent.width-48); height: Math.min(720,parent.height-48,simulationContent.item ? simulationContent.item.desiredHeight : 440); padding: 22
    background: Rectangle { color: Theme.panel; radius: 6; border.color: Theme.gold }
    contentItem: Loader { id: simulationContent; active: dialog.visible; sourceComponent: Component { ColumnLayout {
        readonly property real desiredHeight: simulationSections.implicitHeight+simulationHeader.implicitHeight+60
        spacing: 16
        RowLayout { id: simulationHeader; Layout.fillWidth: true
            AppText { text: "模拟与测试"; color: Theme.gold; font.pixelSize: 21; Layout.fillWidth: true }
            AppButton { objectName: "closeSimulationSettings"; text: "×"; implicitWidth: 32; onClicked: dialog.close() }
        }
        ScrollView { id: view; Layout.fillWidth: true; Layout.fillHeight: true; clip: true; contentWidth: availableWidth
            ColumnLayout { id: simulationSections; width: view.availableWidth; spacing: 16
                MockValidationPanel { }
                SimulationPreviewPanel { }
                Panel { Layout.fillWidth: true; Layout.preferredHeight: flowBody.implicitHeight+24
                    ColumnLayout { id: flowBody; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 12; spacing: 10
                        DisclosureHeader { id: flowTools; Layout.fillWidth: true; title: backend.translate("演出规则测试",backend.language); summary: "选择已读取的流程，添加独立测试规则" }
                        RowLayout { visible: flowTools.expanded; Layout.fillWidth: true; spacing: 12
                            AppCombo { id: flowChoice; Layout.fillWidth: true; model: backend.observedFlows; textRole: "name" }
                            AppButton { objectName: "addObservedFlowRule"; text: "添加此身份的模拟规则"; enabled: flowChoice.currentIndex>=0 && flowChoice.currentIndex<backend.observedFlows.length; onClicked: backend.addFlowRule(flowChoice.currentIndex) }
                        }
                    }
                }
            }
        }
    } } }
}
