import QtQuick
import QtQuick.Controls.Basic
Slider {
    id: control
    property color accent: Theme.gold
    from: 0; to: 100; stepSize: 1; implicitHeight: 24
    background: Rectangle { x: control.leftPadding; y: control.topPadding+(control.availableHeight-height)/2; width: control.availableWidth; height: 3; radius: 2; color: Theme.border; Rectangle { width: control.visualPosition*parent.width; height: parent.height; color: control.accent; radius: 2 } }
    handle: Rectangle { x: control.leftPadding+control.visualPosition*(control.availableWidth-width); y: control.topPadding+(control.availableHeight-height)/2; width: 12; height: 16; radius: 3; color: control.pressed ? Qt.lighter(control.accent,1.25) : control.accent; border.color: Theme.bg }
}
