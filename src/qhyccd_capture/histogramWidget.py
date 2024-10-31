from PyQt5.QtWidgets import QWidget, QVBoxLayout
import numpy as np
import pyqtgraph as pg
from napari import Viewer
from .language import translations
import threading
import time
import cv2  # 确保导入cv2

class HistogramWidget(QWidget):
    def __init__(self, viewer: Viewer, img_buffer, language: str):
        super().__init__()
        self.viewer = viewer
        self.img_buffer = img_buffer
        self.language = language
        
        self.setWindowTitle(translations[self.language]["histogramWidget"]["histogram"])
        self.layout = QVBoxLayout(self)
        self.plotWidget = pg.PlotWidget()
        self.plotWidget.getViewBox().setLimits(xMin=0, yMin=0)
        self.layout.addWidget(self.plotWidget)
        self.setMinimumSize(400, 300)
        
        # 设置画布背景为灰黑色
        self.plotWidget.setBackground('k')  # 'k' stands for black in matplotlib, similar usage here
        
        self.viewer.window.add_dock_widget(self, area='left', name=translations[self.language]["histogramWidget"]["histogram"])
        
        self.update_lock = threading.Lock()
        self.histogram = None
        self.min_line = None
        self.max_line = None
        self.is_updating_histogram = False
        self.histogram_update_lock = threading.Lock()

        self.hide()  # Initialize hidden window

    def show_widget(self):
        """显示 HistogramWidget 窗口"""
        if translations[self.language]["histogramWidget"]["histogram"] not in [name for name in self.viewer.window._dock_widgets]:
            self.viewer.window.add_dock_widget(self, area='left', name=translations[self.language]["histogramWidget"]["histogram"])
        self.show()

    def hide_widget(self):
        """隐藏 HistogramWidget 窗口"""
        self.hide()

    def update_histogram(self):
        """Update histogram with optimized drawing in a separate thread to avoid UI freeze."""
        if not self.try_enter_update():
            # 如果正在更新中，则从缓冲区获取并丢弃一个数据，以避免缓冲区过满
            skipped_data = self.img_buffer.get()  # 获取并丢弃数据
            print(f"直方图更新正在进行中，跳过这次更新，丢弃数据: {skipped_data.shape if skipped_data is not None else '无数据'}")
            return

        try:
            imgdata_np = self.img_buffer.get()
            if imgdata_np is None:
                return
            print(f"进行一次直方图更新: {imgdata_np.shape}")
            # 清除当前的直方图曲线，保留其他图形元素
            self.clear_histogram_plots()
            
            if imgdata_np.dtype == np.uint16:
                bins_range = (0, 65535)  # 16位图像的范围
                bins_number = 65536       # 包括一个额外的点
                self.plotWidget.getViewBox().setLimits(xMax=65536)
            else:
                bins_range = (0, 255)    # 8位图像的范围
                bins_number = 256         # 包括一个额外的点
                self.plotWidget.getViewBox().setLimits(xMax=256)
            if imgdata_np.ndim == 2:  # 灰度图像
                self.plot_single_channel_histogram(imgdata_np, bins_number, bins_range, 'w')
            elif imgdata_np.ndim == 3:  # 彩色图像
                colors = ['r', 'g', 'b']
                for i, color in enumerate(colors):
                    self.plot_single_channel_histogram(imgdata_np[:, :, i], bins_number, bins_range, color)
        finally:
            self.leave_update()

    def try_enter_update(self):
        """尝试进入更新状态，如果已经在更新中则返回 False。"""
        with self.histogram_update_lock:
            if self.is_updating_histogram:
                return False
            self.is_updating_histogram = True
            return True

    def leave_update(self):
        """离开更新状态，允许其他线程进入更新。"""
        with self.histogram_update_lock:
            self.is_updating_histogram = False

    def clear_histogram_plots(self):
        """清除图表中的直方图曲线，保留其他图形元素如线条。"""
        for item in self.plotWidget.listDataItems():
            if isinstance(item, pg.PlotDataItem):
                self.plotWidget.removeItem(item)

    def plot_single_channel_histogram(self, data, bins_number, bins_range, color):
        """使用 OpenCV 计算并绘制单通道直方图。"""
        # 计算直方图
        hist = cv2.calcHist([data], [0], None, [bins_number], bins_range)
        hist = hist.flatten()  # 将直方图数据扁平化
        
        # 计算每个bin的中心位置，用于折线图的x坐标
        bin_edges = np.linspace(bins_range[0], bins_range[1], bins_number + 1)
        bin_centers = 0.5 * (bin_edges[:-1] + bin_edges[1:])
        
        # 绘制折线图
        self.plotWidget.plot(bin_centers, hist, pen=pg.mkPen(color, width=2))

    def update_min_max_lines(self, min_value, max_value):
        """Update min and max lines."""
        if self.min_line:
            self.plotWidget.removeItem(self.min_line)
        if self.max_line:
            self.plotWidget.removeItem(self.max_line)

        self.min_line = pg.InfiniteLine(pos=min_value, angle=90, pen=pg.mkPen('w', width=2))
        self.max_line = pg.InfiniteLine(pos=max_value, angle=90, pen=pg.mkPen('w', width=2))

        self.plotWidget.addItem(self.min_line, ignoreBounds=True)
        self.plotWidget.addItem(self.max_line, ignoreBounds=True)