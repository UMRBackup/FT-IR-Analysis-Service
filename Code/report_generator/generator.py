import requests
import os
import json
import base64
import csv
import time
from pypdf import PdfReader
from jinja2 import Environment, FileSystemLoader
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from datetime import datetime
from typing import Dict, Any, List, Tuple

try:
    from .compound_search import get_compound_info
except ImportError:
    from compound_search import get_compound_info

try:
    from .literature_search import search_literature_and_cite
except ImportError:
    from literature_search import search_literature_and_cite

try:
    OPENROUTER_API_KEY: str = os.environ["OPENROUTER_API_KEY"]
except KeyError:
    OPENROUTER_API_KEY = ""
    print("Warning: Missing OPENROUTER_API_KEY environment variable")

def call_gemini(prompt: str, model: str = "google/gemini-3.1-pro-preview", max_retries: int = 3) -> Dict[str, Any]:
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
            ]
        }
    ]

    payload = {
        "model": model,
        "messages": messages
    }

    for attempt in range(max_retries):
        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=120 # 设置超时
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            err_msg = str(e)
            print(f"API call failed ({attempt + 1}/{max_retries}): {err_msg}")
            if attempt < max_retries - 1:
                time.sleep(2)  # 等待2秒后重试
            else:
                raise RuntimeError(f"Failed after {max_retries} retries: {err_msg}")
    
    return {}

def extract_pdf_report_text(pdf_path: str) -> str:
    if not os.path.exists(pdf_path):
        print(f"Warning: PDF file not found {pdf_path}")
        return "PDF text not provided or unreadable."

    try:
        reader = PdfReader(pdf_path)
        pdf_text = "\n".join([page.extract_text() for page in reader.pages if page.extract_text()])
        return pdf_text
    except Exception as e:
        print(f"Warning: Failed to read PDF text: {e}")
        return "PDF text not provided or unreadable."

def sample_csv_data(csv_path: str, sample_rate: int = 5) -> Tuple[str, List[List[str]]]:
    if not os.path.exists(csv_path):
        print(f"Warning: CSV file not found {csv_path}")
        return "", []

    try:
        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            rows = [row for row in reader if row]
            # 进行降采样
            sampled_rows = rows[::sample_rate] 
            csv_text = "\n".join([f"{r[0]}, {r[1]}" for r in sampled_rows])
        return csv_text, rows
    except Exception as e:
        print(f"Warning: Failed to read CSV: {e}")
        return "", []

def generate_spectrum_image(csv_rows: List[List[str]], output_image_path: str) -> str:
    if not csv_rows:
        return ""

    try:
        matplotlib.rcParams['font.sans-serif'] = ['SimHei']
        matplotlib.rcParams['axes.unicode_minus'] = False

        x_data = []
        y_data = []

        for row in csv_rows:
            try:
                x_data.append(float(row[0]))
                y_data.append(float(row[1]))
            except ValueError:
                continue

        if not x_data or not y_data:
            return ""

        # 判断数据类型
        max_y = max(y_data)
        is_transmittance = max_y > 3.0

        y_label = 'Transmittance (%)' if is_transmittance else 'Absorbance'
        title = 'IR Spectrum'

        plt.figure(figsize=(10, 5))

        # X轴（波数）倒序排列
        plt.plot(x_data, y_data, color='#1f77b4', linewidth=1.5)

        if x_data[0] < x_data[-1]:
            plt.gca().invert_xaxis() # 从高到低排列

        plt.xlabel('Wavenumber (cm$^{-1}$)')  # 使用 MathText 替代特殊字符
        plt.ylabel(y_label)
        plt.title(title)

        # 添加网格线
        plt.grid(True, which='both', linestyle='--', linewidth=0.5, alpha=0.7)
        plt.tight_layout()

        # 如果输出路径的文件夹不存在，自动创建
        os.makedirs(os.path.dirname(os.path.abspath(output_image_path)), exist_ok=True)
        plt.savefig(output_image_path, dpi=300, facecolor='w', edgecolor='w', bbox_inches='tight')
        plt.close()

        return output_image_path

    except Exception as e:
        print(f"[Image Generation Error] Exception: {e}")
        return ""

def analyze_spectrum_with_ai(pdf_text: str, csv_text: str) -> Dict[str, Any]:
    prompt = f"""
你是一个专业的红外光谱(IR)分析专家。以下是OMNIC的【检索匹配报告】以及【红外光谱数据(波数与透过率/吸光度的采样点)】。
请你对这些数据进行深度的综合分析，并 **严格按照以下JSON格式返回结果**(不要返回任何其他格式字符或Markdown边界符号如 ```json)。

{{
  "detected_compounds": [
    {{
      "name_cn": "物质的中文名",
      "name_en": "物质的英文名",
      "cas": "CAS号(若无请填'-')",
      "formula": "化学式(若无请填'-')",
      "weight": "分子量(若无请填'-')",
      "content": "含量百分比(%)"
    }}
  ],
  "key_peaks": [
    {{
      "x": "特征波数(例如 3300或大约范围)",
      "note": "该峰对应的官能团归属及特征(如：-OH 伸缩振动，强峰)"
    }}
  ],
  "analysis_text": "此处填写你的综合分析结论，采用分点分段论述。说明谱图中哪些重要的峰佐证了对应的官能团，并给出你综合判定所含物质的理由。论述中不要提及OMNIC检索报告中的信息。"
}}

注意：content 条目可能难以精确地确定，请大致估计，如高纯物质可写 >95，只可以使用数学表示，不可置空。detected_compounds 列表最多提供前三名最有可能的物质，是否采纳匹配列表中的其他物质由你综合考虑决定。key_peaks 提取具代表性的峰，尽量多些。分析结论不能提及检索报告的检索结果和匹配度分数等内容，而是要基于谱图特征和化学知识进行综合判断。

============ 初步检索报告文字 ============
{pdf_text}

============ CSV 谱图采样点(波数, 值) ============
{csv_text}
"""
    try:
        response_data = call_gemini(prompt)
        
        # 检查并安全获取 content
        if not response_data or 'choices' not in response_data or not response_data['choices']:
            print(f"  -> Invalid API response format: {response_data}")
            return {}
            
        message = response_data['choices'][0].get('message', {})
        content = message.get('content')
        
        if content is None:
            print("  -> AI model returned empty content (possible safety filter or network error)")
            return {}
            
        raw_content = content.strip()

        # 清洗可能带有的 markdown 标识
        if raw_content.startswith("```json"):
            raw_content = raw_content[7:]
        if raw_content.endswith("```"):
            raw_content = raw_content[:-3]

        ai_data = json.loads(raw_content.strip())
        return ai_data
    except json.JSONDecodeError:
        print("  -> Warning: Parsing failed!")
        return {}
    except Exception as e:
        print(f"  -> Analysis exception: {e}")
        return {}

def generate_pdf_report(ai_data: Dict[str, Any], csv_path: str, image_path: str, output_path: str, references: List[Any] = [], structure_images: List[str] = []) -> None:
    try:
        template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "template")
        env = Environment(loader=FileSystemLoader(template_dir))
        template = env.get_template("report_template.html")

        # 组装数据并抹平异常值
        sample_id = os.path.basename(csv_path).split('.')[0] if csv_path else "未知样品"
        img_url = f"file:///{os.path.abspath(image_path).replace(chr(92), '/')}" if image_path and os.path.exists(image_path) else ""

        render_context = {
            "report_title": "红外光谱AI智能分析报告",
            "sample_id": sample_id,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "spectrum_image": img_url,
            "detected_compounds": ai_data.get("detected_compounds", []),
            "key_peaks": ai_data.get("key_peaks", []),
            "analysis_text": ai_data.get("analysis_text", "AI 分析过程未能生成有效结论。"),
            "references": references or [],
            "structure_images": structure_images
        }

        html_out = template.render(**render_context)

        # 落盘保存一份 HTML 文件
        html_output_path = output_path.replace(".pdf", ".html")
        with open(html_output_path, "w", encoding="utf-8") as f:
            f.write(html_out)

        # 尝试使用 WeasyPrint 渲染 PDF
        try:
            from weasyprint import HTML
            HTML(string=html_out, base_url=template_dir).write_pdf(output_path)
            print(f"Report generated successfully! Saved to: {output_path}")
        except Exception as e:
            import subprocess
            edge_paths = [
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Google\Chrome\Application\chrome.exe"
            ]
            browser_path = next((p for p in edge_paths if os.path.exists(p)), None)

            if browser_path:
                try:
                    subprocess.run([
                        browser_path,
                        "--headless",
                        "--disable-gpu",
                        "--no-pdf-header-footer",
                        f"--print-to-pdf={os.path.abspath(output_path)}",
                        os.path.abspath(html_output_path)
                    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    print(f"Report generated successfully! Saved to: {output_path}")
                except Exception as eval_e:
                     print(f"Export failed: {eval_e}")
            else:
                print("Could not find Edge/Chrome browser for automatic conversion. Please view the HTML file directly.")

    except Exception as e:
        print(f"Core report rendering process failed: {e}")

def generate_report(csv_path: str, pdf_path: str, output_path: str) -> None:
    # 1. 提取基础分析数据 (PDF纯文本 + 降采样的CSV)
    pdf_text = extract_pdf_report_text(pdf_path)
    csv_text, full_csv_rows = sample_csv_data(csv_path, sample_rate=5)

    # 2. 自动生成用于渲染的图表
    generated_img_path = ""
    if full_csv_rows:
        img_temp_path = os.path.join(os.path.dirname(os.path.abspath(output_path)), "spectrum_plot_auto.png")
        print("Generating spectrum image...")
        generated_img_path = generate_spectrum_image(full_csv_rows, img_temp_path)

    # 3. 将两部分数据交由大模型进行深度分析处理
    ai_analysis_result = analyze_spectrum_with_ai(pdf_text, csv_text)

    # 4. 对结果进行二次校对
    if not ai_analysis_result:
        print("Warning: No valid analysis result obtained, an empty template report will be generated")
    else:
        detected_compounds = ai_analysis_result.get("detected_compounds", [])
        for comp in detected_compounds:
            en_name = comp.get("name_en", "").strip()
            # 仅在有有效的英文名称时进行校验
            if en_name and en_name not in ["-", "未知", "N/A", "Unknown", "None", "null"]:
                info = get_compound_info(en_name)
                if info:
                    if info.get("rn"):
                        comp["cas"] = info.get("rn")
                    if info.get("molecularFormula"):
                        comp["formula"] = info.get("molecularFormula")
                    if info.get("molecularMass"):
                        comp["weight"] = info.get("molecularMass")

                    images_list = []

                    # 单个图片
                    image_data = info.get("image")
                    if image_data:
                        images_list.append(image_data)

                    # 多个图片
                    images_data = info.get("images")
                    if isinstance(images_data, list):
                        images_list.extend(images_data)

                    comp["images"] = images_list

        # 根据 CAS 号对重复物质进行合并
        merged_compounds = []
        seen_cas = {}
        import re

        def extract_content_val(s):
            m = re.search(r'\d+(\.\d+)?', str(s))
            return float(m.group()) if m else -1.0

        for comp in detected_compounds:
            cas = comp.get("cas", "").strip()
            if cas and cas not in ["-", "未知", "N/A", "Unknown", "None", "null", ""]:
                if cas in seen_cas:
                    existing_comp = seen_cas[cas]
                    # 名称保留并合并
                    if comp.get("name_cn") and comp.get("name_cn") not in existing_comp.get("name_cn", ""):
                        existing_comp["name_cn"] = f"{existing_comp.get('name_cn', '')} / {comp['name_cn']}"
                    if comp.get("name_en") and comp.get("name_en") not in existing_comp.get("name_en", ""):
                        existing_comp["name_en"] = f"{existing_comp.get('name_en', '')} / {comp['name_en']}"

                    # 含量取最大值
                    if extract_content_val(comp.get("content", "")) > extract_content_val(existing_comp.get("content", "")):
                        existing_comp["content"] = comp.get("content", "")

                    # 分子量、化学式补齐
                    if not existing_comp.get("formula") or existing_comp.get("formula") in ["-", "", "未知"]:
                        existing_comp["formula"] = comp.get("formula", existing_comp.get("formula"))
                    if not existing_comp.get("weight") or existing_comp.get("weight") in ["-", "", "未知"]:
                        existing_comp["weight"] = comp.get("weight", existing_comp.get("weight"))

                    if comp.get("images"):
                        if "images" not in existing_comp:
                            existing_comp["images"] = []
                        existing_comp["images"].extend([img for img in comp["images"] if img not in existing_comp["images"]])
                else:
                    seen_cas[cas] = comp
                    merged_compounds.append(comp)
            else:
                merged_compounds.append(comp)
        ai_analysis_result["detected_compounds"] = merged_compounds

    # 获取文献引用
    references = []
    seen_references = set()
    if ai_analysis_result:
        for comp in ai_analysis_result.get("detected_compounds", []):
            en_name = comp.get("name_en", "").strip()
            if en_name and en_name not in ["-", "未知", "N/A", "Unknown", "None", "null"]:
                keyword = f"{en_name} infrared"
                citations = search_literature_and_cite(keyword, max_results=3)
                if citations:
                    added_count = 0
                    for citation in citations:
                        # 用 title 或 apa_citation 作为去重依据
                        ref_key = citation.get("apa_citation", citation.get("title", ""))
                        if ref_key and ref_key not in seen_references:
                            seen_references.add(ref_key)
                            references.append(citation)
                            added_count += 1

    # 5. 提取并转换结构图为 base64 数据 URI
    structure_images = []
    if ai_analysis_result:
        for comp in ai_analysis_result.get("detected_compounds", []):
            for svg_str in comp.get("images", []):
                val = svg_str.strip()
                if val.startswith("<svg"):
                    b64_img = base64.b64encode(val.encode('utf-8')).decode('utf-8')
                    data_uri = f"data:image/svg+xml;base64,{b64_img}"
                    if data_uri not in structure_images:
                        structure_images.append(data_uri)
                elif val.startswith("data:image"):
                    if val not in structure_images:
                        structure_images.append(val)

    # 6. 根据结果渲染终版 PDF 
    generate_pdf_report(
        ai_data=ai_analysis_result,
        csv_path=csv_path,
        image_path=generated_img_path,
        output_path=output_path,
        references=references,
        structure_images=structure_images
    )

def main():
    import argparse

    parser = argparse.ArgumentParser(description="AI 智能红外光谱报告生成器")
    parser.add_argument("--csv", required=True, help="输入的 CSV 谱图数据文件路径")
    parser.add_argument("--pdf", required=True, help="OMNIC 初步生成的检索匹配 PDF 报告路径")
    parser.add_argument("--output", required=True, help="最终输出的 AI PDF 报告路径")
    args = parser.parse_args()

    generate_report(args.csv, args.pdf, args.output)

if __name__ == "__main__":
    main()