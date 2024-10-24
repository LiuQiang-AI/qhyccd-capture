# qhyccd-capture

## 项目简介

`qhyccd-capture` 是一个用于操作 QHYCCD 系列相机的基本操作库。该库提供了与 QHYCCD 相机进行交互的功能，包括相机连接、参数设置、图像捕获和显示等。该项目是一个 [napari] 插件，旨在通过图形用户界面简化相机的使用。

## 功能

- **相机连接**：支持在不同操作系统（如 Windows、Linux、macOS）上加载相应的 QHYCCD 动态链接库，并初始化相机资源。
- **参数设置**：提供了设置相机参数的功能，如曝光时间、增益、偏移量、USB 带宽等。
- **图像捕获**：支持单帧模式曝光，并获取图像数据。
- **图像显示**：通过 napari 显示捕获的图像，支持分布式显示、单一显示和序列显示模式。
- **直方图和白平衡**：提供直方图均衡化和白平衡调整功能。
- **ROI（感兴趣区域）**：支持创建和应用 ROI，以便对特定区域进行操作。
- **视频录制**：支持视频录制，并保存为多种视频格式。
- **温度控制**：支持温度控制，并显示温度。
- **CFW 控制**：支持 CFW 控制，并显示 CFW 状态。
- **星点解析**：支持星点解析，并显示星点解析结果。
  
![qhyccd-capture 插件界面显示](https://raw.githubusercontent.com/LiuQiang-AI/qhyccd-capture/main/src/qhyccd_capture/images/image.png)

## 安装
您可以通过pip安装:

    pip install qhyccd-capture

如果要安装最新的开发版本:

    pip install git+https://github.com/nightliar-L/qhyccd-capture.git

## 依赖安装
#### Astrometry.net 
目前astrometry.net仅支持ubuntu系统

    sudo apt-get install astrometry.net
    sudo apt-get install astrometry-data-tycho2
    sudo vim ~/.bashrc
    # 添加以下内容
    export PATH=$PATH:/usr/local/astrometry/bin

## 版本变化

- 2024-10-23 版本 0.0.1 初始版本
- 2024-10-23 版本 0.0.2 版本 修复了发布带来的部分问题
- 2024-10-24 版本 0.0.3 版本 修改了部分描述和初始配置

## 贡献

欢迎贡献。可以使用 [tox] 运行测试，请确保提交拉取请求前覆盖率至少保持不变。

## 许可证

根据 [BSD-3] 许可证条款分发，
"qhyccd-sdk" 是自由和开源软件

