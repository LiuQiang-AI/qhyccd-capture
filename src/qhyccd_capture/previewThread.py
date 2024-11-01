from PyQt5.QtCore import QThread, pyqtSignal
import numpy as np
import ctypes
from ctypes import *
import time
from multiprocessing import Array
from threading import Lock
import warnings
from .language import translations

class PreviewThread(QThread):
    frame_captured = pyqtSignal(float)  # 定义一个信号
    request_stop = pyqtSignal()  # 添加一个信号用于请求停止线程
    request_start = pyqtSignal()  # 添加一个信号用于请求启动线程

    def __init__(self, camhandle, qhyccddll, image_w, image_h, camera_bit, is_color_camera, Debayer_mode, viewer, shared_image_data, language):
        super().__init__()
        self.camhandle = camhandle
        self.qhyccddll = qhyccddll
        self.image_w = image_w
        self.image_h = image_h
        self.camera_bit = camera_bit
        self.is_color_camera = is_color_camera
        self.Debayer_mode = Debayer_mode
        self.image_c = 3 if Debayer_mode else 1
        self.viewer = viewer
        self.running = False
        self.frame_times = []
        self.shared_image_data = shared_image_data
        self.lock = Lock()
        self.language = language
        self.paused = False  # 新增一个属性来控制是否暂停

        self.request_stop.connect(self.handle_stop)
        self.request_start.connect(self.handle_start)  # 连接启动信号到槽

    def run(self):
        while self.running:
            if not self.paused:  # 只有在不暂停的情况下才捕获帧
                tip = self.capture_frame()
                if tip:
                    self.frame_times.append(time.time())
                    if len(self.frame_times) > 300:
                        self.frame_times.pop(0)
                    if len(self.frame_times) > 1:
                        fps = len(self.frame_times) / (self.frame_times[-1] - self.frame_times[0] + 0.0001)
                    else:
                        fps = 0.0
                    self.frame_captured.emit(fps)
            else:
                time.sleep(0.1)
                
    def pause(self,pause):
        if pause:
            ret = self.qhyccddll.StopQHYCCDLive(self.camhandle)
            if ret != 0:
                warnings.warn(f"{translations[self.language]['debug']['stop_qhyccd_live_failed']}: {ret}")
                self.append_text(f"{translations[self.language]['debug']['stop_qhyccd_live_failed']}: {ret}")
                return
            self.update_fps()
            self.paused = pause
        else:
            ret = self.qhyccddll.BeginQHYCCDLive(self.camhandle)
            if ret != 0:
                warnings.warn(f"{translations[self.language]['debug']['begin_qhyccd_live_failed']}: {ret}")
                self.append_text(f"{translations[self.language]['debug']['begin_qhyccd_live_failed']}: {ret}")
                return
            self.paused = pause

    def update_fps(self):
        self.frame_times.clear()

    def capture_frame(self):
        w = ctypes.c_uint32()
        h = ctypes.c_uint32()
        b = ctypes.c_uint32()
        c = ctypes.c_uint32()
        with self.lock:  # 使用锁
            # 创建临时缓冲区
            temp_buffer = (c_ubyte * (self.image_w * self.image_h * self.image_c*(self.camera_bit//8)))()
            ret = self.qhyccddll.GetQHYCCDLiveFrame(self.camhandle, byref(w), byref(h), byref(b), byref(c), temp_buffer)
            if ret == -1:
                # time.sleep(0.001)
                return 0
            if c.value != self.image_c:
                return 0
            img_size = w.value * h.value * c.value * (b.value//8)
            # 添加代码以将BGR转换为RGB
            if c.value == 3:  # 确保是彩色图像
                # 假设图像数据是连续的，每个像素3个字节
                
                img = np.ctypeslib.as_array(temp_buffer, shape=(img_size,))
                img = img.reshape((h.value, w.value, c.value))
                img = img[:, :, ::-1]  # 将BGR转换为RGB
                # 将转换后的图像数据复制回共享内存
                np.copyto(np.ctypeslib.as_array(cast(addressof(self.shared_image_data), POINTER(c_ubyte)), shape=(img_size,)), img.flatten())
                return 1
            else:
                img = np.ctypeslib.as_array(temp_buffer, shape=(img_size,))
                if self.camera_bit == 16:
                    # 重新解释数组为16位整数
                    img = img.view(np.uint16).reshape((h.value, w.value))
                    np.copyto(np.ctypeslib.as_array(cast(addressof(self.shared_image_data), POINTER(c_ushort)), shape=(img_size//2,)), img.flatten())
                else:
                    img = img.reshape((h.value, w.value))
                    # 将转换后的图像数据复制回共享内存
                    np.copyto(np.ctypeslib.as_array(cast(addressof(self.shared_image_data), POINTER(c_ubyte)), shape=(img_size,)), img.flatten())
                return 1
        
    def handle_start(self):
        """处理启动请求的槽函数"""
        ret = self.qhyccddll.BeginQHYCCDLive(self.camhandle)
        if ret != 0:
            warnings.warn(f"{translations[self.language]['debug']['begin_qhyccd_live_failed']}: {ret}")
            self.append_text(f"{translations[self.language]['debug']['begin_qhyccd_live_failed']}: {ret}")
        else:
            self.running = True
            self.start()

    def start_thread(self):
        """外部调用启动线程的方法"""
        self.request_start.emit()  # 发射信号，请求启动线程


    def handle_stop(self):
        """处理停止请求的槽函数"""
        ret = self.qhyccddll.StopQHYCCDLive(self.camhandle)
        if ret != 0:
            warnings.warn(f"{translations[self.language]['debug']['stop_qhyccd_live_failed']}: {ret}")
            self.append_text(f"{translations[self.language]['debug']['stop_qhyccd_live_failed']}: {ret}")
            return
        self.running = False
        self.update_fps()
        self.quit()

    def stop(self):
        """外部调用停止线程的方法"""
        self.request_stop.emit()  # 发射信号，请求停止线程

    def update_image_parameters(self, image_w, image_h, camera_bit, Debayer_mode,shared_image_data):
        """更新图像参数的方法"""
        with self.lock:  # 使用锁来确保线程安全
            self.image_w = image_w
            self.image_h = image_h
            self.camera_bit = camera_bit
            self.Debayer_mode = Debayer_mode
            self.image_c = 3 if Debayer_mode else 1  # 更新通道数
            self.shared_image_data = shared_image_data