import QtQuick

Item {
    id: signal
    property var points: []
    property color accent: "#cfb47e"
    property bool active: false
    property int columns: 24
    property int rows: 5
    readonly property var levels: sampleLevels()
    readonly property real columnGap: 3
    readonly property real rowGap: 1.5
    readonly property real tileWidth: Math.max(1,(width-(columns-1)*columnGap)/columns)
    readonly property real tileHeight: Math.max(1,(height-(rows-1)*rowGap)/rows)
    function sampleLevels() {
        var result=[];
        var samples=points || [];
        for(var column=0;column<columns;column++) {
            var peak=0;
            var start=Math.floor(column*samples.length/columns);
            var end=Math.min(samples.length,Math.max(start+1,Math.floor((column+1)*samples.length/columns)));
            for(var i=start;i<end;i++)peak=Math.max(peak,Math.max(0,Math.min(1,Number(samples[i]) || 0)));
            result.push(Math.ceil(peak*rows));
        }
        return result;
    }
    Repeater {
        model: signal.columns
        Item {
            id: column
            required property int index
            readonly property int filled: signal.active ? Number(signal.levels[index] || 0) : 0
            x: index*(signal.tileWidth+signal.columnGap)
            width: signal.tileWidth; height: signal.height
            Repeater {
                model: signal.rows
                Rectangle {
                    required property int index
                    x: 0; y: column.height-(index+1)*signal.tileHeight-index*signal.rowGap
                    width: signal.tileWidth; height: signal.tileHeight; radius: .5
                    color: index<column.filled ? signal.accent : Qt.rgba(signal.accent.r,signal.accent.g,signal.accent.b,.13)
                }
            }
        }
    }
}
