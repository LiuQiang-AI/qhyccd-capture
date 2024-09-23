from PyQt5.QtCore import QThread, pyqtSignal
import numpy as np
import ctypes
from ctypes import *
import time

class PreviewThread(QThread):
    frame_captured = pyqtSignal(np.ndarray, float)  # 定义一个信号

    def __init__(self, camhandle, qhyccddll, image_w, image_h, camera_bit, is_color_camera, bayer_conversion, viewer):
        super().__init__()
        self.camhandle = camhandle
        self.qhyccddll = qhyccddll
        self.image_w = image_w
        self.image_h = image_h
        self.camera_bit = camera_bit
        self.is_color_camera = is_color_camera
        self.bayer_conversion = bayer_conversion
        self.viewer = viewer
        self.running = True
        self.frame_interval = 1 / 30  # 30 FPS
        self.frame_times = []

    def run(self):
        while self.running:
            imgdata_np = self.capture_frame()
            if imgdata_np is not None:
            # start_time = time.time()
                self.frame_times.append(time.time())
                if len(self.frame_times) > 30:
                    self.frame_times.pop(0)
                if len(self.frame_times) > 1:
                    fps = len(self.frame_times) / (self.frame_times[-1] - self.frame_times[0])
                else:
                    fps = 0.0
                self.frame_captured.emit(imgdata_np, fps)  # 发射信号

    def capture_frame(self):
        w = ctypes.c_uint32()
        h = ctypes.c_uint32()
        b = ctypes.c_uint32()
        c = ctypes.c_uint32()
        length = int(self.image_h * self.image_w * self.camera_bit / 8)
        # print("PreviewThread length =", length)
        if self.camera_bit == 16:
            imgdata = (ctypes.c_uint16 * length)()
            imgdata = ctypes.cast(imgdata, ctypes.POINTER(ctypes.c_ubyte))
        else:
            imgdata = (ctypes.c_uint8 * length)()
            imgdata = ctypes.cast(imgdata, ctypes.POINTER(ctypes.c_ubyte))
        ret = self.qhyccddll.GetQHYCCDLiveFrame(self.camhandle, byref(w), byref(h), byref(b), byref(c), imgdata)
        # print("GetQHYCCDSingleFrame() ret =", ret, "w =", w.value, "h =", h.value, "b =", b.value, "c =", c.value,
        #     "data size =", int(w.value * h.value * b.value * c.value / 8))
        # print("data =", imgdata)
        if ret == -1:
            time.sleep(0.005)
            # print("获取图像数据失败")
            return None
        imgdata = ctypes.cast(imgdata, ctypes.POINTER(ctypes.c_ubyte * length)).contents
        if c.value == 1:
            if self.camera_bit == 16:
                imgdata_np = np.frombuffer(imgdata, dtype=np.uint16).reshape((self.image_h, self.image_w))
            else:
                imgdata_np = np.frombuffer(imgdata, dtype=np.uint8).reshape((self.image_h, self.image_w))
        elif c.value == 3:
            if self.camera_bit == 16:
                imgdata_np = np.frombuffer(imgdata, dtype=np.uint16).reshape((self.image_h, self.image_w, c.value))
            else:
                imgdata_np = np.frombuffer(imgdata, dtype=np.uint8).reshape((self.image_h, self.image_w, c.value))
        else:
            raise ValueError("Unsupported number of channels")
        return imgdata_np

    def stop(self):
        self.running = False
        self.wait()