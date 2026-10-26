import os
import time
import socket
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional, Tuple, Set
import requests

from ..core.metadata import FileMetadata
from ..core.chunker import verify_chunk, merge_chunks
from .protocol import send_packet, recv_packet

# Cấu hình logging
logger = logging.getLogger("Peer")


class PeerNode:
    """
    Đại diện cho một Nút mạng P2P (Peer):
    - Đóng vai SERVER: Lắng nghe kết nối TCP để Upload các chunk cho peer khác.
    - Đóng vai CLIENT: Kết nối tới các peer khác để Download các chunk còn thiếu (hỗ trợ Tải song song).
    - Giao tiếp với Tracker: Đăng ký file, Announce bitfield và gửi Heartbeat.
    """
    def __init__(
        self,
        peer_id: str,
        host: str = "127.0.0.1",
        port: int = 6001,
        storage_dir: str = "./storage",
        tracker_url: str = "http://127.0.0.1:8000"
    ):
        self.peer_id = peer_id
        self.host = host
        self.port = port
        self.storage_dir = storage_dir
        self.tracker_url = tracker_url

        # Mảng bitfield lưu các chunk mình đang sở hữu theo từng file: {file_id: set(chunk_indices)}
        self.owned_chunks: Dict[str, Set[int]] = {}
        self._chunks_lock = threading.Lock()  # Khóa bảo vệ dữ liệu khi nhiều luồng cùng ghi

        # Trạng thái máy chủ socket lắng nghe upload
        self._server_sock: Optional[socket.socket] = None
        self._is_running = False
        self._server_thread: Optional[threading.Thread] = None
        self._heartbeat_thread: Optional[threading.Thread] = None

        # Đảm bảo thư mục lưu trữ tồn tại
        os.makedirs(self.storage_dir, exist_ok=True)

    def _log(self, level: str, msg: str):
        try:
            print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [{level}] [{self.peer_id}@{self.port}]: {msg}")
        except Exception:
            try:
                safe_msg = msg.encode("ascii", errors="replace").decode("ascii")
                print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [{level}] [{self.peer_id}@{self.port}]: {safe_msg}")
            except Exception:
                pass

    # =========================================================================
    # 1. PHẦN SERVER (UPLOAD WORKER - PHỤC VỤ CÁC MÁY KHÁC ĐẾN XIN DỮ LIỆU)
    # =========================================================================

    def start_upload_server(self):
        """Khởi động máy chủ Socket TCP để sẵn sàng upload các chunk khi có yêu cầu."""
        if self._is_running and self._server_sock:
            return
        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_sock.bind((self.host, self.port))
        self._server_sock.listen(20)
        self._is_running = True

        self._server_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._server_thread.start()
        self._log("INFO", f"Máy chủ Upload đã mở cổng lắng nghe tại {self.host}:{self.port}")

    def _listen_loop(self):
        while self._is_running:
            try:
                client_sock, addr = self._server_sock.accept()
                threading.Thread(target=self._handle_client, args=(client_sock, addr), daemon=True).start()
            except Exception:
                break

    def _handle_client(self, client_sock: socket.socket, addr: Tuple[str, int]):
        """Xử lý yêu cầu xin chunk từ một peer khác."""
        try:
            header, _ = recv_packet(client_sock)
            action = header.get("action")

            if action == "REQUEST_CHUNK":
                file_id = header.get("file_id")
                chunk_idx = header.get("chunk_idx")

                # Tìm file chunk trên ổ cứng của mình
                chunk_file = os.path.join(self.storage_dir, "chunks", file_id, f"chunk_{chunk_idx}.bin")
                
                if os.path.exists(chunk_file):
                    with open(chunk_file, "rb") as cf:
                        chunk_data = cf.read()

                    self._log("INFO", f"Đang UPLOAD Chunk {chunk_idx} của file '{file_id}' cho {addr} ({len(chunk_data):,} bytes)")
                    send_packet(client_sock, {"status": "SUCCESS", "chunk_idx": chunk_idx}, chunk_data)
                else:
                    self._log("WARNING", f"Peer {addr} xin Chunk {chunk_idx} nhưng tôi không có!")
                    send_packet(client_sock, {"status": "ERROR", "message": f"Chunk {chunk_idx} not found"})

        except Exception as e:
            self._log("ERROR", f"Lỗi khi truyền dữ liệu cho {addr}: {e}")
        finally:
            client_sock.close()

    def stop(self):
        """Dừng hoàn toàn máy chủ socket."""
        self._is_running = False
        if self._server_sock:
            try:
                self._server_sock.close()
            except Exception:
                pass
            self._server_sock = None
        self._log("INFO", "Máy chủ Upload đã đóng.")

    # =========================================================================
    # 2. PHẦN CLIENT (DOWNLOAD WORKER & TẢI SONG SONG)
    # =========================================================================

    def download_chunk(
        self,
        peer_ip: str,
        peer_port: int,
        file_id: str,
        chunk_idx: int,
        expected_hash: str,
        auto_announce: bool = True,
        timeout: float = 3.0
    ) -> bool:
        """
        Kết nối trực tiếp tới một Peer khác qua Socket TCP để tải về 1 chunk.
        Hỗ trợ timeout ngắn để phát hiện sớm sự cố sập nguồn của peer nguồn.
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)

        try:
            self._log("INFO", f"Kết nối tới {peer_ip}:{peer_port} để tải Chunk {chunk_idx}...")
            sock.connect((peer_ip, peer_port))

            # 1. Gửi gói tin yêu cầu
            req_header = {
                "action": "REQUEST_CHUNK",
                "file_id": file_id,
                "chunk_idx": chunk_idx
            }
            send_packet(sock, req_header)

            # 2. Nhận phản hồi
            resp_header, chunk_data = recv_packet(sock)

            if resp_header.get("status") != "SUCCESS":
                self._log("WARNING", f"Peer {peer_ip}:{peer_port} từ chối cung cấp: {resp_header.get('message')}")
                return False

            # 3. Soi mã băm (Kiểm tra tính toàn vẹn)
            if not verify_chunk(chunk_data, expected_hash):
                self._log("ERROR", f"CẢNH BÁO BẢO MẬT: Chunk {chunk_idx} từ {peer_ip}:{peer_port} SAI HASH (BỊ HỎNG HOẶC GIẢ MẠO)!")
                return False

            # 4. Lưu chunk chuẩn vào ổ cứng của mình
            chunk_dir = os.path.join(self.storage_dir, "chunks", file_id)
            os.makedirs(chunk_dir, exist_ok=True)
            chunk_file_path = os.path.join(chunk_dir, f"chunk_{chunk_idx}.bin")
            with open(chunk_file_path, "wb") as f:
                f.write(chunk_data)

            # Đánh dấu mình đã sở hữu chunk này (Dùng Lock để an toàn đa luồng)
            with self._chunks_lock:
                if file_id not in self.owned_chunks:
                    self.owned_chunks[file_id] = set()
                self.owned_chunks[file_id].add(chunk_idx)

            self._log("INFO", f"Tải & Xác thực THÀNH CÔNG Chunk {chunk_idx} ({len(chunk_data):,} bytes) từ {peer_ip}:{peer_port}")

            # BÁO DANH NGAY LẬP TỨC: Tôi đã có chunk này
            if auto_announce:
                self.announce_to_tracker(file_id)

            return True

        except (socket.timeout, ConnectionRefusedError, ConnectionResetError, ConnectionError, OSError) as e:
            self._log("WARNING", f"SỰ CỐ KẾT NỐI: Không thể tải Chunk {chunk_idx} từ {peer_ip}:{peer_port} ({e})")
            return False
        except Exception as e:
            self._log("ERROR", f"Lỗi không xác định khi tải Chunk {chunk_idx} từ {peer_ip}:{peer_port}: {e}")
            return False
        finally:
            sock.close()

    def download_chunk_with_failover(
        self,
        candidate_peers: List[dict],
        file_id: str,
        chunk_idx: int,
        expected_hash: str
    ) -> bool:
        """
        CƠ CHẾ DUNG LỖI & TỰ ĐỘNG CHUYỂN NGUỒN (Fault Tolerance & Failover):
        Thử tải từ Peer đầu tiên trong danh sách ứng viên.
        Nếu Peer đó bị sập nguồn / mất mạng hoặc gửi chunk hỏng -> TỰ ĐỘNG CHUYỂN SANG PEER TIẾP THEO!
        """
        for peer in candidate_peers:
            p_ip = peer["ip"]
            p_port = peer["port"]
            p_id = peer.get("peer_id", f"{p_ip}:{p_port}")

            self._log("INFO", f"[FAILOVER ENGINE] Đang thử tải Chunk {chunk_idx} từ nguồn: {p_id} ({p_ip}:{p_port})...")
            success = self.download_chunk(p_ip, p_port, file_id, chunk_idx, expected_hash, auto_announce=True, timeout=2.0)

            if success:
                return True
            else:
                self._log("WARNING", f"[FAILOVER TRIGGERED] Nguồn {p_id} thất bại! Tự động chuyển đổi sang nguồn dự phòng tiếp theo...")

        self._log("ERROR", f"[FAILOVER EXHAUSTED] Đã thử tất cả các nguồn nhưng không tải được Chunk {chunk_idx}!")
        return False

    def download_file_parallel(
        self,
        metadata: FileMetadata,
        output_file_path: str,
        max_threads: int = 4,
        override_peers: Optional[List[dict]] = None
    ) -> bool:
        """
        TẢI SONG SONG CÁC CHUNK TỪ NHIỀU PEERS CÙNG LÚC:
        1. Hỏi Tracker danh sách các Peer đang online và bitfield của họ.
        2. Phân công từng chunk cho peer phù hợp đang sở hữu chunk đó.
        3. Chạy đa luồng (ThreadPool) để tải đồng thời từ nhiều nguồn.
        4. Tự động ghép file khi tất cả các luồng hoàn thành.
        """
        file_id = metadata.file_id
        if override_peers is not None:
            peers = override_peers
        else:
            peers = self.get_peers_from_tracker(file_id)

        # Lọc bỏ chính mình khỏi danh sách nguồn tải
        available_peers = [p for p in peers if not (p["ip"] == self.host and p["port"] == self.port)]

        if not available_peers:
            self._log("ERROR", "Không tìm thấy peer nào khác trong mạng để tải!")
            return False

        self._log("INFO", f"Tìm thấy {len(available_peers)} nguồn tải từ Tracker. Bắt đầu lập lịch tải song song...")

        # Xác định những chunk mình còn thiếu
        with self._chunks_lock:
            current_owned = self.owned_chunks.get(file_id, set())
            missing_chunks = [i for i in range(metadata.num_chunks) if i not in current_owned]

        if not missing_chunks:
            self._log("INFO", "Tất cả các chunk đã có sẵn trên máy!")
            return merge_chunks(
                os.path.join(self.storage_dir, "chunks", file_id),
                output_file_path,
                metadata
            )

        # LẬP LỊCH PHÂN PHỐI NGUỒN TẢI:
        # Với mỗi chunk bị thiếu, chọn peer có giữ chunk đó (theo kiểu xoay vòng Round-Robin để cân bằng tải)
        download_tasks: List[Tuple[int, dict]] = []
        peer_assignment_counters = {p["peer_id"]: 0 for p in available_peers}

        for chunk_idx in missing_chunks:
            # Tìm danh sách những peer đang sở hữu chunk_idx này
            candidate_peers = [p for p in available_peers if chunk_idx in p.get("bitfield", [])]
            
            if not candidate_peers:
                self._log("ERROR", f"Không có peer nào trong mạng đang sở hữu Chunk {chunk_idx}!")
                return False

            # Chọn peer ít việc nhất trong danh sách ứng viên (Load balancing đơn giản)
            chosen_peer = min(candidate_peers, key=lambda p: peer_assignment_counters[p["peer_id"]])
            peer_assignment_counters[chosen_peer["peer_id"]] += 1
            # Đưa chosen_peer lên đầu, các peer còn lại làm nguồn dự phòng (Failover)
            ordered_candidates = [chosen_peer] + [p for p in candidate_peers if p != chosen_peer]
            download_tasks.append((chunk_idx, ordered_candidates))

        self._log("INFO", f"Kế hoạch tải song song {len(download_tasks)} chunks qua {max_threads} luồng (Kèm chế độ Failover tự động):")
        for c_idx, candidates in download_tasks:
            primary = candidates[0]
            backup_count = len(candidates) - 1
            self._log("INFO", f" -> Chunk {c_idx} ưu tiên từ {primary['peer_id']} ({primary['ip']}:{primary['port']}) [{backup_count} nguồn dự phòng]")

        # THỰC THI TẢI SONG SONG BẰNG ĐA LUỒNG (THREAD POOL)
        success = True
        with ThreadPoolExecutor(max_workers=max_threads) as executor:
            futures = []
            for c_idx, candidates in download_tasks:
                expected_hash = metadata.chunk_hashes[c_idx]
                f = executor.submit(
                    self.download_chunk_with_failover,
                    candidates,
                    file_id,
                    c_idx,
                    expected_hash
                )
                futures.append((c_idx, f))

            for c_idx, future in futures:
                chunk_ok = future.result()
                if not chunk_ok:
                    self._log("ERROR", f"Tải song song thất bại ở Chunk {c_idx}")
                    success = False

        if not success:
            return False

        # Ghép các chunks lại thành file hoàn chỉnh
        self._log("INFO", "Tất cả các chunk đã tải thành công! Tiến hành ghép file hoàn chỉnh...")
        chunks_dir = os.path.join(self.storage_dir, "chunks", file_id)
        return merge_chunks(chunks_dir, output_file_path, metadata)

    # =========================================================================
    # 3. GIAO TIẾP VỚI TRACKER (ĐIỀU PHỐI DANH BẠ)
    # =========================================================================

    def register_file_to_tracker(self, metadata: FileMetadata) -> bool:
        """Đăng ký file mới với Tracker."""
        try:
            url = f"{self.tracker_url}/register_file"
            res = requests.post(url, json=metadata.to_dict())
            if res.status_code == 201:
                self._log("INFO", f"Đã đăng ký file '{metadata.file_name}' lên Tracker.")
                return True
        except Exception as e:
            self._log("ERROR", f"Lỗi đăng ký file lên Tracker: {e}")
        return False

    def announce_to_tracker(self, file_id: str) -> bool:
        """Gửi danh sách chunk mình đang có (bitfield) lên Tracker."""
        try:
            url = f"{self.tracker_url}/announce"
            with self._chunks_lock:
                current_bitfield = list(sorted(self.owned_chunks.get(file_id, set())))

            payload = {
                "peer_id": self.peer_id,
                "file_id": file_id,
                "ip": self.host,
                "port": self.port,
                "bitfield": current_bitfield
            }
            res = requests.post(url, json=payload)
            if res.status_code == 200:
                self._log("INFO", f"Đã cập nhật bitfield lên Tracker: {current_bitfield}")
                return True
        except Exception as e:
            self._log("ERROR", f"Lỗi announce lên Tracker: {e}")
        return False

    def get_peers_from_tracker(self, file_id: str) -> List[dict]:
        """Hỏi Tracker danh sách các Peer đang có các chunk của file."""
        try:
            url = f"{self.tracker_url}/peers/{file_id}"
            res = requests.get(url)
            if res.status_code == 200:
                data = res.json()
                return data.get("peers", [])
        except Exception as e:
            self._log("ERROR", f"Lỗi tra cứu peers từ Tracker: {e}")
        return []

