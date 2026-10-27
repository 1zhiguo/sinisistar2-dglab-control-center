import QtQuick

Panel {
    id: panel
    property bool ready: false
    property color readyColor: Theme.gold
    property real glow: ready ? 1 : 0
    border.color: ready ? Qt.rgba(readyColor.r,readyColor.g,readyColor.b,.85) : Theme.border
    Behavior on border.color { ColorAnimation { duration: 240 } }
    Behavior on glow { NumberAnimation { duration: 240; easing.type: Easing.OutCubic } }
    Item {
        anchors.fill: parent
        visible: panel.glow>0
        opacity: panel.glow
        Repeater {
            model: 5
            Rectangle {
                required property int index
                anchors.fill: parent
                anchors.margins: -2-index*1.5
                radius: panel.radius+2+index*1.5
                color: "transparent"
                border.width: 2
                border.color: Qt.rgba(panel.readyColor.r,panel.readyColor.g,panel.readyColor.b,.13-index*.022)
            }
        }
        Rectangle {
            anchors.fill: parent; anchors.margins: 5
            color: "transparent"; radius: 3
            border.color: Qt.rgba(panel.readyColor.r,panel.readyColor.g,panel.readyColor.b,.2)
        }
        Canvas {
            id: ornament
            anchors.fill: parent
            onWidthChanged: requestPaint()
            onHeightChanged: requestPaint()
            Connections { target: panel; function onReadyColorChanged(){ornament.requestPaint();} }
            onPaint: {
                var c=getContext("2d");c.reset();c.strokeStyle=panel.readyColor;c.fillStyle=panel.readyColor;c.lineWidth=1;
                for(var i=0;i<4;i++){
                    c.save();c.translate(i%2 ? width : 0,i>=2 ? height : 0);c.scale(i%2 ? -1 : 1,i>=2 ? -1 : 1);
                    c.beginPath();c.moveTo(10,34);c.lineTo(10,20);c.lineTo(20,10);c.lineTo(34,10);c.stroke();
                    c.beginPath();c.moveTo(10,5);c.lineTo(15,10);c.lineTo(10,15);c.lineTo(5,10);c.closePath();c.fill();
                    c.restore();
                }
                // A small pointed crest echoes the gilded corner tracery.
                var x=width/2;
                c.beginPath();c.moveTo(x-35,5);c.lineTo(x-10,5);c.moveTo(x+10,5);c.lineTo(x+35,5);c.stroke();
                c.beginPath();c.moveTo(x,1);c.lineTo(x+4,5);c.lineTo(x,9);c.lineTo(x-4,5);c.closePath();c.fill();
            }
        }
    }
}
