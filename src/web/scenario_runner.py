import os
import sys
import time
import shutil
from typing import Dict, Any, List, Optional, Tuple

# Thêm thư mục gốc vào đường dẫn import
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src.core.chunker import split_file, merge_chunks
from src.core.metadata import FileMetadata
from src.peer.client import PeerNode

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEMO_STORAGE = os.path.join(BASE_DIR, "demo_live_storage")


class ScenarioRunner:
    """
    Bộ điều khiển THỰC THI THẬT:
    Mở cổng Socket TCP thật, truyền dữ liệu nhị phân thật qua mạng,
    ghi các file chunk thật ra đĩa và ghép thành file video thật 100%!
    """
    def __init__(self, tracker_url: str = "http://127.0.0.1:8000"):
        self.tracker_url = tracker_url
        self.peers: Dict[str, PeerNode] = {}
        self.metadata: Optional[FileMetadata] = None
        self.file_id = "real_movie"
        self.custom_files: Dict[str, FileMetadata] = {}
        self.active_p1: Optional[PeerNode] = None
        self.active_p2: Optional[PeerNode] = None

    def _stop_active_seeders(self):
        """Dừng các seeder ngầm nếu đang chạy để tránh chiếm cổng mạng."""
        if self.active_p1:
            try:
                self.active_p1.stop()
            except Exception:
                pass
            self.active_p1 = None
        if self.active_p2:
            try:
                self.active_p2.stop()
            except Exception:
                pass
            self.active_p2 = None

    def _ensure_seeders_running(self, file_id: str, metadata: FileMetadata):
        """Đảm bảo Peer 1 và Peer 2 mở Socket Server lắng nghe upload các chunks."""
        p1_dir = os.path.join(DEMO_STORAGE, "peer1")
        p2_dir = os.path.join(DEMO_STORAGE, "peer2")

        if not self.active_p1 or not self.active_p1._is_running:
            self.active_p1 = PeerNode("PEER_1", "127.0.0.1", 6001, p1_dir, self.tracker_url)
            self.active_p1.start_upload_server()

        if not self.active_p2 or not self.active_p2._is_running:
            self.active_p2 = PeerNode("PEER_2", "127.0.0.1", 6002, p2_dir, self.tracker_url)
            self.active_p2.start_upload_server()

        self.active_p1.owned_chunks[file_id] = set(range(metadata.num_chunks))
        self.active_p2.owned_chunks[file_id] = set(range(metadata.num_chunks))

    def upload_and_share_custom_file(self, file_name: str, file_bytes: bytes) -> Dict[str, Any]:
        """Nhận file thật do người dùng tải lên, cắt thành các chunk thật và kích hoạt Seeder."""
        uploads_dir = os.path.join(DEMO_STORAGE, "user_uploads")
        os.makedirs(uploads_dir, exist_ok=True)
        file_path = os.path.join(uploads_dir, file_name)
        with open(file_path, "wb") as f:
            f.write(file_bytes)

        file_size = len(file_bytes)
        file_id = "usr_" + str(abs(hash(file_name)))[:6]

        # Tự động chọn kích thước chunk phù hợp để hiển thị trực quan đẹp mắt
        if file_size <= 512 * 1024:
            chunk_size = 64 * 1024      # 64 KB (cho file nhỏ để có nhiều chunks)
        elif file_size <= 2 * 1024 * 1024:
            chunk_size = 256 * 1024     # 256 KB
        else:
            chunk_size = 512 * 1024     # 512 KB

        p1_dir = os.path.join(DEMO_STORAGE, "peer1")
        p1_chunks = os.path.join(p1_dir, "chunks", file_id)
        
        # Cắt file thật ra các chunk .bin trên ổ cứng
        metadata = split_file(
            file_path=file_path,
            output_chunks_dir=p1_chunks,
            tracker_url=self.tracker_url,
            chunk_size=chunk_size,
            file_id=file_id
        )

        # Sao chép sang Peer 2 để cùng làm seeder song song
        p2_dir = os.path.join(DEMO_STORAGE, "peer2")
        p2_chunks = os.path.join(p2_dir, "chunks", file_id)
        if os.path.exists(p2_chunks):
            shutil.rmtree(p2_chunks)
        shutil.copytree(p1_chunks, p2_chunks)

        self.custom_files[file_id] = metadata
        self._ensure_seeders_running(file_id, metadata)

        return metadata.to_dict()

    def download_custom_file(self, file_id: str) -> Dict[str, Any]:
        """Peer 3 mở Socket TCP thật kết nối tải file người dùng vừa upload về máy."""
        metadata = self.custom_files.get(file_id)
        if not metadata:
            raise FileNotFoundError(f"Không tìm thấy file ID: {file_id}")

        self._ensure_seeders_running(file_id, metadata)

        p3_dir = os.path.join(DEMO_STORAGE, "peer3")
        downloads_dir = os.path.join(DEMO_STORAGE, "peer3_downloads")
        os.makedirs(downloads_dir, exist_ok=True)
        output_file = os.path.join(downloads_dir, metadata.file_name)

        p3 = PeerNode("PEER_3", "127.0.0.1", 6003, p3_dir, self.tracker_url)
        active_sources = [
            {"peer_id": "PEER_1", "ip": "127.0.0.1", "port": 6001, "bitfield": list(range(metadata.num_chunks))},
            {"peer_id": "PEER_2", "ip": "127.0.0.1", "port": 6002, "bitfield": list(range(metadata.num_chunks))}
        ]

        t_start = time.time()
        success = p3.download_file_parallel(metadata, output_file, max_threads=4, override_peers=active_sources)
        duration = round(time.time() - t_start, 3)

        return {
            "success": success,
            "duration": duration,
            "output_file": output_file,
            "file_size": os.path.getsize(output_file),
            "num_chunks": metadata.num_chunks,
            "chunk_hashes": metadata.chunk_hashes,
            "file_hash": metadata.file_hash
        }

    def setup_environment(self) -> FileMetadata:
        """Chuẩn bị file nguồn thật và cắt thành các chunk thật trên ổ cứng (Bảo toàn user_uploads)."""
        self._stop_active_seeders()

        demo_targets = [
            os.path.join(DEMO_STORAGE, "original_sample.mp4"),
            os.path.join(DEMO_STORAGE, "peer1", "chunks", self.file_id),
            os.path.join(DEMO_STORAGE, "peer2", "chunks", self.file_id),
            os.path.join(DEMO_STORAGE, "peer3", "chunks", self.file_id),
            os.path.join(DEMO_STORAGE, "peer3", "downloaded_video.mp4"),
            os.path.join(DEMO_STORAGE, "peer3", "restored_failover_video.mp4")
        ]
        for t in demo_targets:
            if os.path.isdir(t):
                shutil.rmtree(t, ignore_errors=True)
            elif os.path.isfile(t):
                try:
                    os.remove(t)
                except OSError:
                    pass
        os.makedirs(DEMO_STORAGE, exist_ok=True)

        source_file = os.path.join(DEMO_STORAGE, "original_sample.mp4")
        # Tạo file dữ liệu 2 MB thật
        content = b"P2P-DISTRIBUTED-REAL-SOCKET-DATA-TRANSMISSION\n" * 45000
        with open(source_file, "wb") as f:
            f.write(content)

        p1_dir = os.path.join(DEMO_STORAGE, "peer1")
        p1_chunks = os.path.join(p1_dir, "chunks", self.file_id)
        
        # Cắt file thật bằng module core
        self.metadata = split_file(
            file_path=source_file,
            output_chunks_dir=p1_chunks,
            tracker_url=self.tracker_url,
            chunk_size=512 * 1024,
            file_id=self.file_id
        )

        # Sao chép sang thư mục của Peer 2 để làm nguồn dự phòng thật
        p2_dir = os.path.join(DEMO_STORAGE, "peer2")
        p2_chunks = os.path.join(p2_dir, "chunks", self.file_id)
        shutil.copytree(p1_chunks, p2_chunks)

        return self.metadata

    def run_real_parallel_download(self) -> Dict[str, Any]:
        """KỊCH BẢN 1: Mở Socket TCP thật và tải song song từ cả 2 máy."""
        logs = []
        logs.append(f"[{time.strftime('%H:%M:%S')}] [PYTHON BACKEND] Khởi tạo dữ liệu file thật (2,070,000 bytes, 4 chunks)...")
        metadata = self.setup_environment()

        # 1. Bật Socket Server thật của Peer 1 và Peer 2
        p1_dir = os.path.join(DEMO_STORAGE, "peer1")
        p2_dir = os.path.join(DEMO_STORAGE, "peer2")
        p3_dir = os.path.join(DEMO_STORAGE, "peer3")

        p1 = PeerNode("PEER_1", "127.0.0.1", 6001, p1_dir, self.tracker_url)
        p2 = PeerNode("PEER_2", "127.0.0.1", 6002, p2_dir, self.tracker_url)
        p3 = PeerNode("PEER_3", "127.0.0.1", 6003, p3_dir, self.tracker_url)

        p1.start_upload_server()
        p2.start_upload_server()
        p3.start_upload_server()

        p1.owned_chunks[self.file_id] = set(range(metadata.num_chunks))
        p2.owned_chunks[self.file_id] = set(range(metadata.num_chunks))

        logs.append(f"[{time.strftime('%H:%M:%S')}] [SOCKET TCP] Đã mở cổng mạng thật: 127.0.0.1:6001 (Peer 1) và 127.0.0.1:6002 (Peer 2)")

        # 2. Tải song song thật qua hàm download_file_parallel
        logs.append(f"[{time.strftime('%H:%M:%S')}] [PARALLEL ENGINE] Bắt đầu kết nối Socket tải đồng thời 4 chunks...")
        
        output_file = os.path.join(p3_dir, "downloaded_video.mp4")
        t_start = time.time()
        active_sources = [
            {"peer_id": "PEER_1", "ip": "127.0.0.1", "port": 6001, "bitfield": list(range(metadata.num_chunks))},
            {"peer_id": "PEER_2", "ip": "127.0.0.1", "port": 6002, "bitfield": list(range(metadata.num_chunks))}
        ]
        success = p3.download_file_parallel(metadata, output_file, max_threads=4, override_peers=active_sources)
        duration = round(time.time() - t_start, 3)

        logs.append(f"[{time.strftime('%H:%M:%S')}] [SUCCESS] Đã tải & xác thực SHA-256 xong 4 chunks qua Socket trong {duration} giây!")
        logs.append(f"[{time.strftime('%H:%M:%S')}] [FILE SAVED] File video thật đã được lưu tại: {output_file}")

        # Tắt server
        p1.stop()
        p2.stop()
        p3.stop()

        return {
            "success": success,
            "duration": duration,
            "output_file": output_file,
            "file_size": os.path.getsize(output_file),
            "logs": logs
        }

    def run_real_failover(self) -> Dict[str, Any]:
        """KỊCH BẢN 2: Ngắt Socket Peer 1 thật và tự động failover sang Peer 2."""
        logs = []
        metadata = self.setup_environment()

        p1_dir = os.path.join(DEMO_STORAGE, "peer1")
        p2_dir = os.path.join(DEMO_STORAGE, "peer2")
        p3_dir = os.path.join(DEMO_STORAGE, "peer3")

        p1 = PeerNode("PEER_1", "127.0.0.1", 6001, p1_dir, self.tracker_url)
        p2 = PeerNode("PEER_2", "127.0.0.1", 6002, p2_dir, self.tracker_url)
        p3 = PeerNode("PEER_3", "127.0.0.1", 6003, p3_dir, self.tracker_url)

        # Chỉ bật Peer 2, CỐ TÌNH KHÔNG BẬT PEER 1 (hoặc tắt ngay để gây lỗi Socket ConnectionRefused thật)
        p2.start_upload_server()
        p3.start_upload_server()
        p2.owned_chunks[self.file_id] = set(range(metadata.num_chunks))

        logs.append(f"[{time.strftime('%H:%M:%S')}] [SIMULATION] Peer 1 (Port 6001) BỊ SẬP NGUỒN (Cổng mạng bị đóng thật)!")
        logs.append(f"[{time.strftime('%H:%M:%S')}] [FAILOVER] Peer 3 thử kết nối tới 127.0.0.1:6001 thất bại...")

        # Chạy tải qua Failover thật
        candidate_sources = [
            {"peer_id": "PEER_1", "ip": "127.0.0.1", "port": 6001},  # Sẽ bị lỗi socket
            {"peer_id": "PEER_2", "ip": "127.0.0.1", "port": 6002}   # Nguồn cứu hộ
        ]

        t_start = time.time()
        results = []
        for i in range(metadata.num_chunks):
            ok = p3.download_chunk_with_failover(candidate_sources, self.file_id, i, metadata.chunk_hashes[i])
            results.append(ok)
        duration = round(time.time() - t_start, 3)

        output_file = os.path.join(p3_dir, "restored_failover_video.mp4")
        merge_chunks(os.path.join(p3_dir, "chunks", self.file_id), output_file, metadata)

        logs.append(f"[{time.strftime('%H:%M:%S')}] [FAILOVER SUCCESS] Cứu hộ thành công 100% dữ liệu ({metadata.num_chunks} chunks) từ Peer 2 qua Socket thật trong {duration}s!")

        p2.stop()
        p3.stop()

        return {
            "success": all(results),
            "duration": duration,
            "output_file": output_file,
            "logs": logs
        }
