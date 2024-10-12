from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QComboBox, QFormLayout, QFileDialog, QMessageBox, QSizePolicy, QSpacerItem  # 添加此行以导入QFileDialog
from PyQt5.QtCore import pyqtSignal, QTimer  # 导入信号和QTimer
from .language import translations
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDoubleSpinBox
from .control_id import CONTROL_ID

class AutoExposureDialog(QDialog):
    mode_changed = pyqtSignal(int)
    exposure_value_signal = pyqtSignal(float)  # 新增信号，用于发送曝光值

    def __init__(self,qhyccddll,camera,language, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.language = language
        self.qhyccddll = qhyccddll
        self.camera = camera
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
            self.mask_mode_combo.setItemData(self.mask_mode_combo.count() - 1, tooltip, Qt.ToolTipRole)

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
        # 获取曝光模式的参数限制
        min, max, step = self.parent.getParamlimit(CONTROL_ID.CONTROL_AUTOEXPOSURE.value)
        print(f"CONTROL_AUTOEXPOSURE min: {min}, max: {max}, step: {step}")
        # 遍历现有的曝光模式，检查它们是否在允许的范围内
        for mode_text, mode_value in list(self.exposure_mode_dict.items()):
            if not (min <= mode_value <= max):
                # 如果模式值不在范围内，从字典和下拉框中移除该模式
                self.exposure_mode_combo.removeItem(self.exposure_mode_combo.findText(mode_text))

        min, max, step = self.parent.getParamlimit(CONTROL_ID.CONTROL_AUTOEXPgainMax.value)
        print(f"CONTROL_AUTOEXPgainMax min: {min}, max: {max}, step: {step}")
        self.gain_Max.setRange(min, max)
        self.gain_Max.setSingleStep(step)
        gain_data = self.qhyccddll.GetQHYCCDParam(self.camera, CONTROL_ID.CONTROL_AUTOEXPgainMax.value)
        self.gain_Max.setValue(gain_data)
        min, max, step = self.parent.getParamlimit(CONTROL_ID.CONTROL_AUTOEXPexpMaxMS.value)
        print(f"CONTROL_AUTOEXPexpMaxMS min: {min}, max: {max}, step: {step}")
        self.exposure_time.setRange(min, max)
        self.exposure_time.setSingleStep(step)
        exposure_data = self.qhyccddll.GetQHYCCDParam(self.camera, CONTROL_ID.CONTROL_AUTOEXPexpMaxMS.value)
        self.exposure_time.setValue(exposure_data)
    
    def apply_changes(self):
        mode = self.exposure_mode_combo.currentIndex()
        if mode == 0:
            if self.qhyccddll.GetQHYCCDParam(self.camera, CONTROL_ID.CONTROL_AUTOEXPOSURE.value) != 0:
                ret = self.qhyccddll.SetQHYCCDParam(self.camera, CONTROL_ID.CONTROL_AUTOEXPOSURE.value, 0.0)
                if ret != 0:
                    self.parent.append_text(f"{translations[self.language]['auto_exposure']['error']}:{translations[self.language]['auto_exposure']['set_auto_exposure_mode_error']}")  
                    QMessageBox.critical(self, translations[self.language]['auto_exposure']['error'], translations[self.language]['auto_exposure']['set_auto_exposure_mode_error'])
                    return
            self.timer.stop()
        elif mode == 1:
            if self.qhyccddll.GetQHYCCDParam(self.camera, CONTROL_ID.CONTROL_AUTOEXPOSURE.value) != 1:
                ret = self.qhyccddll.SetQHYCCDParam(self.camera, CONTROL_ID.CONTROL_AUTOEXPOSURE.value, 1.0)
                if ret != 0:
                    self.parent.append_text(f"{translations[self.language]['auto_exposure']['error']}:{translations[self.language]['auto_exposure']['set_auto_exposure_mode_error']}")
                    QMessageBox.critical(self, translations[self.language]['auto_exposure']['error'], translations[self.language]['auto_exposure']['set_auto_exposure_mode_error'])
                    return
            gain_max = int(self.gain_Max.value())
            ret = self.qhyccddll.SetQHYCCDParam(self.camera, CONTROL_ID.CONTROL_AUTOEXPgainMax.value, gain_max)
            if ret != 0:
                self.parent.append_text(f"{translations[self.language]['auto_exposure']['error']}:{translations[self.language]['auto_exposure']['set_gain_max_error']}")
                QMessageBox.critical(self, translations[self.language]['auto_exposure']['error'], translations[self.language]['auto_exposure']['set_gain_max_error'])
                return
            self.timer.start(500)  # 设置计时器每1000毫秒（1秒）触发一次
        elif mode == 2:
            if self.qhyccddll.GetQHYCCDParam(self.camera, CONTROL_ID.CONTROL_AUTOEXPOSURE.value) != 2:
                ret = self.qhyccddll.SetQHYCCDParam(self.camera, CONTROL_ID.CONTROL_AUTOEXPOSURE.value, 2.0)
                if ret != 0:
                    self.parent.append_text(f"{translations[self.language]['auto_exposure']['error']}:{translations[self.language]['auto_exposure']['set_auto_exposure_mode_error']}")
                    QMessageBox.critical(self, translations[self.language]['auto_exposure']['error'], translations[self.language]['auto_exposure']['set_auto_exposure_mode_error'])
                    return
            exposure_time = int(self.exposure_time.value())
            ret = self.qhyccddll.SetQHYCCDParam(self.camera, CONTROL_ID.CONTROL_AUTOEXPexpMaxMS.value, exposure_time)
            if ret != 0:
                self.parent.append_text(f"{translations[self.language]['auto_exposure']['error']}:{translations[self.language]['auto_exposure']['set_exposure_time_error']}")
                QMessageBox.critical(self, translations[self.language]['auto_exposure']['error'], translations[self.language]['auto_exposure']['set_exposure_time_error'])
                return
            self.timer.start(500)  # 设置计时器每1000毫秒（1秒）触发一次
        elif mode == 3:
            if self.qhyccddll.GetQHYCCDParam(self.camera, CONTROL_ID.CONTROL_AUTOEXPOSURE.value) != 3:
                ret = self.qhyccddll.SetQHYCCDParam(self.camera, CONTROL_ID.CONTROL_AUTOEXPOSURE.value, 3.0)
                if ret != 0:
                    self.parent.append_text(f"{translations[self.language]['auto_exposure']['error']}:{translations[self.language]['auto_exposure']['set_auto_exposure_mode_error']}")
                    QMessageBox.critical(self, translations[self.language]['auto_exposure']['error'], translations[self.language]['auto_exposure']['set_auto_exposure_mode_error'])
                    return
            gain_max = int(self.gain_Max.value())
            ret = self.qhyccddll.SetQHYCCDParam(self.camera, CONTROL_ID.CONTROL_AUTOEXPgainMax.value, gain_max)
            if ret != 0:
                self.parent.append_text(f"{translations[self.language]['auto_exposure']['error']}:{translations[self.language]['auto_exposure']['set_gain_max_error']}")
                QMessageBox.critical(self, translations[self.language]['auto_exposure']['error'], translations[self.language]['auto_exposure']['set_gain_max_error'])
                return
            exposure_time = int(self.exposure_time.value())
            ret = self.qhyccddll.SetQHYCCDParam(self.camera, CONTROL_ID.CONTROL_AUTOEXPexpMaxMS.value, exposure_time)
            if ret != 0:
                self.parent.append_text(f"{translations[self.language]['auto_exposure']['error']}:{translations[self.language]['auto_exposure']['set_exposure_time_error']}")
                QMessageBox.critical(self, translations[self.language]['auto_exposure']['error'], translations[self.language]['auto_exposure']['set_exposure_time_error'])
                return
            self.timer.start(500)  # 设置计时器每1000毫秒（1秒）触发一次
        elif mode == 4:
            pass
        self.mode_changed.emit(mode)
        self.parent.append_text(f"{translations[self.language]['auto_exposure']['apply_success']}:{self.exposure_mode_combo.currentText()}")
        
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
        # 获取当前曝光值
        exposure_value = self.qhyccddll.GetQHYCCDParam(self.camera, CONTROL_ID.CONTROL_EXPOSURE.value)
        self.exposure_value_signal.emit(exposure_value)  # 发送信号