import os
import time
import logging
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException, status, Header, UploadFile, File
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

# Cấu hình logging chuyên nghiệp hiển thị thời gian, nút mạng và sự kiện (Yêu cầu mục 4.1)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [TRACKER]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("Tracker")

app = FastAPI(
    title="P2P BitTorrent Tracker Server",
    description="Máy chủ chỉ đường và quản lý danh bạ Peer cho đồ án Hệ thống phân tán DS02",
    version="1.0.0"
)

# Thời gian tối đa (giây) không nhận được heartbeat trước khi coi Peer là offline
PEER_TIMEOUT_SECONDS = 15


# ==========================================
# CÁC MODEL DỮ LIỆU ĐẦU VÀO (PYDANTIC)
# ==========================================

class RegisterFileRequest(BaseModel):
    file_id: str
    file_name: str
    file_size: int
    chunk_size: int
    num_chunks: int
    chunk_hashes: List[str]
    file_hash: str
    tracker_url: str


class AnnounceRequest(BaseModel):
    peer_id: str
    file_id: str
    ip: str
    port: int
    bitfield: List[int] = Field(
        ..., 
        description="Mảng các chỉ số chunk mà peer đang sở hữu, ví dụ: [0, 1, 2]"
    )


class HeartbeatRequest(BaseModel):
    peer_id: str


class PeerInfo(BaseModel):
    peer_id: str
    ip: str
    port: int
    bitfield: List[int]
    last_seen: float


# ==========================================
# BỘ NHỚ LƯU TRỮ TRONG RAM (IN-MEMORY STATE)
# ==========================================

# Lưu thông tin metadata của các file đã đăng ký: {file_id: FileMetadataDict}
registered_files: Dict[str, dict] = {}

# Lưu danh sách peers theo file: {file_id: {peer_id: PeerInfo}}
file_peers: Dict[str, Dict[str, PeerInfo]] = {}

# Lưu thông tin theo dõi nhịp tim của từng peer: {peer_id: last_seen_timestamp}
peer_heartbeats: Dict[str, float] = {}


# ==========================================
# CÁC API ENDPOINTS
# ==========================================

@app.get("/")
def root(accept: Optional[str] = Header(None)):
    """
    Nếu truy cập từ Trình duyệt (Chrome/Edge), trả về Giao diện Web UI Dashboard.
    Nếu truy cập từ Code/API, trả về JSON kiểm tra trạng thái.
    """
    if accept and "text/html" in accept:
        return get_dashboard()

    return {
        "service": "P2P BitTorrent Tracker",
        "status": "online",
        "total_files": len(registered_files),
        "total_active_peers": len(peer_heartbeats)
    }


@app.get("/dashboard", response_class=HTMLResponse)
def get_dashboard():
    """Trả về Giao diện Web UI Dashboard trực quan cho đồ án (Vô hiệu hóa cache trình duyệt)."""
    html_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "web", "templates", "index.html"))
    if not os.path.exists(html_file):
        raise HTTPException(status_code=404, detail="Không tìm thấy file giao diện index.html")
    with open(html_file, "r", encoding="utf-8") as f:
        content = f.read()
    return HTMLResponse(
        content=content,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )


# ==========================================
# CÁC API THỰC THI SOCKET THẬT 100% CHO WEB
# ==========================================

from ..web.scenario_runner import ScenarioRunner
global_runner = ScenarioRunner(tracker_url="http://127.0.0.1:8000")


@app.post("/api/real_demo/parallel")
def api_real_parallel():
    """Gọi thực thi kịch bản tải song song bằng Socket TCP Python thật 100%."""
    return global_runner.run_real_parallel_download()


@app.post("/api/real_demo/failover")
def api_real_failover():
    """Gọi thực thi kịch bản sập nguồn & chuyển nguồn bằng Socket TCP Python thật 100%."""
    return global_runner.run_real_failover()


@app.post("/api/custom/upload")
async def api_upload_custom_file(file: UploadFile = File(...)):
    """Tiếp nhận file bất kỳ do người dùng tự tải lên, cắt thành chunks thật và seed qua Socket."""
    content = await file.read()
    metadata_dict = global_runner.upload_and_share_custom_file(file.filename, content)
    file_id = metadata_dict["file_id"]
    registered_files[file_id] = metadata_dict
    if file_id not in file_peers:
        file_peers[file_id] = {}
    return metadata_dict


@app.post("/api/peer1/status")
def api_set_peer1_status(online: bool):
    """Bật/tắt tiến trình Peer 1 thật theo yêu cầu từ giao diện Web."""
    global_runner.set_peer1_status(online)
    return {"status": "ok", "peer1_online": online}


@app.post("/api/custom/download/{file_id}")
def api_download_custom_file(file_id: str, p1_online: bool = True):
    """Kích hoạt Peer 3 tải file của người dùng qua cổng Socket TCP thật 100%."""
    return global_runner.download_custom_file(file_id, p1_online=p1_online)


@app.post("/register_file", status_code=status.HTTP_201_CREATED)
def register_file(file_meta: RegisterFileRequest):
    """
    Seeder gọi API này để khai báo một file mới lên hệ thống.
    Tracker chỉ lưu thông tin mô tả (Metadata), KHÔNG LƯU NỘI DUNG FILE.
    """
    file_id = file_meta.file_id
    registered_files[file_id] = file_meta.model_dump()
    if file_id not in file_peers:
        file_peers[file_id] = {}

    logger.info(f"Đã đăng ký file mới: '{file_meta.file_name}' (ID: {file_id}, {file_meta.num_chunks} chunks)")
    return {"message": "Đăng ký file thành công", "file_id": file_id}


@app.post("/announce")
def announce(data: AnnounceRequest):
    """
    Một Peer báo danh với Tracker:
    - Báo mình đang giữ các chunk nào (bitfield).
    - Cập nhật địa chỉ IP và Port lắng nghe chia sẻ của mình.
    """
    file_id = data.file_id
    peer_id = data.peer_id

    if file_id not in registered_files:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File ID '{file_id}' chưa được đăng ký trên Tracker"
        )

    now = time.time()
    peer_info = PeerInfo(
        peer_id=peer_id,
        ip=data.ip,
        port=data.port,
        bitfield=data.bitfield,
        last_seen=now
    )

    file_peers[file_id][peer_id] = peer_info
    peer_heartbeats[peer_id] = now

    logger.info(
        f"Peer '{peer_id}' báo danh cho file '{file_id}' tại {data.ip}:{data.port} | Chunks sở hữu: {data.bitfield}"
    )
    return {"message": "Báo danh thành công", "peer_id": peer_id}


@app.get("/peers/{file_id}")
def get_peers(file_id: str):
    """
    Một Peer gọi API này để lấy danh sách tất cả các Peer đang online và sở hữu các mảnh của file.
    Tự động lọc bỏ các Peer đã offline (quá hạn gửi heartbeat).
    """
    if file_id not in registered_files:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy file ID '{file_id}'"
        )

    now = time.time()
    active_peers = []

    # Quét danh sách và chỉ trả về những peer còn online
    for p_id, p_info in list(file_peers.get(file_id, {}).items()):
        if now - p_info.last_seen <= PEER_TIMEOUT_SECONDS:
            active_peers.append({
                "peer_id": p_info.peer_id,
                "ip": p_info.ip,
                "port": p_info.port,
                "bitfield": p_info.bitfield
            })
        else:
            # Phát hiện sự cố: Peer đã offline (Fault Detection)
            logger.warning(f"Phát hiện Peer '{p_id}' đã mất kết nối (Timeout quá {PEER_TIMEOUT_SECONDS}s). Đang gỡ bỏ.")
            del file_peers[file_id][p_id]
            peer_heartbeats.pop(p_id, None)

    logger.info(f"Trả về danh sách {len(active_peers)} active peer(s) cho file '{file_id}'")
    return {
        "file_id": file_id,
        "metadata": registered_files[file_id],
        "peers": active_peers
    }


@app.post("/heartbeat")
def heartbeat(data: HeartbeatRequest):
    """
    Peer định kỳ gửi nhịp tim để duy trì trạng thái 'còn sống' trên Tracker.
    """
    peer_id = data.peer_id
    now = time.time()

    if peer_id in peer_heartbeats:
        peer_heartbeats[peer_id] = now
        # Cập nhật thời gian trên tất cả file mà peer này tham gia
        for f_id in file_peers:
            if peer_id in file_peers[f_id]:
                file_peers[f_id][peer_id].last_seen = now
        logger.debug(f"Nhận Heartbeat từ Peer '{peer_id}'")
        return {"message": "Heartbeat ghi nhận", "peer_id": peer_id}
    else:
        # Nếu peer chưa từng announce thì yêu cầu announce trước
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Peer '{peer_id}' chưa báo danh. Vui lòng gọi /announce trước."
        )


@app.get("/files")
def list_files():
    """Trả về danh sách tất cả các file đã đăng ký trên Tracker."""
    file_list = []
    for f_id, meta in registered_files.items():
        peers_count = len(file_peers.get(f_id, {}))
        file_list.append({
            "file_id": f_id,
            "file_name": meta.get("file_name"),
            "file_size": meta.get("file_size"),
            "num_chunks": meta.get("num_chunks"),
            "chunk_size": meta.get("chunk_size"),
            "file_hash": meta.get("file_hash"),
            "peers_count": peers_count
        })
    return {"files": file_list}


@app.get("/active_peers")
def list_active_peers():
    """Trả về danh sách tất cả các Peer đang online trên mạng kèm IP và Port thực tế."""
    now = time.time()
    peers = []

    # Thu thập thông tin IP và Port của từng peer từ các file tham gia
    peer_details: Dict[str, dict] = {}
    for f_id, p_map in file_peers.items():
        for p_id, p_info in p_map.items():
            if now - p_info.last_seen <= PEER_TIMEOUT_SECONDS:
                peer_details[p_id] = {
                    "ip": p_info.ip,
                    "port": p_info.port,
                    "bitfield": p_info.bitfield
                }

    for p_id, last_time in list(peer_heartbeats.items()):
        if now - last_time <= PEER_TIMEOUT_SECONDS:
            info = peer_details.get(p_id, {})
            peers.append({
                "peer_id": p_id,
                "ip": info.get("ip", "Unknown"),
                "port": info.get("port", 6001),
                "last_seen_seconds_ago": round(now - last_time, 1)
            })
    return {"active_peers": peers, "count": len(peers)}
