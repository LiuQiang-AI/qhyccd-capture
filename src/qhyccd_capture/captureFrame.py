import numpy as np
import ctypes
from ctypes import byref
import warnings
from .language import translations
import threading
class CaptureThread(threading.Thread):

    def __init__(self, camhandle, qhyccddll,image_w, image_h,image_c, camera_bit,GPS_control,sdk_output_queue,language='cn'):
        super().__init__()
        self.language = language
        self.camhandle = camhandle
        self.qhyccddll = qhyccddll
        self.image_w = image_w
        self.image_h = image_h
        self.image_c = image_c
        self.camera_bit = camera_bit
        self.GPS_control = GPS_control
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
        if self.GPS_control:
            length += 44
        imgdata = (ctypes.c_ubyte * length)()

        ret = self.qhyccddll.GetQHYCCDSingleFrame(self.camhandle, byref(w), byref(h), byref(b), byref(c), imgdata)
        if ret != 0:
            warnings.warn(f"{translations[self.language]['debug']['get_qhyccd_single_frame_failed']}: {ret}")
            return  # 如果获取失败，直接返回避免进一步阻塞

        # 将临时缓冲区转换为 numpy 数组
        img = np.ctypeslib.as_array(imgdata, shape=(length,))
        
        gps_data = None
        if self.GPS_control:
            gps_data = img[:44]
            img = img[44:]
        
        # 根据通道数处理图像
        if c.value == 3:  # 彩色图像
            img = img.reshape((h.value, w.value, c.value))
            img = img[:, :, ::-1]  # 将 BGR 转换为 RGB
        else:  # 灰度或其他格式
            img = img.reshape((h.value, w.value)) if b.value != 16 else img.view(np.uint16).reshape((h.value, w.value))

        self.sdk_output_queue.put({"order":"singleCapture_success",'data':{'img':img,'gps_data':gps_data}})
    
    def stop(self):
        self.qhyccddll.CancelQHYCCDExposingAndReadout(self.camhandle)
        exit()
