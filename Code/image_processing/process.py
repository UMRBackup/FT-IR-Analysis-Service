from typing import List, Tuple, Optional, Any
import os
import cv2
import json
import base64
import numpy as np
import tempfile
import requests
import re
import time
from dashscope import MultiModalConversation

try:
    DASHSCOPE_API_KEY: str = os.environ["DASHSCOPE_API_KEY"]
except KeyError:
    raise RuntimeError("请设置环境变量 DASHSCOPE_API_KEY")

try:
    OPENROUTER_API_KEY: str = os.environ["OPENROUTER_API_KEY"]
except KeyError:
    raise RuntimeError("请设置环境变量 OPENROUTER_API_KEY")

def save_compressed_image(img: np.ndarray, save_path: str, max_mb: int = 5) -> None:
    target_bytes = max_mb * 1024 * 1024
    quality = 95
    current_img = img.copy()

    while True:
        # 尝试编码
        ok, buf = cv2.imencode('.jpg', current_img, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
        if not ok:
            print(f"Warning: 无法编码图片保存至 {save_path}")
            return

        if len(buf) <= target_bytes:
            with open(save_path, "wb") as f:
                f.write(buf)
            print(f"图片已保存: {save_path} ({len(buf)/1024/1024:.2f} MB)")
            return

        # 压缩
        if quality > 60:
            quality -= 10
        else:
            h, w = current_img.shape[:2]
            scale = 0.8
            current_img = cv2.resize(current_img, (int(w*scale), int(h*scale)))
            quality = 90 # 缩放后重置质量

def encode_image_to_b64(img_bgr: np.ndarray, ext: str = ".jpg") -> str:
    # 初始压缩参数
    encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), 95]
    result_b64 = None

    # Base64 限制
    max_size = 8 * 1024 * 1024

    # 工作副本
    current_img = img_bgr.copy()

    while True:
        ok, buf = cv2.imencode(ext, current_img, encode_params)
        if not ok:
            raise RuntimeError("图像编码失败")

        b64 = base64.b64encode(buf).decode("utf-8")

        # 检查大小
        if len(b64) <= max_size:
            result_b64 = b64
            break

        current_quality = encode_params[1]
        if current_quality > 50:
            encode_params[1] -= 15 # 大幅降低质量
            print(f"Base64过大 ({len(b64)/1024/1024:.2f}MB)，降低编码质量至 {encode_params[1]}...")
        else:
            # 缩小分辨率
            h, w = current_img.shape[:2]
            scale = 0.8
            new_w, new_h = int(w * scale), int(h * scale)
            if new_w < 300 or new_h < 300:
                 raise ValueError("无法生成合规 Base64")

            print(f"Base64过大，缩放图像至 {new_w}x{new_h}...")
            current_img = cv2.resize(current_img, (new_w, new_h), interpolation=cv2.INTER_AREA)
            # 适当回调质量
            encode_params[1] = 85

    mime = "image/jpeg" if ext.lower().endswith("jpg") or ext.lower().endswith("jpeg") else "image/png"
    return f"data:{mime};base64,{result_b64}"

def call_gemini_vision(prompt: str, image_path: str, model: str = "google/gemini-3-pro-preview") -> Any:
    # 读取并编码图片
    image_path = normalize_local_path(image_path)
    img = cv2.imdecode(np.fromfile(image_path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(f"无法打开图片：{image_path}")

    b64_image = encode_image_to_b64(img)

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": prompt
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": b64_image
                    }
                }
            ]
        }
    ]

    payload = {
        "model": model,
        "messages": messages
    }

    response = None
    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=60 # 超时
        )
        response.raise_for_status()
        response_data = response.json()
        content = response_data['choices'][0]['message']['content'] or ""
    except Exception as e:
        error_msg = str(e)
        if response is not None and hasattr(response, 'text'):
            error_msg += f" Response: {response.text}"
        raise RuntimeError(f"OpenRouter API 调用失败: {error_msg}")

    # 尝试提取 JSON
    if "```" in content:
        match = re.search(r"```(?:json)?(.*?)```", content, re.DOTALL)
        if match:
            content = match.group(1)

    try:
        return json.loads(content.strip())
    except (json.JSONDecodeError, TypeError, AttributeError):
        return content

def call_qwen_vision(prompt: str, image_path: str, model: str = "qwen3-vl-plus") -> Any:
    abs_path = os.path.abspath(image_path)
    image_uri = f"file://{abs_path}"

    messages = [
        {
            "role": "user",
            "content": [
                {"image": image_uri},
                {"text": prompt},
            ],
        }
    ]

    # 根据模型类型调整参数
    kwargs = {
        "api_key": DASHSCOPE_API_KEY,
        "model": model,
        "messages": messages,
        "stream": False,
    }

    if "qwen3-vl" in model or "reasoning" in model:
        kwargs["enable_thinking"] = True
        kwargs["thinking_budget"] = 3000

    response = None
    last_error = None
    max_retries = 3

    for attempt in range(max_retries):
        try:
            response = MultiModalConversation.call(**kwargs)

            # 检查响应状态码
            if hasattr(response, 'status_code') and response.status_code != 200: # type: ignore
                raise RuntimeError(f"API Code {getattr(response, 'code', 'Unknown')}: {getattr(response, 'message', 'Unknown')}")
            break
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                print(f"Qwen API 网络请求失败 (尝试 {attempt + 1}/{max_retries}): {e}，2秒后重试...")
                time.sleep(2)
            else:
                print(f"Qwen API 重试次数已耗尽。")

    output = getattr(response, 'output', None)
    if not response or not output or not output.choices:
         raise RuntimeError(f"Qwen API 调用失败: {last_error or getattr(response, 'message', 'Unknown error')}")

    content_list = output.choices[0].message.content
    text = ""
    for item in content_list:
        if "text" in item:
            text += item["text"]

    # 提取 JSON
    if text and "```" in text:
        match = re.search(r"```(?:json)?(.*?)```", text, re.DOTALL)
        if match:
            text = match.group(1)

    if not text:
        raise RuntimeError(f"未收到有效的文本响应: {response}")

    return json.loads(text.strip())

def extract_spectrogram_region(image_path: str) -> Tuple[np.ndarray, List[Tuple[int, int]]]:
    image_path = normalize_local_path(image_path)
    img = cv2.imdecode(np.fromfile(image_path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(f"无法打开图片：{image_path}")
    
    # 获取原始宽高
    h, w = img.shape[:2]

    prompt = (
        "This is a photo containing an FT-IR spectrum of a compound. "
        "Please detect the **four corner points** of the spectrum region in this photo. "
        "The target region should encompass the spectrum curve, the complete X and Y axes, and their tick values. "
        "Ignore irrelevant objects in the background. "
        "Please output JSON data, returning the coordinates of the four corners in 'point_2d' format. "
        "The order should be: [Top-Left, Top-Right, Bottom-Right, Bottom-Left]. "
        "If the four corners cannot be determined, please return the bounding box as 'box_2d'. "
        "JSON format example: { \"point_2d\": [[x1, y1], [x2, y2], [x3, y3], [x4, y4]] } "
        "The values should be normalized integer coordinates in the range [0, 1000]."
    )

    try:
        res = call_gemini_vision(prompt, image_path, model="google/gemini-3-pro-preview")

        # 优先处理 point_2d
        polygon = None

        if res.get("point_2d"):
             pts = res.get("point_2d")
             if len(pts) == 4:
                 # 解析归一化坐标
                 polygon = [(int(p[0]/1000*w), int(p[1]/1000*h)) for p in pts]

        # 兼容 polygon
        elif res.get("polygon"):
             poly = res.get("polygon")
             if len(poly) >= 4:
                polygon = [(int(p[0]/1000*w), int(p[1]/1000*h)) for p in poly[:4]]

        else:
            raise ValueError(f"未找到有效的坐标数据, 响应内容: {res}")

    except Exception as e:
        raise RuntimeError(f"模型提取失败，已终止程序: {e}")

    # 将四个点排序为 tl, tr, br, bl
    rect = order_points(np.array(polygon, dtype="float32"))
    warped = four_point_transform(img, rect)
    return warped, [(int(p[0]), int(p[1])) for p in rect.tolist()]

def order_points(pts: np.ndarray) -> np.ndarray:
    # 输入 4x2
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]  # tl
    rect[2] = pts[np.argmax(s)]  # br
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]  # tr
    rect[3] = pts[np.argmax(diff)]  # bl
    return rect

def four_point_transform(image: np.ndarray, rect: np.ndarray) -> np.ndarray:
    (tl, tr, br, bl) = rect
    widthA = np.linalg.norm(br - bl)
    widthB = np.linalg.norm(tr - tl)
    maxWidth = int(max(widthA, widthB))
    heightA = np.linalg.norm(tr - br)
    heightB = np.linalg.norm(tl - bl)
    maxHeight = int(max(heightA, heightB))
    dst = np.array([[0, 0], [maxWidth - 1, 0], [maxWidth - 1, maxHeight - 1], [0, maxHeight - 1]], dtype="float32")
    M = cv2.getPerspectiveTransform(rect, dst)
    warped = cv2.warpPerspective(image, M, (maxWidth, maxHeight))
    return warped

def download_image(image_url: str, save_path: str = 'output.jpg') -> None:
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # 超时设置
            response = requests.get(image_url, stream=True, timeout=(15, 300))
            response.raise_for_status()
            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            print(f"图像已成功下载到: {save_path}")
            return
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                print(f"图像下载失败 (尝试 {attempt + 1}/{max_retries}): {e}，{wait_time}秒后重试...")
                time.sleep(wait_time)
            else:
                raise RuntimeError(f"图像下载失败，已重试 {max_retries} 次: {e}")

def enhance_image(img_bgr: np.ndarray,
                                intermediate_dir: Optional[str] = None,
                                model: str = "qwen-image-edit-plus") -> np.ndarray:

    data_url = encode_image_to_b64(img_bgr, ext=".jpg")

    prompt = (
        "将图中的谱图曲线涂为蓝色#0000FF，背景白色，坐标轴黑色，保留全部谱图曲线与坐标轴（以及刻度），同时切割掉这之外的无关内容；"
        "消除谱图区域的透视变形，使X轴和Y轴垂直，图像整体无旋转倾斜；"
        "去除噪点和伪影，保持图像清晰自然。"
    )

    messages = [
        {
            "role": "user",
            "content": [
                {"image": data_url},
                {"text": prompt},
            ], 
        }
    ]

    response = None
    last_error = None
    max_retries = 3

    for attempt in range(max_retries):
        try:
            response = MultiModalConversation.call(
                api_key=DASHSCOPE_API_KEY,
                model=model,
                messages=messages,
                stream=False,
                n=1,
                negative_prompt=" "
            )
            break # 成功则跳出
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                print(f"Qwen-Image-Edit API 网络请求失败 (尝试 {attempt + 1}/{max_retries}): {e}，2秒后重试...")
                time.sleep(2)
            else:
                print(f"Qwen-Image-Edit API 重试次数已耗尽。")

    if response is None:
        raise RuntimeError(f"Qwen-Image-Edit调用失败: {last_error}")

    status_code = getattr(response, 'status_code', None)

    if status_code == 200:
        result_url = None
        output = getattr(response, 'output', None)

        # 解析 output
        choices = getattr(output, 'choices', None)
        # 如果是字典，尝试字典获取
        if choices is None and isinstance(output, dict):
            choices = output.get('choices')

        if choices and len(choices) > 0:
            first_choice = choices[0]
            message = getattr(first_choice, 'message', None)
            if message is None and isinstance(first_choice, dict):
                message = first_choice.get('message')

            if message:
                content_list = getattr(message, 'content', None)
                if content_list is None and isinstance(message, dict):
                    content_list = message.get('content')

                if isinstance(content_list, list):
                    for item in content_list:
                        # 尝试从字典获取
                        if isinstance(item, dict) and 'image' in item:
                            result_url = item['image']
                            break
                        # 尝试从对象属性获取
                        elif hasattr(item, 'image'):
                            result_url = item.image # type: ignore
                            break

        if not result_url:
            raise RuntimeError(f"未返回有效的图像URL, 响应内容: {output}")
    else:
        code = getattr(response, 'code', 'Unknown')
        msg = getattr(response, 'message', 'Unknown')
        raise RuntimeError(f"Qwen-Image-Edit调用失败，状态码: {status_code}, Code: {code}, Msg: {msg}")

    # 下载图像到本地
    if intermediate_dir:
        os.makedirs(intermediate_dir, exist_ok=True)
        save_path = os.path.join(intermediate_dir, "enhanced.jpg")
    else:
        fd, save_path = tempfile.mkstemp(suffix=".jpg")
        os.close(fd)

    download_image(result_url, save_path)

    # 读取下载的图像
    enhanced_img = cv2.imdecode(np.fromfile(save_path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if enhanced_img is None:
        raise RuntimeError(f"无法读取下载的图像: {save_path}")

    return enhanced_img

def process_image_pipeline(image_path: str, output_path: str, intermediate_dir: Optional[str] = None) -> None:
    if intermediate_dir:
        os.makedirs(intermediate_dir, exist_ok=True)

    # VLM 提取增强染色
    print("VLM 提取...")
    spectro_img, detected_polygon = extract_spectrogram_region(image_path)
    if intermediate_dir:
        save_compressed_image(spectro_img, os.path.join(intermediate_dir, "cropped_v1.jpg"), max_mb=5)
        try:
            with open(os.path.join(intermediate_dir, "polygon_coords.json"), "w", encoding="utf-8") as f:
                json.dump({"polygon": detected_polygon}, f, indent=4)
        except Exception: pass

    print("增强...")
    processed = enhance_image(spectro_img, intermediate_dir=intermediate_dir)

    if intermediate_dir:
        save_compressed_image(processed, os.path.join(intermediate_dir, "processed.jpg"), max_mb=5)

    # 保存最终结果图片 < 5MB
    save_compressed_image(processed, output_path, max_mb=5)
    print(f"处理完成，结果已保存到: {output_path}")

def normalize_local_path(path: str) -> str:
    if not path:
        return path
    if path.startswith("file://"):
        p = path[len("file://"):]
        if p.startswith("/") and len(p) > 2 and p[1].isalpha() and p[2] == ":":
            p = p[1:]
        return os.path.abspath(p)
    return os.path.abspath(path)

def main():
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="从照片中提取谱图曲线并增强图像")
    parser.add_argument("image", help="输入照片路径")
    parser.add_argument("output", help="输出图片路径")
    parser.add_argument("--intermediate", help="保存中间图片的目录", default="C:\\Users\\34029\\Desktop\\IR-Project\\Code\\image_processing\\debug")
    parser.add_argument("--step", type=int, choices=[1, 2], default=2, help="可选：只运行到第几步（1:提取 2:提取+增强）")
    args = parser.parse_args()

    img_path = normalize_local_path(args.image)
    out_path = normalize_local_path(args.output)
    intermediate_out = normalize_local_path(args.intermediate)

    # 校验输入图片
    if not os.path.isfile(img_path):
        print(f"输入图片不存在: {img_path}", file=sys.stderr)
        sys.exit(1)

    # 确保输出目录
    out_dir = os.path.dirname(os.path.abspath(out_path)) or os.getcwd()
    try:
        os.makedirs(out_dir, exist_ok=True)
    except Exception as e:
        print(f"无法创建输出目录 {out_dir}: {e}", file=sys.stderr)
        sys.exit(1)

    # 确保中间目录
    if intermediate_out:
        try:
            os.makedirs(intermediate_out, exist_ok=True)
        except Exception as e:
            print(f"无法创建中间目录 {intermediate_out}: {e}", file=sys.stderr)
            sys.exit(1)

    if args.step == 1:
        img, poly = extract_spectrogram_region(img_path)
        save_compressed_image(img, out_path, max_mb=5)
        print(f"已保存提取结果到 {out_path}")

        if intermediate_out:
            coords_path = os.path.join(intermediate_out, "polygon_coords.json")
            try:
                with open(coords_path, "w", encoding="utf-8") as f:
                    json.dump({"polygon": poly}, f, indent=4)
                print(f"提取的区域坐标已保存到: {coords_path}")
            except Exception as e:
                print(f"保存坐标文件失败: {e}")
    else:
        process_image_pipeline(img_path, out_path, intermediate_dir=intermediate_out)

if __name__ == "__main__":
    main()