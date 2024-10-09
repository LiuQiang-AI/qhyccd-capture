from PyQt5.QtCore import QThread, pyqtSignal
import numpy as np
import ctypes
from ctypes import byref
import warnings
from .language import translations
class CaptureThread(QThread):
    capture_finished = pyqtSignal(np.ndarray)

    def __init__(self, camhandle, qhyccddll, image_w, image_h, camera_bit, is_color_camera, bayer_conversion,language):
        super().__init__()
        self.language = language
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
        if ret != 0:
            warnings.warn(f"{translations[self.language]['debug']['exp_qhyccd_single_frame_failed']}: {ret}")
            return  # 如果启动失败，直接返回避免进一步阻塞

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
        # print("datasize =", length)

        ret = self.qhyccddll.GetQHYCCDSingleFrame(self.camhandle, byref(w), byref(h), byref(b), byref(c), imgdata)
        if ret != 0:
            warnings.warn(f"{translations[self.language]['debug']['get_qhyccd_single_frame_failed']}: {ret}")
            return  # 如果获取失败，直接返回避免进一步阻塞

        # print("GetQHYCCDSingleFrame() ret =", ret, "w =", w.value, "h =", h.value, "b =", b.value, "c =", c.value,
        #     "data size =", int(w.value * h.value * b.value * c.value / 8))
        # print("data =", imgdata)


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