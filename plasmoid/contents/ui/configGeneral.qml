import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import org.kde.kcmutils as KCM
import org.kde.kirigami as Kirigami

KCM.SimpleKCM {
    property alias cfg_refreshInterval: refreshInterval.value

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
    }
}
