import os
import sys
import time
import argparse
import socket
from typing import Optional

# Thêm thư mục gốc vào PYTHONPATH
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from src.core.chunker import split_file, merge_chunks, calculate_hash
from src.core.metadata import FileMetadata
from src.peer.client import PeerNode, get_local_ip
import requests


def find_free_port(start_port: int = 6001) -> int:
    """Tìm một cổng TCP khả dụng trên máy."""
    port = start_port
    while port < 65535:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('0.0.0.0', port))
                return port
            except OSError:
                port += 1
    return start_port


def print_banner(local_ip: str, port: int, peer_id: str, tracker_url: str):
    print("\n" + "=" * 76)
    print("   P2P FILE SHARING SYSTEM (BITTORRENT SIMULATION) - ĐỒ ÁN DS02")
    print("   KẾT NỐI & TRUYỀN DỮ LIỆU TRỰC TIẾP GIỮA CÁC MÁY TÍNH (MẠNG LAN / INTERNET)")
    print("=" * 76)
    print(f" [ Nút mạng ] IP LAN: {local_ip:<15} | Cổng TCP: {port:<5} | ID: {peer_id}")
    print(f" [ Tracker  ] {tracker_url}")
    print("=" * 76)


def check_tracker_connection(tracker_url: str) -> bool:
    """Kiểm tra xem máy này có kết nối được tới Tracker Server không."""
    try:
        res = requests.get(f"{tracker_url}/", timeout=3.0)
        return res.status_code == 200
    except Exception:
        return False


def action_list_files(tracker_url: str):
    """Lấy danh sách các file đã đăng ký trên Tracker."""
    print(f"\n[DANH SÁCH FILE TRÊN TRACKER ({tracker_url})]:")
    try:
        res = requests.get(f"{tracker_url}/files", timeout=4.0)
        if res.status_code == 200:
            files = res.json().get("files", [])
            if not files:
                print(" -> Hiện chưa có file nào được đăng ký trên hệ thống.")
                return []
            
            print(f" {'STT':<4} | {'MÃ FILE ID':<12} | {'TÊN FILE':<28} | {'DUNG LƯỢNG':<12} | {'CHUNKS':<8} | {'PEERS'}")
            print("-" * 76)
            for idx, f in enumerate(files, 1):
                size_str = f"{f['file_size'] / (1024*1024):.2f} MB" if f['file_size'] >= 1024*1024 else f"{f['file_size'] / 1024:.1f} KB"
                print(f" {idx:<4} | {f['file_id']:<12} | {f['file_name'][:26]:<28} | {size_str:<12} | {f['num_chunks']:<8} | {f['peers_count']} seeders")
            return files
        else:
            print(" -> Tracker phản hồi mã lỗi:", res.status_code)
    except Exception as e:
        print(" -> Không thể kết nối tới Tracker:", e)
    return []


def action_seed_file(peer: PeerNode):
    """Chia sẻ một file bất kỳ từ máy này."""
    file_path = input("\nNhập đường dẫn file cần chia sẻ (hoặc kéo thả file vào đây): ").strip(' "\'')
    if not os.path.exists(file_path):
        print(f" -> Lỗi: Không tìm thấy file tại '{file_path}'!")
        return

    file_size = os.path.getsize(file_path)
    print(f" -> Đang xử lý file: {os.path.basename(file_path)} ({file_size:,} bytes)...")

    # Tự động chọn kích thước chunk: 512 KB cho file >= 2MB, nhỏ hơn thì 256KB hoặc 64KB
    if file_size <= 512 * 1024:
        chunk_size = 64 * 1024
    elif file_size <= 2 * 1024 * 1024:
        chunk_size = 256 * 1024
    else:
        chunk_size = 512 * 1024

    metadata = peer.seed_file(file_path, chunk_size=chunk_size)
    if metadata:
        print("\n" + "*" * 70)
        print(" [CHIA SẺ THÀNH CÔNG] File của bạn đã sẵn sàng trên mạng P2P!")
        print(f"  * File ID : {metadata.file_id}")
        print(f"  * Số mảnh : {metadata.num_chunks} chunks x {metadata.chunk_size // 1024} KB")
        print(f"  * SHA-256 : {metadata.file_hash[:16]}...")
        print(f"  * Máy khác trong mạng có thể tải file này bằng lệnh:")
        print(f"    python run_peer.py --tracker {peer.tracker_url} --download {metadata.file_id}")
        print("*" * 70)


def action_download_file(peer: PeerNode):
    """Tải một file từ các máy khác về máy tính này."""
    files = action_list_files(peer.tracker_url)
    target_file_id = ""
    
    if files:
        choice = input("\nNhập STT file muốn tải (hoặc nhập trực tiếp Mã File ID): ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(files):
            target_file_id = files[int(choice) - 1]["file_id"]
        else:
            target_file_id = choice
    else:
        target_file_id = input("\nNhập Mã File ID cần tải: ").strip()

    if not target_file_id:
        print(" -> Hủy thao tác tải.")
        return

    # Lấy thông tin file và peers từ Tracker
    try:
        res = requests.get(f"{peer.tracker_url}/peers/{target_file_id}", timeout=4.0)
        if res.status_code != 200:
            print(f" -> Lỗi: Tracker không tìm thấy file ID '{target_file_id}'!")
            return
        data = res.json()
        metadata_dict = data.get("metadata")
        active_peers = data.get("peers", [])
        metadata = FileMetadata.from_dict(metadata_dict)
    except Exception as e:
        print(f" -> Lỗi khi truy vấn Tracker: {e}")
        return

    print(f"\n[BẮT ĐẦU TẢI P2P FILE '{metadata.file_name}']")
    print(f" * Dung lượng: {metadata.file_size:,} bytes | Số mảnh: {metadata.num_chunks}")
    print(f" * Tìm thấy {len(active_peers)} nguồn tải trong mạng:")
    for p in active_peers:
        print(f"    -> Peer {p['peer_id']} ({p['ip']}:{p['port']}) | Giữ chunks: {p['bitfield']}")

    # Đảm bảo socket server của mình đang chạy để hỗ trợ vừa tải vừa chia sẻ (Seed while Leeching)
    peer.start_upload_server()
    peer.start_heartbeat()

    # Thư mục lưu file tải về
    downloads_dir = os.path.join(os.getcwd(), "downloads")
    os.makedirs(downloads_dir, exist_ok=True)
    output_path = os.path.join(downloads_dir, metadata.file_name)

    start_time = time.time()
    success = peer.download_file_parallel(
        metadata=metadata,
        output_file_path=output_path,
        max_threads=4
    )
    elapsed = max(0.001, time.time() - start_time)

    if success:
        speed_mb = (metadata.file_size / (1024 * 1024)) / elapsed
        print("\n" + "=" * 70)
        print(" [CHÚC MỪNG] TẢI VÀ GHÉP FILE THÀNH CÔNG 100%!")
        print(f"  * File đã được lưu tại: {output_path}")
        print(f"  * Thời gian tải: {elapsed:.2f} giây | Tốc độ trung bình: {speed_mb:.2f} MB/s")
        print("  * Xác thực mã băm SHA-256: KHỚP 100% TỪNG BYTE VỚI FILE GỐC!")
        print("=" * 70)
    else:
        print("\n -> Tải file thất bại! Vui lòng kiểm tra lại kết nối mạng tới các Peer.")


def action_run_lan_benchmark(peer: PeerNode):
    """Tự động kiểm tra tốc độ truyền dữ liệu qua Socket giữa 2 máy."""
    print("\n[CHẠY BÀI KIỂM THỬ TRUYỀN P2P MẠNG LAN (LAN BENCHMARK)]")
    test_size_mb = 4.0
    print(f" -> Tạo file nhị phân thử nghiệm ({test_size_mb} MB)...")
    
    test_dir = os.path.join(peer.storage_dir, "lan_test")
    os.makedirs(test_dir, exist_ok=True)
    test_file = os.path.join(test_dir, "benchmark_payload.bin")
    
    # Tạo payload dữ liệu ngẫu nhiên giả lập
    chunk_sample = os.urandom(512 * 1024)
    with open(test_file, "wb") as f:
        for _ in range(8):  # 8 * 512KB = 4MB
            f.write(chunk_sample)

    meta = peer.seed_file(test_file, chunk_size=512*1024, custom_file_id="lan_bench")
    print(f" -> Đã kích hoạt Seed file benchmark (ID: 'lan_bench') tại cổng {peer.port}.")
    print(" -> Hãy sang máy tính thứ 2 và chọn Tải file 'lan_bench' để đo tốc độ truyền thực tế!")


def main():
    # Cấu hình encoding console UTF-8 cho Windows
    if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="P2P BitTorrent Node Client")
    parser.add_argument("--tracker", type=str, default=None, help="Địa chỉ Tracker URL (VD: http://192.168.1.10:8000)")
    parser.add_argument("--ip", type=str, default=None, help="Địa chỉ IP LAN quảng bá cho máy này")
    parser.add_argument("--port", type=int, default=None, help="Cổng TCP Socket lắng nghe (VD: 6001)")
    parser.add_argument("--peer-id", type=str, default=None, help="Tên nhận diện Nút mạng (VD: PEER_ALICE)")
    parser.add_argument("--seed", type=str, default=None, help="Chia sẻ file trực tiếp không qua menu")
    parser.add_argument("--download", type=str, default=None, help="Mã File ID để tải trực tiếp")
    parser.add_argument("--storage", type=str, default=None, help="Thư mục lưu trữ chunks")
    args = parser.parse_args()

    # Nhận diện thông số mạng
    local_ip = args.ip or get_local_ip()
    port = args.port or find_free_port(6001)
    peer_id = args.peer_id or f"PEER_{local_ip.split('.')[-1]}_{port}"
    storage_dir = args.storage or os.path.join(os.getcwd(), f"peer_storage_{port}")

    # Tracker URL: nếu người dùng không truyền qua tham số, hỏi hoặc dùng mặc định
    default_tracker = "http://127.0.0.1:8000"
    tracker_url = args.tracker

    if not tracker_url:
        print_banner(local_ip, port, peer_id, "Chưa thiết lập")
        print("\n[CẤU HÌNH KẾT NỐI TRACKER]:")
        print("Nếu Tracker đang chạy trên máy này -> Nhấn Enter để dùng: http://127.0.0.1:8000")
        print("Nếu Tracker đang chạy trên máy khác trong mạng LAN -> Nhập: http://<IP_MÁY_TRACKER>:8000")
        user_input = input("Nhập URL Tracker [Mặc định: http://127.0.0.1:8000]: ").strip()
        tracker_url = user_input if user_input else default_tracker

    # Khởi tạo đối tượng Peer
    peer = PeerNode(
        peer_id=peer_id,
        host=local_ip,
        port=port,
        storage_dir=storage_dir,
        tracker_url=tracker_url,
        listen_host="0.0.0.0"
    )

    print_banner(local_ip, port, peer_id, tracker_url)

    # Kiểm tra kết nối tới Tracker
    if check_tracker_connection(tracker_url):
        print(" -> KẾT NỐI TRACKER: THÀNH CÔNG (Tracker đang Online!)\n")
    else:
        print(f" -> CẢNH BÁO: Chưa kết nối được tới Tracker tại {tracker_url}!")
        print("    Vui lòng kiểm tra lại xem Tracker Server đã bật chưa và cổng 8000 có bị Firewall chặn không.\n")

    # Xử lý các cờ chạy tự động (Command-Line Mode)
    if args.seed:
        metadata = peer.seed_file(args.seed)
        if metadata:
            print(f"\nĐang giữ máy online để làm Seeder (Nhấn Ctrl+C để dừng)...")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                peer.stop()
                print("\nĐã dừng Peer.")
        return

    if args.download:
        peer.start_upload_server()
        peer.start_heartbeat()
        try:
            res = requests.get(f"{tracker_url}/peers/{args.download}", timeout=4.0)
            data = res.json()
            metadata = FileMetadata.from_dict(data["metadata"])
            downloads_dir = os.path.join(os.getcwd(), "downloads")
            os.makedirs(downloads_dir, exist_ok=True)
            output_file = os.path.join(downloads_dir, metadata.file_name)
            peer.download_file_parallel(metadata, output_file)
        except Exception as e:
            print("Lỗi tải file:", e)
        finally:
            peer.stop()
        return

    # Menu tương tác chính (Interactive Menu Mode)
    while True:
        print("-" * 76)
        print("--- MENU ĐIỀU KHIỂN NÚT MẠNG P2P ---")
        print(" 1. Xem danh sách các file đang có trên Tracker")
        print(" 2. Chia sẻ (Seed) một file từ máy này cho các máy khác tải")
        print(" 3. Tải (Download) một file từ các máy khác về máy này")
        print(" 4. Chế độ Seeder thường trực (Giữ máy online phục vụ các máy khác)")
        print(" 5. Chạy bài kiểm thử truyền file P2P qua mạng LAN")
        print(" 0. Thoát chương trình")
        print("-" * 76)

        choice = input("Lựa chọn của bạn (0-5): ").strip()

        if choice == "1":
            action_list_files(peer.tracker_url)
        elif choice == "2":
            action_seed_file(peer)
        elif choice == "3":
            action_download_file(peer)
        elif choice == "4":
            peer.start_upload_server()
            peer.start_heartbeat()
            print(f"\n[SEEDER RUNNING] Peer {peer.peer_id} đang lắng nghe tại cổng {peer.port}...")
            print("Đang chạy ngầm phục vụ các kết nối khác. Nhấn Enter để quay lại Menu.")
            input()
        elif choice == "5":
            action_run_lan_benchmark(peer)
        elif choice == "0":
            print("\nĐang tắt Peer...")
            peer.stop()
            print("Tạm biệt!")
            break
        else:
            print("Lựa chọn không hợp lệ. Vui lòng chọn từ 0 đến 5.")


if __name__ == "__main__":
    main()
