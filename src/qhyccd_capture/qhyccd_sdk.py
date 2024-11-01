from PyQt5.QtCore import QThread, pyqtSignal
import ctypes
from ctypes import *

# 相机状态字典，包含状态代码和描述
CAMERA_STATUS = {
    'INITIALIZATION_SUCCESS': {
        'code': 0,
        'description': '相机初始化成功.'
    },
    'INITIALIZATION_FAILED': {
        'code': 1,
        'description': '相机初始化失败.'
    },
    'LIVE_MODE_STARTED': {
        'code': 2,
        'description': '相机进入实时模式.'
    },
    'LIVE_MODE_STOPPED': {
        'code': 3,
        'description': '相机退出实时模式.'
    }
}

class CameraThread(QThread):
    initialize_camera_signal = pyqtSignal()  # 初始化相机的信号
    status_signal = pyqtSignal(int)  # 状态更新信号
    stop_thread_signal = pyqtSignal()  # 停止线程的信号
    update_live_mode_signal = pyqtSignal(bool)  # 更新参数的信号

    def __init__(self, camhandle, qhyccddll):
        super().__init__()
        self.camhandle = camhandle
        self.qhyccddll = qhyccddll
        self.initialize_camera_signal.connect(self.initialize_camera)
        self.stop_thread_signal.connect(self.stop_thread)
        self.update_live_mode_signal.connect(self.update_live_mode)
    def run(self):
        # 启动事件循环，等待信号
        self.exec_()

    def initialize_camera(self):
        # 初始化QHYCCD资源
        ret = self.qhyccddll.InitQHYCCDResource()
        if ret != 0:
            self.status_signal.emit(CAMERA_STATUS['INITIALIZATION_FAILED']['code'])
        else:
            self.status_signal.emit(CAMERA_STATUS['INITIALIZATION_SUCCESS']['code'])

    def update_live_mode(self, live_mode):
        if live_mode:
            self.qhyccddll.BeginQHYCCDLive(self.camhandle)
            self.status_signal.emit(CAMERA_STATUS['LIVE_MODE_STARTED']['code'])
        else:
            self.qhyccddll.StopQHYCCDLive(self.camhandle)
            self.status_signal.emit(CAMERA_STATUS['LIVE_MODE_STOPPED']['code'])
            
    def stop_thread(self):
        # 退出事件循环，结束线程
        self.quit()

# 使用示例
# 在主界面或控制逻辑中创建和管理 CameraThread 实例
# camera_thread = CameraThread(camhandle, qhyccddll)
# camera_thread.start()
# camera_thread.initialize_camera_signal.emit()
# camera_thread.stop_thread_signal.emit()

