import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Panel { id: preview; readonly property var plan: backend.simulation; Layout.fillWidth: true; Layout.preferredHeight: previewFrame.implicitHeight+24
        ColumnLayout { id: previewFrame; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 12; spacing: 10
            DisclosureHeader { id: previewHeader; objectName: "policyPreviewDisclosure"; Layout.fillWidth: true; title: backend.translate("曲线预览（不发送）",backend.language); summary: preview.plan.running ? preview.plan.reason : "展开后选择实时数据或样例，查看四路曲线" }
            ColumnLayout { visible: previewHeader.expanded; Layout.fillWidth: true; spacing: 10
            RowLayout { Layout.fillWidth: true
                ColumnLayout { spacing: 4
                    AppText { text: "波形预览 · "+preview.plan.source; color: Theme.gold; font.pixelSize: 18 }
                    AppText { text: preview.plan.reason+"  /  参与状态 "+preview.plan.abnormal_count+" 项"; color: Theme.muted; font.pixelSize: 11 }
                }
                Item { Layout.fillWidth: true }
                AppCombo { objectName: "simulationSampleChoice"; implicitWidth: 190; model: ["实时游戏","样例 · 抓取掉 HP","样例 · 多异常叠加","样例 · 演出阶段"]; currentIndex: ["live","grab_hp","abnormals","flow"].indexOf(preview.plan.mode); onActivated: backend.simulationSource(["live","grab_hp","abnormals","flow"][currentIndex]) }
                AppButton { objectName: "toggleSimulationPreview"; text: preview.plan.running ? "暂停曲线预览" : "开始曲线预览"; primary: true; onClicked: backend.toggleSimulation() }
            }
            RowLayout { Layout.fillWidth: true; Layout.preferredHeight: 128; spacing: 18
                Repeater { model: ["pulseA","pulseB","vibrationA","vibrationB"]
                    ColumnLayout { required property string modelData; Layout.fillWidth: true; spacing: 5
                        AppText { text: (modelData.indexOf("pulse")===0 ? "Pulse " : "震动 ")+modelData.slice(-1)+"  "+Number(preview.plan[modelData]).toFixed(1); color: modelData.indexOf("pulse")===0 ? Theme.gold : Theme.violet; font.pixelSize: 13 }
                        WavePlot { Layout.fillWidth: true; Layout.fillHeight: true; points: preview.plan.traces[modelData]; lineColor: modelData.indexOf("pulse")===0 ? Theme.gold : Theme.violet }
                        AppText { text: "计划上限 "+Number(preview.plan.peaks[modelData] || 0).toFixed(1); color: Theme.muted; font.pixelSize: 10 }
                        AppText { Layout.fillWidth: true; text: "来源："+(preview.plan.selected[modelData] || []).join(" + "); color: Theme.muted; font.pixelSize: 10 }
                    }
                }
            }
            }
        }
    }
