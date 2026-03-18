# FT-IR AI Analysis Report Generator

[English](README_en.md) | [简体中文](README.md)

This project is an automated pipeline for FT-IR (Fourier Transform Infrared Spectroscopy) image recognition, data processing, and intelligent diagnostic report generation. It integrates FT-IR spectral curve extraction and automated AI diagnostic report generation, significantly improving the automation level of batch testing reports.

## ✨ Main Features

- **Multi-modal Input Processing**: Supports direct input of FT-IR spectrum images (intelligently extracts curve coordinate dot matrices and converts them to CSV), as well as direct processing of pre-exported CSV raw data files.
- **Image Recognition and Curve Extraction**: Includes computer vision-based image preprocessing (`pretreat.py`), spectral curve dyeing (`curve_dye.py`), and high-precision coordinate data extraction (`extract.py`).
- **Infrared Software Automation Control**: Achieves background automated retrieval, operation, and spectral PDF export for the OMNIC desktop software via RPA scripts (`ir_rpa.py`).
- **Automated AI Report Generation**: Generates beautifully formatted PDF or HTML diagnostic reports automatically by combining the digital features of the extracted curves with the spectral results.
- **Dual Support for GUI and CLI**: Provides a user-friendly graphical user interface (`run_gui.py`) and a command-line interface (`pipeline.py`) that is convenient for script invocation.

## 📂 Core Directory Structure

- `run_gui.py`: The main entry point for the Tkinter graphical user interface.
- `pipeline.py`: The core processing pipeline script that integrates the calling logic of various submodules.
- `image_processing/`: Image processing module (preprocessing, curve extraction).
- `software_agent/`: Automation control module for the OMNIC software.
- `report_generator/`: Report layout and generation module.
- `Demo/`: Included test sample data (images and CSV files).

## 🚀 Quick Start

### 1. Environment Preparation

It is recommended to use Conda or venv to create and activate a virtual environment (running on Python 3.12+ is advised):

```bash
python -m venv .venv
.\.venv\Scripts\activate

# Install the required Python dependencies
pip install -r requirements.txt
```

**External Dependency Requirements:**

- The **OMNIC** software needs to be correctly installed locally. The default RPA path in the system is configured as `C:\Program Files (x86)\Omnic\omnic32.exe`. If the path is different, please modify it in `pipeline.py`.

### 2. Execution Methods

**A: Using the Graphical User Interface (GUI)**
In the interface, you can view processing logs at any time, select input files and output directories, and choose whether to keep intermediate files generated during the process.

```bash
python run_gui.py
```

**B: Using the Command Line Interface (CLI)**
Provides a parameterized pipeline invocation:

```bash
python pipeline.py <input_file_path> [output_directory] [--max_size_mb 8] [--no_intermediate]

# Example 1: Process an FT-IR spectrum screenshot image and output to the output/ directory
python pipeline.py Demo/test_image.jpg ./output

# Example 2: Process an existing CSV data file directly
python pipeline.py Demo/7343-3.CSV ./output
```
