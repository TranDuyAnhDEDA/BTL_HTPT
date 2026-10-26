import os
import sys
import time
import threading
import requests
import uvicorn

# Đảm bảo in ký tự tiếng Việt không bị lỗi encoding trên Windows console
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Thêm thư mục gốc vào đường dẫn import
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.metadata import FileMetadata
from src.tracker.server import app, PEER_TIMEOUT_SECONDS

TRACKER_HOST = "127.0.0.1"
TRACKER_PORT = 8000
BASE_URL = f"http://{TRACKER_HOST}:{TRACKER_PORT}"


def start_tracker_server():
    """Khởi chạy máy chủ Tracker trong một luồng riêng biệt."""
    uvicorn.run(app, host=TRACKER_HOST, port=TRACKER_PORT, log_level="warning")


def main():
    print("=" * 60)
    print("  KIỂM THỬ BƯỚC 2: TRACKER SERVER & CƠ CHẾ ĐIỀU PHỐI DANH BẠ")
    print("=" * 60)

    # 1. Khởi chạy Tracker Server ở chế độ nền (Background Thread)
    print(f"\n[1] Đang khởi chạy Tracker Server tại {BASE_URL}...")
    server_thread = threading.Thread(target=start_tracker_server, daemon=True)
    server_thread.start()

    # Chờ 1.5 giây để server khởi động sẵn sàng
    time.sleep(1.5)

    # 2. Kiểm tra Tracker Server có đang online không
    try:
        res = requests.get(f"{BASE_URL}/")
        assert res.status_code == 200
        print(" -> Tracker Server phản hồi thành công:", res.json())
    except Exception as e:
        print(f" -> Lỗi không thể kết nối Tracker: {e}")
        return

    # 3. Đăng ký File Metadata lên Tracker (Mô phỏng Seeder đăng ký chia sẻ file)
    metadata_file = os.path.join(os.path.dirname(__file__), "temp_step1", "sample_video.metadata.json")
    if not os.path.exists(metadata_file):
        print(f" -> Không tìm thấy file {metadata_file}. Vui lòng chạy tests/test_step1.py trước!")
        return

    metadata = FileMetadata.load_json(metadata_file)
    print(f"\n[2] Seeder gửi đăng ký file lên Tracker...")
    print(f"    * File ID: {metadata.file_id} | Tên file: {metadata.file_name} | Số chunks: {metadata.num_chunks}")
    
    res = requests.post(f"{BASE_URL}/register_file", json=metadata.to_dict())
    assert res.status_code == 201
    print(" -> Tracker phản hồi:", res.json())

    # 4. Peer 1 (Seeder ban đầu) báo danh: Nắm giữ toàn bộ các chunks [0, 1, 2]
    print(f"\n[3] Peer 1 (Seeder) báo danh với Tracker...")
    peer1_data = {
        "peer_id": "peer_seeder_01",
        "file_id": metadata.file_id,
        "ip": "127.0.0.1",
        "port": 6001,
        "bitfield": [0, 1, 2]  # Có đủ 100% chunks
    }
    res = requests.post(f"{BASE_URL}/announce", json=peer1_data)
    assert res.status_code == 200
    print(" -> Peer 1 báo danh thành công:", res.json())

    # 5. Peer 2 (Một Leecher mới vào và vừa tải được chunk 0) báo danh
    print(f"\n[4] Peer 2 (Leecher) báo danh: Vừa có chunk [0]...")
    peer2_data = {
        "peer_id": "peer_leecher_02",
        "file_id": metadata.file_id,
        "ip": "127.0.0.1",
        "port": 6002,
        "bitfield": [0]  # Mới chỉ có chunk số 0
    }
    res = requests.post(f"{BASE_URL}/announce", json=peer2_data)
    assert res.status_code == 200
    print(" -> Peer 2 báo danh thành công:", res.json())

    # 6. Peer 3 (Một máy mới tinh muốn tải) hỏi Tracker: "Ai đang giữ file này?"
    print(f"\n[5] Peer 3 hỏi Tracker: 'Ai đang có các mảnh của file {metadata.file_id}?'...")
    res = requests.get(f"{BASE_URL}/peers/{metadata.file_id}")
    assert res.status_code == 200
    tracker_reply = res.json()
    active_peers = tracker_reply["peers"]
    
    print(f" -> Tracker trả về {len(active_peers)} peer(s):")
    for p in active_peers:
        print(f"    * Peer ID: {p['peer_id']} ({p['ip']}:{p['port']}) sở hữu Chunks: {p['bitfield']}")

    # 7. Kiểm tra cơ chế Heartbeat
    print(f"\n[6] Kiểm tra cơ chế nhịp tim (Heartbeat)...")
    res = requests.post(f"{BASE_URL}/heartbeat", json={"peer_id": "peer_seeder_01"})
    assert res.status_code == 200
    print(" -> Gửi Heartbeat từ Peer 1 thành công:", res.json())

    # 8. Kiểm tra cơ chế Phát hiện sự cố (Fault Tolerance / Timeout)
    print(f"\n[7] Thử nghiệm phát hiện Peer offline (Fault Detection)...")
    from src.tracker.server import file_peers
    # Cố tình chỉnh thời gian last_seen của Peer 2 về quá khứ 20 giây trước (mô phỏng việc mất mạng/tắt máy)
    print(" -> Giả lập: Peer 2 bị ngắt kết nối đột ngột (không gửi heartbeat trong 20s)...")
    file_peers[metadata.file_id]["peer_leecher_02"].last_seen -= (PEER_TIMEOUT_SECONDS + 5)

    # Hỏi lại Tracker danh sách peers
    res = requests.get(f"{BASE_URL}/peers/{metadata.file_id}")
    active_peers_after = res.json()["peers"]
    remaining_ids = [p["peer_id"] for p in active_peers_after]
    print(f" -> Danh sách peer còn sống sau khi quét timeout: {remaining_ids}")

    assert "peer_leecher_02" not in remaining_ids
    print(" -> BẢO ĐẢM DUNG LỖI THÀNH CÔNG: Tracker đã tự động gỡ bỏ Peer 2 bị sập nguồn!")

    print("\n" + "=" * 60)
    print("  CHÚC MỪNG: BƯỚC 2 HOÀN TẤT XUẤT SẮC! TRACKER ĐÃ SẴN SÀNG.")
    print("=" * 60)


if __name__ == "__main__":
    main()
