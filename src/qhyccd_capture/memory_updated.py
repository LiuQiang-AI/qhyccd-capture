import psutil  # 确保安装 psutil 库以获取内存信息
from PyQt5.QtCore import QThread, pyqtSignal

# 创建一个线程类来获取内存信息
class MemoryMonitorThread(QThread):
    memory_updated = pyqtSignal(float)  # 定义信号以传递内存信息

    def run(self):
        while True:
            try:
                # 获取内存信息
                memory_info = psutil.virtual_memory()
                used_memory = memory_info.percent  # 已用内存
                self.memory_updated.emit(used_memory)  # 发射信号
            except Exception as e:
                print(f"Error retrieving memory info: {e}")
                used_memory = 0
            self.sleep(1)  # 每秒更新一次