import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

ScrollView {
    id: page
    objectName: "cgFeedbackPage"
    clip: true; contentWidth: availableWidth
    property string scope: "cg"
    readonly property bool gallery: scope==="gallery"
    readonly property string prefix: gallery ? "gallery/" : ""
    readonly property var config: gallery ? backend.gallerySettings : backend.cgSettings
    ColumnLayout { width: page.availableWidth; spacing: 16
        RowLayout { objectName: "tutorialCgTabs"; Layout.fillWidth: true; spacing: 10
            AppButton { objectName: "cgGameTab"; Layout.fillWidth: true; text: "游戏 CG / 互动"; primary: !page.gallery; onClicked: page.scope="cg" }
            AppButton { objectName: "cgGalleryTab"; Layout.fillWidth: true; text: "图鉴独立反馈"; primary: page.gallery; onClicked: page.scope="gallery" }
        }
        Panel { Layout.fillWidth: true; Layout.preferredHeight: header.implicitHeight+32
            ColumnLayout { id: header; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 16; spacing: 11
                RowLayout { Layout.fillWidth: true
                    AppText { text: page.gallery ? "图鉴回放反馈" : "CG 观看反馈"; color: Theme.gold; font.pixelSize: 22; Layout.fillWidth: true }
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
                AppText { Layout.fillWidth: true; text: "切换 [1]/[2]/[3]：等待新片段载入后重置队列与渐强。返回图鉴列表或预览页立即停止；暂支持已验证的 EventPlayer 回放。游戏暂停、加载、失联与急停仍停止输出。"; color: Theme.muted; font.pixelSize: 10; wrapMode: Text.Wrap; elide: Text.ElideNone }
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
                AppText { Layout.fillWidth: true; text: "两次独立通知确认，至少间隔 0.2 秒。演出结束立即停止；若仍停留对话，则在断流超时后停止。默认关闭，启用或调整会暂停设备输出。"; color: Theme.muted; font.pixelSize: 10; wrapMode: Text.Wrap; elide: Text.ElideNone }
            }
        }
        RowLayout { Layout.fillWidth: true; spacing: 16; Layout.alignment: Qt.AlignTop
            CgRouteEditor { scope: page.scope; route: "pulse"; Layout.alignment: Qt.AlignTop }
            CgRouteEditor { scope: page.scope; route: "vibration"; Layout.alignment: Qt.AlignTop }
        }
        AppText { Layout.fillWidth: true; text: page.gallery ? "图鉴反馈默认关闭。启用本规则后仍需启用设备输出；强度受全局、通道及 APP 上限约束。" : "适用于已识别的 GO 场景、战败演出与 1 HP 锁血互动。检测逻辑保持不变，暂停、加载、失联与急停仍归零；强度受全局、通道及 APP 上限约束。"; color: Theme.muted; font.pixelSize: 11; wrapMode: Text.Wrap; elide: Text.ElideNone }
    }
}
