import QtQuick
import QtQuick.Layouts

Rectangle {
    id: guide; objectName: "tutorialDialog"
    visible: false; implicitHeight: 156; height: implicitHeight
    color: Theme.panel; border.color: Theme.border; radius: 6
    property int step: 0
    readonly property var current: backend.tutorialSteps[step] || ({title:"",body:"",page:1})
    readonly property bool lastStep: step===backend.tutorialSteps.length-1
    signal navigate(int page)
    function showStep() {
        navigate(backend.tutorialSteps[step].page);
        backend.saveTutorial(step,false);
    }
    function open() {
        step=backend.tutorialState.completed ? 0 : backend.tutorialState.step;
        visible=true;showStep();
    }
    function close() {backend.saveTutorial(step,false);visible=false;}
    onStepChanged: if(visible)showStep()
    RowLayout { anchors.fill: parent; anchors.margins: 18; spacing: 22
        ColumnLayout { Layout.fillWidth: true; Layout.fillHeight: true; spacing: 7
            AppText { text: "新手教程"+"  ·  "+(guide.step+1)+" / "+backend.tutorialSteps.length; color: Theme.muted; font.pixelSize: 11 }
            AppText { objectName: "tutorialTitle"; Layout.fillWidth: true; text: guide.current.title; color: Theme.gold; font.pixelSize: 19; wrapMode: Text.Wrap; elide: Text.ElideNone }
            AppText { objectName: "tutorialBody"; Layout.fillWidth: true; Layout.fillHeight: true; text: guide.current.body; color: Theme.text; font.pixelSize: 12; wrapMode: Text.Wrap; elide: Text.ElideNone }
        }
        ColumnLayout { Layout.preferredWidth: 224; Layout.fillHeight: true; spacing: 8
            AppButton { objectName: "tutorialClose"; text: "×"; implicitWidth: 28; implicitHeight: 25; Layout.alignment: Qt.AlignRight; onClicked: guide.close() }
            Item { Layout.fillHeight: true }
            AppButton { objectName: "tutorialHudSettings"; visible: guide.lastStep; Layout.fillWidth: true; implicitHeight: 32; text: "调整 HUD 位置"; onClicked: backend.openHudSettings() }
            RowLayout { Layout.fillWidth: true; spacing: 8
                AppButton { objectName: "tutorialPrevious"; text: "上一步"; Layout.fillWidth: true; implicitWidth: 100; enabled: guide.step>0; onClicked: guide.step-- }
                AppButton { objectName: "tutorialNext"; text: guide.lastStep ? "完成教程" : "下一步"; Layout.fillWidth: true; implicitWidth: 110; primary: true; onClicked: {if(guide.lastStep){backend.saveTutorial(guide.step,true);guide.close();}else guide.step++;} }
            }
        }
    }
}
