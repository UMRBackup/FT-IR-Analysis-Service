from __future__ import annotations
import argparse
import csv
import time
import re
from dataclasses import dataclass
from pathlib import Path
import win32api
import win32con
from pywinauto import Application, Desktop, mouse
from pywinauto.keyboard import send_keys

@dataclass(frozen=True)
class Coordinates:
	pick_start: tuple[int, int] = (275, 253)
	drag_from: tuple[int, int] = (512, 280)
	drag_to: tuple[int, int] = (512, 400)
	shift_click: tuple[int, int] = (290, 405)
	button_a: tuple[int, int] = (620, 285)
	button_b: tuple[int, int] = (880, 665)
	print_dialog_1: tuple[int, int] = (1595, 1095)
	print_dialog_2: tuple[int, int] = (1690, 1095)
	clear_focus_click: tuple[int, int] = (1910, 40)

class OmnicRpa:
	def __init__(
		self,
		omnic_exe: str,
		csv_path: str,
		pdf_path: str,
		coord: Coordinates | None = None,
		default_timeout: float = 60.0,
		short_delay: float = 0.3,
	) -> None:
		self.omnic_exe = omnic_exe
		self.csv_path = str(Path(csv_path).expanduser().resolve())
		self.pdf_path = str(Path(pdf_path).expanduser().resolve())
		self.coord = coord or Coordinates()
		self.default_timeout = default_timeout
		self.short_delay = short_delay
		self.app: Application | None = None

	def run(self) -> None:
		self._start_app()
		self._maximize_main_window()
		self._open_and_run_search()
		self._configure_search_region()
		self._confirm_search()
		self._sleep(2.5)
		self._print_to_pdf()
		self._clear_application_content()
		self._close_result_window()

	def _start_app(self) -> None:
		self.app = Application(backend="win32").start(self.omnic_exe, timeout=30)
		self._sleep(2.0)

	def _wait_window(self, title: str, timeout: float | None = None):
		timeout = timeout if timeout is not None else self.default_timeout
		wnd = Desktop(backend="win32").window(title_re=title if title.startswith("^") else f"^{re.escape(title)}$")
		wnd.wait("exists ready visible", timeout=timeout)
		try:
			wnd.set_focus()
		except Exception:
			pass
		return wnd

	def _send_keys_to_window(self, title: str, keys: str, timeout: float | None = None) -> None:
		self._wait_window(title, timeout=timeout)
		send_keys(keys, pause=0.05, with_spaces=True)
		self._sleep(self.short_delay)

	def _click(self, pos: tuple[int, int]) -> None:
		mouse.click(button="left", coords=pos)
		self._sleep(self.short_delay)

	def _drag(self, begin: tuple[int, int], end: tuple[int, int]) -> None:
		mouse.move(coords=begin)
		self._sleep(0.1)
		mouse.press(button="left", coords=begin)
		self._sleep(0.1)
		mouse.move(coords=end)
		self._sleep(0.1)
		mouse.release(button="left", coords=end)
		self._sleep(self.short_delay)

	def _maximize_main_window(self) -> None:
		wnd = self._wait_window(r"^OMNIC - \[.*\]$", timeout=120)
		try:
			wnd.restore()
		except Exception:
			pass
		wnd.maximize()
		self._sleep(0.5)

	def _get_csv_y_max(self) -> float:
		max_val = -float('inf')
		try:
			# 使用 utf-8-sig
			with open(self.csv_path, 'r', newline='', encoding='utf-8-sig') as f:
				reader = csv.reader(f)
				for row in reader:
					# 第二列是 Y 值
					if len(row) >= 2:
						try:
							val = float(row[1])
							if val > max_val:
								max_val = val
						except ValueError:
							continue
		except Exception:
			# 读取失败时默认保持原有逻辑
			return 100.0

		if max_val == -float('inf'):
			return 100.0

		return max_val

	def _open_and_run_search(self) -> None:
		self._send_keys_to_window(r"^OMNIC - \[.*\]$", "^o")
		self._send_keys_to_window("打开", self.csv_path, timeout=20)
		self._send_keys_to_window("打开", "{ENTER}", timeout=20)

		# 获取 Y 最大值进行判断
		max_y = self._get_csv_y_max()

		if not (0 <= max_y <= 1):
			self._send_keys_to_window("参数", "{TAB 2}", timeout=20)
			self._send_keys_to_window("参数", "{UP}", timeout=20)

		self._send_keys_to_window("参数", "{ENTER}", timeout=20)

		self._send_keys_to_window(r"^OMNIC - \[.*\]$", "%a", timeout=20)
		self._send_keys_to_window(r"^OMNIC - \[.*\]$", "y", timeout=20)

	def _configure_search_region(self) -> None:
		mouse.move(coords=self.coord.pick_start)
		self._click(self.coord.pick_start)
		self._drag(self.coord.drag_from, self.coord.drag_to)
		mouse.move(coords=self.coord.shift_click)
		self._sleep(0.1)

		self._wait_window("检索设置")
		self._shift_click(self.coord.shift_click)

		mouse.move(coords=self.coord.button_a)
		self._click(self.coord.button_a)
		mouse.move(coords=self.coord.button_b)
		self._click(self.coord.button_b)

	def _confirm_search(self) -> None:
		self._send_keys_to_window(r"^OMNIC - \[.*\]$", "^l", timeout=60)

	def _print_to_pdf(self) -> None:
		mouse.move(coords=self.coord.print_dialog_1)
		self._click(self.coord.print_dialog_1)
		mouse.move(coords=self.coord.print_dialog_2)
		self._click(self.coord.print_dialog_2)

		self._send_keys_to_window("打印", "{ENTER}", timeout=20)
		self._send_keys_to_window("将打印输出另存为", self.pdf_path, timeout=20)
		self._send_keys_to_window("将打印输出另存为", "{ENTER}", timeout=20)

	def _clear_application_content(self) -> None:
		mouse.move(coords=self.coord.clear_focus_click)
		self._click(self.coord.clear_focus_click)

		self._send_keys_to_window(r"^OMNIC - \[.*\]$", "^{DELETE}", timeout=20)

	def _close_result_window(self) -> None:
		target_wnd = None

		try:
			target_wnd = self._wait_window(r"^OMNIC - \[Window1\]$", timeout=8)
		except Exception:
			pass

		if target_wnd is None:
			for w in Desktop(backend="win32").windows():
				try:
					t = (w.window_text() or "").strip()
					if t.startswith("OMNIC - [") and t.endswith("]"):
						target_wnd = w
						break
				except Exception:
					continue

		if target_wnd is not None:
			try:
				target_wnd.set_focus()
			except Exception:
				pass
			try:
				target_wnd.close()
				target_wnd.wait_not("exists", timeout=8)
				return
			except Exception:
				pass

		send_keys("%{F4}", pause=0.05)
		self._sleep(0.5)

	@staticmethod
	def _sleep(seconds: float) -> None:
		time.sleep(seconds)

	def _shift_click(self, pos: tuple[int, int]) -> None:
		win32api.keybd_event(win32con.VK_SHIFT, 0, 0, 0)
		try:
			self._click(pos)
		finally:
			win32api.keybd_event(win32con.VK_SHIFT, 0, win32con.KEYEVENTF_KEYUP, 0)  # key up
		self._sleep(0.1)

def build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(description="使用 pywinauto 复现 taskt 的 OMNIC 自动化流程")
	parser.add_argument(
		"csv",
		help="待打开的 CSV 文件路径",
	)
	parser.add_argument(
		"pdf",
		help="导出的 PDF 文件路径",
	)
	parser.add_argument(
		"--omnic-exe",
		default=r"C:\Program Files (x86)\Omnic\omnic32.exe",
		help="OMNIC 可执行文件路径",
	)
	parser.add_argument(
		"--delay",
		type=float,
		default=0.3,
		help="动作之间的短暂停顿（秒）",
	)
	return parser

def main() -> None:
	args = build_parser().parse_args()
	workflow = OmnicRpa(
		omnic_exe=args.omnic_exe,
		csv_path=args.csv,
		pdf_path=args.pdf,
		short_delay=args.delay,
	)
	workflow.run()

if __name__ == "__main__":
	main()
