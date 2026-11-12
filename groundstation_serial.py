import argparse
import asyncio
import base64
import json
import threading

import serial

from groundstation import main

APC220_FRAME_MAGIC = b"\xC3\x5A"
APC220_FRAME_SIZE = 4 + 12 + 67 + 16


class SerialTransport:
    def __init__(self, port, baudrate):
        self.port = port
        self.serial = serial.Serial(
            port=port,
            baudrate=baudrate,
            timeout=0.2,
            write_timeout=2,
        )
        self.write_lock = threading.Lock()

    def receive(self):
        while True:
            line = self.serial.readline()
            if line.strip():
                return line, ("serial", self.port)

    def send(self, payload, address=None):
        frame = payload.encode("utf-8")
        if not frame.endswith(b"\n"):
            frame += b"\n"

        with self.write_lock:
            self.serial.write(frame)
            self.serial.flush()


class APC220BinaryTransport(SerialTransport):
    def __init__(self, port, baudrate):
        super().__init__(port, baudrate)
        self.buffer = bytearray()

    def receive(self):
        while True:
            frame_start = self.buffer.find(APC220_FRAME_MAGIC)
            if frame_start < 0:
                if self.buffer.endswith(APC220_FRAME_MAGIC[:1]):
                    self.buffer[:] = self.buffer[-1:]
                else:
                    self.buffer.clear()
            elif frame_start:
                del self.buffer[:frame_start]
            if len(self.buffer) >= APC220_FRAME_SIZE:
                frame = bytes(self.buffer[:APC220_FRAME_SIZE])
                if frame[2] != 1:
                    del self.buffer[0]
                    continue
                del self.buffer[:APC220_FRAME_SIZE]

                nonce_start = 4
                ciphertext_start = nonce_start + 12
                tag_start = ciphertext_start + 67
                envelope = {
                    "protocol": "CANSAT-TLM-ENC",
                    "version": 1,
                    "type": "encrypted_telemetry_binary",
                    "cansat_id": frame[3],
                    "nonce": base64.b64encode(
                        frame[nonce_start:ciphertext_start]
                    ).decode("ascii"),
                    "ciphertext": base64.b64encode(
                        frame[ciphertext_start:tag_start]
                    ).decode("ascii"),
                    "tag": base64.b64encode(frame[tag_start:]).decode("ascii"),
                }
                return json.dumps(envelope, separators=(",", ":")).encode(
                    "utf-8"
                ), ("serial", self.port)

            incoming = self.serial.read(max(1, self.serial.in_waiting))
            if incoming:
                self.buffer.extend(incoming)

    def send(self, payload, address=None):
        raise OSError("O transporte APC220 binário está configurado apenas para receção.")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Ground Station CANSAT-TLM através de uma porta serial"
    )
    parser.add_argument(
        "--port",
        default="/dev/ttyUSB0",
        help="porta serial (COM5, /dev/ttyUSB0; default: %(default)s)",
    )
    parser.add_argument(
        "--baudrate",
        type=int,
        default=None,
        help="baudrate (default: 115200 USB; 9600 APC220 binário)",
    )
    parser.add_argument(
        "--apc220-binary",
        action="store_true",
        help="recebe frames binários compactos do APC220 em vez de linhas JSON",
    )
    return parser.parse_args()


def create_serial_transport(port, baudrate):
    serial_transport = SerialTransport(port, baudrate)

    def factory(_host, _port):
        return serial_transport

    return factory


if __name__ == "__main__":
    args = parse_args()
    baudrate = args.baudrate or (9600 if args.apc220_binary else 115200)
    transport_class = APC220BinaryTransport if args.apc220_binary else SerialTransport
    serial_transport = transport_class(args.port, baudrate)

    def transport_factory(_host, _port):
        return serial_transport

    print(
        f"[Serial] Porta {args.port} aberta a {baudrate} baud; "
        + (
            "aguardando frames binários APC220..."
            if args.apc220_binary
            else "aguardando linhas JSON..."
        )
    )
    asyncio.run(main(transport_factory))