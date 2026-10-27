import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

AbstractButton {
    id: control
    property string title: ""
    property string summary: ""
    property bool expanded: false
    property color accent: Theme.gold
    implicitHeight: contentItem.implicitHeight+16
    implicitWidth: 300
    padding: 8
    onClicked: expanded=!expanded
    background: Rectangle { radius: 3; color: control.hovered ? "#282119" : "transparent" }
    contentItem: ColumnLayout { spacing: 6
        RowLayout { Layout.fillWidth: true; spacing: 10
            AppText { text: control.expanded ? "▾" : "▸"; color: control.accent; font.pixelSize: 13 }
            AppText { text: control.title; color: control.accent; font.pixelSize: 15; Layout.fillWidth: true }
            AppText { text: control.expanded ? "收起" : "展开"; color: Theme.muted; font.pixelSize: 10 }
        }
        AppText { visible: control.summary!==""; Layout.fillWidth: true; text: control.summary; color: Theme.muted; font.pixelSize: 10; wrapMode: Text.Wrap; elide: Text.ElideNone }
    }
}
