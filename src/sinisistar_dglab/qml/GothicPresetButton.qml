import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Window

AppButton {
    id: control
    property string tier: "low"
    readonly property bool fierce: tier==="high"
    readonly property color ritualInk: fierce ? Theme.crimson : tier==="medium" ? "#d0af71" : Theme.silver
    readonly property bool alive: visible && (primary || hovered) && (!Window.window || Window.window.visibility!==Window.Minimized)
    property real glow: .45
    accent: ritualInk
    implicitHeight: 76
    hoverEnabled: true
    Accessible.name: text
    scale: down ? .985 : 1
    Behavior on scale { NumberAnimation { duration: 110 } }
    contentItem: Item {
        Row {
            anchors.centerIn: parent; spacing: 13
            Canvas {
                id: seal; width: 31; height: 39
                onPaint: {
                    var c=getContext("2d");c.reset();c.strokeStyle=control.ritualInk;c.lineWidth=1;
                    c.beginPath();c.moveTo(3,35);c.lineTo(3,18);c.quadraticCurveTo(3,9,15.5,2);c.quadraticCurveTo(28,9,28,18);c.lineTo(28,35);c.closePath();c.stroke();
                    c.globalAlpha=.35;c.beginPath();c.moveTo(7,33);c.lineTo(7,18);c.quadraticCurveTo(7,11,15.5,6);c.quadraticCurveTo(24,11,24,18);c.lineTo(24,33);c.stroke();c.globalAlpha=1;
                    if(control.tier==="low"){
                        c.fillStyle=control.ritualInk;c.beginPath();c.arc(15.5,17,3,0,Math.PI*2);c.fill();
                        c.beginPath();c.moveTo(15.5,22);c.lineTo(15.5,30);c.moveTo(11,26);c.lineTo(20,26);c.stroke();
                    } else if(control.tier==="medium"){
                        c.beginPath();c.moveTo(15.5,12);c.lineTo(21,21);c.lineTo(15.5,30);c.lineTo(10,21);c.closePath();c.stroke();
                        c.beginPath();c.moveTo(8,21);c.lineTo(23,21);c.moveTo(15.5,9);c.lineTo(15.5,33);c.stroke();
                    } else {
                        c.beginPath();c.moveTo(10,12);c.lineTo(8,20);c.lineTo(15.5,31);c.lineTo(23,20);c.lineTo(21,12);c.moveTo(15.5,10);c.lineTo(15.5,31);c.moveTo(10,21);c.lineTo(21,21);c.stroke();
                    }
                }
            }
            Column {
                anchors.verticalCenter: parent.verticalCenter; spacing: 4
                AppText { text: control.text; font.pixelSize: 15; font.weight: control.primary ? Font.DemiBold : Font.Normal; color: control.ritualInk }
                AppText { text: ({low:"CANDLELIGHT",medium:"GILDED ALTAR",high:"CRIMSON ABYSS"})[control.tier]; font.family: "Georgia"; font.letterSpacing: 1.5; font.pixelSize: 8; color: Qt.rgba(control.ritualInk.r,control.ritualInk.g,control.ritualInk.b,.6) }
            }
        }
    }
    background: Item {
        Rectangle { anchors.fill: parent; anchors.margins: -2; radius: 7; color: "transparent"; border.width: 3; border.color: control.ritualInk; opacity: control.alive ? control.glow*.19 : 0 }
        Rectangle { anchors.fill: parent; radius: 5
            gradient: Gradient {
                GradientStop { position: 0; color: control.fierce ? (control.primary ? "#39151c" : "#261217") : control.tier==="medium" ? (control.primary ? "#3a2e1d" : "#282219") : (control.primary ? "#302d38" : "#25232a") }
                GradientStop { position: 1; color: control.fierce ? "#100c0f" : "#141312" }
            }
            border.color: Qt.rgba(control.ritualInk.r,control.ritualInk.g,control.ritualInk.b,control.primary ? .85 : control.hovered ? .65 : .3)
            Behavior on border.color { ColorAnimation { duration: 150 } }
        }
        Rectangle { anchors.fill: parent; anchors.margins: 5; radius: 2; color: "transparent"; border.color: control.ritualInk; opacity: control.primary ? .22 : .09 }
        Rectangle { anchors.top: parent.top; anchors.topMargin: 1; anchors.horizontalCenter: parent.horizontalCenter; width: parent.width*.45; height: 1; color: control.ritualInk; opacity: control.alive ? control.glow : .25 }
        Repeater { model: 4
            Rectangle {
                required property int index
                x: index<2 ? 10 : parent.width-12; y: index%2===0 ? 10 : parent.height-12
                width: 3; height: 3; rotation: 45; color: control.ritualInk; opacity: control.primary ? .8 : .35
            }
        }
        Repeater { model: 4
            Rectangle {
                id: ember; required property int index
                width: index%2 ? 2 : 1; height: index%2 ? 2 : 4; rotation: 35
                x: 12+(index+1)*(parent.width-24)/5; y: parent.height-10
                color: control.fierce ? "#e57b70" : control.ritualInk; opacity: 0
                SequentialAnimation {
                    running: control.alive; loops: Animation.Infinite
                    PauseAnimation { duration: ember.index*260 }
                    ParallelAnimation {
                        NumberAnimation { target: ember; property: "y"; from: control.height-10; to: 10; duration: 1800 }
                        SequentialAnimation {
                            NumberAnimation { target: ember; property: "opacity"; from: 0; to: .65; duration: 450 }
                            NumberAnimation { target: ember; property: "opacity"; to: 0; duration: 1350 }
                        }
                    }
                }
            }
        }
    }
    SequentialAnimation on glow {
        running: control.alive; loops: Animation.Infinite
        NumberAnimation { from: .3; to: .85; duration: control.fierce ? 1100 : 1900; easing.type: Easing.InOutSine }
        NumberAnimation { from: .85; to: .3; duration: control.fierce ? 1100 : 1900; easing.type: Easing.InOutSine }
    }
}
