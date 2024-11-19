from PyQt5.QtWidgets import QDialog
from PyQt5.QtCore import pyqtSignal, QTimer  # 导入信号和QTimer
from .language import translations
from .control_id import CONTROL_ID
import warnings

class AutoWhiteBalanceDialog(QDialog):
    def __init__(self, camera,sdk_input_queue, language):
        super().__init__()
        self.language = language
        self.camera = camera
        self.sdk_input_queue = sdk_input_queue
        self.timer = QTimer(self)  # 创建一个定时器
        self.timer.timeout.connect(self.fetch_data)  # 将定时器超时信号连接到fetch_data方法

    def start(self):
        self.sdk_input_queue.put({"order":"set_auto_white_balance","data":1.0})
    
    def start_auto_white_balance_success(self,data):
        if data == 1.0:
            self.timer.start(1000)  # 每秒触发一次
            
    def fetch_data(self):
        self.sdk_input_queue.put({"order":"get_auto_white_balance_values","data":""})

    def stop(self):
        self.timer.stop()
        self.sdk_input_queue.put({"order":"set_auto_white_balance","data":0.0})
