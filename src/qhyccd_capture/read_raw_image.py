from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QRadioButton, QButtonGroup
import numpy as np
from PyQt5.QtWidgets import QApplication, QComboBox
from pathlib import Path
from typing import List, Tuple, Any, Dict, Optional, Callable
from PyQt5.QtGui import QIntValidator
from PyQt5.QtCore import Qt

# 定义 FullLayerData 为包含数据、元数据字典和层类型字符串的元组
FullLayerData = Tuple[Any, Dict[str, Any], str]

# LayerData 可以是只有数据的元组、数据和元数据的元组，或者 FullLayerData
LayerData = FullLayerData

class DimensionDialog(QDialog):
    def __init__(self, pixel_count: int, image_name: str):
        super().__init__()
        self.image_name = image_name
        self.pixel_count = pixel_count
        self.initUI()

    def initUI(self):
        self.setWindowTitle('输入图像尺寸')
        self.layout = QVBoxLayout(self)

        # 创建一个水平布局用于宽度和高度输入
        self.dimension_layout = QHBoxLayout()

        # 宽度输入
        self.width_label = QLabel('宽度:', self)
        self.width_input = QLineEdit(self)
        self.width_input.setValidator(QIntValidator(1, 10000))  # 设置最小和最大值范围
        self.dimension_layout.addWidget(self.width_label)
        self.dimension_layout.addWidget(self.width_input)

        # 高度输入
        self.height_label = QLabel('高度:', self)
        self.height_input = QLineEdit(self)
        self.height_input.setValidator(QIntValidator(1, 10000))  # 设置最小和最大值范围
        self.dimension_layout.addWidget(self.height_label)
        self.dimension_layout.addWidget(self.height_input)

        # 将水平布局添加到主布局
        self.layout.addLayout(self.dimension_layout)

        # 创建位数输入
        self.bit_depth_layout = QHBoxLayout()
        self.bit_depth_label = QLabel('位数:', self)
        self.bit_depth_input = QLineEdit(self)
        self.bit_depth_input.setText('16')
        self.bit_depth_input.setValidator(QIntValidator(1, 16))  # 假设最大位数为16
        self.bit_depth_layout.addWidget(self.bit_depth_label)
        self.bit_depth_layout.addWidget(self.bit_depth_input)
        self.layout.addLayout(self.bit_depth_layout)

        # 创建字节序选择
        self.endianness_layout = QHBoxLayout()
        self.endianness_label = QLabel('字节序:', self)
        self.big_endian_radio = QRadioButton("大端", self)
        self.little_endian_radio = QRadioButton("小端", self)
        self.big_endian_radio.setChecked(True)  # 默认设置为大端
        self.endianness_layout.addWidget(self.endianness_label)
        self.endianness_layout.addWidget(self.big_endian_radio)
        self.endianness_layout.addWidget(self.little_endian_radio)
        self.layout.addLayout(self.endianness_layout)

        # 创建下拉选择框
        self.size_selector = QComboBox(self)
        self.size_selector.clear()
        for width, height in self.find_possible_dimensions(self.pixel_count):
            if self.width_input.text() == '' or self.height_input.text() == '':
                self.width_input.setText(str(width))
                self.height_input.setText(str(height))
            self.size_selector.addItem(f"{width}x{height}", (width, height))
        self.size_selector.currentIndexChanged.connect(self.update_dimensions_from_selection)
        self.layout.addWidget(self.size_selector)
        
        # 确认按钮
        self.confirm_button = QPushButton('确认', self)
        self.confirm_button.clicked.connect(self.accept)  # 使用 accept() 方法作为槽函数
        self.layout.addWidget(self.confirm_button)
        

    def getDimensions(self):
        return (int(self.width_input.text()), int(self.height_input.text()),
                int(self.bit_depth_input.text()),
                0 if self.big_endian_radio.isChecked() else 1)

    def update_dimensions_from_selection(self, index):
        width, height = self.size_selector.itemData(index)
        if width and height:
            self.width_input.setText(str(width))
            self.height_input.setText(str(height))
    
    def find_possible_dimensions(self, total_pixels):
        possible_sizes = []
        for i in range(1, int(total_pixels**0.5) + 1):
            if total_pixels % i == 0:
                j = total_pixels // i
                if i / j <= 2 and j / i <= 2:
                    possible_sizes.append((j, i))
        return possible_sizes

def raw_file_reader(path: str) -> List[LayerData]:
    try:
        with open(path, 'rb') as file:
            raw_data = file.read()
    except IOError as e:
        print(f"无法读取文件: {e}")
        return [(np.array([]).reshape(0, 0), {}, 'image')]  # 返回包含空图像层的列表
    file_name = Path(path).stem
    pixel_count = len(raw_data) // 2

    app = QApplication.instance() or QApplication([])
    dialog = DimensionDialog(pixel_count, file_name)
    if dialog.exec_():  # 使用 exec_() 方法显示对话框，并等待用户确认
        width, height, bit_depth, endianness = dialog.getDimensions()
        if width <= 0 or height <= 0 or bit_depth <= 0 or endianness not in [0, 1]:
            print("输入的尺寸无效。")
            return [(np.array([]).reshape(0, 0), {}, 'image')]  # 返回包含空图像层的列表

        # 处理图像数据
        try:
            if endianness == 0:
                data = np.frombuffer(raw_data, dtype=np.uint16).reshape((height, width))
            else:
                data = np.frombuffer(raw_data, dtype=np.uint16).byteswap().reshape((height, width))
        except ValueError as e:
            print(f"尺寸与数据不匹配: {e}")
            return [(np.array([]).reshape(0, 0), {}, 'image')]  # 返回包含空图像层的列表

        # 根据位数调整数据
        if bit_depth < 16:
            shift_amount = 16 - bit_depth
            data = data << shift_amount  # 右移以适配位数

        meta = {"name": file_name, "file_name": Path(path).name}
        layer_attributes = {"name": meta["name"], "metadata": meta}
        return [(data, layer_attributes, 'image')]
    else:
        print("用户取消操作。")
        return [(np.array([]).reshape(0, 0), {}, 'image')]  # 用户取消时返回空图像层列表

def napari_get_reader(path: str) -> Optional[Callable[[str], List[LayerData]]]:
    if isinstance(path, str) and path.endswith('.raw'):
        return raw_file_reader
    return None
