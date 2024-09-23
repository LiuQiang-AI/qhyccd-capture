from PyQt5.QtWidgets import *
'''(QWidget, QVBoxLayout, QPushButton, QLabel, QComboBox, QHBoxLayout, QGroupBox, QFormLayout, QSpinBox, QSlider, QCheckBox,QLineEdit)'''
from PyQt5.QtCore import Qt,pyqtSlot, QTimer, QThread, pyqtSignal
from PyQt5.QtGui import QIcon
from napari_plugin_engine import napari_hook_implementation
from napari.layers import Shapes
import numpy as np
import ctypes
from ctypes import *
import os
import warnings
from datetime import datetime
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import cv2
import time
from qtrangeslider import QRangeSlider
from .control_id import CONTROL_ID
from .previewThread import PreviewThread
from .captureStatus import CaptureStatusThread
from .captureFrame import CaptureThread
from .save_video import SaveThread
from .histogramWidget import HistogramWidget
from .memory_updated import MemoryMonitorThread
import queue

class CameraControlWidget(QWidget):
    def __init__(self, napari_viewer):
        super().__init__()
        
        ''' 相机配置参数 '''
        self.init_state = False
        self.camera_state = False
        
        self.system_name = os.name
        
        self.viewer = napari_viewer
        self.contrast_limits_connection = None
        # self.viewer.events.layers.connect(self.on_layer_selection_change)
        
        self.histogram_window = None  # 用于存储直方图窗口

        self.camera = None
        self.camera_name = None
        
        self.roi_layer = None
        self.roi_created = False
        
        self.camhandle = 0
        self.qhyccddll = None
        

        self.camera_W = 0
        self.camera_H = 0
        self.camera_bit = 0
        
        self.bin = [1,1]
        
        self.image_w = 0
        self.image_h = 0
        
        self.camera_ids = {}
        
        self.buffer_queue = queue.Queue()  # 用于保存图像数据的队列
        
        self.last_update_time = None
        self.last_histogram_update_time = None
        self.is_recording = False

        '''主布局设置'''
        # 创建一个滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QWidget()

        # 将原有的布局添加到滚动区域的内容布局中
        layout = QVBoxLayout(scroll_content)
    
        scroll_area.setWidget(scroll_content)
        
        
        '''相机连接设置布局'''
        self.connect_box = QGroupBox('连接设置')
        start_setting_layout = QFormLayout()
    
        self.qhyccd_path_label = QLabel()
        self.qhyccd_path_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.qhyccd_path_label.setWordWrap(True)  # 允许文本换行

        self.select_qhyccd_path_button = QPushButton('SDK')
        self.select_qhyccd_path_button.clicked.connect(self.select_qhyccd_path)

        self.init_qhyccd_button = QPushButton('初始化')
        self.init_qhyccd_button.clicked.connect(self.init_qhyccd_with_path)

        # 创建水平布局
        h_layout = QHBoxLayout()
        h_layout.addWidget(self.qhyccd_path_label)
        h_layout.addWidget(self.select_qhyccd_path_button)
        h_layout.addWidget(self.init_qhyccd_button)
        
        start_setting_layout.addRow(h_layout)
        # 相机选择
        self.camera_selector = QComboBox()

        start_setting_layout.addRow(QLabel('选择相机:'),self.camera_selector)
        
        # 相机模式选择
        self.camera_mode = '单帧模式'
        self.camera_mode_ids = {'单帧模式':0,'连续模式':1}
        self.camera_mode_selector = QComboBox()
        self.camera_mode_selector.addItems(list(self.camera_mode_ids.keys()))
        self.camera_mode_selector.currentIndexChanged.connect(self.on_camera_mode_changed)
        start_setting_layout.addRow(QLabel('选择相机模式:'),self.camera_mode_selector)
        
        # 连接和断开按钮
        grid_layout = QGridLayout()
        self.connect_button = QPushButton('连接')
        self.disconnect_button = QPushButton('断开')
        self.reset_camera_button = QPushButton('重新扫描相机')
        
        self.connect_button.clicked.connect(self.connect_camera)
        self.disconnect_button.clicked.connect(self.disconnect_camera)
        self.reset_camera_button.clicked.connect(self.read_camera_name)
        
        grid_layout.addWidget(self.connect_button,0,0)
        grid_layout.addWidget(self.disconnect_button,0,1)
        grid_layout.addWidget(self.reset_camera_button,0,2)
        start_setting_layout.addRow(grid_layout)
        grid_layout = QGridLayout()
        # 相机配置显示
        self.config_label = QLabel('未连接')
        self.config_label.setStyleSheet("color: red;")  # 设置字体颜色为红色
        grid_layout.addWidget(self.config_label,0,0)
        
        self.fps_label = QLabel('FPS: ~')
        self.fps_label.setVisible(False)
        grid_layout.addWidget(self.fps_label,0,1)
        
        self.memory_label = QLabel('内存:')
        grid_layout.addWidget(self.memory_label,0,2)
        
        self.memory_progress_bar = QProgressBar(self)  # 创建进度条控件
        self.memory_progress_bar.setRange(0, 100)  # 设置进度条范围（0% 到 100%）
        self.memory_progress_bar.setValue(0)
        
        grid_layout.addWidget(self.memory_progress_bar,0,3)
        start_setting_layout.addRow(grid_layout)
        
        self.state_label = QLabel()
        start_setting_layout.addRow(QLabel("状态:"),self.state_label)
        
        # 内存监控
        self.memory_monitor_thread = MemoryMonitorThread()
        self.memory_monitor_thread.memory_updated.connect(self.update_memory_progress)
        self.memory_monitor_thread.start()
        
        # 区显示开关
        grid_layout = QGridLayout()
        
        self.show_settings_checkbox = QPushButton()
        self.show_settings_checkbox.setIcon(QIcon('src/qhyccd_capture/icon/camera_icon.png'))  # 设置图标路径
        self.show_settings_checkbox.setToolTip('显示相机设置')  # 设置提示文本

        self.show_control_checkbox = QPushButton()
        self.show_control_checkbox.setIcon(QIcon('src/qhyccd_capture/icon/instagram_icon.png'))  # 设置图标路径
        self.show_control_checkbox.setToolTip('显示拍摄控制')

        self.show_image_control_checkbox = QPushButton()
        self.show_image_control_checkbox.setIcon(QIcon('src/qhyccd_capture/icon/film_icon.png'))  # 设置图标路径
        self.show_image_control_checkbox.setToolTip('显示图像控制')

        self.show_temperature_control_checkbox = QPushButton()
        self.show_temperature_control_checkbox.setIcon(QIcon('src/qhyccd_capture/icon/thermometer_icon.png'))  # 设置图标路径
        self.show_temperature_control_checkbox.setToolTip('显示温度控制')

        self.show_CFW_control_checkbox = QPushButton()
        self.show_CFW_control_checkbox.setIcon(QIcon('src/qhyccd_capture/icon/toggle_right_icon.png'))  # 设置图标路径
        self.show_CFW_control_checkbox.setToolTip('显示滤镜轮控制')

        self.show_video_control_checkbox = QPushButton()
        self.show_video_control_checkbox.setIcon(QIcon('src/qhyccd_capture/icon/video_icon.png'))  # 设置图标路径
        self.show_video_control_checkbox.setToolTip('显示录像控制')
        
        self.show_settings_checkbox.clicked.connect(lambda: self.toggle_settings_box())
        self.show_control_checkbox.clicked.connect(lambda: self.toggle_control_box())
        self.show_image_control_checkbox.clicked.connect(lambda: self.toggle_image_control_box())
        self.show_temperature_control_checkbox.clicked.connect(lambda: self.toggle_temperature_control_box())
        self.show_CFW_control_checkbox.clicked.connect(lambda: self.toggle_CFW_control_box())
        self.show_video_control_checkbox.clicked.connect(lambda: self.toggle_video_control_box())
        
        
        grid_layout.addWidget(self.show_settings_checkbox,1,0)
        grid_layout.addWidget(self.show_control_checkbox,1,1)
        grid_layout.addWidget(self.show_image_control_checkbox,1,2)
        grid_layout.addWidget(self.show_video_control_checkbox,1,3)
        grid_layout.addWidget(self.show_temperature_control_checkbox,1,4)
        grid_layout.addWidget(self.show_CFW_control_checkbox,1,5)
        start_setting_layout.addRow(grid_layout)
        
        # 将 start_setting_layout 包装在一个 QWidget 中
        self.connect_box.setLayout(start_setting_layout)
        layout.addWidget(self.connect_box)
        
        
        '''相机配置设置布局'''
        self.settings_box = QGroupBox('相机设置')
        settings_layout = QFormLayout()

        # 读出模式选择框
        self.camera_read_mode_ids= {}
        self.readout_mode_selector = QComboBox()
        self.readout_mode_selector.addItems(list(self.camera_read_mode_ids.keys()))  # 示例项
        self.readout_mode_selector.currentIndexChanged.connect(self.on_readout_mode_changed)
        settings_layout.addRow(QLabel('读出模式:'), self.readout_mode_selector)

        # 像素合并Bin选择框
        self.camera_pixel_bin = {'1*1':[1,1],'2*2':[2,2],'3*3':[3,3],'4*4':[4,4]}
        self.pixel_bin_selector = QComboBox()
        self.pixel_bin_selector.addItems(list(self.camera_pixel_bin.keys()))  # 示例项
        self.pixel_bin_selector.currentIndexChanged.connect(self.on_pixel_bin_changed)
        settings_layout.addRow(QLabel('像素合并 Bin:'), self.pixel_bin_selector)

        # 图像位深度选择框
        self.camera_depth_options = {}
        self.depth_selector = QComboBox()  # 创建图像位深度选择框
        self.depth_selector.addItems(list(self.camera_depth_options.keys()))  
        self.depth_selector.currentIndexChanged.connect(self.on_depth_changed)
        self.depth_name = QLabel("图像位深度:")
        settings_layout.addRow(self.depth_name, self.depth_selector)
        
        # 分辨率选择框
        # 变量定义
        self.x = QSpinBox()
        self.y = QSpinBox()
        self.w = QSpinBox()
        self.h = QSpinBox()
        self.set_resolution_button = QPushButton('设置分辨率')
        self.set_original_resolution_button = QPushButton('还原')
        self.set_original_resolution_button.setToolTip('还原为相机初始分辨率')
        self.show_roi_button = QPushButton('ROI')
        self.show_roi_button.setToolTip('ROI (鼠标第一次点击确定起始点，第二次点击确定终止点)')

        # 布局设置
        grid_layout = QGridLayout()
        grid_layout.addWidget(QLabel('x:'),0,0)
        grid_layout.addWidget(self.x,0,1)
        grid_layout.addWidget(QLabel('y:'),0,2)
        grid_layout.addWidget(self.y,0,3)
        grid_layout.addWidget(QLabel('w:'),1,0)
        grid_layout.addWidget(self.w,1,1)
        grid_layout.addWidget(QLabel('h:'),1,2)
        grid_layout.addWidget(self.h,1,3)
        
        # 创建一个QWidget容器来放置Grid布局
        grid_widget = QWidget()
        grid_widget.setLayout(grid_layout)
        
        settings_layout.addRow(grid_widget)
        
        # 创建一个水平布局
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.show_roi_button)
        button_layout.addWidget(self.set_resolution_button)
        button_layout.addWidget(self.set_original_resolution_button)

        # 将水平布局添加到 QFormLayout
        settings_layout.addRow(button_layout)

        # 连接信号和槽
        self.set_resolution_button.clicked.connect(self.on_set_resolution_clicked)
        self.set_original_resolution_button.clicked.connect(self.on_set_original_resolution_clicked)
        self.show_roi_button.clicked.connect(self.show_roi_component)

        # 初始化拖动框
        self.shapes_layer = None

        self.settings_box.setLayout(settings_layout)

        # 主布局
        layout.addWidget(self.settings_box)
        


        '''拍摄控制设置布局'''
        self.control_box = QGroupBox('拍摄控制')
        control_layout = QFormLayout()
        
        self.exposure_time = QDoubleSpinBox()  # 修改为 QDoubleSpinBox
        self.exposure_time.setSuffix(' ms')  # 设置单位为毫秒
        self.exposure_time.setDecimals(3)  # 保留三位小数
        self.exposure_time.valueChanged.connect(self.update_exposure_time)
        control_layout.addRow(QLabel('曝光时间:'), self.exposure_time)
        
        # 增益设置
        self.gain = QDoubleSpinBox()
        self.gain.setSuffix(' dB')
        self.gain.valueChanged.connect(self.update_gain)
        control_layout.addRow(QLabel('增益:'), self.gain)

        # 偏移量设置
        self.offset = QDoubleSpinBox()
        self.offset.setSuffix(' units')
        self.offset.valueChanged.connect(self.update_offset)
        control_layout.addRow(QLabel('偏移量:'), self.offset)

        # USB 传输设置
        self.usb_traffic = QSpinBox()
        self.usb_traffic.setSuffix(' MB/s')
        self.usb_traffic.setRange(1, 500)  # 设置 USB 输范围
        self.usb_traffic.valueChanged.connect(self.update_usb_traffic)
        control_layout.addRow(QLabel('USB 宽带:'), self.usb_traffic)
        
        # 添加图像显示方式选择框
        self.display_mode_selector = QComboBox()
        self.display_mode_selector.addItems(['分布式显示', '单一显示', '序列显示'])
        
        control_layout.addRow(QLabel('图像显示方式:'), self.display_mode_selector)

        # 添加 Bayer 类型转换组件
        self.bayer_conversion_selector = QComboBox()
        self.bayer_conversion_selector.addItems(["None", "RGGB", "BGGR", "GRBG", "GBRG"])
        self.bayer_conversion_selector.currentIndexChanged.connect(self.on_bayer_conversion_changed)
        self.bayer_conversion = "None"
        self.bayer_name = QLabel("Bayer 类型转换:")
        # 将 Bayer 类型转换组件添加到布局中
        control_layout.addRow(self.bayer_name, self.bayer_conversion_selector)
        
        grid_layout = QGridLayout()
        self.start_button = QPushButton('开始拍摄')
        self.save_button = QPushButton('保存')
        self.save_button.setToolTip('保存最后拍摄的未经过图像处理的图像')
        self.start_button.clicked.connect(self.start_capture)
        self.save_button.clicked.connect(self.save_image)
        grid_layout.addWidget(self.start_button,0,0)
        grid_layout.addWidget(self.save_button,0,1)
        control_layout.addRow(grid_layout)
        
        self.capture_in_progress = False
        self.capture_status_label = QLabel('')
        control_layout.addRow(self.capture_status_label)

        self.capture_status_thread = None
        
        self.control_box.setLayout(control_layout)
        layout.addWidget(self.control_box)

        '''录像设置布局'''
        self.preview_thread = None
        
        # 录像区域
        self.video_control_box = QGroupBox('录像')
        video_layout = QFormLayout()
        
        grid_layout = QGridLayout()
        # 预览模式控件
        self.preview_status = False
        self.preview_checkbox = QCheckBox('启动预览模式')
        self.preview_checkbox.setToolTip('预览模式下，相机将实时输出图像数据，并显示在窗口中')
        self.preview_checkbox.stateChanged.connect(self.toggle_preview_mode)
        grid_layout.addWidget(self.preview_checkbox,0,0)
        # 是否顶置的控件
        # self.top_checkbox_status = False
        self.top_checkbox = QCheckBox('是否顶置')
        self.top_checkbox.setToolTip('勾选后，图像将顶置显示')
        # self.top_checkbox.stateChanged.connect(self.toggle_top_checkbox)
        grid_layout.addWidget(self.top_checkbox,0,1)
        # 创建水平布局，将两个复选框放在左边
        checkbox_layout = QHBoxLayout()
        checkbox_layout.addWidget(self.preview_checkbox)
        checkbox_layout.addWidget(self.top_checkbox)

        # 保存进度显示
        self.save_progress_indicator = QLabel("")
        # self.save_progress_indicator.setVisible(False)  # 初始隐藏
        grid_layout.addWidget(self.save_progress_indicator,0,3)
        video_layout.addRow(grid_layout)  # 将转圈指示器添加到布局中

        # 默认路径和文件名
        self.default_path = os.getcwd()  # 当前工作目录
        self.default_filename = f"qhyccd_now-time"
        self.save_thread = None
        
        # 保存方式选择框
        self.save_mode = '单帧存储'
        self.save_mode_selector = QComboBox()
        self.save_mode_selector.addItems(['单帧存储', '视频存储'])
        self.save_mode_selector.currentIndexChanged.connect(self.on_save_mode_changed)
        # 添加到布局中
        video_layout.addRow(QLabel('保存方式:'), self.save_mode_selector)
        
        # 路径选择控件
        self.path_selector = QLineEdit()
        self.path_selector.setText(self.default_path)
        self.path_button = QPushButton('选择路径')
        self.path_button.clicked.connect(self.select_path)
        path_layout = QHBoxLayout()
        path_layout.addWidget(self.path_selector)
        path_layout.addWidget(self.path_button)
        video_layout.addRow(QLabel('录像路径:'), path_layout)
        
        # 录像文件名选择控件
        self.record_file_name = QLineEdit()
        self.record_file_name.setPlaceholderText("请输入录像文件名")
        self.record_file_name.setText(self.default_filename)
        
        # 添加保存格式选择控件
        self.save_format_selector = QComboBox()
        if self.save_mode == '单帧存储':
            self.save_format_selector.addItems(['png', 'jpeg', 'tiff', 'fits'])  # 图片格式
        elif self.save_mode == '视频存储':
            self.save_format_selector.addItems(['avi', 'mp4', 'mkv'])  # 视频格式
        name_layout = QHBoxLayout()
        name_layout.addWidget(self.record_file_name)
        name_layout.addWidget(self.save_format_selector)
        video_layout.addRow(QLabel('录像文件名:'), name_layout)   
        
        # 录像模式选择控件
        self.record_mode = '连续模式'
        self.record_mode_ids = {"连续模式":0,'时间模式':1,'帧数模式':2}
        self.record_mode_selector = QComboBox()
        self.record_mode_selector.addItems(list(self.record_mode_ids.keys()))
        self.record_mode_selector.currentIndexChanged.connect(self.on_record_mode_changed)
        video_layout.addRow(QLabel('录像模式:'), self.record_mode_selector)
        
        # 显示时间输入框
        self.start_save_time = None
        self.record_time_input = QSpinBox()
        self.record_time_input.setSuffix(' 秒')
        self.record_time_input.setRange(1, 3600)  # 设置范围为1秒到3600秒
        self.record_time_input_label = QLabel('录制时长:')
        video_layout.addRow(self.record_time_input_label, self.record_time_input)
        self.record_time_input.setVisible(False)
        self.record_time_input_label.setVisible(False)
        
        # 显示帧数输入框
        self.record_frame_count = 0
        self.frame_count_input = QSpinBox()
        self.frame_count_input.setRange(1, 10000)  # 设置范围为1到10000帧
        self.frame_count_input_label = QLabel('录制帧数:')
        video_layout.addRow(self.frame_count_input_label, self.frame_count_input)
        self.frame_count_input.setVisible(False)
        self.frame_count_input_label.setVisible(False)

        grid_layout = QGridLayout()
        # 开启录像按钮
        self.record_button = QPushButton('开始录像')
        grid_layout.addWidget(self.record_button,0,0)
        self.record_button.clicked.connect(self.start_recording)
        
        # 停止录像按钮
        self.stop_record_button = QPushButton('停止录像')
        self.stop_record_button.clicked.connect(self.stop_recording)
        grid_layout.addWidget(self.stop_record_button,0,1)
        video_layout.addRow(grid_layout)
        
        # 添加进度条
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 100)  # 设置进度条范围
        self.progress_bar.setValue(0)  # 初始值为0
        # 将进度条添加到布局中
        video_layout.addRow(QLabel('录制进度:'), self.progress_bar)
        
        self.video_control_box.setLayout(video_layout)
        layout.addWidget(self.video_control_box)
        


        # '''图像处理设置布局'''
        # # 图像控制区域
        self.image_control_box = QGroupBox('图像处理')
        image_control_layout = QVBoxLayout()
        
        # 添加直方图控制
        histogram_group = QGroupBox("直方图")
        histogram_layout = QFormLayout()
        
        # 添加是否显示直方图的复选框
        self.show_histogram_checkbox = QCheckBox("显示直方图")
        self.show_histogram_checkbox.stateChanged.connect(self.toggle_histogram_display)
        histogram_layout.addRow(self.show_histogram_checkbox)
        
        # 添加绘图区域
        self.histogram_widget = HistogramWidget(self.viewer)

        self.last_time = 0  # 初始化上次更新时间
        self.update_interval = 1   # 每秒 1 次更新的时间间隔
        self.preview_contrast_limits_connection = None
        self.contrast_limits_connection = None
        
        histogram_group.setLayout(histogram_layout)
        

        
        # 添加白平衡控制
        self.wb_group = QGroupBox("白平衡控制")
        wb_layout = QFormLayout()
        self.wb_red = QSlider(Qt.Horizontal)
        self.wb_green = QSlider(Qt.Horizontal)
        self.wb_blue = QSlider(Qt.Horizontal)
        
        wb_layout.addRow(QLabel("红色:"), self.wb_red)
        wb_layout.addRow(QLabel("绿:"), self.wb_green)
        wb_layout.addRow(QLabel("蓝色:"), self.wb_blue)
        self.wb_group.setLayout(wb_layout)
        
        # 将新的布局添加到主布局中
        image_control_layout.addWidget(histogram_group)
        image_control_layout.addWidget(self.wb_group)
        
        self.image_control_box.setLayout(image_control_layout)
        layout.addWidget(self.image_control_box)


        '''温度控制布局'''
        # 温度控制
        self.temperature_control_box = QGroupBox('温度控制')
        temperature_layout = QFormLayout()
        
        self.temperature_setpoint = QDoubleSpinBox()
        self.temperature_setpoint.setSuffix(' °C')
        self.temperature_setpoint.valueChanged.connect(self.update_temperature_setpoint)
        temperature_layout.addRow(QLabel('设定温度:'), self.temperature_setpoint)
        
        grid_layout = QGridLayout()
        self.current_temperature_label = QLabel('温度: 未知')
        self.current_humidity_label = QLabel('湿度: 未知')
        grid_layout.addWidget(self.current_temperature_label,0,0)
        grid_layout.addWidget(self.current_humidity_label,0,1)
        temperature_layout.addRow(grid_layout)
        
        self.temperature_control_box.setLayout(temperature_layout)
        layout.addWidget(self.temperature_control_box)
        

        '''滤镜轮控制布局'''
        # 滤镜轮控制区域
        self.CFW_control_box = QGroupBox('滤镜轮控制')
        CFW_layout = QFormLayout()
        
        self.CFW_id = None # 当前选中滤镜轮ID
        
        self.CFW_number_ids = {}
        self.CFW_filter_selector = QComboBox()
        self.CFW_filter_selector.addItems(list(self.CFW_number_ids.keys()))  # 示例项
        self.CFW_filter_selector.currentIndexChanged.connect(self.on_CFW_filter_changed)
        
        CFW_layout.addRow(QLabel('滤镜轮位置:'), self.CFW_filter_selector)
        self.CFW_control_box.setLayout(CFW_layout)
        layout.addWidget(self.CFW_control_box)



        '''主布局'''
        self.setLayout(QVBoxLayout())
        self.layout().addWidget(scroll_area)
        
        
        '''初始化所有区域为隐藏状态'''
        self.settings_box.setVisible(False)
        self.control_box.setVisible(False)
        self.image_control_box.setVisible(False)
        self.temperature_control_box.setVisible(False)
        self.CFW_control_box.setVisible(False)
        self.video_control_box.setVisible(False)
        
        # 初始化SDK
        self.connect_button.setEnabled(False)
        self.disconnect_button.setEnabled(False)
        self.reset_camera_button.setEnabled(False)
        
        # 禁用复选框
        self.show_settings_checkbox.setEnabled(False)
        self.show_control_checkbox.setEnabled(False)
        self.show_image_control_checkbox.setEnabled(False)
        self.show_temperature_control_checkbox.setEnabled(False)
        self.show_CFW_control_checkbox.setEnabled(False)
        self.show_video_control_checkbox.setEnabled(False)    
    
        self.current_image = None
        self.current_image_name = None
        self.preview_image = None
        self.contrast_limits_name = None
    
        self.is_color_camera = False  # 新增变量，判断相机是否是彩色相机
        
        self.temperature_update_timer = QTimer(self)
        self.temperature_update_timer.timeout.connect(self.update_current_temperature)
        
        self.is_CFW_control = False  # 新增变量，判断相机是否连接滤镜轮
        
        self.roi_points = []
        self.roi_layer = None
        self.roi_created = False
        self.viewer.mouse_drag_callbacks.append(self.on_mouse_click)
        self.viewer.mouse_double_click_callbacks.append(self.on_mouse_double_click)
        
        self.state_label.setText("初始化完成")
        
        '''初始化相机资源'''
        try:
            self.init_qhyccdResource()
            self.read_camera_name()
        except Exception as e:
            self.qhyccd_path_label.setText(f"初始化失败: {str(e)}")
            self.init_qhyccd_button.setEnabled(False)
            
        
    
    def init_qhyccd_with_path(self):
        file_path = self.qhyccd_path_label.text()
        self.init_qhyccdResource(file_path)
    
    def select_qhyccd_path(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "选择SDK文件", "", "DLL Files (*.dll);;SO Files (*.so)")
        if file_path:
            self.qhyccd_path_label.setText(file_path)
            self.qhyccd_path = file_path
            
    # 初始化QHYCCD资源
    def init_qhyccdResource(self,file_path=None):
        
        if file_path is None:
            if self.system_name == 'posix':
                # 类 Unix 系统（如 Linux 或 macOS）
                lib_path = '/usr/local/lib/libqhyccd.so'
                if os.path.exists(lib_path):
                    self.qhyccddll = cdll.LoadLibrary(lib_path)
                    self.qhyccd_path_label.setText(lib_path)
                else:
                    raise FileNotFoundError(f"文件 {lib_path} 不存在")
            elif self.system_name == 'nt':
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
                    # 其他架构（不推荐使用）
                    lib_path = './qhyccd.dll'
                    warnings.warn(f"未知的架构 {arch}，请注意路径问题")
                if os.path.exists(lib_path):
                    self.qhyccddll = cdll.LoadLibrary(lib_path)
                    self.qhyccd_path_label.setText(lib_path)
                else:
                    raise FileNotFoundError(f"文件 {lib_path} 不存在")
            else:
                # 其他操作系统（不推荐使用）
                lib_path = './qhyccd.dll'
                if os.path.exists(lib_path):
                    self.qhyccddll = cdll.LoadLibrary(lib_path)
                    self.qhyccd_path_label.setText(lib_path)
                else:
                    warnings.warn(f"当操作系统是 {self.system_name}，请注意路径问题")
                    raise FileNotFoundError(f"文件 {lib_path} 不存在")
        else:
            self.qhyccddll = cdll.LoadLibrary(file_path)
        
        # 设置函数的参数和返回值类型

        # 获取机 ID
        self.qhyccddll.GetQHYCCDId.argtypes = [ctypes.c_uint32, ctypes.c_char_p]

        # 通过相机 ID 打开相机
        self.qhyccddll.OpenQHYCCD.argtypes = [ctypes.c_char_p]
        self.qhyccddll.OpenQHYCCD.restype = ctypes.c_void_p

        # 关闭相机
        self.qhyccddll.CloseQHYCCD.argtypes = [ctypes.c_void_p]

        # 读模式
        self.qhyccddll.GetQHYCCDNumberOfReadModes.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
        self.qhyccddll.GetQHYCCDReadModeName.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_char_p]
        self.qhyccddll.GetQHYCCDReadModeResolution.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32),
                                                        ctypes.POINTER(ctypes.c_uint32)]
        self.qhyccddll.SetQHYCCDReadMode.argtypes = [ctypes.c_void_p, ctypes.c_uint32]

        # 设置帧模式或实时流模式
        self.qhyccddll.SetQHYCCDStreamMode.argtypes = [ctypes.c_void_p, ctypes.c_uint32]

        # 初始化相机
        self.qhyccddll.InitQHYCCD.argtypes = [ctypes.c_void_p]

        # 获取相机芯片信息
        self.qhyccddll.GetQHYCCDChipInfo.argtypes = [ctypes.c_void_p,
                                            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
                                            ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint32),
                                            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
                                            ctypes.POINTER(ctypes.c_uint32)]

        # 判断参数是否可用
        self.qhyccddll.IsQHYCCDControlAvailable.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        self.qhyccddll.IsQHYCCDControlAvailable.restype = ctypes.c_bool

        
        # 获参数值
        self.qhyccddll.GetQHYCCDParam.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        self.qhyccddll.GetQHYCCDParam.restype = ctypes.c_double

        # 设置参数
        self.qhyccddll.SetQHYCCDParam.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_double]

        # 获取参数值的范围
        self.qhyccddll.GetQHYCCDParamMinMaxStep.argtypes = [ctypes.c_void_p, ctypes.c_uint32,
                                                    ctypes.POINTER(ctypes.c_double),ctypes.POINTER(ctypes.c_double),
                                                    ctypes.POINTER(ctypes.c_double)]
        self.qhyccddll.GetQHYCCDParamMinMaxStep.restype = ctypes.c_double

        # 设置去马赛克（Debayer）开关，仅对彩色相机有效
        self.qhyccddll.SetQHYCCDDebayerOnOff.argtypes = [ctypes.c_void_p, ctypes.c_bool]

        # 设置 bin 模式
        self.qhyccddll.SetQHYCCDBinMode.argtypes = [ctypes.c_void_p, ctypes.c_uint32]

        # 设置分辨率和 ROI
        self.qhyccddll.SetQHYCCDResolution.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32,
                                                ctypes.c_uint32]

        # 启动单帧模式曝光
        self.qhyccddll.ExpQHYCCDSingleFrame.argtypes = [ctypes.c_void_p]
        
        # 获取已曝光时长
        self.qhyccddll.GetQHYCCDExposureRemaining.argtypes = [ctypes.c_void_p]
        # self.qhyccddll.GetQHYCCDExposureRemaining.restype = ctypes.c_double
        
        # 获取单帧数据
        self.qhyccddll.GetQHYCCDSingleFrame.argtypes = [ctypes.c_void_p,
                                                ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint32),
                                                ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint32),
                                                ctypes.POINTER(ctypes.c_uint8)]

        # 取消单次曝光，相机将不输出帧数据
        self.qhyccddll.CancelQHYCCDExposingAndReadout.argtypes = [ctypes.c_void_p]

        # 启动实时流式
        self.qhyccddll.BeginQHYCCDLive.argtypes = [ctypes.c_void_p]

        # 获取实时帧数据
        self.qhyccddll.GetQHYCCDLiveFrame.argtypes = [ctypes.c_void_p,
                                                ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint32),
                                                ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint32),
                                                ctypes.POINTER(ctypes.c_uint8)]

        # 停止实时流模式
        self.qhyccddll.StopQHYCCDLive.argtypes = [ctypes.c_void_p]

        # 转换图像数据（从16位转换为8位）
        self.qhyccddll.Bits16ToBits8.argtypes = [ctypes.c_void_p,
                                            ctypes.POINTER(ctypes.c_uint8), ctypes.POINTER(ctypes.c_uint8),
                                            ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint16, ctypes.c_uint16]
        
        # 判断滤镜轮是否连接
        self.qhyccddll.IsQHYCCDCFWPlugged.argtypes = [ctypes.c_void_p]
        self.qhyccddll.IsQHYCCDCFWPlugged.restype = ctypes.c_bool
        
        # EXPORTC uint32_t STDCALL SendOrder2QHYCCDCFW(qhyccd_handle *handle,char *order,uint32_t length);
        # 发送命令到滤镜轮
        self.qhyccddll.SendOrder2QHYCCDCFW.argtypes = [ctypes.c_void_p,ctypes.c_char_p,ctypes.c_uint32]

        # 获取湿度
        self.qhyccddll.GetQHYCCDHumidity.argtypes = [ctypes.c_void_p,ctypes.POINTER(ctypes.c_double)]

        # 获取相机有效扫描范围
        self.qhyccddll.GetQHYCCDEffectiveArea.argtypes = [ctypes.c_void_p,ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint32)]
        
        # 初始化QHYCCD资源
        ret = self.qhyccddll.InitQHYCCDResource()
         
        # self.read_camera_name()
        
        self.connect_button.setEnabled(True)
        self.disconnect_button.setEnabled(True)
        self.reset_camera_button.setEnabled(True)

        self.init_state = True
        
        

    # 读取模式变化逻辑
    def on_camera_mode_changed(self):
        self.camera_mode = self.camera_mode_selector.currentText()
        print(f"self.camera_mode:{self.camera_mode}")
        if self.camhandle != 0 or self.camera_state:
            self.disconnect_camera()
            self.connect_camera()

    # 创建一个方法来更新进度条
    def update_memory_progress(self, used_memory):
        # print(f"Used Memory: {used_memory},")
        if used_memory > 0:
            memory_usage_percentage = int(used_memory)
            self.memory_progress_bar.setValue(memory_usage_percentage)  # 更新进度条值
            
            # 根据内存占用设置进度条颜色
            if memory_usage_percentage < 60:
                self.memory_progress_bar.setStyleSheet("QProgressBar::chunk { background-color: green; }")  # 低于60%为绿色
            elif memory_usage_percentage < 80:
                # 渐变为黄色
                yellow_value = int((memory_usage_percentage - 60) * 255 / 20)  # 计算黄色值
                self.memory_progress_bar.setStyleSheet(f"QProgressBar::chunk {{ background-color: rgb({yellow_value}, 255, 0); }}")
            else:
                # 渐变为红色
                red_value = int((memory_usage_percentage - 80) * 255 / 20)  # 计算红色值
                self.memory_progress_bar.setStyleSheet(f"QProgressBar::chunk {{ background-color: rgb(255, {255 - red_value}, 0); }}")
    
    def read_camera_name(self):
        if self.init_state:
            self.disconnect_camera()
        self.init_qhyccdResource()
        # 扫描QHYCCD相机
        num = self.qhyccddll.ScanQHYCCD()
        print("ScanQHYCCD() num =", num)
        self.camera_ids = {}
        # 遍历所有扫描到的相机
        for index in range(num):
            print("index =", index)

            # 获相机 ID
            id_buffer = ctypes.create_string_buffer(40)
            ret = self.qhyccddll.GetQHYCCDId(index, id_buffer)
            result_id = id_buffer.value.decode("utf-8")
            self.camera_ids[result_id] = id_buffer
            print(f"id_buffer:{id_buffer},{type(id_buffer)},self.camera_ids[result_id]:{self.camera_ids[result_id]},{type(self.camera_ids[result_id])}")
            print("GetQHYCCDId() ret =", ret, "id =", result_id)
    
        self.camera_selector.clear()
        self.camera_selector.addItems(list(self.camera_ids.keys()))
    
    # 连接相机
    def connect_camera(self,mode=0,bin=[1,1]):
        if self.camhandle != 0:
            self.disconnect_camera()
        if not self.init_state:
            self.init_qhyccdResource()
        camera_name = self.camera_selector.currentText()
        self.camera_name = camera_name
        print(f"self.camera_ids[camera_name]:{self.camera_ids[camera_name]},{type(self.camera_ids[camera_name])}")
        
        self.camhandle = self.qhyccddll.OpenQHYCCD(self.camera_ids[camera_name])
        print("OpenQHYCCD() camhandle =", hex(self.camhandle))

        # 如果相机句柄不为0，表示相机打开成功
        if self.camhandle != 0 and self.camhandle > 0:
            # 获取相机的读取模式数量
            readmodenum = ctypes.c_uint32()
            ret = self.qhyccddll.GetQHYCCDNumberOfReadModes(self.camhandle, byref(readmodenum))
            print("GetQHYCCDNumberOfReadModes() ret =", ret, "num =", readmodenum.value)

            self.camera_read_mode_ids.clear()
            # 遍历所有的读取模式
            for index in range(readmodenum.value):
                print("index =", index)

                # 获取每种读取模式的名称
                name_buffer = ctypes.create_string_buffer(40)
                ret = self.qhyccddll.GetQHYCCDReadModeName(self.camhandle, index, name_buffer)
                result_name = name_buffer.value.decode("utf-8")
                print("GetQHYCCDReadModeName() ret =", ret, "name =", result_name)
                
                self.camera_read_mode_ids[f"{result_name}"] = index

            if mode == 0:
                # 设置相机为第一个读取模式 (index 0)
                ret = self.qhyccddll.SetQHYCCDReadMode(self.camhandle, 0)
            else:
                self.camera_read_mode_ids = self.swap_elements(self.camera_read_mode_ids,mode)
                ret = self.qhyccddll.SetQHYCCDReadMode(self.camhandle, self.camera_read_mode_ids[mode])
            
            print("SetQHYCCDReadMode() ret =", ret)

            # 设置相机模式 
            ret = self.qhyccddll.SetQHYCCDStreamMode(self.camhandle, self.camera_mode_ids[self.camera_mode])
            print("SetQHYCCDStreamMode() ret =", ret)
            # 初始化相机
            ret = self.qhyccddll.InitQHYCCD(self.camhandle)
            print("InitQHYCCD() ret =", ret)
            print("相机已开启!")
            
            # 更新参数
            self.update_camera_color()
            self.update_limit_selector()
            self.update_camera_config()
            self.update_readout_mode_selector()
            self.update_camera_pixel_bin(bin=bin)
            self.update_depth_selector()
            self.update_resolution(0,0,self.image_w,self.image_h)
            self.update_camera_mode()
            self.update_camera_temperature()
            self.update_CFW_control()
            self.start_capture_status_thread()
            
            # 启用复选框
            self.show_settings_checkbox.setEnabled(True)
            self.show_control_checkbox.setEnabled(True)
            self.show_image_control_checkbox.setEnabled(True)
            
            # 显示复选框
            self.toggle_settings_box(True)
            self.toggle_control_box(True)
            self.toggle_image_control_box(True)
            
            self.camera_state = True
            self.connect_button.setEnabled(False)
            self.reset_camera_button.setEnabled(False)
            
            self.config_label.setText(f'已连接!')
            self.config_label.setStyleSheet("color: green;")  # 设置字体颜色为绿色
                
            self.state_label.setText("连接相机完成")
    
    def disconnect_camera(self):
        """断开相机连接"""
        if self.camhandle == 0:
            return
        if self.capture_in_progress:
            self.cancel_capture()

            
        ret = self.qhyccddll.CloseQHYCCD(self.camhandle)
        print("CloseQHYCCD() ret =", ret)

        # 释放QHYCCD资源
        ret = self.qhyccddll.ReleaseQHYCCDResource()
        print("ReleaseQHYCCDResource() ret =", ret)
        self.camhandle = 0
        self.config_label.setText('未连接')
        self.config_label.setStyleSheet("color: red;")  # 设置字体颜色为红色
        print("相机已关闭！")
        
        self.current_image = None
        self.current_image_name = None
        
        if self.is_color_camera:    
            # 断开连接信号
            for slider in [self.wb_red, self.wb_green, self.wb_blue]:
                slider.valueChanged.disconnect()  # 断开之前的连接
        
        self.init_state = False
        # 初始化所有区域为隐藏状态
        self.settings_box.setVisible(False)
        self.control_box.setVisible(False)
        self.image_control_box.setVisible(False)
        self.temperature_control_box.setVisible(False)
        self.CFW_control_box.setVisible(False)
        self.video_control_box.setVisible(False)
        # 取消选项
        self.toggle_settings_box(False)
        self.toggle_control_box(False)
        self.toggle_image_control_box(False)
        self.toggle_temperature_control_box(False)
        self.toggle_CFW_control_box(False)
        self.toggle_video_control_box(False)

        # 禁用复选框
        self.show_settings_checkbox.setEnabled(False)
        self.show_control_checkbox.setEnabled(False)
        self.show_image_control_checkbox.setEnabled(False)
        self.show_temperature_control_checkbox.setEnabled(False)
        self.show_CFW_control_checkbox.setEnabled(False)
        self.show_video_control_checkbox.setEnabled(False)
        self.camera_state = False
        
        self.temperature_update_timer.stop()
        self.connect_button.setEnabled(True)
        
        self.reset_camera_button.setEnabled(True)
        
        self.stop_preview()
        self.state_label.setText("断开相机连接")

    def start_capture_status_thread(self):
        if self.capture_status_thread is None:
            self.capture_status_thread = CaptureStatusThread(self.qhyccddll, self.camhandle)
            self.capture_status_thread.update_status.connect(self.capture_status_label.setText)
            self.capture_status_thread.end_capture.connect(self.end_capture)
            self.capture_status_thread.start()
            self.capture_status_thread.pause_capture()
            
    def end_capture(self):
        if self.capture_status_label.text().startswith("拍摄中"):
            self.capture_status_label.setText("拍摄完成！")
               
    def update_camera_color(self):
        # 判断相机是否是彩色相机
        try:
            if not self.qhyccddll.IsQHYCCDControlAvailable(self.camhandle, CONTROL_ID.CAM_IS_COLOR.value):
                min_data, max_data, step = self.getParamlimit(CONTROL_ID.CAM_IS_COLOR.value)
                print(f"彩色相机判断参数: min_data:{min_data}, max_data:{max_data}, step:{step}")
                is_color_value = self.qhyccddll.GetQHYCCDParam(self.camhandle, CONTROL_ID.CAM_IS_COLOR.value)
                if is_color_value == 4294967295.0:
                    print("返回值表示错误或无效，使用相机名字进行判断")
                    self.is_color_camera = self.is_color_camera_by_name(self.camera_name)
                else:
                    self.is_color_camera = (int(min_data) == 0)
            else:
                self.is_color_camera = self.is_color_camera_by_name(self.camera_name)

            print(f"相机是否是彩色相机: {self.is_color_camera}")
        except Exception as e:
            print(f"获取相机颜色信息时出错: {e}")
            self.is_color_camera = self.is_color_camera_by_name(self.camera_name)
        
        if not self.is_color_camera:
            self.bayer_conversion = "None"
            self.bayer_conversion_selector.setCurrentText("None")
            # 隐藏控件并移除占用空间
            self.bayer_conversion_selector.setEnabled(False)
            self.bayer_conversion_selector.setVisible(False)
            self.layout().removeWidget(self.bayer_conversion_selector)  # 从布局中移除

            self.wb_group.setVisible(False)
            self.layout().removeWidget(self.wb_group)  # 从布局中移除

            self.bayer_name.setVisible(False)
            self.layout().removeWidget(self.bayer_name)  # 从布局中移除

        else:
            self.wb_group.setVisible(True)
            self.wb_group.setEnabled(True)
            self.bayer_conversion_selector.setVisible(True)
            self.bayer_conversion_selector.setEnabled(True)
            self.bayer_name.setVisible(True)
            if self.camera_mode == "连续模式":  
                for slider in [self.wb_red, self.wb_green, self.wb_blue]:
                    slider.valueChanged.connect(self.apply_white_balance_hardware)
            else:
                for slider in [self.wb_red, self.wb_green, self.wb_blue]:
                    slider.valueChanged.connect(lambda: self.on_set_white_balance_clicked())
            
        self.state_label.setText("判断是否为彩色相机")
            
    def update_limit_selector(self):
        # 设置曝光限制
        exposure = self.qhyccddll.GetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_EXPOSURE.value)
        min_data, max_data, _ = self.getParamlimit(CONTROL_ID.CONTROL_EXPOSURE.value)
        print("exposure_time", min_data, max_data)
        self.exposure_time.setRange(min_data/1000, max_data/1000)  # 使用 QDoubleSpinBox 设置范围
        self.exposure_time.setValue(exposure/1000)
        self.exposure_time.setSingleStep(1/1000)
        
        # 设置增益
        gain = self.qhyccddll.GetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_GAIN.value)
        min_data, max_data, step = self.getParamlimit(CONTROL_ID.CONTROL_GAIN.value)
        print("gain", min_data, max_data)
        self.gain.setRange(int(min_data), int(max_data))
        self.gain.setSingleStep(float(step))
        self.gain.setValue(int(gain))
        
        # 设置偏移
        offset = self.qhyccddll.GetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_OFFSET.value)
        min_data, max_data, step = self.getParamlimit(CONTROL_ID.CONTROL_OFFSET.value)
        print("offset", min_data, max_data)
        self.offset.setRange(int(min_data), int(max_data))
        self.offset.setSingleStep(float(step))
        self.offset.setValue(int(offset))
        
        # 设置USB宽带
        usb_traffic = self.qhyccddll.GetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_USBTRAFFIC.value)
        min_data, max_data, step = self.getParamlimit(CONTROL_ID.CONTROL_USBTRAFFIC.value)
        print("usb_traffic", min_data, max_data)
        self.usb_traffic.setRange(int(min_data), int(max_data))
        self.usb_traffic.setSingleStep(int(step))
        self.usb_traffic.setValue(int(usb_traffic))
        
        # 设置白平衡限制
        # if self.qhyccddll.IsQHYCCDControlAvailable(self.camhandle, CONTROL_ID.CONTROL_WBR.value) or not self.is_color_camera:
        if not self.is_color_camera:
            self.wb_red.setVisible(False)
            self.layout().removeWidget(self.wb_red)  # 从布局中移除
            self.wb_red.setEnabled(False)
        else:
            self.wb_red.setVisible(True)
            self.wb_red.setEnabled(True)
            wb_red = self.qhyccddll.GetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_WBR.value)
            min_data, max_data, step = self.getParamlimit(CONTROL_ID.CONTROL_WBR.value)
            print(f"wb_red:{wb_red},min_data:{min_data},max_data:{max_data},step:{step}")
            if self.camera_mode == "单帧模式":
                self.wb_red.setRange(int(-100), int(100))
                self.wb_red.setSingleStep(int(1))
                self.wb_red.setValue(int(0))
            else:   
                self.wb_red.setRange(int(min_data), int(max_data))
                self.wb_red.setSingleStep(int(step))
                self.wb_red.setValue(int(wb_red))
        
        # if self.qhyccddll.IsQHYCCDControlAvailable(self.camhandle, CONTROL_ID.CONTROL_WBG.value) or not self.is_color_camera:
        if not self.is_color_camera:
            self.wb_green.setVisible(False)
            self.layout().removeWidget(self.wb_green)  # 从布局中移除
            self.wb_green.setEnabled(False)
        else:
            self.wb_green.setVisible(True)
            self.wb_green.setEnabled(True)
            wb_green = self.qhyccddll.GetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_WBG.value)
            min_data, max_data, step = self.getParamlimit(CONTROL_ID.CONTROL_WBG.value)
            print(f"wb_green:{wb_green},min_data:{min_data},max_data:{max_data},step:{step}")
            if self.camera_mode == "单帧模式":
                self.wb_green.setRange(int(-100), int(100))
                self.wb_green.setSingleStep(int(1))
                self.wb_green.setValue(int(0))
            else:
                self.wb_green.setRange(int(min_data), int(max_data))
                self.wb_green.setSingleStep(int(step))
                self.wb_green.setValue(int(wb_green))
        
        # if self.qhyccddll.IsQHYCCDControlAvailable(self.camhandle, CONTROL_ID.CONTROL_WBB.value ) or not self.is_color_camera:
        if not self.is_color_camera:
            self.wb_blue.setVisible(False)
            self.layout().removeWidget(self.wb_blue)  # 从布局中移除
            self.wb_blue.setEnabled(False)
        else:
            self.wb_blue.setVisible(True)
            self.wb_blue.setEnabled(True)
            wb_blue = self.qhyccddll.GetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_WBB.value)
            min_data, max_data, step = self.getParamlimit(CONTROL_ID.CONTROL_WBB.value)
            print(f"wb_blue:{wb_blue},min_data:{min_data},max_data:{max_data},step:{step}")
            if self.camera_mode == "单帧模式":
                self.wb_blue.setRange(int(-100), int(100))
                self.wb_blue.setSingleStep(int(1))
                self.wb_blue.setValue(int(0))
            else:
                self.wb_blue.setRange(int(min_data), int(max_data))
                self.wb_blue.setSingleStep(int(step))
                self.wb_blue.setValue(int(wb_blue))
        
        # 获取相机有效扫描范围
        startX = ctypes.c_uint32()
        startY = ctypes.c_uint32()
        sizeX = ctypes.c_uint32()
        sizeY = ctypes.c_uint32()
        ret = self.qhyccddll.GetQHYCCDEffectiveArea(self.camhandle, byref(startX), byref(startY), byref(sizeX), byref(sizeY))
        print(f"GetQHYCCDEffectiveArea() ret =", ret)
        print(f"startX:{startX.value},startY:{startY.value},sizeX:{sizeX.value},sizeY:{sizeY.value}")
        self.camera_H = sizeY.value
        self.camera_W = sizeX.value
        self.x.setRange(int(startX.value),int(startX.value+sizeX.value))
        self.y.setRange(int(startY.value),int(startY.value+sizeY.value))
        self.w.setRange(1,int(sizeX.value))
        self.h.setRange(1,int(sizeY.value))
        
        self.state_label.setText("对参数增加限制")
    
    def update_camera_config(self):
        """更新相机配置显示"""
        chipW = ctypes.c_double()  # 芯片宽度
        chipH = ctypes.c_double()  # 芯片高度
        imageW = ctypes.c_uint32()  # 图像宽度
        imageH = ctypes.c_uint32()  # 图像高度
        pixelW = ctypes.c_double()  # 像素宽度
        pixelH = ctypes.c_double()  # 像素高度
        imageB = ctypes.c_uint32()  # 图像位深度

        ret = self.qhyccddll.GetQHYCCDChipInfo(self.camhandle, byref(chipW), byref(chipH), byref(imageW), byref(imageH), byref(pixelW),
                                        byref(pixelH), byref(imageB))
        # print("GetQHYCCDChipInfo() ret =", ret)
        # print("GetQHYCCDChipInfo() chip info =", chipW.value, "x", chipH.value, "mm")
        # print("GetQHYCCDChipInfo() pixel info =", pixelW.value, "x", pixelH.value, "um")
        # print("GetQHYCCDChipInfo() image info =", imageW.value, "x", imageH.value, imageB.value, "bits")

        # self.camera_W = imageW.value
        # self.camera_H = imageH.value
        print(f"imageW:{self.camera_W},imageH:{self.camera_H}")
        self.image_w = imageW.value
        self.image_h = imageH.value
        self.camera_bit = imageB.value
        self.camera_depth_options = self.swap_elements(self.camera_depth_options, f"{imageB.value}bit")
        print(f'芯片宽度: {chipW.value}\n'
                       f'芯片高度: {chipH.value}\n'
                       f'图像宽度: {imageW.value}\n'
                       f'图像高度: {imageH.value}\n'
                       f'像素宽度: {pixelW.value}\n'
                       f'像素高度: {pixelH.value}\n'
                       f'图像位深: {imageB.value}')

        self.state_label.setText("更新相机状态")
    # 更新 pixel_bin_selector 中的选项
    def update_readout_mode_selector(self):
        self.readout_mode_selector.clear()  # 清空现有选项
        updated_items = list(self.camera_read_mode_ids.keys())  # 获取新的选项列表
        self.readout_mode_selector.addItems(updated_items)  # 添加新的选项

    def update_camera_pixel_bin(self,bin=[1,1]):
        self.pixel_bin_selector.clear()  # 清空现有选项
        updated_items = []
        for i in list(self.camera_pixel_bin.keys()):
            if self.qhyccddll.SetQHYCCDBinMode(self.camhandle, self.camera_pixel_bin[i][0], self.camera_pixel_bin[i][1]) != -1:
                if self.camera_pixel_bin[i] == bin:
                    updated_items.insert(0,i)
                    continue
                updated_items.append(i)
        # ret = self.qhyccddll.SetQHYCCDBinMode(self.camhandle, 1, 1) 
        ret = self.qhyccddll.SetQHYCCDBinMode(self.camhandle, self.camera_pixel_bin[updated_items[0]][0], self.camera_pixel_bin[updated_items[0]][1])
        
        self.image_w = int(self.camera_W/self.camera_pixel_bin[updated_items[0]][0])
        self.image_h = int(self.camera_H/self.camera_pixel_bin[updated_items[0]][1])
        print(f"update_camera_pixel_bin:{ret}, {self.camera_pixel_bin[updated_items[0]]},w:{self.image_w},h{self.image_h}")
        self.pixel_bin_selector.addItems(updated_items)  # 添加新的选项
        
        self.state_label.setText("更新bin模式")
        
    def update_depth_selector(self):
        minValue,maxValue,step=self.getParamlimit(CONTROL_ID.CONTROL_TRANSFERBIT.value)
        
        self.depth_selector.clear()  # 清空现有选项
        self.camera_depth_options.clear()
        for i in range(int(minValue),int(maxValue+1),int(step)):
            self.camera_depth_options[f"{i}bit"] = i
        print(f"位深度数: \nmin:{minValue} , max:{maxValue} , step:{step}")
        updated_items = list(self.camera_depth_options.keys())  # 获取新的选项列表
        ret = self.qhyccddll.SetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_TRANSFERBIT.value, self.camera_depth_options[updated_items[0]])
        if ret == -1:
            print(f"位深{self.camera_depth_options[updated_items[0]]}设置失败!")
            return -1
        self.camera_bit = self.camera_depth_options[updated_items[0]]
        self.depth_selector.addItems(updated_items)  # 添加新的选项
        
        self.state_label.setText("更新位深模式")
    
    def update_resolution(self,x,y,w,h):
        print(f"分辨率W:{w},H:{h}")
        # 设置分辨率
        ret = self.qhyccddll.SetQHYCCDResolution(self.camhandle, x, y, w, h)
        self.x.setRange(0,w-1)
        self.x.setValue(x)
        self.y.setRange(0,h-1)
        self.y.setValue(y)
        self.w.setRange(0,w)
        self.w.setValue(w)
        self.h.setRange(0,h)
        self.h.setValue(h)
        self.state_label.setText("更新初始分辨率")
        return ret
    
    def update_camera_mode(self):
        # 判断相机是单帧模式还是连续模式
        if self.camera_mode == '连续模式':
            self.video_control_box.setVisible(True)
            self.show_video_control_checkbox.setVisible(True)
            self.show_video_control_checkbox.setEnabled(True)
            self.toggle_video_control_box(True)
            self.start_preview()
            self.depth_selector.setEnabled(False)
            self.depth_selector.setVisible(False)
            self.layout().removeWidget(self.depth_selector)  # 从布局中移除
            self.depth_name.setVisible(False)
            self.layout().removeWidget(self.depth_name)  # 从布局中移除
            
            self.fps_label.setVisible(True)
            self.fps_label.setStyleSheet("color: green;")
        else:
            self.video_control_box.setVisible(False)
            self.layout().removeWidget(self.video_control_box)  # 从布局中移除
            self.layout().removeWidget(self.show_video_control_checkbox)  # 从布局中移除
            self.show_video_control_checkbox.setVisible(False)
            self.show_video_control_checkbox.setEnabled(False)
            # self.toggle_video_control_box(False)
            self.depth_selector.setEnabled(True)
            self.depth_selector.setVisible(True)
            self.depth_name.setVisible(True)
            self.fps_label.setVisible(False)
        self.state_label.setText("更新相机模式")
    
    def update_camera_temperature(self):
        # 判断相机是否支持温度控制
        self.has_temperature_control = self.qhyccddll.GetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_CURTEMP.value) != 0
        
        print(f"has_temperature_control:{self.has_temperature_control}")
        
        if self.has_temperature_control:
            self.show_temperature_control_checkbox.show()
            self.temperature_control_box.setVisible(True)
            self.toggle_temperature_control_box()
            self.show_temperature_control_checkbox.setEnabled(True)
            self.update_current_temperature()
            self.temperature_update_timer.start(5000)  # 每5秒更新一次温度
        else:
            self.temperature_control_box.setVisible(False)
            self.layout().removeWidget(self.temperature_control_box)  # 从布局中移除
            self.show_temperature_control_checkbox.hide()
            self.layout().removeWidget(self.show_temperature_control_checkbox)  # 从布局中移除
            self.temperature_update_timer.stop()
        self.state_label.setText("更新相机温度控制")
    
    def update_CFW_control(self):
        self.is_CFW_control = self.qhyccddll.IsQHYCCDCFWPlugged(self.camhandle) == 0
        print(f"is_CFW_control:{self.is_CFW_control}")
        
        if self.is_CFW_control:
            self.show_CFW_control_checkbox.show()
            self.CFW_control_box.setVisible(True)
            self.toggle_CFW_control_box(True)
            self.show_CFW_control_checkbox.setEnabled(True)
            
            maxslot = self.qhyccddll.GetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_CFWSLOTSNUM.value)
            if maxslot > 0:
                for i in range(int(maxslot)):
                    # 使用 hex() 函数将十进制数转换为十六进制字符串
                    hex_str = hex(i)
                    # 移除 '0x' 前缀
                    hex_str = hex_str[2:]
                    self.CFW_number_ids[f"滤镜{i}"] = hex_str
                self.CFW_filter_selector.clear()
                self.CFW_filter_selector.addItems(list(self.CFW_number_ids.keys()))  # 示例项
        else:
            self.CFW_control_box.setVisible(False)
            self.layout().removeWidget(self.CFW_control_box)  # 从布局中移除
            self.show_CFW_control_checkbox.hide()
            self.layout().removeWidget(self.show_CFW_control_checkbox)  # 从布局中移除
            self.toggle_CFW_control_box(False)
            self.show_CFW_control_checkbox.setEnabled(False)
        self.state_label.setText("更新相机滤镜轮控制")
    
    # 设置分辨率
    def on_set_resolution_clicked(self):
        x = int(self.x.value())
        y = int(self.y.value())
        w = int(self.w.value())
        h = int(self.h.value())

        if x+w > self.camera_W:
            w = self.camera_W-x
            self.w.setValue(w)
        if y+h > self.camera_H:
            h = self.camera_H-y
            self.h.setValue(h)

        self.image_w = w
        self.image_h = h
        
        # 在这里添加处理分辨率设置的代码
        print(f"设置分辨率为: ({x},{y}) --> ({x+w},{y+h})")
        if self.camera_mode == "连续模式" and self.preview_thread is not None:
            self.stop_preview()
        # 设置相机分辨率为图像的宽度和高度
        ret = self.qhyccddll.SetQHYCCDResolution(self.camhandle, x, y,w , h)
        if ret == -1:
            print(f"分辨率设置失败!")
            return -1
        print("SetQHYCCDResolution() ret =", ret)
        if self.camera_mode == "连续模式" and self.preview_thread is None:
            self.start_preview()
        self.state_label.setText(f"设置分辨率为({x},{y}) --> ({x+w},{y+h})")
        return ret

    def on_set_original_resolution_clicked(self):
        if self.camera_mode == "连续模式" and self.preview_thread is not None:
            self.stop_preview()
        # 设置相机分辨率为图像的宽度和高度
        ret = self.qhyccddll.SetQHYCCDResolution(self.camhandle, 0, 0,self.camera_W , self.camera_H)
        if ret == -1:
            print(f"分辨率设置失败!")
            return -1
        print(f"还原分辨率设置为: ({0},{0}) --> ({self.camera_W},{self.camera_H})")
        self.image_w = self.camera_W
        self.image_h = self.camera_H
        self.x.setValue(0)
        self.y.setValue(0)
        self.w.setValue(self.image_w)
        self.h.setValue(self.image_h)
        if self.camera_mode == "连续模式" and self.preview_thread is None:
            self.start_preview()

    '''
    控制相机设置区域的显示与隐藏
    '''
    def toggle_settings_box(self,state = None):
        if state is None:   
            # 切换相机设置区域的显示与隐藏
            visible = not self.settings_box.isVisible()
        else:
            visible = state
        print(f"toggle_settings_box:{visible} , state:{state}")
        self.settings_box.setVisible(visible)
        self.show_settings_checkbox.setStyleSheet("background-color: green;" if visible else "")  # 设置按钮颜色

        if not visible:
            self.layout().removeWidget(self.settings_box)  # 从布局中移除控件
    
    def toggle_control_box(self,state = None):
        if state is None:   
            # 切换拍摄控制区域的显示与隐藏
            visible = not self.control_box.isVisible()
        else:
            visible = state
        self.control_box.setVisible(visible)
        self.show_control_checkbox.setStyleSheet("background-color: green;" if visible else "")  # 设置按钮颜色

        if not visible:
            self.layout().removeWidget(self.control_box)  # 从布局中移除控件
    
    def toggle_image_control_box(self,state = None):
        if state is None:  
            # 切换图像控制区域的显示与隐藏
            visible = not self.image_control_box.isVisible()
        else:
            visible = state
        self.image_control_box.setVisible(visible)
        self.show_image_control_checkbox.setStyleSheet("background-color: green;" if visible else "")  # 设置按钮颜色

        if not visible:
            self.layout().removeWidget(self.image_control_box)  # 从布局中移除控件
    
    def toggle_temperature_control_box(self,state = None):
        if state is None:   
            # 切换温度控制区域的显示与隐藏
            visible = not self.temperature_control_box.isVisible()
        else:
            visible = state
        self.temperature_control_box.setVisible(visible)
        self.show_temperature_control_checkbox.setStyleSheet("background-color: green;" if visible else "")  # 设置按钮颜色

        if not visible:
            self.layout().removeWidget(self.temperature_control_box)  # 从布局中移除控件
    
    def toggle_CFW_control_box(self,state = None):
        if state is None:   
            # 切换CFW控制区域的显示与隐藏
            visible = not self.CFW_control_box.isVisible()
        else:
            visible = state
        self.CFW_control_box.setVisible(visible)
        self.show_CFW_control_checkbox.setStyleSheet("background-color: green;" if visible else "")  # 设置按钮颜色

        if not visible:
            self.layout().removeWidget(self.CFW_control_box)  # 从布局中移除控件
    
    def toggle_video_control_box(self,state = None):
        if state is None:   
            # 切换录像控制区域的显示与隐藏
            visible = not self.video_control_box.isVisible()
        else:
            visible = state
        self.video_control_box.setVisible(visible)
        self.show_video_control_checkbox.setStyleSheet("background-color: green;" if visible else "")  # 设置按钮颜色

        if not visible:
            self.layout().removeWidget(self.video_control_box)  # 从布局中移除控件
    
    @pyqtSlot(int)
    def on_readout_mode_changed(self, index):
        if not self.camera_state:
            return -1
        # 获取选中的读出模式
        mode = self.readout_mode_selector.itemText(index)
        if mode == ' ' or mode is None :
            return -1
        print(f'选中的读出模式: {mode}')
        
        
        # 在这里添加设置读出模式的代码
        self.disconnect_camera()
        self.connect_camera(mode=mode,bin=self.bin)

    @pyqtSlot(int)
    def on_pixel_bin_changed(self, index):
        if not self.camera_state:
            return -1
        # 获取选中的像素合并 Bin
        bin_size = self.pixel_bin_selector.itemText(index)
        if self.camera_mode == "连续模式":
            self.stop_preview()
        print(f'选中的像素合并 Bin: {bin_size}')
        ret = self.qhyccddll.SetQHYCCDBinMode(self.camhandle, self.camera_pixel_bin[bin_size][0], self.camera_pixel_bin[bin_size][1])
        if ret == -1:
            print(f"像素合并 Bin {bin_size} 设置失败!")
            return -1
        self.bin = self.camera_pixel_bin[bin_size]
        self.image_w = int(self.camera_W/self.camera_pixel_bin[bin_size][0])
        self.image_h = int(self.camera_H/self.camera_pixel_bin[bin_size][1])
        print("SetQHYCCDBinMode() ret =", ret)
        self.update_resolution(0,0,self.image_w,self.image_h)
        if self.camera_mode == "连续模式":
            self.start_preview()
        # self.update_camera_config()
        return ret

    @pyqtSlot(int)
    def on_depth_changed(self, index):
        # 获取选中的输出格式
        depth = self.depth_selector.itemText(index)
        if depth == ' ' or depth is None or depth == '':
            return -1
        print(f'选中的输出格式: {self.camera_depth_options[depth]},{type(self.camera_depth_options[depth])}')
        # 在这里添加设置输出格式的代码
        ret = self.qhyccddll.SetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_TRANSFERBIT.value, self.camera_depth_options[depth])
        if ret == -1:
            print(f"位深{depth}设置失败!")
            return -1
        self.camera_bit = self.camera_depth_options[depth]
        # self.update_camera_config()
        return ret

    def start_capture(self):
        if self.capture_in_progress :
            self.cancel_capture()
            return
        
        self.capture_in_progress = True
        self.start_button.setText('取消拍摄')
        self.capture_status_thread.resume_capture()
        
        print("开始拍摄")
        self.update_exposure_time()
        if self.camera_mode == "单帧模式":
            self.capture_thread = CaptureThread(
                self.camhandle, self.qhyccddll, self.image_w, self.image_h, self.camera_bit, self.is_color_camera, self.bayer_conversion
            )
            self.capture_thread.capture_finished.connect(self.on_capture_finished)
            self.capture_thread.start()
        elif self.camera_mode == "连续模式":
            while self.preview_image is None:
                time.sleep(0.1)
            self.on_capture_finished(self.preview_image)
        self.state_label.setText("开始拍摄")
            
    def on_capture_finished(self, imgdata_np):
        if not self.capture_in_progress :
            return
        
        self.capture_status_thread.pause_capture()

        if self.bayer_conversion != "None" and imgdata_np.ndim == 2:
            imgdata_np = self.convert_bayer(imgdata_np, self.bayer_conversion)
            
        # 获取当前时间并格式化
        current_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        camera_name = self.camera_selector.currentText()
        
        display_mode = self.display_mode_selector.currentText()
        
        if display_mode == '分布式显示':
            print(f"分布式显示 图像形状: {imgdata_np.shape}, 维度: {imgdata_np.ndim}")
            self.current_image = imgdata_np
            self.current_image_name = f'{camera_name}-{current_time}'
            self.viewer.add_image(self.current_image, name=self.current_image_name)
            if self.camera_mode == "单帧模式":
                print("单帧模式")
                imgdata_np = self.apply_white_balance_software(imgdata_np=self.current_image.copy())
                self.viewer.layers[self.current_image_name].data = imgdata_np
        elif display_mode == '单一显示':
            self.current_image_name = f'{camera_name}-one'
            print(f"单一显示 图像形状: {imgdata_np.shape}, 维度: {imgdata_np.ndim}")
            if self.current_image_name in self.viewer.layers and self.current_image.ndim == imgdata_np.ndim and self.current_image.shape[-1] == imgdata_np.shape[-1]:
                self.current_image = imgdata_np

                self.viewer.layers[self.current_image_name].data = self.current_image
            else:
                self.current_image = imgdata_np
                if self.current_image_name in self.viewer.layers:
                    self.viewer.layers.pop(self.current_image_name)
                self.viewer.add_image(self.current_image, name=self.current_image_name)
            # 确保图像在最上层
            self.viewer.layers.selection.active = self.viewer.layers[self.current_image_name]
            if self.camera_mode == "单帧模式":
                print("单帧模式")
                imgdata_np = self.apply_white_balance_software(imgdata_np=self.current_image.copy())
                self.viewer.layers[self.current_image_name].data = imgdata_np
        elif display_mode == '序列显示':
            # 打印图像的形状和维度
            print(f"序列显示 图像形状: {imgdata_np.shape}, 维度: {imgdata_np.ndim}")
            if imgdata_np.ndim == 2:
                imgdata_np_3c = np.stack([imgdata_np] * 3, axis=-1)
                imgdata_np_3c = imgdata_np_3c[np.newaxis, ...]
            if imgdata_np.ndim == 3:
                # imgdata_np = imgdata_np.transpose(2,0,1)
                imgdata_np_3c = imgdata_np[np.newaxis, ...]
            # print(f"imgdata_np.ndim: {imgdata_np.ndim}")
            if self.current_image is None or (imgdata_np_3c.ndim != self.current_image.ndim and imgdata_np_3c.dtype != self.current_image.dtype) or self.current_image.ndim != 4:
                self.current_image = imgdata_np_3c
                self.current_image_name = f'{camera_name}-sequence'
            else:
                self.current_image = np.concatenate((self.current_image, imgdata_np_3c), axis=0)
                self.current_image_name = f'{camera_name}-sequence'
            
            # 检查是否已经存在名为 'qhy-{camera_name}-sequence' 的图层
            if self.current_image_name in self.viewer.layers:
                self.viewer.layers[self.current_image_name].data = self.current_image
            else:
                self.viewer.add_image(self.current_image, name=self.current_image_name)
            
            if self.camera_mode == "单帧模式" and self.is_color_camera:
                print("单帧模式")
                imgdata_np = self.apply_white_balance_software(imgdata_np=self.current_image.copy())
                self.viewer.layers[self.current_image_name].data = imgdata_np
            # 定位显示拍摄的最后一张图片
            self.viewer.layers[self.current_image_name].refresh()
            self.viewer.dims.set_point(0, self.current_image.shape[0] - 1)
        # 确保图像在最上层
        if self.viewer.layers:
            self.viewer.layers.selection.active = self.viewer.layers[-1]
        if not self.top_checkbox.isChecked():
            self.contrast_limits_name = self.current_image_name
        
        self.bind_contrast_limits_event()

        print(f"拍摄完成！")
        self.state_label.setText("拍摄完成")
        
        self.capture_in_progress = False
        self.start_button.setText('开始拍摄')
        self.capture_status_label.setText('拍摄完成！')
        self.histogram_widget.update_histogram(imgdata_np)
        # self.capture_status_thread.pause_capture()

    def cancel_capture(self):
        self.capture_in_progress = False
        self.start_button.setText('开始拍摄')
        self.capture_status_label.setText('拍摄已取消')
        self.state_label.setText("取消拍摄")
        self.capture_status_thread.pause_capture()
        self.qhyccddll.CancelQHYCCDExposingAndReadout(self.camhandle)
        print("拍摄已取消")

    def save_image(self):
        if self.current_image is not None:
            options = QFileDialog.Options()
            file_path, _ = QFileDialog.getSaveFileName(self, "保存图像", "", "PNG Files (*.png);;JPEG Files (*.jpg);;All Files (*)", options=options)
            if file_path:
                if not (file_path.endswith('.png') or file_path.endswith('.jpg')):
                    file_path += '.png'

                if self.current_image.ndim == 2:
                    cv2.imwrite(file_path, self.current_image)
                elif self.current_image.ndim == 3 and self.current_image.shape[2] == 3:
                    cv2.imwrite(file_path, cv2.cvtColor(self.current_image, cv2.COLOR_RGB2BGR))
                print(f"图像已保存到: {file_path}")
                self.state_label.setText(f"图像已保存到{file_path}")
        else:
            print("没有图像可保存")
            self.state_label.setText(f"图像保存失败")
        

    def getParamlimit(self,data_id):
        minValue = ctypes.c_double()  # 最小值
        maxValue = ctypes.c_double()  # 最大值
        step = ctypes.c_double() # 步长
        
        ret = self.qhyccddll.GetQHYCCDParamMinMaxStep(self.camhandle, data_id,byref(minValue),byref(maxValue),byref(step))
        if ret == -1:
            print(f"参数范围获取失败！")
        return minValue.value,maxValue.value,step.value
    
    def update_exposure_time(self):
        
        # 处理曝光时间变化的逻辑
        exposure_time = int(self.exposure_time.value()*1000)
        print(f"exposure_time:{exposure_time},{type(exposure_time)}")
        ret = self.qhyccddll.SetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_EXPOSURE.value, exposure_time)
        if ret == 0:
            print(f"曝光时间设置为: {exposure_time} us")
        else:
            print(f"曝光时间设置失败！")
        return ret
    
    def update_gain(self, value):
        ret = self.qhyccddll.SetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_GAIN.value, value)
        if ret == 0:
            print(f"增益设置为: {value} dB")
        else:
            print(f"增益设置失败！")
        return ret

    def update_offset(self, value):
        ret = self.qhyccddll.SetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_OFFSET.value, value)
        if ret == 0:
            print(f"偏移量设置为: {value} ")
        else:
            print(f"偏移量设置失败！")
        return ret

    def update_usb_traffic(self, value):
        ret = self.qhyccddll.SetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_USBTRAFFIC.value, value)
        if ret == 0:
            print(f"USB带宽设置为: {value} ")
        else:
            print(f"USB带宽设置失败！")
        return ret
         
    def show_roi_component(self):
        # 检查是否存在以QHY开头的图片
        if not any(layer.name.startswith('QHY') for layer in self.viewer.layers ) :
            print("没有以QHY开头的图片，无法启动ROI模式")
            return

        if not self.roi_created:
            self.roi_created = True
            self.show_roi_button.setText('应用ROI')
            self.set_resolution_button.setEnabled(False)
            self.viewer.camera.interactive = False  # 锁定图像
            print("ROI模式已激活，请在图像上点击以选择区域")
        else:
            self.clear_roi()
            self.roi_created = False
            self.show_roi_button.setText('ROI')
            self.set_resolution_button.setEnabled(True)
            self.viewer.camera.interactive = True  # 解锁图像
            print("ROI模式已关闭")

    def on_mouse_click(self, viewer, event):
        if not self.roi_created:
            return

        if event.type == 'mouse_press' and event.button == 1:
            if len(self.roi_points) >= 2:
                self.clear_roi()

            # 将鼠标点击位置转换为图像坐标
            image_coords = self.viewer.layers[0].world_to_data(event.position)
            self.roi_points.append(image_coords)
            print(f"ROI点: {self.roi_points}")

            if len(self.roi_points) == 2:
                self.update_roi_layer()
                self.update_resolution_display()

    def on_mouse_double_click(self, viewer, event):
        self.clear_roi()
        print("所有ROI矩形框已删除")
        
    def on_save_mode_changed(self, index):
        self.save_mode = self.save_mode_selector.itemText(index)
        print(f"选中的录像模式: {self.save_mode}")
        if self.save_mode == '单帧存储':
            self.save_format_selector.clear()
            self.save_format_selector.addItems(['png', 'jpeg', 'tiff', 'fits'])  # 图片格式
        elif self.save_mode == '视频存储':
            self.save_format_selector.clear()
            self.save_format_selector.addItems(['avi', 'mp4', 'mkv'])  # 视频格式

    def clear_roi(self):
        if self.roi_layer is not None:
            self.viewer.layers.remove(self.roi_layer)
            self.roi_layer = None
        self.roi_points = []

    def update_roi_layer(self):
        if self.roi_layer is not None:
            self.viewer.layers.remove(self.roi_layer)

        if len(self.roi_points) == 2:
            x0, y0 = self.roi_points[0]
            x1, y1 = self.roi_points[1]
            rect = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
            self.roi_layer = self.viewer.add_shapes(
                rect,
                shape_type='rectangle',
                edge_width=10,  # 设置边框宽度为10个像素
                edge_color='green',  # 设置边框颜色为绿色
                face_color='transparent',
                name='ROI'
            )

    def update_resolution_display(self):
        if len(self.roi_points) == 2:
            y0,x0 = self.roi_points[0]
            if x0 < 0:
                x0 = 0
            if x0 > self.camera_W:
                x0 = self.camera_W
            if y0 < 0:
                y0 = 0
            if y0 > self.camera_H:
                y0 = self.camera_H
            y1,x1 = self.roi_points[1]
            if x1 < 0:
                x1 = 0
            if x1 > self.camera_W:
                x1 = self.camera_W
            if y1 < 0:
                y1 = 0
            if y1 > self.camera_H:
                y1 = self.camera_H
            x = int(min(x0, x1))
            y = int(min(y0, y1))
            h = int(abs(y1 - y0))
            w = int(abs(x1 - x0))
            # 确保 x, y, w, h 是偶数
            if x % 2 != 0:
                x += 1  # 如果 x 是奇数，则加 1
            if y % 2 != 0:
                y += 1  # 如果 y 是奇数，则加 1
            if w % 2 != 0:
                w += 1  # 如果 w 是奇数，则加 1
            if h % 2 != 0:
                h += 1  # 如果 h 是奇数，则加 1
            self.x.setValue(int(x))
            self.y.setValue(int(y))
            self.w.setValue(int(w))
            self.h.setValue(int(h))
            print(f"更新分辨率显示: x={x}, y={y}, w={w}, h={h}")

    def toggle_histogram_display(self, state):
        """切换直方图显示"""
        if state == Qt.Checked:
            self.histogram_widget.show_widget()
        else:
            self.histogram_widget.hide_widget()  # 隐藏直方图窗口
                   
    def on_set_white_balance_clicked(self):
        if self.current_image is None:
            return
        red_gain = 1+self.wb_red.value()/ self.wb_red.maximum() # 获取红色增益
        green_gain = 1+self.wb_green.value() / self.wb_green.maximum()  # 获取绿色增益
        blue_gain = 1+self.wb_blue.value() / self.wb_blue.maximum()  # 获取蓝色增益
        imgdata_np = self.apply_white_balance_software(self.current_image.copy(),red_gain,green_gain,blue_gain)
        if self.camera_mode == "单帧模式" and len(self.viewer.layers) > 0 and self.viewer.layers[-1].name.startswith('QHY') and imgdata_np.ndim == self.viewer.layers[-1].data.ndim:
            self.viewer.layers[-1].data = imgdata_np
            self.histogram_widget.update_histogram(imgdata_np)
    
    def apply_white_balance_software(self, imgdata_np=None, red_gain=None, green_gain=None, blue_gain=None):
        if imgdata_np is None:
            return
        
        # 获取增益值
        if red_gain is None:
            red_gain = 1 + self.wb_red.value() / self.wb_red.maximum()   # 获取红色增益
        if green_gain is None:
            green_gain = 1 + self.wb_green.value() / self.wb_green.maximum()  # 获取绿色增益
        if blue_gain is None:
            blue_gain = 1 + self.wb_blue.value() / self.wb_blue.maximum()  # 获取蓝色增益

        # 处理单帧图像
        if self.is_color_camera and imgdata_np.ndim == 3 and imgdata_np.shape[2] == 3:
            imgdata_np = self._apply_gain_to_image(imgdata_np, red_gain, green_gain, blue_gain)

        # 处理序列图像
        elif self.is_color_camera and imgdata_np.ndim == 4 and imgdata_np.shape[3] == 3:
            imgdata_np[-1] = self._apply_gain_to_image(imgdata_np[-1], red_gain, green_gain, blue_gain)

        return imgdata_np  # 返回处理后的图像

    def _apply_gain_to_image(self, image, red_gain, green_gain, blue_gain):
        """应用增益到单帧图像"""
        if image.dtype == np.uint16:
            # 处理16位图像
            image[..., 0] = np.clip(image[..., 0] * red_gain, 0, 65535)  # 红色通道
            image[..., 1] = np.clip(image[..., 1] * green_gain, 0, 65535)  # 绿色通道
            image[..., 2] = np.clip(image[..., 2] * blue_gain, 0, 65535)  # 蓝色通道
        else:
            # 处理8位图像
            image[..., 0] = np.clip(image[..., 0] * red_gain, 0, 255)  # 红色通道
            image[..., 1] = np.clip(image[..., 1] * green_gain, 0, 255)  # 绿色通道
            image[..., 2] = np.clip(image[..., 2] * blue_gain, 0, 255)  # 蓝色通道

        return image 
    
    def apply_white_balance_hardware(self):

        red_gain = self.wb_red.value()
        green_gain = self.wb_green.value()
        blue_gain = self.wb_blue.value()
        
        ret = self.qhyccddll.SetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_WBR.value, red_gain)
        if ret == 0:        
            print(f"红色增益设置为: {red_gain}")
        else:
            print(f"红色增益设置失败！")
        ret = self.qhyccddll.SetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_WBG.value, green_gain)
        if ret == 0:
            print(f"绿色增益设置为: {green_gain}")
        else:
            print(f"绿色增益设置失败！")
        ret = self.qhyccddll.SetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_WBB.value, blue_gain)
        if ret == 0:
            print(f"蓝色增益设置为: {blue_gain}")
        else:
            print(f"蓝色增益设置失败！")    
        return 0
    
    def on_bayer_conversion_changed(self, index):
        self.bayer_conversion = self.bayer_conversion_selector.itemText(index)
        print(f"选中的 Bayer 类型转换: {self.bayer_conversion}")

    def convert_bayer(self, img, pattern):
        if img.ndim == 3:
            return img
        if pattern == "RGGB":
            return cv2.cvtColor(img, cv2.COLOR_BAYER_RG2RGB_EA if img.dtype == np.uint16 else cv2.COLOR_BAYER_RG2RGB)
        elif pattern == "BGGR":
            return cv2.cvtColor(img, cv2.COLOR_BAYER_BG2RGB_EA if img.dtype == np.uint16 else cv2.COLOR_BAYER_BG2RGB)
        elif pattern == "GRBG":
            return cv2.cvtColor(img, cv2.COLOR_BAYER_GR2RGB_EA if img.dtype == np.uint16 else cv2.COLOR_BAYER_GR2RGB)
        elif pattern == "GBRG":
            return cv2.cvtColor(img, cv2.COLOR_BAYER_GB2RGB_EA if img.dtype == np.uint16 else cv2.COLOR_BAYER_GB2RGB)
        else:
            return img

    def update_current_temperature(self):
        """更新当前温度显示"""
        current_humidity = ctypes.c_double()
        if self.has_temperature_control:
            current_temp = self.qhyccddll.GetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_CURTEMP.value)
            self.current_temperature_label.setText(f'温度: {current_temp:.2f} °C')
            current_humidity = self.qhyccddll.GetQHYCCDHumidity(self.camhandle,byref(current_humidity))
            if current_humidity > 0:
                self.current_humidity_label.setText(f'湿度: {current_humidity:.2f} %')
    
    def update_temperature_setpoint(self, value):
        """更新温度设定点"""
        if self.has_temperature_control:
            ret = self.qhyccddll.SetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_COOLER.value, value)
            if ret == 0:
                print(f"温度设定点设置为: {value} °C")
            else:
                print(f"温度设定点设置失败！")
                
    def on_CFW_filter_changed(self, index):
        self.CFW_id = self.CFW_filter_selector.itemText(index)
        if self.CFW_id == "None" or self.CFW_id == "" or self.CFW_id == " ":
            return -1
        print(f"选中的 CFW 滤镜: {self.CFW_id},{self.CFW_number_ids[self.CFW_id]}")
        # 将字符串转换为字节字符串
        order = self.CFW_number_ids[self.CFW_id].encode('utf-8')
        ret = self.qhyccddll.SendOrder2QHYCCDCFW(self.camhandle, c_char_p(order), len(order))
        if ret == 0:
            print(f"移动滤镜轮到位置: {self.CFW_id}")
        else:
            print(f"移动滤镜轮失败！")
        
    def is_color_camera_by_name(self, camera_name):
        """根据相机名字判断是否是彩色相机"""
        if camera_name and camera_name.split('-')[0].endswith('C'):
            return True
        return False
    
    def swap_elements(self, dictionary, key):
        """
        将指定键的值移到字典的开头，并返回更新后的字典。
        :param dictionary: 要更新的字典
        :param key: 要移动的键
        :return: 更新后的字典
        """
        if key in dictionary:
            value = dictionary.pop(key)  # 移除指定键
            dictionary = {key: value, **dictionary}  # 将其添加到字典的开头
        return dictionary
    
    def toggle_preview_mode(self, state):
        if state == Qt.Checked:
            self.preview_status = True
        else:
            self.preview_status = False

    def select_path(self):
        options = QFileDialog.Options()
        directory = QFileDialog.getExistingDirectory(self, "选择保存路径", options=options)
        if directory:
            self.path_selector.setText(directory)
            
    def on_record_mode_changed(self, index):
        self.record_mode = self.record_mode_selector.itemText(index)
        print(f"选中的录像模式: {self.record_mode}")

        if self.record_mode == "时间模式":
            self.record_time_input.setVisible(True)
            self.record_time_input_label.setVisible(True)
            self.frame_count_input.setVisible(False)
            self.frame_count_input_label.setVisible(False)
            self.layout().removeWidget(self.frame_count_input)  # 从布局中移除
            self.layout().removeWidget(self.frame_count_input_label)  # 从布局中移除
        elif self.record_mode == "帧数模式":
            self.record_time_input.setVisible(False)
            self.record_time_input_label.setVisible(False)
            self.layout().removeWidget(self.record_time_input)  # 从布局中移除
            self.layout().removeWidget(self.record_time_input_label)  # 从布局中移除
            self.frame_count_input.setVisible(True)
            self.frame_count_input_label.setVisible(True)

        elif self.record_mode == "连续模式":
            self.record_time_input.setVisible(False)
            self.record_time_input_label.setVisible(False)
            self.frame_count_input.setVisible(False)
            self.frame_count_input_label.setVisible(False)
            self.layout().removeWidget(self.record_time_input)  # 从布局中移除
            self.layout().removeWidget(self.record_time_input_label)  # 从布局中移除
            self.layout().removeWidget(self.frame_count_input)  # 从布局中移除
            self.layout().removeWidget(self.frame_count_input_label)  # 从布局中移除

    def start_recording(self):
        self.record_button.setEnabled(False)
        self.is_recording = True
        self.save_progress_indicator.setVisible(True)
        self.save_progress_indicator.setText("保存中...")
        
    def on_save_thread_finished(self):
        self.save_progress_indicator.setText("保存完成")

    def stop_recording(self):
        self.is_recording = False
        self.record_button.setEnabled(True)
        self.buffer_queue.put("end")
        self.save_thread = None
        self.record_time_input.setEnabled(True)
        self.frame_count_input.setEnabled(True)
        self.record_mode_selector.setEnabled(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)  # 重置进度条

    def start_preview(self):
        if self.preview_thread is None:
            ret = self.qhyccddll.BeginQHYCCDLive(self.camhandle)
            print("BeginQHYCCDLive() ret =", ret)
            self.preview_thread = PreviewThread(
                self.camhandle, self.qhyccddll, self.image_w, self.image_h, self.camera_bit, self.is_color_camera, 
                self.bayer_conversion, self.viewer
            )
            self.preview_thread.frame_captured.connect(self.data_received)  # 连接信号到槽函数
            self.preview_thread.start()
            self.preview_checkbox.setChecked(True)
            
    def stop_preview(self):
        if self.preview_thread is not None:
            ret = self.qhyccddll.StopQHYCCDLive(self.camhandle)
            print("StopQHYCCDLive() ret =", ret)
            self.preview_thread.stop()
            self.preview_checkbox.setChecked(False)
            self.preview_thread = None
        
    def data_received(self, imgdata_np, fps):
        if self.top_checkbox.isChecked():
            self.contrast_limits_name = 'QHY-Preview'
        
        
        # 传输数据到保存
        if self.is_recording:
            if self.save_thread is None:
                self.buffer_queue = queue.Queue()
                # 创建并启动保存线程
                self.save_thread = SaveThread(self.buffer_queue, self.path_selector.text(), self.record_file_name.text(), self.save_format_selector.currentText(), self.save_mode, int(fps))
                self.save_thread.finished.connect(self.on_save_thread_finished)  # 连接信号
                self.save_thread.start()
                self.record_time_input.setEnabled(False)
                self.frame_count_input.setEnabled(False)
                self.record_mode_selector.setEnabled(False)
                
                # 重置进度条
                self.progress_bar.setValue(0)
                self.progress_bar.setTextVisible(True)
                self.progress_bar.setStyleSheet("")  # 还原颜色

            if self.record_mode == "时间模式":
                if self.start_save_time is None:
                    self.record_time_input.setEnabled(False)
                    self.record_mode_selector.setEnabled(False)
                    self.start_save_time = time.time()
                
                elapsed_time = time.time() - self.start_save_time
                total_time = self.record_time_input.value()  # 获取总时间
                if total_time > 0:
                    progress = min((elapsed_time / total_time) * 100, 100)  # 计算进度
                    self.progress_bar.setValue(int(progress))

                self.buffer_queue.put(imgdata_np)
                if elapsed_time > total_time:
                    self.buffer_queue.put("end")
                    self.start_save_time = None
                    self.save_thread = None
                    self.stop_recording()
                    self.record_button.setEnabled(True)
                    self.record_time_input.setEnabled(True)
                    self.frame_count_input.setEnabled(True)
                    self.record_mode_selector.setEnabled(True)
                    self.progress_bar.setValue(0)  # 重置进度条
                    
            elif self.record_mode == "帧数模式":
                self.buffer_queue.put(imgdata_np)
                self.record_frame_count += 1
                total_frames = self.frame_count_input.value()  # 获取总帧数
                if total_frames > 0:
                    progress = min((self.record_frame_count / total_frames) * 100, 100)  # 计算进度
                    self.progress_bar.setValue(int(progress))

                if self.record_frame_count >= total_frames:
                    self.buffer_queue.put("end")
                    self.record_frame_count = 0
                    self.save_thread = None
                    self.stop_recording()
                    self.record_button.setEnabled(True)
                    self.record_time_input.setEnabled(True)
                    self.frame_count_input.setEnabled(True)
                    self.record_mode_selector.setEnabled(True)
                    self.progress_bar.setValue(0)  # 重置进度条
            elif self.record_mode == "连续模式":
                self.buffer_queue.put(imgdata_np)
                # 进度条循环
                self.progress_bar.setRange(0, 0)
                # self.progress_bar.setValue((self.progress_bar.value() + 1) % 100)  # 循环更新进度条
                # self.progress_bar.setTextVisible(False)
        
            else:
                print("未选择录像模式！")
                
        # 获取当前时间
        current_time = time.time()
        
        # 应用 Bayer 转换
        if self.is_color_camera and self.bayer_conversion != "None":
            # print(f"经过convert_bayer() imgdata_np.shape: {imgdata_np.shape}")
            imgdata_np = self.convert_bayer(imgdata_np, self.bayer_conversion)
        
        # 传输数据到画布显示，限制最高帧率为30fps   
        if self.last_update_time is not None and current_time - self.last_update_time < 1/30:
            pass
        else:   
            self.update_viewer(imgdata_np, fps)
            self.last_update_time = current_time
            
        if (self.last_histogram_update_time is None or current_time - self.last_histogram_update_time > 1) and self.top_checkbox.isChecked():
            # self.histogram_widget.show_widget()
            self.histogram_widget.update_histogram(imgdata_np)
            self.last_histogram_update_time = current_time
            # self.show_histogram_checkbox.setChecked(True)

    def update_viewer(self, imgdata_np, fps):
        layer_name = 'QHY-Preview'
        
        # self.current_image = imgdata_np
        self.preview_image = imgdata_np
        if not self.preview_status:
            if layer_name in self.viewer.layers:
                self.viewer.layers.remove(layer_name)
            return

        self.fps_label.setText(f'FPS: {fps:.2f}')
        
        # 在图像上绘制帧率
        img_with_fps = imgdata_np.copy()
        
        # 设置文本位置
        text_position = (img_with_fps.shape[1] - 150, 30)  # 右上角

        # 创建半透明背景
        overlay = img_with_fps.copy()
        cv2.rectangle(overlay, (text_position[0] - 10, text_position[1] - 30), 
                                (text_position[0] + 140, text_position[1] + 10), 
                                (0, 0, 0), -1)  # 黑色背景

        # 计算对比色
        contrast_color = (255, 255, 255)  # 白色文本

        # 在图像上绘制 FPS
        cv2.putText(overlay, f'FPS: {fps:.2f}', text_position, 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, contrast_color, 2, cv2.LINE_AA)

        # 将半透明背景叠加到原图像上
        cv2.addWeighted(overlay, 0.5, img_with_fps, 0.5, 0, img_with_fps)

        if layer_name in self.viewer.layers:
            if self.viewer.layers[layer_name].data.shape == img_with_fps.shape:
                self.viewer.layers[layer_name].data = img_with_fps
            else:
                self.viewer.layers.remove(layer_name)
                self.viewer.add_image(img_with_fps, name=layer_name)
        else:
            self.viewer.add_image(img_with_fps, name=layer_name)
            
        # 设置分辨率显示大小占图像的1/100
        resolution_text = f'Resolution: {img_with_fps.shape[1]}x{img_with_fps.shape[0]}'
        resolution_position = (10, img_with_fps.shape[0] - 10)  # 左下角

        # 在图像上绘制分辨率
        cv2.putText(img_with_fps, resolution_text, resolution_position, 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.01 * img_with_fps.shape[0] / 100, contrast_color, 1, cv2.LINE_AA)

        # 如果需要将图层移动到顶部，可以使用以下方法
        if self.top_checkbox.isChecked():  # 检查复选框状态
            layer_index = self.viewer.layers.index(layer_name)  # 获取图层的索引
            self.viewer.layers.move(layer_index, -1)  # 将图层移动到索引0的位置
            self.bind_contrast_limits_event()

    def bind_contrast_limits_event(self):
        # 绑定当前图层的对比度限制变化事件
        current_layer = self.viewer.layers[self.contrast_limits_name]
        try:
            self.contrast_limits_connection = current_layer.events.contrast_limits.connect(self.on_contrast_limits_change)
        except Exception as e:
            print(f"Error connecting contrast limits event: {e}")

    def on_contrast_limits_change(self, event):
        # 当对比度限制变化时触发的函数
        contrast_limits = self.viewer.layers[self.contrast_limits_name].contrast_limits
        # print(f"contrast_limit: {contrast_limits}")
        self.histogram_widget.update_min_max_lines(contrast_limits[0], contrast_limits[1])

        
@napari_hook_implementation
def napari_experimental_provide_dock_widget():
    """注册插件窗口部件"""
    return [CameraControlWidget]

