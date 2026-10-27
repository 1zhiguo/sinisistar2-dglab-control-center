import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

ColumnLayout {
    id: control
    property real low: 0
    property real high: 20
    property real maximum: 100
    property real step: 1
    property color accent: Theme.gold
    property string identifier: ""
    readonly property real displayedLow: slider.first.value
    readonly property real displayedHigh: slider.second.value
    objectName: "strengthRange_"+identifier
    signal edited(real low,real high)
    spacing: 3
    RowLayout { Layout.fillWidth: true
        AppText { text: "起始 "+Math.round(control.low); color: Theme.muted; font.pixelSize: 10 }
        Item { Layout.fillWidth: true }
        AppText { text: "峰值 "+Math.round(control.high); color: control.accent; font.pixelSize: 10 }
    }
    RangeSlider {
        id: slider
        objectName: "rangeSlider_"+control.identifier
        Layout.fillWidth: true; Layout.minimumWidth: 90
        implicitHeight: 26; from: 0; to: control.maximum; stepSize: control.step
        function syncValues(){
            if(first.pressed || second.pressed)return;
            var high=Math.max(0,Math.min(control.maximum,control.high));
            setValues(Math.max(0,Math.min(high,control.low)),high);
        }
        Component.onCompleted: Qt.callLater(syncValues)
        first.onPressedChanged: if(!first.pressed)Qt.callLater(syncValues)
        second.onPressedChanged: if(!second.pressed)Qt.callLater(syncValues)
        Connections { target: control
            function onLowChanged(){Qt.callLater(slider.syncValues);}
            function onHighChanged(){Qt.callLater(slider.syncValues);}
            function onMaximumChanged(){Qt.callLater(slider.syncValues);}
        }
        first.onMoved: control.edited(first.value,second.value)
        second.onMoved: control.edited(first.value,second.value)
        background: Rectangle { x: slider.leftPadding; y: slider.topPadding+(slider.availableHeight-height)/2; width: slider.availableWidth; height: 3; radius: 2; color: Theme.border
            Rectangle { x: slider.first.visualPosition*parent.width; width: Math.max(0,(slider.second.visualPosition-slider.first.visualPosition)*parent.width); height: parent.height; radius: 2; color: control.accent }
        }
        first.handle: Rectangle { objectName: "rangeStart_"+control.identifier; x: slider.leftPadding+slider.first.visualPosition*(slider.availableWidth-width); y: slider.topPadding+(slider.availableHeight-height)/2; width: 12; height: 17; radius: 3; color: slider.first.pressed ? Qt.lighter(control.accent,1.25) : control.accent; border.color: Theme.bg }
        second.handle: Rectangle { objectName: "rangePeak_"+control.identifier; x: slider.leftPadding+slider.second.visualPosition*(slider.availableWidth-width); y: slider.topPadding+(slider.availableHeight-height)/2; width: 12; height: 17; radius: 3; color: slider.second.pressed ? Qt.lighter(control.accent,1.25) : control.accent; border.color: Theme.bg }
    }
}
