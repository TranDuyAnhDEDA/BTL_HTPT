import os
import sys
import time
import shutil
import threading
import uvicorn

# Đảm bảo in ký tự tiếng Việt không bị lỗi encoding trên Windows console
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Thêm thư mục gốc vào đường dẫn import
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.chunker import split_file, merge_chunks
from src.core.metadata import FileMetadata
from src.tracker.server import app
from src.peer.client import PeerNode

TRACKER_HOST = "127.0.0.1"
TRACKER_PORT = 8000


def run_tracker():
    uvicorn.run(app, host=TRACKER_HOST, port=TRACKER_PORT, log_level="error")


def main():
    print("=" * 65)
    print("  KIỂM THỬ BƯỚC 3: KẾT NỐI P2P TRỰC TIẾP (1 SEEDER - 1 LEECHER)")
    print("=" * 65)

    # 1. Khởi chạy Tracker Server ở chế độ nền
    print("\n[1] Đang khởi chạy Tracker Server...")
    tracker_thread = threading.Thread(target=run_tracker, daemon=True)
    tracker_thread.start()
    time.sleep(1.5)

    # 2. Chuẩn bị thư mục lưu trữ riêng biệt cho từng Peer
    work_dir = os.path.join(os.path.dirname(__file__), "temp_step3")
    if os.path.exists(work_dir):
        shutil.rmtree(work_dir)
    os.makedirs(work_dir, exist_ok=True)

    seeder_dir = os.path.join(work_dir, "seeder_storage")
    leecher_dir = os.path.join(work_dir, "leecher_storage")
    leecher_output_file = os.path.join(work_dir, "leecher_downloads", "downloaded_video.mp4")

    # Tạo file gốc mẫu 1.5MB tại phía Seeder
    source_file = os.path.join(work_dir, "original_source.mp4")
    content = b"DATA-CHUNK-FOR-P2P-BITTORRENT-SIMULATION-SYSTEM\n" * 32000
    with open(source_file, "wb") as f:
        f.write(content)
    print(f" -> Đã tạo file nguồn gốc ({len(content):,} bytes)")

    # 3. Phía Seeder cắt file thành các chunk 512KB
    file_id = "ds02file"
    seeder_chunks_dir = os.path.join(seeder_dir, "chunks", file_id)
    metadata = split_file(
        file_path=source_file,
        output_chunks_dir=seeder_chunks_dir,
        tracker_url=f"http://{TRACKER_HOST}:{TRACKER_PORT}",
        chunk_size=512 * 1024,
        file_id=file_id
    )
    print(f" -> Seeder đã cắt file thành {metadata.num_chunks} chunks.")

    # 4. Khởi động PEER 1 (SEEDER): Mở cổng Socket 6001 và đăng ký lên Tracker
    print("\n[2] Khởi động Peer 1 (Seeder) tại cổng 6001...")
    peer_seeder = PeerNode(
        peer_id="PEER_SEEDER_1",
        host="127.0.0.1",
        port=6001,
        storage_dir=seeder_dir,
        tracker_url=f"http://{TRACKER_HOST}:{TRACKER_PORT}"
    )
    # Khởi động máy chủ Socket để lắng nghe yêu cầu upload
    peer_seeder.start_upload_server()

    # Đăng ký file với Tracker và báo danh mình có đủ tất cả các chunk
    peer_seeder.register_file_to_tracker(metadata)
    peer_seeder.owned_chunks[file_id] = set(range(metadata.num_chunks))
    peer_seeder.announce_to_tracker(file_id)

    # 5. Khởi động PEER 2 (LEECHER): Chưa có file nào, muốn tải về
    print("\n[3] Khởi động Peer 2 (Leecher) tại cổng 6002 để bắt đầu tải...")
    peer_leecher = PeerNode(
        peer_id="PEER_LEECHER_2",
        host="127.0.0.1",
        port=6002,
        storage_dir=leecher_dir,
        tracker_url=f"http://{TRACKER_HOST}:{TRACKER_PORT}"
    )
    peer_leecher.start_upload_server()

    # Peer 2 hỏi Tracker danh sách ai đang giữ file
    print("\n[4] Peer 2 hỏi Tracker tìm nguồn tải...")
    peers_list = peer_leecher.get_peers_from_tracker(file_id)
    print(f" -> Tracker phản hồi tìm thấy {len(peers_list)} nguồn:")
    for p in peers_list:
        print(f"    * Peer ID: {p['peer_id']} ({p['ip']}:{p['port']}) | Có chunks: {p['bitfield']}")

    # 6. Peer 2 kết nối trực tiếp Socket TCP tới Peer 1 để tải từng chunk
    print("\n[5] TIẾN HÀNH TRUYỀN DỮ LIỆU P2P QUA SOCKET (BỎ QUA TRACKER)...")
    target_peer = peers_list[0]
    
    for chunk_idx in range(metadata.num_chunks):
        expected_hash = metadata.chunk_hashes[chunk_idx]
        success = peer_leecher.download_chunk(
            peer_ip=target_peer["ip"],
            peer_port=target_peer["port"],
            file_id=file_id,
            chunk_idx=chunk_idx,
            expected_hash=expected_hash
        )
        assert success, f"Tải chunk {chunk_idx} thất bại!"

    # 7. Ghép các chunks đã tải về thành file hoàn chỉnh
    print("\n[6] Đang dán ghép các chunks vừa tải về thành file hoàn chỉnh...")
    leecher_chunks_dir = os.path.join(leecher_dir, "chunks", file_id)
    merge_success = merge_chunks(leecher_chunks_dir, leecher_output_file, metadata)
    assert merge_success

    # 8. Đối chiếu file sau khi tải với file gốc
    with open(source_file, "rb") as f_orig, open(leecher_output_file, "rb") as f_down:
        if f_orig.read() == f_down.read():
            print("\n" + "=" * 65)
            print("  CHÚC MỪNG: BƯỚC 3 HOÀN TẤT XUẤT SẮC!")
            print("  Dữ liệu file đã bay thẳng qua Socket TCP giữa 2 máy tính!")
            print("  File gốc và File tải về khớp nhau 100% từng byte!")
            print("=" * 65)

    # Dọn dẹp máy chủ
    peer_seeder.stop()
    peer_leecher.stop()


if __name__ == "__main__":
    main()
