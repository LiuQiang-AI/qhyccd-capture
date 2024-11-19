import os
import json
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QComboBox, QTableWidget, QPushButton, QTableWidgetItem, QTimeEdit, QSpinBox, QDoubleSpinBox, QHeaderView, QInputDialog, QMessageBox
from PyQt5.QtCore import Qt, QTime, QTimer, pyqtSignal
from functools import partial

class PlannedShootingDialog(QDialog):
    plan_running_signal = pyqtSignal(dict)  # 定义信号

    def __init__(self, parent=None):
        super().__init__(parent)
        self.data_dict = {}
        self.current_row = 0
        self.running_row = 0
        
        self.setWindowTitle("Planned Shooting")
        self.setGeometry(100, 100, 800, 600)

        layout = QVBoxLayout(self)
        self.setLayout(layout)

        self.planComboBox = QComboBox()
        self.planComboBox.addItem("None")  # 默认选项
        layout.addWidget(self.planComboBox)
        self.label_text = ["相机", "读出模式", "间隔时长", "曝光时长", "增益", "偏置", "位数", "滤镜", "状态"]
        self.table = QTableWidget()
        self.table.setColumnCount(len(self.label_text))
        self.table.setHorizontalHeaderLabels(self.label_text)
        layout.addWidget(self.table)

        self.table.resizeColumnsToContents()
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch) # type: ignore

        tableControlLayout = QHBoxLayout()
        self.addButton = QPushButton("添加行")
        self.removeButton = QPushButton("删除行")
        tableControlLayout.addWidget(self.addButton)
        tableControlLayout.addWidget(self.removeButton)
        layout.addLayout(tableControlLayout)

        buttonsLayout = QHBoxLayout()
        self.startButton = QPushButton("开始计划")
        self.cancelButton = QPushButton("取消计划")
        self.saveButton = QPushButton("保存计划表")
        self.deleteButton = QPushButton("删除计划表")
        buttonsLayout.addWidget(self.startButton)
        buttonsLayout.addWidget(self.cancelButton)
        buttonsLayout.addWidget(self.saveButton)
        buttonsLayout.addWidget(self.deleteButton)
        layout.addLayout(buttonsLayout)

        self.initUI()

        self.startButton.clicked.connect(self.startPlan)

        self.addButton.clicked.connect(self.addRow)
        self.removeButton.clicked.connect(self.removeRow)
        self.saveButton.clicked.connect(self.savePlan)
        self.deleteButton.clicked.connect(self.deletePlan)
        self.planComboBox.currentIndexChanged.connect(self.loadPlan)

        self.timer = QTimer(self)  # 创建定时器
        self.timer.timeout.connect(self.updateCountdown)  # 连接定时器的超时信号

        self.cancelButton.clicked.connect(self.cancelPlan)

    def initUI(self):
        self.loadPlans()

    def savePlan(self):
        plan_name, ok = QInputDialog.getText(self, "保存计划", "输入计划名称:")
        if ok and plan_name:
            plan_data = self.collectPlanData()
            
            for camera in plan_data[-1].values():
                if 'ids' in camera:
                    camera['ids'] = ''
            all_plans = self.loadAllPlans()
            all_plans[plan_name] = plan_data
            with open("plans.json", "w", encoding='utf-8') as file:
                json.dump(all_plans, file, ensure_ascii=False, indent=4)
            QMessageBox.information(self, "保存成功", "计划已成功保存！")
            
            # 自动调整选择的计划表为保存的计划表
            if self.planComboBox.findText(plan_name) == -1:
                self.planComboBox.addItem(plan_name)
            self.planComboBox.setCurrentText(plan_name)  # 设置当前选择为保存的计划表

    def deletePlan(self):
        plan_name = self.planComboBox.currentText()  # 获取当前选择的计划表
        if plan_name and plan_name != "None":  # 确保选中的计划表不是 None
            # 弹出确认对话框
            reply = QMessageBox.question(self, "确认删除", f"您确定要删除计划 '{plan_name}' 吗？", 
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                all_plans = self.loadAllPlans()
                if plan_name in all_plans:
                    del all_plans[plan_name]
                    with open("plans.json", "w") as file:
                        json.dump(all_plans, file)
                    QMessageBox.information(self, "删除成功", "计划已成功删除！")
                    self.planComboBox.removeItem(self.planComboBox.findText(plan_name))

    def loadPlan(self):
        plan_name = self.planComboBox.currentText()
        if plan_name != "None":
            all_plans = self.loadAllPlans()
            if plan_name in all_plans:
                self.applyPlanData(all_plans[plan_name])
        else:
            self.table.setRowCount(0)  

    def collectPlanData(self):
        plan_data = []
        camera_names = []
        for row in range(self.table.rowCount()):
            # 获取滤镜选项
            filter_selector = self.table.cellWidget(row, 7)
            if self.table.cellWidget(row, 0).currentText() not in camera_names:
                camera_names.append(self.table.cellWidget(row, 0).currentText())
            row_data = {
                "name": self.table.cellWidget(row, 0).currentText(),
                "readout_mode": self.table.cellWidget(row, 1).currentText(),
                "interval": self.table.cellWidget(row, 2).time().toString("HH:mm:ss"),
                "exposure": self.table.cellWidget(row, 3).value(),
                "gain": self.table.cellWidget(row, 4).value(),
                "offset": self.table.cellWidget(row, 5).value(),
                "depth": self.table.cellWidget(row, 6).currentText(),
                "CFW": filter_selector.currentText(),
            }
            plan_data.append(row_data)
        camera_dict = {}
        for i in self.data_dict.keys():
            if i in camera_names:
                camera_dict[i] = self.data_dict[i]
        plan_data.append(camera_dict)
        return plan_data

    def collectSingleRowData(self, row):
        """获取指定行的数据"""
        row_data = {
            "name": self.table.cellWidget(row, 0).currentText(),
            "readout_mode": self.data_dict[self.table.cellWidget(row, 0).currentText()]['readout_mode'][self.table.cellWidget(row, 1).currentText()],
            "interval": self.table.cellWidget(row, 2).time().toString("HH:mm:ss"),
            "exposure": self.table.cellWidget(row, 3).value(),
            "gain": self.table.cellWidget(row, 4).value(),
            "offset": self.table.cellWidget(row, 5).value(),
            "depth": self.data_dict[self.table.cellWidget(row, 0).currentText()]['depth'][self.table.cellWidget(row, 6).currentText()],
            "CFW": self.data_dict[self.table.cellWidget(row, 0).currentText()]['CFW'][1].get(self.table.cellWidget(row, 7).currentText(), 'None'),
        }
        return row_data

    def applyPlanData(self, plan_data):
        self.table.setRowCount(0)  # 清空表格
        for key in plan_data[-1].keys():
            if key not in self.data_dict.keys():
                self.data_dict[key] = plan_data[-1][key]
                self.data_dict[key]['connection'] = False
        for row_data in plan_data[:-1]:
            row_count = self.table.rowCount()
            self.table.insertRow(row_count)
            # 设置相机选择
            camera_selector = QComboBox()
            camera_selector.addItems(list(self.data_dict.keys()))
            camera_selector.setCurrentText(row_data.get("name", ""))
            # 设置样式表
            if self.data_dict[camera_selector.currentText()]['connection'] == False:
                camera_selector.setStyleSheet("QComboBox { background-color: rgb(255, 255, 224); color: rgb(0, 0, 0); }")
            else:
                camera_selector.setStyleSheet("")
            
            camera_selector.currentIndexChanged.connect(partial(self.updateRowOptions, row_count))
            
            self.table.setCellWidget(row_count, 0, camera_selector)
            
            # 设置读出模式
            readout_mode_selector = QComboBox()
            readout_mode_selector.addItems(list(self.data_dict[camera_selector.currentText()]['readout_mode'].keys()))
            readout_mode_selector.setCurrentText(row_data.get("readout_mode", "None"))
            self.table.setCellWidget(row_count, 1, readout_mode_selector)
            
            # 设置拍摄时间
            time_edit = QTimeEdit()
            time_edit.setDisplayFormat("HH:mm:ss")
            time_edit.setTime(QTime.fromString(row_data.get("interval", "00:00:00"), "HH:mm:ss"))
            self.table.setCellWidget(row_count, 2, time_edit)

            # 设置曝光时长
            exposure_time = QDoubleSpinBox()
            exposure_time.setDecimals(0)
            exposure_time.setRange(self.data_dict[row_data.get('name')]['exposure'][0], self.data_dict[row_data.get('name')]['exposure'][1])  # 假设范围
            exposure_time.setSingleStep(self.data_dict[row_data.get('name')]['exposure'][2])
            exposure_time.setValue(row_data.get("exposure", 0))
            self.table.setCellWidget(row_count, 3, exposure_time)

            # 设置增益
            gain_input = QSpinBox()
            gain_input.setRange(self.data_dict[row_data.get('name')]['gain'][0], self.data_dict[row_data.get('name')]['gain'][1])  # 假设范围
            gain_input.setSingleStep(self.data_dict[row_data.get('name')]['gain'][2])
            gain_input.setValue(row_data.get("gain", 0))
            self.table.setCellWidget(row_count, 4, gain_input)

            # 设置偏置
            bias_input = QSpinBox()
            bias_input.setRange(self.data_dict[row_data.get('name')]['offset'][0], self.data_dict[row_data.get('name')]['offset'][1])  # 假设范围
            bias_input.setSingleStep(self.data_dict[row_data.get('name')]['offset'][2])
            bias_input.setValue(row_data.get("offset", 0))
            self.table.setCellWidget(row_count, 5, bias_input)

            # 设置位数
            depth_input = QComboBox()
            depth_input.addItems(list(self.data_dict[row_data.get('name')]['depth'].keys()))
            depth_input.setCurrentText(row_data.get("depth", "bit8"))
            self.table.setCellWidget(row_count, 6, depth_input)

            # 设置滤镜
            filter_selector = QComboBox()
            if self.data_dict[row_data.get('name')]['CFW'][0]:
                filter_selector.addItems(list(self.data_dict[row_data.get('name')]['CFW'][1].keys()))
            else:
                filter_selector.addItem("None")
            filter_selector.setCurrentText(row_data.get("CFW", "None"))
            self.table.setCellWidget(row_count, 7, filter_selector)

            # 设置状态
            status_display = QTableWidgetItem('')
            status_display.setFlags(Qt.ItemIsEnabled) 
            self.table.setItem(row_count, 8, status_display)

    def getPlanNames(self):
        # Retrieve a list of saved plan names for deletion
        all_plans = self.loadAllPlans()
        return list(all_plans.keys())

    def addRow(self):
        row_count = self.table.rowCount()
        self.table.insertRow(row_count)
        self.setRowWidgets(row_count)

    def removeRow(self):
        row_count = self.table.rowCount()
        if row_count > 0:
            self.table.removeRow(row_count - 1)

    def setRowWidgets(self, row):
        camera_selector = QComboBox()
        camera_selector.addItems(list(self.data_dict.keys()))
        camera_selector.currentIndexChanged.connect(lambda: self.updateRowOptions(row))
        self.table.setCellWidget(row, 0, camera_selector)

        camera_name = camera_selector.currentText() if camera_selector else None
        
        camera_info = self.data_dict[camera_name]

        readout_mode_selector = QComboBox()
        readout_mode_selector.addItems(list(camera_info['readout_mode'].keys()))
        self.table.setCellWidget(row, 1, readout_mode_selector)

        time_edit = QTimeEdit()
        time_edit.setDisplayFormat("HH:mm:ss")
        self.table.setCellWidget(row, 2, time_edit)

        exposure_params = camera_info.get('exposure')  # 曝光时间参数
        exposure_time = QDoubleSpinBox()
        exposure_time.setDecimals(0)
        exposure_time.setRange(exposure_params[0], exposure_params[1])
        exposure_time.setSingleStep(exposure_params[2])
        exposure_time.setValue(exposure_params[3])
        self.table.setCellWidget(row, 3, exposure_time)

        gain_params = camera_info.get('gain')  # 增益参数
        gain_input = QSpinBox()
        gain_input.setRange(gain_params[0], gain_params[1])
        gain_input.setSingleStep(gain_params[2])
        gain_input.setValue(gain_params[3])
        self.table.setCellWidget(row, 4, gain_input)

        bias_input = QSpinBox()
        bias_params = camera_info.get('offset')  # 偏移参数
        bias_input.setRange(bias_params[0], bias_params[1])
        bias_input.setSingleStep(bias_params[2])
        bias_input.setValue(bias_params[3])
        self.table.setCellWidget(row, 5, bias_input)
        
        depth_input = QComboBox()
        depth_params = camera_info.get('depth')  # 位数参数
        depth_input.addItems(list(depth_params.keys()))
        self.table.setCellWidget(row, 6, depth_input)

        filter_selector = QComboBox()
        if camera_info.get('CFW')[0]:  # 检查是否连接了滤镜轮
            filter_selector.addItems(list(camera_info.get('CFW')[1].keys()))  # 添加滤镜轮名称
        else:
            filter_selector.addItem("None")
        self.table.setCellWidget(row, 7, filter_selector)

        status_display = QTableWidgetItem("")
        status_display.setFlags(Qt.ItemIsEnabled) # type: ignore
        self.table.setItem(row, 8, status_display)
    
    def updateTableOptions(self, data_dict):
        self.data_dict = data_dict

    def loadPlans(self):
        all_plans = self.loadAllPlans()
        for plan_name in all_plans.keys():
            if self.planComboBox.findText(plan_name) == -1:
                self.planComboBox.addItem(plan_name)

    def loadAllPlans(self):
        try:
            with open("plans.json", "r") as file:
                return json.load(file)
        except FileNotFoundError:
            return {}

    def updateRowOptions(self, row):
        camera_name = self.table.cellWidget(row, 0).currentText()  # 获取当前选择的相机名称
        connection = self.data_dict.get(camera_name, {}).get('connection', False)
        if connection == False:
            self.table.cellWidget(row, 0).setStyleSheet("QComboBox { background-color: rgb(255, 255, 224); color: rgb(0, 0, 0); }")
        else:
            self.table.cellWidget(row, 0).setStyleSheet("")
        camera_info = self.data_dict.get(camera_name, {})
        
        # 更新曝光时间、增益、偏置和滤镜的值
        if camera_info:
            readout_mode_selector = self.table.cellWidget(row, 1)
            readout_mode_selector.clear()
            readout_mode_selector.addItems(list(camera_info.get('readout_mode', {}).keys()))

            exposure_params = camera_info.get('exposure', [0, 100, 1, 0])  # 默认值
            exposure_time = self.table.cellWidget(row, 3)
            exposure_time.setRange(exposure_params[0], exposure_params[1])  # 使用原始曝光参数
            exposure_time.setSingleStep(exposure_params[2])  # 设置步长
            exposure_time.setValue(exposure_params[3])  # 设置当前值

            gain_params = camera_info.get('gain', [0, 480, 1, 30])  # 默认值
            gain_input = self.table.cellWidget(row, 4)
            gain_input.setRange(gain_params[0], gain_params[1])
            gain_input.setSingleStep(gain_params[2])
            gain_input.setValue(gain_params[3])

            bias_params = camera_info.get('offset', [0, 255, 1, 0])  # 默认值
            bias_input = self.table.cellWidget(row, 5)
            bias_input.setRange(bias_params[0], bias_params[1])
            bias_input.setSingleStep(bias_params[2])
            bias_input.setValue(bias_params[3])

            depth_params = camera_info.get('depth', {'bit8':8,'bit16':16})  # 默认值
            depth_input = self.table.cellWidget(row, 6)
            depth_input.clear()
            depth_input.addItems(list(depth_params.keys()))

            filter_selector = self.table.cellWidget(row, 7)
            filter_selector.clear()
            if camera_info.get('CFW')[0]:  # 检查是否连接了滤镜轮
                filter_selector.addItems(list(camera_info.get('CFW')[1].keys()))  # 添加滤镜轮名称
            else:
                filter_selector.addItem("None")

    def clearTable(self):
        self.planComboBox.setCurrentText("None")
        self.table.setRowCount(0)
        
    def startPlan(self):
        reply = QMessageBox.question(self, "确认执行", "您确定要开始计划吗？", 
                                 QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            if self.current_row != 0 or self.running_row != 0 and self.current_row < self.table.rowCount()-1:
                continue_reply = QMessageBox.question(self, "继续执行", "当前有计划执行中断，您要继续吗？", 
                                                  QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if continue_reply == QMessageBox.No:
                    self.current_row = 0  # 重置当前行
                    for i in range(self.table.rowCount()):
                        self.table.item(i, 8).setText('')
                else:
                    self.current_row = self.running_row  # 设置当前行为正在执行的行
                    for i in range(self.current_row, self.table.rowCount()):
                        self.table.item(i, 8).setText('')
            print(f"开始执行当前行: {self.current_row}")
            self.executeRow(self.current_row)  # 开始执行当前行

    def executeRow(self, row):
        if row < self.table.rowCount():
            time = self.table.cellWidget(row, 2).time()  # 获取当前行的时间
            countdown_seconds = time.hour() * 3600 + time.minute() * 60 + time.second()
            
            # 检查第六列的单元格是否存在
            status_item = self.table.item(row, 8)  # 获取状态单元格
            if status_item is None:  # 如果状态单元格不存在，创建一个新的 QTableWidgetItem
                status_item = QTableWidgetItem('')
                self.table.setItem(row, 8, status_item)

            if status_item.text() == '执行完成':
                self.current_row += 1
                self.executeRow(self.current_row)
            else:
                self.timer.start(1000)  # 每秒更新一次
                self.remaining_time = countdown_seconds  # 设置剩余时间
        else:
            self.timer.stop()
            self.current_row = 0

    def updateCountdown(self):
        if self.remaining_time > 0:
            self.remaining_time -= 1
            # 更新表格中的时间
            self.table.cellWidget(self.current_row, 2).setTime(QTime.fromString(QTime(0, 0).addSecs(self.remaining_time).toString("HH:mm:ss"), "HH:mm:ss"))
        else:
            self.timer.stop()  # 停止定时器
            if self.current_row > 0 and self.table.item(self.running_row, 8).text() != '执行完成':
                self.timer.start(1000)  # 如果上一行未完成，重新开始倒计时
                return
            self.table.item(self.current_row, 8).setText('正在执行')
            self.running_row = self.current_row
            self.current_row += 1  # 移动到下一行
            self.plan_running_signal.emit(self.collectSingleRowData(self.running_row))  # 发送信号
            self.executeRow(self.current_row)  # 执行下一行

    def cancelPlan(self):
        self.timer.stop()  # 停止定时器

        
    def update_row_state(self):
        print(f"更新状态为执行完成")
        self.table.item(self.running_row, 8).setText('执行完成')  # 更新状态为执行完成

