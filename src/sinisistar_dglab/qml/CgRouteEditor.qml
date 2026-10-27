import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Panel {
    id: card
    property string scope: "cg"
    readonly property string scopePrefix: scope==="gallery" ? "gallery/" : ""
    property string route: "pulse"
    property string channel: "A"
    readonly property string selector: scopePrefix+route+":"+channel
    readonly property color ink: route==="pulse" ? Theme.gold : Theme.violet
    readonly property var config: scope==="gallery" ? backend.gallerySettings : backend.cgSettings
    readonly property var rule: config.rule
    readonly property var options: config.routes[route][channel]
    readonly property real strengthLimit: Math.min(route==="pulse" ? 100 : 200, Number(backend.simulationSettings[route+"_cap_"+channel.toLowerCase()]))
    function rampSeconds(seconds){backend.setCgOption(selector,"ramp_seconds",Math.max(.1,Math.min(1800,Math.round(seconds*10)/10)));}
    readonly property var catalog: route==="pulse" ? backend.waves : backend.vibrationWaves
    objectName: "cgRoute_"+route
    function value(field){return rule[route+"_"+field];}
    function save(field,v){backend.setCgRule(scopePrefix+route+"_"+field,v);}
    function waveIndex(key){return catalog.findIndex(function(w){return w.key===key;});}
    function wave(key){return catalog[waveIndex(key)] || ({name:"波形缺失",points:[]});}
    function peak(c){var v=value("strength_"+c);if(v===null || v===undefined)v=value("strength");return isFinite(Number(v)) ? Math.max(0,Number(v)) : 0;}
    function start(c){var v=value("start_strength_"+c);if(v===null || v===undefined)v=value("start_strength");return v===null || v===undefined || !isFinite(Number(v)) ? peak(c) : Math.min(Math.max(0,Number(v)),peak(c));}
    Layout.fillWidth: true; Layout.preferredHeight: body.implicitHeight+32
    ColumnLayout {
        id: body; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 16; spacing: 12
        RowLayout { Layout.fillWidth: true
            AppText { text: card.route==="pulse" ? "PULSE · 郊狼" : "负鼠 · 振动"; color: card.ink; font.pixelSize: 19; Layout.fillWidth: true }
            AppSwitch { objectName: "cgEnabled_"+card.route; accent: card.ink; checked: card.value("enabled"); onToggled: card.save("enabled",checked) }
        }
        RowLayout { Layout.fillWidth: true
            AppText { text: "输出通道"; color: Theme.muted; font.pixelSize: 11 }
            AppCombo { objectName: "cgChannels_"+card.route; Layout.fillWidth: true; model: ["仅 A","仅 B","A + B"]; currentIndex: ["A","B","AB"].indexOf(card.value("channel")); onActivated: card.save("channel",["A","B","AB"][currentIndex]) }
        }
        RowLayout { Layout.fillWidth: true; spacing: 8
            Repeater { model: ["A","B"]
                AppButton { required property string modelData; objectName: "cgChannel"+modelData+"_"+card.route; Layout.fillWidth: true; text: "通道 "+modelData; accent: card.ink; primary: card.channel===modelData; onClicked: card.channel=modelData }
            }
        }
        AppText { Layout.fillWidth: true; text: "正在编辑 "+card.channel+" 通道 · "+(card.value("channel").indexOf(card.channel)>=0 ? "已参与输出" : "未参与输出，可在上方选择通道"); color: card.ink; font.pixelSize: 11 }
        RowLayout { Layout.fillWidth: true
            AppText { text: "本通道反馈范围"; color: Theme.muted; font.pixelSize: 11 }
            AppCombo { objectName: "cgFeedbackMode_"+card.route; accent: card.ink; Layout.fillWidth: true; model: ["受伤反馈","CG 反馈","受伤+CG 反馈"]; currentIndex: ["damage","cg","both"].indexOf(backend.simulationSettings.channel_feedback[card.route][card.channel]); onActivated: backend.setChannelFeedback(card.route,card.channel,["damage","cg","both"][currentIndex]) }
        }
        AppText { objectName: "cgChannelFilterHint_"+card.route; visible: backend.simulationSettings.channel_feedback[card.route][card.channel]==="damage"; Layout.fillWidth: true; text: "当前通道仅受伤，不参与游戏 CG 和图鉴反馈。请在上方改为 CG 或受伤+CG 反馈。"; color: card.ink; font.pixelSize: 11; wrapMode: Text.Wrap; elide: Text.ElideNone }
        StrengthRange { Layout.fillWidth: true; identifier: "cg_"+card.route+"_"+card.channel.toLowerCase(); accent: card.ink; maximum: card.strengthLimit; step: card.route==="pulse" ? 1 : 10; low: card.start(card.channel.toLowerCase()); high: card.peak(card.channel.toLowerCase()); onEdited: (low,high)=>backend.setCgStrengthRange(card.scopePrefix+card.route,card.channel.toLowerCase(),low,high) }
        AppText { Layout.fillWidth: true; text: "强度范围 0–"+card.strengthLimit+" · "+(backend.quickPolicy.active ? ({low:"低",medium:"中",high:"高"})[backend.quickPolicy.active]+"档预设" : "自定义")+" · 起始和峰值可分别调整"; color: Theme.muted; font.pixelSize: 10; wrapMode: Text.Wrap; elide: Text.ElideNone }
        AppText { visible: card.peak(card.channel.toLowerCase())>card.strengthLimit; Layout.fillWidth: true; text: "当前峰值超过本通道上限，实际输出按上限限制。"; color: Theme.violet; font.pixelSize: 10 }
        RowLayout { Layout.fillWidth: true
            AppText { text: "渐强用时 · 越短越快"; color: Theme.muted; font.pixelSize: 11; Layout.fillWidth: true }
            CgNumber { objectName: "cgRampSeconds_"+card.route; amount: card.options.ramp_seconds; minimum: .1; maximum: 1800; accent: card.ink; onEdited: amount=>card.rampSeconds(amount) }
            AppText { text: "秒"; color: Theme.muted; font.pixelSize: 11 }
        }
        RowLayout { Layout.fillWidth: true
            AppText { text: "快"; color: Theme.muted; font.pixelSize: 10 }
            AppSlider { objectName: "cgRampSpeed_"+card.route; Layout.fillWidth: true; accent: card.ink; from: 0; to: 1; stepSize: .005; value: Math.log(card.options.ramp_seconds/.1)/Math.log(18000); onMoved: card.rampSeconds(.1*Math.pow(18000,value)) }
            AppText { text: "慢"; color: Theme.muted; font.pixelSize: 10 }
            AppButton { objectName: "cgRampFaster_"+card.route; text: "加快 ×2"; accent: card.ink; onClicked: card.rampSeconds(card.options.ramp_seconds/2) }
            AppButton { objectName: "cgRampSlower_"+card.route; text: "放慢 ×2"; accent: card.ink; onClicked: card.rampSeconds(card.options.ramp_seconds*2) }
        }
        AppCombo { objectName: "cgRampScope_"+card.route; visible: card.options.mode!=="fixed"; Layout.fillWidth: true; model: ["整段 CG 持续渐强","每轮队列重新渐强","每条波形重新渐强"]; currentIndex: ["episode","cycle","wave"].indexOf(card.options.ramp_scope); onActivated: backend.setCgOption(card.selector,"ramp_scope",["episode","cycle","wave"][currentIndex]) }
        AppText { Layout.fillWidth: true; text: "从 "+Math.round(card.start(card.channel.toLowerCase()))+" 到 "+Math.round(card.peak(card.channel.toLowerCase()))+"，用时 "+Number(card.options.ramp_seconds).toFixed(1)+" 秒"+(card.options.ramp_mode==="linear" ? " · 每秒约 +"+Number((card.peak(card.channel.toLowerCase())-card.start(card.channel.toLowerCase()))/card.options.ramp_seconds).toFixed(2) : " · 曲线可在下方调整"); color: card.ink; font.pixelSize: 10; wrapMode: Text.Wrap; elide: Text.ElideNone }
        AppCombo { objectName: "cgMode_"+card.route; Layout.fillWidth: true; model: ["单波形","队列 · 顺序循环","队列 · 随机循环（每轮不重复）"]; currentIndex: ["fixed","sequence","shuffle"].indexOf(card.options.mode); onActivated: backend.setCgOption(card.selector,"mode",["fixed","sequence","shuffle"][currentIndex]) }
        ColumnLayout { visible: card.options.mode==="fixed"; Layout.fillWidth: true; spacing: 8
            WaveChoice { accent: card.ink; period: card.options.period; objectName: "cgWave_"+card.route; Layout.fillWidth: true; model: card.catalog; textRole: "name"; currentIndex: card.waveIndex(card.options.wave); onActivated: backend.setCgOption(card.selector,"wave",card.catalog[currentIndex].key) }
            RowLayout { Layout.fillWidth: true
                AppText { text: "波形周期"; color: Theme.muted; font.pixelSize: 11; Layout.fillWidth: true }
                CgNumber { amount: card.options.period; minimum: .1; maximum: 60; accent: card.ink; onEdited: amount=>backend.setCgOption(card.selector,"period",amount) }
                AppText { text: "秒"; color: Theme.muted; font.pixelSize: 11 }
            }
            WavePlot { Layout.fillWidth: true; Layout.preferredHeight: 60; points: card.wave(card.options.wave).points; lineColor: card.ink }
        }
        ColumnLayout { visible: card.options.mode!=="fixed"; Layout.fillWidth: true; spacing: 9
            RowLayout { Layout.fillWidth: true
                AppText { text: "循环队列 · "+Number(card.options.queue.reduce(function(t,x){return t+x.seconds;},0)).toFixed(1)+" 秒"; color: card.ink; font.pixelSize: 12; Layout.fillWidth: true }
                AppSwitch { objectName: "cgQueueLoop_"+card.route; accent: card.ink; checked: card.options.loop; onToggled: backend.setCgOption(card.selector,"loop",checked) }
                AppText { text: card.options.loop ? "循环" : "仅一轮"; color: Theme.muted; font.pixelSize: 11 }
            }
            AppCombo { visible: !card.options.loop; Layout.fillWidth: true; model: ["一轮后保持最后波形","一轮后停止本路输出"]; currentIndex: card.options.end==="stop" ? 1 : 0; onActivated: backend.setCgOption(card.selector,"end",currentIndex===1 ? "stop" : "hold") }
            DisclosureHeader { id: queueDetails; objectName: "cgQueueDetails_"+card.route; accent: card.ink; Layout.fillWidth: true; title: backend.translate("编辑循环队列",backend.language); summary: card.options.queue.length+" 种波形 · 展开调整顺序、时长与比例" }
            Repeater { model: queueDetails.expanded ? card.options.queue : []
                Rectangle {
                    id: queueItem
                    required property var modelData
                    required property int index
                    objectName: "cgQueueItem_"+card.route+"_"+index
                    Layout.fillWidth: true; Layout.preferredHeight: queueBody.implicitHeight+20; color: Theme.raised; radius: 4; border.color: Theme.border
                    ColumnLayout { id: queueBody; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 10; spacing: 7
                        RowLayout { Layout.fillWidth: true; spacing: 5
                            AppText { text: String(queueItem.index+1); color: card.ink; font.pixelSize: 11 }
                            WaveChoice { accent: card.ink; period: queueItem.modelData.period; objectName: "cgQueueWave_"+card.route+"_"+queueItem.index; Layout.fillWidth: true; model: card.catalog; textRole: "name"; currentIndex: card.waveIndex(queueItem.modelData.wave); onActivated: backend.setCgQueue(card.selector,queueItem.index,"wave",card.catalog[currentIndex].key) }
                            AppButton { objectName: "cgQueueUp_"+card.route+"_"+queueItem.index; implicitWidth: 28; text: "↑"; enabled: queueItem.index>0; onClicked: backend.moveCgQueue(card.selector,queueItem.index,-1) }
                            AppButton { objectName: "cgQueueDown_"+card.route+"_"+queueItem.index; implicitWidth: 28; text: "↓"; enabled: queueItem.index<card.options.queue.length-1; onClicked: backend.moveCgQueue(card.selector,queueItem.index,1) }
                            AppButton { objectName: "cgQueueRemove_"+card.route+"_"+queueItem.index; implicitWidth: 28; text: "×"; onClicked: backend.removeCgQueue(card.selector,queueItem.index) }
                        }
                        RowLayout { Layout.fillWidth: true
                            AppText { text: "播放 / 秒"; color: Theme.muted; font.pixelSize: 10 }
                            CgNumber { objectName: "cgQueueSeconds_"+card.route+"_"+queueItem.index; Layout.fillWidth: true; amount: queueItem.modelData.seconds; minimum: .1; maximum: 600; accent: card.ink; onEdited: amount=>backend.setCgQueue(card.selector,queueItem.index,"seconds",amount) }
                            AppText { text: "周期 / 秒"; color: Theme.muted; font.pixelSize: 10 }
                            CgNumber { Layout.fillWidth: true; amount: queueItem.modelData.period; minimum: .1; maximum: 60; accent: card.ink; onEdited: amount=>backend.setCgQueue(card.selector,queueItem.index,"period",amount) }
                        }
                        RowLayout { Layout.fillWidth: true
                            AppText { text: "输出比例"; color: Theme.muted; font.pixelSize: 10 }
                            AppSlider { objectName: "cgQueueScale_"+card.route+"_"+queueItem.index; Layout.fillWidth: true; accent: card.ink; from: 0; to: 1; stepSize: .01; value: queueItem.modelData.scale===undefined ? 1 : queueItem.modelData.scale; onMoved: backend.setCgQueue(card.selector,queueItem.index,"scale",value) }
                            AppText { text: Math.round((queueItem.modelData.scale===undefined ? 1 : queueItem.modelData.scale)*100)+"%"; color: card.ink; font.pixelSize: 11 }
                        }
                        AppText { visible: card.waveIndex(queueItem.modelData.wave)<0; text: "波形已缺失，请重新选择"; color: Theme.red; font.pixelSize: 10 }
                    }
                }
            }
            RowLayout { visible: queueDetails.expanded; Layout.fillWidth: true
                WaveChoice { id: addWave; objectName: "cgAddWave_"+card.route; accent: card.ink; Layout.fillWidth: true; model: card.catalog; textRole: "name" }
                AppButton { objectName: "cgQueueAdd_"+card.route; text: "+ 加入"; accent: card.ink; enabled: card.options.queue.length<32; onClicked: backend.addCgQueue(card.selector,card.catalog[addWave.currentIndex].key) }
            }
            AppText { visible: card.options.queue.length===0; Layout.fillWidth: true; text: "队列为空，本路不输出。选择波形后加入队列。"; color: Theme.violet; font.pixelSize: 11; wrapMode: Text.Wrap; elide: Text.ElideNone }
        }
        DisclosureHeader { id: advanced; objectName: "cgAdvanced_"+card.route; Layout.fillWidth: true; title: backend.translate("渐强细节",backend.language); summary: "曲线、重新渐强的时机与频率" }
        ColumnLayout { visible: advanced.expanded; Layout.fillWidth: true; spacing: 9
            AppCombo { objectName: "cgRampMode_"+card.route; Layout.fillWidth: true; model: ["线性渐强","先缓后强","先强后缓","阶梯渐强","固定峰值强度"]; currentIndex: ["linear","ease_in","ease_out","steps","constant"].indexOf(card.options.ramp_mode); onActivated: backend.setCgOption(card.selector,"ramp_mode",["linear","ease_in","ease_out","steps","constant"][currentIndex]) }
            RowLayout { visible: card.options.ramp_mode==="steps"; Layout.fillWidth: true
                AppText { text: "阶梯数量"; color: Theme.muted; font.pixelSize: 11; Layout.fillWidth: true }
                CgNumber { amount: card.options.ramp_steps; minimum: 2; maximum: 20; decimals: 0; accent: card.ink; onEdited: amount=>backend.setCgOption(card.selector,"ramp_steps",amount) }
            }
            RowLayout { visible: card.route==="pulse"; Layout.fillWidth: true
                AppText { text: "自绘波形频率 / Hz"; color: Theme.muted; font.pixelSize: 11; Layout.fillWidth: true }
                CgNumber { amount: card.options.frequency; minimum: 1; maximum: 100; decimals: 0; accent: card.ink; onEdited: amount=>backend.setCgOption(card.selector,"frequency",amount) }
            }
            AppText { Layout.fillWidth: true; text: "当前仅修改 "+card.channel+" 通道。官方波形保留帧内频率，自绘波形可调频率；另一通道的队列、循环与渐强保持独立。"; color: Theme.muted; font.pixelSize: 10; wrapMode: Text.Wrap; elide: Text.ElideNone }
        }
    }
}
