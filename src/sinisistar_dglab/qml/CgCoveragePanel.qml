import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

ColumnLayout {
    id: panel
    readonly property var rows: backend.cgCoverage
    readonly property var filtered: rows.filter(function(r){
        var q=search.text.trim().toLowerCase();
        return (!q || [r.name,r.kind,r.scenes,r.detail].join(" ").toLowerCase().indexOf(q)>=0)
            && (filter.currentIndex===0 || filter.currentIndex===1 && r.stage==="未测试" || filter.currentIndex===2 && r.stage!=="未测试" || filter.currentIndex===3 && r.game==="实战待验证");
    })
    spacing: 12
    Panel { Layout.fillWidth: true; Layout.preferredHeight: intro.implicitHeight+28
        ColumnLayout { id: intro; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 14; spacing: 10
            AppText { text: "CG 覆盖检查"; color: Theme.gold; font.pixelSize: 21 }
            AppText { Layout.fillWidth: true; text: "目录引用 → 播放识别 → 生成波形 → 控制中心发送。图鉴与实战分别记录；发送记录不代表实体体感已验证。"; color: Theme.muted; wrapMode: Text.Wrap; elide: Text.ElideNone; font.pixelSize: 11 }
            AppText { Layout.fillWidth: true; text: "片段配置 "+panel.rows.length+" · 已识别 "+panel.rows.filter(r=>r.stage!=="未测试" && r.stage!=="已选择 · 未确认").length+" · 有发送记录 "+panel.rows.filter(r=>r.stage==="已发送").length; color: Theme.silver; font.pixelSize: 12 }
            RowLayout { Layout.fillWidth: true
                AppButton { objectName: "cgCoverageStartMock"; text: "连接模拟 APP"; onClicked: backend.startMockBoth() }
                AppButton { objectName: "cgCoverageExport"; text: "导出覆盖报告"; onClicked: backend.exportCgCoverage() }
                Item { Layout.fillWidth: true }
                AppButton { objectName: "cgCoverageClear"; text: "清空本轮记录"; onClicked: backend.clearCgCoverage() }
            }
        }
    }
    RowLayout { Layout.fillWidth: true
        TextField { id: search; objectName: "cgCoverageSearch"; Layout.fillWidth: true; placeholderText: backend.translate("搜索片段、场景或未触发原因",backend.language); color: Theme.text; font.pixelSize: 12; background: Rectangle { color: Theme.raised; border.color: Theme.border; radius: 4 } }
        AppCombo { id: filter; objectName: "cgCoverageFilter"; Layout.preferredWidth: 160; model: ["全部片段","未测试","已观察","实战待验证"] }
    }
    Panel { Layout.fillWidth: true; Layout.preferredHeight: 580
        ListView { id: list; objectName: "cgCoverageList"; anchors.fill: parent; anchors.margins: 10; clip: true; spacing: 8; model: panel.filtered
            delegate: Rectangle {
                required property var modelData
                width: ListView.view.width; height: row.implicitHeight+24; color: Theme.raised; radius: 4; border.color: Theme.border
                ColumnLayout { id: row; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 12; spacing: 5
                    RowLayout { Layout.fillWidth: true
                        AppText { text: modelData.name; Layout.fillWidth: true; color: Theme.silver; font.pixelSize: 14 }
                        AppText { text: modelData.kind; color: Theme.muted; font.pixelSize: 11 }
                        AppText { text: modelData.stage; color: modelData.stage==="已发送" ? Theme.green : Theme.gold; font.pixelSize: 12 }
                    }
                    AppText { Layout.fillWidth: true; text: modelData.scenes+" · "+modelData.mapping+" · "+modelData.gallery+" · "+modelData.game; color: Theme.muted; font.pixelSize: 10 }
                    AppText { visible: modelData.channels!==""; Layout.fillWidth: true; text: modelData.channels; color: Theme.violet; font.pixelSize: 10 }
                    AppText { visible: modelData.detail!==""; Layout.fillWidth: true; text: modelData.detail; color: Theme.muted; font.pixelSize: 10; wrapMode: Text.Wrap; elide: Text.ElideNone; maximumLineCount: 3 }
                }
            }
            ScrollBar.vertical: ScrollBar {}
        }
    }
}
