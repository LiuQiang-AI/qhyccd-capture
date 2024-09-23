from PyQt5.QtCore import QThread, pyqtSignal
import numpy as np
import ctypes
from ctypes import byref

class CaptureThread(QThread):
    capture_finished = pyqtSignal(np.ndarray)

    def __init__(self, camhandle, qhyccddll, image_w, image_h, camera_bit, is_color_camera, bayer_conversion):
        super().__init__()
        self.camhandle = camhandle
        self.qhyccddll = qhyccddll
        self.image_w = image_w
        self.image_h = image_h
        self.camera_bit = camera_bit
        self.is_color_camera = is_color_camera
        self.bayer_conversion = bayer_conversion

    def run(self):
        # 启动单帧模式曝光
        ret = self.qhyccddll.ExpQHYCCDSingleFrame(self.camhandle)
        print("ExpQHYCCDSingleFrame() ret =", ret)

        # 获取单帧图像数据
        w = ctypes.c_uint32()
        h = ctypes.c_uint32()
        b = ctypes.c_uint32()
        c = ctypes.c_uint32()
        length = int(self.image_h * self.image_w * self.camera_bit / 8)
        if self.camera_bit == 16:
            imgdata = (ctypes.c_uint16 * length)()
            imgdata = ctypes.cast(imgdata, ctypes.POINTER(ctypes.c_ubyte))
        else:
            imgdata = (ctypes.c_uint8 * length)()
            imgdata = ctypes.cast(imgdata, ctypes.POINTER(ctypes.c_ubyte))
        print("datasize =", length)

        ret = self.qhyccddll.GetQHYCCDSingleFrame(self.camhandle, byref(w), byref(h), byref(b), byref(c), imgdata)
        print("GetQHYCCDSingleFrame() ret =", ret, "w =", w.value, "h =", h.value, "b =", b.value, "c =", c.value,
            "data size =", int(w.value * h.value * b.value * c.value / 8))
        print("data =", imgdata)

        if ret == -1:
            print("获取图像数据失败")
            return

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

        self.capture_finished.emit(imgdata_np)