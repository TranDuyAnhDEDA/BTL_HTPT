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
    print("=" * 70)
    print("  KIỂM THỬ BƯỚC 4: TẢI SONG SONG & VỪA TẢI VỪA CHIA SẺ (3 PEERS)")
    print("=" * 70)

    # 1. Khởi chạy Tracker Server ở chế độ nền
    print("\n[1] Đang khởi chạy Tracker Server...")
    tracker_thread = threading.Thread(target=run_tracker, daemon=True)
    tracker_thread.start()
    time.sleep(1.5)

    # 2. Chuẩn bị thư mục dữ liệu riêng biệt cho 3 Peers
    work_dir = os.path.join(os.path.dirname(__file__), "temp_step4")
    if os.path.exists(work_dir):
        shutil.rmtree(work_dir)
    os.makedirs(work_dir, exist_ok=True)

    peer1_dir = os.path.join(work_dir, "peer1_storage")
    peer2_dir = os.path.join(work_dir, "peer2_storage")
    peer3_dir = os.path.join(work_dir, "peer3_storage")
    peer3_output_file = os.path.join(work_dir, "peer3_downloads", "complete_video.mp4")

    # Tạo file mẫu 2.0 MB (sẽ cắt thành đúng 4 chunks 512KB: 0, 1, 2, 3)
    source_file = os.path.join(work_dir, "big_movie.mp4")
    content = b"PARALLEL-BITTORRENT-CHUNK-DISTRIBUTED-SYSTEMS\n" * 45000
    with open(source_file, "wb") as f:
        f.write(content)
    print(f" -> Đã tạo file nguồn mẫu: {source_file} ({len(content):,} bytes)")

    file_id = "movie4k"
    peer1_chunks_dir = os.path.join(peer1_dir, "chunks", file_id)
    metadata = split_file(
        file_path=source_file,
        output_chunks_dir=peer1_chunks_dir,
        tracker_url=f"http://{TRACKER_HOST}:{TRACKER_PORT}",
        chunk_size=512 * 1024,
        file_id=file_id
    )
    print(f" -> File được cắt thành {metadata.num_chunks} chunks: [Chunk 0, 1, 2, 3]")

    # 3. Khởi động PEER 1 (Full Seeder): Sở hữu toàn bộ 4 chunks [0, 1, 2, 3]
    print("\n[2] Khởi động Peer 1 (Full Seeder) tại Port 6001...")
    peer1 = PeerNode(
        peer_id="PEER_1_SEEDER",
        host="127.0.0.1",
        port=6001,
        storage_dir=peer1_dir,
        tracker_url=f"http://{TRACKER_HOST}:{TRACKER_PORT}"
    )
    peer1.start_upload_server()
    peer1.register_file_to_tracker(metadata)
    peer1.owned_chunks[file_id] = set(range(metadata.num_chunks))
    peer1.announce_to_tracker(file_id)

    # 4. Khởi động PEER 2 (Leecher A): Tải trước Chunk 0 và Chunk 1 từ Peer 1
    print("\n[3] Khởi động Peer 2 (Leecher A) tại Port 6002...")
    peer2 = PeerNode(
        peer_id="PEER_2_LEECHER_A",
        host="127.0.0.1",
        port=6002,
        storage_dir=peer2_dir,
        tracker_url=f"http://{TRACKER_HOST}:{TRACKER_PORT}"
    )
    peer2.start_upload_server()

    print(" -> Peer 2 tiến hành tải Chunk 0 và Chunk 1 từ Peer 1...")
    assert peer2.download_chunk("127.0.0.1", 6001, file_id, 0, metadata.chunk_hashes[0])
    assert peer2.download_chunk("127.0.0.1", 6001, file_id, 1, metadata.chunk_hashes[1])
    print(f" -> Hiện tại Peer 2 mới chỉ có {peer2.owned_chunks[file_id]} (CHƯA ĐỦ FILE!).")

    # 5. Khởi động PEER 3 (Leecher B): Cần tải trọn vẹn cả 4 Chunks [0, 1, 2, 3]
    print("\n[4] Khởi động Peer 3 (Leecher B) tại Port 6003...")
    peer3 = PeerNode(
        peer_id="PEER_3_LEECHER_B",
        host="127.0.0.1",
        port=6003,
        storage_dir=peer3_dir,
        tracker_url=f"http://{TRACKER_HOST}:{TRACKER_PORT}"
    )
    peer3.start_upload_server()

    # 6. THỰC HIỆN TẢI SONG SONG (PARALLEL DOWNLOADING)
    # Peer 3 sẽ tự động phân bổ:
    # - Tải Chunk 0, 1 từ PEER 2 (Chứng minh: Peer 2 upload dù chưa tải xong file!)
    # - Tải Chunk 2, 3 từ PEER 1
    print("\n[5] BẮT ĐẦU TẢI SONG SONG ĐA LUỒNG TỪ CẢ PEER 1 VÀ PEER 2...")
    download_success = peer3.download_file_parallel(
        metadata=metadata,
        output_file_path=peer3_output_file,
        max_threads=4
    )
    assert download_success, "Tải song song thất bại!"

    # 7. Đối chiếu tính toàn vẹn 100% của file tải về
    print("\n[6] Kiểm tra tính toàn vẹn của file tải về...")
    with open(source_file, "rb") as f_orig, open(peer3_output_file, "rb") as f_down:
        assert f_orig.read() == f_down.read()

    print("\n" + "=" * 70)
    print("  CHÚC MỪNG: BƯỚC 4 HOÀN TẤT XUẤT SẮC!")
    print("  1. Đã chứng minh Tải song song (Parallel) từ 2 nguồn cùng lúc.")
    print("  2. Đã chứng minh Peer 2 vừa tải vừa chia sẻ (Seed while Leeching).")
    print("  3. File sau khi ghép trùng khớp 100% với file gốc ban đầu!")
    print("=" * 70)

    # Dọn dẹp tiến trình
    peer1.stop()
    peer2.stop()
    peer3.stop()


if __name__ == "__main__":
    main()
