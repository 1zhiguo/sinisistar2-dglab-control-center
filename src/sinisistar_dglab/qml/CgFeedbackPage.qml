import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

ScrollView {
    id: page
    objectName: "cgFeedbackPage"
    clip: true; contentWidth: availableWidth
    property string scope: "cg"
    readonly property bool gallery: scope==="gallery"
    readonly property bool coverage: scope==="coverage"
    readonly property bool batch: scope==="batch"
    function prepareToLeave(){if(batchLoader.item)batchLoader.item.flushNote();}
    readonly property string prefix: gallery ? "gallery/" : ""
    readonly property var config: gallery ? backend.gallerySettings : backend.cgSettings
    ColumnLayout { width: page.availableWidth; spacing: 16
        RowLayout { objectName: "tutorialCgTabs"; Layout.fillWidth: true; spacing: 10
            AppButton { objectName: "cgGameTab"; Layout.fillWidth: true; text: "游戏 CG / 互动"; primary: page.scope==="cg"; onClicked: page.scope="cg" }
            AppButton { objectName: "cgGalleryTab"; Layout.fillWidth: true; text: "图鉴独立反馈"; primary: page.gallery; onClicked: page.scope="gallery" }
            AppButton { visible: backend.developerTools; objectName: "cgBatchTab"; Layout.fillWidth: true; text: "批量测试"; primary: page.batch; onClicked: page.scope="batch" }
            AppButton { visible: backend.developerTools; objectName: "cgCoverageTab"; Layout.fillWidth: true; text: "参考目录"; primary: page.coverage; onClicked: page.scope="coverage" }
        }
        Panel { visible: backend.developerTools && !page.batch; Layout.fillWidth: true; Layout.preferredHeight: detection.implicitHeight+28
            ColumnLayout { id: detection; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 14; spacing: 8
                RowLayout { Layout.fillWidth: true
                    AppText { text: "CG 识别模式"; color: Theme.silver; font.pixelSize: 14 }
                    AppCombo { objectName: "cgDetectionMode"; Layout.fillWidth: true; model: ["正常 · CG 播放信号 + HP 兜底","消融测试 · 仅 CG 播放信号（无 HP）"]; currentIndex: backend.simulationSettings.cg_detection_mode==="playback_only" ? 1 : 0; onActivated: backend.setCgDetectionMode(currentIndex===1 ? "playback_only" : "hybrid") }
                }
                AppText { Layout.fillWidth: true; text: backend.simulationSettings.cg_detection_mode==="playback_only" ? "仅使用 CG 播放信号：优先核对共享 Animator 与动画状态，并要求有效演出上下文。HP、抓取和异常兜底均不参与。修改模式会暂停输出。" : "优先识别共享动画和已知演出；未匹配时保留原有 HP 与互动规则。图鉴始终使用独立播放信号。"; color: Theme.muted; font.pixelSize: 11; wrapMode: Text.Wrap; elide: Text.ElideNone }
                AppText { Layout.fillWidth: true; text: backend.state.cgPlayback.recognized ? "当前 CG："+backend.state.cgPlayback.name+" · "+(backend.state.cgPlayback.kind==="SharedAnimator" ? "共享动画" : backend.state.cgPlayback.kind)+" · 无 HP" : backend.state.galleryPlayback.inGallery ? backend.state.galleryPlayback.label : backend.state.cgPlayback.reason || "等待 CG 观察插件"; color: Theme.gold; font.pixelSize: 11 }
            }
        }
        Loader { active: page.coverage; visible: active; Layout.fillWidth: true; sourceComponent: Component { CgCoveragePanel {} } }
        Loader { id: batchLoader; active: page.batch; visible: active; Layout.fillWidth: true; sourceComponent: Component { CgBatchPanel {} } }
        Loader { active: !page.coverage && !page.batch; visible: active; asynchronous: true; Layout.fillWidth: true
        sourceComponent: Component { ColumnLayout { spacing: 16
        Panel { Layout.fillWidth: true; Layout.preferredHeight: header.implicitHeight+32
            ColumnLayout { id: header; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 16; spacing: 11
                RowLayout { Layout.fillWidth: true
                    AppText { text: page.gallery ? "图鉴回放反馈" : "CG 观看反馈"; color: Theme.gold; font.pixelSize: 22; Layout.fillWidth: true }
                    AppButton { objectName: "syncCgFeedback"; text: page.gallery ? "同步到游戏 CG" : "同步到图鉴反馈"; onClicked: backend.syncCgFeedback(page.scope)
                        ToolTip.visible: hovered
                        ToolTip.text: backend.translate("复制两种设备的 A/B 强度、波形、循环队列与渐强；保留目标页总开关、触发和暂停规则。同步后暂停输出并自动保存。",backend.language)
                    }
                    AppText { text: "总开关"; color: Theme.muted; font.pixelSize: 11 }
                    AppSwitch { objectName: "cgMasterEnabled"; checked: page.config.rule.enabled; onToggled: backend.setCgRule(page.prefix+"enabled",checked) }
                }
                AppText { Layout.fillWidth: true; text: page.gallery ? "强度随低／中／高预设同步，手动调整后为自定义。图鉴与游戏 CG 独立保存 A/B 波形、队列与渐强速度。" : page.config.inherit_death ? "强度沿用死亡惩罚；A/B 已各自提供不同的 60 秒循环。修改后独立保存。" : "强度随低／中／高预设同步，手动调整后为自定义。A/B 各自设置波形、循环队列、随机与渐强速度。"; color: Theme.violet; font.pixelSize: 11; wrapMode: Text.Wrap; elide: Text.ElideNone }
                RowLayout { visible: !page.gallery; Layout.fillWidth: true
                    AppText { text: "结束方式"; color: Theme.muted; font.pixelSize: 11 }
                    AppCombo { objectName: "cgEndMode"; Layout.fillWidth: true; model: ["持续到 CG / 互动结束或复活","固定反馈时长"]; currentIndex: page.config.rule.death_mode==="timed" ? 1 : 0; onActivated: backend.setCgRule("death_mode",currentIndex===1 ? "timed" : "until_end") }
                    CgNumber { objectName: "cgEndSeconds"; visible: page.config.rule.death_mode==="timed"; amount: page.config.rule.death_seconds; minimum: .1; maximum: 120; onEdited: amount=>backend.setCgRule("death_seconds",amount) }
                    AppText { visible: page.config.rule.death_mode==="timed"; text: "秒"; color: Theme.muted; font.pixelSize: 11 }
                    AppButton { objectName: "cgCopyDeath"; text: "复制当前死亡参数"; onClicked: backend.copyDeathToCg() }
                }
                AppText { Layout.fillWidth: true; text: "当前识别："+(page.gallery ? backend.state.galleryPlayback.label : backend.state.nonDamageLabel || backend.state.penaltyLabel || "等待 CG / 锁血互动")+"。修改设置会暂停两路输出，重新启用后从新策略开始。"; color: Theme.muted; font.pixelSize: 11; wrapMode: Text.Wrap; elide: Text.ElideNone }
                AppText { Layout.fillWidth: true; text: "默认循环已就绪：每轮 60 秒、五段各 12 秒，比例 35 → 50 → 65 → 80 → 100%。A/B 波形错开，可分别修改。"; color: Theme.muted; font.pixelSize: 10; wrapMode: Text.Wrap; elide: Text.ElideNone }
            }
        }
        Panel { visible: page.gallery; Layout.fillWidth: true; Layout.preferredHeight: galleryBody.implicitHeight+28
            ColumnLayout { id: galleryBody; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 14; spacing: 10
                RowLayout { Layout.fillWidth: true
                    AppText { text: "Space 暂停时停止输出"; color: Theme.silver; font.pixelSize: 16; Layout.fillWidth: true }
                    AppSwitch { objectName: "galleryPauseOnStop"; accent: Theme.gold; checked: !!page.config.pause_on_stop; onToggled: backend.setGalleryPauseOnStop(checked) }
                }
                AppText { Layout.fillWidth: true; text: page.config.pause_on_stop ? "开启：按 Space 停止输出并冻结队列与渐强进度，恢复后继续。演出内部等待仍持续反馈。" : "关闭：按 Space 暂停图鉴画面时仍继续输出，队列与渐强照常推进。"; color: Theme.muted; font.pixelSize: 11; wrapMode: Text.Wrap; elide: Text.ElideNone }
                AppText { Layout.fillWidth: true; text: "切换 [1]/[2]/[3]：等待新片段载入后重置队列与渐强。返回列表或预览页立即停止。支持演出、声明动画和有效片段会话；游戏暂停、加载、失联与急停仍停止输出。"; color: Theme.muted; font.pixelSize: 10; wrapMode: Text.Wrap; elide: Text.ElideNone }
            }
        }
        Panel { visible: !page.gallery; Layout.fillWidth: true; Layout.preferredHeight: sameHpBody.implicitHeight+28
            ColumnLayout { id: sameHpBody; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 14; spacing: 10
                RowLayout { Layout.fillWidth: true
                    AppText { text: "同值 HP 演出反馈 · 泛用规则"; color: Theme.silver; font.pixelSize: 17; Layout.fillWidth: true }
                    AppSwitch { objectName: "cgSameHpEnabled"; accent: Theme.silver; checked: !!page.config.same_hp_enabled; onToggled: backend.setSameHpFeedbackEnabled(checked) }
                }
                AppText { Layout.fillWidth: true; text: "正在播放演出，且重复收到 HP 前后相同的伤害通知时，沿用下方 CG 波形、A/B 与渐强策略。普通快照 HP 不变、演出外使用技能和历史记录不触发。"; color: Theme.muted; font.pixelSize: 11; wrapMode: Text.Wrap; elide: Text.ElideNone }
                RowLayout { Layout.fillWidth: true
                    AppText { Layout.fillWidth: true; text: "同类回调停止后结束反馈"; color: Theme.muted; font.pixelSize: 11 }
                    CgNumber { objectName: "cgSameHpTimeout"; amount: page.config.same_hp_timeout; minimum: .5; maximum: 30; onEdited: amount=>backend.setSameHpTimeout(amount) }
                    AppText { text: "秒"; color: Theme.silver; font.pixelSize: 11 }
                }
                AppText { Layout.fillWidth: true; text: "两次独立通知确认，至少间隔 0.2 秒。演出结束立即停止；若仍停留对话，则在断流超时后停止。默认开启，启用或调整会暂停设备输出。"; color: Theme.muted; font.pixelSize: 10; wrapMode: Text.Wrap; elide: Text.ElideNone }
            }
        }
        RowLayout { Layout.fillWidth: true; spacing: 16; Layout.alignment: Qt.AlignTop
            CgRouteEditor { scope: page.scope; route: "pulse"; Layout.alignment: Qt.AlignTop }
            CgRouteEditor { scope: page.scope; route: "vibration"; Layout.alignment: Qt.AlignTop }
        }
        AppText { Layout.fillWidth: true; text: page.gallery ? "图鉴反馈默认开启，设备输出仍需单独启用；强度受全局、通道及 APP 上限约束。" : "适用于已识别的 CG 播放；正常模式保留 GO、锁血和同值 HP 兜底。暂停、加载、失联与急停仍归零。"; color: Theme.muted; font.pixelSize: 11; wrapMode: Text.Wrap; elide: Text.ElideNone }
        }
        } }
    }
}
