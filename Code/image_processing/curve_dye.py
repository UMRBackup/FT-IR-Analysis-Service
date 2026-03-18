import cv2
import numpy as np
import os


def dye_curve_blue(image_path: str, output_path: str):
    # 处理包含中文路径的问题
    img = cv2.imdecode(np.fromfile(image_path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(f"Failed to load image: {image_path}")

    # 转换到 HSV 颜色空间，便于颜色分割
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    # 定义掩膜（Mask）策略：严格限制为红色

    # 红色范围1: hue [0, 10]
    lower_red1 = np.array([0, 43, 46])
    upper_red1 = np.array([10, 255, 255])
    mask1 = cv2.inRange(hsv, lower_red1, upper_red1)

    # 红色范围2: hue [170, 180]
    lower_red2 = np.array([170, 43, 46])
    upper_red2 = np.array([180, 255, 255])
    mask2 = cv2.inRange(hsv, lower_red2, upper_red2)

    # 合并掩膜
    mask = cv2.add(mask1, mask2)

    # 生成结果图像副本
    result = img.copy()

    # 目标颜色：蓝色 (BGR: 255, 0, 0) -> OpenCV中是 BGR 顺序
    target_color = (255, 0, 0) 

    # 在掩膜区域应用颜色
    result[mask > 0] = target_color

    # 保存结果
    output_dir = os.path.dirname(os.path.abspath(output_path))
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    is_success, buffer = cv2.imencode(".jpg", result)
    if is_success:
        with open(output_path, "wb") as f:
            f.write(buffer)
        print(f"Processing complete: {output_path}")
    else:
        print("Failed to save image")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="将光谱曲线染成蓝色")

    parser.add_argument("input", help="输入图片路径")
    parser.add_argument("output", help="输出图片路径")

    args = parser.parse_args()

    try:
        dye_curve_blue(args.input, args.output)
    except Exception as e:
        print(f"An error occurred: {e}")