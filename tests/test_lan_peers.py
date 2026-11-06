import os
import sys
import time
import argparse
import socket

# Thêm thư mục gốc vào đường dẫn import
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.chunker import split_file, merge_chunks, calculate_hash
from src.core.metadata import FileMetadata
from src.peer.client import PeerNode, get_local_ip
import requests


def main():
    if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="Kiểm thử truyền file P2P qua mạng LAN giữa 2 máy tính")
    parser.add_argument("--role", choices=["seeder", "leecher"], required=True, help="Vai trò: 'seeder' (Máy 1) hoặc 'leecher' (Máy 2)")
    parser.add_argument("--tracker", default="http://127.0.0.1:8000", help="Địa chỉ Tracker URL (VD: http://192.168.1.10:8000)")
    parser.add_argument("--port", type=int, default=6001, help="Cổng P2P socket (mặc định 6001)")
    args = parser.parse_args()

    local_ip = get_local_ip()
    file_id = "lan_test_file"

    print("=" * 70)
    print("  BÀI KIỂM THỬ TRUYỀN FILE P2P GIỮA 2 MÁY TÍNH QUA MẠNG LAN")
    print(f"  * Vai trò: {args.role.upper()} | IP LAN: {local_ip}:{args.port}")
    print(f"  * Tracker: {args.tracker}")
    print("=" * 70)

    work_dir = os.path.join(os.path.dirname(__file__), f"temp_lan_{args.role}")
    os.makedirs(work_dir, exist_ok=True)

    peer = PeerNode(
        peer_id=f"PEER_LAN_{args.role.upper()}",
        host=local_ip,
        port=args.port,
        storage_dir=work_dir,
        tracker_url=args.tracker,
        listen_host="0.0.0.0"
    )

    if args.role == "seeder":
        # MÁY 1 (SEEDER): Tạo file mẫu 2.5 MB, cắt thành 5 chunks và chia sẻ
        source_file = os.path.join(work_dir, "lan_source_video.mp4")
        content = b"P2P-LAN-DISTRIBUTED-SYSTEMS-REAL-CROSS-MACHINE-TEST\n" * 50000
        with open(source_file, "wb") as f:
            f.write(content)
        print(f"\n[1] Đã tạo file nguồn mẫu: {source_file} ({len(content):,} bytes)")

        metadata = peer.seed_file(source_file, chunk_size=512 * 1024, custom_file_id=file_id)
        print(f"\n[2] Máy 1 đang SEED file '{file_id}' qua Socket tại {local_ip}:{args.port}")
        print(" -> Bây giờ hãy sang MÁY 2 (Leecher) và chạy lệnh sau:")
        print(f"    python tests/test_lan_peers.py --role leecher --tracker {args.tracker} --port 6002")
        print("\n(Nhấn Ctrl+C để dừng seeder sau khi Máy 2 tải xong)...")

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            peer.stop()
            print("\nĐã dừng Seeder.")

    elif args.role == "leecher":
        # MÁY 2 (LEECHER): Hỏi Tracker tìm Seeder và tải về qua Socket
        print(f"\n[1] Đang hỏi Tracker ({args.tracker}) thông tin file '{file_id}'...")
        try:
            res = requests.get(f"{args.tracker}/peers/{file_id}", timeout=5.0)
            if res.status_code != 200:
                print(f" -> Lỗi: Chưa tìm thấy file '{file_id}' trên Tracker! Bạn đã bật Seeder trên Máy 1 chưa?")
                return
            data = res.json()
            metadata = FileMetadata.from_dict(data["metadata"])
            peers = data["peers"]
            print(f" -> Tracker phản hồi: Tìm thấy {len(peers)} seeder(s) trong mạng:")
            for p in peers:
                print(f"    * {p['peer_id']} ({p['ip']}:{p['port']}) sở hữu chunks: {p['bitfield']}")
        except Exception as e:
            print(f" -> Không thể kết nối tới Tracker: {e}")
            return

        peer.start_upload_server()
        peer.start_heartbeat()

        output_file = os.path.join(work_dir, "lan_downloaded_video.mp4")
        print(f"\n[2] Bắt đầu tải song song qua Socket từ các máy khác...")
        start_t = time.time()
        ok = peer.download_file_parallel(metadata, output_file, max_threads=4)
        elapsed = max(0.001, time.time() - start_t)

        if ok and os.path.exists(output_file):
            with open(output_file, "rb") as f:
                downloaded_hash = calculate_hash(f.read())

            if downloaded_hash == metadata.file_hash:
                speed_mb = (metadata.file_size / (1024 * 1024)) / elapsed
                print("\n" + "=" * 70)
                print("  CHÚC MỪNG: BÀI TEST TRUYỀN P2P QUA MẠNG LAN THÀNH CÔNG 100%!")
                print(f"  * File tải về: {output_file}")
                print(f"  * Dung lượng : {metadata.file_size:,} bytes")
                print(f"  * Tốc độ     : {speed_mb:.2f} MB/s (Thời gian: {elapsed:.2f}s)")
                print(f"  * SHA-256    : KHỚP 100% VỚI MÁY NGUỒN!")
                print("=" * 70)
            else:
                print("\n -> LỖI: Mã băm file tải về không khớp!")
        else:
            print("\n -> Tải thất bại!")

        peer.stop()


if __name__ == "__main__":
    main()
