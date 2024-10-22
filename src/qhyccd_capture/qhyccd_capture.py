from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt, pyqtSlot, QTimer
from PyQt5.QtGui import QIcon, QTextCursor
from napari_plugin_engine import napari_hook_implementation
import napari
import numpy as np
import ctypes
from ctypes import *
import os
import warnings
from datetime import datetime

import cv2
import time
import queue
import json
import pickle
import csv
from multiprocessing import Array
from threading import Lock
from astropy.stats import sigma_clipped_stats
from astropy.io import fits


# Import custom modules
from .control_id import CONTROL_ID
from .previewThread import PreviewThread
from .captureStatus import CaptureStatusThread
from .captureFrame import CaptureThread
from .save_video import SaveThread
from .histogramWidget import HistogramWidget
from .memory_updated import MemoryMonitorThread
from .setting import SettingsDialog
from .language import translations
from .camera_thread import CameraConnectionThread
from .fits_header import FitsHeaderEditor
from .auto_exposure import AutoExposureDialog
from .auto_white_balance import AutoWhiteBalanceDialog
from .stellarSolver import StellarSolver
from .astrometry import AstrometrySolver, AstrometryDialog


class CameraControlWidget(QWidget):
    def __init__(self, napari_viewer):
        super().__init__()
        self.viewer = napari_viewer
        self.initialize_settings()
        self.initialize_histogram_and_memory_monitor()
        self.initialize_state()
        self.initialize_ui()
        self.append_text(translations[self.language]['qhyccd_capture']['init_complete'])

        '''初始化相机资源'''
        try:
            if self.settings_dialog.qhyccd_path_label.text() is None or self.settings_dialog.qhyccd_path_label.text() == "" or self.settings_dialog.qhyccd_path_label.text() == " ":
                self.init_qhyccdResource()
            else:
                self.init_qhyccdResource(self.settings_dialog.qhyccd_path_label.text())
            self.read_camera_name()
        except Exception as e:
            print(f"{translations[self.language]['debug']['init_failed']}: {str(e)}")
            self.append_text(translations[self.language]['qhyccd_capture']['init_failed'])

    def initialize_settings(self):
        # 加载配置
        self.settings_file = "settings.json"  # 设置文件路径
        self.load_settings()  # 加载设置
        self.luts = {}
        if os.path.exists('luts.pkl'):
            with open('luts.pkl', 'rb') as f:
                self.luts = pickle.load(f)
        else:
            self.create_luts([255, 65535], 0, 2.0, 1/100)

    def initialize_histogram_and_memory_monitor(self):
        # 初始化直方图和内存监控
        self.histogram_window = None
        self.memory_monitor_thread = MemoryMonitorThread()
        self.memory_monitor_thread.memory_updated.connect(self.update_memory_progress)
        self.memory_monitor_thread.start()

    def initialize_state(self):
        # 初始化状态
        self.init_state = False
        self.camera_state = False
        
        self.system_name = os.name
        
        
        self.contrast_limits_connection = None
        
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
        
        self.image_x = 0
        self.image_y = 0
        self.image_w = 0
        self.image_h = 0
        
        self.camera_ids = {}
        
        self.buffer_queue = queue.Queue()  # 用于保存图像数据的队列

        
        self.last_update_time = None
        self.last_histogram_update_time = None
        self.is_recording = False
        
        self.file_format = None
        
        self.lock = Lock()
        
        self.camera_connection_thread = None
        
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
        
        # 星点解析库
        self.astrometrySolver = None
        try:
            self.astrometrySolver = AstrometrySolver(language=self.language)
            self.astrometrySolver.finished.connect(self.on_astrometry_finished)
            self.astrometrySolver.error.connect(self.on_astrometry_error)
            self.astrometrySolver.star_info.connect(self.on_astrometry_star_info)
        except Exception as e:
            print(f"Failed to initialize AstrometrySolver: {str(e)}")
        
        
        self.stellarSolver = None
        try:
            self.stellarSolver = StellarSolver()
        except Exception as e:
            print(f"Failed to initialize StellarSolver: {str(e)}")

    def initialize_ui(self):
         # 创建一个滚动区域
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QWidget()
        # 将原有的布局添加到滚动区域的内容布局中
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_area.setWidget(self.scroll_content)
        
        self.init_start_settings_ui()
        self.init_settings_ui()
        self.init_capture_control_ui()
        self.init_video_control_ui()
        self.init_image_control_ui()
        self.init_temperature_control_ui()
        self.init_CFW_control_ui()
        
        
        
        self.init_ui_state()
        
    def init_start_settings_ui(self):
        self.connect_box = QGroupBox(translations[self.language]['qhyccd_capture']['connect_settings'])
        start_setting_layout = QFormLayout()
        
        # 设置设置按钮
        # 创建一个水平布局
        h_layout = QHBoxLayout()
        
        self.settings_dialog = SettingsDialog(self)
        self.settings_button = QPushButton(translations[self.language]['qhyccd_capture']['settings'])
        self.settings_button.clicked.connect(self.show_settings_dialog)
        
        self.state_label = QTextEdit()
        self.state_label.setReadOnly(True)
        self.state_label.setLineWrapMode(QTextEdit.NoWrap)
        self.state_label.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)  # 禁用水平滚动条
        self.state_label.setFixedHeight(self.state_label.fontMetrics().height() + 10)  # 设置固定高度为一行文本的高度加上一些边距
        self.state_label.setStyleSheet("""
            QScrollBar:vertical { width: 2px; }
        """)  # 设置垂直滚动条的宽度为2像素
        
        # 将控件添加到水平布局中
        h_layout.addWidget(QLabel(translations[self.language]['qhyccd_capture']['status']))
        h_layout.addWidget(self.state_label)
        h_layout.addWidget(self.settings_button)
        
        # 将水平布局添加到表单布局中
        start_setting_layout.addRow(h_layout)
        # 相机选择
        self.camera_selector = QComboBox()

        start_setting_layout.addRow(QLabel(translations[self.language]['qhyccd_capture']['select_camera']),self.camera_selector)
        
        # 相机模式选择
        self.camera_mode = translations[self.language]['qhyccd_capture']['single_frame_mode']
        self.camera_mode_ids = {translations[self.language]['qhyccd_capture']['single_frame_mode']:0,translations[self.language]['qhyccd_capture']['continuous_mode']:1}
        self.camera_mode_selector = QComboBox()
        self.camera_mode_selector.addItems(list(self.camera_mode_ids.keys()))
        self.camera_mode_selector.currentIndexChanged.connect(self.on_camera_mode_changed)
        start_setting_layout.addRow(QLabel(translations[self.language]['qhyccd_capture']['select_camera_mode']),self.camera_mode_selector)
        
        # 连接和断开按钮
        grid_layout = QGridLayout()
        self.connect_button = QPushButton(translations[self.language]['qhyccd_capture']['connect'])
        self.disconnect_button = QPushButton(translations[self.language]['qhyccd_capture']['disconnect'])
        self.reset_camera_button = QPushButton(translations[self.language]['qhyccd_capture']['reset_camera'])
        
        self.connect_button.clicked.connect(self.connect_camera)
        self.disconnect_button.clicked.connect(self.disconnect_camera)
        self.reset_camera_button.clicked.connect(self.read_camera_name)
        
        grid_layout.addWidget(self.connect_button,0,0)
        grid_layout.addWidget(self.disconnect_button,0,1)
        grid_layout.addWidget(self.reset_camera_button,0,2)
        start_setting_layout.addRow(grid_layout)
        grid_layout = QGridLayout()
        # 相机配置显示
        self.config_label = QLabel(translations[self.language]['qhyccd_capture']['not_connected'])
        self.config_label.setStyleSheet("color: red;")  # 设置字体颜色为红色
        grid_layout.addWidget(self.config_label,0,0)
        
        self.fps_label = QLabel(translations[self.language]['qhyccd_capture']['fps'])
        self.fps_label.setVisible(False)
        grid_layout.addWidget(self.fps_label,0,1)
        
        self.memory_label = QLabel(translations[self.language]['qhyccd_capture']['memory'])
        grid_layout.addWidget(self.memory_label,0,2)
        
        self.memory_progress_bar = QProgressBar(self)  # 创建进度条控件
        self.memory_progress_bar.setRange(0, 100)  # 设置进度条范围（0% 到 100%）
        self.memory_progress_bar.setValue(0)
        
        grid_layout.addWidget(self.memory_progress_bar,0,3)
        start_setting_layout.addRow(grid_layout)
        
        # 内存监控
        self.memory_monitor_thread = MemoryMonitorThread()
        self.memory_monitor_thread.memory_updated.connect(self.update_memory_progress)
        self.memory_monitor_thread.start()
        
        # 区显示开关
        grid_layout = QGridLayout()
        
        self.show_settings_checkbox = QPushButton()
        self.show_settings_checkbox.setIcon(QIcon('src/qhyccd_capture/icon/camera_icon.png'))  # 设置图标路径
        self.show_settings_checkbox.setToolTip(translations[self.language]['qhyccd_capture']['show_camera_settings'])  # 设置提示文本

        self.show_control_checkbox = QPushButton()
        self.show_control_checkbox.setIcon(QIcon('src/qhyccd_capture/icon/instagram_icon.png'))  # 设置图标路径
        self.show_control_checkbox.setToolTip(translations[self.language]['qhyccd_capture']['show_capture_control'])

        self.show_image_control_checkbox = QPushButton()
        self.show_image_control_checkbox.setIcon(QIcon('src/qhyccd_capture/icon/film_icon.png'))  # 设置图标路径
        self.show_image_control_checkbox.setToolTip(translations[self.language]['qhyccd_capture']['show_image_control'])

        self.show_temperature_control_checkbox = QPushButton()
        self.show_temperature_control_checkbox.setIcon(QIcon('src/qhyccd_capture/icon/thermometer_icon.png'))  # 设置图标路径
        self.show_temperature_control_checkbox.setToolTip(translations[self.language]['qhyccd_capture']['show_temperature_control'])

        self.show_CFW_control_checkbox = QPushButton()
        self.show_CFW_control_checkbox.setIcon(QIcon('src/qhyccd_capture/icon/toggle_right_icon.png'))  # 设置图标路径
        self.show_CFW_control_checkbox.setToolTip(translations[self.language]['qhyccd_capture']['show_cfw_control'])

        self.show_video_control_checkbox = QPushButton()
        self.show_video_control_checkbox.setIcon(QIcon('src/qhyccd_capture/icon/video_icon.png'))  # 设置图标路径
        self.show_video_control_checkbox.setToolTip(translations[self.language]['qhyccd_capture']['show_video_control'])
        
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
        
        # 创建一个垂直方向的 spacer
        spacer = QSpacerItem(20, 2, QSizePolicy.Minimum, QSizePolicy.Expanding)

        # 将 spacer 添加到布局的底部
        start_setting_layout.addItem(spacer)
        
        # 将 start_setting_layout 包装在一个 QWidget 中
        self.connect_box.setLayout(start_setting_layout)
        self.scroll_layout.addWidget(self.connect_box)
        
    def init_settings_ui(self):
        self.settings_box = QGroupBox(translations[self.language]['qhyccd_capture']['camera_settings'])
        settings_layout = QFormLayout()

        # 读出模式选择框
        self.camera_read_mode_ids= {}
        self.readout_mode_selector = QComboBox()
        self.readout_mode_selector.addItems(list(self.camera_read_mode_ids.keys()))  # 示例项
        self.readout_mode_selector.currentIndexChanged.connect(self.on_readout_mode_changed)
        settings_layout.addRow(QLabel(translations[self.language]['qhyccd_capture']['readout_mode']), self.readout_mode_selector)

        # 像素合并Bin选择框
        self.camera_pixel_bin = {'1*1':[1,1],'2*2':[2,2],'3*3':[3,3],'4*4':[4,4]}
        self.pixel_bin_selector = QComboBox()
        self.pixel_bin_selector.addItems(list(self.camera_pixel_bin.keys()))  # 示例项
        self.pixel_bin_selector.currentIndexChanged.connect(self.on_pixel_bin_changed)
        settings_layout.addRow(QLabel(translations[self.language]['qhyccd_capture']['pixel_bin']), self.pixel_bin_selector)

        # 图像位深度选择框
        self.camera_depth_options = {}
        self.depth_selector = QComboBox()  # 创建图像位深度选择框
        self.depth_selector.addItems(list(self.camera_depth_options.keys()))  
        self.depth_selector.currentIndexChanged.connect(self.on_depth_changed)
        self.depth_name = QLabel(translations[self.language]['qhyccd_capture']['image_depth'])
        settings_layout.addRow(self.depth_name, self.depth_selector)
        
        self.camera_Debayer_mode = {translations[self.language]['qhyccd_capture']['debayer_mode_true']:True,translations[self.language]['qhyccd_capture']['debayer_mode_false']:False}
        self.Debayer_mode = False
        self.Debayer_mode_selector = QComboBox()
        self.Debayer_mode_selector.addItems(list(self.camera_Debayer_mode.keys()))
        self.Debayer_mode_selector.currentIndexChanged.connect(self.on_Debayer_mode_changed)
        self.Debayer_mode_label = QLabel(translations[self.language]['qhyccd_capture']['debayer_mode'])
        settings_layout.addRow(self.Debayer_mode_label, self.Debayer_mode_selector)
        
        # 分辨率选择框
        # 变量定义
        self.x = QSpinBox()
        self.y = QSpinBox()
        self.w = QSpinBox()
        self.h = QSpinBox()
        self.set_resolution_button = QPushButton(translations[self.language]['qhyccd_capture']['set_resolution'])
        self.set_original_resolution_button = QPushButton(translations[self.language]['qhyccd_capture']['reset_resolution'])
        self.set_original_resolution_button.setToolTip(translations[self.language]['qhyccd_capture']['reset_resolution_tooltip'])
        self.show_roi_button = QPushButton(translations[self.language]['qhyccd_capture']['roi'])
        self.show_roi_button.setToolTip(translations[self.language]['qhyccd_capture']['roi_tooltip'])

        # 布局设置
        grid_layout = QGridLayout()
        grid_layout.addWidget(QLabel(translations[self.language]['qhyccd_capture']['x']),0,0)
        grid_layout.addWidget(self.x,0,1)
        grid_layout.addWidget(QLabel(translations[self.language]['qhyccd_capture']['y']),0,2)
        grid_layout.addWidget(self.y,0,3)
        grid_layout.addWidget(QLabel(translations[self.language]['qhyccd_capture']['w']),1,0)
        grid_layout.addWidget(self.w,1,1)
        grid_layout.addWidget(QLabel(translations[self.language]['qhyccd_capture']['h']),1,2)
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
        self.scroll_layout.addWidget(self.settings_box)
        
    def init_capture_control_ui(self):
        self.control_box = QGroupBox(translations[self.language]['qhyccd_capture']['capture_control'])
        control_layout = QFormLayout()
        
        exposure_layout = QHBoxLayout()
        self.exposure_time = QDoubleSpinBox()  # 修改为 QDoubleSpinBox
        self.exposure_time.setSuffix(' ms')  # 设置单位为毫秒
        self.exposure_time.setDecimals(3)  # 保留三位小数
        self.exposure_time.valueChanged.connect(self.update_exposure_time)
        exposure_layout.addWidget(self.exposure_time)
        
        self.auto_exposure_dialog = None
        self.auto_exposure_button = QPushButton(translations[self.language]['qhyccd_capture']['auto_exposure'])
        self.auto_exposure_button.clicked.connect(self.toggle_auto_exposure)
        
        # self.auto_exposure_button.setEnabled(False)
        exposure_layout.addWidget(self.auto_exposure_button)
        
        control_layout.addRow(QLabel(translations[self.language]['qhyccd_capture']['exposure_time']), exposure_layout)
        
        # 增益设置
        self.gain = QDoubleSpinBox()
        self.gain.setSuffix(' dB')
        self.gain.valueChanged.connect(self.update_gain)
        control_layout.addRow(QLabel(translations[self.language]['qhyccd_capture']['gain']), self.gain)

        # 偏移量设置
        self.offset = QDoubleSpinBox()
        self.offset.setSuffix(' units')
        self.offset.valueChanged.connect(self.update_offset)
        control_layout.addRow(QLabel(translations[self.language]['qhyccd_capture']['offset']), self.offset)

        # USB 传输设置
        self.usb_traffic = QSpinBox()
        self.usb_traffic.setSuffix(' MB/s')
        self.usb_traffic.setRange(1, 500)  # 设置 USB 输范围
        self.usb_traffic.valueChanged.connect(self.update_usb_traffic)
        control_layout.addRow(QLabel(translations[self.language]['qhyccd_capture']['usb_traffic']), self.usb_traffic)
        
        # 添加图像显示方式选择框
        self.display_mode_selector = QComboBox()
        self.display_mode_selector.addItems([translations[self.language]['qhyccd_capture']['distributed_display'], translations[self.language]['qhyccd_capture']['single_display'], translations[self.language]['qhyccd_capture']['sequential_display']])
        
        control_layout.addRow(QLabel(translations[self.language]['qhyccd_capture']['display_mode']), self.display_mode_selector)

        # 添加 Bayer 类型转换组件
        self.bayer_conversion_selector = QComboBox()
        self.bayer_conversion_selector.addItems(["None", "RGGB", "BGGR", "GRBG", "GBRG"])
        self.bayer_conversion_selector.currentIndexChanged.connect(self.on_bayer_conversion_changed)
        self.bayer_conversion = "None"
        self.bayer_name = QLabel(translations[self.language]['qhyccd_capture']['bayer_conversion'])
        # 将 Bayer 类型转换组件添加到布局中
        control_layout.addRow(self.bayer_name, self.bayer_conversion_selector)
        
        grid_layout = QGridLayout()
        self.start_button = QPushButton(translations[self.language]['qhyccd_capture']['start_capture'])
        self.save_button = QPushButton(translations[self.language]['qhyccd_capture']['save'])
        self.save_button.setToolTip(translations[self.language]['qhyccd_capture']['save_tooltip'])
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
        self.scroll_layout.addWidget(self.control_box)

    def init_video_control_ui(self):
        self.preview_thread = None
        
        # 录像区域
        self.video_control_box = QGroupBox(translations[self.language]['qhyccd_capture']['recording'])
        video_layout = QFormLayout()
        
        grid_layout = QGridLayout()
        # 预览模式控件
        self.preview_status = False
        self.preview_checkbox = QCheckBox(translations[self.language]['qhyccd_capture']['preview_mode'])
        self.preview_checkbox.setToolTip(translations[self.language]['qhyccd_capture']['preview_mode_tooltip'])
        self.preview_checkbox.stateChanged.connect(self.toggle_preview_mode)
        grid_layout.addWidget(self.preview_checkbox,0,0)
        # 是否顶置的控件
        # self.top_checkbox_status = False
        self.top_checkbox = QCheckBox(translations[self.language]['qhyccd_capture']['top_checkbox'])
        self.top_checkbox.setToolTip(translations[self.language]['qhyccd_capture']['top_checkbox_tooltip'])
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
        self.save_mode = translations[self.language]['qhyccd_capture']['single_frame_storage']
        self.save_mode_selector = QComboBox()
        self.save_mode_selector.addItems([translations[self.language]['qhyccd_capture']['single_frame_storage'], translations[self.language]['qhyccd_capture']['video_storage']])
        self.save_mode_selector.currentIndexChanged.connect(self.on_save_mode_changed)
        # 添加到布局中1chin
        video_layout.addRow(QLabel(translations[self.language]['qhyccd_capture']['save_mode']), self.save_mode_selector)
        
        # 路径选择控件
        self.path_selector = QLineEdit()
        self.path_selector.setText(self.default_path)
        self.path_button = QPushButton(translations[self.language]['qhyccd_capture']['select_path'])
        self.path_button.clicked.connect(self.select_path)
        path_layout = QHBoxLayout()
        path_layout.addWidget(self.path_selector)
        path_layout.addWidget(self.path_button)
        video_layout.addRow(QLabel(translations[self.language]['qhyccd_capture']['record_path']), path_layout)
        
        # 录像文件名选择控件
        self.record_file_name = QLineEdit()
        self.record_file_name.setPlaceholderText(translations[self.language]['qhyccd_capture']['record_file_name'])
        self.record_file_name.setText(self.default_filename)
        
        # 添加保存格式选择控件
        self.fits_header = None
        self.save_format_selector = QComboBox()
        if self.save_mode == translations[self.language]['qhyccd_capture']['single_frame_storage']:
            self.save_format_selector.addItems(['png', 'jpeg', 'tiff', 'fits'])  # 图片格式
        elif self.save_mode == translations[self.language]['qhyccd_capture']['video_storage']:
            self.save_format_selector.addItems(['avi', 'mp4', 'mkv'])  # 视频格式
        self.save_format_selector.currentIndexChanged.connect(self.on_save_format_changed)
 
        self.jpeg_quality = QDoubleSpinBox()
        self.jpeg_quality.setRange(0, 100)
        self.jpeg_quality.setValue(100)
        self.jpeg_quality.setDecimals(0) 
        self.jpeg_quality.setSuffix('%')
        self.jpeg_quality.setToolTip(translations[self.language]['qhyccd_capture']['quality_tooltip'])
        self.jpeg_quality.setVisible(False)

        self.tiff_compression = QComboBox()
        self.tiff_compression.setVisible(False)
        
        self.show_fits_header = QPushButton(translations[self.language]['qhyccd_capture']['fits_header'])
        self.show_fits_header.setToolTip(translations[self.language]['qhyccd_capture']['fits_header_tooltip'])
        self.show_fits_header.setVisible(False)
        self.show_fits_header.clicked.connect(self.toggle_fits_header)

        self.fits_header_dialog = FitsHeaderEditor(self.viewer,self.language)
        name_layout = QHBoxLayout()
        name_layout.addWidget(self.record_file_name)
        name_layout.addWidget(self.save_format_selector)
        name_layout.addWidget(self.jpeg_quality) 
        name_layout.addWidget(self.tiff_compression)
        name_layout.addWidget(self.show_fits_header)
        video_layout.addRow(QLabel(translations[self.language]['qhyccd_capture']['record_file_name']), name_layout)   
        
        # 录像模式选择控件
        self.record_mode = translations[self.language]['qhyccd_capture']['continuous_mode']
        self.record_mode_ids = {translations[self.language]['qhyccd_capture']['continuous_mode']:0,translations[self.language]['qhyccd_capture']['time_mode']:1,translations[self.language]['qhyccd_capture']['frame_mode']:2}
        self.record_mode_selector = QComboBox()
        self.record_mode_selector.addItems(list(self.record_mode_ids.keys()))
        self.record_mode_selector.currentIndexChanged.connect(self.on_record_mode_changed)
        video_layout.addRow(QLabel(translations[self.language]['qhyccd_capture']['record_mode']), self.record_mode_selector)
        
        # 显示时间输入框
        self.start_save_time = None
        self.record_time_input = QSpinBox()
        self.record_time_input.setSuffix(translations[self.language]['qhyccd_capture']['seconds'])
        self.record_time_input.setRange(1, 3600)  # 设置范围为1秒到3600秒
        self.record_time_input_label = QLabel(translations[self.language]['qhyccd_capture']['record_time'])
        video_layout.addRow(self.record_time_input_label, self.record_time_input)
        self.record_time_input.setVisible(False)
        self.record_time_input_label.setVisible(False)
        
        # 显示帧数输入框
        self.record_frame_count = 0
        self.frame_count_input = QSpinBox()
        self.frame_count_input.setRange(1, 10000)  # 设置范围为1到10000帧
        self.frame_count_input_label = QLabel(translations[self.language]['qhyccd_capture']['record_frames'])
        video_layout.addRow(self.frame_count_input_label, self.frame_count_input)
        self.frame_count_input.setVisible(False)
        self.frame_count_input_label.setVisible(False)

        grid_layout = QGridLayout()
        # 开启录像按钮
        self.record_button = QPushButton(translations[self.language]['qhyccd_capture']['start_record'])
        grid_layout.addWidget(self.record_button,0,0)
        self.record_button.clicked.connect(self.start_recording)
        
        # 停止录像按钮
        self.stop_record_button = QPushButton(translations[self.language]['qhyccd_capture']['stop_record'])
        self.stop_record_button.clicked.connect(self.stop_recording)
        grid_layout.addWidget(self.stop_record_button,0,1)
        video_layout.addRow(grid_layout)
        
        # 添加进度条
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 100)  # 设置进度条范围
        self.progress_bar.setValue(0)  # 初始值为0
        # 将进度条添加到布局中
        video_layout.addRow(QLabel(translations[self.language]['qhyccd_capture']['record_progress']), self.progress_bar)
        
        self.video_control_box.setLayout(video_layout)
        self.scroll_layout.addWidget(self.video_control_box)

    def init_image_control_ui(self):
        # 图像控制区域
        self.image_control_box = QGroupBox(translations[self.language]['qhyccd_capture']['image_processing'])
        image_control_layout = QVBoxLayout()
        
        # 添加直方图控制
        histogram_group = QGroupBox(translations[self.language]['qhyccd_capture']['histogram'])
        histogram_layout = QFormLayout()
        
        # 添加是否显示直方图的复选框
        self.show_histogram_checkbox = QCheckBox(translations[self.language]['qhyccd_capture']['show_histogram'])
        self.show_histogram_checkbox.stateChanged.connect(self.toggle_histogram_display)
        histogram_layout.addRow(self.show_histogram_checkbox)
        
        # 添加绘图区域
        self.img_buffer = queue.Queue()
        self.histogram_widget = HistogramWidget(self.viewer,self.img_buffer,self.language)

        self.last_time = 0  # 初始化上次更新时间
        self.update_interval = 1   # 每秒 1 次更新的时间间隔
        self.preview_contrast_limits_connection = None
        self.contrast_limits_connection = None
        
        histogram_group.setLayout(histogram_layout)
        
        # 添加白平衡控制
        self.wb_group = QGroupBox(translations[self.language]['qhyccd_capture']['white_balance_control'])
        wb_layout = QFormLayout()
        self.wb_red = QSlider(Qt.Horizontal)
        self.wb_green = QSlider(Qt.Horizontal)
        self.wb_blue = QSlider(Qt.Horizontal)
        
        wb_layout.addRow(QLabel(translations[self.language]['qhyccd_capture']['red']), self.wb_red)
        wb_layout.addRow(QLabel(translations[self.language]['qhyccd_capture']['green']), self.wb_green)
        wb_layout.addRow(QLabel(translations[self.language]['qhyccd_capture']['blue']), self.wb_blue)
        
        self.auto_white_balance_dialog = None
        self.auto_white_balance_button = QPushButton(translations[self.language]['qhyccd_capture']['auto_white_balance'])
        self.auto_white_balance_button.clicked.connect(self.toggle_auto_white_balance)
        
        wb_layout.addRow(self.auto_white_balance_button)
        self.wb_group.setLayout(wb_layout)
        
        # 将新的布局添加到主布局中
        image_control_layout.addWidget(histogram_group)
        image_control_layout.addWidget(self.wb_group)
        
        
        self.star_group = QGroupBox(translations[self.language]['qhyccd_capture']['star_analysis'])
        star_layout = QFormLayout()
        
        self.star_fwhm = QDoubleSpinBox()
        self.star_fwhm.setRange(1, 100)
        self.star_fwhm.setSingleStep(1)
        self.star_fwhm.setValue(3)
        self.star_fwhm.setToolTip(translations[self.language]['qhyccd_capture']['star_fwhm_tooltip'])
        star_layout.addRow(QLabel(translations[self.language]['qhyccd_capture']['star_fwhm']), self.star_fwhm)
        
        
        # 星点解析方法选择
        self.star_analysis_method_selector = QComboBox()
        self.star_analysis_method_selector.addItems([
            'photutils',
            'Astrometry',
        ])
        star_layout.addRow(QLabel(translations[self.language]['qhyccd_capture']['star_analysis_method']), self.star_analysis_method_selector)
        
        # 星点解析和保存表格按钮的水平布局
        star_button_layout = QHBoxLayout()
        
        # 星点解析按钮
        self.star_analysis_button = QPushButton(translations[self.language]['qhyccd_capture']['star_analysis'])
        self.star_analysis_button.clicked.connect(self.star_analysis)
        star_button_layout.addWidget(self.star_analysis_button)
        
        # 保存表格按钮
        self.save_star_table_button = QPushButton(translations[self.language]['qhyccd_capture']['save_star_table'])
        self.save_star_table_button.clicked.connect(self.save_star_table)
        star_button_layout.addWidget(self.save_star_table_button)
        
        # 将按钮布局添加到星点解析布局中
        star_layout.addRow(star_button_layout)
        
        # 添加循环进度条
        self.star_progress_bar = QProgressBar()
        self.star_progress_bar.setRange(0, 100)  # 设置为循环模式
        star_layout.addRow(self.star_progress_bar)
        
        self.star_group.setLayout(star_layout)
        image_control_layout.addWidget(self.star_group)
        
        self.image_control_box.setLayout(image_control_layout)
        self.scroll_layout.addWidget(self.image_control_box)

    def init_temperature_control_ui(self):
        '''温度控制布局'''
        # 温度控制
        self.temperature_control_box = QGroupBox(translations[self.language]['qhyccd_capture']['temperature_control'])
        temperature_layout = QFormLayout()
        
        self.temperature_setpoint = QDoubleSpinBox()
        self.temperature_setpoint.setSuffix(' °C')
        self.temperature_setpoint.valueChanged.connect(self.update_temperature_setpoint)
        temperature_layout.addRow(QLabel(translations[self.language]['qhyccd_capture']['set_temperature']), self.temperature_setpoint)
        
        grid_layout = QGridLayout()
        self.current_temperature_label = QLabel(translations[self.language]['qhyccd_capture']['temperature'])
        self.current_humidity_label = QLabel(translations[self.language]['qhyccd_capture']['humidity'])
        grid_layout.addWidget(self.current_temperature_label,0,0)
        grid_layout.addWidget(self.current_humidity_label,0,1)
        temperature_layout.addRow(grid_layout)
        
        self.temperature_control_box.setLayout(temperature_layout)
        self.scroll_layout.addWidget(self.temperature_control_box)
        
    def init_CFW_control_ui(self):
        '''滤镜轮控制布局'''
        # 滤镜轮控制区域
        self.CFW_control_box = QGroupBox(translations[self.language]['qhyccd_capture']['CFW_control'])
        CFW_layout = QFormLayout()
        
        self.CFW_id = None # 当前选中滤镜轮ID
        
        self.CFW_number_ids = {}
        self.CFW_filter_selector = QComboBox()
        self.CFW_filter_selector.addItems(list(self.CFW_number_ids.keys()))  # 示例项
        self.CFW_filter_selector.currentIndexChanged.connect(self.on_CFW_filter_changed)
        
        CFW_layout.addRow(QLabel(translations[self.language]['qhyccd_capture']['CFW_position']), self.CFW_filter_selector)
        self.CFW_control_box.setLayout(CFW_layout)
        self.scroll_layout.addWidget(self.CFW_control_box)
    
    def init_ui_state(self):
        '''初始化UI状态'''
        # 创建一个垂直方向的 spacer
        spacer = QSpacerItem(20, 2, QSizePolicy.Minimum, QSizePolicy.Expanding)

        # 将 spacer 添加到布局的底部
        self.scroll_layout.addItem(spacer)

        '''主布局'''
        self.setLayout(QVBoxLayout())
        self.layout().addWidget(self.scroll_area)
        
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
    
    def append_text(self, text):
        # 向 QTextEdit 添加文本
        self.state_label.append(text)
        now_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"{now_time}: {text}")
        # # 自动滚动到底部

        self.state_label.moveCursor(QTextCursor.End)
        self.state_label.moveCursor(QTextCursor.StartOfLine) # 滚动到最左边
    
    def show_settings_dialog(self):
        self.settings_dialog.exec_()
        
    def load_settings(self):
        if os.path.exists(self.settings_file):
            with open(self.settings_file, 'r') as f:
                settings = json.load(f)
                self.qhyccd_path = settings.get("qhyccd_path", "")
                self.language = settings.get("language", "zh")
        else:
            self.qhyccd_path = ""
            self.language = "zh"  # 默认语言
        # self.append_text(translations[self.language]['qhyccd_capture']['settings_loaded'])
            
    # 初始化QHYCCD资源
    def init_qhyccdResource(self,file_path=None):
        
        if file_path is None:
            if self.system_name == 'posix':
                # 类 Unix 系统（如 Linux 或 macOS）
                lib_path = '/usr/local/lib/libqhyccd.so'
                if os.path.exists(lib_path):
                    self.qhyccddll = cdll.LoadLibrary(lib_path)
                else:
                    raise FileNotFoundError(f"{translations[self.language]['debug']['not_found_sdk']}: {lib_path} 不存在")
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
                    raise FileNotFoundError(f"{translations[self.language]['debug']['unknown_architecture']}: {arch}")
                if os.path.exists(lib_path):
                    self.qhyccddll = cdll.LoadLibrary(lib_path)
                else:
                    raise FileNotFoundError(f"{translations[self.language]['debug']['not_found_sdk']}: {lib_path} ")
            else:
                # 其他操作系统（不推荐使用）
                lib_path = '/usr/local/lib/libqhyccd.so'
                if os.path.exists(lib_path):
                    self.qhyccddll = cdll.LoadLibrary(lib_path)
                else:
                    raise FileNotFoundError(f"{translations[self.language]['debug']['not_found_sdk']}: {lib_path} ")
            # 设置函数的参数和返回值类型
            self.settings_dialog.qhyccd_path_label.setText(lib_path)
        else:
            self.qhyccddll = cdll.LoadLibrary(file_path)


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
        
        # 输出Debug
        self.qhyccddll.OutputQHYCCDDebug.argtypes = [ctypes.c_char_p]
        
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
        # print(f"self.camera_mode:{self.camera_mode}")
        if self.camhandle != 0 or self.camera_state:
            self.disconnect_camera()
            self.connect_camera()
        self.append_text(f'{translations[self.language]["qhyccd_capture"]["update_camera_mode"]}')

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
        # print("ScanQHYCCD() num =", num)
        self.camera_ids = {}
        # 遍历所有扫描到的相机
        for index in range(num):
            # print("index =", index)

            # 获相机 ID
            id_buffer = ctypes.create_string_buffer(40)
            ret = self.qhyccddll.GetQHYCCDId(index, id_buffer)
            if ret != 0:
                warnings.warn(f"{translations[self.language]['debug']['get_qhyccd_id_failed']}: {ret}")
                self.append_text(f"{translations[self.language]['debug']['get_qhyccd_id_failed']}: {ret}")
            result_id = id_buffer.value.decode("utf-8")
            self.camera_ids[result_id] = id_buffer
        self.camera_selector.clear()
        self.camera_selector.addItems(list(self.camera_ids.keys()))
        self.append_text(f'{translations[self.language]["qhyccd_capture"]["update_camera_name"]}')
    # 连接相机
    def connect_camera(self,mode=0):
        self.connect_button.setEnabled(False)
        start_time = time.time()
        if self.camhandle != 0:
            self.disconnect_camera()
        if not self.init_state:
            self.init_qhyccdResource()
        camera_name = self.camera_selector.currentText()
        self.camera_name = camera_name
        
        self.camera_connection_thread = CameraConnectionThread(self.qhyccddll, self.camera_ids[camera_name],mode,self.camera_mode_ids[self.camera_mode], self.language,self)
        self.camera_connection_thread.handle_signal.connect(self.handle_signal)
        self.camera_connection_thread.get_read_mode_signal.connect(self.get_read_mode_signal)
        self.camera_connection_thread.update_status_signal.connect(self.append_text)
        self.camera_connection_thread.already_connected_signal.connect(self.already_connected_signal)
        self.camera_connection_thread.already_disconnected_signal.connect(self.already_disconnected_signal)
        self.camera_connection_thread.start()
      
    def handle_signal(self,signal):
        self.camhandle = int(signal)
        
    def get_read_mode_signal(self,read_mode):
        self.camera_read_mode_ids.clear()
        self.camera_read_mode_ids = read_mode
        
    def already_connected_signal(self,connected,read_mode):
        if not connected:
            # self.append_text(f"{translations[self.language]['debug']['camera_connected_failed']}")
            warnings.warn(f"{translations[self.language]['debug']['camera_connected_failed']}")
            self.append_text(f"{translations[self.language]['debug']['camera_connected_failed']}")
            return
        # 更新参数
        self.update_camera_color()
        self.update_camera_config()
        self.update_limit_selector()
        self.update_readout_mode_selector(read_mode)
        self.update_camera_pixel_bin(bin=bin)
        self.update_depth_selector()
        self.update_debayer_mode()
        self.update_resolution(0,0,self.image_w,self.image_h)
        self.update_camera_mode()
        self.update_camera_temperature()
        self.update_CFW_control()
        self.update_tiff_compression()
        self.start_capture_status_thread()
        self.update_auto_exposure()
        self.update_auto_white_balance()
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
        
        self.config_label.setText(f'{translations[self.language]["qhyccd_capture"]["connected"]}')
        self.config_label.setStyleSheet("color: green;")  # 设置字体颜色为绿色
        self.connect_button.setEnabled(True)
        
        # 初始禁用自动白平衡和自动曝光按钮
        self.auto_white_balance_button.setVisible(False)
        self.auto_exposure_button.setVisible(False)
    
    def already_disconnected_signal(self,disconnected):
        if not disconnected:
            return
        
        self.camhandle = 0
        self.config_label.setText(f'{translations[self.language]["qhyccd_capture"]["disconnected"]}')
        self.config_label.setStyleSheet("color: red;")  # 设置字体颜色为红色
 
        self.current_image = None
        self.current_image_name = None
        try:    
            if self.is_color_camera:    
                # 断开连接信号
                for slider in [self.wb_red, self.wb_green, self.wb_blue]:
                    slider.valueChanged.disconnect()  # 断开之前的连接
        except Exception as e:
            warnings.warn(f"{translations[self.language]['debug']['disconnect_white_balance_failed']}: {e}")
            self.append_text(f"{translations[self.language]['debug']['disconnect_white_balance_failed']}: {e}")
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
        
        self.settings_dialog.camera_info_label.setText(f'{translations[self.language]["qhyccd_capture"]["camera_info_disconnected"]}')
        self.stop_preview()
        self.disconnect_button.setEnabled(True)

    def disconnect_camera(self):
        """断开相机连接"""
        if self.camhandle == 0:
            return
        self.disconnect_button.setEnabled(False)
        if self.capture_in_progress:
            self.cancel_capture()

        self.camera_connection_thread.disconnect()
        self.camera_connection_thread.wait()

    def start_capture_status_thread(self):
        if self.capture_status_thread is None:
            self.capture_status_thread = CaptureStatusThread(self.qhyccddll, self.camhandle,self.language)
            self.capture_status_thread.update_status.connect(self.capture_status_label.setText)
            self.capture_status_thread.end_capture.connect(self.end_capture)
            self.capture_status_thread.start()
            self.capture_status_thread.pause_capture()
            
    def end_capture(self):
        if self.capture_status_label.text().startswith(translations[self.language]["qhyccd_capture"]["capturing"]):
            self.capture_status_label.setText(translations[self.language]["qhyccd_capture"]["capture_complete"])
               
    def update_camera_color(self):   
        # 判断相机是否是彩色相机
        try:
            if not self.qhyccddll.IsQHYCCDControlAvailable(self.camhandle, CONTROL_ID.CAM_IS_COLOR.value):
                is_color_value = self.qhyccddll.GetQHYCCDParam(self.camhandle, CONTROL_ID.CAM_IS_COLOR.value)
                if is_color_value == 4294967295.0:
                    warnings.warn(f"{translations[self.language]['debug']['get_qhyccd_is_color_camera_failed']}")
                    self.append_text(f"{translations[self.language]['debug']['get_qhyccd_is_color_camera_failed']}")
                    self.is_color_camera = self.is_color_camera_by_name(self.camera_name)
                else:
                    self.is_color_camera = not bool(is_color_value)
            else:
                self.is_color_camera = self.is_color_camera_by_name(self.camera_name)
        except Exception as e:
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
            
            self.Debayer_mode_selector.setEnabled(False)
            self.Debayer_mode_selector.setVisible(False)
            self.Debayer_mode_label.setVisible(False)

        else:
            self.wb_group.setVisible(True)
            self.wb_group.setEnabled(True)
            self.bayer_conversion_selector.setVisible(True)
            self.bayer_conversion_selector.setEnabled(True)
            
            self.Debayer_mode_selector.setVisible(True)
            self.Debayer_mode_selector.setEnabled(True)
            self.Debayer_mode_label.setVisible(True)
            
            self.bayer_name.setVisible(True)
            if self.camera_mode == translations[self.language]["qhyccd_capture"]["continuous_mode"]:  
                for slider in [self.wb_red, self.wb_green, self.wb_blue]:
                    slider.valueChanged.connect(self.apply_white_balance_hardware)
            else:
                for slider in [self.wb_red, self.wb_green, self.wb_blue]:
                    slider.valueChanged.connect(lambda: self.on_set_white_balance_clicked())
            
        self.append_text(f'{translations[self.language]["qhyccd_capture"]["update_camera_color"]}')
            
    def update_limit_selector(self):
        # 设置曝光限制
        exposure = self.qhyccddll.GetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_EXPOSURE.value)
        min_data, max_data, _ = self.getParamlimit(CONTROL_ID.CONTROL_EXPOSURE.value)
        # print("exposure_time", min_data, max_data)
        self.exposure_time.setRange(min_data/1000, max_data/1000)  # 使用 QDoubleSpinBox 设置范围
        self.exposure_time.setValue(exposure/1000)
        self.exposure_time.setSingleStep(1/1000)
        
        # 设置增益
        gain = self.qhyccddll.GetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_GAIN.value)
        min_data, max_data, step = self.getParamlimit(CONTROL_ID.CONTROL_GAIN.value)
        # print("gain", min_data, max_data)
        self.gain.setRange(int(min_data), int(max_data))
        self.gain.setSingleStep(float(step))
        self.gain.setValue(int(gain))
        
        # 设置偏移
        offset = self.qhyccddll.GetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_OFFSET.value)
        min_data, max_data, step = self.getParamlimit(CONTROL_ID.CONTROL_OFFSET.value)
        # print("offset", min_data, max_data)
        self.offset.setRange(int(min_data), int(max_data))
        self.offset.setSingleStep(float(step))
        self.offset.setValue(int(offset))
        
        # 设置USB宽带
        usb_traffic = self.qhyccddll.GetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_USBTRAFFIC.value)
        min_data, max_data, step = self.getParamlimit(CONTROL_ID.CONTROL_USBTRAFFIC.value)
        # print("usb_traffic", min_data, max_data)
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
            self.append_text(f"wb_red:{wb_red},min_data:{min_data},max_data:{max_data},step:{step}")
            if self.camera_mode == translations[self.language]["qhyccd_capture"]["single_frame_mode"]:
                self.qhyccddll.SetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_WBR.value, (max_data-min_data)//2)
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
            self.append_text(f"wb_green:{wb_green},min_data:{min_data},max_data:{max_data},step:{step}")
            if self.camera_mode == translations[self.language]["qhyccd_capture"]["single_frame_mode"]:
                self.qhyccddll.SetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_WBG.value, (max_data-min_data)//2)
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
            self.append_text(f"wb_blue:{wb_blue},min_data:{min_data},max_data:{max_data},step:{step}")
            if self.camera_mode == translations[self.language]["qhyccd_capture"]["single_frame_mode"]:
                self.qhyccddll.SetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_WBB.value, (max_data-min_data)//2)
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
        if ret != 0:
            warnings.warn(f"{translations[self.language]['debug']['get_qhyccd_effective_area_failed']}: {ret}")
            self.append_text(f"{translations[self.language]['debug']['get_qhyccd_effective_area_failed']}: {ret}")
        self.camera_H = sizeY.value
        self.camera_W = sizeX.value
        self.image_x = startX.value
        self.image_y = startY.value
        self.image_w = sizeX.value
        self.image_h = sizeY.value
        self.x.setRange(int(startX.value),int(startX.value+sizeX.value))
        self.y.setRange(int(startY.value),int(startY.value+sizeY.value))
        self.w.setRange(1,int(sizeX.value))
        self.h.setRange(1,int(sizeY.value))
        # print(f"self.camera_H:{self.camera_H},self.camera_W:{self.camera_W},self.image_w:{self.image_w},self.image_h:{self.image_h}")
        self.append_text(f'{translations[self.language]["qhyccd_capture"]["update_limit_selector"]}')
    
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
        if ret != 0:
            warnings.warn(f"{translations[self.language]['debug']['get_qhyccd_chip_info_failed']}: {ret}")
            self.append_text(f"{translations[self.language]['debug']['get_qhyccd_chip_info_failed']}: {ret}")
        self.camera_bit = imageB.value
        self.camera_depth_options = self.swap_elements(self.camera_depth_options, f"{imageB.value}bit")

 
        # 计算最长的标签长度
        max_label_length = max(
            len(translations[self.language]["qhyccd_capture"]["camera_info_name"]),
            len(translations[self.language]["qhyccd_capture"]["camera_info_chip"]),
            len(translations[self.language]["qhyccd_capture"]["camera_info_image"]),
            len(translations[self.language]["qhyccd_capture"]["camera_info_pixel"])
        )

        # 计算最长的值字符串长度
        max_value_length = max(
            len(self.camera_name),
            len(f"{str(chipW.value)}um * {str(chipH.value)}um"),
            len(f"{str(imageW.value)}px * {str(imageH.value)}px {str(imageB.value)}bit"),
            len(f"{str(pixelW.value)}um * {str(pixelH.value)}um")
        )

        # 设置文本并居中对齐
        self.settings_dialog.camera_info_label.setText(
            f'\n'
            f'{translations[self.language]["qhyccd_capture"]["camera_info_name"].center(max_label_length)}: {self.camera_name.center(max_value_length)}\n'
            f'{translations[self.language]["qhyccd_capture"]["camera_info_chip"].center(max_label_length)}: {f"{str(chipW.value)}um * {str(chipH.value)}um".center(max_value_length)}\n'
            f'{translations[self.language]["qhyccd_capture"]["camera_info_image"].center(max_label_length)}: {f"{str(imageW.value)}px * {str(imageH.value)}px {str(imageB.value)}bit".center(max_value_length)}\n'
            f'{translations[self.language]["qhyccd_capture"]["camera_info_pixel"].center(max_label_length)}: {f"{str(pixelW.value)}um * {str(pixelH.value)}um".center(max_value_length)}\n'
        )

        self.append_text(f'{translations[self.language]["qhyccd_capture"]["update_camera_config"]}')
    # 更新 pixel_bin_selector 中的选项
    def update_readout_mode_selector(self,read_mode):
        self.readout_mode_selector.clear()  # 清空现有选项
        updated_items = list(self.camera_read_mode_ids.keys())  # 获取新的选项列表
        self.readout_mode_selector.addItems(updated_items)  # 添加新的选项
        for item in updated_items:
            if self.camera_read_mode_ids[item] == read_mode:
                self.readout_mode_selector.setCurrentText(item)
                break

    def update_camera_pixel_bin(self,bin=[1,1]):
        self.pixel_bin_selector.clear()  # 清空现有选项
        # 将字典的键转换为列表并获取第i个键
        key_list = list(self.camera_pixel_bin.keys())
        updated_items = []
        for index, i in enumerate([CONTROL_ID.CAM_BIN1X1MODE.value, CONTROL_ID.CAM_BIN2X2MODE.value, CONTROL_ID.CAM_BIN3X3MODE.value, CONTROL_ID.CAM_BIN4X4MODE.value]):
            if self.qhyccddll.IsQHYCCDControlAvailable(self.camhandle, i) == 0:
                updated_items.append(key_list[index])
            
        # ret = self.qhyccddll.SetQHYCCDBinMode(self.camhandle, 1, 1) 
        ret = self.qhyccddll.SetQHYCCDBinMode(self.camhandle, self.camera_pixel_bin[updated_items[0]][0], self.camera_pixel_bin[updated_items[0]][1])
        if ret != 0:
            warnings.warn(f"{translations[self.language]['debug']['set_qhyccd_bin_mode_failed']}: {ret}")
            self.append_text(f"{translations[self.language]['debug']['set_qhyccd_bin_mode_failed']}: {ret}")
        
        self.image_w = int(self.camera_W/self.camera_pixel_bin[updated_items[0]][0])
        self.image_h = int(self.camera_H/self.camera_pixel_bin[updated_items[0]][1])
        
        self.update_resolution(0,0,self.image_w,self.image_h)
        
        self.pixel_bin_selector.addItems(updated_items)  # 添加新的选项
        
        self.append_text(f'{translations[self.language]["qhyccd_capture"]["update_bin_mode"]}')
        
    def update_depth_selector(self):
        minValue,maxValue,step=self.getParamlimit(CONTROL_ID.CONTROL_TRANSFERBIT.value)
        
        self.depth_selector.clear()  # 清空现有选项
        self.camera_depth_options.clear()
        for i in range(int(minValue),int(maxValue+1),int(step)):
            self.camera_depth_options[f"{i}bit"] = i
        # print(f"位深度数: \nmin:{minValue} , max:{maxValue} , step:{step}")
        updated_items = list(self.camera_depth_options.keys())  # 获取新的选项列表
        ret = self.qhyccddll.SetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_TRANSFERBIT.value, self.camera_depth_options[updated_items[0]])
        if ret == -1:
            warnings.warn(f"{translations[self.language]['debug']['set_qhyccd_transferbit_failed']}: {ret}")
            self.append_text(f"{translations[self.language]['debug']['set_qhyccd_transferbit_failed']}: {ret}")
            return -1
        self.camera_bit = self.camera_depth_options[updated_items[0]]
        self.depth_selector.addItems(updated_items)  # 添加新的选项
        
        self.append_text(f'{translations[self.language]["qhyccd_capture"]["update_depth_mode"]}')
    
    def update_debayer_mode(self):
        if not self.is_color_camera or self.camera_mode == translations[self.language]["qhyccd_capture"]["single_frame_mode"]:
            self.Debayer_mode_selector.setEnabled(False)
            self.Debayer_mode_selector.setVisible(False)
            self.Debayer_mode_label.setVisible(False)
            self.Debayer_mode = False
            ret = self.qhyccddll.SetQHYCCDDebayerOnOff(self.camhandle, False)
            if ret == -1:
                # print(f"Debayer模式{mode}设置失败!")
                warnings.warn(f"{translations[self.language]['debug']['set_qhyccd_debayer_mode_failed']}: {ret}")
                self.append_text(f"{translations[self.language]['debug']['set_qhyccd_debayer_mode_failed']}: {ret}")
        elif self.camera_mode == translations[self.language]["qhyccd_capture"]["continuous_mode"] and self.is_color_camera:
            self.Debayer_mode_selector.setEnabled(True)
            self.Debayer_mode_selector.setVisible(True)
            self.Debayer_mode_label.setVisible(True)
            self.Debayer_mode_selector.setCurrentText(translations[self.language]["qhyccd_capture"]["debayer_mode_false"])
            self.Debayer_mode = False
            ret = self.qhyccddll.SetQHYCCDDebayerOnOff(self.camhandle, False)
            if ret == -1:
                # print(f"Debayer模式{mode}设置失败!")
                warnings.warn(f"{translations[self.language]['debug']['set_qhyccd_debayer_mode_failed']}: {ret}")
                self.append_text(f"{translations[self.language]['debug']['set_qhyccd_debayer_mode_failed']}: {ret}")
    
    def update_resolution(self,x,y,w,h):
        # print(f"update_resolution: ({x},{y}) --> ({x+w},{y+h})")
        # 设置分辨率
        ret = self.qhyccddll.SetQHYCCDResolution(self.camhandle, x, y, w, h)
        if ret == -1:
            warnings.warn(f"{translations[self.language]['debug']['set_qhyccd_resolution_failed']}: {ret}")
            self.append_text(f"{translations[self.language]['debug']['set_qhyccd_resolution_failed']}: {ret}")
            return -1
        self.x.setRange(0,w-1)
        self.x.setValue(x)
        self.y.setRange(0,h-1)
        self.y.setValue(y)
        self.w.setRange(0,w)
        self.w.setValue(w)
        self.h.setRange(0,h)
        self.h.setValue(h)
        self.append_text(f'{translations[self.language]["qhyccd_capture"]["update_resolution"]} : ({x},{y}) --> ({x+w},{y+h})')
        return ret
    
    def update_camera_mode(self):
        # 判断相机是单帧模式还是连续模式
        if self.camera_mode == translations[self.language]["qhyccd_capture"]["continuous_mode"]:
            self.video_control_box.setVisible(True)
            self.show_video_control_checkbox.setVisible(True)
            self.show_video_control_checkbox.setEnabled(True)
            self.toggle_video_control_box(True)
            self.start_preview()
            self.layout().removeWidget(self.depth_name)  # 从布局中移除
            
            self.fps_label.setVisible(True)
            self.fps_label.setStyleSheet("color: green;")
        else:
            self.video_control_box.setVisible(False)
            self.layout().removeWidget(self.video_control_box)  # 从布局中移除
            self.layout().removeWidget(self.show_video_control_checkbox)  # 从布局中移除
            self.show_video_control_checkbox.setVisible(False)
            self.show_video_control_checkbox.setEnabled(False)
            self.fps_label.setVisible(False)
        self.append_text(f'{translations[self.language]["qhyccd_capture"]["update_camera_mode"]}')
    
    def update_camera_temperature(self):
        # 判断相机是否支持温度控制
        self.has_temperature_control = self.qhyccddll.GetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_CURTEMP.value) != 0
        # print(f"has_temperature_control:{self.has_temperature_control}")
        
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
        self.append_text(f'{translations[self.language]["qhyccd_capture"]["update_temperature_control"]}')
    
    def update_CFW_control(self):
        self.is_CFW_control = self.qhyccddll.IsQHYCCDCFWPlugged(self.camhandle) == 0
        # print(f"is_CFW_control:{self.is_CFW_control}")
        
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
                    self.CFW_number_ids[f"{translations[self.language]['qhyccd_capture']['CFW_position']}{i}"] = hex_str
                self.CFW_filter_selector.clear()
                self.CFW_filter_selector.addItems(list(self.CFW_number_ids.keys()))  # 示例项
        else:
            self.CFW_control_box.setVisible(False)
            self.layout().removeWidget(self.CFW_control_box)  # 从布局中移除
            self.show_CFW_control_checkbox.hide()
            self.layout().removeWidget(self.show_CFW_control_checkbox)  # 从布局中移除
            self.toggle_CFW_control_box(False)
            self.show_CFW_control_checkbox.setEnabled(False)
        self.append_text(f'{translations[self.language]["qhyccd_capture"]["update_CFW_control"]}')   
    
    def update_tiff_compression(self):
        self.tiff_compression_dict = {
            "None":1,
            "CCITT Huffman RLE":2,
            "CCITT Group 3 Fax":3,
            "CCITT Group 4 Fax":4,
            "LZW":5,
            "JPEG":7,
            "ZLIB (DEFLATE)":8,
            "PackBits":32773
        }
        if self.camera_bit == 16 and self.Debayer_mode is False and self.bayer_conversion == 'None':
            update = self.tiff_compression_dict
            del update['CCITT Huffman RLE']
            del update['CCITT Group 3 Fax']
            del update['CCITT Group 4 Fax']
            del update['JPEG']
            self.tiff_compression.clear()
            self.tiff_compression.addItems(list(update.keys()))
        elif self.camera_bit == 8 and self.Debayer_mode is False and self.bayer_conversion == 'None':
            update = self.tiff_compression_dict
            del update['CCITT Huffman RLE']
            del update['CCITT Group 3 Fax']
            del update['CCITT Group 4 Fax']
            del update['JPEG']
            self.tiff_compression.clear()
            self.tiff_compression.addItems(list(self.tiff_compression_dict.keys()))
        elif self.camera_bit == 16 and (self.Debayer_mode is True or self.bayer_conversion != 'None') and self.is_color_camera:
            update = self.tiff_compression_dict
            del update['CCITT Huffman RLE']
            del update['CCITT Group 3 Fax']
            del update['CCITT Group 4 Fax']
            del update['JPEG']
            self.tiff_compression.clear()
            self.tiff_compression.addItems(list(update.keys()))
        elif self.camera_bit == 8 and (self.Debayer_mode is True or self.bayer_conversion != 'None') and self.is_color_camera:
            update = self.tiff_compression_dict
            del update['CCITT Huffman RLE']
            del update['CCITT Group 3 Fax']
            del update['CCITT Group 4 Fax']
            del update['JPEG']
            self.tiff_compression.clear()
            self.tiff_compression.addItems(list(update.keys()))
    
    def update_auto_exposure(self):
        if self.qhyccddll.IsQHYCCDControlAvailable(self.camhandle, CONTROL_ID.CONTROL_AUTOEXPOSURE.value) == 0:
            self.auto_exposure_dialog = AutoExposureDialog(self.qhyccddll,self.camera,self.language,self)
            self.auto_exposure_dialog.mode_changed.connect(self.on_auto_exposure_changed)
            self.auto_exposure_dialog.exposure_value_signal.connect(self.on_auto_exposure_value_changed)
            self.auto_exposure_button.setVisible(True)
        else:
            self.auto_exposure_button.setVisible(False)
        
    def update_auto_white_balance(self):
        if self.qhyccddll.IsQHYCCDControlAvailable(self.camhandle, CONTROL_ID.CONTROL_AUTOWHITEBALANCE.value) == 0:
            self.auto_white_balance_button.setVisible(True)
            self.auto_white_balance_dialog = AutoWhiteBalanceDialog(self.qhyccddll,self.camera,self.language,self)
            self.auto_white_balance_dialog.balance_complete_signal.connect(self.on_auto_white_balance_complete)
            self.auto_white_balance_dialog.values_signal.connect(self.on_auto_white_balance_values_changed)
        else:
            self.auto_white_balance_button.setVisible(False)
        
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
        
        self.image_x = x
        self.image_y = y
        
        # 在这里添加处理分辨率设置的代码
        # print(f"设置分辨率为: ({x},{y}) --> ({x+w},{y+h})")
        if self.camera_mode == translations[self.language]["qhyccd_capture"]["continuous_mode"] and self.preview_thread is not None:
            self.stop_preview()
        # 设置相机分辨率为图像的宽度和高度
        ret = self.qhyccddll.SetQHYCCDResolution(self.camhandle, x, y,w , h)
        if ret == -1:
            # print(f"分辨率设置失败!")
            warnings.warn(f"{translations[self.language]['debug']['set_qhyccd_resolution_failed']}: {ret}")
            self.append_text(f"{translations[self.language]['debug']['set_qhyccd_resolution_failed']}: {ret}")
            return -1
        # print("SetQHYCCDResolution() ret =", ret)
        if self.camera_mode == translations[self.language]["qhyccd_capture"]["continuous_mode"] and self.preview_thread is None:
            self.start_preview()
        self.append_text(f"{translations[self.language]['qhyccd_capture']['set_resolution']}({x},{y}) --> ({x+w},{y+h})")
        return ret

    def on_set_original_resolution_clicked(self):
        if self.camera_mode == translations[self.language]["qhyccd_capture"]["continuous_mode"] and self.preview_thread is not None:
            self.stop_preview()
            
        self.image_w = self.camera_W//self.camera_pixel_bin[self.pixel_bin_selector.currentText()][0]
        self.image_h = self.camera_H//self.camera_pixel_bin[self.pixel_bin_selector.currentText()][1]
        self.image_x = 0
        self.image_y = 0
        # 设置相机分辨率为图像的宽度和高度
        ret = self.qhyccddll.SetQHYCCDResolution(self.camhandle, self.image_x, self.image_y,self.image_w , self.image_h)
        if ret == -1:
            # print(f"分辨率设置失败!")
            warnings.warn(f"{translations[self.language]['debug']['set_qhyccd_resolution_failed']}: {ret}")
            self.append_text(f"{translations[self.language]['debug']['set_qhyccd_resolution_failed']}: {ret}")
            return -1
        # print(f"还原分辨率设置为: ({0},{0}) --> ({self.camera_W},{self.camera_H})")
        self.x.setValue(0)
        self.y.setValue(0)
        self.w.setValue(self.image_w)
        self.h.setValue(self.image_h)
        if self.camera_mode == translations[self.language]["qhyccd_capture"]["continuous_mode"] and self.preview_thread is None:
            self.start_preview()
        self.append_text(f"{translations[self.language]['qhyccd_capture']['set_resolution']}({0},{0}) --> ({self.camera_W},{self.camera_H})")

    '''
    控制相机设置区域的显示与隐藏
    '''
    def toggle_settings_box(self,state = None):
        if state is None:   
            # 切换相机设置区域的显示与隐藏
            visible = not self.settings_box.isVisible()
        else:
            visible = state
        # print(f"toggle_settings_box:{visible} , state:{state}")
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
        # print(f'选中的读出模式: {mode}')
        
        
        # 在这里添加设置读出模式的代码
        self.disconnect_camera()
        self.connect_camera(mode=self.camera_read_mode_ids[mode])
        self.append_text(f"{translations[self.language]['qhyccd_capture']['update_readout_mode']}{mode}")
    
    @pyqtSlot(int)
    def on_pixel_bin_changed(self, index):
        if not self.camera_state:
            return -1
        bin_size = self.pixel_bin_selector.itemText(index)
        if self.camera_mode == translations[self.language]["qhyccd_capture"]["continuous_mode"]:
            self.stop_preview()
        ret = self.qhyccddll.SetQHYCCDBinMode(self.camhandle, self.camera_pixel_bin[bin_size][0], self.camera_pixel_bin[bin_size][1])
        if ret == -1:
            warnings.warn(f"{translations[self.language]['debug']['set_qhyccd_bin_mode_failed']}: {ret}")
            self.append_text(f"{translations[self.language]['debug']['set_qhyccd_bin_mode_failed']}: {ret}")
            return -1
        self.bin = self.camera_pixel_bin[bin_size]
        self.image_x = 0
        self.image_y = 0
        self.image_w = int(self.camera_W/self.camera_pixel_bin[bin_size][0])
        self.image_h = int(self.camera_H/self.camera_pixel_bin[bin_size][1])
        # print("SetQHYCCDBinMode() ret =", ret)
        self.update_resolution(self.image_x,self.image_y,self.image_w,self.image_h)
        if self.camera_mode == translations[self.language]["qhyccd_capture"]["continuous_mode"]:
            self.start_preview()
        # self.update_camera_config()
        self.append_text(f"{translations[self.language]['qhyccd_capture']['update_pixel_bin']}{bin_size}")
        return ret

    @pyqtSlot(int)
    def on_depth_changed(self, index):
        # 获取选中的输出格式
        depth = self.depth_selector.itemText(index)
        if depth == ' ' or depth is None or depth == '':
            return -1
        
        if self.camera_mode == translations[self.language]["qhyccd_capture"]["continuous_mode"]:
            if self.camera_depth_options[depth] == 16 and self.is_color_camera:
                ret = self.qhyccddll.SetQHYCCDDebayerOnOff(self.camhandle,False)
                if ret == -1:
                    # print(f"Debayer模式设置失败!")
                    warnings.warn(f"{translations[self.language]['debug']['set_qhyccd_debayer_mode_failed']}: {ret}")
                    self.append_text(f"{translations[self.language]['debug']['set_qhyccd_debayer_mode_failed']}: {ret}")
                self.Debayer_mode_selector.setEnabled(False)
                self.Debayer_mode_selector.setCurrentText(translations[self.language]["qhyccd_capture"]["debayer_mode_false"])
                self.Debayer_mode = False
            elif self.camera_depth_options[depth] == 8 and self.is_color_camera:
                self.Debayer_mode_selector.setEnabled(True)
            self.stop_preview()
            
        # 在这里添加设置输出格式的代码
        ret = self.qhyccddll.SetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_TRANSFERBIT.value, self.camera_depth_options[depth])
        if ret == -1:
            # print(f"位深{depth}设置失败!")
            warnings.warn(f"{translations[self.language]['debug']['set_qhyccd_transferbit_failed']}: {ret}")
            self.append_text(f"{translations[self.language]['debug']['set_qhyccd_transferbit_failed']}: {ret}")
            return -1
        self.camera_bit = self.camera_depth_options[depth]
        if self.camera_mode == translations[self.language]["qhyccd_capture"]["continuous_mode"]:
            self.start_preview()
        self.append_text(f"{translations[self.language]['qhyccd_capture']['update_depth']}{depth}")
        
        self.update_tiff_compression()
        return ret

    @pyqtSlot(int)
    def on_Debayer_mode_changed(self, index):
        if not self.camera_state:
            return -1
        # 获取选中的Debayer模式
        mode = self.Debayer_mode_selector.itemText(index)
        if mode == ' ' or mode is None :
            return -1
        # print(f'选中的Debayer模式: {mode}')
        self.Debayer_mode = self.camera_Debayer_mode[mode]
        if self.camera_mode == translations[self.language]["qhyccd_capture"]["continuous_mode"]:
            self.stop_preview()
            self.on_set_original_resolution_clicked()
            self.set_original_resolution_button.setEnabled(not self.camera_Debayer_mode[mode])
            self.set_resolution_button.setEnabled(not self.camera_Debayer_mode[mode])
            self.show_roi_button.setEnabled(not self.camera_Debayer_mode[mode])
        ret = self.qhyccddll.SetQHYCCDDebayerOnOff(self.camhandle, self.camera_Debayer_mode[mode])
        if ret == -1:
            # print(f"Debayer模式{mode}设置失败!")
            warnings.warn(f"{translations[self.language]['debug']['set_qhyccd_debayer_mode_failed']}: {ret}")
            self.append_text(f"{translations[self.language]['debug']['set_qhyccd_debayer_mode_failed']}: {ret}")
        if self.camera_mode == translations[self.language]["qhyccd_capture"]["continuous_mode"]:
            self.start_preview()
        self.append_text(f"{translations[self.language]['qhyccd_capture']['update_debayer_mode']}{mode}")
        self.update_tiff_compression()
        return ret
    
    def start_capture(self):
        if self.capture_in_progress :
            self.cancel_capture()
            return
        
        self.capture_in_progress = True
        self.start_button.setText(translations[self.language]["qhyccd_capture"]["cancel_capture"])
        self.capture_status_thread.resume_capture()
        
        # print("开始拍摄")
        self.update_exposure_time()
        if self.camera_mode == translations[self.language]["qhyccd_capture"]["single_frame_mode"]:
            self.capture_thread = CaptureThread(
                self.camhandle, self.qhyccddll, self.image_w, self.image_h, self.camera_bit, self.is_color_camera, self.bayer_conversion,self.language
            )
            self.capture_thread.capture_finished.connect(self.on_capture_finished)
            self.capture_thread.start()
        elif self.camera_mode == translations[self.language]["qhyccd_capture"]["continuous_mode"]:
            self.on_capture_finished(self.preview_image)
        self.append_text(translations[self.language]["qhyccd_capture"]["start_capture"])
            
    def on_capture_finished(self, imgdata_np):
        if not self.capture_in_progress :
            return
        
        self.capture_status_thread.pause_capture()

        if self.bayer_conversion != "None" and imgdata_np.ndim == 2:
            imgdata_np = self.convert_bayer(imgdata_np, self.bayer_conversion)
        
        if self.file_format == "fits":
                dict_value = {
                    "SIMPLE": "True",
                    "BITPIX": imgdata_np.dtype.name,
                    "NAXIS": imgdata_np.ndim,
                    "NAXIS1": self.image_w,
                    "NAXIS2": self.image_h,
                    "EXTEND": "False",
                    "DATE-OBS": datetime.now().strftime("%Y-%m-%d_%H-%M-%S"),
                    "EXPTIME": f"{self.exposure_time.value():.3f} ms",
                    "TELESCOP": self.camera_name,     
                }
                self.fits_header_dialog.update_table_with_dict(dict_value)


        # 获取当前时间并格式化
        current_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        camera_name = self.camera_selector.currentText()
        
        display_mode = self.display_mode_selector.currentText()
        
        if display_mode == translations[self.language]["qhyccd_capture"]["distributed_display"]:
            # print(f"分布式显示 图像形状: {imgdata_np.shape}, 维度: {imgdata_np.ndim}")
            self.current_image = imgdata_np
            self.current_image_name = f'{camera_name}-{current_time}'
            self.viewer.add_image(self.current_image, name=self.current_image_name)
            if self.camera_bit == 16:
                self.viewer.layers[self.current_image_name].contrast_limits = (0, 65535)
            else:
                self.viewer.layers[self.current_image_name].contrast_limits = (0, 255)
            if self.camera_mode == translations[self.language]["qhyccd_capture"]["single_frame_mode"]:
                # print("单帧模式")
                imgdata_np = self.apply_white_balance_software(imgdata_np=self.current_image.copy())
                self.viewer.layers[self.current_image_name].data = imgdata_np
        elif display_mode == translations[self.language]["qhyccd_capture"]["single_display"]:
            self.current_image_name = f'{camera_name}-one'
            # print(f"单一显示 图像形状: {imgdata_np.shape}, 维度: {imgdata_np.ndim}")
            if self.current_image is not None and self.current_image_name in self.viewer.layers and self.current_image.ndim == imgdata_np.ndim and self.current_image.shape == imgdata_np.shape:
                self.current_image = imgdata_np

                self.viewer.layers[self.current_image_name].data = self.current_image
            else:
                self.current_image = imgdata_np
                if self.current_image_name in self.viewer.layers:
                    self.viewer.layers.pop(self.current_image_name)
                self.viewer.add_image(self.current_image, name=self.current_image_name)
            
            if self.camera_mode == translations[self.language]["qhyccd_capture"]["single_frame_mode"]:
 
                imgdata_np = self.apply_white_balance_software(imgdata_np=self.current_image.copy())
                self.viewer.layers[self.current_image_name].data = imgdata_np
            
        elif display_mode == translations[self.language]["qhyccd_capture"]["sequential_display"]:
            # 打印图像的形状和维度
            # print(f"序列显示 图像形状: {imgdata_np.shape}, 维度: {imgdata_np.ndim}")
            if imgdata_np.ndim == 2:
                imgdata_np_3c = np.stack([imgdata_np] * 3, axis=-1)
                imgdata_np_3c = imgdata_np_3c[np.newaxis, ...]
                sequential_display_ndim = 2
            if imgdata_np.ndim == 3:
                imgdata_np_3c = imgdata_np[np.newaxis, ...]
                sequential_display_ndim = 3
            # print(f"imgdata_np.ndim: {imgdata_np.ndim}")
            if self.current_image is None or (imgdata_np_3c.ndim != self.current_image.ndim or imgdata_np_3c.shape[1:] != self.current_image.shape[1:] or imgdata_np_3c.dtype != self.current_image.dtype) or self.current_image.ndim != 4:
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
                if self.camera_bit == 16:
                    self.viewer.layers[self.current_image_name].contrast_limits = (0, 65535)
                else:
                    self.viewer.layers[self.current_image_name].contrast_limits = (0, 255)
            
            if self.camera_mode == translations[self.language]["qhyccd_capture"]["single_frame_mode"] and self.is_color_camera:
                # print("单帧模式")
                imgdata_np = self.apply_white_balance_software(imgdata_np=self.current_image.copy())
                self.viewer.layers[self.current_image_name].data = imgdata_np
            else:
                sequential_display_ndim = 1
            # 定位显示拍摄的最后一张图片
            self.viewer.layers[self.current_image_name].refresh()
            self.viewer.dims.set_point(0, self.current_image.shape[0] - 1)
            
        # 检查图层是否存在于图层列表中
        if self.current_image_name in self.viewer.layers:
            # 获取当前图层
            layer = self.viewer.layers[self.current_image_name]
            # 获取当前图层的索引
            current_index = self.viewer.layers.index(layer)
            # 计算最上层的索引（即图层列表的长度减一）
            top_index = len(self.viewer.layers) - 1
            # 如果图层不在最上层，则移动到最上层
            if current_index != top_index and display_mode == translations[self.language]["qhyccd_capture"]["sequential_display"]:
                # 获取当前图层
                layer = self.viewer.layers[self.current_image_name]
                # 移除当前图层
                self.viewer.layers.remove(layer)
                # 重新添加图层到列表末尾，使其显示在最上层
                self.viewer.layers.append(layer)
                # 设置为当前活跃的图层
                self.viewer.layers.selection.active = layer
                            # 定位显示拍摄的最后一张图片
                self.viewer.layers[self.current_image_name].refresh()
                self.viewer.dims.set_point(0, self.current_image.shape[0] - 1)
            else:
                # 移动图层到最上层
                self.viewer.layers.move(current_index, top_index)
            # 设置为当前活跃的图层
            self.viewer.layers.selection.active = layer
            
        self.contrast_limits_name = self.current_image_name
        
        self.bind_contrast_limits_event()

        self.append_text(translations[self.language]["qhyccd_capture"]["capture_finished"])
        
        self.capture_in_progress = False
        self.start_button.setText(translations[self.language]["qhyccd_capture"]["start_capture"])
        self.capture_status_label.setText(translations[self.language]["qhyccd_capture"]["capture_finished"])
        if display_mode == translations[self.language]["qhyccd_capture"]["sequential_display"]:
            if sequential_display_ndim == 2:
                self.img_buffer.put(imgdata_np[-1,:,:,-1])
            elif sequential_display_ndim == 3:
                self.img_buffer.put(imgdata_np[-1])
            else:
                self.img_buffer.put(imgdata_np)
        else:
            self.img_buffer.put(imgdata_np)
        self.histogram_widget.update_histogram()
        # self.capture_status_thread.pause_capture()

    def cancel_capture(self):
        self.capture_in_progress = False
        self.start_button.setText(translations[self.language]["qhyccd_capture"]["start_capture"])
        self.capture_status_label.setText(translations[self.language]["qhyccd_capture"]["capture_canceled"])
        self.append_text(translations[self.language]["qhyccd_capture"]["cancel_capture"])
        self.capture_status_thread.pause_capture()
        self.qhyccddll.CancelQHYCCDExposingAndReadout(self.camhandle)
        # print("拍摄已取消")

    def save_image(self):
        if self.current_image is not None:
            options = QFileDialog.Options()
            file_path, _ = QFileDialog.getSaveFileName(self, translations[self.language]["qhyccd_capture"]["save_image"], "", "PNG Files (*.png);;JPEG Files (*.jpg);;All Files (*)", options=options)
            if file_path:
                if not (file_path.endswith('.png') or file_path.endswith('.jpg')):
                    file_path += '.png'

                if self.current_image.ndim == 2:
                    cv2.imwrite(file_path, self.current_image)
                elif self.current_image.ndim == 3 and self.current_image.shape[2] == 3:
                    cv2.imwrite(file_path, cv2.cvtColor(self.current_image, cv2.COLOR_RGB2BGR))
                # print(f"图像已保存到: {file_path}")
                self.append_text(f"{translations[self.language]['qhyccd_capture']['save_image_success']}:{file_path}")
        else:
            # print("没有图像可保存")
            self.append_text(translations[self.language]["qhyccd_capture"]["save_image_failed"])
    
    def getParamlimit(self,data_id):
        minValue = ctypes.c_double()  # 最小值
        maxValue = ctypes.c_double()  # 最大值
        step = ctypes.c_double() # 步长
        
        ret = self.qhyccddll.GetQHYCCDParamMinMaxStep(self.camhandle, data_id,byref(minValue),byref(maxValue),byref(step))
        if ret == -1:
            # print(f"参数范围获取失败！")
            warnings.warn(f"{translations[self.language]['debug']['get_qhyccd_param_failed']}: {ret}")
            self.append_text(f"{translations[self.language]['debug']['get_qhyccd_param_failed']}: {ret}")
        return minValue.value,maxValue.value,step.value
    
    def update_exposure_time(self):
        
        # 处理曝光时间变化的逻辑
        exposure_time = int(self.exposure_time.value()*1000)
        # print(f"exposure_time:{exposure_time},{type(exposure_time)}")
        ret = self.qhyccddll.SetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_EXPOSURE.value, exposure_time)
        if ret == 0:
            self.append_text(f"{translations[self.language]['qhyccd_capture']['set_exposure_time_success']}: {exposure_time} us")
        else:
            warnings.warn(f"{translations[self.language]['debug']['set_qhyccd_exposure_time_failed']}: {ret}")
            self.append_text(f"{translations[self.language]['debug']['set_qhyccd_exposure_time_failed']}: {ret}")
        return ret
    
    def update_gain(self, value):
        ret = self.qhyccddll.SetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_GAIN.value, value)
        if ret == 0:
            self.append_text(f"{translations[self.language]['qhyccd_capture']['set_gain_success']}: {value} dB")
        else:
            warnings.warn(f"{translations[self.language]['debug']['set_qhyccd_gain_failed']}: {ret}")
            self.append_text(f"{translations[self.language]['debug']['set_qhyccd_gain_failed']}: {ret}")
        return ret

    def update_offset(self, value):
        ret = self.qhyccddll.SetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_OFFSET.value, value)
        if ret == 0:
            self.append_text(f"{translations[self.language]['qhyccd_capture']['set_offset_success']}: {value} ")
        else:
            warnings.warn(f"{translations[self.language]['debug']['set_qhyccd_offset_failed']}: {ret}")
            self.append_text(f"{translations[self.language]['debug']['set_qhyccd_offset_failed']}: {ret}")
        return ret

    def update_usb_traffic(self, value):
        ret = self.qhyccddll.SetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_USBTRAFFIC.value, value)
        if ret == 0:
            self.append_text(f"{translations[self.language]['qhyccd_capture']['set_usb_traffic_success']}: {value} ")
        else:
            warnings.warn(f"{translations[self.language]['debug']['set_qhyccd_usb_traffic_failed']}: {ret}")
            self.append_text(f"{translations[self.language]['debug']['set_qhyccd_usb_traffic_failed']}: {ret}")
        return ret
         
    def show_roi_component(self):
        # 检查是否存在以QHY开头的图片
        if not any(layer.name.startswith('QHY') for layer in self.viewer.layers ) :
            warnings.warn(f"{translations[self.language]['debug']['no_qhy_image']}")
            self.append_text(f"{translations[self.language]['debug']['no_qhy_image']}")
            return

        if not self.roi_created:
            self.roi_created = True
            self.show_roi_button.setText(translations[self.language]["qhyccd_capture"]["apply_roi"])
            self.set_resolution_button.setEnabled(False)
            self.viewer.camera.interactive = False  # 锁定图像
            self.append_text(translations[self.language]["qhyccd_capture"]["roi_activated"])
        else:
            self.clear_roi()
            self.roi_created = False
            self.show_roi_button.setText(translations[self.language]["qhyccd_capture"]["roi"])
            self.set_resolution_button.setEnabled(True)
            self.viewer.camera.interactive = True  # 解锁图像
            self.append_text(translations[self.language]["qhyccd_capture"]["roi_closed"])

    def on_mouse_click(self, viewer, event):
        if not self.roi_created:
            return

        if event.type == 'mouse_press' and event.button == 1:
            if len(self.roi_points) >= 2:
                self.clear_roi()

            # 将鼠标点击位置转换为图像坐标
            image_coords = self.viewer.layers[-1].world_to_data(event.position)
            self.roi_points.append(image_coords)

            if len(self.roi_points) == 2:
                self.update_roi_layer()
                self.update_resolution_display()

    def on_mouse_double_click(self, viewer, event):
        self.clear_roi()
        # print("所有ROI矩形框已删除")
        
    def on_save_mode_changed(self, index):
        self.save_mode = self.save_mode_selector.itemText(index)
        # print(f"选中的录像模式: {self.save_mode}")
        if self.save_mode == translations[self.language]["qhyccd_capture"]["single_frame_storage"]:
            self.save_format_selector.clear()
            self.save_format_selector.addItems(['png', 'jpeg', 'tiff', 'fits'])  # 图片格式
        elif self.save_mode == translations[self.language]["qhyccd_capture"]["video_storage"]:
            self.save_format_selector.clear()
            self.save_format_selector.addItems(['avi', 'mp4', 'mkv'])  # 视频格式
    
    def on_save_format_changed(self, index):
        self.file_format = self.save_format_selector.itemText(index)
        if self.save_mode == translations[self.language]["qhyccd_capture"]["single_frame_storage"]:
            if self.file_format == 'png':
                self.file_format = 'png'
                self.jpeg_quality.setVisible(False)
                self.tiff_compression.setVisible(False)
                self.show_fits_header.setVisible(False)
            elif self.file_format == 'jpeg':
                self.file_format = 'jpg'
                self.jpeg_quality.setVisible(True)
                self.tiff_compression.setVisible(False)
                self.show_fits_header.setVisible(False)
            elif self.file_format == 'tiff':
                self.file_format = 'tif'
                self.jpeg_quality.setVisible(False)
                self.tiff_compression.setVisible(True)
                self.show_fits_header.setVisible(False)
            elif self.file_format == 'fits':
                self.file_format = 'fits'
                self.jpeg_quality.setVisible(False)
                self.tiff_compression.setVisible(False)
                self.show_fits_header.setVisible(True)

    def toggle_fits_header(self):
        # 切换FITS头编辑器的显示状态
        self.fits_header_dialog.toggle_window()

    def clear_roi(self):
        try:    
            if self.roi_layer is not None and self.roi_layer in self.viewer.layers:
                self.viewer.layers.remove(self.roi_layer)
        except Exception as e:
            warnings.warn(f"{translations[self.language]['debug']['clear_roi_failed']}: {e}")
            self.append_text(f"{translations[self.language]['debug']['clear_roi_failed']}: {e}")
        self.roi_layer = None
        self.roi_points = []

    def update_roi_layer(self):
        if self.roi_layer is not None:
            self.viewer.layers.remove(self.roi_layer)

        if len(self.roi_points) == 2:
            x0, y0 = self.roi_points[0][-2:]
            x1, y1 = self.roi_points[1][-2:]
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
            y0,x0 = self.roi_points[0][-2:]
            if x0 < 0:
                x0 = 0
            if x0 > self.image_w:
                x0 = self.image_w
            if y0 < 0:
                y0 = 0
            if y0 > self.image_h:
                y0 = self.image_h
            y1,x1 = self.roi_points[1][-2:]
            if x1 < 0:
                x1 = 0
            if x1 > self.image_w:
                x1 = self.image_w
            if y1 < 0:
                y1 = 0
            if y1 > self.image_h:
                y1 = self.image_h
            x = int(min(x0, x1))+self.image_x
            y = int(min(y0, y1))+self.image_y
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
            # print(f"更新分辨率显示: x={x}, y={y}, w={w}, h={h}")

    def toggle_histogram_display(self, state):
        """切换直方图显示"""
        if state == Qt.Checked:
            self.histogram_widget.show_widget()
        else:
            self.histogram_widget.hide_widget()  # 隐藏直方图窗口
                   
    def on_set_white_balance_clicked(self):
        if self.current_image is None or self.current_image.ndim != 3 or self.current_image.shape[2] == 1:
            return
        red_gain = 1+self.wb_red.value()/ self.wb_red.maximum() # 获取红色增益
        green_gain = 1+self.wb_green.value() / self.wb_green.maximum()  # 获取绿色增益
        blue_gain = 1+self.wb_blue.value() / self.wb_blue.maximum()  # 获取蓝色增益
        imgdata_np = self.apply_white_balance_software(self.current_image.copy(),red_gain,green_gain,blue_gain)
        if self.camera_mode == translations[self.language]["qhyccd_capture"]["single_frame_mode"] and len(self.viewer.layers) > 0 and self.viewer.layers[-1].name.startswith('QHY') and imgdata_np.ndim == self.viewer.layers[-1].data.ndim:
            self.viewer.layers[-1].data = imgdata_np
            self.img_buffer.put(imgdata_np)
            self.histogram_widget.update_histogram()
    
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
        if self.is_color_camera and imgdata_np.ndim == 3 and imgdata_np.shape[-1] == 3:
            imgdata_np = self._apply_gain_to_image(imgdata_np, red_gain, green_gain, blue_gain)

        # 处理序列图像
        elif self.is_color_camera and imgdata_np.ndim == 4 and imgdata_np.shape[-1] == 3:
            imgdata_np[-1] = self._apply_gain_to_image(imgdata_np[-1], red_gain, green_gain, blue_gain)
            self.current_image[-1] = imgdata_np[-1]

        return imgdata_np  # 返回处理后的图像
    
    def _apply_gain_to_image(self, image, red_gain, green_gain, blue_gain):
        """应用增益到单帧图像，优化版本"""
        # 根据图像的数据类型设置最大值
        # start_time = time.time()
        max_value = 65535 if image.dtype == np.uint16 else 255
        # 将增益转换为字符串键
        str_red_gain = f"{red_gain:.2f}"
        str_green_gain = f"{green_gain:.2f}"
        str_blue_gain = f"{blue_gain:.2f}"
        # print(f"str_red_gain: {str_red_gain}")
        # print(f"str_green_gain: {str_green_gain}")
        # print(f"str_blue_gain: {str_blue_gain}")
        # print(f"luts keys: {self.luts.keys()}")
        lut_red = self.luts[max_value][str_red_gain]
        lut_green = self.luts[max_value][str_green_gain]
        lut_blue = self.luts[max_value][str_blue_gain]

        # 应用查找表
        image[:, :, 0] = lut_red[image[:, :, 0]]
        image[:, :, 1] = lut_green[image[:, :, 1]]
        image[:, :, 2] = lut_blue[image[:, :, 2]]
        # print(f"增益处理完成，用时: {time.time() - start_time} 秒")
        return image    
    
    # 生成全局查找表
    def create_luts(self, max_values, gain_start, gain_end, gain_step):
        """
        创建并保存映射表。
        :param max_values: 像素最大值列表，例如 [255, 65535]
        :param gain_start: 增益起始值
        :param gain_end: 增益结束值
        :param gain_step: 增益步长
        :return: None
        """
        # 使用 np.linspace 确保包括结束值
        num_steps = int((gain_end - gain_start) / gain_step) + 1
        gains = np.linspace(gain_start, gain_end, num_steps)
        
        luts = {}
        for max_value in max_values:
            luts[max_value] = {}
            for gain in gains:
                # 四舍五入增益值到合适的小数位数
                rounded_gain = round(gain, 2)
                original_values = np.arange(max_value + 1)
                adjusted_values = np.clip(original_values * rounded_gain, 0, max_value)
                lut = adjusted_values.astype(np.uint16 if max_value > 255 else np.uint8)
                # 使用四舍五入后的增益值作为键
                luts[max_value][f"{rounded_gain:.2f}"] = lut

        self.luts = luts
        # 保存查找表到文件
        with open('luts.pkl', 'wb') as f:
            pickle.dump(luts, f)
    
    def apply_white_balance_hardware(self):

        red_gain = self.wb_red.value()
        green_gain = self.wb_green.value()
        blue_gain = self.wb_blue.value()
        
        ret = self.qhyccddll.SetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_WBR.value, red_gain)
        if ret == 0:        
            # print(f"红色增益设置为: {red_gain}")
            self.append_text(f"{translations[self.language]['qhyccd_capture']['set_red_gain_success']}: {red_gain} dB")
        else:
            # print(f"红色增益设置失败！")
            warnings.warn(f"{translations[self.language]['debug']['set_qhyccd_red_gain_failed']}: {ret}")
            self.append_text(f"{translations[self.language]['debug']['set_qhyccd_red_gain_failed']}: {ret}")
        ret = self.qhyccddll.SetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_WBG.value, green_gain)
        if ret == 0:
            # print(f"绿色增益设置为: {green_gain}")
            self.append_text(f"{translations[self.language]['qhyccd_capture']['set_green_gain_success']}: {green_gain} dB")
        else:
            # print(f"绿色增益设置失败！")
            warnings.warn(f"{translations[self.language]['debug']['set_qhyccd_green_gain_failed']}: {ret}")
            self.append_text(f"{translations[self.language]['debug']['set_qhyccd_green_gain_failed']}: {ret}")
        ret = self.qhyccddll.SetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_WBB.value, blue_gain)
        if ret == 0:
            # print(f"蓝色增益设置为: {blue_gain}")
            self.append_text(f"{translations[self.language]['qhyccd_capture']['set_blue_gain_success']}: {blue_gain} dB")
        else:
            # print(f"蓝色增益设置失败！")
            warnings.warn(f"{translations[self.language]['debug']['set_qhyccd_blue_gain_failed']}: {ret}")    
            self.append_text(f"{translations[self.language]['debug']['set_qhyccd_blue_gain_failed']}: {ret}")
        return 0
    
    def on_bayer_conversion_changed(self, index):
        self.bayer_conversion = self.bayer_conversion_selector.itemText(index)
        self.update_tiff_compression()

    def convert_bayer(self, img, pattern):
        if img.ndim == 2:
            if pattern == "RGGB":
                img_bgr = cv2.cvtColor(img, cv2.COLOR_BAYER_RG2BGR_EA if img.dtype == np.uint16 else cv2.COLOR_BAYER_RG2BGR)
            elif pattern == "BGGR":
                img_bgr = cv2.cvtColor(img, cv2.COLOR_BAYER_BG2BGR_EA if img.dtype == np.uint16 else cv2.COLOR_BAYER_BG2BGR)
            elif pattern == "GRBG":
                img_bgr = cv2.cvtColor(img, cv2.COLOR_BAYER_GR2BGR_EA if img.dtype == np.uint16 else cv2.COLOR_BAYER_GR2BGR)
            elif pattern == "GBRG":
                img_bgr = cv2.cvtColor(img, cv2.COLOR_BAYER_GB2BGR_EA if img.dtype == np.uint16 else cv2.COLOR_BAYER_GB2BGR)
            else:
                return img
            return img_bgr
        return img
        # return cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)  # 将BGR转换为RGB

    def update_current_temperature(self):
        """更新当前温度显示"""
        current_humidity = ctypes.c_double()
        if self.has_temperature_control:
            current_temp = self.qhyccddll.GetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_CURTEMP.value)
            self.current_temperature_label.setText(f'{translations[self.language]["qhyccd_capture"]["temperature"]}: {current_temp:.2f} °C')
            current_humidity = self.qhyccddll.GetQHYCCDHumidity(self.camhandle,byref(current_humidity))
            if current_humidity > 0:
                self.current_humidity_label.setText(f'{translations[self.language]["qhyccd_capture"]["humidity"]}: {current_humidity:.2f} %')
    
    def update_temperature_setpoint(self, value):
        """更新温度设定点"""
        if self.has_temperature_control:
            ret = self.qhyccddll.SetQHYCCDParam(self.camhandle, CONTROL_ID.CONTROL_COOLER.value, value)
            if ret == 0:
                # print(f"温度设定点设置为: {value} °C")
                self.append_text(f"{translations[self.language]['qhyccd_capture']['set_temperature_success']}: {value} °C")
            else:
                # print(f"温度设定点设置失败！")
                warnings.warn(f"{translations[self.language]['debug']['set_qhyccd_temperature_failed']}: {ret}")
                self.append_text(f"{translations[self.language]['debug']['set_qhyccd_temperature_failed']}: {ret}")
                
    def on_CFW_filter_changed(self, index):
        self.CFW_id = self.CFW_filter_selector.itemText(index)
        if self.CFW_id == "None" or self.CFW_id == "" or self.CFW_id == " ":
            return -1
        # print(f"选中的 CFW 滤镜: {self.CFW_id},{self.CFW_number_ids[self.CFW_id]}")
        # 将字符串转换为字节字符串
        order = self.CFW_number_ids[self.CFW_id].encode('utf-8')
        ret = self.qhyccddll.SendOrder2QHYCCDCFW(self.camhandle, c_char_p(order), len(order))
        if ret == 0:
            # print(f"移动滤镜轮到位置: {self.CFW_id}")
            self.append_text(f"{translations[self.language]['qhyccd_capture']['set_cfw_filter_success']}: {self.CFW_id}")
        else:
            # print(f"移动滤镜轮失败！")
            warnings.warn(f"{translations[self.language]['debug']['set_qhyccd_cfw_filter_failed']}: {ret}")
            self.append_text(f"{translations[self.language]['debug']['set_qhyccd_cfw_filter_failed']}: {ret}")
    
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
        directory = QFileDialog.getExistingDirectory(self, translations[self.language]["qhyccd_capture"]["select_save_path"], options=options)
        if directory:
            self.path_selector.setText(directory)
            
    def on_record_mode_changed(self, index):
        self.record_mode = self.record_mode_selector.itemText(index)
        # print(f"选中的录像模式: {self.record_mode}")

        if self.record_mode == translations[self.language]["qhyccd_capture"]["time_mode"]:
            self.record_time_input.setVisible(True)
            self.record_time_input_label.setVisible(True)
            self.frame_count_input.setVisible(False)
            self.frame_count_input_label.setVisible(False)
            self.layout().removeWidget(self.frame_count_input)  # 从布局中移除
            self.layout().removeWidget(self.frame_count_input_label)  # 从布局中移除
        elif self.record_mode == translations[self.language]["qhyccd_capture"]["frame_mode"]:
            self.record_time_input.setVisible(False)
            self.record_time_input_label.setVisible(False)
            self.layout().removeWidget(self.record_time_input)  # 从布局中移除
            self.layout().removeWidget(self.record_time_input_label)  # 从布局中移除
            self.frame_count_input.setVisible(True)
            self.frame_count_input_label.setVisible(True)

        elif self.record_mode == translations[self.language]["qhyccd_capture"]["continuous_mode"]:
            self.record_time_input.setVisible(False)
            self.record_time_input_label.setVisible(False)
            self.frame_count_input.setVisible(False)
            self.frame_count_input_label.setVisible(False)
            self.layout().removeWidget(self.record_time_input)  # 从布局中移除
            self.layout().removeWidget(self.record_time_input_label)  # 从布局中移除
            self.layout().removeWidget(self.frame_count_input)  # 从布局中移除
            self.layout().removeWidget(self.frame_count_input_label)  # 从布局中移除

    def start_recording(self):
        self.append_text(translations[self.language]["qhyccd_capture"]["start_recording"])
        self.record_button.setEnabled(False)
        self.is_recording = True
        self.save_progress_indicator.setVisible(True)
        self.save_progress_indicator.setText(translations[self.language]["qhyccd_capture"]["saving"])
        
    def on_save_thread_finished(self):
        self.save_progress_indicator.setText(translations[self.language]["qhyccd_capture"]["save_completed"])
        self.append_text(translations[self.language]["qhyccd_capture"]["recording_completed"])

    def stop_recording(self):
        self.is_recording = False
        self.record_button.setEnabled(True)
        self.buffer_queue.put("end")
        self.save_thread = None
        self.record_time_input.setEnabled(True)
        self.frame_count_input.setEnabled(True)
        self.record_mode_selector.setEnabled(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)  # 重置进度条
        self.append_text(translations[self.language]["qhyccd_capture"]["stop_recording"])

    def start_preview(self):
        if self.preview_thread is None:
            ret = self.qhyccddll.BeginQHYCCDLive(self.camhandle)
            if ret != 0:
                warnings.warn(f"{translations[self.language]['debug']['begin_qhyccd_live_failed']}: {ret}")
                self.append_text(f"{translations[self.language]['debug']['begin_qhyccd_live_failed']}: {ret}")
            # 根据位深和颜色模式确定数据类型和大小
            dtype_code = 'H' if self.camera_bit == 16 else 'B'  # 'H' 对应 ctypes.c_uint16，'B' 对应 ctypes.c_ubyte
            
            if self.is_color_camera and self.Debayer_mode:
                channels = 3
            else:
                channels = 1
            
            # 创建共享内存
            self.shared_image_data = Array(dtype_code, self.image_w * self.image_h * channels , lock=False)
            
            self.preview_thread = PreviewThread(
                self.camhandle, self.qhyccddll, self.image_w, self.image_h, self.camera_bit, self.is_color_camera, 
                self.Debayer_mode, self.viewer,self.shared_image_data
            )
            self.preview_thread.frame_captured.connect(self.data_received)  # 连接信号到槽函数
            self.preview_thread.start()
            self.preview_checkbox.setChecked(True)
            
    def stop_preview(self):
        if self.preview_thread is not None:
            ret = self.qhyccddll.StopQHYCCDLive(self.camhandle)
            if ret != 0:
                warnings.warn(f"{translations[self.language]['debug']['stop_qhyccd_live_failed']}: {ret}")
                self.append_text(f"{translations[self.language]['debug']['stop_qhyccd_live_failed']}: {ret}")
            self.preview_thread.stop()
            self.preview_checkbox.setChecked(False)
            self.preview_thread = None
        if 'QHY-Preview' in self.viewer.layers:
            self.viewer.layers.remove('QHY-Preview')
        
    def data_received(self, fps):
        with self.lock:
            if self.top_checkbox.isChecked():
                self.contrast_limits_name = 'QHY-Preview'
            dtype = np.uint16 if self.camera_bit == 16 else np.uint8
            shape = (self.image_h, self.image_w, 3) if self.is_color_camera and self.Debayer_mode  else (self.image_h, self.image_w)
            imgdata_np = np.frombuffer(self.shared_image_data, dtype=dtype).reshape(shape)
        if imgdata_np is None:
            return
        
        # 传输数据到保存
        if self.is_recording:
            if self.file_format == "fits":
                dict_value = {
                    "SIMPLE": "T",
                    "BITPIX": imgdata_np.dtype.name,
                    "NAXIS": imgdata_np.ndim,
                    "NAXIS1": self.image_w,
                    "NAXIS2": self.image_h,
                    "DATE-OBS": datetime.now().strftime("%Y-%m-%d_%H-%M-%S"),
                    "EXPTIME": f"{self.exposure_time.value():.3f} ms",
                    "TELESCOP": self.camera_name,     
                }
                self.fits_header_dialog.update_table_with_dict(dict_value)
    
            # 应用 Bayer 转换
            if self.is_color_camera and self.bayer_conversion != "None":
                # print(f"经过convert_bayer() imgdata_np.shape: {imgdata_np.shape}")
                imgdata_np = self.convert_bayer(imgdata_np, self.bayer_conversion)
            if self.save_thread is None:
                self.buffer_queue = queue.Queue()
                # 创建并启动保存线程
                self.save_thread = SaveThread(self.buffer_queue, self.path_selector.text(), self.record_file_name.text(), self.save_format_selector.currentText(), self.save_mode, int(fps),self.language,int(self.jpeg_quality.value()),int(self.tiff_compression_dict[self.tiff_compression.currentText()]),self.fits_header_dialog.get_table_data())
                self.save_thread.finished.connect(self.on_save_thread_finished)  # 连接信号
                self.save_thread.start()
                self.record_time_input.setEnabled(False)
                self.frame_count_input.setEnabled(False)
                self.record_mode_selector.setEnabled(False)
                
                # 重置进度条
                self.progress_bar.setValue(0)
                self.progress_bar.setTextVisible(True)
                self.progress_bar.setStyleSheet("")  # 还原颜色

            if self.record_mode == translations[self.language]["qhyccd_capture"]["time_mode"]:
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
                    
            elif self.record_mode == translations[self.language]["qhyccd_capture"]["frame_mode"]:
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
            elif self.record_mode == translations[self.language]["qhyccd_capture"]["continuous_mode"]:
                self.buffer_queue.put(imgdata_np)
                # 进度条循环
                self.progress_bar.setRange(0, 0)
                
        # 获取当前时间
        current_time = time.time()
        
        # 传输数据到画布显示，限制最高帧率为30fps   
        if self.last_update_time is not None and current_time - self.last_update_time < 1/30:
            return
        else:   
            if self.is_color_camera and self.bayer_conversion != "None":
                imgdata_np = self.convert_bayer(imgdata_np, self.bayer_conversion)
            self.update_viewer(imgdata_np, fps)
            self.last_update_time = current_time
            
        if (self.last_histogram_update_time is None or current_time - self.last_histogram_update_time > 1) and self.top_checkbox.isChecked():
            self.img_buffer.put(imgdata_np)
            self.histogram_widget.update_histogram()
            self.last_histogram_update_time = current_time

    def update_viewer(self, imgdata_np, fps):
        layer_name = 'QHY-Preview'
        
        self.preview_image = imgdata_np
        if not self.preview_status:
            if layer_name in self.viewer.layers:
                self.viewer.layers.remove(layer_name)
            return

        self.fps_label.setText(f'FPS: {fps:.2f}')
        
        if imgdata_np.shape[1] > 1000:
            img_with_fps = imgdata_np.copy()
            
            # 设置文本位置
            text_position = (img_with_fps.shape[1] - int(img_with_fps.shape[1] / 100 * 15), int(img_with_fps.shape[0] / 100 * 3))
            
            # 创建半透明背景
            overlay = imgdata_np.copy()
            max_value = 65535 if img_with_fps.dtype == np.uint16 else 255
            text = f'FPS: {fps:.2f}'
            font_scale = 0.7 * (img_with_fps.shape[1] / 1000)
            (text_width, text_height), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 2)
            cv2.rectangle(overlay, 
                          (text_position[0] - 10, text_position[1] - text_height - 10), 
                          (text_position[0] + text_width + 10, text_position[1] + 10), 
                          (0, 0, 0), -1)  # 黑色背景

            # 在图像上绘制 FPS
            contrast_color = (max_value, max_value, max_value)  # 白色文本
            cv2.putText(overlay, text, text_position, 
                        cv2.FONT_HERSHEY_SIMPLEX, font_scale, contrast_color, 2, cv2.LINE_AA)

            # 将半透明背景叠加到原图像上
            cv2.addWeighted(overlay, 0.5, img_with_fps, 0.5, 0, img_with_fps)
        else:
            img_with_fps = imgdata_np
        
        if layer_name in self.viewer.layers:
            if self.viewer.layers[layer_name].data.shape == img_with_fps.shape:
                self.viewer.layers[layer_name].data = img_with_fps
            else:
                self.viewer.layers.remove(layer_name)
                self.viewer.add_image(img_with_fps, name=layer_name)
                if self.camera_bit == 16:
                    self.viewer.layers[layer_name].contrast_limits = (0, 65535)
                else:
                    self.viewer.layers[layer_name].contrast_limits = (0, 255)
        else:
            self.viewer.add_image(img_with_fps, name=layer_name)
            if self.camera_bit == 16:
                self.viewer.layers[layer_name].contrast_limits = (0, 65535)
            else:
                self.viewer.layers[layer_name].contrast_limits = (0, 255)
        # print(f"layer_name: {layer_name}")
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
        if self.contrast_limits_name in self.viewer.layers:
            # 当对比度限制变化时触发的函数
            contrast_limits = self.viewer.layers[self.contrast_limits_name].contrast_limits
            # print(f"contrast_limit: {contrast_limits}")
            self.histogram_widget.update_min_max_lines(contrast_limits[0], contrast_limits[1])

    def toggle_auto_exposure(self):
        self.auto_exposure_dialog.exec_()

    def toggle_auto_white_balance(self):
        if self.auto_white_balance_button.text() == translations[self.language]['qhyccd_capture']['auto_white_balance_stop']:
            self.auto_white_balance_dialog.stop()
            self.auto_white_balance_button.setText(translations[self.language]['qhyccd_capture']['auto_white_balance'])
        else:
            self.auto_white_balance_dialog.start()
            self.auto_white_balance_button.setText(translations[self.language]['qhyccd_capture']['auto_white_balance_stop'])
            
    def on_auto_exposure_changed(self, mode):
        if mode == 0:
            self.exposure_time.setEnabled(True)
        else:
            self.exposure_time.setEnabled(False)
     
    def on_auto_exposure_value_changed(self, exposure_time):
        self.exposure_time.setValue(exposure_time)
        
    def on_auto_white_balance_complete(self, wb_red, wb_green, wb_blue):
        self.auto_white_balance_button.setEnabled(True)
        self.wb_red.setValue(wb_red)
        self.wb_green.setValue(wb_green)
        self.wb_blue.setValue(wb_blue)
        
    def on_auto_white_balance_values_changed(self, wb_red, wb_green, wb_blue):
        self.append_text(f"wb_red: {wb_red}, wb_green: {wb_green}, wb_blue: {wb_blue}")
           
    def get_image_layer(self):
        # 从最后一个图层开始向前检查，找到第一个图像图层
        for layer in reversed(self.viewer.layers):
            if isinstance(layer, napari.layers.Image):
                return layer.data
        # 如果没有找到图像图层，返回None
        return None
           
    def star_analysis(self):
        image = self.get_image_layer()
        if image is None:
            self.append_text(translations[self.language]['qhyccd_capture']['no_image_layer'])
            return
        self.append_text(translations[self.language]['qhyccd_capture']['prepare_to_star_analysis'])
        # 如果图像是彩色的，转换为灰度图
        if image.ndim == 3 and image.shape[2] == 3:
            image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        elif image.ndim == 4 and image.shape[-1] == 3:
            image = image[0]
            image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        if self.star_analysis_method_selector.currentText() == 'photutils':
            self.star_progress_bar.setRange(0, 0)
            from photutils import DAOStarFinder
            # 计算背景统计数据
            mean, median, std = sigma_clipped_stats(image, sigma=3.0)

            fwhm = self.star_fwhm.value()
            # 使用 DAOStarFinder 进行星点检测
            daofinder = DAOStarFinder(fwhm=fwhm, threshold=5.*std)
            sources = daofinder(image - median)
            if sources is None or len(sources) == 0:
                self.append_text(translations[self.language]['qhyccd_capture']['no_detected_stars'])
                self.star_progress_bar.setRange(0, 100)
                return

            # 创建新的星点信息表格
            self.star_table = QTableWidget()
            self.star_table.setWindowTitle("Detected Stars")
            self.star_table.setColumnCount(len(sources.colnames))  # 设置列数为 sources 表的列数
            self.star_table.setHorizontalHeaderLabels(sources.colnames)  # 设置表头为 sources 表的列名
            self.star_table.setRowCount(len(sources))  # 设置行数为检测到的星点数

            # 创建点的列表
            points = []

            # 填充表格并添加点
            for i, star in enumerate(sources):
                for j, col_name in enumerate(sources.colnames):
                    value = star[col_name]
                    if isinstance(value, float):
                        value = f"{value:.2f}"  # 格式化浮点数
                    self.star_table.setItem(i, j, QTableWidgetItem(str(value)))

                # 添加点到列表
                point = [star['ycentroid'], star['xcentroid']]
                points.append(point)

            # 显示表格
            self.star_table.show()

            # 在 napari 查看器中添加点图层
            if 'Star Points' in self.viewer.layers:
                self.viewer.layers['Star Points'].data = points
                layer_index = self.viewer.layers.index('Star Points')
                self.viewer.layers.move(layer_index, -1)
            else:
                self.viewer.add_points(points, size=fwhm, face_color='red', edge_color='white', name='Star Points')
            self.star_progress_bar.setRange(0, 100)
            self.append_text(translations[self.language]['qhyccd_capture']['star_analysis_completed'])
        elif self.star_analysis_method_selector.currentText() == 'Astrometry' and self.astrometrySolver is not None:
            dialog = AstrometryDialog(self, self.astrometrySolver,self.language)
            if dialog.exec_() == QDialog.Accepted:  # 检查对话框是否被接受
                self.star_progress_bar.setRange(0, 0)
                params = dialog.get_parameters()
                # print(f"params: {params}")  # 打印或使用参数
                self.astrometrySolver.start_solving(image_input=image, params=params)
                self.star_analysis_button.setEnabled(False)
            else:
                self.append_text(translations[self.language]['qhyccd_capture']['cancel_solving'])  # 可以根据需要处理用户取消的情况
            
    def parse_star_data(self,data):
        # 分割数据为行
        lines = data.strip().split('\n')
        title_line = lines[0].split()
        title_line.insert(0, "ID")
        star_dict = {}
        for i,title in enumerate(title_line):
            star_dict[title] = []
        for line in lines[1:]:
            parts = line.split()
            for i,title in enumerate(title_line):
                star_dict[title].append(float(parts[i]))
        return star_dict    
            
    def on_astrometry_finished(self, result):
        print(f"Astrometry result: {result}")
        self.append_text(f"Astrometry result: {result}")
        self.star_analysis_button.setEnabled(True)
        self.star_progress_bar.setRange(0, 100)
        self.append_text(translations[self.language]['qhyccd_capture']['star_analysis_completed'])
             
    def on_astrometry_error(self, error):
        warnings.warn(f"Astrometry error: {error}")
        self.append_text(f"Astrometry error: {error}")
        self.star_analysis_button.setEnabled(True)
        self.star_progress_bar.setRange(0, 100)
        
    def on_astrometry_star_info(self, data, wcs,wcs_tip):
        self.star_dict = self.parse_star_data(data)
        self.star_table = QTableWidget()
        self.star_table.setWindowTitle("Detected Stars")
        if wcs_tip:
            self.star_table.setColumnCount(len(self.star_dict) + 2)  
            headers = list(self.star_dict.keys()) + ['RA', 'Dec']
        else:
            self.star_table.setColumnCount(len(self.star_dict))
            headers = list(self.star_dict.keys())
        self.star_table.setHorizontalHeaderLabels(headers)
        self.star_table.setRowCount(len(self.star_dict[list(self.star_dict.keys())[0]]))

        points = []
        properties = {'info': []}  # 创建一个字典来存储每个点的信息
        
        for i in range(len(self.star_dict[list(self.star_dict.keys())[0]])):
            x = self.star_dict['X'][i]
            y = self.star_dict['Y'][i]
            if wcs_tip:
                ra, dec = wcs.all_pix2world(x, y, 0)
                info = f"RA: {ra:.6f}, Dec: {dec:.6f}"
                properties['info'].append(info)  # 将信息添加到 properties 字典中

            for j, key in enumerate(self.star_dict.keys()):
                value = self.star_dict[key][i]
                if isinstance(value, float):
                    value = f"{value:.2f}"
                self.star_table.setItem(i, j, QTableWidgetItem(str(value)))
            if wcs_tip:
                self.star_table.setItem(i, len(self.star_dict), QTableWidgetItem(f"{ra:.6f}"))
                self.star_table.setItem(i, len(self.star_dict) + 1, QTableWidgetItem(f"{dec:.6f}"))
            point = [y, x]  # 注意 napari 使用 (y, x) 格式
            points.append(point)

        self.star_table.show()

        # 在 napari 查看器中添加点图层并绑定鼠标悬停事件
        if 'Star Points' in self.viewer.layers:
            self.viewer.layers.remove('Star Points')
        if wcs_tip:
            points_layer = self.viewer.add_points(points, size=self.star_fwhm.value(), face_color='red', border_color='white', name='Star Points', properties=properties)
            points_layer.mouse_move_callbacks.append(self.display_point_info)
        else:
            points_layer = self.viewer.add_points(points, size=self.star_fwhm.value(), face_color='red', border_color='white', name='Star Points')
    
        self.star_progress_bar.setRange(0, 100)

    def display_point_info(self, layer, event):
        """显示鼠标悬停点的信息"""
        hovered_point_index = layer.get_value(event.position, world=True)
        if hovered_point_index is None:
            self.viewer.status = ""
            return
        info = layer.properties['info'][hovered_point_index]
        self.viewer.status = info  # 将信息显示在 napari 
        
    def save_star_table(self):
        if self.star_table is None:
            self.append_text(translations[self.language]['qhyccd_capture']['no_detected_stars'])
            return

        file_path, _ = QFileDialog.getSaveFileName(self, translations[self.language]['qhyccd_capture']['save_star_table'], "", "CSV Files (*.csv)")
        if file_path:
            with open(file_path, 'w', newline='') as file:
                writer = csv.writer(file)
                # 获取所有列的标题
                headers = [self.star_table.horizontalHeaderItem(i).text() for i in range(self.star_table.columnCount())]
                writer.writerow(headers)
                # 写入每一行的数据
                for row in range(self.star_table.rowCount()):
                    row_data = [self.star_table.item(row, col).text() for col in range(self.star_table.columnCount())]
                    writer.writerow(row_data)
            self.append_text(f"{translations[self.language]['qhyccd_capture']['star_table_saved']}: {file_path}")
        
@napari_hook_implementation
def napari_experimental_provide_dock_widget():
    """注册插件窗口部件"""
    return [CameraControlWidget]

