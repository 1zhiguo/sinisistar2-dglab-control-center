import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

RowLayout {
    id: root
    property alias model: combo.model
    property alias currentIndex: combo.currentIndex
    property string textRole: "name"
    property color accent: Theme.gold
    property real period: 0
    readonly property var selectedWave: model && currentIndex>=0 ? model[currentIndex] || ({}) : ({})
    signal activated(int index)
    spacing: 5
    function openPreview(wave){ preview.wave=wave;preview.period=root.period>0 && wave.key===root.selectedWave.key ? root.period : wave.native_period || 2;preview.playing=false;preview.elapsed=0;dialog.open(); }
    AppCombo {
        id: combo; objectName: root.objectName+"_combo"; accent: root.accent; Layout.fillWidth: true; textRole: root.textRole
        onActivated: index=>root.activated(index)
        delegate: ItemDelegate {
            id: entry; required property int index
            readonly property var wave: root.model[index] || ({})
            width: combo.width; height: 64
            contentItem: RowLayout { spacing: 8
                ColumnLayout { Layout.fillWidth: true; spacing: 2
                    AppText { Layout.fillWidth: true; text: entry.wave.name || "波形缺失"; font.pixelSize: 11 }
                    WavePlot { Layout.fillWidth: true; Layout.preferredHeight: 28; points: entry.wave.points || []; grid: false; lineColor: root.accent }
                }
                AppButton { objectName: "waveOptionPreview_"+entry.index; text: "▷"; implicitWidth: 30; implicitHeight: 30; accent: root.accent; onClicked: {Qt.callLater(root.openPreview,entry.wave);combo.popup.close();} }
            }
            background: Rectangle { color: entry.highlighted ? Theme.border : Theme.panel }
        }
    }
    AppButton { objectName: root.objectName+"_preview"; text: "▷"; implicitWidth: 32; implicitHeight: 36; accent: root.accent; enabled: !!root.selectedWave.key; onClicked: root.openPreview(root.selectedWave); ToolTip.visible: hovered; ToolTip.text: backend.translate(("查看形状与播放预览" ),backend.language)}
    Dialog {
        id: dialog; objectName: "wavePreviewDialog"; parent: Overlay.overlay; anchors.centerIn: parent
        width: Math.min(560,parent.width-40); padding: 22; modal: true
        onClosed: preview.playing=false
        background: Rectangle { color: Theme.panel; border.color: root.accent; radius: 5 }
        contentItem: ColumnLayout { spacing: 16
            RowLayout { Layout.fillWidth: true
                AppText { Layout.fillWidth: true; text: preview.wave.name || "波形预览"; color: root.accent; font.pixelSize: 20 }
                AppButton { objectName: "wavePreviewClose"; text: "×"; implicitWidth: 30; onClicked: dialog.close() }
            }
            WavePreview { id: preview; objectName: "wavePreviewPlayer"; Layout.fillWidth: true; accent: root.accent }
        }
    }
}
