import QtQuick
Item {
    id: root
    property string text: ""
    property alias color: label.color
    property alias font: label.font
    property alias renderType: label.renderType
    property alias elide: label.elide
    property alias wrapMode: label.wrapMode
    property alias horizontalAlignment: label.horizontalAlignment
    property alias verticalAlignment: label.verticalAlignment
    property alias textFormat: label.textFormat
    property alias maximumLineCount: label.maximumLineCount
    property alias lineHeight: label.lineHeight
    property alias lineHeightMode: label.lineHeightMode
    property alias leftPadding: label.leftPadding
    property alias rightPadding: label.rightPadding
    property alias topPadding: label.topPadding
    property alias bottomPadding: label.bottomPadding
    readonly property alias contentWidth: label.contentWidth
    readonly property alias contentHeight: label.contentHeight
    readonly property alias truncated: label.truncated
    readonly property string localizedText: label.text
    implicitWidth: label.implicitWidth; implicitHeight: label.implicitHeight; baselineOffset: label.baselineOffset
    Text {
        id: label; anchors.fill: parent; text: backend.translate(root.text,backend.language)
        color: Theme.text; font.family: "Microsoft YaHei UI"; font.pixelSize: 13
        renderType: Text.NativeRendering; elide: Text.ElideRight
    }
}
