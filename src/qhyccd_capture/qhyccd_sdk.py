from ctypes import *
import ctypes
import numpy as np
import os
from .language import translations
import time
import multiprocessing
from multiprocessing import shared_memory
import sys
import threading

from .control_id import CONTROL_ID
from .previewThread import PreviewThread
from .captureFrame import CaptureThread
from .language import translations

class QHYCCDSDK(multiprocessing.Process):
    def __init__(self, input_queue, output_queue,language):
        super().__init__()  # 初始化父类
        self.daemon = True
        self.input_queue = input_queue  # 接收数据的队列
        self.output_queue = output_queue  # 发送结果的队列
        self.image_buffer = None
        self.camhandle = 0  # 相机句柄
        self.qhyccddll = None  # 相机库
        self.language = language  # 语言
        self.qhyccd_resource_path = None
        self.preview_thread = None
        self.last_order = None
        self.last_data = None
        self.capture_thread = None
        self.shm1 = None
        self.shm2 = None
        self.is_running = True
        self.init_command_map()
    
    def init_command_map(self):
        self.command_map = {
            'stop': self.stop,      # 停止进程
            'init_qhyccd_resource': self.init_qhyccd_resource,     # 初始化相机资源
            'read_camera_name': self.read_camera_name,               # 读取相机名称
            'open_camera': self.open_camera,                         # 打开相机
            'get_readout_mode': self.get_readout_mode,               # 获取读取模式
            'get_stream_and_capture_mode': self.get_stream_and_capture_mode, # 获取流和捕获模式
            'init_camera': self.init_camera,                           # 初始化相机
            'set_camera_depth': self.set_camera_depth,               # 设置相机深度
            'update_debayer_mode': self.update_debayer_mode,         # 更新去马赛克模式
            'close_camera': self.close_camera,                         # 关闭相机
            'get_is_color_camera': self.get_is_color_camera,           # 获取是否彩色相机
            'get_limit_data': self.get_limit_data,                   # 获取限位器数据
            'get_effective_area': self.get_effective_area,           # 获取有效区域
            'get_camera_config': self.get_camera_config,             # 获取相机配置
            'get_camera_pixel_bin': self.get_camera_pixel_bin,       # 获取相机像素bin
            'set_camera_pixel_bin': self.set_camera_pixel_bin,       # 设置相机像素bin
            'update_resolution': self.update_resolution,                 # 更新分辨率
            'get_camera_depth': self.get_camera_depth,               # 获取相机深度
            'set_resolution': self.set_resolution,                     # 设置分辨率
            'get_planned_shooting_data': self.get_planned_shooting_data, # 获取计划拍摄数据
            'get_cfw_info': self.get_cfw_info,                         # 获取滤镜轮信息
            'run_plan': self.run_plan,                                 # 运行计划
            'get_is_temperature_control': self.get_is_temperature_control, # 获取是否温度控制
            'get_temperature': self.get_temperature,                   # 获取温度
            'set_temperature': self.set_temperature,                   # 设置温度
            'get_auto_exposure_is_available': self.get_auto_exposure_is_available, # 获取是否自动曝光
            'get_auto_exposure_limits': self.get_auto_exposure_limits, # 获取自动曝光限制
            'set_auto_exposure': self.set_auto_exposure,             # 设置自动曝光
            'get_exposure_value': self.get_exposure_value,           # 获取曝光值
            'get_auto_white_balance_is_available': self.get_auto_white_balance_is_available, # 获取是否自动白平衡
            'set_auto_white_balance': self.set_auto_white_balance,   # 设置自动白平衡
            'get_auto_white_balance_values': self.get_auto_white_balance_values, # 获取自动白平衡值 
            'set_exposure_time': self.set_exposure_time,               # 设置曝光时间
            'setCFWFilter': self.set_CFW_filter,                         # 设置滤镜轮
            'set_offset': self.set_offset,                               # 设置偏移
            'set_gain': self.set_gain,                                   # 设置增益
            'set_usb_traffic': self.set_usb_traffic,                     # 设置USB流量
            'set_white_balance': self.set_white_balance,                 # 设置白平衡
            'stop_preview': self.stop_preview,                           # 停止预览
            'start_preview': self.start_preview,                         # 开始预览
            'set_preview_pause': self.update_preview_pause,             # 设置预览暂停
            'update_shared_image_data': self.update_shared_image_data, # 更新共享图像数据
            'clear_fps_data': self.clear_fps_data,                       # 清除FPS数据
            'singleCapture': self.single_capture,                       # 单次捕获
            'cancel_capture': self.cancel_capture,                       # 取消捕获
            'get_image_buffer_size': self.get_image_buffer_size,         # 获取图像缓冲区大小
            'set_image_buffer': self.set_image_buffer,                   # 设置图像缓冲区
        }

    def run(self):
        try:
            # 进程运行的主循环
            while self.is_running:
                data = self.input_queue.get()  # 从输入队列获取数据
                if data is None:  # 检查是否为退出信号
                    self.is_running = False  # 设置运行标志为False
                    continue
                if data['order'] == 'end':
                    self.is_running = False  # 确保能够响应结束命令
                    break
                order = data['order']
                if order not in self.command_map:
                    self._report_error(translations[self.language]['qhyccd_sdk']['command_not_found'],sys._getframe().f_lineno)
                if self.input_queue.qsize() >= 3:
                    self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['queue_size']} {self.input_queue.qsize()}"})
                self.command_map[order](data['data'])
        except Exception as e:
            self._report_error(f"{translations[self.language]['qhyccd_sdk']['process_error']}: {e}",sys._getframe().f_lineno)
        finally:
            self.stop(None)
         
    def _report_error(self, message, line_number=None):
        error_location = f"{translations[self.language]['qhyccd_sdk']['file']   }: {__file__}, {translations[self.language]['qhyccd_sdk']['line_number']}: {line_number if line_number is not None else sys._getframe().f_lineno}"  # 获取当前文件名和行号
        self.output_queue.put({"order": "error", "data": f"{message}, {error_location}"})
    
    def init_qhyccd_resource(self,file_path=None,state=False):
        system_name = os.name
        if file_path is None or file_path == "": 
            if system_name == 'posix':
                # 类 Unix 系统（如 Linux 或 macOS）
                lib_path = '/usr/local/lib/libqhyccd.so'
                if os.path.exists(lib_path):
                    self.qhyccddll = cdll.LoadLibrary(lib_path)
                else:
                    self._report_error(translations[self.language]['qhyccd_sdk']['not_found_sdk'],sys._getframe().f_lineno)
            elif system_name == 'nt':
                # Windows 系统
                import platform
                arch = platform.architecture()[0]
                if arch == '32bit':
                    # X86 系统
                    lib_path = 'C:\\Program Files\\QHYCCD\\AllInOne\\sdk\\x86\\qhyccd.dll'
                elif arch == '64bit':
                    # X64 系统
                    lib_path = 'C:\\Program Files\\QHYCCD\\AllInOne\\sdk\\x64\\qhyccd.dll'
                else:
                    self._report_error(translations[self.language]['qhyccd_sdk']['unknown_architecture'],sys._getframe().f_lineno)
                if os.path.exists(lib_path):
                    self.qhyccddll = cdll.LoadLibrary(lib_path)
                else:
                    self._report_error("not_found_sdk",sys._getframe().f_lineno)
            else:
                # 其他操作系统（不推荐使用）
                lib_path = '/usr/local/lib/libqhyccd.so'
                if os.path.exists(lib_path):
                    self.qhyccddll = cdll.LoadLibrary(lib_path)
                else:
                    self._report_error(translations[self.language]['qhyccd_sdk']['not_found_sdk'],sys._getframe().f_lineno)
            # 设置函数的参数和返回值类型
            file_path = lib_path
        else:
            self.qhyccddll = cdll.LoadLibrary(file_path)

        # 获取机 ID
        self.qhyccddll.GetQHYCCDId.argtypes = [ctypes.c_uint32, ctypes.c_char_p] # type: ignore

        # 通过相机 ID 打开相机
        self.qhyccddll.OpenQHYCCD.argtypes = [ctypes.c_char_p] # type: ignore
        self.qhyccddll.OpenQHYCCD.restype = ctypes.c_void_p # type: ignore

        # 关闭相机
        self.qhyccddll.CloseQHYCCD.argtypes = [ctypes.c_void_p] # type: ignore

        # 读模式
        self.qhyccddll.GetQHYCCDNumberOfReadModes.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)] # type: ignore
        self.qhyccddll.GetQHYCCDReadModeName.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_char_p] # type: ignore  
        self.qhyccddll.GetQHYCCDReadModeResolution.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32), # type: ignore
                                                        ctypes.POINTER(ctypes.c_uint32)] # type: ignore
        self.qhyccddll.SetQHYCCDReadMode.argtypes = [ctypes.c_void_p, ctypes.c_uint32] # type: ignore

        # 设置帧模式或实时流模式
        self.qhyccddll.SetQHYCCDStreamMode.argtypes = [ctypes.c_void_p, ctypes.c_uint32] # type: ignore

        # 初始化相机
        self.qhyccddll.InitQHYCCD.argtypes = [ctypes.c_void_p] # type: ignore

        # 获取相机芯片信息
        self.qhyccddll.GetQHYCCDChipInfo.argtypes = [ctypes.c_void_p,       # type: ignore
                                            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
                                            ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint32),
                                            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
                                            ctypes.POINTER(ctypes.c_uint32)] # type: ignore

        # 判断参数是否可用
        self.qhyccddll.IsQHYCCDControlAvailable.argtypes = [ctypes.c_void_p, ctypes.c_uint32] # type: ignore
        self.qhyccddll.IsQHYCCDControlAvailable.restype = ctypes.c_bool # type: ignore

        
        # 获参数值
        self.qhyccddll.GetQHYCCDParam.argtypes = [ctypes.c_void_p, ctypes.c_uint32] # type: ignore
        self.qhyccddll.GetQHYCCDParam.restype = ctypes.c_double # type: ignore

        # 设置参数
        self.qhyccddll.SetQHYCCDParam.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_double] # type: ignore

        # 获取参数值的范围
        self.qhyccddll.GetQHYCCDParamMinMaxStep.argtypes = [ctypes.c_void_p, ctypes.c_uint32, # type: ignore
                                                    ctypes.POINTER(ctypes.c_double),ctypes.POINTER(ctypes.c_double),
                                                    ctypes.POINTER(ctypes.c_double)] # type: ignore
        self.qhyccddll.GetQHYCCDParamMinMaxStep.restype = ctypes.c_double # type: ignore

        # 设置去马赛克（Debayer）开关，仅对彩色相机有效
        self.qhyccddll.SetQHYCCDDebayerOnOff.argtypes = [ctypes.c_void_p, ctypes.c_bool] # type: ignore

        # 设置 bin 模式
        self.qhyccddll.SetQHYCCDBinMode.argtypes = [ctypes.c_void_p, ctypes.c_uint32] # type: ignore

        # 设置分辨率和 ROI
        self.qhyccddll.SetQHYCCDResolution.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, # type: ignore
                                                ctypes.c_uint32]

        # 启动单帧模式曝光
        self.qhyccddll.ExpQHYCCDSingleFrame.argtypes = [ctypes.c_void_p] # type: ignore
        
        # 获取已曝光时长
        self.qhyccddll.GetQHYCCDExposureRemaining.argtypes = [ctypes.c_void_p] # type: ignore
        # self.qhyccddll.GetQHYCCDExposureRemaining.restype = ctypes.c_double
        
        # 获取单帧数据
        self.qhyccddll.GetQHYCCDSingleFrame.argtypes = [ctypes.c_void_p, # type: ignore
                                                ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint32),
                                                ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint32),
                                                ctypes.POINTER(ctypes.c_uint8)]

        # 取消单次曝光，相机将不输出帧数据
        self.qhyccddll.CancelQHYCCDExposingAndReadout.argtypes = [ctypes.c_void_p] # type: ignore

        # 启动实时流式
        self.qhyccddll.BeginQHYCCDLive.argtypes = [ctypes.c_void_p] # type: ignore

        # 获取实时帧数据
        self.qhyccddll.GetQHYCCDLiveFrame.argtypes = [ctypes.c_void_p, # type: ignore
                                                ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint32),
                                                ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint32),
                                                ctypes.POINTER(ctypes.c_uint8)] # type: ignore

        # 停止实时流模式
        self.qhyccddll.StopQHYCCDLive.argtypes = [ctypes.c_void_p] # type: ignore

        # 转换图像数据（从16位转换为8位）
        self.qhyccddll.Bits16ToBits8.argtypes = [ctypes.c_void_p, # type: ignore
                                            ctypes.POINTER(ctypes.c_uint8), ctypes.POINTER(ctypes.c_uint8),
                                            ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint16, ctypes.c_uint16]
        
        # 判断滤镜轮是否连接
        self.qhyccddll.IsQHYCCDCFWPlugged.argtypes = [ctypes.c_void_p] # type: ignore
        self.qhyccddll.IsQHYCCDCFWPlugged.restype = ctypes.c_bool # type: ignore
        
        # EXPORTC uint32_t STDCALL SendOrder2QHYCCDCFW(qhyccd_handle *handle,char *order,uint32_t length);
        # 发送命令到滤镜轮
        self.qhyccddll.SendOrder2QHYCCDCFW.argtypes = [ctypes.c_void_p,ctypes.c_char_p,ctypes.c_uint32] # type: ignore

        # 获取湿度
        self.qhyccddll.GetQHYCCDHumidity.argtypes = [ctypes.c_void_p,ctypes.POINTER(ctypes.c_double)] # type: ignore

        # 获取相机有效扫描范围
        self.qhyccddll.GetQHYCCDEffectiveArea.argtypes = [ctypes.c_void_p,ctypes.POINTER(ctypes.c_uint32), # type: ignore
                                                        ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint32), # type: ignore
                                                        ctypes.POINTER(ctypes.c_uint32)] # type: ignore
        
        # 输出Debug
        self.qhyccddll.OutputQHYCCDDebug.argtypes = [ctypes.c_char_p] # type: ignore
        # 初始化QHYCCD资源
        ret = self.qhyccddll.InitQHYCCDResource() # type: ignore
        if ret != 0:
            self._report_error(translations[self.language]['qhyccd_sdk']['init_failed'],sys._getframe().f_lineno)
        else:
            self.qhyccd_resource_path = file_path
            if not state:
                self.output_queue.put({"order":"init_qhyccd_resource_success","data":file_path})
            self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['init_success']}:{file_path}"})
            
    def releaseQHYCCDResource(self,data):
        ret = self.qhyccddll.ReleaseQHYCCDResource() # type: ignore
        if ret != 0:
            self._report_error(translations[self.language]['qhyccd_sdk']['release_resource_failed'],sys._getframe().f_lineno)
        else:
            self.qhyccddll = None
            self.output_queue.put({"order":"tip","data":translations[self.language]['qhyccd_sdk']['release_resource_success']})
            self.output_queue.put({"order":"releaseResource_success","data":None})
    
    def stop(self, data):
        try:
            if self.camhandle > 0:
                self.close_camera(False)
            if self.qhyccddll is not None:
                self.releaseQHYCCDResource('')
                self.qhyccddll = None
            self.cleanup_shared_memory(self.shm1)
            self.cleanup_shared_memory(self.shm2)
            self.input_queue.close()
            self.output_queue.close()
        finally:
            self.is_running = False
            
    def cleanup_shared_memory(self, shm):
        if shm is not None:
            try:
                shm.close()
                shm.unlink()
            finally:
                shm = None

    def read_camera_name(self,data):
        # 扫描QHYCCD相机
        num = self.qhyccddll.ScanQHYCCD() # type: ignore
        self.camera_ids = {}
        # 遍历所有扫描到的相机
        for index in range(num):
            # 获相机 ID
            id_buffer = ctypes.create_string_buffer(40)
            ret = self.qhyccddll.GetQHYCCDId(index, id_buffer) # type: ignore
            if ret != 0:
                self._report_error(translations[self.language]['qhyccd_sdk']['get_camera_id_failed'],sys._getframe().f_lineno)
            else:
                result_id = id_buffer.value.decode("utf-8")
                self.camera_ids[result_id] = id_buffer
        self.output_queue.put({"order":"readCameraName_success","data":list(self.camera_ids.keys())})
        self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['scan_camera_success']}:{len(self.camera_ids)}"})

    def get_image_buffer_size(self,data):
        max_buffer_size = 0
        for camera_name in list(self.camera_ids.keys()):
            camera_id = self.camera_ids[camera_name]
            camhandle = self.qhyccddll.OpenQHYCCD(camera_id) # type: ignore
            if camhandle <= 0:
                self._report_error(translations[self.language]['qhyccd_sdk']['open_camera_failed'],sys._getframe().f_lineno)
                continue
            readModeNum = ctypes.c_uint32()
            ret = self.qhyccddll.GetQHYCCDNumberOfReadModes(camhandle,byref(readModeNum)) # type: ignore
            if ret < 0:
                self._report_error(translations[self.language]['qhyccd_sdk']['get_read_mode_number_failed'],sys._getframe().f_lineno)
                continue
            for index in range(readModeNum.value):
                name_buffer = ctypes.create_string_buffer(40)
                ret = self.qhyccddll.GetQHYCCDReadModeName(camhandle, index, name_buffer) # type: ignore
                if ret != 0:
                    self._report_error(translations[self.language]['qhyccd_sdk']['get_readout_mode_name_failed'],sys._getframe().f_lineno)
                    continue
                ret = self.qhyccddll.SetQHYCCDReadMode(camhandle, index) # type: ignore
                if ret != 0:
                    self._report_error(translations[self.language]['qhyccd_sdk']['set_readout_mode_failed'],sys._getframe().f_lineno)
                    continue
                ret = self.qhyccddll.SetQHYCCDStreamMode(camhandle, 0) # type: ignore
                if ret != 0:
                    self._report_error(translations[self.language]['qhyccd_sdk']['set_stream_mode_failed'],sys._getframe().f_lineno)
                    continue
                ret = self.qhyccddll.InitQHYCCD(camhandle) # type: ignore
                if ret != 0:
                    self._report_error(translations[self.language]['qhyccd_sdk']['init_camera_failed'],sys._getframe().f_lineno)
                    continue
                chipW = ctypes.c_double()  # 芯片宽度
                chipH = ctypes.c_double()  # 芯片高度
                imageW = ctypes.c_uint32()  # 图像宽度
                imageH = ctypes.c_uint32()  # 图像高度
                pixelW = ctypes.c_double()  # 像素宽度
                pixelH = ctypes.c_double()  # 像素高度
                imageB = ctypes.c_uint32()  # 图像位深度
                ret = self.qhyccddll.GetQHYCCDChipInfo(camhandle, byref(chipW), byref(chipH), byref(imageW), byref(imageH), byref(pixelW), # type: ignore
                                                byref(pixelH), byref(imageB)) # type: ignore
                if ret != 0:
                    self._report_error(translations[self.language]['qhyccd_sdk']['get_camera_config_failed'],sys._getframe().f_lineno)
                    continue
                
                is_color_camera = False
                try:
                    if not self.qhyccddll.IsQHYCCDControlAvailable(camhandle, CONTROL_ID.CAM_IS_COLOR.value): # type: ignore
                        is_color_value = self.qhyccddll.GetQHYCCDParam(camhandle, CONTROL_ID.CAM_IS_COLOR.value) # type: ignore
                        if is_color_value == 4294967295.0:
                            self._report_error(translations[self.language]['qhyccd_sdk']['get_camera_is_color_failed'],sys._getframe().f_lineno)
                            is_color_camera = self.is_color_camera_by_name(camera_name)
                        else:
                            is_color_camera = not bool(is_color_value)
                    else:
                        is_color_camera = self.is_color_camera_by_name(camera_name)
                except Exception as e:
                    is_color_camera = self.is_color_camera_by_name(camera_name)
                finally:
                    if is_color_camera:
                        buffer_size = imageW.value * imageH.value * 3 
                    else:
                        buffer_size = imageW.value * imageH.value * 2
                
                if buffer_size > max_buffer_size:
                    max_buffer_size = buffer_size
                if camhandle != self.camhandle:
                    ret = self.qhyccddll.CloseQHYCCD(camhandle) # type: ignore
                    if ret != 0:
                        self._report_error(translations[self.language]['qhyccd_sdk']['close_camera_failed'],sys._getframe().f_lineno)
    
        self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['get_image_buffer_size_success']}:{max_buffer_size}"})
        self.output_queue.put({"order":"getImageBufferSize_success","data":max_buffer_size})

    def open_camera(self,camera_name):
        if camera_name not in self.camera_ids or camera_name == "":
            return
        camera_id = self.camera_ids[camera_name]
        self.camera_name = camera_name
        ret = self.qhyccddll.OpenQHYCCD(camera_id) # type: ignore
        if ret is None or ret <= 0:
            self._report_error(translations[self.language]['qhyccd_sdk']['open_camera_failed'],sys._getframe().f_lineno)
        self.camhandle = ret
        self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['open_camera_success']}:{camera_name}"})
        readModeNum = ctypes.c_uint32()
        ret = self.qhyccddll.GetQHYCCDNumberOfReadModes(self.camhandle,byref(readModeNum)) # type: ignore
        if ret < 0:
            self._report_error(translations[self.language]['qhyccd_sdk']['get_read_mode_number_failed'],sys._getframe().f_lineno)
            return
        '''获取相机读取模式名称'''
        self.readout_mode_name_dict = {}
        for index in range(readModeNum.value):
            name_buffer = ctypes.create_string_buffer(40)
            ret = self.qhyccddll.GetQHYCCDReadModeName(self.camhandle, index, name_buffer) # type: ignore
            if ret != 0:
                self._report_error(translations[self.language]['qhyccd_sdk']['get_readout_mode_name_failed'],sys._getframe().f_lineno)
                return
            result_name = name_buffer.value.decode("utf-8")
            self.readout_mode_name_dict[f"{result_name}"] = index
        self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['get_readout_mode_name_success']}"})
        
        self.stream_and_capture_mode_dict = {}
        ret = self.qhyccddll.IsQHYCCDControlAvailable(self.camhandle, CONTROL_ID.CAM_LIVEVIDEOMODE.value) # type: ignore
        if ret != 0:    
            self._report_error(translations[self.language]['qhyccd_sdk']['camera_not_support_continuous_mode'],sys._getframe().f_lineno)
        else:
            self.stream_and_capture_mode_dict[f"{translations[self.language]['qhyccd_capture']['continuous_mode']}"] = 1
        ret = self.qhyccddll.IsQHYCCDControlAvailable(self.camhandle, CONTROL_ID.CAM_SINGLEFRAMEMODE.value) # type: ignore
        if ret != 0:
            self._report_error(translations[self.language]['qhyccd_sdk']['camera_not_support_single_frame_mode'],sys._getframe().f_lineno)
        else:
            self.stream_and_capture_mode_dict[f"{translations[self.language]['qhyccd_capture']['single_frame_mode']}"] = 0
        self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['get_stream_and_capture_mode_success']}"})
        self.output_queue.put({"order":"openCamera_success","data":{'id':self.camhandle,'readout_mode_name_dict':self.readout_mode_name_dict,'stream_and_capture_mode_dict':self.stream_and_capture_mode_dict}})
 
    def get_readout_mode(self,data):
        readModeNum = ctypes.c_uint32()
        ret = self.qhyccddll.GetQHYCCDNumberOfReadModes(self.camhandle,byref(readModeNum)) # type: ignore
        if ret < 0:
            self._report_error(translations[self.language]['qhyccd_sdk']['get_read_mode_number_failed'],sys._getframe().f_lineno)
            return
        '''获取相机读取模式名称'''
        self.readout_mode_name_dict = {}
        for index in range(readModeNum.value):
            name_buffer = ctypes.create_string_buffer(40)
            ret = self.qhyccddll.GetQHYCCDReadModeName(self.camhandle, index, name_buffer) # type: ignore
            if ret != 0:
                self._report_error(translations[self.language]['qhyccd_sdk']['get_readout_mode_name_failed'],sys._getframe().f_lineno)
                return
            result_name = name_buffer.value.decode("utf-8")
            self.readout_mode_name_dict[f"{result_name}"] = index   
        self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['get_readout_mode_name_success']}"})
        self.output_queue.put({"order":"readoutModeName_success","data":self.readout_mode_name_dict})
        return self.readout_mode_name_dict
        
    def get_stream_and_capture_mode(self,data):
        self.stream_and_capture_mode_dict = {}
        ret = self.qhyccddll.IsQHYCCDControlAvailable(self.camhandle, CONTROL_ID.CAM_LIVEVIDEOMODE.value) # type: ignore
        if ret != 0:    
            self._report_error(translations[self.language]['qhyccd_sdk']['camera_not_support_continuous_mode'],sys._getframe().f_lineno)
        else:
            self.stream_and_capture_mode_dict[f"{translations[self.language]['qhyccd_capture']['continuous_mode']}"] = 1
        ret = self.qhyccddll.IsQHYCCDControlAvailable(self.camhandle, CONTROL_ID.CAM_SINGLEFRAMEMODE.value) # type: ignore
        if ret != 0:
            self._report_error(translations[self.language]['qhyccd_sdk']['camera_not_support_single_frame_mode'],sys._getframe().f_lineno)
        else:
            self.stream_and_capture_mode_dict[f"{translations[self.language]['qhyccd_capture']['single_frame_mode']}"] = 0
        self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['get_stream_and_capture_mode_success']}"})
        self.output_queue.put({"order":"streamAndCaptureMode_success","data":self.stream_and_capture_mode_dict})
        return self.stream_and_capture_mode_dict
    
    def init_camera(self,data):
        camera_name,readout_mode,camera_mode = data
        self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['prepare_to_init_camera']}:{camera_name}..."})
        if self.camhandle > 0:
            self.close_camera(False)
        if self.qhyccddll is not None:
            self.releaseQHYCCDResource('')
            self.qhyccddll = None
        self.init_qhyccd_resource(self.qhyccd_resource_path,True)
        
        camera_id = self.camera_ids[camera_name]
        ret = self.qhyccddll.OpenQHYCCD(camera_id) # type: ignore
        if ret <= 0:
            self._report_error(translations[self.language]['qhyccd_sdk']['open_camera_failed'],sys._getframe().f_lineno)
        self.camhandle = ret
        
        readout_id = self.readout_mode_name_dict[readout_mode]
        ret = self.qhyccddll.SetQHYCCDReadMode(self.camhandle, readout_id) # type: ignore
        if ret != 0:
            self._report_error(translations[self.language]['qhyccd_sdk']['set_readout_mode_failed'],sys._getframe().f_lineno)
        self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['set_readout_mode_success']}:{readout_mode}"})
        readout_w = ctypes.c_uint32()
        readout_h = ctypes.c_uint32()
        ret = self.qhyccddll.GetQHYCCDReadModeResolution(self.camhandle, readout_id, byref(readout_w), byref(readout_h)) # type: ignore
        if ret != 0:
            self._report_error(translations[self.language]['qhyccd_sdk']['get_readout_mode_resolution_failed'],sys._getframe().f_lineno)
        self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['get_readout_mode_resolution_success']}:{readout_w.value}x{readout_h.value}"})
        stream_id = self.stream_and_capture_mode_dict[camera_mode]
        ret = self.qhyccddll.SetQHYCCDStreamMode(self.camhandle, stream_id) # type: ignore
        if ret != 0:
            self._report_error(translations[self.language]['qhyccd_sdk']['set_stream_mode_failed'],sys._getframe().f_lineno)
        self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['set_stream_mode_success']}:{camera_mode}"})
        ret = self.qhyccddll.InitQHYCCD(self.camhandle) # type: ignore
        if ret != 0:
            self._report_error(translations[self.language]['qhyccd_sdk']['init_camera_failed'],sys._getframe().f_lineno)
        self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['init_camera_success']}"})
        camera_param = {}
        # 判断相机是否是彩色相机
        camera_param['is_color'] = self.get_is_color_camera('')
        camera_param['config'] = self.get_camera_config('')
        camera_param['limit'] = self.get_limit_data('')
        camera_param['pixel_bin'] = self.get_camera_pixel_bin('')
        camera_param['effective_area'] = self.get_effective_area('')
        camera_param['depth'] = self.get_camera_depth('')
        camera_param['debayer'] = self.get_debayer_mode('')
        camera_param['temperature'] = self.get_is_temperature_control('')
        camera_param['CFW'] = self.get_cfw_info('')
        camera_param['auto_exposure'] = self.get_auto_exposure_is_available('')
        camera_param['auto_white_balance'] = self.get_auto_white_balance_is_available('')
        camera_param['readout_w'] = readout_w.value
        camera_param['readout_h'] = readout_h.value
        self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['init_camera_success']}:{camera_name}"})
        self.output_queue.put({"order":"initCamera_success","data":camera_param})
        
    def set_camera_depth(self, depth):
        ret = self.qhyccddll.SetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_TRANSFERBIT.value, depth)  # type: ignore
        if ret != 0:
            self._report_error(translations[self.language]['qhyccd_sdk']['set_camera_depth_failed'],sys._getframe().f_lineno)
        else:
            self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['set_camera_depth_success']}:{depth}"})
            self.output_queue.put({"order": "setDepth_success", "data": depth})
    
    def get_debayer_mode(self,data):
        self.debayer_mode = self.qhyccddll.IsQHYCCDControlAvailable(self.camhandle, CONTROL_ID.CAM_IS_COLOR.value) == 0 # type: ignore
        self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['get_debayer_mode_success']}:{self.debayer_mode}"})
        return self.debayer_mode

    def update_debayer_mode(self,debayer_mode):
        if self.qhyccddll.IsQHYCCDControlAvailable(self.camhandle, CONTROL_ID.CAM_IS_COLOR.value) == 0: # type: ignore
            ret = self.qhyccddll.SetQHYCCDDebayerOnOff(self.camhandle, debayer_mode) # type: ignore
            if ret != 0:
                self._report_error(translations[self.language]['qhyccd_sdk']['set_debayer_mode_failed'],sys._getframe().f_lineno)
            else:
                self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['set_debayer_mode_success']}:{debayer_mode}"})
                self.output_queue.put({"order":"setDebayerMode_success","data":f"{translations[self.language]['qhyccd_sdk']['set_debayer_mode_success']}:{debayer_mode}"})
            
    def close_camera(self,state):
        if self.camhandle == 0:
            self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['camera_not_open']}"})
            self.output_queue.put({"order":"closeCamera_success","data":None})
            return
        ret = self.qhyccddll.CloseQHYCCD(self.camhandle) # type: ignore
        if ret != 0:
            self._report_error(translations[self.language]['qhyccd_sdk']['close_camera_failed'],sys._getframe().f_lineno)
        else:
            self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['close_camera_success']}"})
            self.output_queue.put({"order":"closeCamera_success","data":None})
            self.camhandle = 0
                
    def get_is_color_camera(self,data):
        self.is_color_camera = False
        try:
            if not self.qhyccddll.IsQHYCCDControlAvailable(self.camhandle, CONTROL_ID.CAM_IS_COLOR.value): # type: ignore
                is_color_value = self.qhyccddll.GetQHYCCDParam(self.camhandle, CONTROL_ID.CAM_IS_COLOR.value) # type: ignore
                if is_color_value == 4294967295.0:
                    self._report_error(translations[self.language]['qhyccd_sdk']['get_camera_is_color_failed'],sys._getframe().f_lineno)
                    self.is_color_camera = self.is_color_camera_by_name(self.camera_name)
                else:
                    self.is_color_camera = not bool(is_color_value)
            else:
                self.is_color_camera = self.is_color_camera_by_name(self.camera_name)
        except Exception as e:
            self.is_color_camera = self.is_color_camera_by_name(self.camera_name)
        finally:
            self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['get_is_color_camera_success']}:{self.is_color_camera}"})
            return self.is_color_camera
            
    def is_color_camera_by_name(self, camera_name):
        """根据相机名字判断是否是彩色相机"""
        if camera_name and camera_name.split('-')[0].endswith('C'):
            return True
        return False

    def get_limit_data(self,data):
        self.limit_dict = {}
        # 设置曝光限制
        exposure = self.qhyccddll.GetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_EXPOSURE.value) # type: ignore
        min_data, max_data, step = self.getParamlimit(CONTROL_ID.CONTROL_EXPOSURE.value)
        self.limit_dict["exposure"] = (min_data, max_data,step,exposure)
        # 设置增益
        gain = self.qhyccddll.GetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_GAIN.value) # type: ignore
        min_data, max_data, step = self.getParamlimit(CONTROL_ID.CONTROL_GAIN.value)
        self.limit_dict["gain"] = (min_data, max_data,step,gain)
        # 设置偏移
        offset = self.qhyccddll.GetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_OFFSET.value) # type: ignore
        min_data, max_data, step = self.getParamlimit(CONTROL_ID.CONTROL_OFFSET.value)
        self.limit_dict["offset"] = (min_data, max_data,step,offset)
        # 设置USB宽带
        usb_traffic = self.qhyccddll.GetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_USBTRAFFIC.value) # type: ignore
        min_data, max_data, step = self.getParamlimit(CONTROL_ID.CONTROL_USBTRAFFIC.value)
        self.limit_dict["usb_traffic"] = (min_data, max_data,step,usb_traffic)
        # 设置白平衡限制
        if self.is_color_camera:
            wb_red = self.qhyccddll.GetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_WBR.value) # type: ignore
            min_data, max_data, step = self.getParamlimit(CONTROL_ID.CONTROL_WBR.value)
            self.limit_dict["wb_red"] = (min_data, max_data,step,wb_red)
            wb_green = self.qhyccddll.GetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_WBG.value) # type: ignore
            min_data, max_data, step = self.getParamlimit(CONTROL_ID.CONTROL_WBG.value)
            self.limit_dict["wb_green"] = (min_data, max_data,step,wb_green)        
            wb_blue = self.qhyccddll.GetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_WBB.value) # type: ignore
            min_data, max_data, step = self.getParamlimit(CONTROL_ID.CONTROL_WBB.value)
            self.limit_dict["wb_blue"] = (min_data, max_data,step,wb_blue)
        self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['get_limit_data_success']}"})
        return self.limit_dict
        
    def get_effective_area(self,data):
        # 获取相机有效扫描范围
        startX = ctypes.c_uint32()
        startY = ctypes.c_uint32()
        sizeX = ctypes.c_uint32()
        sizeY = ctypes.c_uint32()
        ret = self.qhyccddll.GetQHYCCDEffectiveArea(self.camhandle, byref(startX), byref(startY), byref(sizeX), byref(sizeY)) # type: ignore
        if ret != 0:
            self._report_error(translations[self.language]['qhyccd_sdk']['get_effective_area_failed'],sys._getframe().f_lineno)
            return
        self.effective_area_dict = {
            "startX":startX.value,
            "startY":startY.value,
            "sizeX":sizeX.value,
            "sizeY":sizeY.value
        }
        self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['get_effective_area_success']}:{self.effective_area_dict}"})
        return self.effective_area_dict
        
    def get_camera_config(self,data):
        """更新相机配置显示"""
        chipW = ctypes.c_double()  # 芯片宽度
        chipH = ctypes.c_double()  # 芯片高度
        imageW = ctypes.c_uint32()  # 图像宽度
        imageH = ctypes.c_uint32()  # 图像高度
        pixelW = ctypes.c_double()  # 像素宽度
        pixelH = ctypes.c_double()  # 像素高度
        imageB = ctypes.c_uint32()  # 图像位深度

        ret = self.qhyccddll.GetQHYCCDChipInfo(self.camhandle, byref(chipW), byref(chipH), byref(imageW), byref(imageH), byref(pixelW), # type: ignore
                                        byref(pixelH), byref(imageB)) # type: ignore
        if ret != 0:
            self._report_error(translations[self.language]['qhyccd_sdk']['get_camera_config_failed'],sys._getframe().f_lineno)
            return
        self.camera_config_dict = {
            "chipW":chipW.value,
            "chipH":chipH.value,
            "imageW":imageW.value,
            "imageH":imageH.value,
            "pixelW":pixelW.value,
            "pixelH":pixelH.value,
            "imageB":imageB.value
        }
        self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['get_camera_config_success']}:{self.camera_config_dict}"})
        return self.camera_config_dict
    
    def get_camera_pixel_bin(self,data):
        self.camera_pixel_bin_dict = {}
        for index, i in enumerate([CONTROL_ID.CAM_BIN1X1MODE.value, CONTROL_ID.CAM_BIN2X2MODE.value, CONTROL_ID.CAM_BIN3X3MODE.value, CONTROL_ID.CAM_BIN4X4MODE.value]):
            if self.qhyccddll.IsQHYCCDControlAvailable(self.camhandle, i) == 0: # type: ignore
                self.camera_pixel_bin_dict[f"{index+1}*{index+1}"] = (index+1,index+1)
        
        ret = self.qhyccddll.SetQHYCCDBinMode(self.camhandle, self.camera_pixel_bin_dict[list(self.camera_pixel_bin_dict.keys())[0]][0], self.camera_pixel_bin_dict[list(self.camera_pixel_bin_dict.keys())[0]][1]) # type: ignore
        if ret != 0:
            self._report_error(translations[self.language]['qhyccd_sdk']['set_camera_pixel_bin_failed'],sys._getframe().f_lineno)
        
        self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['get_camera_pixel_bin_success']}:{self.camera_pixel_bin_dict}"})
        return self.camera_pixel_bin_dict
        
    def set_camera_pixel_bin(self,pixel_bin):
        ret = self.qhyccddll.SetQHYCCDBinMode(self.camhandle, self.camera_pixel_bin_dict[pixel_bin][0], self.camera_pixel_bin_dict[pixel_bin][1]) # type: ignore
        if ret != 0:
            self._report_error(translations[self.language]['qhyccd_sdk']['set_camera_pixel_bin_failed'],sys._getframe().f_lineno)
        else:
            self.output_queue.put({"order":"setCameraPixelBin_success","data":f"{translations[self.language]['qhyccd_sdk']['set_camera_pixel_bin_success']}:{pixel_bin}"})
            self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['set_camera_pixel_bin_success']}:{pixel_bin}"})
            
    def update_resolution(self,data):
        startX,startY,sizeX,sizeY = data
        ret = self.qhyccddll.SetQHYCCDResolution(self.camhandle, startX, startY, sizeX, sizeY) # type: ignore
        if ret != 0:
            self._report_error(translations[self.language]['qhyccd_sdk']['set_resolution_failed'],sys._getframe().f_lineno)
        else:
            self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['set_resolution_success']}:{startX}*{startY}*{sizeX}*{sizeY}"})
  
    def getParamlimit(self,data_id,camhandle = None):
        if camhandle is None:
            camhandle = self.camhandle
        minValue = ctypes.c_double()  # 最小值
        maxValue = ctypes.c_double()  # 最大值
        step = ctypes.c_double() # 步长
        
        ret = self.qhyccddll.GetQHYCCDParamMinMaxStep(camhandle, data_id,byref(minValue),byref(maxValue),byref(step)) # type: ignore
        if ret == -1:
            self._report_error(translations[self.language]['qhyccd_sdk']['get_param_limit_failed'],sys._getframe().f_lineno)
        return minValue.value,maxValue.value,step.value

    def get_camera_depth(self,data):
        self.camera_depth_options = {}
        minValue,maxValue,step=self.getParamlimit(CONTROL_ID.CONTROL_TRANSFERBIT.value)
        for i in range(int(minValue),int(maxValue+1),int(step)):
            self.camera_depth_options[f"{i}bit"] = i
        updated_items = list(self.camera_depth_options.keys())  # 获取新的选项列表
        ret = self.qhyccddll.SetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_TRANSFERBIT.value, self.camera_depth_options[updated_items[0]]) # type: ignore
        if ret == -1:
            self._report_error(translations[self.language]['qhyccd_sdk']['set_camera_depth_failed'],sys._getframe().f_lineno)
            return -1
        self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['get_camera_depth_success']}:{self.camera_depth_options}"})
        return self.camera_depth_options

    def stop_live(self,data):
        ret = self.qhyccddll.StopQHYCCDLive(self.camhandle) # type: ignore
        if ret != 0:
            self._report_error(translations[self.language]['qhyccd_sdk']['stop_live_failed'],sys._getframe().f_lineno)
            return
        self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['stop_live_success']}"})

    def start_live(self,data):
        ret = self.qhyccddll.BeginQHYCCDLive(self.camhandle) # type: ignore
        if ret != 0:
            self._report_error(translations[self.language]['qhyccd_sdk']['start_live_failed'],sys._getframe().f_lineno)
            return
        self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['start_live_success']}"})

    def set_resolution(self,data):
        startX,startY,sizeX,sizeY = data
        ret = self.qhyccddll.SetQHYCCDResolution(self.camhandle, startX, startY, sizeX, sizeY) # type: ignore
        if ret == -1:
            self._report_error(translations[self.language]['qhyccd_sdk']['set_resolution_failed'],sys._getframe().f_lineno)
            return -1
        self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['set_resolution_success']}:{startX}*{startY}*{sizeX}*{sizeY}"})
        self.output_queue.put({"order":"setResolution_success","data":f"{startX}*{startY}*{sizeX}*{sizeY}"})

    def get_cfw_info(self,data):
        self.is_CFW_control = self.qhyccddll.IsQHYCCDCFWPlugged(self.camhandle) == 0 # type: ignore
        self.CFW_number_ids = {}
        if self.is_CFW_control:
            maxslot = self.qhyccddll.GetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_CFWSLOTSNUM.value) # type: ignore
            if maxslot > 0:
                for i in range(int(maxslot)):
                    # 使用 hex() 函数将十进制数转换为十六进制字符串
                    hex_str = hex(i)
                    # 移除 '0x' 前缀
                    hex_str = hex_str[2:]
                    self.CFW_number_ids[f"CFW:{i}"] = hex_str
        self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['get_cfw_info_success']}:{(self.is_CFW_control,self.CFW_number_ids)}"})
        return (self.is_CFW_control,self.CFW_number_ids)

    def get_planned_shooting_data(self,data):
        self.planned_shooting_data = {}
        camera_name = self.camera_ids
        # 获取相机名称
        for i in list(camera_name.keys()):
            plan_data = {}
            if i == self.camera_name:
                camhandle = self.camhandle
            else:
                camhandle = self.qhyccddll.OpenQHYCCD(camera_name[i]) # type: ignore
                if camhandle <= 0:
                    continue
            plan_data['ids'] = i
            
            # 设置读出模式
            readModeNum = ctypes.c_uint32()
            ret = self.qhyccddll.GetQHYCCDNumberOfReadModes(camhandle,byref(readModeNum)) # type: ignore
            if ret < 0:
                self._report_error(translations[self.language]['qhyccd_sdk']['get_readout_mode_num_failed'],sys._getframe().f_lineno)
  
            '''获取相机读取模式名称'''
            readout_mode_name_dict = {}
            for index in range(readModeNum.value):
                name_buffer = ctypes.create_string_buffer(40)
                ret = self.qhyccddll.GetQHYCCDReadModeName(camhandle, index, name_buffer) # type: ignore
                if ret != 0:
                    self._report_error(translations[self.language]['qhyccd_sdk']['get_readout_mode_name_failed'],sys._getframe().f_lineno)
                result_name = name_buffer.value.decode("utf-8")
                readout_mode_name_dict[f"{result_name}"] = index  
            plan_data['readout_mode'] = readout_mode_name_dict
            
            # 设置曝光限制
            exposure = self.qhyccddll.GetQHYCCDParam(camhandle, CONTROL_ID.CONTROL_EXPOSURE.value) # type: ignore
            min_data, max_data, step = self.getParamlimit(CONTROL_ID.CONTROL_EXPOSURE.value,camhandle)
            plan_data['exposure'] = [int(min_data),int(max_data),int(step),int(exposure)]
            # 设置增益
            gain = self.qhyccddll.GetQHYCCDParam(camhandle, CONTROL_ID.CONTROL_GAIN.value) # type: ignore
            min_data, max_data, step = self.getParamlimit(CONTROL_ID.CONTROL_GAIN.value,camhandle)
            plan_data['gain'] = [int(min_data),int(max_data),int(step),int(gain)]
            # 设置偏移
            offset = self.qhyccddll.GetQHYCCDParam(camhandle, CONTROL_ID.CONTROL_OFFSET.value) # type: ignore
            min_data, max_data, step = self.getParamlimit(CONTROL_ID.CONTROL_OFFSET.value,camhandle)
            plan_data['offset'] =[int(min_data),int(max_data),int(step),int(offset)]
            
            # 设置位数
            depth = self.qhyccddll.GetQHYCCDParam(camhandle, CONTROL_ID.CONTROL_TRANSFERBIT.value) # type: ignore
            min_data, max_data, step = self.getParamlimit(CONTROL_ID.CONTROL_TRANSFERBIT.value,camhandle)
            depth_options = {}
            for j in range(int(min_data),int(max_data+1),int(step)):
                depth_options[f"{j}bit"] = j
            plan_data['depth'] = depth_options
            
            # 判断滤镜轮是否可用
            is_CFW_control = self.qhyccddll.IsQHYCCDCFWPlugged(camhandle) == 0 # type: ignore
            CFW_number_ids = {}
            if is_CFW_control:
                maxslot = self.qhyccddll.GetQHYCCDParam(camhandle, CONTROL_ID.CONTROL_CFWSLOTSNUM.value) # type: ignore
                if maxslot > 0:
                    for j in range(int(maxslot)):
                        # 使用 hex() 函数将十进制数转换为十六进制字符串
                        hex_str = hex(j)
                        # 移除 '0x' 前缀
                        hex_str = hex_str[2:]
                        CFW_number_ids[f"CFW:{j}"] = hex_str
            if i != self.camera_name:
                ret = self.qhyccddll.CloseQHYCCD(camhandle) # type: ignore
                if ret<0:
                    continue
            plan_data['CFW'] = [is_CFW_control,CFW_number_ids]
            plan_data['connection'] = True
            if i == self.camera_name:
                plan_data['state'] = camhandle
            else:
                plan_data['state'] = 0
            self.planned_shooting_data[i] = plan_data
        self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['get_planned_shooting_data_success']}"})
        self.output_queue.put({"order":"getPlannedShootingData_success","data":self.planned_shooting_data})

    def run_plan(self,data):
        if data['name'] in self.camera_ids.keys():
            if data['name'] == self.camera_name:
                camhandle = self.camhandle
            else:
                camhandle = self.qhyccddll.OpenQHYCCD(self.camera_ids[data['name']]) # type: ignore
            if camhandle <= 0:
                self._report_error(translations[self.language]['qhyccd_sdk']['open_camera_failed'],sys._getframe().f_lineno)
                return
        self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['run_plan_success']}{translations[self.language]['qhyccd_sdk']['open_camera']}{data['name']}"})
        # 设置读出模式
        readout_mode_index = data['readout_mode']
        # 获取当前读出模式分辨率
        image_w = ctypes.c_uint32()
        image_h = ctypes.c_uint32()
        ret = self.qhyccddll.GetQHYCCDReadModeResolution(camhandle, readout_mode_index,byref(image_w), byref(image_h)) # type: ignore
        if ret != 0:
            self._report_error(translations[self.language]['qhyccd_sdk']['get_resolution_failed'],sys._getframe().f_lineno)
            return
        self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['run_plan_success']}{translations[self.language]['qhyccd_sdk']['get_resolution_success']}:{image_w.value}*{image_h.value}"})
        # 设置读出模式
        ret = self.qhyccddll.SetQHYCCDReadMode(camhandle, readout_mode_index) # type: ignore
        if ret != 0:
            self._report_error(translations[self.language]['qhyccd_sdk']['set_readout_mode_failed'],sys._getframe().f_lineno)
            return
        self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['run_plan_success']}{translations[self.language]['qhyccd_sdk']['set_readout_mode_success']}"})
        # 设置单帧模式
        ret = self.qhyccddll.SetQHYCCDStreamMode(camhandle, 0) # type: ignore
        if ret != 0:
            self._report_error(translations[self.language]['qhyccd_sdk']['set_stream_mode_failed'],sys._getframe().f_lineno)
            return
        self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['run_plan_success']}{translations[self.language]['qhyccd_sdk']['set_stream_mode_success']}"})
        # 初始化相机
        ret = self.qhyccddll.InitQHYCCD(camhandle) # type: ignore
        if ret != 0:
            self._report_error(translations[self.language]['qhyccd_sdk']['init_camera_failed'],sys._getframe().f_lineno)
            return
        self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['run_plan_success']}{translations[self.language]['qhyccd_sdk']['init_camera_success']}"})
        # 设置曝光    
        ret = self.qhyccddll.SetQHYCCDParam(camhandle, CONTROL_ID.CONTROL_EXPOSURE.value, data['exposure']) # type: ignore
        if ret != 0:
            self._report_error(translations[self.language]['qhyccd_sdk']['set_exposure_failed'],sys._getframe().f_lineno)
            return
        self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['run_plan_success']}{translations[self.language]['qhyccd_sdk']['set_exposure_success']}:{data['exposure']}us"})
        # 设置增益
        ret = self.qhyccddll.SetQHYCCDParam(camhandle, CONTROL_ID.CONTROL_GAIN.value, data['gain']) # type: ignore
        if ret != 0:
            self._report_error(translations[self.language]['qhyccd_sdk']['set_gain_failed'],sys._getframe().f_lineno)
            return
        self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['run_plan_success']}{translations[self.language]['qhyccd_sdk']['set_gain_success']}:{data['gain']}"})
        # 设置偏移
        ret = self.qhyccddll.SetQHYCCDParam(camhandle, CONTROL_ID.CONTROL_OFFSET.value, data['offset']) # type: ignore
        if ret != 0:
            self._report_error(translations[self.language]['qhyccd_sdk']['set_offset_failed'],sys._getframe().f_lineno)
            return
        self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['run_plan_success']}{translations[self.language]['qhyccd_sdk']['set_offset_success']}:{data['offset']}"})
        # 设置位数
        ret = self.qhyccddll.SetQHYCCDParam(camhandle, CONTROL_ID.CONTROL_TRANSFERBIT.value, data['depth']) # type: ignore
        if ret != 0:
            self._report_error(translations[self.language]['qhyccd_sdk']['set_depth_failed'],sys._getframe().f_lineno)
            return
        self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['run_plan_success']}{translations[self.language]['qhyccd_sdk']['set_depth_success']}:{data['depth']}"})
        if data['CFW'] != 'None':
            order = ord(data['CFW'])
            ret = self.qhyccddll.SetQHYCCDParam(camhandle, CONTROL_ID.CONTROL_CFWPORT.value, order) # type: ignore
            if ret != 0:
                self._report_error(translations[self.language]['qhyccd_sdk']['set_CFW_failed'],sys._getframe().f_lineno)
                return
            while True:
                is_exposing_done = self.qhyccddll.GetQHYCCDParam(camhandle, CONTROL_ID.CONTROL_CFWPORT.value) # type: ignore
                if is_exposing_done == order:
                    break
                else:
                    self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['run_plan_success']}{translations[self.language]['qhyccd_sdk']['set_CFW_moving']}:{is_exposing_done}"})
                    time.sleep(0.1)
        self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['run_plan_success']}{translations[self.language]['qhyccd_sdk']['set_CFW_success']}:{order}"})
        # 开始曝光
        ret = self.qhyccddll.ExpQHYCCDSingleFrame(camhandle) # type: ignore
        if ret != 0:
            self._report_error(translations[self.language]['qhyccd_sdk']['exposure_failed'],sys._getframe().f_lineno)
            return  # 如果启动失败，直接返回避免进一步阻塞
        self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['run_plan_success']}{translations[self.language]['qhyccd_sdk']['exposure_success']}"})
        image_w = image_w.value
        image_h = image_h.value
        image_c = 1
        image_b = data['depth']
        length = image_w * image_h * image_c * (image_b // 8)
        w = ctypes.c_uint32()
        h = ctypes.c_uint32()
        b = ctypes.c_uint32()
        c = ctypes.c_uint32()
  
        if data['depth'] == 16:
            imgdata = (ctypes.c_uint16 * length)()
            imgdata = ctypes.cast(imgdata, ctypes.POINTER(ctypes.c_ubyte))
        else:
            imgdata = (ctypes.c_uint8 * length)()
            imgdata = ctypes.cast(imgdata, ctypes.POINTER(ctypes.c_ubyte))

        ret = self.qhyccddll.GetQHYCCDSingleFrame(camhandle, byref(w), byref(h), byref(b), byref(c), imgdata) # type: ignore
        if ret != 0:
            self._report_error(translations[self.language]['qhyccd_sdk']['get_single_frame_failed'],sys._getframe().f_lineno)
            return  # 如果获取失败，直接返回避免进一步阻塞
        self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['run_plan_success']}{translations[self.language]['qhyccd_sdk']['get_single_frame_success']}"})
        imgdata = ctypes.cast(imgdata, ctypes.POINTER(ctypes.c_ubyte * length)).contents

        if c.value == 1:
            if data['depth'] == 16:
                imgdata_np = np.frombuffer(imgdata, dtype=np.uint16).reshape((h.value, w.value))
            else:
                imgdata_np = np.frombuffer(imgdata, dtype=np.uint8).reshape((h.value, w.value))
        elif c.value == 3:
            if data['depth'] == 16:
                imgdata_np = np.frombuffer(imgdata, dtype=np.uint16).reshape((h.value, w.value, c.value))
            else:
                imgdata_np = np.frombuffer(imgdata, dtype=np.uint8).reshape((h.value, w.value, c.value))
        else:
            raise ValueError("Unsupported number of channels")

        if data['name'] != self.camera_name:
            ret = self.qhyccddll.CloseQHYCCD(camhandle) # type: ignore
            if ret<0:
                self._report_error(translations[self.language]['qhyccd_sdk']['close_camera_failed'],sys._getframe().f_lineno)
                return
        self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['run_plan_success']}{translations[self.language]['qhyccd_sdk']['close_camera_success']}:{data['name']}"})
        self.output_queue.put({"order":"runPlan_success","data":imgdata_np})
        
    def get_is_temperature_control(self,data):
        self.has_temperature_control = self.qhyccddll.GetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_CURTEMP.value) != 0 # type: ignore
        self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['get_is_temperature_control_success']}: {self.has_temperature_control}"})
        return self.has_temperature_control
    
    def get_temperature(self,data):
        current_temp = self.qhyccddll.GetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_CURTEMP.value) # type: ignore
        self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['get_temperature_success']}: {current_temp}"})
        self.output_queue.put({"order":"getTemperature_success","data":current_temp})
        
    def set_temperature(self,data):
        ret = self.qhyccddll.SetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_COOLER.value, data) # type: ignore
        if ret != 0:
            self._report_error(translations[self.language]['qhyccd_sdk']['set_temperature_failed'],sys._getframe().f_lineno)
            return
        self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['set_temperature_success']}: {data}"})
        
    def get_auto_exposure_is_available(self,data):
        self.auto_exposure_is_available = self.qhyccddll.IsQHYCCDControlAvailable(self.camhandle, CONTROL_ID.CONTROL_AUTOEXPOSURE.value) == 0 # type: ignore
        self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['get_auto_exposure_is_available_success']}: {self.auto_exposure_is_available}"})
        return self.auto_exposure_is_available

    def get_auto_exposure_limits(self,data):
        exposure_mode_dict = {}
        all_exposure_mode_dict = {translations[self.language]['auto_exposure']['mode_off']:0,  # 关闭自动曝光
            translations[self.language]['auto_exposure']['mode_gain_only']:1,  # 仅调节gain模式
            translations[self.language]['auto_exposure']['mode_exp_only']:2,  # 仅调节exp模式
            translations[self.language]['auto_exposure']['mode_hybrid']:3,  # 混合调节模式
            translations[self.language]['auto_exposure']['mode_all_day']:4  # 全天模式(暂未实现)
        }
        # 获取曝光模式的参数限制
        min, max, step = self.getParamlimit(CONTROL_ID.CONTROL_AUTOEXPOSURE.value)
        # 遍历现有的曝光模式，检查它们是否在允许的范围内
        for mode_text, mode_value in list(all_exposure_mode_dict.items()):
            if not (min <= mode_value <= max):
                # 如果模式值不在范围内，从字典和下拉框中移除该模式
                all_exposure_mode_dict.pop(mode_text)
        exposure_mode_dict['mode'] = all_exposure_mode_dict
        # 获取增益限制
        min, max, step = self.getParamlimit(CONTROL_ID.CONTROL_AUTOEXPgainMax.value)
        gain_data = self.qhyccddll.GetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_AUTOEXPgainMax.value) # type: ignore
        exposure_mode_dict['gain'] = [min, max, step,gain_data]
        # 获取曝光时间限制
        min, max, step = self.getParamlimit(CONTROL_ID.CONTROL_AUTOEXPexpMaxMS.value)
        exposure_data = self.qhyccddll.GetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_AUTOEXPexpMaxMS.value) # type: ignore
        exposure_mode_dict['exposure'] = [min, max, step,exposure_data]
        self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['get_auto_exposure_limits_success']}: {exposure_mode_dict}"})
        self.output_queue.put({"order":"getAutoExposureLimits_success","data":exposure_mode_dict})
    
    def set_auto_exposure(self,data):
        mode, gain, exposure = data
        if mode == 0:
            if self.qhyccddll.GetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_AUTOEXPOSURE.value) != mode: # type: ignore
                ret = self.qhyccddll.SetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_AUTOEXPOSURE.value, mode) # type: ignore
                if ret != 0:
                    self._report_error(translations[self.language]['qhyccd_sdk']['set_auto_exposure_failed'],sys._getframe().f_lineno)
                    return
        elif mode == 1:
            if self.qhyccddll.GetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_AUTOEXPOSURE.value) != 1: # type: ignore
                ret = self.qhyccddll.SetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_AUTOEXPOSURE.value, 1.0) # type: ignore
                if ret != 0:
                    self._report_error(translations[self.language]['qhyccd_sdk']['set_auto_exposure_failed'],sys._getframe().f_lineno)
                    return
            gain_max = int(gain)
            ret = self.qhyccddll.SetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_AUTOEXPgainMax.value, gain_max) # type: ignore
            if ret != 0:
                self._report_error(translations[self.language]['qhyccd_sdk']['set_gain_failed'],sys._getframe().f_lineno)
                return
        elif mode == 2:
            if self.qhyccddll.GetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_AUTOEXPOSURE.value) != 2: # type: ignore
                ret = self.qhyccddll.SetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_AUTOEXPOSURE.value, 2.0) # type: ignore
                if ret != 0:
                    self._report_error(translations[self.language]['qhyccd_sdk']['set_auto_exposure_failed'],sys._getframe().f_lineno)
                    return
            exposure_time = int(exposure)
            ret = self.qhyccddll.SetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_AUTOEXPexpMaxMS.value, exposure_time) # type: ignore
            if ret != 0:
                self._report_error(translations[self.language]['qhyccd_sdk']['set_exposure_failed'],sys._getframe().f_lineno)
                return
        elif mode == 3:
            if self.qhyccddll.GetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_AUTOEXPOSURE.value) != 3: # type: ignore
                ret = self.qhyccddll.SetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_AUTOEXPOSURE.value, 3.0) # type: ignore
                if ret != 0:
                    self._report_error(translations[self.language]['qhyccd_sdk']['set_auto_exposure_failed'],sys._getframe().f_lineno)
                    return
            gain_max = int(gain)
            ret = self.qhyccddll.SetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_AUTOEXPgainMax.value, gain_max) # type: ignore
            if ret != 0:
                self._report_error(translations[self.language]['qhyccd_sdk']['set_gain_failed'],sys._getframe().f_lineno)
                return
            exposure_time = int(exposure)
            ret = self.qhyccddll.SetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_AUTOEXPexpMaxMS.value, exposure_time) # type: ignore
            if ret != 0:
                self._report_error(translations[self.language]['qhyccd_sdk']['set_exposure_failed'],sys._getframe().f_lineno)
                return
        elif mode == 4:
            pass
        self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['set_auto_exposure_success']}: {mode}"})
        self.output_queue.put({"order":"setAutoExposure_success","data":mode})
    
    def get_exposure_value(self,data):
        exposure_value = self.qhyccddll.GetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_EXPOSURE.value) # type: ignore
        self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['get_exposure_value_success']}: {exposure_value}"})
        self.output_queue.put({"order":"getExposureValue_success","data":exposure_value})
        
    def get_auto_white_balance_is_available(self,data):
        self.auto_white_balance_is_available = self.qhyccddll.IsQHYCCDControlAvailable(self.camhandle, CONTROL_ID.CONTROL_AUTOWHITEBALANCE.value) == 0 # type: ignore
        self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['get_auto_white_balance_is_available_success']}: {self.auto_white_balance_is_available}"})
        self.output_queue.put({"order":"getAutoWhiteBalanceIsAvailable_success","data":self.auto_white_balance_is_available})
        
    def set_auto_white_balance(self,data):
        auto_white_balance_data = self.qhyccddll.GetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_AUTOWHITEBALANCE.value) # type: ignore
        if auto_white_balance_data != data:
            ret = self.qhyccddll.SetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_AUTOWHITEBALANCE.value, data) # type: ignore
            if ret != 0:
                self._report_error(translations[self.language]['qhyccd_sdk']['set_auto_white_balance_failed'],sys._getframe().f_lineno)
                return
        self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['set_auto_white_balance_success']}: {data}"})
        self.output_queue.put({"order":"setAutoWhiteBalance_success","data":data})

    def get_auto_white_balance_values(self,data):
        wb_red = self.qhyccddll.GetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_WBR.value) # type: ignore
        wb_green = self.qhyccddll.GetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_WBG.value) # type: ignore
        wb_blue = self.qhyccddll.GetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_WBB.value) # type: ignore
        auto_white_balance_is_running = self.qhyccddll.GetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_AUTOWHITEBALANCE.value) == 0 # type: ignore
        self.output_queue.put({"order":"autoWhiteBalanceComplete","data":(wb_red, wb_green, wb_blue,auto_white_balance_is_running)})
       
    def set_exposure_time(self,data):
        ret = self.qhyccddll.SetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_EXPOSURE.value, data) # type: ignore
        if ret == 0:
            self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['set_exposure_time_success']}: {data}"})
            self.output_queue.put({"order":"setExposureTime_success","data":data})
        else:
            self._report_error(translations[self.language]['qhyccd_sdk']['set_exposure_time_failed'],sys._getframe().f_lineno)
            return
        
    def set_gain(self,data):
        ret = self.qhyccddll.SetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_GAIN.value, data) # type: ignore
        if ret == 0:
            self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['set_gain_success']}: {data}"})
            self.output_queue.put({"order":"setGain_success","data":data})
        else:
            self._report_error(translations[self.language]['qhyccd_sdk']['set_gain_failed'],sys._getframe().f_lineno)
            return
    
    def set_offset(self,data):
        ret = self.qhyccddll.SetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_OFFSET.value, data) # type: ignore
        if ret == 0:    
            self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['set_offset_success']}: {data}"})
            self.output_queue.put({"order":"setOffset_success","data":data})
        else:
            self._report_error(translations[self.language]['qhyccd_sdk']['set_offset_failed'],sys._getframe().f_lineno)
            return

    def set_usb_traffic(self,data):
        ret = self.qhyccddll.SetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_USBTRAFFIC.value, data) # type: ignore
        if ret == 0:
            self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['set_usb_traffic_success']}: {data}"})
            self.output_queue.put({"order":"setUsbTraffic_success","data":data})
        else:
            self._report_error(translations[self.language]['qhyccd_sdk']['set_usb_traffic_failed'],sys._getframe().f_lineno)
            return
            
    def set_white_balance(self,data):
        red, green, blue = data
        ret = self.qhyccddll.SetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_WBR.value, red) # type: ignore
        if ret != 0:        
            self._report_error(f"{translations[self.language]['debug']['set_qhyccd_red_gain_failed']}: {ret}",sys._getframe().f_lineno)
            red = -1
        ret = self.qhyccddll.SetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_WBG.value, green) # type: ignore
        if ret != 0:
            self._report_error(f"{translations[self.language]['debug']['set_qhyccd_green_gain_failed']}: {ret}",sys._getframe().f_lineno)
            green = -1
        ret = self.qhyccddll.SetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_WBB.value, blue) # type: ignore
        if ret != 0:
            self._report_error(f"{translations[self.language]['debug']['set_qhyccd_blue_gain_failed']}: {ret}",sys._getframe().f_lineno)
            blue = -1
        self.output_queue.put({"order":"tip","data":f"{translations[self.language]['qhyccd_sdk']['set_white_balance_success']}: r={red}, g={green}, b={blue}"})
        self.output_queue.put({"order":"setWhiteBalance_success","data":(red, green, blue)})
            
    def set_CFW_filter(self, data):
        # 创建并启动线程
        thread = threading.Thread(target=self._set_CFW_filter_thread, args=(data,))
        thread.start()

    def _set_CFW_filter_thread(self, data):
        CFW_id = data
        order = self.CFW_number_ids[CFW_id].encode('utf-8')
        ret = self.qhyccddll.SendOrder2QHYCCDCFW(self.camhandle, c_char_p(order), len(order))  # type: ignore
        if ret == 0:
            while True:
                is_moving_done = self.qhyccddll.GetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_CFWPORT.value)  # type: ignore
                if is_moving_done == ord(order):
                    break
                else:
                    time.sleep(0.1)
            self.output_queue.put({"order": "tip", "data": f"{translations[self.language]['qhyccd_sdk']['set_CFW_filter_success']}: {CFW_id}"})
            self.output_queue.put({"order": "setCFWFilter_success", "data": CFW_id})
        else:
            self._report_error(translations[self.language]['qhyccd_sdk']['set_CFW_filter_failed'], sys._getframe().f_lineno)
    
    def start_preview(self, data):
        w, h, c, depth, exposure_time, gain, offset, debayer_mode = data
        self.preview_thread = PreviewThread(self.camhandle, self.qhyccddll, w, h, c, depth, self.shm1, self.shm2, self.output_queue,self.language)
        self.preview_thread.handle_start()
        
    def stop_preview(self,data):
        if self.preview_thread is not None:
            self.preview_thread.handle_stop()
        
    def update_preview_pause(self, data):
        if self.preview_thread is not None:
            self.preview_thread.set_pause(data) 
            
    def update_shared_image_data(self, data):
        w, h, c, b = data
        if self.preview_thread is not None:
            self.preview_thread.update_image_parameters(w, h, c, b)
        
    def clear_fps_data(self,data):
        if self.preview_thread is not None: 
            self.preview_thread.update_fps()
            
    def single_capture(self,data):
        image_w, image_h, image_c, camera_bit = data
        self.capture_thread = CaptureThread(self.camhandle, self.qhyccddll, image_w, image_h, image_c, camera_bit, self.output_queue, self.language)
        self.capture_thread.start()
        
    def get_single_capture_status(self,data):
        elapsed_time = self.qhyccddll.GetQHYCCDExposureRemaining(self.camhandle) # type: ignore
        if elapsed_time == -1:
            elapsed_time = 0
        self.output_queue.put({"order":"singleCapture_status","data":elapsed_time})
        
    def cancel_capture(self,data):
        self.qhyccddll.CancelQHYCCDExposingAndReadout(self.camhandle) # type: ignore
        
    def set_image_buffer(self,data):
        self.shm1 = shared_memory.SharedMemory(name=data['shm1'])
        self.shm2 = shared_memory.SharedMemory(name=data['shm2'])