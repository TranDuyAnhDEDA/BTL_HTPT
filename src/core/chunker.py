import os
import hashlib
import uuid
from typing import List, Optional
from .metadata import FileMetadata

# Kích thước chunk mặc định: 512 KB (512 * 1024 bytes)
DEFAULT_CHUNK_SIZE = 512 * 1024


def calculate_hash(data: bytes) -> str:
    """Tính mã băm SHA-256 cho dữ liệu nhị phân."""
    return hashlib.sha256(data).hexdigest()


def split_file(
    file_path: str,
    output_chunks_dir: str,
    tracker_url: str = "http://localhost:8000",
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    file_id: Optional[str] = None
) -> FileMetadata:
    """
    Chia nhỏ một file thành các chunks, tính mã băm SHA-256 và lưu các chunk ra đĩa.
    Trả về đối tượng FileMetadata.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Không tìm thấy file nguồn: {file_path}")

    os.makedirs(output_chunks_dir, exist_ok=True)

    file_size = os.path.getsize(file_path)
    file_name = os.path.basename(file_path)
    if not file_id:
        file_id = str(uuid.uuid4())[:8]  # Tạo mã ID ngắn gọn cho file

    chunk_hashes: List[str] = []
    full_file_hasher = hashlib.sha256()

    with open(file_path, "rb") as f:
        chunk_idx = 0
        while True:
            chunk_data = f.read(chunk_size)
            if not chunk_data:
                break

            # Cập nhật hash toàn file
            full_file_hasher.update(chunk_data)

            # Tính hash của chunk này
            chunk_hash = calculate_hash(chunk_data)
            chunk_hashes.append(chunk_hash)

            # Lưu chunk ra file riêng biệt: chunk_0.bin, chunk_1.bin,...
            chunk_file_path = os.path.join(output_chunks_dir, f"chunk_{chunk_idx}.bin")
            with open(chunk_file_path, "wb") as cf:
                cf.write(chunk_data)

            chunk_idx += 1

    metadata = FileMetadata(
        file_id=file_id,
        file_name=file_name,
        file_size=file_size,
        chunk_size=chunk_size,
        num_chunks=len(chunk_hashes),
        chunk_hashes=chunk_hashes,
        file_hash=full_file_hasher.hexdigest(),
        tracker_url=tracker_url
    )

    return metadata


def verify_chunk(chunk_data: bytes, expected_hash: str) -> bool:
    """
    Kiểm tra tính toàn vẹn của một chunk:
    Băm dữ liệu nhận được và so sánh với mã băm kỳ vọng trong metadata.
    """
    return calculate_hash(chunk_data) == expected_hash


def merge_chunks(
    chunks_dir: str,
    output_file_path: str,
    metadata: FileMetadata
) -> bool:
    """
    Ghép các chunk theo đúng thứ tự thành file hoàn chỉnh và đối chiếu mã băm.
    Yêu cầu:
    1. Kiểm tra mã băm từng chunk trước khi ghép (bỏ qua/báo lỗi nếu có chunk hỏng).
    2. Ghép lần lượt theo thứ tự từ 0 -> num_chunks - 1.
    3. Xác thực mã băm của file cuối cùng với metadata.file_hash.
    """
    # Đảm bảo thư mục lưu file đầu ra tồn tại
    output_dir = os.path.dirname(output_file_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    full_file_hasher = hashlib.sha256()

    with open(output_file_path, "wb") as out_f:
        for idx in range(metadata.num_chunks):
            chunk_file_path = os.path.join(chunks_dir, f"chunk_{idx}.bin")
            
            if not os.path.exists(chunk_file_path):
                raise FileNotFoundError(f"Thiếu chunk {idx}: không tìm thấy tại {chunk_file_path}")

            with open(chunk_file_path, "rb") as cf:
                chunk_data = cf.read()

            # 1. Xác thực tính toàn vẹn của từng chunk
            expected_hash = metadata.chunk_hashes[idx]
            if not verify_chunk(chunk_data, expected_hash):
                raise ValueError(f"Chunk {idx} bị lỗi hoặc bị sửa đổi! Hash không khớp.")

            # 2. Ghi chunk vào file và cập nhật hash toàn file
            out_f.write(chunk_data)
            full_file_hasher.update(chunk_data)

    # 3. Xác thực hash toàn bộ file cuối cùng
    merged_hash = full_file_hasher.hexdigest()
    if merged_hash != metadata.file_hash:
        raise ValueError("Lỗi ghép file: Mã băm toàn bộ file không khớp với metadata gốc!")

    return True
