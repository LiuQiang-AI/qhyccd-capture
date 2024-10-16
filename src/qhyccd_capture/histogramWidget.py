import numpy as np
import matplotlib.pyplot as plt
from PyQt5.QtWidgets import QWidget, QVBoxLayout  # 导入 QWidget 和 QVBoxLayout
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from napari import Viewer  # 导入 Viewer
from napari.layers import Image  # 导入 Image 层
from .language import translations
from scipy.ndimage import gaussian_filter
import threading

class HistogramWidget(QWidget):  # 保持类名不变
    def __init__(self, viewer: Viewer, img_buffer, language: str):  # 添加 viewer 参数
        super().__init__()
        
        self.viewer = viewer
        self.img_buffer = img_buffer
        self.language = language
        
        self.setWindowTitle(translations[self.language]["histogramWidget"]["histogram"])  # 设置窗口标题

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
        self.viewer.window.add_dock_widget(self, area='left', name=translations[self.language]["histogramWidget"]["histogram"])

        # Initialize histogram and lines
        self.histogram = None
        self.min_line = None
        self.max_line = None

        self.hide()  # Initialize hidden window

        self.update_lock = threading.Lock()  # 添加一个线程锁

    def show_widget(self):  # 新增方法
        """显示 HistogramWidget 窗"""
        if translations[self.language]["histogramWidget"]["histogram"] not in [name for name in self.viewer.window._dock_widgets]:
            self.viewer.window.add_dock_widget(self, area='left', name=translations[self.language]["histogramWidget"]["histogram"])
        self.show()  # 显示窗口
        self.canvas.show()  # 显示画布  {{ edit_1 }}

    def hide_widget(self):  # 新增方法
        """隐藏 HistogramWidget 窗口"""
        # print("hide_widget")
        self.hide()  # 隐藏窗口
        self.canvas.hide()  # 隐藏画布  {{ edit_2 }}

    def update_histogram(self):
        """Update histogram with optimized drawing in a separate thread to avoid UI freeze."""

        with self.update_lock:  # 使用锁来确保只有一个线程可以执行以下代码
            imgdata_np = self.img_buffer.get()
            if imgdata_np is None:
                return
            
            if translations[self.language]["histogramWidget"]["histogram"] not in [name for name in self.viewer.window._dock_widgets]:
                # 如果不在，则重新添加到 viewer 的 dock widget
                self.viewer.window.add_dock_widget(self, area='left', name=translations[self.language]["histogramWidget"]["histogram"])

            # 清除当前直方图线和图例
            if self.histogram is not None:
                if isinstance(self.histogram, list):  # 如果是列表，移除所有线
                    for line in self.histogram:
                        if line.figure is not None:  # 检查线条是否仍在图中
                            line.remove()
                else:
                    if self.histogram.figure is not None:  # 检查线条是否仍在图中
                        self.histogram.remove()
            if self.ax.get_legend():
                self.ax.get_legend().remove()  # 移除现有的图例

            max_value = 0

            # 使用NumPy的向量化操作计算直方图
            mask = imgdata_np > 0
            if imgdata_np.dtype == np.uint16:
                bins_range = (1, 65535)
                bins_number = 65535
            else:
                bins_range = (1, 255)
                bins_number = 256

            if imgdata_np.ndim == 2:  # 灰度图像
                histogram, bins = np.histogram(imgdata_np[mask].flatten(), bins=bins_number, range=bins_range)
                smoothed_histogram = gaussian_filter(histogram, sigma=2)  # 使用高斯滤波平滑数据
                valid_indices = smoothed_histogram > 0  # 获取非零值的索引
                self.histogram, = self.ax.plot(bins[:-1][valid_indices], smoothed_histogram[valid_indices], color='black', label="Gray Level Distribution")
                smoothed_histogram_max = smoothed_histogram[int(len(smoothed_histogram)*0.05):int(len(smoothed_histogram)*0.95)].max()
                if smoothed_histogram_max > max_value:
                    max_value = smoothed_histogram_max

            else:  # 彩色图像
                colors = ('r', 'g', 'b')
                self.histogram = []
                for i, color in enumerate(colors):
                    channel_histogram, bins = np.histogram(imgdata_np[:, :, i][mask[:, :, i]].flatten(), bins=bins_number, range=bins_range)
                    smoothed_histogram = gaussian_filter(channel_histogram, sigma=2)  # 使用高斯滤波平滑数据
                    valid_indices = smoothed_histogram > 0  # 获取非零值的索引
                    line, = self.ax.plot(bins[:-1][valid_indices], smoothed_histogram[valid_indices], color=color, label=f'{color.upper()} Channel')
                    self.histogram.append(line)
                    smoothed_histogram_max = smoothed_histogram[int(len(smoothed_histogram)*0.05):int(len(smoothed_histogram)*0.95)].max()
                    if smoothed_histogram_max > max_value:
                        max_value = smoothed_histogram_max
            self.ax.set_xlim(bins_range)
            self.ax.set_ylim(0, int(max_value))

            # 添加图例，仅当不存在时
            if not self.ax.get_legend():
                self.ax.legend()

            self.canvas.draw_idle()

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

        # 添加图例，仅当不存在时
        if not self.ax.get_legend():
            self.ax.legend()
            
        # 更新画布
        self.canvas.draw_idle()  