import QtQuick
import QtQuick.Window

Item {
    id: frame
    property color ink: Theme.gold
    property bool hovered: false
    property bool active: false
    property bool pressed: false
    property bool danger: false
    property bool available: true
    readonly property bool animated: visible && available && (hovered || active) && (!Window.window || Window.window.active && Window.window.visibility!==Window.Minimized)
    readonly property real glow: animated ? .55+.25*Math.sin(Theme.motionTime*Math.PI/1.4) : .4
    opacity: available ? 1 : .4
    Rectangle { anchors.fill: parent; anchors.margins: -2; radius: 7; color: "transparent"; border.width: 3; border.color: frame.ink; opacity: frame.animated ? frame.glow*.22 : 0 }
    Rectangle {
        anchors.fill: parent; radius: 5
        gradient: Gradient {
            GradientStop { position: 0; color: frame.danger ? (frame.pressed ? "#54202a" : "#35151d") : frame.pressed ? "#3d3120" : frame.active ? "#302719" : "#211d17" }
            GradientStop { position: 1; color: frame.danger ? "#170d11" : "#131210" }
        }
        border.color: Qt.rgba(frame.ink.r,frame.ink.g,frame.ink.b,frame.hovered ? .95 : frame.active ? .72 : frame.danger ? .6 : .42)
        Behavior on border.color { ColorAnimation { duration: 140 } }
    }
    Rectangle { anchors.fill: parent; anchors.margins: 4; radius: 2; color: "transparent"; border.color: frame.ink; opacity: frame.hovered ? .3 : .12 }
    Repeater { model: 4
        Item { required property int index; width: 8; height: 8
            x: index%2 ? frame.width-width-2 : 2; y: index<2 ? 2 : frame.height-height-2
            rotation: index===0 ? 0 : index===1 ? 90 : index===2 ? -90 : 180
            opacity: frame.hovered ? 1 : .55
            Rectangle { width: 6; height: 1; color: frame.ink }
            Rectangle { width: 1; height: 6; color: frame.ink }
        }
    }
    Rectangle { anchors.top: parent.top; anchors.topMargin: -1; anchors.horizontalCenter: parent.horizontalCenter; width: 3; height: 3; rotation: 45; color: frame.ink; opacity: frame.animated ? frame.glow : .45 }
    Rectangle { anchors.bottom: parent.bottom; anchors.bottomMargin: 1; anchors.horizontalCenter: parent.horizontalCenter; width: frame.width*.3; height: 1; color: frame.ink; opacity: frame.animated ? frame.glow*.65 : .12 }
}
