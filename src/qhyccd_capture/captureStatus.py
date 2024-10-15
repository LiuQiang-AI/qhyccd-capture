from PyQt5.QtCore import QThread, pyqtSignal, QMutex
import time
from .language import translations
class CaptureStatusThread(QThread):
    update_status = pyqtSignal(str)
    end_capture = pyqtSignal()

    def __init__(self, qhyccddll, camhandle,language):
        super().__init__()
        self.language = language
        self.qhyccddll = qhyccddll
        self.camhandle = camhandle
        self.running = True
        self.paused = False
        self.mutex = QMutex()  # 创建互斥锁
        self.time = 0

    def run(self):
        status_texts = [translations[self.language]["captureStatus"]["capturing"], translations[self.language]["captureStatus"]["capturing_1"], translations[self.language]["captureStatus"]["capturing_2"]]
        index = 0
        paused_signal_sent = False  # 添加标志位
        while self.running:
            self.mutex.lock()  # 锁定
            if not self.paused:
                if paused_signal_sent:  # 取消暂停后，重置标志位
                    paused_signal_sent = False
                # 计算耗时
                elapsed_time = self.qhyccddll.GetQHYCCDExposureRemaining(self.camhandle)
                if elapsed_time == -1:
                    elapsed_time = 0
                # 发送状态文本和耗时
                self.update_status.emit(f"{status_texts[index]} {translations[self.language]['captureStatus']['exposure']}{elapsed_time}")
                index = (index + 1) % len(status_texts)
            else:
                if not paused_signal_sent:  # 仅在第一次暂停时发送信号
                    self.end_capture.emit()
                    paused_signal_sent = True  # 设置标志位，避免重复发送
            self.mutex.unlock()  # 解锁
            self.msleep(300)

    def pause_capture(self):
        self.mutex.lock()  # 锁定
        self.paused = True
        self.mutex.unlock()  # 解锁

    def resume_capture(self):
        self.mutex.lock()  # 锁定
        self.paused = False
        self.time = time.time()  # 记录恢复时的时间
        self.mutex.unlock()  # 解锁

    def stop(self):
        self.running = False
        self.wait()