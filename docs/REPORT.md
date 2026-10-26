# BÁO CÁO KỸ THUẬT: HỆ THỐNG CHIA SẺ FILE P2P MÔ PHỎNG BITTORRENT (DS02)

## 1. Giới thiệu tổng quan
Hệ thống mô phỏng giao thức BitTorrent hoạt động phân tán thực sự trên mạng TCP/IP:
- **FastAPI Central Tracker**: Quản lý danh sách Peer và Metadata (SHA-256 chunk hashes), hoàn toàn không lưu trữ hay phân phối dữ liệu file nhị phân.
- **P2P Socket Nodes**: Giao tiếp trực tiếp ngang hàng qua TCP Sockets với giao thức nhị phân tự định nghĩa (Framing Protocol).
- **Chunking & SHA-256**: File được chia thành các mảnh cố định 512 KB, mã băm SHA-256 xác thực tính toàn vẹn độc lập cho từng mảnh.
- **Multi-Peer Parallel Download**: Tải song song đa luồng từ nhiều Seeder đồng thời.
- **Fault Tolerance & Dynamic Failover**: Phát hiện Peer chết qua Socket Timeout và tự động chuyển giao tải sang Seeder dự phòng; phát hiện chunk hỏng/giả mạo và tự loại bỏ, tải lại từ Seeder chuẩn.
- **Real-time Web Dashboard**: Giao diện trực quan hoá Piece Map, tiến độ tải, log sự kiện socket thời gian thực.

---

## 2. Kiến trúc hệ thống
```
                    +-----------------------------+
                    |    CENTRAL TRACKER (REST)   |
                    |      Port 8000 (FastAPI)    |
                    |  (Metadata & Peer Registry) |
                    +--------------+--------------+
                                   ^
            Register / Announce    |  Heartbeat / Peer Discovery
        +--------------------------+--------------------------+
        |                          |                          |
        v                          v                          v
+---------------+          +---------------+          +---------------+
|    PEER 1     |<========>|    PEER 2     |<========>|    PEER 3     |
|   Port 6001   |  Direct  |   Port 6002   |  Direct  |   Port 6003   |
| (Seeder A)    | TCP Sockets (Seeder B)   | TCP Sockets (Leecher)    |
+---------------+          +---------------+          +---------------+
```

---

## 3. Giao thức nhị phân Framing Protocol (TCP)
Header cố định 14 bytes:
`MAGIC (4B: 0x50325031) | Header Length (2B: H) | Payload Length (4B: I) | Reserved (4B: 0x00)`
- **Header**: JSON metadata (`action`, `file_id`, `chunk_index`, `status`, `error`).
- **Payload**: Dữ liệu nhị phân của chunk (`bytes`).

---

## 4. Hướng dẫn khởi chạy
### Cách 1: Khởi chạy trực tiếp (Windows/Linux)
```bash
pip install -r requirements.txt
python -m uvicorn src.tracker.server:app --port 8000
```
Truy cập: `http://localhost:8000/dashboard`

### Cách 2: Khởi chạy qua Docker Compose
```bash
cd deploy
docker compose up --build
```

### Cách 3: Chạy bộ kiểm thử tự động
```bash
python -m unittest tests/test_step1.py
python -m unittest tests/test_step2.py
python -m unittest tests/test_step3.py
python -m unittest tests/test_step4.py
python -m unittest tests/test_step5.py
```
