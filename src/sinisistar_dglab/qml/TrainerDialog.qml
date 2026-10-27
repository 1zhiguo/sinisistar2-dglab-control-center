import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Dialog {
    id: dialog
    objectName: "trainerDialog"
    parent: Overlay.overlay; anchors.centerIn: parent
    width: Math.min(850,parent.width-40); height: Math.min(730,parent.height-40)
    padding: 22; modal: true; closePolicy: Popup.CloseOnEscape
    readonly property var state: backend.trainerState || ({})
    property int tabIndex: 0
    readonly property var currentStatuses: state.abnormals || []
    onOpened: { hpCard.sync();mpCard.sync();attackCard.sync(); }
    background: Rectangle { color: Theme.panel; border.color: Theme.gold; radius: 7 }
    component NumberBox: SpinBox {
        id: box
        property int scaleFactor: 1
        readonly property real number: value/scaleFactor
        implicitWidth: 115; implicitHeight: 36; editable: true
        from: 0; to: 10000000; stepSize: 1
        textFromValue: function(v,locale){return Number(v/scaleFactor).toLocaleString(locale,'f',scaleFactor===1 ? 0 : 2);}
        valueFromText: function(t,locale){return Math.round(Number.fromLocaleString(locale,t)*scaleFactor);}
        validator: DoubleValidator { bottom: box.from/box.scaleFactor; top: box.to/box.scaleFactor; decimals: box.scaleFactor===1 ? 0 : 2 }
        contentItem: TextInput { text: box.textFromValue(box.value,box.locale); color: Theme.text; font.pixelSize: 13; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; readOnly: !box.editable; validator: box.validator; inputMethodHints: Qt.ImhFormattedNumbersOnly }
        background: Rectangle { radius: 3; color: Theme.bg; border.color: Theme.border }
        up.indicator: Rectangle { x: box.width-width; width: 25; height: box.height; color: box.up.pressed ? Theme.border : Theme.raised; AppText { anchors.centerIn: parent; text: "+"; color: Theme.gold; font.pixelSize: 17 } }
        down.indicator: Rectangle { width: 25; height: box.height; color: box.down.pressed ? Theme.border : Theme.raised; AppText { anchors.centerIn: parent; text: "−"; color: Theme.gold; font.pixelSize: 17 } }
        leftPadding: 26;rightPadding: 26
    }
    component ResourceCard: Panel {
        id: card
        property string field: "hp"
        property string title: "HP"
        readonly property bool attack: field==="attack"
        readonly property var resource: dialog.state[field] || ({})
        readonly property var current: attack ? dialog.state.attack_multiplier : resource.current
        readonly property int maximum: attack ? 10 : Number(resource.max || 100)
        readonly property bool available: !!dialog.state.can_edit && (!attack || !!dialog.state.attack_available)
        property bool dirty: false
        function sync(){dirty=false;if(current!==undefined && current!==null)target.value=Math.round(Number(current)*target.scaleFactor);}
        onCurrentChanged: if(!dirty && current!==undefined && current!==null)target.value=Math.round(Number(current)*target.scaleFactor)
        Layout.fillWidth: true; Layout.preferredHeight: 142
        ColumnLayout { anchors.fill: parent; anchors.margins: 15; spacing: 12
            RowLayout { Layout.fillWidth: true
                AppText { text: card.title; color: Theme.gold; font.pixelSize: 18; Layout.fillWidth: true }
                AppText { objectName: "trainerCurrent_"+card.field; text: card.current===undefined || card.current===null ? "等待游戏" : card.attack ? Number(card.current).toFixed(2)+" ×" : card.current+" / "+card.maximum; color: Theme.text; font.pixelSize: 18 }
            }
            RowLayout { Layout.fillWidth: true; spacing: 10
                AppText { text: "每次"; color: Theme.muted; font.pixelSize: 11 }
                NumberBox { id: step; objectName: "trainerStep_"+card.field; scaleFactor: card.attack ? 100 : 1; from: card.attack ? 1 : 1; to: card.attack ? 1000 : 10000; stepSize: card.attack ? 5 : 1; value: card.attack ? 25 : 10 }
                AppButton { objectName: "trainerMinus_"+card.field; text: "减少"; implicitWidth: 75; enabled: card.available; onClicked: backend.modifyGameValue(card.field,"add",-step.number) }
                AppButton { objectName: "trainerPlus_"+card.field; text: "增加"; implicitWidth: 75; primary: true; enabled: card.available; onClicked: backend.modifyGameValue(card.field,"add",step.number) }
                Item { Layout.fillWidth: true }
                NumberBox { id: target; objectName: "trainerTarget_"+card.field; scaleFactor: card.attack ? 100 : 1; to: card.maximum*scaleFactor; stepSize: card.attack ? 25 : 1; value: card.attack ? 100 : 100; onValueModified: card.dirty=true }
                AppButton { objectName: "trainerSet_"+card.field; text: "设为此值"; implicitWidth: 90; enabled: card.available; onClicked: backend.modifyGameValue(card.field,"set",target.number) }
            }
        }
    }
    contentItem: ColumnLayout { spacing: 14
        RowLayout { Layout.fillWidth: true
            AppText { text: "游戏辅助"; font.pixelSize: 24; color: Theme.gold; Layout.fillWidth: true }
            AppText { text: dialog.state.online ? "辅助插件 "+(dialog.state.version || "")+" 在线" : dialog.state.installed ? "已安装 · 等待重启加载" : "等待辅助插件"; color: dialog.state.online ? Theme.green : Theme.muted; font.pixelSize: 11 }
            AppButton { objectName: "installTrainerButton"; text: "安装 / 更新辅助插件"; enabled: !dialog.state.pending; onClicked: backend.installTrainer() }
        }
        AppText { Layout.fillWidth: true; text: "HP / MP 支持增加、减少与指定数值；攻击倍率 1× 为原始伤害，低于 1× 可降低。修改前自动暂停 Pulse 与负鼠。"; color: Theme.muted; font.pixelSize: 11; wrapMode: Text.Wrap; elide: Text.ElideNone }
        RowLayout { Layout.fillWidth: true; spacing: 10
            AppButton { objectName: "trainerAttributesTab"; text: "属性调整"; primary: dialog.tabIndex===0; onClicked: dialog.tabIndex=0 }
            AppButton { objectName: "trainerStatusesTab"; text: "当前异常 · "+dialog.currentStatuses.length; primary: dialog.tabIndex===1; onClicked: dialog.tabIndex=1 }
            Item { Layout.fillWidth: true }
        }
        ScrollView { id: view; Layout.fillWidth: true; Layout.fillHeight: true; clip: true; contentWidth: availableWidth
            ColumnLayout { width: view.availableWidth; spacing: 12
                ColumnLayout { visible: dialog.tabIndex===0; Layout.fillWidth: true; spacing: 12
                ResourceCard { id: hpCard; field: "hp"; title: backend.translate("生命 HP",backend.language) }
                ResourceCard { id: mpCard; field: "mp"; title: backend.translate("魔力 MP",backend.language) }
                ResourceCard { id: attackCard; field: "attack"; title: backend.translate("辅助攻击倍率",backend.language) }
                AppText { objectName: "trainerGameAttackLevel"; visible: !!dialog.state.valid && dialog.state.attack_level!==undefined && dialog.state.attack_level!==null; text: "游戏攻击等级：Lv."+dialog.state.attack_level+" · 游戏内升级照常生效"; color: Theme.gold; font.pixelSize: 12 }
                AppText { visible: !!dialog.state.online && !dialog.state.attack_persistent; text: "当前插件尚不保存辅助倍率，请退出游戏后更新到 0.2.1。"; color: Theme.gold; font.pixelSize: 11 }
                RowLayout { Layout.fillWidth: true
                    AppText { Layout.fillWidth: true; text: "辅助倍率自动保存，重启后保留；1× 为游戏当前原始伤害，不改变攻击升级。HP / MP 限制在当前上限内；HP 改为 0 会进入死亡流程。"; color: Theme.muted; font.pixelSize: 10; wrapMode: Text.Wrap; elide: Text.ElideNone }
                    AppButton { objectName: "trainerResetAttack"; text: "重置辅助倍率 1×"; implicitWidth: 130; enabled: attackCard.available; onClicked: backend.modifyGameValue("attack","reset",0) }
                }
                }
                ColumnLayout { visible: dialog.tabIndex===1; Layout.fillWidth: true; spacing: 12
                    RowLayout { Layout.fillWidth: true
                        AppText { text: "当前生效异常"; color: Theme.gold; font.pixelSize: 18; Layout.fillWidth: true }
                        AppButton { objectName: "trainerClearNegative"; text: "清除负面异常"; primary: true; enabled: !!dialog.state.can_edit && !!dialog.state.status_removal_available && dialog.state.negative_count>0; onClicked: backend.modifyGameValue("abnormals","clear_negative",0) }
                    }
                    AppText { Layout.fillWidth: true; text: "逐项解除由你选择；批量清除保留加护。解除后由游戏回读确认，环境或流程仍可能重新施加状态。"; color: Theme.muted; font.pixelSize: 11; wrapMode: Text.Wrap; elide: Text.ElideNone }
                    AppText { visible: !dialog.state.status_removal_available; Layout.fillWidth: true; text: "异常解除需要辅助插件 0.2.0。请保存并退出游戏，更新辅助插件后重新启动。"; color: Theme.gold; font.pixelSize: 11; wrapMode: Text.Wrap; elide: Text.ElideNone }
                    Repeater { model: dialog.currentStatuses
                        Panel {
                            id: statusCard
                            required property var modelData
                            Layout.fillWidth: true; Layout.preferredHeight: 76
                            RowLayout { anchors.fill: parent; anchors.margins: 14; spacing: 12
                                ColumnLayout { Layout.fillWidth: true; spacing: 6
                                    AppText { text: statusCard.modelData.label+" · Lv."+statusCard.modelData.level; color: Theme.text; font.pixelSize: 15; Layout.fillWidth: true }
                                    AppText { text: statusCard.modelData.positive ? "正面加护 · 批量清除时保留" : "当前负面状态"; color: statusCard.modelData.positive ? Theme.green : Theme.muted; font.pixelSize: 10 }
                                }
                                AppButton { objectName: "removeCurrentAbnormal_"+statusCard.modelData.type_raw; text: "移除"; enabled: !!dialog.state.can_edit && !!dialog.state.status_removal_available; onClicked: backend.modifyGameValue("abnormal","remove",statusCard.modelData.type_raw) }
                            }
                        }
                    }
                    AppText { visible: !!dialog.state.status_removal_available && dialog.currentStatuses.length===0; text: dialog.state.valid ? "当前没有生效异常" : "等待进入可操作存档"; color: Theme.muted; font.pixelSize: 12 }
                }

            }
        }
        AppText { objectName: "trainerResult"; Layout.fillWidth: true; text: dialog.state.error || (dialog.state.online && !dialog.state.valid ? "辅助插件已连接，请进入可操作存档后使用。" : dialog.state.message) || "首次安装后请保存并重启游戏，然后进入可操作存档。"; color: dialog.state.error ? Theme.red : Theme.muted; font.pixelSize: 11; wrapMode: Text.Wrap; elide: Text.ElideNone }
        AppButton { text: "完成"; Layout.alignment: Qt.AlignRight; onClicked: dialog.close() }
    }
}
