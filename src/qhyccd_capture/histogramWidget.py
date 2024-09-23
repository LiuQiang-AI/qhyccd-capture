import numpy as np
import matplotlib.pyplot as plt
from PyQt5.QtWidgets import QWidget, QVBoxLayout  # 导入 QWidget 和 QVBoxLayout
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from napari import Viewer  # 导入 Viewer
from napari.layers import Image  # 导入 Image 层

class HistogramWidget(QWidget):  # 保持类名不变
    def __init__(self, viewer: Viewer):  # 添加 viewer 参数
        super().__init__()
        self.setWindowTitle("Histogram")  # 设置窗口标题

        self.layout = QVBoxLayout()
        self.canvas = FigureCanvas(plt.figure())
        self.layout.addWidget(self.canvas)

        self.setLayout(self.layout)  # 设置布局
        
        self.setMinimumSize(400, 300)

        # 初始化为空白画布  {{ edit_1 }}
        self.ax = self.canvas.figure.add_subplot(111)  # 添加子图
        self.ax.clear()  # 清空子图以初始化为空白画布
        self.canvas.draw()  # 更新画布

        # 将部件添加到 Napari 窗口的左侧  {{ edit_2 }}
        viewer.window.add_dock_widget(self, area='left', name='Histogram')

        # Initialize histogram and lines
        self.histogram = None
        self.min_line = None
        self.max_line = None

        self.hide()  # Initialize hidden window

    def show_widget(self):  # 新增方法
        """显示 HistogramWidget 窗口"""
        print("show_widget")
        self.show()  # 显示窗口
        self.canvas.show()  # 显示画布  {{ edit_1 }}

    def hide_widget(self):  # 新增方法
        """隐藏 HistogramWidget 窗口"""
        print("hide_widget")
        self.hide()  # 隐藏窗口
        self.canvas.hide()  # 隐藏画布  {{ edit_2 }}

    def update_histogram(self, img):
        """Update histogram"""
        # 清除当前直方图线
        if self.histogram is not None:
            if isinstance(self.histogram, list):  # 如果是列表，移除所有线
                for line in self.histogram:
                    line.remove()
            else:
                self.histogram.remove()  # 移除之前的直方图线

        # 计算直方图
        if img.ndim == 2:  # 灰度图像
            if img.dtype == np.uint8:  # 8位图像
                histogram, bins = np.histogram(img.flatten(), bins=256, range=[0, 256])
                plt.xlim([0, 255])
            elif img.dtype == np.uint16:  # 16位图像
                histogram, bins = np.histogram(img.flatten(), bins=65536, range=[0, 65536])
                plt.xlim([0, 65535])
            else:
                raise ValueError("Unsupported image depth for grayscale")

            # 绘制新的直方图
            self.histogram, = plt.plot(bins[:-1], histogram, color='black')  # 更新直方图引用

        else:  # 彩色图像
            colors = ('r', 'g', 'b')
            self.histogram = []  # 初始化为列表以存储每个通道的直方图
            for i, color in enumerate(colors):
                if img.dtype == np.uint8:  # 8位图像
                    histogram, bins = np.histogram(img[:, :, i].flatten(), bins=256, range=[0, 256])
                    plt.xlim([0, 255])
                elif img.dtype == np.uint16:  # 16位图像
                    histogram, bins = np.histogram(img[:, :, i].flatten(), bins=65536, range=[0, 65536])
                    plt.xlim([0, 65535])
                else:
                    raise ValueError("Unsupported image depth for color")

                # 绘制每个通道的直方图
                line, = plt.plot(bins[:-1], histogram, color=color, label=f'{color.upper()} Channel')
                self.histogram.append(line)  # 将每个通道的直方图线添加到列表中

        # 更新画布
        if not self.canvas.isVisible():
            self.canvas.show()
        if any(artist.get_label() for artist in plt.gca().get_lines()):
            plt.legend()
        self.canvas.draw()  # Update drawing

    def update_min_max_lines(self, min_value, max_value):
        """Update min and max lines"""
        # 移除旧的最小和最大线
        if self.min_line is not None:
            self.min_line.remove()  # 移除旧的最小线
        if self.max_line is not None:
            self.max_line.remove()  # 移除旧的最大线

        # 绘制新的最小和最大线
        self.min_line = plt.axvline(x=min_value, color='red', linestyle='--', label='Min Value')  # Min line
        self.max_line = plt.axvline(x=max_value, color='green', linestyle='--', label='Max Value')  # Max line

        # 更新画布
        plt.legend()
        self.canvas.draw()  # Update drawing
