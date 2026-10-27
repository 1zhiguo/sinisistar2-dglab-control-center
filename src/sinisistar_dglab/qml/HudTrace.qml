import QtQuick
Item {
    id: trace
    property var points: []
    property color lineColor: Theme.gold
    property bool active: false
    onPointsChanged: graph.requestPaint()
    onLineColorChanged: graph.requestPaint()
    onActiveChanged: graph.requestPaint()
    Canvas { id: graph; anchors.fill: parent; onWidthChanged: requestPaint(); onHeightChanged: requestPaint()
        onPaint: {
            var c=getContext("2d");c.reset();var base=height-3;
            c.strokeStyle="#4652483a";c.lineWidth=.7;c.beginPath();c.moveTo(0,base);c.lineTo(width,base);
            for(var t=0;t<=12;t++){var x=t*width/12;c.moveTo(x,base);c.lineTo(x,base-(t%3===0?4:2));}c.stroke();
            if(!trace.points || trace.points.length<2)return;
            c.beginPath();for(var i=0;i<trace.points.length;i++){var px=1+i*(width-2)/(trace.points.length-1);var py=base-Math.max(0,Math.min(1,Number(trace.points[i]) || 0))*(height-6);if(i===0)c.moveTo(px,py);else c.lineTo(px,py);}
            c.strokeStyle="#b0090807";c.lineWidth=3.4;c.stroke();c.strokeStyle=trace.lineColor;c.lineWidth=trace.active?1.6:1;c.stroke();
        }
    }
}
