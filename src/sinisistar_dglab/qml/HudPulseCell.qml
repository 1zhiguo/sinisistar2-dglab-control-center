import QtQuick
import QtQuick.Layouts

Item {
    id: cell
    property string channel: "A"
    property string route: "pulse"
    property var options: backend.hudSettings
    readonly property var s: backend.state
    readonly property var sim: backend.simulation
    readonly property bool pulse: route==="pulse"
    readonly property bool preview: !!sim.running
    readonly property bool connected: pulse ? !!s.connected : !!s.ovcConnected
    readonly property string planKey: (pulse ? "pulse" : "vibration")+channel
    readonly property var wire: (pulse ? s.outputChannels : s.ovcChannels || {})[channel] || ({active:false,strength:0})
    readonly property color accent: channel==="A" ? "#cfb47e" : "#b8adc8"
    readonly property bool active: !s.emergency && (preview ? Number((sim.peaks || {})[planKey] || 0)>0 : !!wire.active)
    readonly property real amount: preview ? Number(sim[planKey] || 0) : Number(wire.strength || 0)
    readonly property real cap: preview ? Number(backend.simulationSettings[(pulse ? "pulse" : "vibration")+"_cap_"+channel.toLowerCase()] || 0) : pulse ? Math.min(Number(backend.simulationSettings["pulse_cap_"+channel.toLowerCase()] || 0),Number(backend.channels[channel==="A"?0:1].limit),Number(channel==="A" ? s.limitA || 0 : s.limitB || 0)) : Number(wire.limit || 0)
    readonly property var traces: preview ? ((sim.traces || {})[planKey] || []).map(function(v){return cell.cap>0 ? Math.min(1,Number(v)*100/cell.cap) : 0;}) : pulse ? channel==="A" ? s.traceA || [] : s.traceB || [] : wire.trace || []
    function number(value){return value===null || value===undefined ? "—" : Math.round(value).toString();}
    function waveName() {
        if(!preview && !connected)return "未连接";
        var catalog=pulse ? backend.waves : backend.vibrationWaves;
        if(wire.wave && !preview){for(var w=0;w<catalog.length;w++)if(catalog[w].key===wire.wave)return catalog[w].name;return wire.wave;}
        var plan=preview ? sim : pulse ? backend.pulsePlan : ({});
        var selected=(plan.selected || {})[planKey] || [];
        var active=plan.active || [];
        var key="";
        for(var i=0;i<active.length;i++)for(var j=0;j<selected.length;j++)if(selected[j].indexOf(active[i].name)>=0){key=active[i][pulse ? "pulse_wave" : "vibration_wave"];break;}
        for(var n=0;n<catalog.length;n++)if(catalog[n].key===key)return catalog[n].name;
        return cell.active ? "联动波形" : "等待联动";
    }
    implicitWidth: 176; implicitHeight: options.show_waveforms ? 66 : 44
    ColumnLayout { anchors.fill: parent; spacing: 4
        RowLayout { Layout.fillWidth: true; spacing: 8
            AppText { text: cell.channel; font.family: "Georgia"; font.pixelSize: 25; color: cell.accent; Layout.preferredWidth: 21 }
            ColumnLayout { Layout.fillWidth: true; spacing: 2
                AppText { text: cell.pulse ? "郊狼" : "负鼠"; color: cell.accent; font.pixelSize: 10 }
                AppText { Layout.fillWidth: true; text: cell.waveName(); color: cell.active ? "#dfd5c2" : "#978e7d"; font.pixelSize: 8 }
            }
            AppText { visible: cell.options.show_numbers; text: cell.number(cell.amount); font.family: "Georgia"; font.pixelSize: 26; color: cell.active ? "#eee6d7" : "#8b8273" }
        }
        HudSignalGrid { visible: cell.options.show_waveforms; Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 15; points: cell.traces; active: cell.active; accent: cell.accent }
        Row { visible: cell.options.show_waveforms; Layout.fillWidth: true; spacing: 3
            Repeater { model: 18
                Rectangle { required property int index; width: Math.max(2,(cell.width-51)/18); height: 3; radius: .5; color: cell.active && cell.cap>0 && index<Math.ceil(Math.max(0,Math.min(1,cell.amount/cell.cap))*18) ? cell.accent : Qt.rgba(cell.accent.r,cell.accent.g,cell.accent.b,.2) }
            }
        }
    }
}
