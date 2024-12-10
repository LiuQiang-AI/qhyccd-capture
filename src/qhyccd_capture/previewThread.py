from re import T
import threading  # 导入 threading 模块
import numpy as np
import ctypes
from ctypes import *
import queue
import time
from multiprocessing import Array
from threading import Lock
import psutil
from .sharedMemoryManager import SharedMemoryManager
from .language import translations
from .save_video import SaveThread

class PreviewThread(threading.Thread):  
    def __init__(self, camhandle, qhyccddll, image_w,image_h, image_c, image_b,shm1_name,shm2_name,output_buffer, language='en'):
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
        self.shm1_name = shm1_name
        self.shm2_name = shm2_name
        self.shm_status = True
        self.output_buffer = output_buffer
        self.lock = Lock()
        self.language = language
        self.paused = False  # 新增一个属性来控制是否暂停
        self.burst_mode_state = False
        self.GPS_control = False
        self.save_thread = None
        self.buffer_queue = None
        self.save_thread_running = False
        self.memory_state = True
        self.memory_warning = False
        self.fps = 0
        self.record_time_mode = False
        self.record_frame_mode = False
        self.continuous_mode = False
        self.record_time = 0
        self.total_frames = 0
        self.record_start_time = 0
        self.record_frame_count = 0
        self.progress_bar_value = 0
        
    def run(self):
        while self.running:
            if not self.paused:  # 只有在不暂停的情况下才捕获帧
                img,gps_data = self.capture_frame()
                if img is not None:
                    if not self.burst_mode_state:
                        self.frame_times.append(time.time())
                        if len(self.frame_times) > 300:
                            self.frame_times.pop(0)
                        if len(self.frame_times) > 1:
                            self.fps = len(self.frame_times) / (self.frame_times[-1] - self.frame_times[0] + 0.0001)
                        else:
                            self.fps = 0.0001
                            
                        memory_info = psutil.virtual_memory()
                        used_memory = memory_info.percent  # 已用内存
                        if int(used_memory) < 80:
                            self.memory_state = True
                        else:
                            self.memory_state = False
                            
                        if not self.memory_state and self.save_thread is not None and self.save_thread_running and self.buffer_queue is not None and not self.memory_warning:
                            self.output_buffer.put({"order":"tip","data":translations[self.language]['preview_thread']['memory_warning']})
                            self.memory_warning = True
                        if self.save_thread is not None and self.save_thread_running and self.buffer_queue is not None and self.memory_state:
                            self.buffer_queue.put(img)
                            if self.record_time_mode:
                                if self.record_start_time == 0:
                                    self.record_start_time = time.time()
                                if time.time() - self.record_start_time >= self.record_time:
                                    self.stop_save_video()
                                    self.output_buffer.put({"order":"tip","data":translations[self.language]['preview_thread']['record_time_mode_success']})
                                    self.output_buffer.put({"order":"record_end","data":''})
                                else:
                                    self.progress_bar_value = int((time.time() - self.record_start_time) / self.record_time * 100)
                                    self.output_buffer.put({"order":"progress_bar_value","data":self.progress_bar_value})
                            elif self.record_frame_mode:
                                self.record_frame_count += 1
                                if self.record_frame_count >= self.total_frames:
                                    self.stop_save_video()
                                    self.output_buffer.put({"order":"tip","data":translations[self.language]['preview_thread']['record_frame_mode_success']})
                                    self.output_buffer.put({"order":"record_end","data":''})
                                else:
                                    self.progress_bar_value = int(self.record_frame_count / self.total_frames * 100)
                                    self.output_buffer.put({"order":"progress_bar_value","data":self.progress_bar_value})
                        self.frame_captured = self.fps
                        with SharedMemoryManager(name=self.shm1_name) as shm1, SharedMemoryManager(name=self.shm2_name) as shm2:
                            shm = shm1 if self.shm_status else shm2
                            with self.lock:
                                shm.buf[:self.image_size] = img.tobytes()
                        self.output_buffer.put({"order":"preview_frame","data":{"fps":self.fps,"shm_status":self.shm_status,"image_size":self.image_size,"shape":(self.image_h,self.image_w,self.image_c,self.image_b),"gps_data":gps_data}})
                        self.shm_status = not self.shm_status
                    else:
                        with SharedMemoryManager(name=self.shm1_name) as shm1, SharedMemoryManager(name=self.shm2_name) as shm2:
                            shm = shm1 if self.shm_status else shm2
                            with self.lock:
                                shm.buf[:self.image_size] = img.tobytes()
                            self.output_buffer.put({"order":"burst_mode_frame","data":{"shm_status":self.shm_status,"image_size":self.image_size,"shape":(self.image_h,self.image_w,self.image_c,self.image_b),"gps_data":gps_data}})
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

    def update_GPS_control(self,data):
        self.GPS_control = data

    def update_fps(self):
        self.frame_times.clear()

    def capture_frame(self):
        try:
            w = ctypes.c_uint32()
            h = ctypes.c_uint32()
            b = ctypes.c_uint32()
            c = ctypes.c_uint32()
            
            with self.lock:
                # 计算图像缓冲区大小
                buffer_size = self.image_w * self.image_h * self.image_c * (self.image_b // 8)
                self.image_size = buffer_size
                if self.GPS_control:
                    buffer_size += 44  # 增加44字节的GPS数据大小

                temp_buffer = (ctypes.c_ubyte * buffer_size)()  # 创建临时缓冲区
                
                # 获取图像帧
                ret = self.qhyccddll.GetQHYCCDLiveFrame(self.camhandle, byref(w), byref(h), byref(b), byref(c), temp_buffer)
                # 检查返回值
                if ret == -1 or c.value != self.image_c:
                    time.sleep(0.001)  # 等待一小段时间
                    return None, None  
                # 解析GPS数据
                if self.GPS_control:
                    # 直接使用 np.frombuffer 并切片获取 GPS 数据
                    gps_data = np.frombuffer(temp_buffer, dtype=np.uint8)[:44]
                else:
                    gps_data = None
                
                # 计算图像数据的实际大小
                dtype = np.uint8 if b.value == 8 else np.uint16  # 根据位深选择数据类型
                offset = 22 if self.GPS_control else 0
                if b.value == 8:
                    offset *= 2
                # 直接从缓冲区创建数组，避免额外的数据复制
                img = np.frombuffer(temp_buffer, dtype=dtype)[offset:]
                # 定义形状并重塑数组
                if c.value == 3:
                    shape = (h.value, w.value, c.value)
                    img = img.reshape(shape)
                    img = img[:, :, ::-1]  # 将 BGR 转换为 RGB
                else:
                    shape = (h.value, w.value)
                    img = img.reshape(shape)
        except Exception as e:
            self.output_buffer.put({"order":"error","data":f"{translations[self.language]['preview_thread']['capture_frame_failed']}: {e}"})
            return None, None
        return img, gps_data
        
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
        self.set_burst_mode((False,0,0))
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

    def start_burst_mode(self,data):
        if not self.burst_mode_state:
            return
        state,min_value,max_value = data
        
        ret = self.qhyccddll.SetQHYCCDBurstModeStartEnd(self.camhandle,min_value,max_value)
        if ret != 0:
            self.output_buffer.put({"order":"error","data":f"{translations[self.language]['preview_thread']['set_burst_mode_start_end_failed']}: {state}"})
            return
        self.output_buffer.put({"order":"tip","data":f"{translations[self.language]['preview_thread']['set_burst_mode_start_end_success']}: {state}"})
        
        ret = self.qhyccddll.SetQHYCCDBurstIDLE(self.camhandle,True)
        if ret != 0:
            self.output_buffer.put({"order":"error","data":f"{translations[self.language]['preview_thread']['set_burst_mode_idle_failed']}: {ret}"})
            return
        self.output_buffer.put({"order":"tip","data":f"{translations[self.language]['preview_thread']['set_burst_mode_idle_success']}: {ret}"})
        time.sleep(0.2)
        ret = self.qhyccddll.ReleaseQHYCCDBurstIDLE(self.camhandle)
        if ret != 0:
            self.output_buffer.put({"order":"error","data":f"{translations[self.language]['preview_thread']['release_burst_mode_idle_failed']}: {ret}"})
            return
        self.output_buffer.put({"order":"tip","data":f"{translations[self.language]['preview_thread']['release_burst_mode_idle_success']}: {ret}"})

    def set_burst_mode(self,data):
        state,min_value,max_value = data
        if state:
            ret = self.qhyccddll.SetQHYCCDBurstModeStartEnd(self.camhandle,min_value,max_value)
            if ret != 0:
                self.output_buffer.put({"order":"error","data":f"{translations[self.language]['preview_thread']['set_burst_mode_start_end_failed']}: {state}"})
                return
            self.output_buffer.put({"order":"tip","data":f"{translations[self.language]['preview_thread']['set_burst_mode_start_end_success']}: {state}"})
            
            ret = self.qhyccddll.SetQHYCCDBurstModePatchNumber(self.camhandle,32001)
            if ret != 0:
                self.output_buffer.put({"order":"error","data":f"{translations[self.language]['preview_thread']['set_burst_mode_patch_number_failed']}: {state}"})
                return
            self.output_buffer.put({"order":"tip","data":f"{translations[self.language]['preview_thread']['set_burst_mode_patch_number_success']}: {state}"})
            
            ret = self.qhyccddll.EnableQHYCCDBurstMode(self.camhandle,True)
            if ret != 0:
                self.output_buffer.put({"order":"error","data":f"{translations[self.language]['preview_thread']['set_burst_mode_failed']}: {state}"})
                return
            self.output_buffer.put({"order":"tip","data":f"{translations[self.language]['preview_thread']['set_burst_mode_success']}: {state}"})
            self.burst_mode_state = True
        else:
            self.burst_mode_state = False
            ret = self.qhyccddll.EnableQHYCCDBurstMode(self.camhandle,False)
            if ret != 0:
                self.output_buffer.put({"order":"error","data":f"{translations[self.language]['preview_thread']['set_burst_mode_failed']}: {state}"})
                return
            self.output_buffer.put({"order":"tip","data":f"{translations[self.language]['preview_thread']['set_burst_mode_success']}: {state}"})

    def start_save_video(self,data):
        self.record_time_mode = data['record_time_mode']
        self.record_frame_mode = data['record_frame_mode']
        self.continuous_mode = data['continuous_mode']
        self.record_time = data['record_time']
        self.total_frames = data['total_frames']
        self.buffer_queue = queue.Queue()
        self.save_thread = SaveThread(self.output_buffer,self.buffer_queue, data['path'], data['file_name'], data['save_format'], data['save_mode'], self.fps,self.language,data['jpeg_quality'],data['tiff_compression'],data['fits_header'])
        self.save_thread_running = True
        self.save_thread.start()
        self.output_buffer.put({"order":"tip","data":translations[self.language]['preview_thread']['start_save_video_success']})
        
    def stop_save_video(self):
        if self.save_thread is not None:
            self.save_thread_running = False
            if self.buffer_queue is not None:
                self.buffer_queue.put("end")
            self.save_thread = None
            self.buffer_queue = None
        self.fps = 0
        self.record_time_mode = False
        self.record_frame_mode = False
        self.continuous_mode = False
        self.record_time = 0
        self.total_frames = 0
        self.record_start_time = 0
        self.record_frame_count = 0
        self.progress_bar_value = 0
        self.memory_warning = False
        self.output_buffer.put({"order":"record_end","data":''})
        self.output_buffer.put({"order":"tip","data":translations[self.language]['preview_thread']['stop_save_video_success']})
    