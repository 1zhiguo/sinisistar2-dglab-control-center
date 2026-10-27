import QtQuick
import QtQuick.Window

Window {
    id: detector
    objectName: "eventDetectorWindow"
    property var ownerWindow: null
    property bool placed: false
    title: backend.translate("SiNiSistar2 · 事件检测器",backend.language)
    color: Theme.bg
    visible: false
    flags: Qt.Window
    transientParent: null
    width: 1150; height: 820
    minimumWidth: 850; minimumHeight: 620
    function openDetector(){
        if(!placed){
            var area=backend.detectorScreen;
            width=Math.min(1240,Math.max(minimumWidth,Number(area.width || 1280)-64));
            height=Math.min(920,Math.max(minimumHeight,Number(area.height || 900)-64));
            x=Number(area.x || 0)+Math.max(0,(Number(area.width || 1280)-width)/2);
            y=Number(area.y || 0)+Math.max(0,(Number(area.height || 900)-height)/2);
            placed=true;
        }
        show();raise();requestActivate();
    }
    onClosing: close=>{close.accepted=false;detector.hide();}
    Connections { target: backend; function onDetectorRequested(){detector.openDetector();} }
    Connections { target: detector.ownerWindow; function onClosing(close){detector.hide();} }
    EventDetectorPage { anchors.fill: parent; anchors.margins: 24; detached: true; suspended: !detector.visible || detector.visibility===Window.Minimized }
}
