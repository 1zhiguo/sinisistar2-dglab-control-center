import QtQuick
import QtQuick.Layouts

ColumnLayout {
    id: root
    property var wave: ({})
    property real period: wave.native_period || 2
    property color accent: Theme.gold
    property bool playing: false
    property real elapsed: 0
    property double started: 0
    readonly property real phase: (elapsed / Math.max(.1,period)) % 1
    readonly property var samples: {
        var f=wave.frames || [],p=[];
        if(f.length){for(var i=0;i<f.length;i++)for(var j=0;j<4;j++)p.push(parseInt(f[i].slice(8+j*2,10+j*2),16)/100);return p;}
        return wave.points || [];
    }
    readonly property real amplitude: {
        if(!samples.length)return 0;
        var x=phase*samples.length,i=Math.floor(x)%samples.length;
        return wave.frames ? samples[i] : samples[i]*(1-(x-i))+samples[(i+1)%samples.length]*(x-i);
    }
    onWaveChanged: { elapsed=0;started=Date.now(); }
    onPlayingChanged: if(playing)started=Date.now()-elapsed*1000
    onVisibleChanged: if(!visible)playing=false
    spacing: 10
    Item { Layout.fillWidth: true; Layout.preferredHeight: 140
        WavePlot { anchors.fill: parent; points: root.samples; lineColor: root.accent }
        Rectangle { x: 8+(parent.width-16)*root.phase; y: 10; width: 1; height: parent.height-22; color: root.accent }
    }
    RowLayout { Layout.fillWidth: true
        AppButton { objectName: "wavePreviewPlay"; text: root.playing ? "Ⅱ 暂停" : "▷ 播放预览"; accent: root.accent; onClicked: root.playing=!root.playing }
        AppButton { text: "重播"; onClicked: {root.elapsed=0;root.started=Date.now();root.playing=true;} }
        AppText { Layout.fillWidth: true; horizontalAlignment: Text.AlignRight; text: Math.round(root.amplitude*100)+"% · 周期 "+Number(root.period).toFixed(1)+" 秒"; color: root.accent; font.pixelSize: 11 }
    }
    Rectangle { Layout.fillWidth: true; height: 6; color: Theme.border; radius: 3
        Rectangle { width: parent.width*root.amplitude; height: parent.height; color: root.accent; radius: 3 }
    }
    AppText { Layout.fillWidth: true; text: "仅动画预览，不向设备发送。图形显示幅度，官方帧内频率保持原值。"; font.pixelSize: 10; color: Theme.muted; wrapMode: Text.Wrap; elide: Text.ElideNone }
    Timer { interval: 33; repeat: true; running: root.playing && root.visible; onTriggered: root.elapsed=(Date.now()-root.started)/1000 }
}
