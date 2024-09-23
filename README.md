# qhyccd-sdk

[![License BSD-3](https://img.shields.io/pypi/l/qhyccd-sdk.svg?color=green)](https://github.com//qhyccd-sdk/raw/main/LICENSE)
[![PyPI](https://img.shields.io/pypi/v/qhyccd-sdk.svg?color=green)](https://pypi.org/project/qhyccd-sdk)
[![Python Version](https://img.shields.io/pypi/pyversions/qhyccd-sdk.svg?color=green)](https://python.org)
[![tests](https://github.com//qhyccd-sdk/workflows/tests/badge.svg)](https://github.com//qhyccd-sdk/actions)
[![codecov](https://codecov.io/gh//qhyccd-sdk/branch/main/graph/badge.svg)](https://codecov.io/gh//qhyccd-sdk)
[![napari hub](https://img.shields.io/endpoint?url=https://api.napari-hub.org/shields/qhyccd-sdk)](https://napari-hub.org/plugins/qhyccd-sdk)

## 项目简介

`qhyccd-capture` 是一个用于操作 QHYCCD 系列相机的基本操作库。该库提供了与 QHYCCD 相机进行交互的功能，包括相机连接、参数设置、图像捕获和显示等。该项目是一个 [napari] 插件，旨在通过图形用户界面简化相机的使用。

## 功能

- **相机连接**：支持在不同操作系统（如 Windows、Linux、macOS）上加载相应的 QHYCCD 动态链接库，并初始化相机资源。
- **参数设置**：提供了设置相机参数的功能，如曝光时间、增益、偏移量、USB 带宽等。
- **图像捕获**：支持单帧模式曝光，并获取图像数据。
- **图像显示**：通过 napari 显示捕获的图像，支持分布式显示、单一显示和序列显示模式。
- **直方图和白平衡**：提供直方图均衡化和白平衡调整功能。
- **ROI（感兴趣区域）**：支持创建和应用 ROI，以便对特定区域进行操作。

## 安装

你可以通过 [pip] 安装 `qhyccd-capture`：

    conda create -n qhyccd-capture python=3.10
    git clone https://github.com/nightliar-L/qhyccd-capture.git
    cd qhyccd-capture
    pip install -r requirements.txt
    pip install -e .

## 使用

    conda activate qhyccd-capture
    napari

## Contributing

Contributions are very welcome. Tests can be run with [tox], please ensure
the coverage at least stays the same before you submit a pull request.

## License

Distributed under the terms of the [BSD-3] license,
"qhyccd-sdk" is free and open source software

## Issues

If you encounter any problems, please [file an issue] along with a detailed description.

[napari]: https://github.com/napari/napari
[copier]: https://copier.readthedocs.io/en/stable/
[@napari]: https://github.com/napari
[MIT]: http://opensource.org/licenses/MIT
[BSD-3]: http://opensource.org/licenses/BSD-3-Clause
[GNU GPL v3.0]: http://www.gnu.org/licenses/gpl-3.0.txt
[GNU LGPL v3.0]: http://www.gnu.org/licenses/lgpl-3.0.txt
[Apache Software License 2.0]: http://www.apache.org/licenses/LICENSE-2.0
[Mozilla Public License 2.0]: https://www.mozilla.org/media/MPL/2.0/index.txt
[napari-plugin-template]: https://github.com/napari/napari-plugin-template

[napari]: https://github.com/napari/napari
[tox]: https://tox.readthedocs.io/en/latest/
[pip]: https://pypi.org/project/pip/
[PyPI]: https://pypi.org/
