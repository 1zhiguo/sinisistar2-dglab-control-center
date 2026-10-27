import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

ScrollView {
    id: page
    objectName: "quickSettingsPage"
    signal openAbnormals()
    signal openCg()
    clip: true; contentWidth: availableWidth
    readonly property var policy: backend.quickPolicy
    readonly property string selectedPreset: policy.active || ""
    property string pendingPreset: ""
    function choosePreset(key){pendingPreset=key;if(!policy.active)replaceDialog.open();else backend.applyQuickPreset(key,false);}
    readonly property var draft: policy.current || ({})
    readonly property var keys: ["low","medium","high"]
    function label(key){return ({low:"低",medium:"中",high:"高"})[key] || "自定义";}
    function summary(key){return "Pulse "+draft["pulse_"+key]+" / 负鼠 "+draft["ovc_"+key];}
    component Amount: RowLayout {
        id: control
        property string field: ""
        property bool sharedDeath: false
        readonly property bool ovc: field.indexOf("ovc_")===0
        readonly property string otherField: field.slice(0,-1)+"b"
        readonly property bool mixed: false
        function update(value){if(sharedDeath)backend.editQuickRange((ovc ? "ovc" : "pulse")+"_death",0,value);else backend.editQuickValue(field,value);}
        Layout.fillWidth: true; spacing: 9
        AppText { visible: control.mixed; Layout.fillWidth: true; text: "A "+page.draft[control.field]+"  /  B "+page.draft[control.otherField]; color: Theme.violet; font.pixelSize: 13 }
        AppButton { visible: control.mixed; text: "分别调整"; onClicked: advancedHeader.expanded=true }
        AppSlider { objectName: "presetSlider_"+control.field; accent: control.ovc ? Theme.violet : Theme.gold; visible: !control.mixed; Layout.fillWidth: true; Layout.minimumWidth: 65; to: control.ovc && control.field.indexOf("stack_bonus")<0 ? 200 : 100; stepSize: control.ovc ? 10 : 1; value: Number(page.draft[control.field] || 0); onMoved: control.update(value) }
        SpinBox { id: numeric; visible: !control.mixed; objectName: (control.sharedDeath ? "shared_" : "preset_")+control.field; from: 0; to: control.ovc && control.field.indexOf("stack_bonus")<0 ? 200 : 100; stepSize: control.ovc ? 10 : 1; editable: true; value: Number(page.draft[control.field] || 0); implicitWidth: 88; implicitHeight: 30; leftPadding: 25; rightPadding: 25
            onValueModified: control.update(value)
            contentItem: TextInput { text: numeric.textFromValue(numeric.value,numeric.locale); font.pixelSize: 12; color: Theme.text; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; readOnly: !numeric.editable; validator: numeric.validator; inputMethodHints: Qt.ImhDigitsOnly }
            background: Rectangle { color: Theme.raised; border.color: Theme.border; radius: 3 }
            up.indicator: Rectangle { x: numeric.width-width; width: 24; height: numeric.height; color: numeric.up.pressed ? Theme.border : Theme.raised; AppText { anchors.centerIn: parent; text: "+"; color: control.ovc ? Theme.violet : Theme.gold; font.pixelSize: 17 } }
            down.indicator: Rectangle { width: 24; height: numeric.height; color: numeric.down.pressed ? Theme.border : Theme.raised; AppText { anchors.centerIn: parent; text: "−"; color: control.ovc ? Theme.violet : Theme.gold; font.pixelSize: 17 } }
        }
    }
    component RangeAmount: ColumnLayout {
        id: control
        property string field: ""
        property bool sharedDeath: false
        readonly property bool ovc: field.indexOf("ovc_")===0
        readonly property string prefix: field.indexOf("death")>=0 ? field.slice(0,field.lastIndexOf("_")) : field
        readonly property string lowField: field.indexOf("death")>=0 ? prefix+"_start_"+field.slice(-1) : field+"_start"
        readonly property bool mixed: sharedDeath && (page.draft[field]!==page.draft[prefix+"_b"] || page.draft[lowField]!==page.draft[prefix+"_start_b"])
        Layout.fillWidth: true; spacing: 4
        AppText { visible: control.mixed; Layout.fillWidth: true; text: "A "+page.draft[control.lowField]+"–"+page.draft[control.field]+"  /  B "+page.draft[control.prefix+"_start_b"]+"–"+page.draft[control.prefix+"_b"]; color: Theme.violet; font.pixelSize: 12 }
        AppButton { visible: control.mixed; text: "分别调整范围"; onClicked: advancedHeader.expanded=true }
        StrengthRange { visible: !control.mixed; objectName: (control.sharedDeath ? "sharedRange_" : "presetRange_")+control.field; identifier: control.sharedDeath ? "shared_"+control.field : control.field; Layout.fillWidth: true; maximum: control.ovc ? 200 : 100; step: control.ovc ? 10 : 1; accent: control.ovc ? Theme.violet : Theme.gold; low: Number(page.draft[control.lowField] || 0); high: Number(page.draft[control.field] || 0); onEdited: (low,high)=>backend.editQuickRange(control.sharedDeath ? control.prefix : control.field,low,high) }
    }
    component Labels: RowLayout {
        Layout.fillWidth: true; spacing: 20
        Item { Layout.preferredWidth: 110 }
        AppText { text: "PULSE"; color: Theme.gold; font.pixelSize: 10; Layout.fillWidth: true; Layout.preferredWidth: 1 }
        AppText { text: "负鼠"; color: Theme.violet; font.pixelSize: 10; Layout.fillWidth: true; Layout.preferredWidth: 1 }
    }
    component Pair: RowLayout {
        id: pair
        property string caption: ""
        property string field: ""
        property bool sharedDeath: false
        property bool range: false
        Layout.fillWidth: true; spacing: 20
        AppText { text: pair.caption; color: Theme.text; font.pixelSize: 12; Layout.preferredWidth: 110 }
        Loader { Layout.fillWidth: true; Layout.preferredWidth: 1; sourceComponent: pair.range ? pulseRange : pulseAmount }
        Loader { Layout.fillWidth: true; Layout.preferredWidth: 1; sourceComponent: pair.range ? ovcRange : ovcAmount }
        Component { id: pulseAmount; Amount { field: "pulse_"+pair.field } }
        Component { id: ovcAmount; Amount { field: "ovc_"+pair.field } }
        Component { id: pulseRange; RangeAmount { field: "pulse_"+pair.field; sharedDeath: pair.sharedDeath } }
        Component { id: ovcRange; RangeAmount { field: "ovc_"+pair.field; sharedDeath: pair.sharedDeath } }
    }
    ColumnLayout { width: page.availableWidth; spacing: 14
        Panel { Layout.fillWidth: true; Layout.preferredHeight: intro.implicitHeight+32
            ColumnLayout { id: intro; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 16; spacing: 12
                RowLayout { Layout.fillWidth: true
                    ColumnLayout { Layout.fillWidth: true; spacing: 5
                        AppText { text: "预设强度"; font.pixelSize: 23; color: Theme.gold }
                        AppText { text: "当前使用："+(page.policy.active ? page.label(page.policy.active)+"档预设" : "自定义策略")+"  ·  修改后自动保存"; color: Theme.muted; font.pixelSize: 11 }
                    }
                    Item { Layout.fillWidth: true }
                    AppText { text: "✓ 已自动保存"; color: Theme.green; font.pixelSize: 11 }
                }
                RowLayout { objectName: "tutorialPresetChoices"; Layout.fillWidth: true; spacing: 12
                    Repeater { model: page.keys
                        GothicPresetButton { required property string modelData; objectName: "choosePreset_"+modelData; tier: modelData; Layout.fillWidth: true; text: page.label(modelData)+" · "+({low:"轻柔",medium:"均衡",high:"强烈"})[modelData]; primary: page.selectedPreset===modelData; onClicked: page.choosePreset(modelData) }
                    }
                }
                AppText { Layout.fillWidth: true; text: "滑块与数值修改立即生效并自动保存为自定义，同时暂停两路输出。再次选低／中／高前会确认覆盖；手机 APP 上限仍独立有效。"; color: Theme.muted; font.pixelSize: 10; wrapMode: Text.Wrap; elide: Text.ElideNone }
            }
        }
        Panel { Layout.fillWidth: true; Layout.preferredHeight: essentials.implicitHeight+32
            ColumnLayout { id: essentials; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 16; spacing: 13
                AppText { text: "常用强度"; color: Theme.gold; font.pixelSize: 17 }
                Labels { }
                Pair { caption: "硬上限"; field: "cap" }
                Pair { caption: "普通死亡惩罚"; field: "death_a"; sharedDeath: true; range: true }
                RowLayout { Layout.fillWidth: true; spacing: 20
                    AppText { text: "死亡结束方式"; color: Theme.text; font.pixelSize: 12; Layout.preferredWidth: 110 }
                    AppCombo { objectName: "quickDeathMode"; Layout.fillWidth: true; model: ["持续到复活 / CG 结束","固定时长"]; currentIndex: page.draft.death_mode==="timed" ? 1 : 0; onActivated: backend.editQuickValue("death_mode",currentIndex===1 ? "timed" : "until_end") }
                }
                RowLayout { visible: page.draft.death_mode==="timed"; Layout.fillWidth: true; spacing: 12
                    AppText { text: "惩罚总时长"; color: Theme.muted; font.pixelSize: 11; Layout.preferredWidth: 118 }
                    AppSlider { objectName: "quickDeathSeconds"; Layout.fillWidth: true; from: .1; to: 120; stepSize: .1; value: page.draft.death_seconds || 3; onMoved: backend.editQuickValue("death_seconds",value) }
                    AppText { text: Number(page.draft.death_seconds || 3).toFixed(1)+" 秒"; color: Theme.gold; font.pixelSize: 11; Layout.preferredWidth: 60 }
                }
                Pair { caption: "抓取持续"; field: "grab"; range: true }
                RowLayout { Layout.fillWidth: true; spacing: 20
                    AppText { text: "异常反馈"; color: Theme.text; font.pixelSize: 12; Layout.preferredWidth: 110 }
                    AppText { text: "每种 10 · 不同种类相加"; color: Theme.gold; font.pixelSize: 12; Layout.fillWidth: true; Layout.preferredWidth: 1 }
                    AppText { text: "负鼠 0 · 不反馈"; color: Theme.violet; font.pixelSize: 12; Layout.fillWidth: true; Layout.preferredWidth: 1 }
                    AppButton { objectName: "manageAbnormals"; text: "管理异常"; onClicked: page.openAbnormals() }
                }
                AppText { Layout.fillWidth: true; text: "双头滑块设置起始与峰值，按线性强度逐渐上升。定时死亡惩罚到时停止；持续模式到复活 / CG 结束停止。上升用时可展开调整。"; color: Theme.muted; font.pixelSize: 10; wrapMode: Text.Wrap; elide: Text.ElideNone }
                RowLayout { Layout.fillWidth: true
                    AppText { Layout.fillWidth: true; text: backend.cgSettings.inherit_death ? "CG 当前沿用死亡参数，可独立设置波形、队列与渐强。" : "CG 已使用独立配置；此页普通死亡参数不覆盖 CG。"; color: Theme.violet; font.pixelSize: 10; wrapMode: Text.Wrap; elide: Text.ElideNone }
                    AppButton { objectName: "openCgFeedback"; text: "设置 CG 反馈"; onClicked: page.openCg() }
                }
            }
        }
        Panel { Layout.fillWidth: true; Layout.preferredHeight: channels.implicitHeight+32
            ColumnLayout { id: channels; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 16; spacing: 12
                AppText { text: "A/B 通道策略"; color: Theme.gold; font.pixelSize: 17 }
                ChannelFeedbackSettings { Layout.fillWidth: true }
            }
        }
        Panel { Layout.fillWidth: true; Layout.preferredHeight: combat.implicitHeight+24
            ColumnLayout { id: combat; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 12; spacing: 12
                DisclosureHeader { id: combatHeader; objectName: "quickCombatDisclosure"; Layout.fillWidth: true; title: backend.translate("战斗反馈",backend.language); summary: "受伤 "+page.summary("damage")+"   ·   仅 HP 下降触发" }
                ColumnLayout { visible: combatHeader.expanded; Layout.fillWidth: true; spacing: 13
                    Labels { }
                    Pair { caption: "受伤"; field: "damage" }
                    Pair { caption: "服装破损"; field: "break" }
                    AppText { text: "MP 消耗不触发反馈，使用技能不会引发受伤联动。"; color: Theme.muted; font.pixelSize: 10 }
                }
            }
        }
        Panel { Layout.fillWidth: true; Layout.preferredHeight: advanced.implicitHeight+24
            ColumnLayout { id: advanced; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 12; spacing: 12
                DisclosureHeader { id: advancedHeader; objectName: "quickAdvancedDisclosure"; Layout.fillWidth: true; title: backend.translate("上升速度、A/B 与更多设置",backend.language); summary: "单次反馈时长、抓取 / 死亡的上升用时、独立通道范围" }
                ColumnLayout { visible: advancedHeader.expanded; Layout.fillWidth: true; spacing: 13
                    Labels { }
                    Pair { caption: "死亡惩罚 A"; field: "death_a"; range: true }
                    Pair { caption: "死亡惩罚 B"; field: "death_b"; range: true }
                    Repeater { model: [{key:"feedback_seconds",label:"单次反馈时长"},{key:"grab_ramp_seconds",label:"抓取上升用时"},{key:"death_ramp_seconds",label:"死亡上升用时"}]
                        RowLayout { required property var modelData; Layout.fillWidth: true; spacing: 12
                            AppText { text: parent.modelData.label; color: Theme.muted; font.pixelSize: 11; Layout.preferredWidth: 110 }
                            AppSlider { Layout.fillWidth: true; from: .1; to: parent.modelData.key==="feedback_seconds" ? 30 : 120; stepSize: .1; value: page.draft[parent.modelData.key]; onMoved: backend.editQuickValue(parent.modelData.key,value) }
                            AppText { text: Number(page.draft[parent.modelData.key]).toFixed(1)+" 秒"; color: Theme.gold; font.pixelSize: 11; Layout.preferredWidth: 60 }
                        }
                    }
                    RowLayout { Layout.fillWidth: true; spacing: 10
                        AppText { text: "所有调整已保存到当前自定义策略"; color: Theme.muted; font.pixelSize: 10 }
                        Item { Layout.fillWidth: true }
                    }
                    Rectangle { Layout.fillWidth: true; height: 1; color: Theme.border }
                    AppText { text: "当前策略 · 死亡惩罚开关"; color: Theme.gold; font.pixelSize: 13 }
                    RowLayout { Layout.fillWidth: true; spacing: 14
                        AppText { text: "死亡惩罚"; color: Theme.muted; font.pixelSize: 11 }
                        AppSwitch { checked: page.policy.deathEnabled; onToggled: backend.setSimulationRule("rules",backend.simulationEvents.findIndex(function(r){return r.key==="defeat_hold";}),"enabled",checked) }
                        Repeater { model: [{route:"pulse",channel:"A"},{route:"pulse",channel:"B"},{route:"vibration",channel:"A"},{route:"vibration",channel:"B"}]
                            RowLayout { required property var modelData; spacing: 5
                                AppText { text: (parent.modelData.route==="pulse" ? "Pulse " : "负鼠 ")+parent.modelData.channel; color: Theme.muted; font.pixelSize: 11 }
                                AppSwitch { objectName: "deathChannelToggle_"+parent.modelData.route+parent.modelData.channel; accent: parent.modelData.route==="vibration" ? Theme.violet : Theme.gold; checked: (parent.modelData.route==="pulse" ? page.policy.pulseChannels : page.policy.ovcChannels).indexOf(parent.modelData.channel)>=0; onToggled: backend.setDeathChannel(parent.modelData.route,parent.modelData.channel,checked) }
                            }
                        }
                    }
                    AppText { Layout.fillWidth: true; text: "当前强度：Pulse A "+page.policy.death.pulseA+" / B "+page.policy.death.pulseB+"  ·  负鼠 A "+page.policy.death.vibrationA+" / B "+page.policy.death.vibrationB+"。开关修改立即保存，并暂停输出。"; color: Theme.muted; font.pixelSize: 10; wrapMode: Text.Wrap; elide: Text.ElideNone }
                    AppText { Layout.fillWidth: true; text: "预设保留原有波形、周期、通道分配与规则开关；异常固定每种 Pulse 10、负鼠 0，需在管理异常中启用。MP 消耗不参与。所有强度仍受通道与 APP 上限限制。"; color: Theme.muted; font.pixelSize: 10; wrapMode: Text.Wrap; elide: Text.ElideNone }
                }
            }
        }
    }
    Dialog {
        id: replaceDialog; objectName: "replaceCustomPresetDialog"; parent: Overlay.overlay; anchors.centerIn: parent
        width: Math.min(500,parent.width-40); modal: true; padding: 24; closePolicy: Popup.CloseOnEscape
        background: Rectangle { color: Theme.panel; border.color: Theme.gold; radius: 5 }
        contentItem: ColumnLayout { spacing: 18
            AppText { text: "替换当前自定义设置？"; color: Theme.gold; font.pixelSize: 21 }
            AppText { Layout.fillWidth: true; text: "切换到「"+page.label(page.pendingPreset)+"」档，会覆盖当前自定义的强度、上限和反馈时长，无法撤销。游戏 CG 和图鉴的 A/B 强度范围也会同步；队列、波形、通道分配和渐强用时会保留。"; color: Theme.text; font.pixelSize: 12; wrapMode: Text.Wrap; elide: Text.ElideNone }
            RowLayout { Layout.fillWidth: true
                AppButton { objectName: "cancelPresetReplace"; text: "保留自定义"; onClicked: replaceDialog.close() }
                Item { Layout.fillWidth: true }
                AppButton { objectName: "confirmPresetReplace"; text: "确认切换"; primary: true; onClicked: {backend.applyQuickPreset(page.pendingPreset,false);replaceDialog.close();} }
            }
        }
    }

}
