import QtQuick
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.plasma.components as PlasmaComponents3
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.plasmoid

PlasmoidItem {
    id: root

    property var usageData: null
    property var accountData: null
    property var buckets: []
    property string sessionId: ""
    property string errorText: ""
    property string warningText: ""
    property bool loading: true
    property bool reconnecting: false
    property int reconnectAttempts: 0
    property date updatedAt: new Date(0)
    readonly property int refreshIntervalSeconds: Math.max(
        5, Number(Plasmoid.configuration.refreshInterval) || 30
    )
    readonly property int compactHorizontalPadding: Math.max(
        0, Math.min(32, Number(Plasmoid.configuration.compactHorizontalPadding))
    )
    readonly property int compactVerticalPadding: Math.max(
        0, Math.min(16, Number(Plasmoid.configuration.compactVerticalPadding))
    )
    readonly property var primaryWindow: usageData && usageData.rateLimits
                                         ? usageData.rateLimits.primary : null
    readonly property int primaryRemaining: primaryWindow
                                            ? Math.max(0, 100 - primaryWindow.usedPercent) : -1

    Plasmoid.title: i18n("Codex 用量")
    Plasmoid.icon: "io.github.codexdesktoplinux.usagemonitor"
    toolTipMainText: i18n("Codex 用量")
    toolTipSubText: reconnecting ? i18n("正在重新连接当前账号…")
                    : errorText.length > 0 ? errorText
                    : warningText.length > 0 ? i18n("暂时无法更新，显示上次成功数据")
                    : primaryRemaining >= 0 ? i18n("主要窗口剩余 %1%", primaryRemaining)
                    : i18n("正在读取…")
    preferredRepresentation: compactRepresentation

    Plasmoid.contextualActions: [
        PlasmaCore.Action {
            text: i18n("立即更新")
            icon.name: "view-refresh"
            enabled: !root.reconnecting
            onTriggered: root.forceRefresh()
        }
    ]

    function durationText(minutes) {
        if (minutes === null || minutes === undefined)
            return i18n("用量窗口")
        if (minutes >= 1440)
            return i18n("%1 天窗口", Math.ceil(minutes / 1440))
        if (minutes >= 60)
            return i18n("%1 小时窗口", Math.ceil(minutes / 60))
        return i18n("%1 分钟窗口", Math.ceil(minutes))
    }

    function resetText(seconds) {
        if (!seconds)
            return i18n("重置时间未知")
        return i18n("重置：%1", new Date(seconds * 1000).toLocaleString(Qt.locale(), Locale.ShortFormat))
    }

    function rebuildBuckets(result) {
        var values = []
        var byId = result.rateLimitsByLimitId
        if (byId) {
            var ids = Object.keys(byId).sort()
            for (var i = 0; i < ids.length; ++i) {
                var item = byId[ids[i]]
                values.push({
                    id: ids[i], name: item.limitName || ids[i], plan: item.planType || "",
                    primary: item.primary || null, secondary: item.secondary || null
                })
            }
        }
        if (values.length === 0 && result.rateLimits) {
            values.push({
                id: result.rateLimits.limitId || "codex",
                name: result.rateLimits.limitName || "Codex",
                plan: result.rateLimits.planType || "",
                primary: result.rateLimits.primary || null,
                secondary: result.rateLimits.secondary || null
            })
        }
        buckets = values
    }

    function accountTypeText(type) {
        if (type === "chatgpt") return i18n("ChatGPT 登录")
        if (type === "apiKey") return i18n("API Key 登录")
        if (type === "amazonBedrock") return i18n("Amazon Bedrock")
        return i18n("登录方式未知")
    }

    function forceRefresh() {
        reconnecting = true
        reconnectAttempts = 0
        loading = true
        accountData = null
        usageData = null
        buckets = []
        errorText = ""
        warningText = ""
        var request = new XMLHttpRequest()
        request.open("POST", "http://127.0.0.1:9000/api/refresh")
        request.timeout = 5000
        request.onreadystatechange = function() {
            if (request.readyState !== XMLHttpRequest.DONE)
                return
            if (request.status === 200) {
                reconnectTimer.start()
            } else {
                reconnecting = false
                loading = false
                errorText = i18n("无法请求重新连接用量服务")
            }
        }
        request.ontimeout = function() {
            reconnecting = false
            loading = false
            errorText = i18n("重新连接请求超时")
        }
        request.onerror = function() {
            reconnecting = false
            loading = false
            errorText = i18n("无法连接本地用量服务")
        }
        request.send()
    }

    function refresh() {
        loading = true
        var request = new XMLHttpRequest()
        request.open("GET", "http://127.0.0.1:9000/api/usage")
        request.timeout = 5000
        request.onreadystatechange = function() {
            if (request.readyState !== XMLHttpRequest.DONE)
                return
            loading = false
            if (request.status !== 200) {
                if (root.reconnecting) return
                errorText = i18n("用量服务不可用（HTTP %1）", request.status)
                return
            }
            try {
                var payload = JSON.parse(request.responseText)
                if (root.reconnecting && (!payload.sessionId || payload.sessionId === root.sessionId))
                    return
                accountData = payload.account || null
                if (payload.error && !payload.data)
                    throw new Error(payload.error)
                if (!payload.data || !payload.data.rateLimits)
                    throw new Error(i18n("响应中没有用量数据"))
                usageData = payload.data
                rebuildBuckets(payload.data)
                errorText = ""
                warningText = payload.warning || payload.error || ""
                updatedAt = payload.updatedAt ? new Date(payload.updatedAt * 1000) : new Date()
                sessionId = payload.sessionId || ""
                reconnecting = false
                reconnectTimer.stop()
            } catch (error) {
                usageData = null
                buckets = []
                errorText = error.message || String(error)
                warningText = ""
            }
        }
        request.ontimeout = function() { loading = false; if (!root.reconnecting) errorText = i18n("读取用量超时") }
        request.onerror = function() { loading = false; if (!root.reconnecting) errorText = i18n("无法连接本地用量服务") }
        request.send()
    }

    Timer {
        id: reconnectTimer
        interval: 1200
        repeat: true
        onTriggered: {
            if (++root.reconnectAttempts > 20) {
                stop()
                root.reconnecting = false
                root.loading = false
                if (!root.errorText.length)
                    root.errorText = i18n("重新连接用量服务超时")
            } else {
                root.refresh()
            }
        }
    }

    Timer {
        interval: root.refreshIntervalSeconds * 1000
        repeat: true
        running: true
        triggeredOnStart: true
        onTriggered: root.refresh()
    }

    compactRepresentation: MouseArea {
        implicitWidth: compactRow.implicitWidth + root.compactHorizontalPadding * 2
        implicitHeight: compactRow.implicitHeight + root.compactVerticalPadding * 2
        Layout.minimumWidth: implicitWidth
        Layout.preferredWidth: implicitWidth
        Layout.minimumHeight: implicitHeight
        Layout.preferredHeight: implicitHeight
        onClicked: root.expanded = !root.expanded

        RowLayout {
            id: compactRow
            anchors.centerIn: parent
            spacing: Kirigami.Units.smallSpacing
            Kirigami.Icon {
                source: "io.github.codexdesktoplinux.usagemonitor"
                implicitWidth: Kirigami.Units.iconSizes.smallMedium
                implicitHeight: implicitWidth
            }
            PlasmaComponents3.Label {
                text: root.errorText.length > 0 ? "!"
                      : root.primaryRemaining >= 0 ? root.primaryRemaining + "%" : "…"
                font.bold: true
            }
        }
    }

    fullRepresentation: Item {
        Layout.minimumWidth: Kirigami.Units.gridUnit * 22
        Layout.preferredWidth: Kirigami.Units.gridUnit * 24
        Layout.maximumWidth: Kirigami.Units.gridUnit * 28
        implicitWidth: Layout.preferredWidth
        implicitHeight: Math.min(content.implicitHeight + Kirigami.Units.largeSpacing * 2,
                                 Kirigami.Units.gridUnit * 30)

        PlasmaComponents3.ScrollView {
            id: detailsScroll
            anchors.fill: parent
            contentWidth: availableWidth
            ColumnLayout {
                id: content
                width: detailsScroll.availableWidth
                spacing: Kirigami.Units.largeSpacing
                RowLayout {
                    Layout.fillWidth: true
                    PlasmaComponents3.Label {
                        text: i18n("Codex 用量")
                        font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * 1.35
                        font.bold: true
                        Layout.fillWidth: true
                    }
                    PlasmaComponents3.ToolButton {
                        icon.name: "view-refresh"
                        enabled: !root.reconnecting
                        onClicked: root.forceRefresh()
                        PlasmaComponents3.ToolTip.text: i18n("重新连接并刷新当前账号")
                        PlasmaComponents3.ToolTip.visible: hovered
                    }
                }
                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: accountColumn.implicitHeight + Kirigami.Units.largeSpacing * 2
                    radius: Kirigami.Units.smallSpacing
                    color: Kirigami.Theme.alternateBackgroundColor
                    ColumnLayout {
                        id: accountColumn
                        anchors.fill: parent
                        anchors.margins: Kirigami.Units.largeSpacing
                        spacing: Kirigami.Units.smallSpacing
                        PlasmaComponents3.Label {
                            text: i18n("当前账号")
                            opacity: 0.65
                        }
                        PlasmaComponents3.Label {
                            Layout.fillWidth: true
                            text: root.reconnecting ? i18n("正在重新连接…")
                                  : root.accountData && root.accountData.email
                                  ? root.accountData.email
                                  : root.accountData ? root.accountTypeText(root.accountData.type)
                                  : i18n("账号信息不可用")
                            font.bold: true
                            wrapMode: Text.WrapAnywhere
                        }
                        PlasmaComponents3.Label {
                            Layout.fillWidth: true
                            text: root.accountData
                                  ? i18n("%1 · 套餐：%2", root.accountTypeText(root.accountData.type),
                                         root.accountData.planType || "—")
                                  : i18n("登录方式与套餐暂不可用")
                            opacity: 0.65
                            wrapMode: Text.Wrap
                        }
                    }
                }
                PlasmaComponents3.Label {
                    visible: root.errorText.length > 0
                    text: root.errorText
                    color: Kirigami.Theme.negativeTextColor
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                }
                PlasmaComponents3.Label {
                    visible: root.warningText.length > 0
                    text: i18n("暂时无法更新，正在显示上次成功数据")
                    color: Kirigami.Theme.neutralTextColor
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                }
                Repeater {
                    model: root.buckets
                    delegate: ColumnLayout {
                        required property var modelData
                        required property int index
                        Layout.fillWidth: true
                        spacing: Kirigami.Units.smallSpacing
                        RowLayout {
                            Layout.fillWidth: true
                            PlasmaComponents3.Label { text: modelData.name; font.bold: true; Layout.fillWidth: true }
                            PlasmaComponents3.Label { text: modelData.plan; opacity: 0.65 }
                        }
                        UsageWindow { windowData: modelData.primary }
                        UsageWindow { windowData: modelData.secondary }
                        Kirigami.Separator { Layout.fillWidth: true; visible: index < root.buckets.length - 1 }
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    visible: root.usageData !== null
                    PlasmaComponents3.Label {
                        text: {
                            var credits = root.usageData && root.usageData.rateLimits
                                          ? root.usageData.rateLimits.credits : null
                            if (!credits) return i18n("Credits：—")
                            if (credits.unlimited) return i18n("Credits：无限")
                            return i18n("Credits：%1", credits.balance === null ? "—" : credits.balance)
                        }
                        Layout.fillWidth: true
                    }
                    PlasmaComponents3.Label {
                        text: {
                            var resets = root.usageData ? root.usageData.rateLimitResetCredits : null
                            return i18n("可用重置：%1", resets ? resets.availableCount : "—")
                        }
                    }
                }
                PlasmaComponents3.Label {
                    text: root.updatedAt.getTime() > 0
                          ? i18n("更新于 %1", root.updatedAt.toLocaleTimeString(Qt.locale(), Locale.ShortFormat)) : ""
                    opacity: 0.6
                    Layout.alignment: Qt.AlignRight
                }
            }
        }
    }

    component UsageWindow: ColumnLayout {
        required property var windowData
        visible: windowData !== null && windowData !== undefined
        Layout.fillWidth: true
        spacing: Kirigami.Units.smallSpacing
        readonly property int remaining: windowData ? Math.max(0, 100 - windowData.usedPercent) : 0
        RowLayout {
            Layout.fillWidth: true
            PlasmaComponents3.Label {
                text: windowData ? root.durationText(windowData.windowDurationMins) : ""
                Layout.fillWidth: true
            }
            PlasmaComponents3.Label { text: i18n("剩余 %1%", remaining); font.bold: true }
        }
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: Kirigami.Units.smallSpacing
            radius: height / 2
            color: Kirigami.Theme.alternateBackgroundColor
            Rectangle {
                width: parent.width * remaining / 100
                height: parent.height
                radius: parent.radius
                color: remaining <= 10 ? Kirigami.Theme.negativeTextColor
                       : remaining <= 30 ? Kirigami.Theme.neutralTextColor
                       : Kirigami.Theme.positiveTextColor
            }
        }
        PlasmaComponents3.Label {
            text: windowData ? root.resetText(windowData.resetsAt) : ""
            opacity: 0.65
            font.pixelSize: Kirigami.Theme.smallFont.pixelSize
        }
    }
}
