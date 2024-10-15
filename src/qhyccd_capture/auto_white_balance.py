from PyQt5.QtWidgets import QDialog
from PyQt5.QtCore import pyqtSignal, QTimer  # 导入信号和QTimer
from .language import translations
from .control_id import CONTROL_ID
import warnings

class AutoWhiteBalanceDialog(QDialog):
    balance_complete_signal = pyqtSignal(float, float, float)  # 新增信号，通知自动白平衡结束
    values_signal = pyqtSignal(float, float, float)  # 新增信号，用于发送三个值

    def __init__(self, qhyccddll, camera, language, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.language = language
        self.qhyccddll = qhyccddll
        self.camera = camera
        self.timer = QTimer(self)  # 创建一个定时器
        self.timer.timeout.connect(self.fetch_data)  # 将定时器超时信号连接到fetch_data方法

    def start(self):
        ret = self.qhyccddll.GetQHYCCDParam(self.camera, CONTROL_ID.CONTROL_AUTOWHITEBALANCE.value)
        if ret == 0:
            ret = self.qhyccddll.SetQHYCCDParam(self.camera, CONTROL_ID.CONTROL_AUTOWHITEBALANCE.value, 1.0)
            if ret != 0:
                warnings.warn(f"{translations[self.language]['debug']['set_qhyccd_auto_white_balance_failed']}: {ret}")
                self.parent.append_text(f"{translations[self.language]['debug']['set_qhyccd_auto_white_balance_failed']}: {ret}")
                return
            self.parent.append_text(f"{translations[self.language]['auto_white_balance']['set_qhyccd_auto_white_balance_success']}: {ret}")
            self.timer.start(1000)  # 每秒触发一次
        else:
            self.parent.append_text(f"{translations[self.language]['auto_white_balance']['auto_white_balance_already_started']}: {ret}")
            
    def fetch_data(self):
        wb_red = self.qhyccddll.GetQHYCCDParam(self.camera, CONTROL_ID.CONTROL_WBR.value)
        wb_green = self.qhyccddll.GetQHYCCDParam(self.camera, CONTROL_ID.CONTROL_WBG.value)
        wb_blue = self.qhyccddll.GetQHYCCDParam(self.camera, CONTROL_ID.CONTROL_WBB.value)
        self.values_signal.emit(wb_red, wb_green, wb_blue)  # 发送获取的值
        if self.qhyccddll.GetQHYCCDParam(self.camera, CONTROL_ID.CONTROL_AUTOWHITEBALANCE.value) == 0:
            self.timer.stop()
            self.balance_complete_signal.emit(wb_red, wb_green, wb_blue)

    def stop(self):
        self.timer.stop()
        ret = self.qhyccddll.SetQHYCCDParam(self.camera, CONTROL_ID.CONTROL_AUTOWHITEBALANCE.value, 0.0)
        if ret != 0:
            warnings.warn(f"{translations[self.language]['debug']['set_qhyccd_auto_white_balance_failed']}: {ret}")
            self.parent.append_text(f"{translations[self.language]['debug']['set_qhyccd_auto_white_balance_failed']}: {ret}")
            return
        self.parent.append_text(f"{translations[self.language]['qhyccd_capture']['set_qhyccd_auto_white_balance_success']}: {ret}")
