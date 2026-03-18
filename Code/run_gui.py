import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import sys
import os
import threading
import time
import traceback

try:
    from pipeline import run_pipeline
    PIPELINE_AVAILABLE = True
    IMPORT_ERROR = None
except ImportError as e:
    PIPELINE_AVAILABLE = False
    IMPORT_ERROR = str(e)

class RedirectText:
    def __init__(self, text_ctrl):
        self.output = text_ctrl
        self.output.configure(state='disabled')

    def write(self, string):
        try:
            self.output.configure(state='normal')
            self.output.insert(tk.END, string)
            self.output.see(tk.END)
            self.output.configure(state='disabled')
        except Exception:
            pass

    def flush(self):
        pass

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("红外光谱处理")
        self.root.geometry("700x600")

        tk.Label(root, text="红外光谱处理", font=("Microsoft YaHei", 16, "bold")).pack(pady=15)

        container = tk.Frame(root, padx=20)
        container.pack(fill=tk.X)

        # 输入文件
        self.frame_input = tk.Frame(container)
        self.frame_input.pack(pady=5, fill=tk.X)

        tk.Label(self.frame_input, text="输入文件 (图片/CSV):", width=18, anchor="w").pack(side=tk.LEFT)
        self.entry_input = tk.Entry(self.frame_input)
        self.entry_input.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        tk.Button(self.frame_input, text="浏览...", command=self.browse_input).pack(side=tk.LEFT)

        # 输出目录
        self.frame_output = tk.Frame(container)
        self.frame_output.pack(pady=5, fill=tk.X)

        tk.Label(self.frame_output, text="输出保存目录:", width=18, anchor="w").pack(side=tk.LEFT)
        self.entry_output = tk.Entry(self.frame_output)
        self.entry_output.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        tk.Button(self.frame_output, text="浏览...", command=self.browse_output).pack(side=tk.LEFT)

        # 选项区域
        self.frame_options = tk.Frame(container)
        self.frame_options.pack(pady=10, fill=tk.X)
        self.var_keep = tk.BooleanVar(value=True)
        tk.Checkbutton(self.frame_options, text="保留过程文件", variable=self.var_keep).pack(side=tk.LEFT)

        # 运行按钮
        self.btn_run = tk.Button(
            container,
            text="开始处理",
            command=self.start_thread, 
            bg="#007ACC",
            fg="white",
            font=("Microsoft YaHei", 12),
            cursor="hand2",
            padx=20,
            pady=5
        )
        self.btn_run.pack(pady=15)

        # 日志显示区域
        tk.Label(root, text="执行日志:", anchor="w").pack(fill=tk.X, padx=20)
        self.log_text = scrolledtext.ScrolledText(root, height=15, state='disabled', bg="#F0F0F0", font=("Consolas", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 20))

        # 重定向 stdout 和 stderr
        sys.stdout = RedirectText(self.log_text)
        sys.stderr = RedirectText(self.log_text)

        # 检查依赖
        if not PIPELINE_AVAILABLE:
            sys.stdout.write(f"❌ 严重错误: 导入处理核心模块失败。\n原因: {IMPORT_ERROR}\n\n请检查是否已安装所有依赖项。\n")
            self.btn_run.config(state=tk.DISABLED, bg="#AAAAAA")
            messagebox.showerror("环境错误", f"无法加载处理模块:\n{IMPORT_ERROR}\n\n请先安装缺失的库。")

    def browse_input(self):
        filename = filedialog.askopenfilename(
            title="选择输入文件",
            filetypes=[("支持的文件", "*.jpg;*.jpeg;*.png;*.csv"), ("图像文件", "*.jpg;*.jpeg;*.png"), ("CSV 数据", "*.csv"), ("所有文件", "*.*")]
        )
        if filename:
            self.entry_input.delete(0, tk.END)
            self.entry_input.insert(0, filename)
            # 如果输出目录为空，默认设置为输入文件所在目录
            if not self.entry_output.get():
                self.entry_output.delete(0, tk.END)
                self.entry_output.insert(0, os.path.dirname(filename))

    def browse_output(self):
        dirname = filedialog.askdirectory(title="选择输出目录")
        if dirname:
            self.entry_output.delete(0, tk.END)
            self.entry_output.insert(0, dirname)

    def start_thread(self):
        if not PIPELINE_AVAILABLE:
            messagebox.showerror("错误", f"环境配置不完整，无法运行。\n{IMPORT_ERROR}")
            return

        input_path = self.entry_input.get().strip()
        output_base = self.entry_output.get().strip()

        if not input_path or not os.path.exists(input_path):
            messagebox.showerror("路径错误", "请选择有效的输入文件！")
            return
        
        if not output_base:
            messagebox.showerror("路径错误", "请选择输出目录！")
            return

        # 锁定按钮
        self.btn_run.config(state=tk.DISABLED, text="正在运行...", bg="#AAAAAA")
        
        # 清空旧日志
        self.log_text.configure(state='normal')
        self.log_text.delete(1.0, tk.END)
        self.log_text.configure(state='disabled')
        
        # 启动后台线程
        thread = threading.Thread(target=self.run_process, args=(input_path, output_base))
        thread.daemon = True
        thread.start()

    def run_process(self, input_path, output_base):
        final_output_dir = None
        try:
            timestamp_dir = time.strftime("%Y%m%d_%H%M%S")
            final_output_dir = os.path.join(output_base, timestamp_dir)
            
            print(f"--- Task Started ---")
            print(f"Current time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"Input: {input_path}")
            print(f"Output will be saved in: {final_output_dir}")
            print("-" * 30)
            
            # 调用核心函数
            count = run_pipeline( # type: ignore
                image_path=input_path,
                output_dir=final_output_dir,
                keep_intermediate=self.var_keep.get()
            )
            
            print("-" * 30)
            print(f"✅ Processing completed successfully!")
            
            # 自动打开文件夹 (Windows)
            if final_output_dir and os.path.exists(final_output_dir):
                self.root.after(0, lambda: messagebox.showinfo("完成", "执行成功！\n点击确定打开输出文件夹。"))
                os.startfile(final_output_dir)

        except Exception as e:
            print(f"\n❌ A fatal error occurred: {str(e)}")
            traceback.print_exc()
            self.root.after(0, lambda: messagebox.showerror("执行出错", f"处理过程中发生错误:\n{str(e)}"))
        
        finally:
            # 恢复按钮状态
            self.root.after(0, self.reset_ui)

    def reset_ui(self):
        self.btn_run.config(state=tk.NORMAL, text="开始处理", bg="#007ACC")

if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()
