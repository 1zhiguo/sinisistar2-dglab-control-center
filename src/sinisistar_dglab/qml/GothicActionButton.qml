import QtQuick

AppButton {
    id: control
    property bool illuminated: false
    readonly property color ritualInk: danger ? Theme.crimson : accent
    implicitHeight: 44
    leftPadding: 14; rightPadding: 14; topPadding: 6; bottomPadding: 6
    contentItem: AppText {
        text: control.text; color: control.ritualInk; font.pixelSize: 12
        font.weight: control.danger || control.illuminated ? Font.DemiBold : Font.Normal
        horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
        opacity: control.enabled ? 1 : .45
    }
    background: GothicActionFrame { ink: control.ritualInk; danger: control.danger; active: control.illuminated; hovered: control.hovered; pressed: control.down; available: control.enabled }
}
