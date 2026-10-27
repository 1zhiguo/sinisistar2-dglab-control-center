import QtQuick

Item {
    id: pad
    objectName: "waveDrawPad"
    property var points: []
    property color ink: Theme.gold
    property bool drawing: false
    property bool showPreview: true
    property real phase: 0
    property int cursorIndex: -1
    readonly property real plotLeft: 38
    readonly property real plotRight: width-20
    readonly property real plotTop: 15
    readonly property real plotBottom: height-27
    signal strokeStarted()
    signal strokeEdited(real x0,real y0,real x1,real y1)
    signal strokeFinished()
    function unit(x,y) {
        return Qt.point(Math.max(0,Math.min(1,(x-plotLeft)/Math.max(1,plotRight-plotLeft))),
                        Math.max(0,Math.min(1,(plotBottom-y)/Math.max(1,plotBottom-plotTop))));
    }
    onPointsChanged: graph.requestPaint()
    onInkChanged: graph.requestPaint()
    onCursorIndexChanged: graph.requestPaint()
    Canvas {
        id: graph; anchors.fill: parent; antialiasing: true
        onWidthChanged: requestPaint(); onHeightChanged: requestPaint()
        onPaint: {
            var c=getContext("2d");c.reset();var l=pad.plotLeft,r=pad.plotRight,t=pad.plotTop,b=pad.plotBottom;
            c.lineWidth=1;c.strokeStyle="#393126";
            for(var y=0;y<5;y++){var py=t+(b-t)*y/4;c.beginPath();c.moveTo(l,py);c.lineTo(r,py);c.stroke();}
            for(var j=0;j<16;j++){var px=l+(r-l)*j/15;c.strokeStyle=j===pad.cursorIndex?"#786143":"#29251e";c.beginPath();c.moveTo(px,t);c.lineTo(px,b);c.stroke();}
            c.font="10px 'Microsoft YaHei UI'";c.fillStyle="#978e80";c.textAlign="right";
            for(var v=0;v<5;v++)c.fillText(String(100-v*25),l-9,t+(b-t)*v/4+4);
            c.textAlign="center";for(var k=0;k<16;k++)c.fillText(String(k+1),l+(r-l)*k/15,b+18);
            if(pad.points.length!==16)return;
            var tint=pad.ink,g=c.createLinearGradient(0,t,0,b);g.addColorStop(0,Qt.rgba(tint.r,tint.g,tint.b,.22));g.addColorStop(1,Qt.rgba(tint.r,tint.g,tint.b,.015));
            c.beginPath();c.moveTo(l,b);for(var a=0;a<16;a++)c.lineTo(l+(r-l)*a/15,b-Number(pad.points[a])*(b-t));c.lineTo(r,b);c.closePath();c.fillStyle=g;c.fill();
            c.beginPath();for(var n=0;n<16;n++){var xx=l+(r-l)*n/15,yy=b-Number(pad.points[n])*(b-t);if(n===0)c.moveTo(xx,yy);else c.lineTo(xx,yy);}
            c.strokeStyle=tint;c.lineWidth=2.4;c.lineJoin="round";c.stroke();
            for(var q=0;q<16;q++){var x=l+(r-l)*q/15,h=b-Number(pad.points[q])*(b-t);c.beginPath();c.arc(x,h,q===pad.cursorIndex?5.5:3.7,0,Math.PI*2);c.fillStyle=q===pad.cursorIndex?"#f0e8da":tint;c.fill();c.strokeStyle="#15120f";c.lineWidth=1.5;c.stroke();}
        }
    }
    Rectangle { visible: pad.showPreview && !pad.drawing; x: pad.plotLeft+(pad.plotRight-pad.plotLeft)*pad.phase; y: pad.plotTop; width: 1; height: pad.plotBottom-pad.plotTop; color: Qt.rgba(pad.ink.r,pad.ink.g,pad.ink.b,.35) }
    Timer { interval: 33; running: pad.visible && pad.showPreview && !pad.drawing; repeat: true; onTriggered: pad.phase=(pad.phase+.008)%1 }
    MouseArea {
        id: pointer; anchors.fill: parent; hoverEnabled: true; preventStealing: true; cursorShape: Qt.CrossCursor
        property point last: Qt.point(0,0)
        onPressed: mouse=>{var p=pad.unit(mouse.x,mouse.y);last=p;pad.drawing=true;pad.strokeStarted();pad.strokeEdited(p.x,p.y,p.x,p.y);pad.cursorIndex=Math.round(p.x*15);}
        onPositionChanged: mouse=>{var p=pad.unit(mouse.x,mouse.y);pad.cursorIndex=Math.round(p.x*15);if(pressed){pad.strokeEdited(last.x,last.y,p.x,p.y);last=p;}}
        onReleased: {pad.drawing=false;pad.strokeFinished();}
        onCanceled: {if(pad.drawing){pad.drawing=false;pad.strokeFinished();}}
        onExited: {if(!pressed)pad.cursorIndex=-1;}
        onWheel: wheel=>wheel.accepted=false
    }
}
