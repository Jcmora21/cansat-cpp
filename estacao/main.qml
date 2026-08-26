import QtQuick
import QtQuick.Controls

Window {
    width: 900
    height: 600
    visible: true
    title: "🦅 Estação Terrena - CanSat Eagles (C++/Qt 60 FPS)"
    color: "#121212"

    Column {
        anchors.fill: parent
        anchors.margins: 20
        spacing: 20

        // Cabeçalho
        Row {
            width: parent.width
            Text {
                text: "🦅 Estação Terrena CanSat"
                color: "#FFFFFF"
                font.pixelSize: 24
                font.bold: true
            }
            Item { width: 50; height: 1 }
            Text {
                text: "ESTADO: " + telemetry.estado
                color: telemetry.estado === "SUBIDA" ? "#00E676" : "#FFB300"
                font.pixelSize: 20
                font.bold: true
            }
        }

        Rectangle { width: parent.width; height: 2; color: "#333333" }

        // Painel de Métricas Instantâneas
        Grid {
            columns: 3
            spacing: 20
            width: parent.width

            Rectangle {
                width: 260; height: 100; color: "#1E1E1E"; radius: 8
                Column {
                    anchors.centerIn: parent
                    Text { text: "Altitude"; color: "#888888"; font.pixelSize: 14 }
                    Text { text: telemetry.altitude.toFixed(1) + " m"; color: "#00E676"; font.pixelSize: 28; font.bold: true }
                }
            }

            Rectangle {
                width: 260; height: 100; color: "#1E1E1E"; radius: 8
                Column {
                    anchors.centerIn: parent
                    Text { text: "Pressão"; color: "#888888"; font.pixelSize: 14 }
                    Text { text: telemetry.pressao.toFixed(1) + " hPa"; color: "#29B6F6"; font.pixelSize: 28; font.bold: true }
                }
            }

            Rectangle {
                width: 260; height: 100; color: "#1E1E1E"; radius: 8
                Column {
                    anchors.centerIn: parent
                    Text { text: "Temperatura"; color: "#888888"; font.pixelSize: 14 }
                    Text { text: telemetry.temperatura.toFixed(1) + " °C"; color: "#FF7043"; font.pixelSize: 28; font.bold: true }
                }
            }
        }
    }
}
