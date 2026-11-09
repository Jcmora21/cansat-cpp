import argparse
import asyncio
import threading

import serial

from groundstation import main


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
        default=115200,
        help="baudrate da ligação serial (default: %(default)s; APC220 normalmente usa 9600)",
    )
    return parser.parse_args()


def create_serial_transport(port, baudrate):
    serial_transport = SerialTransport(port, baudrate)

    def factory(_host, _port):
        return serial_transport

    return factory


if __name__ == "__main__":
    args = parse_args()
    transport_factory = create_serial_transport(args.port, args.baudrate)
    print(
        f"[Serial] Porta {args.port} aberta a {args.baudrate} baud; "
        "aguardando linhas JSON..."
    )
    asyncio.run(main(transport_factory))