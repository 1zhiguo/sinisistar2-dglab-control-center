import QtQuick
import QtQuick.Controls.Basic
TextField {
    id: field
    property real amount: 0
    property real minimum: 0
    property real maximum: 1800
    property int decimals: 1
    property color accent: Theme.gold
    signal edited(real amount)
    implicitWidth: 76; implicitHeight: 32
    text: Number(amount).toFixed(decimals)
    color: accent; font.pixelSize: 12; horizontalAlignment: Text.AlignHCenter; selectByMouse: true
    validator: DoubleValidator { bottom: field.minimum; top: field.maximum; decimals: field.decimals; notation: DoubleValidator.StandardNotation; locale: "en_US" }
    onEditingFinished: { var n=Number(text);if(isFinite(n))edited(Math.max(minimum,Math.min(maximum,n)));else text=Number(amount).toFixed(decimals); }
    background: Rectangle { color: Theme.raised; border.color: field.activeFocus ? field.accent : Theme.border; radius: 4 }
}
