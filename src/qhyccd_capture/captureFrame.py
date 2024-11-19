import numpy as np
import ctypes
from ctypes import byref
import warnings
from .language import translations
import threading
class CaptureThread(threading.Thread):

    def __init__(self, camhandle, qhyccddll, image_w, image_h,image_c, camera_bit,sdk_output_queue,language='cn'):
        super().__init__()
        self.language = language
        self.camhandle = camhandle
        self.qhyccddll = qhyccddll
        self.image_w = image_w
        self.image_h = image_h
        self.image_c = image_c
        self.camera_bit = camera_bit
        self.sdk_output_queue = sdk_output_queue

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

        self.sdk_output_queue.put({"order":"singleCapture_success",'data':imgdata_np})
    
    def stop(self):
        self.qhyccddll.CancelQHYCCDExposingAndReadout(self.camhandle)
        exit()
