from PyQt5.QtCore import QThread, pyqtSignal
import time

class AcceptSDKData(QThread):
    data_signal = pyqtSignal(dict)  # 定义信号，发送字典数据

    def __init__(self, sdk_output_queue):
        super().__init__()
        self.sdk_output_queue = sdk_output_queue
        self.is_running = True

    def run(self):
        while self.is_running:
            if not self.sdk_output_queue.empty():
                result = self.sdk_output_queue.get()  # 从输出队列获取数据
                self.data_signal.emit(result)  # 发送信号
            else:
                time.sleep(0.1)  # 短暂休眠以减少CPU占用

    def stop(self):
        self.is_running = False

