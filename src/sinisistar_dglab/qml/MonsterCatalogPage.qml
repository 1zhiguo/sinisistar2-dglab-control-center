import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

ColumnLayout {
    id: page
    objectName: "monsterCatalogPage"
    signal openCg()
    spacing: 14
    property string selectedKey: "Zombie"
    property string selectedGroup: ""
    property int frameIndex: 0
    property bool playing: false
    function prepareToLeave(){playing=false;grid.model=null;frameStrip.model=null;}
    readonly property var summary: backend.monsterCatalogSummary
    readonly property var cacheState: backend.monsterCacheState
    readonly property var rows: backend.monsterCatalog.filter(function(r) {
        if (availability.currentIndex===1 && !r.preview) return false;
        if (availability.currentIndex===2 && r.image_count>0) return false;
        if (availability.currentIndex===3 && !r.favorite) return false;
        if (availability.currentIndex===4 && r.kind!=="part") return false;
        if (actionFilter.currentIndex>0 && !r.groups.some(function(g){return g.category===actionFilter.currentText;})) return false;
        var q=search.text.trim().toLowerCase();
        return !q || [r.name,r.key,(r.aliases || []).join(" "),(r.runtime_classes || []).join(" "),r.groups.map(function(g){return g.name;}).join(" ")].join(" ").toLowerCase().indexOf(q)>=0;
    })
    readonly property var selected: rows.find(function(r){return r.key===page.selectedKey;}) || rows[0] || ({})
    readonly property var groups: (selected.groups || []).filter(function(g){return actionFilter.currentIndex===0 || g.category===actionFilter.currentText;})
    readonly property var group: groups.find(function(g){return g.key===page.selectedGroup;}) || groups.find(function(g){return g.frames.some(function(f){return f.id===page.selected.cover;});}) || groups[0] || ({})
    readonly property var frames: group.frames || []
    readonly property var frame: frames[Math.min(frameIndex,Math.max(0,frames.length-1))] || ({})
    onSelectedChanged: { selectedGroup="";frameIndex=0;playing=false; }
    onGroupChanged: { var fs=(group || {}).frames || [];var cover=(selected || {}).cover;frameIndex=Math.max(0,fs.findIndex(function(f){return f.id===cover;}));playing=false; }
    Timer { interval: 180; running: page.playing && page.frames.length>1; repeat: true; onTriggered: page.frameIndex=(page.frameIndex+1)%page.frames.length }

    component Preview: Rectangle {
        property string picture: ""
        property bool ornament: false
        color: "#141312"; border.color: "#332c24"; radius: 3; clip: true
        Rectangle { anchors.horizontalCenter: parent.horizontalCenter; anchors.verticalCenter: parent.verticalCenter; width: Math.min(parent.width,parent.height)*.65; height: width; rotation: 45; color: "transparent"; border.color: "#29241e"; visible: ornament }
        Rectangle { anchors.horizontalCenter: parent.horizontalCenter; y: parent.height*.8; width: parent.width*.64; height: 1; color: "#30291f"; visible: ornament }
        Image { objectName: "monsterPreviewImage"; anchors.fill: parent; anchors.margins: 12; source: parent.picture; fillMode: Image.PreserveAspectFit; smooth: false; mipmap: false; asynchronous: true; cache: true; sourceSize.width: 320; sourceSize.height: 320 }
        AppText { anchors.centerIn: parent; visible: !parent.picture; text: "◇"; font.family: "Georgia"; font.pixelSize: 32; color: "#6c5a40" }
        AppText { anchors.horizontalCenter: parent.horizontalCenter; anchors.bottom: parent.bottom; anchors.bottomMargin: 10; visible: !parent.picture; text: "预览待关联"; font.pixelSize: 10; color: Theme.muted }
    }

    RowLayout { Layout.fillWidth: true; spacing: 14
        ColumnLayout { Layout.fillWidth: true; spacing: 5
            AppText { text: "B E S T I A R Y   /   怪物图鉴"; color: Theme.gold; font.pixelSize: 11; font.letterSpacing: 1 }
            AppText { Layout.fillWidth: true; text: summary.families+" 个资源分组  ·  "+summary.images+" 张登记素材  ·  "+summary.covers+" 组预览就绪"; color: Theme.muted; font.pixelSize: 11 }
        }
        AppButton { objectName: "refreshMonsterPreviews"; text: "刷新预览"; enabled: !cacheState.busy; onClicked: backend.reloadMonsterPreviews() }
        AppButton { objectName: "generateMonsterPreviews"; text: cacheState.busy ? "正在更新…" : "从游戏更新预览"; enabled: !backend.installState.busy; onClicked: backend.generateMonsterPreviews() }
    }
    RowLayout { Layout.fillWidth: true; spacing: 10
        TextField { id: search; objectName: "monsterSearch"; Layout.fillWidth: true; implicitHeight: 38; placeholderText: backend.translate(("搜索怪物名称 / 原名 / 动作，如 Zombie、守墓人、Idle"),backend.language); color: Theme.text; font.family: "Microsoft YaHei UI"; font.pixelSize: 12; selectByMouse: true; leftPadding: 12; rightPadding: 10; background: Rectangle { color: Theme.panel; border.color: search.activeFocus ? Theme.gold : Theme.border; radius: 4 } }
        AppCombo { id: availability; objectName: "monsterAvailability"; Layout.preferredWidth: 135; model: ["全部分组","有贴图预览","待关联贴图","我的收藏","部位 / 附属"] }
        AppCombo { id: actionFilter; objectName: "monsterActionFilter"; Layout.preferredWidth: 135; model: ["全部动作","待机","移动","攻击","受击","抓取 / 受制","战败相关","其他 / 部件"] }
    }
    RowLayout { Layout.fillWidth: true; spacing: 8
        AppText { text: "筛选 "+page.rows.length+" 项"; color: Theme.gold; font.pixelSize: 11 }
        Item { Layout.fillWidth: true }
        AppButton { objectName: "locateCurrentMonster"; visible: backend.currentMonster!==""; text: "定位当前抓取者"; onClicked: {search.text="";availability.currentIndex=0;actionFilter.currentIndex=0;page.selectedKey=backend.currentMonster;} }
        AppText { text: "素材分组与动作名称可供参考，数量不代表独立怪物或 CG 数量。"; color: Theme.muted; font.pixelSize: 10 }
    }
    RowLayout { Layout.fillWidth: true; Layout.fillHeight: true; spacing: 14
        Panel { Layout.fillWidth: true; Layout.fillHeight: true; color: "#191613"
            GridView { id: grid; objectName: "monsterGrid"; anchors.fill: parent; anchors.margins: 10; clip: true; model: page.rows
                cellWidth: width/Math.max(2,Math.floor(width/165)); cellHeight: 215
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar { }
                delegate: Rectangle {
                    id: card
                    required property var modelData
                    required property int index
                    objectName: "monsterCard_"+modelData.key
                    width: grid.cellWidth-10; height: grid.cellHeight-10; radius: 4
                    color: page.selected.key===modelData.key ? "#2b241c" : cardMouse.containsMouse ? "#26211b" : Theme.panel
                    border.color: page.selected.key===modelData.key ? Theme.gold : Theme.border
                    ColumnLayout { anchors.fill: parent; anchors.margins: 10; spacing: 7
                        Preview { Layout.fillWidth: true; Layout.fillHeight: true; picture: modelData.preview; ornament: true
                            Rectangle { visible: !!modelData.layered; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 5; width: 56; height: 19; radius: 2; color: "#dd1d1a17"; AppText { anchors.centerIn: parent; text: "分层部件"; font.pixelSize: 9; color: Theme.muted } }
                        }
                        AppText { Layout.fillWidth: true; text: modelData.name; font.pixelSize: 12; color: page.selected.key===modelData.key ? Theme.gold : Theme.text }
                        AppText { Layout.fillWidth: true; text: modelData.key; font.pixelSize: 10; color: Theme.muted }
                        RowLayout { Layout.fillWidth: true
                            AppText { Layout.fillWidth: true; text: (modelData.kind==="part" ? "部位 / 附属 · " : "")+(modelData.image_count ? modelData.image_count+" 张素材" : "共享引用待核对"); font.pixelSize: 10; color: Theme.muted }
                            AppText { text: modelData.favorite ? "★" : "◇"; color: modelData.favorite ? Theme.gold : Theme.border; font.pixelSize: 12 }
                        }
                    }
                    MouseArea { id: cardMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: page.selectedKey=card.modelData.key }
                }
            }
            Column { visible: page.rows.length===0; anchors.centerIn: parent; width: parent.width-60; spacing: 14
                AppText { width: parent.width; text: "◇"; horizontalAlignment: Text.AlignHCenter; font.pixelSize: 36; color: Theme.gold }
                AppText { width: parent.width; text: "没有符合筛选的怪物"; horizontalAlignment: Text.AlignHCenter; color: Theme.text }
                AppText { width: parent.width; text: "试试其他名称，或清除筛选条件。"; horizontalAlignment: Text.AlignHCenter; color: Theme.muted; font.pixelSize: 11 }
            }
        }
        Panel { Layout.preferredWidth: 338; Layout.fillHeight: true
            ScrollView { id: details; anchors.fill: parent; anchors.margins: 16; clip: true; contentWidth: availableWidth
                ColumnLayout { width: details.availableWidth; spacing: 10; visible: !!page.selected.key
                    RowLayout { Layout.fillWidth: true
                        ColumnLayout { Layout.fillWidth: true; spacing: 4
                            AppText { Layout.fillWidth: true; text: page.selected.name || ""; font.pixelSize: 21; color: Theme.gold }
                            AppText { Layout.fillWidth: true; text: page.selected.key || ""; font.pixelSize: 11; color: Theme.muted }
                        }
                        AppButton { objectName: "favoriteMonster"; implicitWidth: 86; text: page.selected.favorite ? "★ 已收藏" : "☆ 收藏"; onClicked: backend.toggleMonsterFavorite(page.selected.key) }
                    }
                    AppText { visible: page.selected.key===backend.currentMonster; text: "◆ 当前抓取者 · 名称匹配"; color: Theme.violet; font.pixelSize: 11 }
                    Preview { objectName: "selectedMonsterPreview"; Layout.fillWidth: true; Layout.preferredHeight: 175; picture: page.frame.url || ""; ornament: true }
                    RowLayout { Layout.fillWidth: true
                        AppText { Layout.fillWidth: true; text: page.frame.width ? page.frame.width+" × "+page.frame.height+"  /  原始单帧尺寸" : "本地素材预览"; font.pixelSize: 10; color: Theme.muted }
                        AppButton { objectName: "monsterSlideshow"; text: page.playing ? "暂停轮播" : "素材轮播"; enabled: page.frames.length>1 && !!page.frame.url; onClicked: page.playing=!page.playing }
                    }
                    AppText { Layout.fillWidth: true; text: page.selected.image_count ? "原始像素素材，可能包含分层部件；轮播速度仅用于浏览。" : "此分组没有独立图片条目，需进一步关联共用贴图。"; font.pixelSize: 10; color: Theme.muted; wrapMode: Text.Wrap; elide: Text.ElideNone }
                    Rectangle { Layout.fillWidth: true; height: 1; color: Theme.border }
                    RowLayout { Layout.fillWidth: true
                        AppText { text: "动作素材"; font.pixelSize: 13; color: Theme.gold }
                        Item { Layout.fillWidth: true }
                        AppText { text: page.selected.image_count+" 张 · "+(page.selected.groups || []).length+" 组"; font.pixelSize: 10; color: Theme.muted }
                    }
                    AppCombo { id: groupChoice; objectName: "monsterGroupChoice"; Layout.fillWidth: true; visible: page.groups.length>0; model: page.groups.map(function(g){return g.name+" · "+g.frames.length+" 张";}); function sync(){currentIndex=Math.max(0,page.groups.findIndex(function(g){return g.key===page.group.key;}));} onModelChanged: Qt.callLater(sync); onActivated: page.selectedGroup=page.groups[currentIndex].key }
                    Connections { target: page; function onGroupChanged(){groupChoice.sync();} }
                    AppText { Layout.fillWidth: true; visible: page.groups.length>0; text: (page.group.category || "")+"  ·  "+(page.frameIndex+1)+" / "+page.frames.length; font.pixelSize: 11; color: Theme.violet }
                    ListView { id: frameStrip; objectName: "monsterFrameStrip"; Layout.fillWidth: true; Layout.preferredHeight: page.frames.length ? 65 : 0; clip: true; orientation: ListView.Horizontal; spacing: 6; model: page.frames
                        ScrollBar.horizontal: ScrollBar { }
                        delegate: Rectangle {
                            required property var modelData
                            required property int index
                            width: 53; height: 53; color: Theme.bg; border.color: page.frameIndex===index ? Theme.gold : Theme.border; radius: 3
                            Image { anchors.fill: parent; anchors.margins: 5; source: modelData.url || ""; fillMode: Image.PreserveAspectFit; smooth: false; asynchronous: true; sourceSize.width: 64; sourceSize.height: 64 }
                            MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: {page.playing=false;page.frameIndex=parent.index;} }
                        }
                    }
                    AppText { Layout.fillWidth: true; text: page.frame.name || ""; font.pixelSize: 10; color: Theme.text; wrapMode: Text.Wrap; elide: Text.ElideNone }
                    DisclosureHeader { id: sources; objectName: "monsterSourceDetails"; Layout.fillWidth: true; title: backend.translate("资源来源与说明",backend.language); summary: "展开资源路径与目录信息" }
                    ColumnLayout { visible: sources.expanded; Layout.fillWidth: true; spacing: 8
                        AppText { visible: !!page.selected.scene_embedded; Layout.fillWidth: true; text: "含场景包中的敌人渲染器或动画引用素材；整理路径保留场景来源，不作为 Enemy 表中的原始文件路径。"; color: Theme.violet; font.pixelSize: 10; wrapMode: Text.Wrap; elide: Text.ElideNone }
                        AppText { visible: !!page.selected.runtime_classes; Layout.fillWidth: true; text: "敌人组件："+(page.selected.runtime_classes || []).join(" / "); color: Theme.muted; font.pixelSize: 10; wrapMode: Text.Wrap; elide: Text.ElideNone }
                        TextArea { Layout.fillWidth: true; text: page.frame.path || ("Design/Character/Enemy/"+(page.selected.key || "")+"/"); readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap; color: Theme.muted; font.pixelSize: 10; background: Rectangle { color: Theme.bg; radius: 3 } }
                        AppText { Layout.fillWidth: true; text: "游戏版本 "+summary.version+"。中文为工作译名，保留资源原名供对照；动作分类依据文件命名，不代表已实测的 CG 阶段。"; color: Theme.muted; font.pixelSize: 10; wrapMode: Text.Wrap; elide: Text.ElideNone }
                    }
                    Rectangle { Layout.fillWidth: true; height: 1; color: Theme.border }
                    AppButton { objectName: "monsterOpenCg"; Layout.fillWidth: true; text: "打开通用 CG 反馈"; onClicked: page.openCg() }
                    AppText { Layout.fillWidth: true; text: "当前使用通用联动策略；浏览和收藏不会修改设备输出。"; font.pixelSize: 10; color: Theme.muted; wrapMode: Text.Wrap; elide: Text.ElideNone }
                }
            }
        }
    }
    AppText { Layout.fillWidth: true; text: cacheState.busy ? cacheState.message : cacheState.error ? "预览更新失败："+cacheState.error : summary.bundled_previews ? "随包预览已就绪 · 无需等待提取，可按需从本地游戏更新。" : summary.previews ? "本地预览已就绪。" : "在「设备与游戏」选择游戏目录后自动生成本地图鉴。"; color: cacheState.error ? Theme.red : Theme.muted; font.pixelSize: 10; wrapMode: Text.Wrap; elide: Text.ElideNone }
}
