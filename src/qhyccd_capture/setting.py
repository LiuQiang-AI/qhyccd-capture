import json
import os

from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QComboBox, QFormLayout, QFileDialog, QMessageBox, QSizePolicy, QSpacerItem  # 添加此行以导入QFileDialog
from PyQt5.QtCore import pyqtSignal  # 导入信号
from .language import translations
from PyQt5.QtGui import QFont

class SettingsDialog(QDialog):
    language_changed = pyqtSignal(str)  # 定义一个信号，用于语言更改

    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings_file = "settings.json"  # 设置文件路径
        self.load_settings()  # 加载设置
        # self.parent = parent
        self.setWindowTitle(translations[self.language]["setting"]["settings"])
        self.setGeometry(100, 100, 400, 300)



        layout = QVBoxLayout()
        
        self.camera_info_label = QLabel(translations[self.language]["qhyccd_capture"]["camera_info_disconnected"])
        # self.camera_info_label.setStyleSheet("border: 1px solid black;")  # 设置边框
        # 创建一个 QFont 对象，指定字体和大小
        monospace_font = QFont("Courier New", 20)  # 你可以选择 'Consolas', 'Courier New', 或其他等宽字体

        # 设置 camera_info_label 的字体为等宽字体
        self.camera_info_label.setFont(monospace_font)
        layout.addWidget(self.camera_info_label)
        
        # 添加设置控件
        self.qhyccd_path_label = QLabel()  # 使用加载的路径
        self.qhyccd_path_label.setStyleSheet("border: 1px solid black;")  # 设置边框

        self.select_qhyccd_path_button = QPushButton('SDK')
        self.select_qhyccd_path_button.clicked.connect(self.select_qhyccd_path)

        # 创建水平布局
        h_layout = QHBoxLayout()
        h_layout.addWidget(self.qhyccd_path_label)
        h_layout.addWidget(self.select_qhyccd_path_button)
        
        # 添加语言选择
        self.language_name = {"中文":"zh","English":"en"}
        self.language_label = QLabel(translations[self.language]["setting"]["language"])
        self.language_combo = QComboBox()
        self.language_combo.addItems(self.language_name.keys())
        self.language_combo.setCurrentText(self.language)  # 设置默认语言
        
        # 创建表单布局
        form_layout = QFormLayout()
        form_layout.addRow(self.language_label, self.language_combo)
        form_layout.addRow(h_layout)
        
        layout.addLayout(form_layout)
        
        # 创建一个垂直方向的 spacer
        spacer = QSpacerItem(20, 2, QSizePolicy.Minimum, QSizePolicy.Expanding)

        # 将 spacer 添加到布局的底部
        layout.addItem(spacer)
        
        # 添加底部按钮
        self.apply_button = QPushButton(translations[self.language]["setting"]["apply"])
        self.apply_button.clicked.connect(self.save_settings)  # 保存设置
        self.cancel_button = QPushButton(translations[self.language]["setting"]["cancel"])
        self.cancel_button.clicked.connect(self.cancel_settings)  # 连接取消按钮到取消设置的方法
        self.reset_button = QPushButton(translations[self.language]["setting"]["reset"])
        self.reset_button.clicked.connect(self.reset_settings)  # 连接重置按钮到重置设置的方法
        
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.apply_button)
        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.reset_button)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        self.update_ui()  # 启动时更新UI

    def load_settings(self):
        if os.path.exists(self.settings_file):
            with open(self.settings_file, 'r') as f:
                settings = json.load(f)
                self.qhyccd_path = settings.get("qhyccd_path", "")
                self.language = settings.get("language", "zh")
        else:
            self.qhyccd_path = ""
            self.language = "zh"  # 默认语言

    def save_settings(self):
        current_language = self.language_combo.currentText()
        settings = {
            "qhyccd_path": self.qhyccd_path_label.text(),
            "language": self.language_name[self.language_combo.currentText()]
        }
        with open(self.settings_file, 'w') as f:
            json.dump(settings, f)
        QMessageBox.information(self, translations[self.language]["setting"]["settings_saved"], translations[self.language]["setting"]["settings_saved_message"])  # 添加提示信息

    def select_qhyccd_path(self):
        file_path, _ = QFileDialog.getOpenFileName(self, translations[self.language]["setting"]["select_qhyccd_path"], "", "DLL Files (*.dll);;SO Files (*.so)")
        if file_path:
            self.qhyccd_path_label.setText(file_path)
            self.qhyccd_path = file_path

    def cancel_settings(self):
        self.hide()  # 隐藏对话框
        self.load_settings()  # 重新加载设置
        self.update_ui()  # 更新UI以反映加载的设置

    def reset_settings(self):
        self.load_settings()  # 重新加载设置
        self.update_ui()  # 更新UI以反映加载的设置

    def update_ui(self):
        # 创建一个反向映射从语言代码到语言名称
        language_key = {v: k for k, v in self.language_name.items()}
        # 使用反向映射设置当前语言的正确显示名称
        self.language_combo.setCurrentText(language_key[self.language])
        self.qhyccd_path_label.setText(self.qhyccd_path)  # 更新路径标签
      


