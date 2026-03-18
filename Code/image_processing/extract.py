import re
import os
import json
import base64
import time
import csv
from typing import Optional, Tuple, Any, Union
import cv2
import numpy as np
from sklearn.linear_model import RANSACRegressor, LinearRegression
from dashscope import MultiModalConversation
import requests

try:
    DASHSCOPE_API_KEY: str = os.environ["DASHSCOPE_API_KEY"]
except KeyError:
    DASHSCOPE_API_KEY = ""
    raise RuntimeError("缺少环境变量 DASHSCOPE_API_KEY")

try:
    OPENROUTER_API_KEY: str = os.environ["OPENROUTER_API_KEY"]
except KeyError:
    OPENROUTER_API_KEY = ""
    raise RuntimeError("缺少环境变量 OPENROUTER_API_KEY")

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

def save_vlm_output(raw: Any, debug_dir: Optional[str]) -> None:
    if not debug_dir:
        return
    try:
        os.makedirs(debug_dir, exist_ok=True)
        out_path = os.path.join(debug_dir, "vlm_output.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(raw, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[VLM] 保存原始输出失败: {e}")

def call_gemini_vision(prompt: str, image_input: str, model: str = "google/gemini-3-pro-preview", debug_dir: Optional[str] = None) -> Any:

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
                        "url": image_input
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
            timeout=60 # 设置超时
        )
        response.raise_for_status()
        resp_json = response.json()
        content = resp_json['choices'][0]['message']['content'] or ""
    except Exception as e:
        error_msg = str(e)
        raise RuntimeError(f"OpenRouter API 调用失败：{error_msg}")

    # 提取 JSON
    if "```" in content:
        match = re.search(r"```(?:json)?(.*?)```", content, re.DOTALL)
        if match:
            content = match.group(1)

    parsed = json.loads(content.strip())
    save_vlm_output(parsed, debug_dir)
    return parsed

def call_qwen_vision(prompt: str, image_input: str, model: str = "qwen3-vl-plus", debug_dir: Optional[str] = None) -> Any:

    messages = [
        {
            "role": "user",
            "content": [
                {"image": image_input},
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

    parsed = json.loads(text.strip())
    save_vlm_output(parsed, debug_dir)
    return parsed

def fit_linear_mapping(pixel_vals):
    # RANSAC拟合
    if not pixel_vals or len(pixel_vals) < 2: return None
    data = np.array(pixel_vals, dtype=float)
    X = data[:, 0].reshape(-1, 1)
    y = data[:, 1]

    # 点太少用线性回归
    if len(X) < 3:
        m, b = np.polyfit(X.flatten(), y, 1)
        return float(m), float(b)

    try:
        # 误差范围为值域的 4%
        val_range = np.max(y) - np.min(y) if len(y) > 0 else 1
        threshold = val_range * 0.04
        if threshold == 0: threshold = 1.0

        ransac = RANSACRegressor(
            estimator=LinearRegression(),
            min_samples=2,
            residual_threshold=threshold,
            random_state=42
        )
        ransac.fit(X, y)

        # 获取拟合出的模型参数
        estimator = ransac.estimator_
        m = estimator.coef_[0]
        b = estimator.intercept_

        inlier_mask = ransac.inlier_mask_
        n_inliers = np.sum(inlier_mask)
        n_outliers = len(X) - n_inliers
        print(f"  [RANSAC] 拟合完成: m={m:.4f}, b={b:.2f} (Inliers: {n_inliers}, Outliers: {n_outliers})")

        return float(m), float(b)

    except Exception as e:
        print(f"  [RANSAC] 拟合失败，回退到线性回归: {e}")
        m, b = np.polyfit(X.flatten(), y, 1)
        return float(m), float(b)

def refine_tick_location(grad_map: np.ndarray, gray_img: np.ndarray, axis: str, box_2d: list, img_w: int, img_h: int) -> float:
    ymin, xmin, ymax, xmax = box_2d

    # 归一化坐标(0-1000) -> 像素坐标
    x1 = int(xmin / 1000.0 * img_w)
    x2 = int(xmax / 1000.0 * img_w)
    y1 = int(ymin / 1000.0 * img_h)
    y2 = int(ymax / 1000.0 * img_h)

    # 兜底：框中心
    cx = (x1 + x2) / 2.0
    cy = (y1 + y2) / 2.0

    # 搜索范围设置
    if axis == 'x':
        # X轴刻度：通常在数字上方/下方，或者是轴线上的黑块
        margin_x = 4   # 水平方向限制在数字宽度内
        search_range = 60 # 垂直搜索范围 (向上/下找轴线)

        roi_x1 = max(0, x1 - margin_x)
        roi_x2 = min(img_w, x2 + margin_x)
        roi_y1 = max(0, y1 - search_range)
        roi_y2 = min(img_h, y2 + search_range)

        if roi_x2 <= roi_x1 or roi_y2 <= roi_y1: return cx

        roi_grad = grad_map[roi_y1:roi_y2, roi_x1:roi_x2]
        roi_gray = gray_img[roi_y1:roi_y2, roi_x1:roi_x2]

        # 策略 A: 梯度投影
        grad_proj = np.sum(roi_grad, axis=0)
        grad_peak_idx = int(np.argmax(grad_proj))
        grad_max_val = grad_proj[grad_peak_idx]
        grad_mean_val = np.mean(grad_proj) if grad_proj.size > 0 else 0

        # 如果梯度峰值非常显著 (例如是均值的2倍以上)，说明有明显的垂直线
        if grad_max_val > grad_mean_val * 2.0 and grad_max_val > 1000:
            return float(roi_x1 + grad_peak_idx)

        # 策略 B: 灰度极值

        # 反转灰度：黑 -> 255, 白 -> 0
        gray_inv = 255 - roi_gray

        row_means = np.mean(roi_gray, axis=1)
        axis_rows_mask = row_means < 200 # 假设背景是近似白色，轴线行比较暗

        if np.any(axis_rows_mask):
            # 只在疑似轴线的行中进行投影
            masked_roi = gray_inv[axis_rows_mask, :]
            if masked_roi.shape[0] > 0:
                dark_proj = np.sum(masked_roi, axis=0) # 累加黑度

                # 简单平滑
                dark_proj = cv2.GaussianBlur(dark_proj.reshape(1, -1), (3, 1), 0).flatten()

                dark_peak_idx = int(np.argmax(dark_proj))
                dark_max = dark_proj[dark_peak_idx]
                dark_mean = np.mean(dark_proj)

                if dark_max > dark_mean * 1.2:
                     return float(roi_x1 + dark_peak_idx)

        # 如果两个策略都失败，返回数字中心
        return cx

    elif axis == 'y':
        # Y轴逻辑类似
        margin_y = 4
        search_range = 60

        roi_y1 = max(0, y1 - margin_y)
        roi_y2 = min(img_h, y2 + margin_y)
        roi_x1 = max(0, x1 - search_range)
        roi_x2 = min(img_w, x2 + search_range)

        if roi_x2 <= roi_x1 or roi_y2 <= roi_y1: return cy

        roi_grad = grad_map[roi_y1:roi_y2, roi_x1:roi_x2]
        roi_gray = gray_img[roi_y1:roi_y2, roi_x1:roi_x2]

        # 策略 A: 梯度投影 (寻找水平线)
        grad_proj = np.sum(roi_grad, axis=1) # 行投影
        grad_peak_idx = int(np.argmax(grad_proj))
        grad_max_val = grad_proj[grad_peak_idx]
        grad_mean_val = np.mean(grad_proj) if grad_proj.size > 0 else 0

        if grad_max_val > grad_mean_val * 2.0 and grad_max_val > 1000:
            return float(roi_y1 + grad_peak_idx)

        # 策略 B: 灰度极值
        gray_inv = 255 - roi_gray

        # 找出"可能有轴线"的列 (垂直方向灰度值普遍较低的列)
        col_means = np.mean(roi_gray, axis=0)
        axis_cols_mask = col_means < 200

        if np.any(axis_cols_mask):
            masked_roi = gray_inv[:, axis_cols_mask]
            if masked_roi.shape[1] > 0:
                # 注意：masked_roi 不再保持原始空间位置，这步仅用于判断是否存在强黑块
                # 重新在原始 ROI 上做加权处理比较好

                # 简化逻辑：直接对原始inv灰度图做加权行投影
                # 给予较暗的列更高的权重
                weights = (col_means < 150).astype(float) # 只有深色轴线列参与投票
                weighted_roi = gray_inv * weights.reshape(1, -1)

                dark_proj = np.sum(weighted_roi, axis=1)
                dark_proj = cv2.GaussianBlur(dark_proj.reshape(-1, 1), (1, 3), 0).flatten()
                
                dark_peak_idx = int(np.argmax(dark_proj))

                # 验证这个峰值是否真的对应一个黑点
                # 检查该行最黑的像素是否够黑
                row_min_val = np.min(roi_gray[dark_peak_idx, :])
                if row_min_val < 100: # 必须有深灰/黑色像素
                    return float(roi_y1 + dark_peak_idx)

        return cy

    return cx if axis == 'x' else cy

def get_axis_info(img_bgr: np.ndarray, debug_dir: Optional[str] = None) -> Tuple[Optional[Tuple[float, float]], Optional[Tuple[float, float]]]:
    if not DASHSCOPE_API_KEY or not OPENROUTER_API_KEY:
        print("错误: 缺少 API Key。")
        return None, None

    h, w = img_bgr.shape[:2]
    img_b64 = encode_image_to_b64(img_bgr)

    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

    # Sobel 算子提取边缘
    # abs_grad_x 响应垂直线 (检测X轴刻度)
    grad_x = cv2.Sobel(gray, cv2.CV_16S, 1, 0, ksize=3)
    abs_grad_x = cv2.convertScaleAbs(grad_x)

    # abs_grad_y 响应水平线 (检测Y轴刻度)
    grad_y = cv2.Sobel(gray, cv2.CV_16S, 0, 1, ksize=3)
    abs_grad_y = cv2.convertScaleAbs(grad_y)

    # 去除非线性的噪点
    # 对于垂直线(X刻度)，强化垂直结构
    kernel_v = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 5))
    clean_grad_x = cv2.morphologyEx(abs_grad_x, cv2.MORPH_CLOSE, kernel_v)

    # 对于水平线(Y刻度)
    kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 1))
    clean_grad_y = cv2.morphologyEx(abs_grad_y, cv2.MORPH_CLOSE, kernel_h)

    if debug_dir:
        cv2.imwrite(os.path.join(debug_dir, "debug_grad_x.jpg"), clean_grad_x)
        cv2.imwrite(os.path.join(debug_dir, "debug_grad_y.jpg"), clean_grad_y)

    # VLM 获取区域
    prompt = (
        "Output the axis ticks of this infrared spectrum plot in JSON."
        "The X-axis represents Wavenumber (cm-1) and Y-axis represents Transmittance (%) or Absorbance."
        "Return object format: {'x_axis': [{'value': number, 'box_2d': [ymin, xmin, ymax, xmax]}, ...], 'y_axis': [...]}"
        "Requirements:"
        "1. 'value' must be a number, which represents the axis tick value."
        "2. 'box_2d' must use normalized coordinates (0-1000)."
        "3. Only detect the numbers ON THE AXIS lines. Ignore potential peak labels inside the plot."
        "4. The numbers on the same axis usually have the same step size between them, both in value and in pixel distance."
    )

    print("调用 VLM 进行轴线数值定位...")
    # try:
    data = call_gemini_vision(prompt, img_b64, model="google/gemini-3-pro-preview", debug_dir=debug_dir)

    x_points = []
    y_points = []
    x_debug_info = []
    y_debug_info = []

    # 处理 X 轴
    if 'x_axis' in data:
        for item in data['x_axis']:
            try:
                val_str = str(item.get('value', '')).replace('−', '-')
                val = float(re.findall(r"[-+]?\d*\.?\d+", val_str)[0])
                box = item.get('box_2d')
                if not box or len(box) != 4: continue # 修复之前的空缩进

                # 基于梯度图 + 灰度图精定位
                final_px = refine_tick_location(clean_grad_x, gray, 'x', box, w, h)

                x_points.append((final_px, val))

                ymin, xmin, ymax, xmax = box
                cx = ((xmin + xmax) / 2000.0) * w
                cy = ((ymin + ymax) / 2000.0) * h
                x_debug_info.append((box, cx, cy, final_px, val))
            except: continue

    # 处理 Y 轴
    if 'y_axis' in data:
        for item in data['y_axis']:
            try:
                val_str = str(item.get('value', '')).replace('−', '-')
                val = float(re.findall(r"[-+]?\d*\.?\d+", val_str)[0])
                box = item.get('box_2d')
                if not box or len(box) != 4: continue # 修复之前的空缩进

                # 基于梯度图 + 灰度图精定位
                final_py = refine_tick_location(clean_grad_y, gray, 'y', box, w, h)

                y_points.append((final_py, val))

                ymin, xmin, ymax, xmax = box
                cx = ((xmin + xmax) / 2000.0) * w
                cy = ((ymin + ymax) / 2000.0) * h
                y_debug_info.append((box, cx, cy, final_py, val))

            except: continue

    print(f"匹配结果 -> X轴有效点 {len(x_points)} 个, Y轴有效点 {len(y_points)} 个")

    # 调试绘图
    if debug_dir:
        vis = img_bgr.copy()

        for box, cx, cy, final_px, val in x_debug_info:
            ymin, xmin, ymax, xmax = box
            x1 = int(xmin / 1000.0 * w)
            x2 = int(xmax / 1000.0 * w)
            y1 = int(ymin / 1000.0 * h)
            y2 = int(ymax / 1000.0 * h)

            cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 200, 255), 1)
            cv2.circle(vis, (int(cx), int(cy)), 3, (255, 255, 0), -1)

            cv2.line(vis, (int(final_px), 0), (int(final_px), h - 1), (0, 255, 0), 1)
            cv2.circle(vis, (int(final_px), int(cy)), 4, (0, 255, 0), -1)
            cv2.putText(vis, f"X:{val:g}", (int(final_px) + 4, max(12, int(cy) - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 180, 0), 1)

        for box, cx, cy, final_py, val in y_debug_info:
            ymin, xmin, ymax, xmax = box
            x1 = int(xmin / 1000.0 * w)
            x2 = int(xmax / 1000.0 * w)
            y1 = int(ymin / 1000.0 * h)
            y2 = int(ymax / 1000.0 * h)

            cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 200, 255), 1)
            cv2.circle(vis, (int(cx), int(cy)), 3, (255, 255, 0), -1)

            cv2.line(vis, (0, int(final_py)), (w - 1, int(final_py)), (0, 0, 255), 1)
            cv2.circle(vis, (int(cx), int(final_py)), 4, (0, 0, 255), -1)
            cv2.putText(vis, f"Y:{val:g}", (max(4, int(cx) + 6), int(final_py) - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 180), 1)

        cv2.imwrite(os.path.join(debug_dir, "vlm_mapping_result.jpg"), vis)

    return fit_linear_mapping(x_points), fit_linear_mapping(y_points)

def crop_plot_area(img_bgr: np.ndarray, debug_dir: Optional[str] = None) -> Tuple[np.ndarray, int, int]:
    h, w = img_bgr.shape[:2]
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)

    # 去噪，防止框干扰
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
    closed = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)

    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    best_rect = (0, 0, w, h)
    max_area = 0
    total_area = w * h
    found = False

    # 找最大框
    for cnt in contours:
        x, y, rw, rh = cv2.boundingRect(cnt)
        area = rw * rh
        if area > total_area * 0.25:
            if area > max_area:
                max_area = area
                best_rect = (x, y, rw, rh)
                found = True

    if not found:
        print("未检测到明显的绘图边框，默认全图分析。")
        return img_bgr, 0, 0

    x, y, rw, rh = best_rect
    # 向内收缩 margin
    margin = 4
    if rw > 2*margin and rh > 2*margin:
        x += margin; y += margin; rw -= 2*margin; rh -= 2*margin

    print(f"检测到绘图区域: {rw}x{rh} @ ({x},{y})")
    cropped = img_bgr[y:y+rh, x:x+rw]

    if debug_dir:
        cv2.imwrite(os.path.join(debug_dir, "debug_crop.jpg"), cropped)

    return cropped, x, y

def _correct_y_mapping_with_bounds(y_map: Tuple[float, float], curve_pixels: list) -> Tuple[float, float]:
    if not curve_pixels:
        return y_map
    m, b = y_map
    vals = [m * py + b for _, py in curve_pixels]
    y_min = float(np.min(vals))
    y_max = float(np.max(vals))

    upper = 100.0 if y_max > 2.0 else 1.0
    eps = 0.1 if upper == 100.0 else 0.001

    if y_min >= eps and y_max <= (upper - eps):
        return y_map

    if y_max == y_min:
        target = min(max(y_min, eps), upper - eps)
        new_b = b + (target - y_min)
        print(f"  [Y校正] 单值范围，b: {b:.2f}->{new_b:.2f}")
        return m, new_b

    target_min = max(eps, y_min)
    target_max = min(upper - eps, y_max)

    if target_max <= target_min:
        # 回退为平移校正
        shift = 0.0
        if y_max > (upper - eps):
            shift = (upper - eps) - y_max
        elif y_min < eps:
            shift = eps - y_min
        new_b = b + shift
        print(f"  [Y校正] 退化平移，b: {b:.2f}->{new_b:.2f}")
        return m, new_b

    s = (target_max - target_min) / (y_max - y_min)
    d = target_min - s * y_min
    new_m = m * s
    new_b = b * s + d
    print(f"  [Y校正] scale={s:.4f}, shift={d:.4f} => m: {m:.4f}->{new_m:.4f}, b: {b:.2f}->{new_b:.2f}")
    return new_m, new_b

def extract_function_points(image_input: Union[str, np.ndarray], debug_dir: Optional[str] = None):
    spec_bgr = _load_image_bgr(image_input)

    # 排除周围文字，只留纯曲线
    plot_img, offset_x, offset_y = crop_plot_area(spec_bgr, debug_dir)
    h, w = plot_img.shape[:2]

    # 提取曲线 (优先蓝色，其次找黑色)
    hsv = cv2.cvtColor(plot_img, cv2.COLOR_BGR2HSV)
    mask_blue = cv2.inRange(hsv, np.array([100, 200, 200]), np.array([140, 255, 255]))

    if cv2.countNonZero(mask_blue) < 100:
        print("未发现蓝色曲线，尝试提取黑色曲线...")
        gray = cv2.cvtColor(plot_img, cv2.COLOR_BGR2GRAY)
        # 二值反转
        _, mask_blue = cv2.threshold(gray, 100, 255, cv2.THRESH_BINARY_INV)
    else:
        # 连接断点
        mask_blue = cv2.morphologyEx(mask_blue, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))

    if debug_dir:
        cv2.imwrite(os.path.join(debug_dir, "debug_curve_mask.jpg"), mask_blue)

    # 建立坐标映射 
    print("开始进行坐标映射分析...")
    x_map, y_map = get_axis_info(spec_bgr, debug_dir)

    if not x_map: x_map = (1.0, 0.0)
    if not y_map: y_map = (1.0, 0.0)

    print(f"映射函数建立: X_val = {x_map[0]:.4f}*px + {x_map[1]:.2f}")
    print(f"映射函数建立: Y_val = {y_map[0]:.4f}*py + {y_map[1]:.2f}")

    # 收集曲线像素点
    curve_pixels = []
    for local_px in range(w):
        col = mask_blue[:, local_px]
        ys = np.where(col > 0)[0]
        if ys.size > 0:
            local_py = np.median(ys)
            global_px = local_px + offset_x
            global_py = local_py + offset_y
            curve_pixels.append((global_px, global_py))

    if not curve_pixels:
        return []

    # Y 轴校正
    y_map = _correct_y_mapping_with_bounds(y_map, curve_pixels)

    # 扫描曲线并转换
    result_data = []
    for global_px, global_py in curve_pixels:
        val_x = x_map[0] * global_px + x_map[1]
        val_y = y_map[0] * global_py + y_map[1]
        result_data.append((val_x, val_y, global_px, global_py))

    return result_data

def _load_image_bgr(image_input: Union[str, np.ndarray]) -> np.ndarray:
    if isinstance(image_input, np.ndarray):
        return image_input

    if not isinstance(image_input, str):
        raise TypeError("image_input 必须是 str(路径) 或 np.ndarray(BGR图像)")

    if not os.path.exists(image_input):
        raise FileNotFoundError(f"错误: 找不到文件 '{image_input}'")

    # 用 imdecode + fromfile 兼容中文路径
    img = cv2.imdecode(np.fromfile(image_input, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"错误: 无法读取图像 '{image_input}'")
    return img

def extract_to_csv(
    image_input: Union[str, np.ndarray],
    output_csv: str,
    debug_dir: Optional[str] = None
):
    data = extract_function_points(image_input, debug_dir=debug_dir)

    os.makedirs(os.path.dirname(output_csv), exist_ok=True)
    with open(output_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        for p in data:
            writer.writerow([f"{p[0]:.2f}", f"{p[1]:.2f}"])
    return data

def main():
    import sys
    import argparse

    parser = argparse.ArgumentParser(description="提取曲线数据点")
    parser.add_argument("image_path", help="输入图像路径")
    parser.add_argument("output", help="输出CSV文件路径")
    parser.add_argument("--debug_dir", "-d", default="C:\\Users\\34029\\Desktop\\IR-Project\\Code\\image_processing\\debug", help="调试输出目录")

    args = parser.parse_args()

    os.makedirs(args.debug_dir, exist_ok=True)
    os.makedirs(os.path.dirname(args.output), exist_ok=True)

    try:
        start_time = time.time()
        data = extract_to_csv(args.image_path, args.output, debug_dir=args.debug_dir)
        elapsed = time.time() - start_time

        print(f"分析完成，耗时 {elapsed:.2f} 秒。")
        print(f"提取到 {len(data)} 个数据点。")

        if data:
            debug_csv_path = os.path.join(args.debug_dir, "extracted.csv")
            with open(debug_csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['Value_X', 'Value_Y', 'Pixel_X', 'Pixel_Y'])
                for p in data:
                    writer.writerow([f"{p[0]:.2f}", f"{p[1]:.2f}", int(p[2]), int(p[3])])
            print(f"调试数据已保存至: {debug_csv_path}")
            print(f"最终结果已保存至: {args.output}")
        else:
            print("未能提取到有效的数据点。")

    except Exception as e:
        print(f"执行过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()