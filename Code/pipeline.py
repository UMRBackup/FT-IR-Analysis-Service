import argparse
import csv
import os
import shutil
import time
from image_processing.curve_dye import dye_curve_blue
from image_processing.extract import extract_to_csv
from image_processing.pretreat import preprocess_image
from software_agent.ir_rpa import OmnicRpa
from report_generator.generator import generate_report


def _init_pipeline_paths(image_path: str, output_dir: str, reset_work_dir: bool = True) -> dict[str, str]:
    image_path = os.path.abspath(image_path)
    output_dir = os.path.abspath(output_dir)

    os.makedirs(output_dir, exist_ok=True)

    if not os.path.isfile(image_path):
        raise FileNotFoundError(f"Input file does not exist: {image_path}")

    input_stem = os.path.splitext(os.path.basename(image_path))[0]
    input_ext = os.path.splitext(image_path)[1].lower()
    output_csv = os.path.join(output_dir, f"{input_stem}.csv")
    final_pdf = os.path.join(output_dir, f"{input_stem}.pdf")
    pipeline_root = os.path.join(output_dir, "work_dir")
    omnic_pdf = os.path.join(pipeline_root, f"{input_stem}_omnic.pdf")

    if reset_work_dir and os.path.exists(pipeline_root):
        shutil.rmtree(pipeline_root, ignore_errors=True)
    os.makedirs(pipeline_root, exist_ok=True)

    return {
        "image_path": image_path,
        "output_dir": output_dir,
        "input_stem": input_stem,
        "input_ext": input_ext,
        "output_csv": output_csv,
        "final_pdf": final_pdf,
        "pipeline_root": pipeline_root,
        "omnic_pdf": omnic_pdf,
    }


def run_preprocess_stage(
    image_path: str,
    output_dir: str,
    max_size_mb: int = 6,
) -> dict[str, str | int]:
    paths = _init_pipeline_paths(image_path=image_path, output_dir=output_dir, reset_work_dir=True)

    points_count = 0
    input_ext = paths["input_ext"]
    output_csv = paths["output_csv"]
    pipeline_root = paths["pipeline_root"]

    if input_ext == ".csv":
        print("[1/3] Checking input data file format...")
        try:
            with open(paths["image_path"], "r", newline="", encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                rows = [row for row in reader if row]

            if len(rows) < 800:
                raise ValueError(f"CSV line count must be at least 800 (current: {len(rows)})")

            for i, row in enumerate(rows):
                if len(row) != 2:
                    raise ValueError(f"Row {i + 1} does not meet requirement (current: {len(row)} columns)")

            points_count = len(rows)
            shutil.copy2(paths["image_path"], output_csv)
            print(f"[1/3] Validation passed.")
        except Exception as e:
            raise ValueError(f"Invalid file: {e}")
    else:
        source_copy_path = os.path.join(paths["output_dir"], os.path.basename(paths["image_path"]))
        shutil.copy2(paths["image_path"], source_copy_path)

        input_stage_dir = os.path.join(pipeline_root, "stage0_input")
        pretreated_stage_dir = os.path.join(pipeline_root, "stage1_pretreated")
        dye_stage_dir = os.path.join(pipeline_root, "stage2_dyed")
        debug_dir = os.path.join(pipeline_root, "debug")

        os.makedirs(input_stage_dir, exist_ok=True)
        os.makedirs(pretreated_stage_dir, exist_ok=True)
        os.makedirs(dye_stage_dir, exist_ok=True)
        os.makedirs(debug_dir, exist_ok=True)

        copied_input_path = os.path.join(input_stage_dir, os.path.basename(paths["image_path"]))
        shutil.copy2(paths["image_path"], copied_input_path)

        print("[1/3] Starting image processing...")
        pretreated_output_path = os.path.join(pretreated_stage_dir, "pretreated.jpg")
        pretreated_image_path = preprocess_image(
            copied_input_path, pretreated_output_path, max_size_mb=max_size_mb
        )

        dyed_image_path = os.path.join(dye_stage_dir, "dyed_result.jpg")
        dye_curve_blue(pretreated_image_path, dyed_image_path)

        points = extract_to_csv(dyed_image_path, output_csv, debug_dir=debug_dir)
        points_count = len(points)
        print(f"[1/3] Image processing completed: {points_count} points extracted.")

    return {
        "points_count": points_count,
        "input_ext": input_ext,
        "output_csv": output_csv,
        "pipeline_root": pipeline_root,
        "work_dir": pipeline_root,
        "omnic_pdf": paths["omnic_pdf"],
        "final_pdf": paths["final_pdf"],
    }


def run_rpa_stage(
    output_csv: str,
    omnic_pdf: str,
    omnic_exe: str = r"C:\Program Files (x86)\Omnic\omnic32.exe",
) -> str:
    output_csv = os.path.abspath(output_csv)
    omnic_pdf = os.path.abspath(omnic_pdf)
    os.makedirs(os.path.dirname(omnic_pdf), exist_ok=True)

    print("[2/3] Starting RPA retrieval...")
    omnic_workflow = OmnicRpa(
        omnic_exe=omnic_exe,
        csv_path=output_csv,
        pdf_path=omnic_pdf,
    )
    omnic_workflow.run()
    print(f"[2/3] Retrieval completed.")
    return omnic_pdf


def run_postprocess_stage(
    output_csv: str,
    omnic_pdf: str,
    final_pdf: str,
) -> str:
    output_csv = os.path.abspath(output_csv)
    omnic_pdf = os.path.abspath(omnic_pdf)
    final_pdf = os.path.abspath(final_pdf)

    print("[3/3] Generating diagnostic report...")
    generate_report(csv_path=output_csv, pdf_path=omnic_pdf, output_path=final_pdf)
    print(f"[3/3] Report generated! Saved to -> {final_pdf}")
    return final_pdf

def run_pipeline(
    image_path: str,
    output_dir: str,
    max_size_mb: int = 6,
    keep_intermediate: bool = True,
    omnic_exe: str = r"C:\Program Files (x86)\Omnic\omnic32.exe",
) -> int:
    preprocess_result = run_preprocess_stage(
        image_path=image_path,
        output_dir=output_dir,
        max_size_mb=max_size_mb,
    )

    output_csv = str(preprocess_result["output_csv"])
    omnic_pdf = str(preprocess_result["omnic_pdf"])
    final_pdf = str(preprocess_result["final_pdf"])
    pipeline_root = str(preprocess_result["pipeline_root"])

    run_rpa_stage(output_csv=output_csv, omnic_pdf=omnic_pdf, omnic_exe=omnic_exe)
    run_postprocess_stage(output_csv=output_csv, omnic_pdf=omnic_pdf, final_pdf=final_pdf)

    if pipeline_root:
        if not keep_intermediate:
            shutil.rmtree(pipeline_root, ignore_errors=True)
        else:
            print(f"Intermediate files retained at: {pipeline_root}")

    return int(preprocess_result["points_count"])

def main() -> None:
    parser = argparse.ArgumentParser(description="红外光谱处理流水线：支持 图片(预处理->提取) 或 CSV(直接检索)")
    parser.add_argument("image", help="输入文件路径 (图片或数据)")
    parser.add_argument(
        "output",
        nargs="?",
        default=None,
        help="输出根目录（默认：输入文件同目录），实际输出目录为 <输出根目录>/<时间戳>",
    )
    parser.add_argument("--max_size_mb", type=int, default=8, help="预处理最大文件大小（MB）")
    parser.add_argument(
        "--no_intermediate",
        dest="keep_intermediate",
        action="store_false",
        help="不保留中间产物目录",
    )
    parser.set_defaults(keep_intermediate=True)

    args = parser.parse_args()

    input_abs_path = os.path.abspath(args.image)
    timestamp_dir = time.strftime("%Y%m%d_%H%M%S")

    base_output_dir = (
        os.path.abspath(args.output)
        if args.output
        else os.path.dirname(input_abs_path)
    )
    output_dir = os.path.join(base_output_dir, timestamp_dir)

    start = time.time()
    count = run_pipeline(
        image_path=args.image,
        output_dir=output_dir,
        max_size_mb=args.max_size_mb,
        keep_intermediate=args.keep_intermediate,
    )
    elapsed = time.time() - start
    print(f"Execution completed in {elapsed:.2f} seconds.")

if __name__ == "__main__":
    main()