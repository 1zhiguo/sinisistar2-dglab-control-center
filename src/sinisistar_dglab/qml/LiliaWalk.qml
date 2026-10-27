import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Window
import "../assets/lilia/parts.js" as Lilia

Item {
    id: root
    objectName: "liliaWalker"
    property bool paused: false
    property bool walking: true
    property bool facingRight: true
    property real travel: 0
    property real gait: 0
    property real pixelScale: 1.55
    readonly property bool motionEnabled: visible && (!Window.window || Window.window.visibility!==Window.Minimized)
    readonly property real stride: walking && !paused ? Math.sin(gait) : 0
    readonly property real actorX: 12+travel*Math.max(0,width-Lilia.width*pixelScale-24)
    readonly property real floorY: height-13
    implicitWidth: 330; implicitHeight: 156
    Rectangle { x: 10; y: root.floorY+2; width: parent.width-20; height: 1; color: "#504131"; opacity: .65 }
    Rectangle { x: root.actorX+Lilia.width*root.pixelScale/2-13; y: root.floorY-2; width: 28; height: 5; radius: 14; color: "#b30a090b" }
    Item {
        id: actor; objectName: "liliaActor"
        x: root.actorX; y: root.floorY-height-(root.walking ? Math.abs(root.stride)*1.2 : 0)
        width: Lilia.width*root.pixelScale; height: Lilia.height*root.pixelScale
        transform: Scale { origin.x: actor.width/2; xScale: root.facingRight ? 1 : -1 }
        Repeater {
            model: Lilia.parts
            Image {
                id: piece
                required property var modelData
                readonly property string part: modelData.name
                readonly property bool leftSide: part.indexOf("Left")===0
                readonly property bool leg: part.indexOf("Leg")>=0 || part.indexOf("Foot")>=0
                readonly property bool arm: part.indexOf("Arm")>=0 || part.indexOf("Shoulder")>=0
                readonly property real hipX: leftSide ? 28 : 23
                readonly property real pivotX: leg ? hipX : arm ? (leftSide ? 28 : 19) : 22
                readonly property real pivotY: leg ? 43 : arm ? 24 : 25
                x: modelData.x*root.pixelScale; y: modelData.y*root.pixelScale
                width: modelData.width*root.pixelScale; height: modelData.height*root.pixelScale; z: modelData.z
                source: "../assets/lilia/"+modelData.file; smooth: false; mipmap: false
                transform: Rotation {
                    origin.x: (piece.pivotX-piece.modelData.x)*root.pixelScale
                    origin.y: (piece.pivotY-piece.modelData.y)*root.pixelScale
                    angle: piece.leg ? root.stride*(piece.leftSide ? 17 : -17) : piece.arm ? root.stride*(piece.leftSide ? -9 : 9) : piece.part==="Hair" ? root.stride*1.5 : piece.part==="Skirt1" ? root.stride*2 : 0
                }
            }
        }
        MouseArea { id: actorMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: root.paused=!root.paused }
        ToolTip.visible: actorMouse.containsMouse
        ToolTip.text: backend.translate((root.paused ? "莉莉娅 · 点击继续走动" : "莉莉娅 · 点击停留"),backend.language)
    }
    SequentialAnimation {
        id: patrol; objectName: "liliaPatrol"; running: root.motionEnabled; paused: root.paused; loops: Animation.Infinite
        PropertyAction { target: root; property: "facingRight"; value: true }
        PropertyAction { target: root; property: "walking"; value: true }
        NumberAnimation { target: root; property: "travel"; from: 0; to: 1; duration: 6200; easing.type: Easing.InOutSine }
        PropertyAction { target: root; property: "walking"; value: false }
        PauseAnimation { duration: 900 }
        PropertyAction { target: root; property: "facingRight"; value: false }
        PropertyAction { target: root; property: "walking"; value: true }
        NumberAnimation { target: root; property: "travel"; from: 1; to: 0; duration: 6200; easing.type: Easing.InOutSine }
        PropertyAction { target: root; property: "walking"; value: false }
        PauseAnimation { duration: 900 }
    }
    NumberAnimation on gait { running: root.motionEnabled && root.walking; paused: root.paused; from: 0; to: Math.PI*2; duration: 820; loops: Animation.Infinite }
}
