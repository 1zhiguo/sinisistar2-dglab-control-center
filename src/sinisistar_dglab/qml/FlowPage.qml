import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

ColumnLayout {
    id: page
    objectName: "captureFlowCatalog"
    property bool leaving: false
    function prepareToLeave(){ leaving=true; }
    readonly property var flow: backend.state.flow
    property int catalogMode: 0
    property string selectedKey: ""
    property var checkedKeys: []
    readonly property var categories: {
        if(page.leaving)return [];
        var result=["全部分类"];
        backend.semanticFlows.forEach(function(r){if(result.indexOf(r.semantic_category)<0)result.push(r.semantic_category);});
        return result;
    }
    readonly property var rows: page.leaving ? [] : backend.semanticFlows.filter(function(r){
        if(page.catalogMode===0 && (r.kind || "").indexOf("static_")===0)return false;
        if(page.catalogMode===1 && (r.kind || "").indexOf("static_")!==0)return false;
        if(page.catalogMode===2 && ["recoverable","recoverable_branch","recoverable_candidate","boss_defeat","regional_go","zero_hp_capture","egg_go","static_scene"].indexOf(r.semantic_family)<0)return false;
        if(categoryChoice.currentIndex>0 && r.semantic_category!==page.categories[categoryChoice.currentIndex])return false;
        if(decisionChoice.currentIndex>0 && r.review_decision!==["","undecided","ramp","observe","skip"][decisionChoice.currentIndex])return false;
        var query=search.text.trim().toLowerCase();
        return !query || [r.semantic_title,r.semantic_category,r.scene,r.key,r.semantic_symbols,r.semantic_evidence].join(" ").toLowerCase().indexOf(query)>=0;
    })
    readonly property var item: rows.find(function(r){return r.key===page.selectedKey;}) || rows[0] || ({})
    onRowsChanged: checkedKeys=checkedKeys.filter(function(k){return page.rows.some(function(r){return r.key===k;});})
    function toggleKey(key) {
        var next=checkedKeys.slice();var i=next.indexOf(key);
        if(i<0)next.push(key);else next.splice(i,1);
        checkedKeys=next;
    }
    spacing: 12
    Panel { Layout.fillWidth: true; Layout.preferredHeight: liveColumn.implicitHeight+24
        ColumnLayout { id: liveColumn; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 12; spacing: 5
            DisclosureHeader { id: liveDetails; Layout.fillWidth: true; title: backend.translate("当前演出 · ",backend.language)+(backend.state.penaltyLabel || flow.name || "无演出播放"); summary: "展开查看阶段、计时和实时来源；下方目录提供中文语义与批量决策清单" }
            ColumnLayout { visible: liveDetails.expanded; Layout.fillWidth: true; spacing: 6
                AppText { Layout.fillWidth: true; text: "场景 / 分组："+(backend.state.scene || "—")+" / "+(flow.group || "—")+"   播放器："+(flow.name || "—"); font.pixelSize: 12 }
                AppText { Layout.fillWidth: true; text: "阶段："+(flow.label || "未捕获")+" · 组件："+(flow.label_type || "—")+" · 下一段："+(flow.next_name || "—"); color: Theme.muted; font.pixelSize: 11 }
                AppText { Layout.fillWidth: true; text: "计时："+Number(flow.elapsed || 0).toFixed(1)+" s · 抓取来源："+backend.state.binder+" · 玩家动画："+backend.state.anim; color: Theme.muted; font.pixelSize: 11 }
                AppText { Layout.fillWidth: true; text: "播放器、标签、Timeline、GameOver 分开记录；标签广播不等于实际动作，未知演出不会自动视作战败。"; color: Theme.violet; font.pixelSize: 11; wrapMode: Text.Wrap; elide: Text.ElideNone }
            }
        }
    }
    RowLayout { Layout.fillWidth: true; Layout.fillHeight: true; spacing: 12
        Panel { Layout.preferredWidth: 350; Layout.fillHeight: true
            ColumnLayout { anchors.fill: parent; anchors.margins: 14; spacing: 8
                AppCombo { objectName: "flowCatalogMode"; Layout.fillWidth: true; model: ["实机流程","静态场景 / 敌人候选","战败 / 受制相关","全部目录"]; currentIndex: page.catalogMode; onActivated: {page.catalogMode=currentIndex;page.checkedKeys=[];} }
                TextField { id: search; objectName: "flowSemanticSearch"; Layout.fillWidth: true; placeholderText: backend.translate(("搜索中文 / 原名 / Hold / 场景"),backend.language); color: Theme.text; font.pixelSize: 12; background: Rectangle { color: Theme.raised; border.color: Theme.border; radius: 4 } }
                RowLayout { Layout.fillWidth: true
                    AppCombo { id: categoryChoice; objectName: "flowCategoryFilter"; Layout.fillWidth: true; model: page.categories }
                    AppCombo { id: decisionChoice; objectName: "flowDecisionFilter"; Layout.fillWidth: true; model: ["全部意向","待决定","希望渐强","仅观察意向","不纳入计划"] }
                }
                RowLayout { Layout.fillWidth: true
                    AppButton { objectName: "selectFilteredFlows"; text: "全选筛选项"; Layout.fillWidth: true; onClicked: page.checkedKeys=page.rows.map(function(r){return r.key;}) }
                    AppButton { text: "清空勾选"; Layout.fillWidth: true; onClicked: page.checkedKeys=[] }
                }
                AppText { Layout.fillWidth: true; text: "筛选 "+page.rows.length+" 项 · 已勾选 "+page.checkedKeys.length+" 项"; font.pixelSize: 11; color: Theme.gold }
                ListView { objectName: "semanticFlowList"; Layout.fillWidth: true; Layout.fillHeight: true; clip: true; model: page.rows; spacing: 5
                    ScrollBar.vertical: ScrollBar { }
                    delegate: Rectangle {
                        required property var modelData
                        width: ListView.view.width-10; height: 86; radius: 4; color: page.item.key===modelData.key ? Theme.raised : Theme.panel
                        CheckBox { id: tick; objectName: "flowReviewCheck"; x: 4; anchors.verticalCenter: parent.verticalCenter; width: 30; height: 34; checked: page.checkedKeys.indexOf(modelData.key)>=0; onClicked: page.toggleKey(modelData.key)
                            indicator: Rectangle { width: 17; height: 17; x: 5; y: 8; radius: 2; color: tick.checked ? Theme.gold : Theme.bg; border.color: Theme.gold; AppText { anchors.centerIn: parent; text: tick.checked ? "✓" : ""; color: Theme.bg; font.pixelSize: 13 } }
                        }
                        Column { x: 38; width: parent.width-46; anchors.verticalCenter: parent.verticalCenter; spacing: 5
                            AppText { width: parent.width; text: modelData.semantic_title; color: page.item.key===modelData.key ? Theme.gold : Theme.text; font.pixelSize: 12 }
                            AppText { width: parent.width; text: modelData.semantic_category+" · "+modelData.review_label; color: modelData.review_decision==="ramp" ? Theme.violet : Theme.muted; font.pixelSize: 10 }
                            AppText { width: parent.width; text: modelData.scene; color: Theme.muted; font.pixelSize: 10 }
                        }
                        MouseArea { x: 36; width: parent.width-36; height: parent.height; onClicked: page.selectedKey=parent.modelData.key; cursorShape: Qt.PointingHandCursor }
                    }
                }
                AppText { Layout.fillWidth: true; text: "批量仅作用于当前勾选项；切换筛选会移除隐藏项的勾选。静态家族数量不等于 CG 数量。"; color: Theme.muted; font.pixelSize: 10; wrapMode: Text.Wrap; elide: Text.ElideNone }
            }
        }
        Panel { Layout.fillWidth: true; Layout.fillHeight: true
            ColumnLayout { anchors.fill: parent; anchors.margins: 16; spacing: 12
                RowLayout { Layout.fillWidth: true
                    AppText { Layout.fillWidth: true; text: "流程语义 · 联动意向"; color: Theme.gold; font.pixelSize: 18 }
                    AppButton { objectName: "exportSemanticFlows"; text: "导出 CSV 清单"; onClicked: backend.exportFlowReview() }
                }
                AppText { Layout.fillWidth: true; text: "目前读到的字段没有统一 semantic 分类。以下中文是人工对照或名称解释，原始身份与证据保留。"; color: Theme.muted; font.pixelSize: 11; wrapMode: Text.Wrap; elide: Text.ElideNone }
                RowLayout { Layout.fillWidth: true; spacing: 6
                    AppButton { objectName: "reviewRampFlows"; Layout.fillWidth: true; implicitWidth: 85; text: "希望渐强"; primary: true; enabled: page.checkedKeys.length>0; onClicked: backend.reviewFlows(page.checkedKeys,"ramp") }
                    AppButton { objectName: "reviewObserveFlows"; Layout.fillWidth: true; implicitWidth: 85; text: "仅观察意向"; enabled: page.checkedKeys.length>0; onClicked: backend.reviewFlows(page.checkedKeys,"observe") }
                    AppButton { objectName: "reviewSkipFlows"; Layout.fillWidth: true; implicitWidth: 85; text: "不纳入计划"; enabled: page.checkedKeys.length>0; onClicked: backend.reviewFlows(page.checkedKeys,"skip") }
                    AppButton { Layout.fillWidth: true; implicitWidth: 85; text: "恢复待决定"; enabled: page.checkedKeys.length>0; onClicked: backend.reviewFlows(page.checkedKeys,"undecided") }
                }
                AppText { Layout.fillWidth: true; text: "这里保存决策清单，不改变当前输出。猪棚等已接入规则仍在「联动策略」控制；新意向需核验起止后接入。"; color: Theme.violet; font.pixelSize: 11; wrapMode: Text.Wrap; elide: Text.ElideNone }
                Rectangle { Layout.fillWidth: true; height: 1; color: Theme.border }
                ScrollView { id: details; Layout.fillWidth: true; Layout.fillHeight: true; clip: true; contentWidth: availableWidth
                    ColumnLayout { width: details.availableWidth; spacing: 10
                        AppText { Layout.fillWidth: true; text: page.item.semantic_title || "没有符合筛选的流程"; font.pixelSize: 19; wrapMode: Text.Wrap; elide: Text.ElideNone }
                        AppText { Layout.fillWidth: true; text: (page.item.semantic_category || "")+" · "+(page.item.review_label || ""); color: Theme.gold; font.pixelSize: 12 }
                        AppText { Layout.fillWidth: true; text: "依据："+(page.item.semantic_evidence || "—"); color: Theme.violet; font.pixelSize: 12; wrapMode: Text.Wrap; elide: Text.ElideNone }
                        AppText { Layout.fillWidth: true; text: "起止 / 结构："+(page.item.semantic_boundary || "—"); font.pixelSize: 12; wrapMode: Text.Wrap; elide: Text.ElideNone }
                        AppText { Layout.fillWidth: true; text: "来源："+(page.item.semantic_source || "—"); color: Theme.muted; font.pixelSize: 10; wrapMode: Text.Wrap; elide: Text.ElideNone }
                        TextArea { objectName: "flowRawIdentity"; Layout.fillWidth: true; text: page.item.key || ""; readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap; color: Theme.text; font.pixelSize: 11; background: Rectangle { color: Theme.raised; border.color: Theme.border; radius: 4 } }
                        DisclosureHeader { id: symbols; Layout.fillWidth: true; title: backend.translate("原始标签 / 任务及名称解释",backend.language); summary: "展开查看原始证据；静态任务的排列不是实际执行顺序" }
                        TextArea { visible: symbols.expanded; Layout.fillWidth: true; text: page.item.semantic_symbols || "未捕获标签"; readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap; color: Theme.muted; font.pixelSize: 11; background: Rectangle { color: Theme.bg; radius: 4 } }
                        AppText { Layout.fillWidth: true; text: page.item.semantic_limit || ""; color: Theme.muted; font.pixelSize: 10; wrapMode: Text.Wrap; elide: Text.ElideNone }
                    }
                }
            }
        }
    }
}
