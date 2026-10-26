# P2P File Sharing System (BitTorrent Simulation) - Topic DS02

Hệ thống chia sẻ file ngang hàng P2P mô phỏng giao thức BitTorrent cho môn học Hệ thống phân tán.

## Cấu trúc thư mục dự án

```text
├── src/
│   ├── core/
│   │   ├── __init__.py
│   │   ├── metadata.py       # Định nghĩa cấu trúc Metadata (.json)
│   │   └── chunker.py        # Module cắt file, băm SHA-256, kiểm tra và ghép file
│   ├── tracker/
│   │   ├── __init__.py
│   │   └── server.py         # Tracker Server (FastAPI REST API điều phối danh bạ)
│   └── peer/
│       ├── __init__.py
│       ├── protocol.py       # Giao thức truyền tin nhị phân qua TCP Socket
│       └── client.py         # Nút mạng Peer (Vừa là Server Upload vừa là Client Download)
├── tests/
│   ├── test_step1.py         # Kiểm thử Bước 1: Cắt, băm, ghép và phát hiện lỗi
│   ├── test_step2.py         # Kiểm thử Bước 2: Tracker Server, Announce, Heartbeat & Fault Tolerance
│   ├── test_step3.py         # Kiểm thử Bước 3: Truyền file P2P trực tiếp qua Socket giữa 2 Peer
│   ├── test_step4.py         # Kiểm thử Bước 4: Tải song song đa luồng & Vừa tải vừa cho (3 Peers)
│   ├── test_step5.py         # Kiểm thử Bước 5: Trọn bộ 7 kịch bản Demo bắt buộc (Failover, Sập nguồn, Chunk hỏng)
│   └── temp_step1/           # Thư mục dữ liệu sinh ra khi chạy test
└── README.md
```

## Hướng dẫn chạy thử nghiệm

### 🌐 KHỞI CHẠY GIAO DIỆN WEB UI DASHBOARD (Dành cho Demo chấm thi)
Chạy lệnh khởi động Tracker Server:
```bash
uvicorn src.tracker.server:app --host 127.0.0.1 --port 8000 --reload
```
Sau đó mở trình duyệt web (Chrome, Edge, Cốc Cốc) và truy cập:
👉 **`http://127.0.0.1:8000/dashboard`** (hoặc `http://127.0.0.1:8000/`)

*Trên giao diện Web, bạn có thể:*
- Xem **bản đồ các mảnh (Chunk Piece Map)** nhảy màu trực quan giống uTorrent.
- Bấm nút **"1. Tải song song"** để xem các luồng tải song song từ 2 máy.
- Bấm nút **"2. Sập nguồn & Chuyển nguồn"** để diễn tập cơ chế Failover.
- Bấm nút **"3. Phát hiện Chunk hỏng"** để xem ô vuông nhấp nháy đỏ báo sai mã băm SHA-256.
- Bấm nút **"Tắt máy / Bật lại"** của Peer 1 để mô phỏng sự cố mạng.

---

### 💻 CHẠY KIỂM THỬ TỰ ĐỘNG BẰNG TERMINAL (Console)
```bash
python tests/test_step1.py
```

### 2. Kiểm thử Bước 2 (Tracker Server)
```bash
python tests/test_step2.py
```

### 3. Kiểm thử Bước 3 (Socket P2P 1-1)
```bash
python tests/test_step3.py
```

### 4. Kiểm thử Bước 4 (Tải song song & Vừa tải vừa cho giữa 3 Peers)
```bash
python tests/test_step4.py
```

### 5. Kiểm thử Bước 5 (Trọn bộ 7 kịch bản Demo bắt buộc)
```bash
python tests/test_step5.py
```

### Các kịch bản đã được kiểm chứng trong Bước 1:
1. **Cắt nhỏ file (Chunking):** Chia file thành các mảnh 512KB (`chunk_0.bin`, `chunk_1.bin`,...).
2. **Tính toán mã băm (Hashing):** Tính SHA-256 cho từng chunk và cho toàn bộ file gốc.
3. **Tạo và đọc file Metadata:** Lưu thông tin file ra file `.json` đúng chuẩn đặc tả.
4. **Phát hiện chunk bị hỏng (Corrupted Chunk - Kịch bản bắt buộc số 6):** Nhận diện chunk bị sửa đổi dữ liệu và từ chối.
5. **Ghép file (Merging) & Đối chiếu toàn vẹn:** Ghép lại các chunk và so sánh mã băm, file sau khi ghép giống file gốc 100%.
