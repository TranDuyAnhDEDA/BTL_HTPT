import os
import sys
import shutil

# Đảm bảo in ký tự tiếng Việt không bị lỗi encoding trên Windows console
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Thêm thư mục gốc vào đường dẫn import
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.chunker import split_file, merge_chunks, verify_chunk
from src.core.metadata import FileMetadata


def main():
    print("=" * 60)
    print("  KIỂM THỬ BƯỚC 1: CẮT - BĂM - GHÉP VÀ XÁC THỰC TÍNH TOÀN VẸN")
    print("=" * 60)

    # 1. Chuẩn bị thư mục làm việc tạm thời
    work_dir = os.path.join(os.path.dirname(__file__), "temp_step1")
    if os.path.exists(work_dir):
        shutil.rmtree(work_dir)
    os.makedirs(work_dir, exist_ok=True)

    sample_file_path = os.path.join(work_dir, "sample_video.mp4")
    chunks_dir = os.path.join(work_dir, "chunks")
    metadata_path = os.path.join(work_dir, "sample_video.metadata.json")
    restored_file_path = os.path.join(work_dir, "restored_video.mp4")

    # Tạo một file mẫu dung lượng khoảng 1.5 MB (1536 KB)
    print("\n[1] Đang tạo file dữ liệu mẫu (1.5 MB)...")
    content = b"BitTorrent-Simulation-Project-Distributed-Systems-DS02\n" * 28000
    with open(sample_file_path, "wb") as f:
        f.write(content)
    print(f" -> Đã tạo file mẫu tại: {sample_file_path} (Dung lượng: {len(content):,} bytes)")

    # 2. Cắt file thành các chunks (kích thước mỗi chunk 512 KB)
    chunk_size = 512 * 1024  # 512 KB
    print(f"\n[2] Đang cắt nhỏ file với kích thước chunk = {chunk_size // 1024} KB...")
    metadata = split_file(
        file_path=sample_file_path,
        output_chunks_dir=chunks_dir,
        tracker_url="http://localhost:8000",
        chunk_size=chunk_size
    )

    print(f" -> Số lượng chunks tạo ra: {metadata.num_chunks}")
    for idx, ch_hash in enumerate(metadata.chunk_hashes):
        print(f"    * Chunk {idx}: SHA-256 = {ch_hash[:16]}... (Đã lưu vào chunk_{idx}.bin)")
    print(f" -> Mã băm toàn bộ file (File Hash): {metadata.file_hash[:20]}...")

    # 3. Lưu file Metadata (tương đương file .torrent)
    print(f"\n[3] Đang lưu file Metadata ra: {metadata_path}")
    metadata.save_json(metadata_path)
    
    # Đọc lại để kiểm chứng
    loaded_metadata = FileMetadata.load_json(metadata_path)
    print(" -> Đọc lại Metadata từ JSON thành công. File ID:", loaded_metadata.file_id)

    # 4. Thử nghiệm kịch bản demo: PHÁT HIỆN CHUNK BỊ HỎNG (Mandatory Scenario 6)
    print("\n[4] Kiểm tra kịch bản giả lập: Phát hiện chunk bị hỏng (Corrupted chunk)...")
    with open(os.path.join(chunks_dir, "chunk_0.bin"), "rb") as cf:
        real_chunk_0 = cf.read()
    
    # Dữ liệu chuẩn
    is_valid = verify_chunk(real_chunk_0, metadata.chunk_hashes[0])
    print(f" -> Kiểm tra Chunk 0 nguyên bản: {'HỢP LỆ (PASSED)' if is_valid else 'LỖI'}")

    # Giả lập chunk bị hỏng (thêm 1 byte lạ vào cuối)
    corrupted_chunk_0 = real_chunk_0 + b"x"
    is_valid_corrupted = verify_chunk(corrupted_chunk_0, metadata.chunk_hashes[0])
    print(f" -> Kiểm tra Chunk 0 bị can thiệp/hỏng: {'HỢP LỆ' if is_valid_corrupted else 'TỪ CHỐI THÀNH CÔNG (PHÁT HIỆN SAI HASH)'}")

    # 5. Ghép lại file từ các chunks
    print(f"\n[5] Đang ghép các chunks lại thành file hoàn chỉnh: {restored_file_path}")
    success = merge_chunks(chunks_dir, restored_file_path, loaded_metadata)
    if success:
        print(" -> Ghép file thành công và đã đối chiếu mã băm toàn file (File Hash khớp 100%)!")

    # 6. So sánh trực tiếp file gốc và file sau khi ghép
    with open(sample_file_path, "rb") as f1, open(restored_file_path, "rb") as f2:
        if f1.read() == f2.read():
            print("\n" + "=" * 60)
            print("  CHÚC MỪNG: BƯỚC 1 HOÀN TẤT XUẤT SẮC! (File gốc và File ghép giống nhau 100%)")
            print("=" * 60)


if __name__ == "__main__":
    main()
