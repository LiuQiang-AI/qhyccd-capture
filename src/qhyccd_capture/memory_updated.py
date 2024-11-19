import psutil  # 确保安装 psutil 库以获取内存信息
from PyQt5.QtCore import QThread, pyqtSignal, QTimer  # 导入 QTimer

# 创建一个线程类来获取内存信息
class MemoryMonitorThread(QThread):
    # 定义信号，参数类型为 float
    memory_updated = pyqtSignal(float)

    def __init__(self):
        super().__init__()
        self.is_running = True

    def run(self):
        while self.is_running:
            try:
                # 获取内存信息
                memory_info = psutil.virtual_memory()
                used_memory = memory_info.percent  # 已用内存
                self.memory_updated.emit(float(used_memory))  # 发射信号
            except Exception as e:
                self.stop()
            self.sleep(1)  # 每秒更新一次
    def stop(self):
        self.is_running = False
        self.terminate()
