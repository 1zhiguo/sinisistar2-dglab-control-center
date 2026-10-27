import QtQuick
import QtQuick.Controls.Basic
ComboBox {
    id: control
    property color accent: Theme.gold
    implicitWidth: 180; implicitHeight: 36
    font.family: "Microsoft YaHei UI"; font.pixelSize: 12
    contentItem: AppText { text: control.displayText; leftPadding: 12; rightPadding: 28; verticalAlignment: Text.AlignVCenter }
    background: Rectangle { color: Theme.raised; border.color: control.activeFocus ? control.accent : Theme.border; radius: 4 }
    indicator: AppText { text: "⌄"; color: control.accent; x: control.width-23; anchors.verticalCenter: parent.verticalCenter }
    delegate: ItemDelegate { required property int index; width: control.width; height: 36; contentItem: AppText { text: control.textAt(index) } background: Rectangle { color: highlighted ? Theme.border : Theme.panel } }
    popup: Popup { y: control.height+4; width: control.width; padding: 4; implicitHeight: Math.min(260,contentItem.implicitHeight+8); background: Rectangle { color: Theme.panel; border.color: Theme.border; radius: 5 } contentItem: ListView { clip: true; implicitHeight: contentHeight; model: control.popup.visible ? control.delegateModel : null; currentIndex: control.highlightedIndex; ScrollIndicator.vertical: ScrollIndicator {} } }
}
