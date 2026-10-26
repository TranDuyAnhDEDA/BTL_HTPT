import json
import struct
import socket
from typing import Tuple, Optional, Any

# Định dạng: 4 bytes đầu tiên quy định độ dài của phần header (JSON)
# Tiếp theo là phần JSON Header, và sau cùng là phần dữ liệu nhị phân (Binary Data)


def send_packet(sock: socket.socket, header: dict, binary_data: bytes = b"") -> None:
    """
    Gửi một gói tin qua TCP Socket:
    [4 bytes: độ dài header] + [Header dạng JSON UTF-8] + [Dữ liệu nhị phân]
    """
    header_json = json.dumps(header).encode("utf-8")
    header_len = len(header_json)
    data_len = len(binary_data)

    # Đóng gói: 4 bytes độ dài header (Big-endian), 4 bytes độ dài binary data
    prefix = struct.pack("!II", header_len, data_len)
    sock.sendall(prefix + header_json + binary_data)


def recv_exact(sock: socket.socket, num_bytes: int) -> bytes:
    """Đọc chính xác num_bytes từ socket, không bị thiếu dữ liệu khi mạng chậm."""
    buf = bytearray()
    while len(buf) < num_bytes:
        packet = sock.recv(num_bytes - len(buf))
        if not packet:
            raise ConnectionError("Kết nối mạng bị đóng bất ngờ khi đang nhận dữ liệu")
        buf.extend(packet)
    return bytes(buf)


def recv_packet(sock: socket.socket) -> Tuple[dict, bytes]:
    """
    Đọc một gói tin hoàn chỉnh từ TCP Socket:
    Trả về: (header_dict, binary_data)
    """
    # 1. Đọc 8 bytes prefix (4 bytes độ dài header + 4 bytes độ dài data)
    prefix = recv_exact(sock, 8)
    header_len, data_len = struct.unpack("!II", prefix)

    # 2. Đọc phần Header JSON
    header_bytes = recv_exact(sock, header_len)
    header = json.loads(header_bytes.decode("utf-8"))

    # 3. Đọc phần Binary Data (nếu có)
    binary_data = b""
    if data_len > 0:
        binary_data = recv_exact(sock, data_len)

    return header, binary_data
