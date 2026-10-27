import QtQuick
Item {
    id: root
    property var points: []
    property color lineColor: Theme.gold
    property bool editable: false
    property bool grid: true
    signal pointEdited(int index, real value)
    onPointsChanged: chart.requestPaint()
    onLineColorChanged: chart.requestPaint()
    Canvas {
        id: chart; anchors.fill: parent
        onWidthChanged: requestPaint(); onHeightChanged: requestPaint()
        onPaint: {
            var ctx=getContext("2d"), w=width, h=height;
            ctx.reset(); var left=8, right=w-8, top=root.grid ? 10 : 3, bottom=h-(root.grid ? 12 : 3);
            if (root.grid) {
                ctx.strokeStyle="#332c23"; ctx.lineWidth=1;
                for (var i=0;i<5;i++) { var y=top+(bottom-top)*i/4; ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(right,y);ctx.stroke(); }
                for(var j=0;j<9;j++){var x=left+(right-left)*j/8;ctx.beginPath();ctx.moveTo(x,top);ctx.lineTo(x,bottom);ctx.stroke();}
            }
            if(root.points.length<2)return;
            var c=root.lineColor;var g=ctx.createLinearGradient(0,top,0,bottom);g.addColorStop(0,Qt.rgba(c.r,c.g,c.b,.2));g.addColorStop(1,Qt.rgba(c.r,c.g,c.b,.005));
            ctx.beginPath();ctx.moveTo(left,bottom);
            for(var k=0;k<root.points.length;k++)ctx.lineTo(left+(right-left)*k/(root.points.length-1),bottom-Number(root.points[k])*(bottom-top));
            ctx.lineTo(right,bottom);ctx.closePath();ctx.fillStyle=g;ctx.fill();
            ctx.beginPath();for(var m=0;m<root.points.length;m++){var px=left+(right-left)*m/(root.points.length-1),py=bottom-Number(root.points[m])*(bottom-top);if(m===0)ctx.moveTo(px,py);else ctx.lineTo(px,py);}
            ctx.strokeStyle=c;ctx.lineWidth=2;ctx.stroke();
            if(root.editable)for(var n=0;n<root.points.length;n++){ctx.beginPath();ctx.arc(left+(right-left)*n/(root.points.length-1),bottom-Number(root.points[n])*(bottom-top),3.5,0,Math.PI*2);ctx.fillStyle=c;ctx.fill();}
        }
    }
    MouseArea { anchors.fill: parent; enabled: root.editable; cursorShape: Qt.CrossCursor
        function edit(x,y){var i=Math.max(0,Math.min(15,Math.round((x-8)/(width-16)*15)));var v=Math.max(0,Math.min(1,(height-12-y)/(height-22)));root.pointEdited(i,v);}
        onPressed: function(mouse){edit(mouse.x,mouse.y)}
        onPositionChanged: function(mouse){if(pressed)edit(mouse.x,mouse.y)}
    }
}
