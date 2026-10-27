import QtQuick
import QtQuick.Controls.Basic
Button {
    id: control
    property bool primary: false
    property bool danger: false
    property bool tinted: false
    property color accent: Theme.gold
    implicitWidth: Math.max(100, implicitContentWidth+32); implicitHeight: 38
    hoverEnabled: true
    contentItem: AppText { text: control.text; color: control.primary ? Theme.bg : control.danger ? Theme.red : control.tinted ? control.accent : Theme.text; font.pixelSize: 12; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
    background: Rectangle { radius: 5; color: control.primary ? (control.down ? Qt.darker(control.accent,1.2) : control.hovered ? Qt.lighter(control.accent,1.15) : control.accent) : control.tinted ? Qt.rgba(control.accent.r,control.accent.g,control.accent.b,control.hovered ? .12 : .035) : control.hovered ? Theme.raised : "transparent"; border.color: control.danger ? "#734842" : control.primary ? control.accent : control.tinted ? Qt.rgba(control.accent.r,control.accent.g,control.accent.b,.35) : Theme.border; opacity: control.enabled ? 1 : .4 }
}
