pragma Singleton
import QtQuick
QtObject {
    id: theme
    // Decoration uses one 30Hz clock, not an animation on every display frame.
    // Gameplay telemetry and device clocks do not depend on this timer.
    property real motionTime: 0
    property Timer motionClock: Timer {
        interval: 33; repeat: true; running: Qt.application.state===Qt.ApplicationActive
        onTriggered: theme.motionTime+=.033
    }
    readonly property color bg: "#11100f"
    readonly property color sidebar: "#161412"
    readonly property color panel: "#1d1a17"
    readonly property color raised: "#27221d"
    readonly property color border: "#3b3329"
    readonly property color text: "#eee7da"
    readonly property color muted: "#978e80"
    readonly property color gold: "#c3a777"
    readonly property color silver: "#d1cbdc"
    readonly property color crimson: "#d66670"
    readonly property color violet: "#a69abb"
    readonly property color red: "#cc7f7a"
    readonly property color green: "#a5b595"
}
