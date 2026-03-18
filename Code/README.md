# FT-IR AI Analysis Report Generator (红外光谱分析与报告生成系统)

[English](README_en.md) | [简体中文](README.md)

本项目是一套自动化的红外光谱（FT-IR）图像识别、数据处理与智能诊断报告生成流水线。项目集成了红外光谱图曲线抓取以及AI诊断报告自动生成功能，能够大幅提升批量检测报告的自动化水平。

## ✨ 主要功能特性

- **多模态输入处理**：支持直接输入红外光谱图像（智能提取曲线坐标点阵并转化为CSV），也支持直接处理预先导出的 CSV 原始数据文件。
- **图像识别与曲线提取**：包含基于计算机视觉的图像预处理(`pretreat.py`)、光谱曲线染色(`curve_dye.py`)和坐标数据高精度提取(`extract.py`)。
- **红外软件自动化控制**：通过 RPA 脚本 (`ir_rpa.py`) 实现对 OMNIC 桌面软件的后台自动化检索、操控并导出分析图谱 PDF。
- **自动化AI报告生成**：结合抓取的曲线数字特征与图谱结果，自动生成美观排版的格式化 PDF 或 HTML 分析报告。
- **GUI与CLI双重支持**：提供友好的图形化操作界面(`run_gui.py`)以及方便脚本调用的命令行接口(`pipeline.py`)。

## 📂 核心目录结构

- `run_gui.py`: Tkinter图形用户界面主入口程序。
- `pipeline.py`: 核心处理流水线脚本，集成各子模块调用逻辑。
- `image_processing/`: 图像处理模块（预处理、曲线提取）。
- `software_agent/`: OMNIC软件自动化控制模块。
- `report_generator/`: 报告排版与生成模块。
- `Demo/`: 附带的测试样例数据（图片与 CSV）。

## 🚀 快速开始

### 1. 环境准备

推荐使用 Conda 或 venv 创建并激活虚拟环境（建议运行在 Python 3.12+）：

```bash
python -m venv .venv
.\.venv\Scripts\activate

# 安装所需的Python依赖
pip install -r requirements.txt
```

**外部依赖要求：**

- 需要在本地正确安装 **OMNIC** 软件，系统默认RPA路径配置为 `C:\Program Files (x86)\Omnic\omnic32.exe`，如果路径不同请在 `pipeline.py` 中修改路径。

### 2. 运行方案

**A：使用图形界面 (GUI)**
在界面中可随时查看处理日志，选择输入文件与输出目录，勾选是否保留运行过程的中间文件。

```bash
python run_gui.py
```

**B：使用命令行 (CLI)**
提供参数化的流水线调用：

```bash
python pipeline.py <输入文件路径> [输出目录] [--max_size_mb 8] [--no_intermediate]

# 示例 1: 处理红外光谱的截屏图片，输出至 output/ 目录
python pipeline.py Demo/test_image.jpg ./output

# 示例 2: 直接处理已有的 CSV 数据文件
python pipeline.py Demo/7343-3.CSV ./output
```
