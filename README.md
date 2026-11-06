# P2P File Sharing System (BitTorrent Simulation) - Topic DS02

Hệ thống chia sẻ file ngang hàng P2P mô phỏng giao thức BitTorrent cho môn học Hệ thống phân tán:
- Truyền file nhị phân trực tiếp qua TCP Sockets với Framing Protocol tự định nghĩa.
- Chia nhỏ file 512 KB, băm SHA-256 từng chunk, bảo đảm toàn vẹn bit-for-bit.
- Tải song song đa nguồn (Parallel Download), vừa tải vừa chia sẻ (Seed-while-Leeching).
- Chịu lỗi: Tự phát hiện peer sập nguồn (Socket Timeout / Heartbeat), chuyển đổi nguồn tải dự phòng (Failover), phát hiện và loại bỏ chunk hỏng/giả mạo.
- Hỗ trợ truyền file giữa nhiều máy tính khác nhau trong mạng LAN / Wi-Fi.

---

## Cấu trúc thư mục dự án

```text
├── src/
│   ├── core/
│   │   ├── metadata.py       # Định nghĩa cấu trúc Metadata (.json)
│   │   └── chunker.py        # Module cắt file, băm SHA-256, kiểm tra và ghép file
│   ├── tracker/
│   │   └── server.py         # Tracker Server (FastAPI REST API điều phối danh bạ)
│   ├── peer/
│   │   ├── protocol.py       # Giao thức truyền tin nhị phân qua TCP Socket (Framing)
│   │   └── client.py         # Nút mạng Peer (Vừa là Server Upload vừa là Client Download)
│   └── web/
│       ├── scenario_runner.py# Bộ điều khiển thực thi Socket thật 100% cho Web
│       └── templates/index.html # Giao diện Web Dashboard trực quan
├── tests/
│   ├── test_step1.py         # Kiểm thử Bước 1: Cắt, băm, ghép và phát hiện lỗi
│   ├── test_step2.py         # Kiểm thử Bước 2: Tracker Server, Announce, Heartbeat & Fault Tolerance
│   ├── test_step3.py         # Kiểm thử Bước 3: Truyền file P2P trực tiếp qua Socket giữa 2 Peer
│   ├── test_step4.py         # Kiểm thử Bước 4: Tải song song đa luồng & Vừa tải vừa cho (3 Peers)
│   ├── test_step5.py         # Kiểm thử Bước 5: Trọn bộ 7 kịch bản Demo bắt buộc (Failover, Sập nguồn, Chunk hỏng)
│   └── test_lan_peers.py     # Kiểm thử truyền file P2P tự động giữa 2 máy tính qua mạng LAN
├── deploy/                   # Cấu hình triển khai Docker Container
│   ├── Dockerfile.tracker
│   ├── Dockerfile.peer
│   └── docker-compose.yml
├── scripts/
│   ├── run_all.bat           # Khởi chạy Tracker và Dashboard bằng 1-click (Windows)
│   ├── run_peer.bat          # Khởi chạy Peer tương tác truyền file (Windows)
│   ├── run_tests.bat         # Chạy toàn bộ 5 bài test tự động (Windows)
│   ├── run_all.sh            # Khởi chạy Tracker (Linux/macOS)
│   ├── run_peer.sh           # Khởi chạy Peer (Linux/macOS)
│   └── run_tests.sh          # Chạy toàn bộ tests (Linux/macOS)
├── run_peer.py               # Công cụ CLI điều khiển Peer truyền file giữa các máy
├── requirements.txt
└── README.md
```

---

## 🚀 HƯỚNG DẪN KẾT NỐI VÀ TRUYỀN FILE GIỮA 2 MÁY TÍNH TRONG MẠNG LAN

### Bước 1: Khởi động Tracker Server (Trên Máy 1)
Mở PowerShell/CMD trên **Máy 1** và chạy:
```bash
python -m uvicorn src.tracker.server:app --host 0.0.0.0 --port 8000
```
> *(Lưu ý: `--host 0.0.0.0` cho phép các máy khác trong cùng mạng LAN kết nối tới).*
> Xem địa chỉ IP của Máy 1 bằng lệnh `ipconfig` (ví dụ: `192.168.1.15`).
> Bạn có thể mở trình duyệt trên bất kỳ máy nào vào: `http://192.168.1.15:8000/dashboard`

### Bước 2: Chia sẻ (Seed) file từ Máy 1
Trên **Máy 1**, mở terminal mới và chạy:
```bash
python run_peer.py --tracker http://127.0.0.1:8000
```
- Chọn mục `2. Chia sẻ (Seed) một file`.
- Nhập đường dẫn file (Video, PDF, ZIP...). Hệ thống tự cắt chunks, băm SHA-256 và mở cổng Socket lắng nghe cấp dữ liệu.

### Bước 3: Tải (Download) file về Máy 2
Trên **Máy 2** (đã clone repo hoặc copy project sang), mở terminal và chạy:
```bash
python run_peer.py --tracker http://192.168.1.15:8000
```
*(Thay `192.168.1.15` bằng IP thật của Máy 1)*
- Chọn mục `1` để xem danh sách các file đang có trên mạng.
- Chọn mục `3` để tải file: Hệ thống sẽ kết nối trực tiếp Socket TCP sang Máy 1, tải các chunks song song, kiểm tra SHA-256 và ghép thành file hoàn chỉnh trong thư mục `./downloads/`!

---

## 🧪 CHẠY CÁC BỘ KIỂM THỬ (TEST SUITES)

### Cách 1: Chạy toàn bộ 5 bài test tự động bằng 1 lệnh
```powershell
.\scripts\run_tests.bat
```
*(Hoặc trên Linux/Mac: `./scripts/run_tests.sh`)*

### Cách 2: Chạy kiểm thử truyền P2P thực tế giữa 2 máy trong mạng LAN
- **Trên Máy 1 (Seeder):**
  ```bash
  python tests/test_lan_peers.py --role seeder --tracker http://192.168.1.15:8000 --port 6001
  ```
- **Trên Máy 2 (Leecher):**
  ```bash
  python tests/test_lan_peers.py --role leecher --tracker http://192.168.1.15:8000 --port 6002
  ```
Máy 2 sẽ tự động kết nối qua Socket tới Máy 1, tải file mẫu, đo tốc độ truyền (MB/s) và xác nhận mã băm SHA-256 khớp 100%.

### Cách 3: Chạy từng bài test đơn vị (Unit Tests)
```bash
python tests/test_step1.py   # Cắt, băm SHA-256, ghép file & phát hiện chunk hỏng
python tests/test_step2.py   # Tracker Server, Announce, Heartbeat & Timeout
python tests/test_step3.py   # Truyền dữ liệu P2P Socket 1-1
python tests/test_step4.py   # Tải song song đa luồng & Seed-while-Leeching (3 Peers)
python tests/test_step5.py   # 7 kịch bản bắt buộc: Sập nguồn, Failover, Chống giả mạo
```
