import os
import cv2
import shutil
import numpy as np

def preprocess_image(source_file_path: str, target_file_path: str, max_size_mb: int = 6) -> str:
    source_file_path = os.path.abspath(source_file_path)
    target_file_path = os.path.abspath(target_file_path)

    if not os.path.exists(source_file_path):
        raise FileNotFoundError(f"错误: 源文件不存在 -> {source_file_path}")

    if not os.path.isfile(source_file_path):
        raise ValueError(f"错误: 输入路径不是文件 -> {source_file_path}")

    target_parent_dir = os.path.dirname(target_file_path)
    if target_parent_dir:
        os.makedirs(target_parent_dir, exist_ok=True)

    source_filename = os.path.basename(source_file_path)

    file_size = os.path.getsize(source_file_path)
    max_bytes = max_size_mb * 1024 * 1024

    print(f"Detected file: {source_filename}")
    print(f"Current size: {file_size / (1024*1024):.2f} MB")

    # 定义OpenCV支持的常见格式
    opencv_formats = ['.jpg', '.jpeg', '.png', '.tif', '.tiff', '.bmp', '.webp']
    src_ext = os.path.splitext(source_filename)[1].lower()

    # 策略 1: 直接复制到目标文件
    if file_size <= max_bytes and src_ext in opencv_formats:
        final_output_path = target_file_path
        print(f"File size within {max_size_mb}MB limit and format ({src_ext}) is supported, copying directly...")

        shutil.copy2(source_file_path, final_output_path)
        print(f"Image is ready: {final_output_path}\n")
        return final_output_path

    # 策略 2: 需要转码或压缩
    print(f"Starting processing (transcoding or compressing)...")

    # 使用 numpy 读取以支持中文路径
    try:
        img_np = np.fromfile(source_file_path, dtype=np.uint8)
        img = cv2.imdecode(img_np, cv2.IMREAD_COLOR)
    except Exception as e:
        raise RuntimeError(f"读取图片失败: {e}") from e

    if img is None:
        raise RuntimeError(f"无法解码图片文件: {source_file_path} (可能是格式不支持或文件损坏)")

    # 压缩参数初始化
    quality = 95 
    h, w = img.shape[:2]
    encoded_data = None

    output_ext = os.path.splitext(target_file_path)[1].lower()
    if output_ext not in [".jpg", ".jpeg"]:
        final_output_path = os.path.splitext(target_file_path)[0] + ".jpg"
    else:
        final_output_path = target_file_path

    while True:
        # 始终尝试编码为 jpg 以适应大小限制
        ext = ".jpg"

        params = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
        
        ok, buf = cv2.imencode(ext, img, params)

        if not ok:
            raise RuntimeError("图片编码失败，终止处理")

        current_size = len(buf)
        if current_size <= max_bytes:
            encoded_data = buf
            print(f"Processing successful (Quality={quality}, Resolution={w}x{h})")
            break

        # 压缩逻辑：优先降质量，质量过低则降分辨率
        quality -= 10
        if quality < 30:
            print(f"Quality reduced to {quality} but still too large, reducing resolution by half...")
            h, w = int(h * 0.7), int(w * 0.7) # 缩小约 50% 面积
            img = cv2.resize(img, (w, h))
            quality = 80 # 重置质量以保证画面清晰度

    # 保存压缩后的数据到文件
    try:
        with open(final_output_path, "wb") as f:
            f.write(encoded_data) # type: ignore
        print(f"Processing complete, final size: {len(encoded_data) / (1024*1024):.2f} MB") # type: ignore
    except Exception as e:
        raise RuntimeError(f"保存文件失败: {e}") from e

    print(f"Image is ready: {final_output_path}\n")
    return final_output_path

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="图片预处理工具")
    parser.add_argument("input", help="输入图片文件路径")
    parser.add_argument("output", help="输出图片文件路径")
    parser.add_argument("--max_size_mb", type=int, default=6, help="最大文件大小（MB）")
    args = parser.parse_args()

    try:
        preprocess_image(args.input, args.output, max_size_mb=args.max_size_mb)
    except Exception as e:
        print(f"主程序错误: {e}")