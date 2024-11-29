from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QComboBox, QFormLayout, QFileDialog, QMessageBox, QSizePolicy, QSpacerItem  # 添加此行以导入QFileDialog
from PyQt5.QtCore import pyqtSignal, QTimer  # 导入信号和QTimer
from .language import translations
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDoubleSpinBox
from .control_id import CONTROL_ID

class AutoExposureDialog(QDialog):
    mode_changed = pyqtSignal(int)

    def __init__(self,camera,language,sdk_input_queue, parent=None):
        super().__init__(parent)
        self.language = language
        self.camera = camera
        self.sdk_input_queue = sdk_input_queue
        self.setWindowTitle(translations[self.language]["auto_exposure"]["auto_exposure"])
        self.setGeometry(100, 100, 400, 300)

        # 主布局
        layout_area = QVBoxLayout()
        form_layout = QFormLayout()

        # 曝光模式选择框    
        self.exposure_mode_dict = {translations[self.language]['auto_exposure']['mode_off']:0,  # 关闭自动曝光
            translations[self.language]['auto_exposure']['mode_gain_only']:1,  # 仅调节gain模式
            translations[self.language]['auto_exposure']['mode_exp_only']:2,  # 仅调节exp模式
            translations[self.language]['auto_exposure']['mode_hybrid']:3,  # 混合调节模式
            translations[self.language]['auto_exposure']['mode_all_day']:4  # 全天模式(暂未实现)
        }
        self.exposure_mode_label = QLabel(translations[self.language]['auto_exposure']['auto_exposure'])
        # 创建曝光模式选择框
        self.exposure_mode_combo = QComboBox()
        self.exposure_mode_combo.addItems(self.exposure_mode_dict.keys())
        self.exposure_mode_combo.currentIndexChanged.connect(self.auto_exposure_mode_changed)
        # 将选择框加入窗口布局
        
        form_layout.addRow(self.exposure_mode_label, self.exposure_mode_combo)
        
        self.exposure_time = QDoubleSpinBox()  # 修改为 QDoubleSpinBox
        self.exposure_time.setSuffix(' ms')  # 设置单位为毫秒
        self.exposure_time.setDecimals(3)  # 保留三位小数
        
        form_layout.addRow(QLabel(translations[self.language]['auto_exposure']['exposure_threshold']), self.exposure_time)
        
        self.gain_Max = QDoubleSpinBox()
        self.gain_Max.setSuffix(' dB')  # 设置单位为毫秒
        self.gain_Max.setDecimals(3)  # 保留三位小数
        form_layout.addRow(QLabel(translations[self.language]['auto_exposure']['gain_Max']), self.gain_Max)
        
        
        # 创建遮罩模式选择框
        self.mask_mode_combo = QComboBox()
        mask_mode_dict = {
            translations[self.language]['auto_exposure']['no_mask']: (0, ""),
            translations[self.language]['auto_exposure']['mask_a']: (1, translations[self.language]['auto_exposure']['mask_a_tooltip']),
            translations[self.language]['auto_exposure']['mask_b']: (2, translations[self.language]['auto_exposure']['mask_b_tooltip'])
        }
        
        for mode, (value, tooltip) in mask_mode_dict.items():
            self.mask_mode_combo.addItem(mode, value)  # 修改此行，添加value作为item的userData
            self.mask_mode_combo.setItemData(self.mask_mode_combo.count() - 1, tooltip, Qt.ToolTipRole)  # type: ignore

        # 将遮罩模式选择框加入窗口布局
        form_layout.addRow(self.mask_mode_combo)

        layout_area.addLayout(form_layout)

        # 按钮布局
        button_layout = QHBoxLayout()
        apply_button = QPushButton(translations[self.language]['auto_exposure']['apply'])
        cancel_button = QPushButton(translations[self.language]['auto_exposure']['cancel'])
        
        # 连接按钮信号
        apply_button.clicked.connect(self.apply_changes)
        cancel_button.clicked.connect(self.reject_changes)  # 使用新的 reject_changes 方法

        # 将按钮添加到布局中
        button_layout.addWidget(apply_button)
        button_layout.addWidget(cancel_button)

        # 将按钮布局添加到主布局中
        layout_area.addLayout(button_layout)

        self.setLayout(layout_area)

        # 保存初始状态
        self.initial_exposure_mode = self.exposure_mode_combo.currentIndex()
        self.initial_mask_mode = self.mask_mode_combo.currentIndex()
        self.initial_exposure_time = self.exposure_time.value()
        self.initial_gain_max = self.gain_Max.value()
        
        self.update_limits()

        self.timer = QTimer(self)  # 创建计时器
        self.timer.timeout.connect(self.send_exposure_value)  # 连接信号

    def update_limits(self):
        self.sdk_input_queue.put({"order":"get_auto_exposure_limits","data":""})

    def update_limits_success(self,data ):
        self.exposure_mode_combo.clear()
        for mode_text, mode_value in list(data['mode'].items()):
            self.exposure_mode_combo.addItem(mode_text, mode_value)
        min, max, step = data['gain'][0:-1]
        self.gain_Max.setRange(min, max)
        self.gain_Max.setSingleStep(step)
        gain_data = data['gain'][-1]
        self.gain_Max.setValue(gain_data)
        min, max, step = data['exposure'][0:-1]
        self.exposure_time.setRange(min, max)
        self.exposure_time.setSingleStep(step)
        exposure_data = data['exposure'][-1]
        self.exposure_time.setValue(exposure_data)
    
    def apply_changes(self):
        self.sdk_input_queue.put({"order":"set_auto_exposure","data":(self.exposure_mode_combo.currentIndex(),self.gain_Max.value(),self.exposure_time.value())})
        
    def apply_changes_success(self,mode):
        if mode == 0:
            self.timer.stop()
        elif mode == 1 or mode == 2 or mode == 3:
            self.timer.start(500)  
        elif mode == 4:
            pass
        
        self.mode_changed.emit(mode)
        self.initial_exposure_mode = self.exposure_mode_combo.currentIndex()
        self.initial_mask_mode = self.mask_mode_combo.currentIndex()
        self.initial_exposure_time = self.exposure_time.value()
        self.initial_gain_max = self.gain_Max.value()
        
        self.hide_dialog()

    def reject_changes(self):
        # 恢复到上一次应用的 UI 状态
        self.restore_ui()
        # 取消更改后隐藏窗口
        self.hide_dialog()

    def restore_ui(self):
        # 恢复曝光模式和遮罩模式选择框到初始状态
        self.exposure_mode_combo.setCurrentIndex(self.initial_exposure_mode)
        self.mask_mode_combo.setCurrentIndex(self.initial_mask_mode)
        # 恢复曝光时间和增益到初始值
        self.exposure_time.setValue(self.initial_exposure_time)
        self.gain_Max.setValue(self.initial_gain_max)

    def hide_dialog(self):
        # 隐藏对话框前确保对话框不是模态的
        self.hide()

    def auto_exposure_mode_changed(self):
        mode = self.exposure_mode_combo.currentIndex()
        if mode == 0:
            self.exposure_time.setEnabled(False)
            self.gain_Max.setEnabled(False)
        elif mode == 1:
            self.exposure_time.setEnabled(False)
            self.gain_Max.setEnabled(True)
        elif mode == 2:
            self.exposure_time.setEnabled(True)
            self.gain_Max.setEnabled(False)
        elif mode == 3:
            self.exposure_time.setEnabled(True)
            self.gain_Max.setEnabled(True)

    def send_exposure_value(self):
        self.sdk_input_queue.put({"order":"get_exposure_value","data":""})
