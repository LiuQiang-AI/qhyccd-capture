from PyQt5.QtWidgets import QWidget, QVBoxLayout, QPushButton, QTableWidget, QTableWidgetItem, QFileDialog, QComboBox
import json
import os
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog
from PyQt5.QtWidgets import QHeaderView  # Import QHeaderView for column resizing
from .language import translations
from .fits_header_defaults import get_header_defaults
from PyQt5.QtWidgets import QInputDialog
from PyQt5.QtWidgets import QMessageBox  # Import QMessageBox for confirmation dialog

class FitsHeaderEditor(QDialog):
    def __init__(self, viewer, language='en'):
        super().__init__()
        self.language = language
        self.HEADER_DEFAULTS = get_header_defaults(language)
        self.viewer = viewer
        
        self.setWindowFlags(self.windowFlags() | Qt.Window)  # 确保窗口是独立的并且具有窗口装饰
        self.setWindowTitle(translations[self.language]['fits_header']['fits_header_editor'])  # 设置窗口标题
        self.resize(800, 600)  # 设置初始大小
        
        self.init_ui()
        self.update_header_files_list()  # 确保启动时更新文件列表

    def init_ui(self):
        self.layout = QVBoxLayout(self)
        self.init_table()
        self.init_buttons()
        self.init_header_files_combo()
        self.setLayout(self.layout)

    def init_table(self):
        self.header_table = QTableWidget()
        self.header_table.setColumnCount(3)
        self.header_table.setHorizontalHeaderLabels(['Keyword', 'Value', 'Description'])
        self.layout.addWidget(self.header_table)
        header = self.header_table.horizontalHeader()  # 获取表格的水平头部
        header.setSectionResizeMode(QHeaderView.Stretch)  # 设置所有列自动调整大小填满表格
        header.setStretchLastSection(True)  # 设置最后一列拉伸以填满剩余空间
        self.populate_default_headers()

    def populate_default_headers(self):
        # 使用 HEADER_DEFAULTS 字典填充表格
        self.header_table.setRowCount(len(self.HEADER_DEFAULTS))
        for row, (key, desc) in enumerate(self.HEADER_DEFAULTS.items()):
            self.header_table.setItem(row, 0, QTableWidgetItem(key))
            self.header_table.setItem(row, 1, QTableWidgetItem(""))  # 初始化值为空
            self.header_table.setItem(row, 2, QTableWidgetItem(desc))

    def init_buttons(self):
        self.save_button = QPushButton(translations[self.language]['fits_header']['save_header'])
        self.save_button.clicked.connect(self.save_header_as_json)  # 修改连接到新的保存方法
        self.layout.addWidget(self.save_button)

        self.delete_button = QPushButton(translations[self.language]['fits_header']['delete_header'])
        self.delete_button.clicked.connect(self.delete_header)
        self.layout.addWidget(self.delete_button)

    def init_header_files_combo(self):
        self.header_files_combo = QComboBox()
        self.layout.addWidget(self.header_files_combo)
        self.header_files_combo.currentIndexChanged.connect(self.on_header_file_selected)

    def update_header_files_list(self):
        self.header_files_combo.clear()
        default_file_path = "headers.json"
        if os.path.exists(default_file_path):
            with open(default_file_path, 'r') as file:
                all_headers = json.load(file)
                for header_name in all_headers.keys():
                    self.header_files_combo.addItem(header_name)

    def on_header_file_selected(self, index):
        header_name = self.header_files_combo.itemText(index)
        if header_name:
            default_file_path = "headers.json"
            with open(default_file_path, 'r') as file:
                all_headers = json.load(file)
                header_data = all_headers.get(header_name, {})
                self.populate_table_with_header_data(header_data)

    def populate_table_with_header_data(self, header_data):
        current_row_count = self.header_table.rowCount()
        new_row_count = len(header_data)
        if new_row_count > current_row_count:
            self.header_table.setRowCount(new_row_count)  # 确保有足够的行

        row = 0
        for key, value in header_data.items():
            # 确保每个单元格都已经初始化
            if not self.header_table.item(row, 0):
                self.header_table.setItem(row, 0, QTableWidgetItem(key))
            if not self.header_table.item(row, 1):
                self.header_table.setItem(row, 1, QTableWidgetItem(""))
            if not self.header_table.item(row, 2):
                self.header_table.setItem(row, 2, QTableWidgetItem(""))

            # 仅当值有效时更新数据
            if value['value'] not in [None, '', ' ']:
                self.header_table.item(row, 0).setText(key)
                self.header_table.item(row, 1).setText(value['value'])
                self.header_table.item(row, 2).setText(value['description'])
            else:
                # 如果值无效，保留原有数据，只更新 key 和 description
                self.header_table.item(row, 0).setText(key)
                self.header_table.item(row, 2).setText(value['description'])

            row += 1

        if row < current_row_count:
            # 清除多余的行
            for clear_row in range(row, current_row_count):
                self.header_table.removeRow(clear_row)

    def save_header_as_json(self):
        header_data = {}
        for row in range(self.header_table.rowCount()):
            key = self.header_table.item(row, 0).text()
            value = self.header_table.item(row, 1).text()
            description = self.header_table.item(row, 2).text()
            header_data[key] = {'value': value, 'description': description}

        # 弹出输入框让用户输入 header 的名称
        header_name, ok = QInputDialog.getText(self, translations[self.language]['fits_header']['input_header_name'], translations[self.language]['fits_header']['please_enter_header_name'])
        if ok and header_name:
            all_headers = {}
            default_file_path = "headers.json"  # 所有 headers 保存在同一个文件
            # 尝试读取现有的 JSON 文件以更新内容
            if os.path.exists(default_file_path):
                with open(default_file_path, 'r') as file:
                    all_headers = json.load(file)
            
            # 更新或添加新的 header 信息
            all_headers[header_name] = header_data

            # 保存更新后的所有 headers
            with open(default_file_path, 'w') as file:
                json.dump(all_headers, file, indent=4)
        
        self.update_header_files_list()  # 在保存后更新下拉框列表

    def delete_header(self):
        header_name = self.header_files_combo.currentText()  # 获取当前选中的 header 名称
        if header_name:
            reply = QMessageBox.question(self, translations[self.language]['fits_header']['confirm_delete'], f" {translations[self.language]['fits_header']['confirm_delete_header']} '{header_name}' ?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                default_file_path = "headers.json"
                if os.path.exists(default_file_path):
                    with open(default_file_path, 'r') as file:
                        all_headers = json.load(file)
                    # 从字典中删除选定的 header
                    if header_name in all_headers:
                        del all_headers[header_name]
                        # 保存更新后的 JSON 文件
                        with open(default_file_path, 'w') as file:
                            json.dump(all_headers, file, indent=4)
                        self.update_header_files_list()  # 确保在删除后更新下拉框列��

                        if self.header_files_combo.count() > 0:
                            self.header_files_combo.setCurrentIndex(0)  # 选择第一个 header
                            self.on_header_file_selected(0)  # 加载选中的 header
                        else:
                            self.populate_default_headers()  # 没有保存的 header，加载默认数据
                            self.header_table.clearContents()  # 清空表格内容
                            self.header_table.setRowCount(len(self.HEADER_DEFAULTS))  # 重置行数为默认 header 的数量
                            self.populate_default_headers()  # 使用默认数据填充表格

    def toggle_window(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()

    def find_row_by_key(self, key):
        for row in range(self.header_table.rowCount()):
            if self.header_table.item(row, 0).text() == key:
                return row
        return -1

    def update_table_with_dict(self, update_data):
        for key, value in update_data.items():
            row = self.find_row_by_key(key)
            if row != -1:  # 键存在于表格中
                self.header_table.item(row, 1).setText(str(value))

    def get_table_data(self, include_empty=False):
        """
        以字典形式返回表格中的数据。
        :param include_empty: 是否包含值为空的项，默认为 False。
        :return: 字典，键为表格中的关键字，值为对应的值和描述。
        """
        data = {}
        for row in range(self.header_table.rowCount()):
            key = self.header_table.item(row, 0).text()
            value = self.header_table.item(row, 1).text()
            description = self.header_table.item(row, 2).text()
            if not include_empty and value in ['', ' ',None]:
                continue
            data[key] = {'value': value, 'description': description}
        if len(data) == 0:
            data = None
        return data

