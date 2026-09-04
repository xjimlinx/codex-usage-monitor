import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import org.kde.kcmutils as KCM
import org.kde.kirigami as Kirigami

KCM.SimpleKCM {
    property alias cfg_refreshInterval: refreshInterval.value
    property int cfg_refreshIntervalDefault: 30
    property alias cfg_compactHorizontalPadding: compactHorizontalPadding.value
    property int cfg_compactHorizontalPaddingDefault: 8
    property alias cfg_compactVerticalPadding: compactVerticalPadding.value
    property int cfg_compactVerticalPaddingDefault: 4
    property alias cfg_proxyUrl: proxyAddress.text
    property string cfg_proxyUrlDefault: ""
    property string proxyStatus: ""
    property bool proxyBusy: false

    function loadProxy() {
        var request = new XMLHttpRequest()
        request.open("GET", "http://127.0.0.1:9000/api/config")
        request.onreadystatechange = function() {
            if (request.readyState !== XMLHttpRequest.DONE)
                return
            if (request.status !== 200) {
                proxyStatus = i18n("无法读取后端代理配置")
                return
            }
            try {
                var payload = JSON.parse(request.responseText)
                proxyAddress.text = payload.proxyUrl || ""
                proxyStatus = payload.usesEnvironmentProxy
                              ? i18n("当前使用 systemd 服务环境中的代理设置") : ""
            } catch (error) {
                proxyStatus = i18n("代理配置响应无效")
            }
        }
        request.onerror = function() { proxyStatus = i18n("无法连接本地用量服务") }
        request.send()
    }

    function saveProxy() {
        proxyBusy = true
        proxyStatus = i18n("正在应用…")
        var request = new XMLHttpRequest()
        request.open("POST", "http://127.0.0.1:9000/api/config")
        request.setRequestHeader("Content-Type", "application/json")
        request.onreadystatechange = function() {
            if (request.readyState !== XMLHttpRequest.DONE)
                return
            proxyBusy = false
            try {
                var payload = JSON.parse(request.responseText)
                if (request.status !== 200 || payload.error)
                    throw new Error(payload.error || i18n("HTTP %1", request.status))
                proxyStatus = i18n("已保存，后端正在重新连接")
            } catch (error) {
                proxyStatus = error.message || String(error)
            }
        }
        request.onerror = function() {
            proxyBusy = false
            proxyStatus = i18n("无法连接本地用量服务")
        }
        request.send(JSON.stringify({proxyUrl: proxyAddress.text.trim()}))
    }

    Component.onCompleted: loadProxy()

    Kirigami.FormLayout {
        RowLayout {
            Kirigami.FormData.label: i18n("刷新间隔：")

            Button {
                text: i18n("− 5 秒")
                enabled: refreshInterval.value > refreshInterval.from
                onClicked: refreshInterval.decrease()
            }

            SpinBox {
                id: refreshInterval
                from: 5
                to: 3600
                stepSize: 5
                editable: true
                Layout.preferredWidth: Kirigami.Units.gridUnit * 7
                up.indicator: null
                down.indicator: null
                textFromValue: function(value) {
                    return i18n("%1 秒", value)
                }
                valueFromText: function(text) {
                    var parsed = parseInt(text, 10)
                    return isNaN(parsed) ? 30 : parsed
                }
            }

            Button {
                text: i18n("+ 5 秒")
                enabled: refreshInterval.value < refreshInterval.to
                onClicked: refreshInterval.increase()
            }
        }

        Label {
            Kirigami.FormData.isSection: true
            text: i18n("设置保存后立即生效。最短 5 秒，最长 1 小时。")
            wrapMode: Text.Wrap
            Layout.fillWidth: true
            opacity: 0.7
        }

        Label {
            Kirigami.FormData.isSection: true
            text: i18n("任务栏布局")
            font.bold: true
        }

        SpinBox {
            id: compactHorizontalPadding
            Kirigami.FormData.label: i18n("横向内边距：")
            from: 0
            to: 32
            editable: true
            textFromValue: function(value) { return i18n("%1 px", value) }
            valueFromText: function(text) {
                var parsed = parseInt(text, 10)
                return isNaN(parsed) ? 8 : parsed
            }
        }

        SpinBox {
            id: compactVerticalPadding
            Kirigami.FormData.label: i18n("纵向内边距：")
            from: 0
            to: 16
            editable: true
            textFromValue: function(value) { return i18n("%1 px", value) }
            valueFromText: function(text) {
                var parsed = parseInt(text, 10)
                return isNaN(parsed) ? 4 : parsed
            }
        }

        TextField {
            id: proxyAddress
            Kirigami.FormData.label: i18n("代理地址：")
            Layout.fillWidth: true
            placeholderText: "http://127.0.0.1:7890"
            inputMethodHints: Qt.ImhUrlCharactersOnly | Qt.ImhNoAutoUppercase
            selectByMouse: true
        }

        RowLayout {
            Layout.fillWidth: true
            Button {
                text: i18n("保存并应用代理")
                enabled: !proxyBusy
                onClicked: saveProxy()
            }
            Button {
                text: i18n("使用服务环境设置")
                enabled: !proxyBusy
                onClicked: {
                    proxyAddress.clear()
                    saveProxy()
                }
            }
        }

        Label {
            text: proxyStatus
            visible: text.length > 0
            wrapMode: Text.Wrap
            Layout.fillWidth: true
            opacity: 0.75
        }

        Label {
            text: i18n("支持 http://、https:// 和 socks5://。为避免泄漏，地址不能包含用户名或密码。")
            wrapMode: Text.Wrap
            Layout.fillWidth: true
            opacity: 0.7
        }
    }
}
