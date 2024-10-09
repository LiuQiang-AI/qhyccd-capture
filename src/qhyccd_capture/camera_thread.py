from PyQt5.QtCore import QThread, pyqtSignal
import ctypes
from ctypes import *
import warnings
from .language import translations

class CameraConnectionThread(QThread):
    update_status_signal = pyqtSignal(str)
    handle_signal = pyqtSignal(str)  # 定义一个新的信号用于发送句柄
    get_read_mode_signal = pyqtSignal(dict)  # 定义一个新的信号用于发送读取模式的字典
    already_connected_signal = pyqtSignal(bool,int)  # 定义一个新的信号用于发送相机是否已经连接
    already_disconnected_signal = pyqtSignal(bool)  # 定义一个新的信号用于发送相机是否已经断开

    def __init__(self, qhyccddll,camera_id, read_mode, stream_mode, language, parent=None):
        super().__init__(parent)
        self.qhyccddll = qhyccddll
        self.camera_id = camera_id
        self.camhandle = 0
        self.language = language
        self.read_mode = read_mode
        self.stream_mode = stream_mode
        
    def run(self):
        self.update_status_signal.emit(translations[self.language]['camera_thread']['start_connect'])
        self.camhandle = self.qhyccddll.OpenQHYCCD(self.camera_id)
        # print(f'OpenQHYCCD() ret = {self.camhandle}, camera_id = {self.camera_id},self.camhandle = {hex(self.camhandle)}')
        if self.camhandle <= 0:
            self.update_status_signal.emit(translations[self.language]['camera_thread']['camera_connected_failed'])
            self.already_connected_signal.emit(False)  # 发送相机未连接的信号
            return
        else:
            self.update_status_signal.emit(translations[self.language]['camera_thread']['camera_connected'])
            self.handle_signal.emit(str(self.camhandle))  # 发送句柄信息
        
        # 获取相机读取模式数量
        self.update_status_signal.emit(translations[self.language]['camera_thread']['get_qhyccd_number_of_read_modes'])
        readModeNum = ctypes.c_uint32()
        ret = self.qhyccddll.GetQHYCCDNumberOfReadModes(self.camhandle,byref(readModeNum))
        if ret < 0:
            warnings.warn(f"{translations[self.language]['camera_thread']['get_qhyccd_number_of_read_modes_failed']}: {ret}")
            self.update_status_signal.emit(translations[self.language]['camera_thread']['get_qhyccd_number_of_read_modes_failed'])
            self.already_connected_signal.emit(False)  # 发送相机未连接的信号
            return
        else:
            self.update_status_signal.emit(translations[self.language]['camera_thread']['get_qhyccd_number_of_read_modes_success'])
        
        read_mode_name_dict = {}
        for index in range(readModeNum.value):
            name_buffer = ctypes.create_string_buffer(40)
            ret = self.qhyccddll.GetQHYCCDReadModeName(self.camhandle, index, name_buffer)
            if ret != 0:
                warnings.warn(f"{translations[self.language]['debug']['get_qhyccd_read_mode_name_failed']}: {ret}")
            result_name = name_buffer.value.decode("utf-8")

            read_mode_name_dict[f"{result_name}"] = index    
        self.get_read_mode_signal.emit(read_mode_name_dict)
        
        self.update_status_signal.emit(translations[self.language]['camera_thread']['set_qhyccd_read_mode'])
        ret = self.qhyccddll.SetQHYCCDReadMode(self.camhandle, self.read_mode)
        if ret != 0:
            warnings.warn(f"{translations[self.language]['debug']['set_qhyccd_read_mode_failed']}: {ret}")
            self.update_status_signal.emit(translations[self.language]['camera_thread']['set_qhyccd_read_mode_failed'])
            self.already_connected_signal.emit(False)  # 发送相机未连接的信号
            return
        else:
            self.update_status_signal.emit(translations[self.language]['camera_thread']['set_qhyccd_read_mode_success'])
        
        self.update_status_signal.emit(translations[self.language]['camera_thread']['set_qhyccd_stream_mode'])
        ret = self.qhyccddll.SetQHYCCDStreamMode(self.camhandle, self.stream_mode)
        if ret != 0:
            warnings.warn(f"{translations[self.language]['debug']['set_qhyccd_stream_mode_failed']}: {ret}")
            self.update_status_signal.emit(translations[self.language]['camera_thread']['set_qhyccd_stream_mode_failed'])
            self.already_connected_signal.emit(False)  # 发送相机未连接的信号
            return
        else:
            self.update_status_signal.emit(translations[self.language]['camera_thread']['set_qhyccd_stream_mode_success'])
        
        self.update_status_signal.emit(translations[self.language]['camera_thread']['init_camera'])
        ret = self.qhyccddll.InitQHYCCD(self.camhandle)
        if ret != 0:
            warnings.warn(f"{translations[self.language]['debug']['init_camera_failed']}: {ret}")
            self.update_status_signal.emit(translations[self.language]['camera_thread']['init_camera_failed'])
            self.already_connected_signal.emit(False)  # 发送相机未连接的信号
            return
        else:
            self.update_status_signal.emit(translations[self.language]['camera_thread']['init_camera_success'])
        self.already_connected_signal.emit(True,self.read_mode)  # 发送相机已经连接的信号
        
    def disconnect(self):
        # 断开相机的逻辑
        self.update_status_signal.emit(translations[self.language]['camera_thread']['close_camera'])
        
        ret = self.qhyccddll.CloseQHYCCD(self.camhandle)
        if ret != 0:
            warnings.warn(f"{translations[self.language]['debug']['close_camera_failed']}: {ret}")
            self.update_status_signal.emit(translations[self.language]['camera_thread']['close_camera_failed'])
            self.already_disconnected_signal.emit(False)  # 发送相机未断开的信号
            return
        else:
            self.update_status_signal.emit(translations[self.language]['camera_thread']['close_camera_success'])
        
        # 释放资源
        self.update_status_signal.emit(translations[self.language]['camera_thread']['release_camera_resource'])
        ret = self.qhyccddll.ReleaseQHYCCDResource()
        if ret != 0:
            warnings.warn(f"{translations[self.language]['debug']['release_camera_resource_failed']}: {ret}")
            self.update_status_signal.emit(translations[self.language]['camera_thread']['release_camera_resource_failed'])
            self.already_disconnected_signal.emit(False)  # 发送相机未断开的信号
            return  
        else:
            self.update_status_signal.emit(translations[self.language]['camera_thread']['release_camera_resource_success'])
        self.already_disconnected_signal.emit(True)  # 发送相机已经断开的信号
        self.quit()