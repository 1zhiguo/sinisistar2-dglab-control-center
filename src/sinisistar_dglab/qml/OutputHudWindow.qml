import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Window

Window {
    id: surface
    readonly property var options: backend.hudSettings
    readonly property var s: backend.state
    readonly property bool preview: backend.simulation.running
    readonly property bool running: !!s.outputActive || !!((s.ovcChannels || {}).A || {}).active || !!((s.ovcChannels || {}).B || {}).active
    readonly property var cells: [{key:"pulse_a",channel:"A",route:"pulse"},{key:"pulse_b",channel:"B",route:"pulse"},{key:"ovc_a",channel:"A",route:"ovc"},{key:"ovc_b",channel:"B",route:"ovc"}].filter(function(c){return !!surface.options[c.key];})
    readonly property real naturalWidth: Math.max(226,cells.length*196+28)
    readonly property real naturalHeight: options.show_waveforms ? 116 : 94
    property real fitScale: 1
    readonly property real displayScale: options.scale/100*fitScale
    property real hudOriginX: 0
    property real hudOriginY: 0
    property real hudClientWidth: 1920
    property real hudClientHeight: 1080
    property bool hudDragging: false
    width: Math.round(naturalWidth*displayScale); height: Math.round(naturalHeight*displayScale)
    color: "transparent"; visible: false
    title: backend.translate("SiNiSistar2 · 联动 HUD",backend.language)
    flags: Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
           | (backend.hudAdjusting ? 0 : Qt.WindowDoesNotAcceptFocus | Qt.WindowTransparentForInput)
    function statusText() {
        if(preview)return "预览";
        if(s.emergency)return "已归零";
        if(running)return "联动中";
        if(s.connected || s.ovcConnected)return s.armed || s.ovcArmed ? "已就绪" : "已暂停";
        return "未连接";
    }
    Item {
        width: surface.naturalWidth; height: surface.naturalHeight
        scale: surface.displayScale; transformOrigin: Item.TopLeft
        Rectangle { anchors.fill: parent; radius: 3; color: Qt.rgba(.055,.049,.043,surface.options.opacity/100); border.color: surface.running ? "#a58d61" : "#716146"
            Canvas { anchors.fill: parent; onWidthChanged: requestPaint(); onHeightChanged: requestPaint()
                onPaint: {
                    var c=getContext("2d");c.reset();c.lineWidth=1;c.strokeStyle="#756247";
                    c.beginPath();c.moveTo(4,17);c.lineTo(4,4);c.lineTo(17,4);
                    c.moveTo(width-17,4);c.lineTo(width-4,4);c.lineTo(width-4,17);
                    c.moveTo(4,height-17);c.lineTo(4,height-4);c.lineTo(17,height-4);
                    c.moveTo(width-17,height-4);c.lineTo(width-4,height-4);c.lineTo(width-4,height-17);c.stroke();
                }
            }
        }
        ColumnLayout { anchors.fill: parent; anchors.margins: 12; spacing: 6
            Item { Layout.fillWidth: true; Layout.preferredHeight: 19
                RowLayout { anchors.fill: parent; spacing: 8
                    Item { width: 10; height: 18
                        Canvas { anchors.fill: parent; onPaint: {
                            var c=getContext("2d");c.reset();c.strokeStyle="#c8ad7b";c.lineWidth=1;c.beginPath();c.moveTo(5,1);c.lineTo(5,17);c.moveTo(1,7);c.lineTo(9,7);c.moveTo(5,3);c.lineTo(8,7);c.lineTo(5,11);c.lineTo(2,7);c.closePath();c.stroke();
                        }}
                    }
                    AppText { text: "SiNiSistar₂"; font.family: "Georgia"; font.pixelSize: 12; color: "#d5c5a5"; font.letterSpacing: 1 }
                    Rectangle { Layout.fillWidth: true; height: 1; color: "#594b38" }
                    Rectangle { width: 4; height: 4; radius: 2; color: surface.running ? "#b7bd8e" : surface.preview ? Theme.gold : "#766f60" }
                    AppText { text: surface.statusText(); color: surface.running ? "#dfd7c5" : Theme.muted; font.pixelSize: 9 }
                    AppButton { visible: backend.hudAdjusting; implicitWidth: 23; implicitHeight: 19; text: "⚙"; onClicked: backend.openHudSettings() }
                }
                MouseArea { anchors.fill: parent; anchors.rightMargin: backend.hudAdjusting ? 30 : 0
                    enabled: backend.hudAdjusting; cursorShape: Qt.SizeAllCursor
                    property point origin
                    property point pointerStart
                    onPressed: mouse=>{surface.hudDragging=true;origin=Qt.point(surface.x,surface.y);pointerStart=mapToGlobal(Qt.point(mouse.x,mouse.y));}
                    onPositionChanged: mouse=>{if(pressed){var p=mapToGlobal(Qt.point(mouse.x,mouse.y));surface.x=origin.x+p.x-pointerStart.x;surface.y=origin.y+p.y-pointerStart.y;}}
                    onReleased: {surface.hudDragging=false;backend.saveHudPosition(surface.x,surface.y,surface.hudOriginX,surface.hudOriginY,surface.hudClientWidth,surface.hudClientHeight,surface.width,surface.height);}
                    onCanceled: surface.hudDragging=false
                }
            }
            RowLayout { Layout.fillWidth: true; Layout.fillHeight: true; spacing: 12
                Repeater { model: surface.cells
                    Item { required property var modelData; required property int index; Layout.fillWidth: true; Layout.fillHeight: true
                        HudPulseCell { anchors.fill: parent; anchors.rightMargin: index<surface.cells.length-1 ? 12 : 0; channel: modelData.channel; route: modelData.route; options: surface.options }
                        Rectangle { visible: index<surface.cells.length-1; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; width: 1; height: parent.height-4; color: "#5b4c37" }
                    }
                }
            }
        }
    }
}
