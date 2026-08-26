#ifndef RECEIVER_HPP
#define RECEIVER_HPP

#include <QObject>
#include <QUdpSocket>
#include <QJsonObject>
#include <QJsonDocument>

class TelemetryReceiver : public QObject {
    Q_OBJECT
    Q_PROPERTY(double altitude READ altitude NOTIFY telemetryUpdated)
    Q_PROPERTY(double pressao READ pressao NOTIFY telemetryUpdated)
    Q_PROPERTY(double temperatura READ temperatura NOTIFY telemetryUpdated)
    Q_PROPERTY(QString estado READ estado NOTIFY telemetryUpdated)
    Q_PROPERTY(int tempo READ tempo NOTIFY telemetryUpdated)

public:
    explicit TelemetryReceiver(QObject *parent = nullptr) : QObject(parent) {
        udpSocket = new QUdpSocket(this);
        udpSocket->bind(QHostAddress::LocalHost, 5005);
        connect(udpSocket, &QUdpSocket::readyRead, this, &TelemetryReceiver::processPendingDatagrams);
    }

    double altitude() const { return m_altitude; }
    double pressao() const { return m_pressao; }
    double temperatura() const { return m_temperatura; }
    QString estado() const { return m_estado; }
    int tempo() const { return m_tempo; }

signals:
    void telemetryUpdated();

private slots:
    void processPendingDatagrams() {
        while (udpSocket->hasPendingDatagrams()) {
            QByteArray datagram;
            datagram.resize(int(udpSocket->pendingDatagramSize()));
            udpSocket->readDatagram(datagram.data(), datagram.size());

            QJsonDocument doc = QJsonDocument::fromJson(datagram);
            if (!doc.isNull() && doc.isObject()) {
                QJsonObject obj = doc.object();
                m_altitude = obj["altitude"].toDouble();
                m_pressao = obj["pressao"].toDouble();
                m_temperatura = obj["temperatura"].toDouble();
                m_estado = obj["estado"].toString();
                m_tempo = obj["tempo"].toInt();
                emit telemetryUpdated();
            }
        }
    }

private:
    QUdpSocket *udpSocket;
    double m_altitude = 0.0;
    double m_pressao = 1013.25;
    double m_temperatura = 25.0;
    QString m_estado = "DESCONHECIDO";
    int m_tempo = 0;
};

#endif
