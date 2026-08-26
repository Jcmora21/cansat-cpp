#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include "receiver.hpp"

int main(int argc, char *argv[]) {
    QGuiApplication app(argc, argv);

    QQmlApplicationEngine engine;
    TelemetryReceiver receiver;

    engine.rootContext()->setContextProperty("telemetry", &receiver);
    engine.load(QUrl(QStringLiteral("main.qml")));

    if (engine.rootObjects().isEmpty())
        return -1;

    return app.exec();
}
