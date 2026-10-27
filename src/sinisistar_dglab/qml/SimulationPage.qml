import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

ColumnLayout {
    id: page
    objectName: "feedbackPolicyPage"
    property int groupIndex: 0
    property int selected: 0
    readonly property var groups: ["rules","abnormals","flows"]
    readonly property var rows: groupIndex===0 ? backend.simulationEvents : groupIndex===1 ? backend.simulationAbnormals : backend.simulationFlows
    readonly property var plan: backend.simulation
    readonly property var settings: backend.simulationSettings
    readonly property var live: backend.state
    readonly property var activeKeys: live.valid && live.pluginFresh ? live.abnormals.map(function(r){return r.name;}) : []
    property string stateFilter: "negative"
    property string categoryFilter: "all"
    readonly property var categories: [{key:"all",label:"全部分类"},{key:"debuff",label:"伤害与减益"},{key:"restraint",label:"束缚与行动"},{key:"parasite",label:"寄生与附着"},{key:"body",label:"身体与持续状态"},{key:"special",label:"特殊与流程"},{key:"positive",label:"正面加护"}]
    function matches(row){
        if((row.name+" "+row.key+" "+(row.category_label || "")).toLowerCase().indexOf(search.text.trim().toLowerCase())<0)return false;
        if(groupIndex!==1)return true;
        if(categoryFilter!=="all" && row.category!==categoryFilter)return false;
        if(stateFilter==="negative" && row.feedback_excluded)return false;
        if(stateFilter==="positive" && !row.feedback_excluded)return false;
        if(stateFilter==="active" && activeKeys.indexOf(row.key)<0)return false;
        if(stateFilter==="enabled" && !row.enabled)return false;
        if(stateFilter==="disabled" && (row.enabled || row.feedback_excluded))return false;
        return true;
    }
    readonly property var filteredRows: rows.map(function(r,i){return Object.assign({},r,{sourceIndex:i});}).filter(function(r){return page.matches(r);})
    readonly property var batchKeys: filteredRows.filter(function(r){return !r.feedback_excluded;}).map(function(r){return r.key;})
    onFilteredRowsChanged: if(!filteredRows.some(function(r){return r.sourceIndex===page.selected;}))selected=filteredRows.length ? filteredRows[0].sourceIndex : -1
    spacing: 15
    Panel { objectName: "tutorialChannelPolicies"; Layout.fillWidth: true; Layout.preferredHeight: channelBody.implicitHeight+24
        ColumnLayout { id: channelBody; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 12; spacing: 10
            AppText { text: "A/B 通道策略"; color: Theme.gold; font.pixelSize: 16 }
            ChannelFeedbackSettings { Layout.fillWidth: true }
        }
    }
    RowLayout { Layout.fillWidth: true; Layout.fillHeight: true; spacing: 16
        Panel { Layout.preferredWidth: 280; Layout.fillHeight: true
            ColumnLayout { anchors.fill: parent; anchors.margins: 13; spacing: 10
                AppCombo { objectName: "policyGroupChoice"; Layout.fillWidth: true; model: ["事件规则","异常状态 · "+backend.simulationAbnormals.length+" 种","已绑定演出规则"]; currentIndex: page.groupIndex; onActivated: {page.groupIndex=currentIndex;search.text="";page.selected=0;} }
                TextField { id: search; objectName: "policySearch"; Layout.fillWidth: true; placeholderText: backend.translate(("搜索中文 / 原名 / 分类"),backend.language); color: Theme.text; font.pixelSize: 12; background: Rectangle { color: Theme.raised; border.color: Theme.border; radius: 4 } }
                AppCombo { objectName: "abnormalStateFilter"; visible: page.groupIndex===1; Layout.fillWidth: true; readonly property var keys: ["negative","all","active","enabled","disabled","positive"]; model: ["负面异常","全部状态","当前生效","已启用反馈","未启用反馈","正面 Buff（不参与）"]; currentIndex: keys.indexOf(page.stateFilter); onActivated: page.stateFilter=keys[currentIndex] }
                AppCombo { objectName: "abnormalCategoryFilter"; visible: page.groupIndex===1; Layout.fillWidth: true; model: page.categories; textRole: "label"; currentIndex: page.categories.findIndex(function(c){return c.key===page.categoryFilter;}); onActivated: page.categoryFilter=page.categories[currentIndex].key }
                RowLayout { visible: page.groupIndex===1; Layout.fillWidth: true; spacing: 8
                    AppButton { objectName: "enableFilteredAbnormals"; Layout.fillWidth: true; implicitWidth: 100; text: "启用筛选项"; primary: true; enabled: page.batchKeys.length>0; onClicked: backend.batchSetAbnormals(page.batchKeys,true) }
                    AppButton { objectName: "disableFilteredAbnormals"; Layout.fillWidth: true; implicitWidth: 100; text: "关闭筛选项"; enabled: page.batchKeys.length>0; onClicked: backend.batchSetAbnormals(page.batchKeys,false) }
                }
                AppText { visible: page.groupIndex===1; Layout.fillWidth: true; text: "筛选 "+page.filteredRows.length+" / "+page.rows.length+" · 已启用 "+page.rows.filter(function(r){return r.enabled && !r.feedback_excluded;}).length+"
批量操作仅作用于当前筛选结果"; color: Theme.muted; font.pixelSize: 10; wrapMode: Text.Wrap; elide: Text.ElideNone }
                ListView { objectName: "policyRuleList"; Layout.fillWidth: true; Layout.fillHeight: true; clip: true; model: page.filteredRows; spacing: 3
                    currentIndex: page.filteredRows.findIndex(function(r){return r.sourceIndex===page.selected;})
                    ScrollBar.vertical: ScrollBar { }
                    delegate: Rectangle {
                        required property var modelData
                        width: ListView.view.width-9; height: 55; radius: 4; color: page.selected===modelData.sourceIndex ? Theme.raised : "transparent"
                        Column { x: 9; anchors.verticalCenter: parent.verticalCenter; width: parent.width-28; spacing: 4
                            AppText { width: parent.width; text: modelData.name; font.pixelSize: 12; color: page.selected===modelData.sourceIndex ? Theme.gold : Theme.text }
                            AppText { width: parent.width; text: modelData.feedback_excluded ? "正面 Buff · 不参与" : (modelData.enabled ? "已启用" : "已关闭")+(page.groupIndex===1 ? " · "+(modelData.category_label || "特殊与流程") : ""); font.pixelSize: 10; color: Theme.muted }
                        }
                        MouseArea { anchors.fill: parent; onClicked: page.selected=parent.modelData.sourceIndex; cursorShape: Qt.PointingHandCursor }
                    }
                }
                AppText { Layout.fillWidth: true; text: page.groupIndex===1 ? "每种 Pulse 10，等级不加成；不同种类按通道叠加。负鼠为 0。异常默认关闭，正面 Buff 不参与。" : "死亡惩罚可选持续到复活 / CG 结束，或固定时长。修改策略会暂停 Pulse 和负鼠。"; font.pixelSize: 10; color: Theme.muted; wrapMode: Text.Wrap; elide: Text.ElideNone }
            }
        }
        ScrollView { id: scroller; Layout.fillWidth: true; Layout.fillHeight: true; clip: true; contentWidth: availableWidth
            ColumnLayout { width: scroller.availableWidth; spacing: 18
                Panel { Layout.fillWidth: true; Layout.preferredHeight: globalOptions.implicitHeight+32
                    ColumnLayout { id: globalOptions; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 16; spacing: 10
                        DisclosureHeader { id: sharedHeader; objectName: "policySharedDisclosure"; Layout.fillWidth: true; title: backend.translate("共享策略设置",backend.language); summary: "叠加方式、零血策略、通道上限与异常规则说明" }
                        ColumnLayout { visible: sharedHeader.expanded; Layout.fillWidth: true; spacing: 10
                        RowLayout { Layout.fillWidth: true
                            AppText { text: "叠加方式"; color: Theme.gold; font.pixelSize: 13 }
                            AppCombo { model: ["按优先级","取最强","限幅叠加"]; currentIndex: ["priority","max","sum"].indexOf(page.settings.mix); onActivated: backend.setSimulationSetting("mix",["priority","max","sum"][currentIndex]) }
                            Item { Layout.fillWidth: true }
                            AppText { text: "Pulse 0–100 · 负鼠 0–200"; color: Theme.muted; font.pixelSize: 10 }
                        }
                        RowLayout { Layout.fillWidth: true
                            AppText { text: "零血反馈策略"; color: Theme.muted; font.pixelSize: 11 }
                            AppCombo { Layout.fillWidth: true; model: ["暂停零血反馈","启用死亡惩罚规则","启用死亡惩罚与异常反馈"]; currentIndex: ["stop","capture","states"].indexOf(page.settings.zero_hp_mode); onActivated: backend.setSimulationSetting("zero_hp_mode",["stop","capture","states"][currentIndex]) }
                            AppText { text: "不据此确认 CG"; color: Theme.violet; font.pixelSize: 10 }
                        }
                        Repeater { model: ["pulse","vibration"]
                            RowLayout { required property string modelData; readonly property string route: modelData; Layout.fillWidth: true
                                AppText { text: route==="pulse" ? "Pulse" : "负鼠"; color: Theme.muted; Layout.preferredWidth: 45 }
                                Repeater { model: ["a","b"]
                                    RowLayout { required property string modelData; readonly property string field: parent.route+"_cap_"+modelData
                                        AppText { text: modelData.toUpperCase()+" 上限 "+page.settings[field]; font.pixelSize: 10; color: Theme.muted; Layout.preferredWidth: 65 }
                                        AppSlider { accent: parent.parent.route==="vibration" ? Theme.violet : Theme.gold; Layout.fillWidth: true; to: parent.parent.route==="vibration" ? 200 : 100; stepSize: parent.parent.route==="vibration" ? 10 : 1; value: page.settings[parent.field]; onMoved: backend.setSimulationSetting(parent.field,value) }
                                    }
                                }
                            }
                        }
                        AppText { Layout.fillWidth: true; text: "异常固定每种 Pulse 10：1 种 = 10、2 种 = 20、3 种 = 30。等级不增加强度，同一种去重；按各自通道叠加并限幅。负鼠异常反馈为 0。"; font.pixelSize: 10; color: Theme.violet; wrapMode: Text.Wrap; elide: Text.ElideNone }
                        }
                    }
                }
                FeedbackRuleEditor { Layout.fillWidth: true; visible: page.filteredRows.length>0 && page.selected>=0; rule: page.rows[page.selected] || ({}); group: page.groups[page.groupIndex]; ruleIndex: page.selected }
                AppButton { visible: page.groupIndex===2 && page.rows.length>0; text: "删除这条演出规则"; onClicked: {backend.removeFlowRule(page.selected);page.selected=0;} }
                AppText { Layout.fillWidth: true; visible: page.filteredRows.length===0; text: page.rows.length===0 ? "暂无绑定演出。先在「演出与流程」记录真实播放器，再添加规则。" : "没有符合筛选条件的规则。"; color: Theme.muted; wrapMode: Text.Wrap; elide: Text.ElideNone }
                Panel { Layout.fillWidth: true; Layout.preferredHeight: activeColumn.implicitHeight+32
                    ColumnLayout { id: activeColumn; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 16; spacing: 9
                        AppText { text: "当前参与规则"; color: Theme.gold; font.pixelSize: 14 }
                        Repeater { model: page.plan.active
                            AppText { required property var modelData; Layout.fillWidth: true; text: modelData.name+" · "+modelData.detail+" · Pulse "+modelData.pulse+" / 震动 "+modelData.vibration+" · "+modelData.pulse_wave+" / "+modelData.vibration_wave+" · "+modelData.pulse_frequency+" Hz"; font.pixelSize: 11; color: Theme.muted; wrapMode: Text.Wrap; elide: Text.ElideNone }
                        }
                        AppText { visible: page.plan.active.length===0; text: "当前没有生效规则"; color: Theme.muted; font.pixelSize: 11 }
                    }
                }
            }
        }
    }
}
