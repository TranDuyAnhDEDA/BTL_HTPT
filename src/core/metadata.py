import json
import uuid
from dataclasses import dataclass, asdict
from typing import List


@dataclass
class FileMetadata:
    """
    Chứa thông tin metadata của file chia sẻ (tương tự file .torrent trong BitTorrent)
    Tuân thủ đúng yêu cầu mục 6.3 Functional Requirements
    """
    file_id: str                   # Mã định danh duy nhất của file
    file_name: str                 # Tên file gốc (ví dụ: test.mp4)
    file_size: int                 # Tổng dung lượng file (bytes)
    chunk_size: int                # Kích thước mỗi chunk (bytes)
    num_chunks: int                # Tổng số chunk
    chunk_hashes: List[str]        # Danh sách mã băm SHA-256 của từng chunk
    file_hash: str                 # Mã băm SHA-256 của toàn bộ file gốc
    tracker_url: str               # Địa chỉ của Tracker server (ví dụ: http://localhost:8000)

    def to_dict(self) -> dict:
        return asdict(self)

    def save_json(self, file_path: str) -> None:
        """Lưu metadata ra file định dạng JSON."""
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=4)

    @classmethod
    def load_json(cls, file_path: str) -> "FileMetadata":
        """Đọc metadata từ file JSON."""
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls(**data)
