import QtQuick
import QtQuick.Controls.Basic
Switch {
    id: control
    property color accent: Theme.gold
    implicitWidth: 42; implicitHeight: 24
    indicator: Rectangle { width: 38; height: 20; y: (control.height-height)/2; radius: 10; opacity: control.enabled ? 1 : .4; color: control.checked ? control.accent : Theme.border; border.color: Qt.rgba(control.accent.r,control.accent.g,control.accent.b,control.checked ? 1 : .35); Rectangle { width: 14; height: 14; radius: 7; y: 3; x: control.checked ? 21 : 3; color: control.checked ? Theme.bg : control.accent; Behavior on x { NumberAnimation { duration: 100 } } } }
}
