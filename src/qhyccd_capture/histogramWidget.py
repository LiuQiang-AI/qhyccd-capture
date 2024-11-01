from PyQt5.QtWidgets import QWidget, QVBoxLayout
from PyQt5.QtCore import QTimer  # 导入QTimer
import numpy as np
import pyqtgraph as pg
from napari import Viewer
from .language import translations
import threading
import time
import cv2

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
        
        self.plotWidget.setBackground('k')  # 设置画布背景为灰黑色
        
        self.viewer.window.add_dock_widget(self, area='left', name=translations[self.language]["histogramWidget"]["histogram"])
        
        self.histogram = None
        self.min_line = None
        self.max_line = None

        self.hide()  # Initialize hidden window

        # 设置定时器
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_histogram)
        self.timer.start(50)  # 设置定时器每1000毫秒（1秒）触发一次

    def show_widget(self):
        """显示 HistogramWidget 窗口"""
        if translations[self.language]["histogramWidget"]["histogram"] not in [name for name in self.viewer.window._dock_widgets]:
            self.viewer.window.add_dock_widget(self, area='left', name=translations[self.language]["histogramWidget"]["histogram"])
        self.show()

    def hide_widget(self):
        """隐藏 HistogramWidget 窗口"""
        self.hide()

    def update_histogram(self):
        if self.img_buffer.qsize() > 0:  # 假设img_buffer有一个is_empty()方法来检查缓冲区是否为空
            try:
                imgdata_np = self.img_buffer.get()
                if imgdata_np is None:
                    return
                print(f"进行一次直方图更新: {imgdata_np.shape}")
                self.clear_histogram_plots()
                
                bins_range = (0, 65535) if imgdata_np.dtype == np.uint16 else (0, 255)
                bins_number = 65536 if imgdata_np.dtype == np.uint16 else 256
                self.plotWidget.getViewBox().setLimits(xMax=bins_range[1] + 1)
                
                if imgdata_np.ndim == 2:
                    self.plot_single_channel_histogram(imgdata_np, bins_number, bins_range, 'w')
                elif imgdata_np.ndim == 3:
                    colors = ['r', 'g', 'b']
                    for i, color in enumerate(colors):
                        self.plot_single_channel_histogram(imgdata_np[:, :, i], bins_number, bins_range, color)
            except Exception as e:
                print(f"直方图更新失败: {e}")

    def clear_histogram_plots(self):
        for item in self.plotWidget.listDataItems():
            if isinstance(item, pg.PlotDataItem):
                self.plotWidget.removeItem(item)

    def plot_single_channel_histogram(self, data, bins_number, bins_range, color):
        hist = cv2.calcHist([data], [0], None, [bins_number], bins_range)
        hist = hist.flatten()
        bin_edges = np.linspace(bins_range[0], bins_range[1], bins_number + 1)
        bin_centers = 0.5 * (bin_edges[:-1] + bin_edges[1:])
        self.plotWidget.plot(bin_centers, hist, pen=pg.mkPen(color, width=2))

    def update_min_max_lines(self, min_value, max_value):
        if self.min_line:
            self.plotWidget.removeItem(self.min_line)
        if self.max_line:
            self.plotWidget.removeItem(self.max_line)
        self.min_line = pg.InfiniteLine(pos=min_value, angle=90, pen=pg.mkPen('w', width=2))
        self.max_line = pg.InfiniteLine(pos=max_value, angle=90, pen=pg.mkPen('w', width=2))
        self.plotWidget.addItem(self.min_line, ignoreBounds=True)
        self.plotWidget.addItem(self.max_line, ignoreBounds=True)
        
    def stop_timer(self):
        self.timer.stop()
        self.img_buffer.clear()
        
    def start_timer(self):
        self.img_buffer.clear()
        self.timer.start(50)
