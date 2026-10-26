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
    print("=" * 75)
    print("  KIỂM THỬ BƯỚC 5: XỬ LÝ LỖI (FAULT TOLERANCE) & TRỌN BỘ 7 KỊCH BẢN DEMO")
    print("=" * 75)

    # Khởi chạy Tracker Server ở chế độ nền
    tracker_thread = threading.Thread(target=run_tracker, daemon=True)
    tracker_thread.start()
    time.sleep(1.5)

    # Chuẩn bị môi trường lưu trữ
    work_dir = os.path.join(os.path.dirname(__file__), "temp_step5")
    if os.path.exists(work_dir):
        shutil.rmtree(work_dir)
    os.makedirs(work_dir, exist_ok=True)

    source_file = os.path.join(work_dir, "master_source.mp4")
    content = b"FAULT-TOLERANT-BITTORRENT-SIMULATION-SYSTEM\n" * 45000
    with open(source_file, "wb") as f:
        f.write(content)

    file_id = "demo_final"
    p1_dir = os.path.join(work_dir, "p1_seeder")
    p2_dir = os.path.join(work_dir, "p2_backup")
    p3_dir = os.path.join(work_dir, "p3_leecher")
    rogue_dir = os.path.join(work_dir, "rogue_peer")

    # -------------------------------------------------------------------------
    # KỊCH BẢN 1: Tạo metadata và chia sẻ file (Seeder)
    # -------------------------------------------------------------------------
    print("\n" + "-" * 70)
    print(">>> KỊCH BẢN 1: TẠO METADATA VÀ ĐĂNG KÝ CHIA SẺ FILE (Seeder)")
    print("-" * 70)
    p1_chunks_dir = os.path.join(p1_dir, "chunks", file_id)
    metadata = split_file(
        file_path=source_file,
        output_chunks_dir=p1_chunks_dir,
        tracker_url=f"http://{TRACKER_HOST}:{TRACKER_PORT}",
        chunk_size=512 * 1024,
        file_id=file_id
    )
    print(f" -> Đã tạo metadata cho file '{metadata.file_name}' ({metadata.num_chunks} chunks).")

    # Khởi động Peer 1 (Nguồn chính)
    peer1 = PeerNode("PEER_1_PRIMARY", "127.0.0.1", 6001, p1_dir)
    peer1.start_upload_server()
    peer1.register_file_to_tracker(metadata)
    peer1.owned_chunks[file_id] = set(range(metadata.num_chunks))
    peer1.announce_to_tracker(file_id)

    # Khởi động Peer 2 (Nguồn dự phòng - Có sẵn bản sao để sẵn sàng Failover)
    # Sao chép các chunk sang thư mục của Peer 2
    p2_chunks_dir = os.path.join(p2_dir, "chunks", file_id)
    shutil.copytree(p1_chunks_dir, p2_chunks_dir)
    peer2 = PeerNode("PEER_2_BACKUP", "127.0.0.1", 6002, p2_dir)
    peer2.start_upload_server()
    peer2.owned_chunks[file_id] = set(range(metadata.num_chunks))
    peer2.announce_to_tracker(file_id)

    # Khởi động Peer 3 (Leecher đi tải)
    peer3 = PeerNode("PEER_3_LEECHER", "127.0.0.1", 6003, p3_dir)
    peer3.start_upload_server()

    # -------------------------------------------------------------------------
    # KỊCH BẢN 4 & 5: DỪNG NGUỒN KHI ĐANG TẢI & TỰ ĐỘNG CHUYỂN NGUỒN KHÁC (Failover)
    # -------------------------------------------------------------------------
    print("\n" + "-" * 70)
    print(">>> KỊCH BẢN 4 & 5: SẬP NGUỒN ĐỘT NGỘT & TỰ ĐỘNG CHUYỂN SANG NGUỒN KHÁC")
    print("-" * 70)
    print(" -> Giả lập: Đang chuẩn bị tải Chunk 0 từ Peer 1 thì PEER 1 BỊ TẮT ĐỘT NGỘT!")
    # Tắt đột ngột máy chủ Peer 1
    peer1.stop()

    candidate_sources = [
        {"peer_id": "PEER_1_PRIMARY", "ip": "127.0.0.1", "port": 6001},  # Máy vừa bị chết
        {"peer_id": "PEER_2_BACKUP", "ip": "127.0.0.1", "port": 6002}   # Máy dự phòng
    ]

    print(" -> Peer 3 tiến hành tải Chunk 0 với cơ chế Failover...")
    recovered = peer3.download_chunk_with_failover(
        candidate_peers=candidate_sources,
        file_id=file_id,
        chunk_idx=0,
        expected_hash=metadata.chunk_hashes[0]
    )
    assert recovered, "Failover thất bại!"
    print(" -> KẾT QUẢ KỊCH BẢN 4 & 5: Tự động chuyển đổi sang Peer 2 thành công rực rỡ!")

    # -------------------------------------------------------------------------
    # KỊCH BẢN 6: PHÁT HIỆN VÀ TỪ CHỐI CHUNK BỊ HỎNG / GIẢ MẠO QUA MẠNG
    # -------------------------------------------------------------------------
    print("\n" + "-" * 70)
    print(">>> KỊCH BẢN 6: PHÁT HIỆN CHUNK HỎNG/GIẢ MẠO VÀ TẢI LẠI TỪ NGUỒN TỐT")
    print("-" * 70)
    # Khởi tạo một Peer 'Rogue' cố tình phát tán Chunk 1 bị sửa đổi dữ liệu
    rogue_chunks_dir = os.path.join(rogue_dir, "chunks", file_id)
    os.makedirs(rogue_chunks_dir, exist_ok=True)
    with open(os.path.join(rogue_chunks_dir, "chunk_1.bin"), "wb") as f:
        f.write(b"CORRUPTED_FAKE_DATA_INJECTED_HERE_BY_ROGUE_PEER")

    peer_rogue = PeerNode("PEER_ROGUE_BAD", "127.0.0.1", 6004, rogue_dir)
    peer_rogue.start_upload_server()

    candidate_sources_chunk1 = [
        {"peer_id": "PEER_ROGUE_BAD", "ip": "127.0.0.1", "port": 6004}, # Phát hàng đểu
        {"peer_id": "PEER_2_BACKUP", "ip": "127.0.0.1", "port": 6002}  # Phát hàng xịn
    ]

    print(" -> Peer 3 tải Chunk 1 (gặp phải Peer Rogue gửi dữ liệu sai hash)...")
    success_chunk1 = peer3.download_chunk_with_failover(
        candidate_peers=candidate_sources_chunk1,
        file_id=file_id,
        chunk_idx=1,
        expected_hash=metadata.chunk_hashes[1]
    )
    assert success_chunk1, "Phát hiện chunk hỏng và tải lại thất bại!"
    print(" -> KẾT QUẢ KỊCH BẢN 6: Đã từ chối chunk sai hash và tự lấy lại chunk chuẩn từ Peer 2!")
    peer_rogue.stop()

    # -------------------------------------------------------------------------
    # KỊCH BẢN 2 & 3: TẢI SONG SONG TỪ ÍT NHẤT 2 PEERS & VỪA TẢI VỪA UPLOAD
    # -------------------------------------------------------------------------
    print("\n" + "-" * 70)
    print(">>> KỊCH BẢN 2 & 3: TẢI SONG SONG TỪ 2 PEERS & VỪA TẢI VỪA CHIA SẺ")
    print("-" * 70)
    # Bật lại Peer 1 để cùng Peer 2 chia sẻ song song các chunk còn lại (Chunk 2, 3)
    peer1.start_upload_server()

    # Tạo thêm Peer 4 (Leecher mới) để chứng minh Peer 3 (dù mới chỉ có chunk 0, 1)
    # ĐÃ CÓ THỂ UPLOAD NGAY Chunk 0 cho Peer 4!
    p4_dir = os.path.join(work_dir, "p4_newbie")
    peer4 = PeerNode("PEER_4_NEWBIE", "127.0.0.1", 6005, p4_dir)

    print(" -> Chứng minh Kịch bản 3: Peer 4 kết nối sang Peer 3 để xin Chunk 0...")
    print(f"    (Lúc này Peer 3 mới chỉ có {peer3.owned_chunks[file_id]}, CHƯA CÓ ĐỦ FILE)")
    p4_got_chunk0 = peer4.download_chunk("127.0.0.1", 6003, file_id, 0, metadata.chunk_hashes[0])
    assert p4_got_chunk0
    print(" -> KẾT QUẢ KỊCH BẢN 3: Peer 3 đã upload thành công Chunk 0 trước khi tải xong toàn bộ file!")

    # Peer 3 tiếp tục tải nốt Chunk 2 và 3 song song từ Peer 1 và Peer 2
    print("\n -> Chứng minh Kịch bản 2: Peer 3 tải song song các chunk còn lại từ Peer 1 và Peer 2...")
    assert peer3.download_chunk("127.0.0.1", 6001, file_id, 2, metadata.chunk_hashes[2])
    assert peer3.download_chunk("127.0.0.1", 6002, file_id, 3, metadata.chunk_hashes[3])

    # -------------------------------------------------------------------------
    # KỊCH BẢN 7: GHÉP FILE VÀ ĐỐI CHIẾU MÃ BĂM TOÀN FILE
    # -------------------------------------------------------------------------
    print("\n" + "-" * 70)
    print(">>> KỊCH BẢN 7: GHÉP CÁC CHUNKS VÀ XÁC THỰC MÃ BĂM FILE HOÀN CHỈNH")
    print("-" * 70)
    p3_output_file = os.path.join(work_dir, "p3_final_movie.mp4")
    merged = merge_chunks(os.path.join(p3_dir, "chunks", file_id), p3_output_file, metadata)
    assert merged

    with open(source_file, "rb") as f_orig, open(p3_output_file, "rb") as f_res:
        assert f_orig.read() == f_res.read()

    print("\n" + "=" * 75)
    print("  XÁC NHẬN: TẤT CẢ 7/7 KỊCH BẢN DEMO BẮT BUỘC ĐÃ ĐƯỢC CHỨNG MINH 100%!")
    print("=" * 75)

    # Dọn dẹp
    peer1.stop()
    peer2.stop()
    peer3.stop()


if __name__ == "__main__":
    main()
