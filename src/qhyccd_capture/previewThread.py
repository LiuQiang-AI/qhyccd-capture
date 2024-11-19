from re import T
import threading  # 导入 threading 模块
import numpy as np
import ctypes
from ctypes import *
import time
from multiprocessing import Array
from threading import Lock
import warnings

from sympy import N
from .language import translations

class PreviewThread(threading.Thread):  
    def __init__(self, camhandle, qhyccddll, image_w,image_h, image_c, image_b,shm1,shm2,output_buffer, language='en'):
        super().__init__()
        self.camhandle = camhandle
        self.qhyccddll = qhyccddll
        self.image_w = image_w
        self.image_h = image_h
        self.image_b = image_b
        self.image_c = image_c
        self.image_size = self.image_w * self.image_h * self.image_c * (self.image_b // 8)
        self.running = False
        self.frame_times = []
        self.shm1 = shm1
        self.shm2 = shm2
        self.shm_status = True
        self.output_buffer = output_buffer
        self.lock = Lock()
        self.language = language
        self.paused = False  # 新增一个属性来控制是否暂停

    def run(self):
        while self.running:
            if not self.paused:  # 只有在不暂停的情况下才捕获帧
                img = self.capture_frame()
                if img is not None:
                    self.frame_times.append(time.time())
                    if len(self.frame_times) > 300:
                        self.frame_times.pop(0)
                    if len(self.frame_times) > 1:
                        fps = len(self.frame_times) / (self.frame_times[-1] - self.frame_times[0] + 0.0001)
                    else:
                        fps = 0.0001
                    self.frame_captured = fps
                    if self.shm_status:
                        # 将图像数据写入共享内存
                        with self.lock :
                            self.shm1.buf[:self.image_size] = img.tobytes()
                    else:
                        with self.lock :
                            self.shm2.buf[:self.image_size] = img.tobytes()
                    
                    self.output_buffer.put({"order":"preview_frame","data":{"fps":fps,"shm_status":self.shm_status,"image_size":self.image_size,"shape":(self.image_h,self.image_w,self.image_c,self.image_b)}})
                    self.shm_status = not self.shm_status
            else:
                time.sleep(0.1)

                
    def set_pause(self,pause):
        if pause:
            ret = self.qhyccddll.StopQHYCCDLive(self.camhandle)
            if ret != 0:
                self.output_buffer.put({"order":"error","data":translations[self.language]['preview_thread']['set_pause_failed']})
                return
            self.update_fps()
            self.paused = pause
        else:
            ret = self.qhyccddll.BeginQHYCCDLive(self.camhandle)
            if ret != 0:
                self.output_buffer.put({"order":"error","data":translations[self.language]['preview_thread']['set_pause_failed']})
                return
            self.paused = pause
        self.output_buffer.put({"order":"tip","data":translations[self.language]['preview_thread']['set_pause_success']})

    def update_fps(self):
        self.frame_times.clear()

    def capture_frame(self):
        w = ctypes.c_uint32()
        h = ctypes.c_uint32()
        b = ctypes.c_uint32()
        c = ctypes.c_uint32()
        
        with self.lock: 
            # 计算图像缓冲区大小
            buffer_size = self.image_w * self.image_h * self.image_c * (self.image_b // 8)
            self.image_size = buffer_size
            temp_buffer = (c_ubyte * buffer_size)()  # 创建临时缓冲区
            
            # 获取图像帧
            ret = self.qhyccddll.GetQHYCCDLiveFrame(self.camhandle, byref(w), byref(h), byref(b), byref(c), temp_buffer)
            
            # 检查返回值
            if ret == -1 or c.value != self.image_c:
                time.sleep(0.001)  # 等待一小段时间
                return None  
            
            img_size = w.value * h.value * c.value * (b.value // 8)
            
            # 将临时缓冲区转换为 numpy 数组
            img = np.ctypeslib.as_array(temp_buffer, shape=(img_size,))
            
            # 根据通道数处理图像
            if c.value == 3:  # 彩色图像
                img = img.reshape((h.value, w.value, c.value))
                img = img[:, :, ::-1]  # 将 BGR 转换为 RGB
            else:  # 灰度或其他格式
                img = img.reshape((h.value, w.value)) if self.image_b != 16 else img.view(np.uint16).reshape((h.value, w.value))
            
        return img  
        
    def handle_start(self):
        """处理启动请求的槽函数"""
        self.set_pause(False)
        self.running = True
        self.start()
        self.output_buffer.put({"order":"start_preview_success","data":''})

    def handle_stop(self):
        """处理停止请求的槽函数"""
        self.set_pause(True)
        self.running = False
        self.output_buffer.put({"order":"stop_preview_success","data":''})
        self.update_fps()
        self.join()  # 等待线程结束

    def update_image_parameters(self, image_w, image_h, image_c, image_b):
        """更新图像参数的方法"""
        with self.lock:  # 使用锁来确保线程安全
            self.image_w = image_w
            self.image_h = image_h
            self.image_c = image_c
            self.image_b = image_b
        self.output_buffer.put({"order":"updateSharedImageData_success","data":(image_w,image_h,image_c,image_b)})
        if self.paused:
            self.set_pause(False)
            self.output_buffer.put({"order":"tip","data":f"{translations[self.language]['preview_thread']['preview_update_parameters_success']}: {image_w}x{image_h}x{image_c}x{image_b}"})

    