import cv2
import os
from concurrent.futures import ThreadPoolExecutor
from PyQt5.QtCore import QThread, pyqtSignal
from datetime import datetime
from astropy.io import fits
import numpy as np
from .language import translations

class SaveThread(QThread):
    finished = pyqtSignal()  # 定义一个信号

    def __init__(self, buffer_queue, file_path, file_name, file_format, save_mode, fps,language,jpeg_quality = 100,tiff_compression = 0,fits_header = None,num_threads=4):
        super().__init__()
        self.language = language
        self.jpeg_quality = jpeg_quality
        self.tiff_compression = tiff_compression
        self.buffer_queue = buffer_queue
        self.file_path = file_path
        self.file_format = file_format
        self.fits_header = fits_header
        if 'now-time' in file_name:
            current_time = datetime.now().strftime('%Y%m%d_%H%M%S')  # 获取当前时间字符串
            file_name = file_name.replace('now-time', current_time)  # 替换 'now-time' 为当前时间
        self.file_name = file_name
        self.save_mode = save_mode
        self.fps = fps  # 帧率
        self.frame_count = 1  # 帧计数器
        self.num_threads = num_threads  # 保存线程数量

    def run(self):
        if self.save_mode == translations[self.language]["qhyccd_capture"]["single_frame_storage"]:
            # 创建文件夹
            folder_path = os.path.join(self.file_path, self.file_name)
            os.makedirs(folder_path, exist_ok=True)

            with ThreadPoolExecutor(max_workers=self.num_threads) as executor:
                while True:
                    imgdata_np = self.buffer_queue.get()
                    if imgdata_np is None:  # 结束信号
                        break
                    if isinstance(imgdata_np, str) and imgdata_np == "end":  # 检查结束信号
                        # print("接收到结束信号，停止单帧存储。")
                        self.buffer_queue.task_done()  # 确保任务标记完成
                        break
                    
                    # 提交保存任务到线程池，传递当前帧计数
                    full_path = f"{folder_path}/{self.frame_count}.{self.file_format}"  # 生成文件名
                    executor.submit(self.save_image, imgdata_np, full_path,self.file_format)
                    self.frame_count += 1
                    self.buffer_queue.task_done()

        elif self.save_mode == translations[self.language]["qhyccd_capture"]["video_storage"]:
            # 视频保存设置
            fourcc = cv2.VideoWriter_fourcc(*'XVID')  # 默认使用 XVID 编码
            if self.file_format.lower() == 'mp4':
                fourcc = cv2.VideoWriter_fourcc(*'mp4v')  # MP4 编码
            elif self.file_format.lower() == 'mkv':
                fourcc = cv2.VideoWriter_fourcc(*'XVID')  # MKV 编码（使用 XVID）
            video_path = os.path.join(self.file_path, f"{self.file_name}.{self.file_format}")  # 使用 .avi 格式以提高兼容性
            first_frame = self.buffer_queue.get()  # 获取第一帧
            if first_frame is None:  # 检查第一帧是否有效
                # print("未获取到有效的第一帧，停止录像。")
                return
            if isinstance(first_frame, str) and first_frame == "end":  # 检查结束信号
                # print("接收到结束信号，停止视频存储。")
                self.buffer_queue.task_done()  # 确保任务标记完成
                return

            # 检查第一帧通道数并转换为三通道
            if first_frame.ndim == 2:  # 单通道灰度图
                first_frame = cv2.cvtColor(first_frame, cv2.COLOR_GRAY2BGR)  # 转换为三通道
            elif first_frame.ndim == 3:  # 检查是否为三通道彩色图像
                first_frame = cv2.cvtColor(first_frame, cv2.COLOR_RGB2BGR)  # 将RGB转换为BGR

            height, width = first_frame.shape[:2]  # 获取帧的尺寸
            video_writer = cv2.VideoWriter(video_path, fourcc, self.fps, (width, height))  # 使用传入的 fps

            # 直接写入第一帧
            video_writer.write(first_frame)

            while True:
                imgdata_np = self.buffer_queue.get()
                if imgdata_np is None:  # 结束信号
                    break
                if isinstance(imgdata_np, str) and imgdata_np == "end":  # 检查结束信号
                    # print("接收到结束信号，停止视频存储。")
                    self.buffer_queue.task_done()  # 确保任务标记完成
                    break
                
                # 检查图像通道数并转换为三通道
                if imgdata_np.ndim == 2:  # 单通道灰度图
                    imgdata_np = cv2.cvtColor(imgdata_np, cv2.COLOR_GRAY2BGR)  # 转换为三通道
                elif imgdata_np.ndim == 3:  # 检查是否为三通道彩色图像
                    imgdata_np = cv2.cvtColor(imgdata_np, cv2.COLOR_RGB2BGR)  # 将RGB转换为BGR

                # 写入视频帧
                video_writer.write(imgdata_np)
                self.buffer_queue.task_done()

            video_writer.release()  # 释放视频写入对象
            # print(f"视频已保存到: {video_path}")

        # 结束时发出信号
        self.finished.emit()  # 发出信号

    def save_image(self, imgdata_np, file_path, file_format='png'):
        """保存图像的方法"""
        try:
            if imgdata_np.ndim == 3:  # 检查是否为三通道彩色图像
                imgdata_np = cv2.cvtColor(imgdata_np, cv2.COLOR_RGB2BGR)  # 将RGB转换为BGR
            if file_format.lower() == 'fits':
                # 创建FITS HDU对象
                hdu = fits.PrimaryHDU(imgdata_np)
                # 假设 self.fits_header 是一个字典，包含要添加到FITS头的键值对
                if self.fits_header is not None:
                    for key, header_item in self.fits_header.items():
                        if key == 'SIMPLE':
                            continue
                        # 尝试将值转换为数字，如果是数字的话
                        value = self.convert_to_number(header_item['value'])
                        hdu.header[key] = value
                        if 'description' in header_item and self.language == "en":
                            hdu.header.comments[key] = header_item['description']
                # 写入文件
                try:
                    hdu.writeto(file_path, overwrite=True)
                except Exception as e:
                    print(f"{translations[self.language]['qhyccd_capture']['debug']['save_image_failed']}: {e}")
            else:
                # 保存为常见格式（PNG, JPEG, TIFF）
                if file_format.lower() == 'png':
                    cv2.imwrite(file_path, imgdata_np)
                elif file_format.lower() == 'jpeg' or file_format.lower() == 'jpg':
                    cv2.imwrite(file_path, imgdata_np, [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality])
                elif file_format.lower() == 'tiff':

                    cv2.imwrite(file_path, imgdata_np, [int(cv2.IMWRITE_TIFF_COMPRESSION), self.tiff_compression])
                else:
                    return
        except Exception as e:
            print(f"{translations[self.language]['qhyccd_capture']['debug']['save_image_failed']}: {e}")

    def convert_to_number(self, value):
        """尝试将字符串转换为整数或浮点数"""
        try:
            # 尝试转换为整数
            return int(value)
        except ValueError:
            # 如果不是整数，尝试转换为浮点数
            try:
                return float(value)
            except ValueError:
                # 如果也不是浮点数，返回原字符串
                return value