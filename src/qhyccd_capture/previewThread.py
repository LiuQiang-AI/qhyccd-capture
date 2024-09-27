from PyQt5.QtCore import QThread, pyqtSignal
import numpy as np
import ctypes
from ctypes import *
import time
from multiprocessing import Array
from threading import Lock

class PreviewThread(QThread):
    frame_captured = pyqtSignal(float)  # 定义一个信号

    def __init__(self, camhandle, qhyccddll, image_w, image_h, camera_bit, is_color_camera, Debayer_mode, viewer,shared_image_data):
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
        self.running = True
        self.frame_times = []
        self.shared_image_data = shared_image_data
        self.lock = Lock()  # 初始化锁

    def run(self):
        while self.running:
            tip = self.capture_frame()
            if tip :
                self.frame_times.append(time.time())
                if len(self.frame_times) > 300:
                    self.frame_times.pop(0)
                if len(self.frame_times) > 1:
                    fps = len(self.frame_times) / (self.frame_times[-1] - self.frame_times[0])
                else:
                    fps = 0.0
                self.frame_captured.emit(fps)

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
                time.sleep(0.001)
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
        

    def stop(self):
        self.running = False
        self.wait()