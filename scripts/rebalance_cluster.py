#!/usr/bin/env python3
import argparse
import socket

from styx.common.message_types import MessageType
from styx.common.serialization import Serializer
from styx.common.tcp_networking import NetworkingManager


def main():
    parser = argparse.ArgumentParser(description="Trigger a Styx coordinator rebalance (snapshot-based InitRecovery).")
    parser.add_argument("--host", default="localhost", help="Coordinator host (default: localhost)")
    parser.add_argument("--port", type=int, default=8886, help="Coordinator port exposed on host (default: 8886)")
    args = parser.parse_args()

    msg = NetworkingManager.encode_message(
        msg=b"",
        msg_type=int(MessageType.Rebalance),
        serializer=Serializer.NONE,
    )
    s = socket.socket()
    s.connect((args.host, args.port))
    s.sendall(msg)
    s.close()
    print(f"Sent rebalance request to {args.host}:{args.port}")


if __name__ == "__main__":
    main()


