from PyQt5.QtCore import QThread, pyqtSignal
import subprocess
import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
import tempfile
import os
from PyQt5.QtWidgets import QDialog, QSpinBox, QDoubleSpinBox, QCheckBox, QLabel, QPushButton, QFormLayout, QComboBox, QHBoxLayout, QLineEdit,QMessageBox
from PyQt5.QtCore import Qt

from .language import translations

class AstrometryDialog(QDialog):
    def __init__(self, parent=None, solver=None, language='en'):
        super().__init__(parent)
        self.language = language
        self.solver = solver  # 接收 AstrometrySolver 实例
        self.setup_ui()

    def setup_ui(self):
        self.setWindowTitle(translations[self.language]['astrometry']['title'])
        self.layout = QFormLayout(self)  # 使用 QFormLayout 替换 QVBoxLayout

        self.scale_units_label = QLabel(translations[self.language]['astrometry']['scale_units'])
        self.scale_units_label.setToolTip(translations[self.language]['astrometry']['scale_units_tooltip'])
        self.scale_units_input_type = QComboBox()
        self.scale_units_input_type.addItems(["arcsecperpix", "arcminwidth", "arcminheight", "degwidth", "decheight"])
        self.scale_units_input_low = QDoubleSpinBox()
        self.scale_units_input_low.setRange(0.0000, 1000.0)
        self.scale_units_input_low.setDecimals(4)
        self.scale_units_input_low.setToolTip(translations[self.language]['astrometry']['scale_units_tooltip_low'])
        self.scale_units_input_high = QDoubleSpinBox()
        self.scale_units_input_high.setRange(0.0000, 1000.0)
        self.scale_units_input_high.setDecimals(4)
        self.scale_units_input_high.setToolTip(translations[self.language]['astrometry']['scale_units_tooltip_high'])

        # 使用 QHBoxLayout 来包含多个控件
        scale_units_layout = QHBoxLayout()
        scale_units_layout.addWidget(self.scale_units_input_type)
        scale_units_layout.addWidget(self.scale_units_input_low)
        scale_units_layout.addWidget(self.scale_units_input_high)
        # 将 QHBoxLayout 添加到 QFormLayout
        self.layout.addRow(self.scale_units_label, scale_units_layout)

        self.uniformize_label = QLabel(translations[self.language]['astrometry']['uniformize_label'])
        self.uniformize_input = QSpinBox()
        self.uniformize_input.setRange(0, 100)  # 设置范围为0到100
        self.uniformize_input.setSingleStep(1)  # 设置步长
        self.uniformize_input.setToolTip(translations[self.language]['astrometry']['uniformize_tooltip'])
        self.layout.addRow(self.uniformize_label, self.uniformize_input)

        self.nsigmalimit_label = QLabel(translations[self.language]['astrometry']['nsigmalimit_label'])
        self.nsigmalimit_input = QSpinBox()
        self.nsigmalimit_input.setRange(0, 100)  # 设置范围为0到100
        self.nsigmalimit_input.setValue(8)
        self.nsigmalimit_input.setSingleStep(1)  # 设置步长
        self.nsigmalimit_input.setToolTip(translations[self.language]['astrometry']['nsigmalimit_tooltip'])
        self.layout.addRow(self.nsigmalimit_label, self.nsigmalimit_input)
        
        self.cpulimit_input = QSpinBox()
        self.cpulimit_input.setRange(0, 10000)
        self.cpulimit_input.setValue(5)
        self.cpulimit_input.setSingleStep(1)
        self.cpulimit_input.setToolTip(translations[self.language]['astrometry']['cpulimit_tooltip'])
        self.layout.addRow(translations[self.language]['astrometry']['cpulimit_label'], self.cpulimit_input)  # 使用 addRow 添加控件

        self.local_angle_checkbox = QLabel(translations[self.language]['astrometry']['local_angle_label'])
        
        self.local_angle_input_ra = QDoubleSpinBox()
        self.local_angle_input_ra.setRange(0, 360)  # 设置范围为0到360
        self.local_angle_input_ra.setDecimals(4)  # 设置小数点后四位
        self.local_angle_input_ra.setSingleStep(0.0001)  # 设置步长
        self.local_angle_input_ra.setToolTip(translations[self.language]['astrometry']['local_angle_tooltip_ra'])

        self.local_angle_input_dec = QDoubleSpinBox()
        self.local_angle_input_dec.setRange(-90, 90)  # 设置范围为-90到90
        self.local_angle_input_dec.setDecimals(4)  # 设置小数点后四位
        self.local_angle_input_dec.setSingleStep(0.0001)  # 设置步长
        self.local_angle_input_dec.setToolTip(translations[self.language]['astrometry']['local_angle_tooltip_dec'])

        self.local_angle_input_radius = QDoubleSpinBox()
        self.local_angle_input_radius.setRange(0, 180)  # 设置范围为0到180
        self.local_angle_input_radius.setDecimals(4)  # 设置小数点后四位
        self.local_angle_input_radius.setSingleStep(0.0001)  # 设置步长
        self.local_angle_input_radius.setToolTip(translations[self.language]['astrometry']['local_angle_tooltip_radius'])

        # 使用 QHBoxLayout 来包含多个控件
        local_angle_layout = QHBoxLayout()
        local_angle_layout.addWidget(self.local_angle_input_ra)
        local_angle_layout.addWidget(self.local_angle_input_dec)
        local_angle_layout.addWidget(self.local_angle_input_radius)

        # 将 QHBoxLayout 添加到 QFormLayout
        self.layout.addRow(self.local_angle_checkbox, local_angle_layout)

        self.overwrite_checkbox = QCheckBox()
        self.overwrite_checkbox.setToolTip(translations[self.language]['astrometry']['overwrite_tooltip'])
        self.overwrite_checkbox.setChecked(True)
        self.layout.addRow(translations[self.language]['astrometry']['overwrite_label'], self.overwrite_checkbox)  # 使用 addRow 添加控件

        self.guess_the_scale_checkbox = QCheckBox()
        self.guess_the_scale_checkbox.setToolTip(translations[self.language]['astrometry']['guess_the_scale_tooltip'])
        self.layout.addRow(translations[self.language]['astrometry']['guess_the_scale_checkbox'], self.guess_the_scale_checkbox)  # 使用 addRow 添加控件

        self.reduce_pixel_size_checkbox = QCheckBox()
        self.reduce_pixel_size_checkbox.setToolTip(translations[self.language]['astrometry']['reduce_pixel_size_tooltip'])
        self.layout.addRow(translations[self.language]['astrometry']['reduce_pixel_size_checkbox'], self.reduce_pixel_size_checkbox)  # 使用 addRow 添加控件
        
        # self.depth
        
        self.timestamp_label = QCheckBox()
        self.timestamp_label.setChecked(True)
        self.timestamp_label.setToolTip(translations[self.language]['astrometry']['timestamp_tooltip'])
        self.layout.addRow(translations[self.language]['astrometry']['timestamp_label'], self.timestamp_label)  # 使用 addRow 添加控件
        
        self.no_remove_lines_checkbox = QCheckBox()
        self.no_remove_lines_checkbox.setChecked(True)
        self.no_remove_lines_checkbox.setToolTip(translations[self.language]['astrometry']['no_remove_lines_tooltip'])
        self.layout.addRow(translations[self.language]['astrometry']['no_remove_lines_label'], self.no_remove_lines_checkbox)  # 使用 addRow 添加控件
        
        self.resort_checkbox = QCheckBox()
        self.resort_checkbox.setToolTip(translations[self.language]['astrometry']['resort_tooltip'])
        self.layout.addRow(translations[self.language]['astrometry']['resort_label'], self.resort_checkbox)  # 使用 addRow 添加控件

        self.no_verify_checkbox = QCheckBox()
        self.no_verify_checkbox.setToolTip(translations[self.language]['astrometry']['no_verify_tooltip'])
        self.layout.addRow(translations[self.language]['astrometry']['no_verify_label'], self.no_verify_checkbox)  # 使用 addRow 添加控件

        self.no_plots_checkbox = QCheckBox()
        self.no_plots_checkbox.setChecked(True)
        self.no_plots_checkbox.setToolTip(translations[self.language]['astrometry']['no_plots_tooltip'])
        self.layout.addRow(translations[self.language]['astrometry']['no_plots_label'], self.no_plots_checkbox)  # 使用 addRow 添加控件
      
        self.save_image_checkbox = QCheckBox()
        self.save_image_checkbox.setToolTip(translations[self.language]['astrometry']['save_image_tooltip'])
        self.save_image_checkbox.stateChanged.connect(self.on_save_image_state_changed)
        self.layout.addRow(translations[self.language]['astrometry']['save_image_label'], self.save_image_checkbox)  # 使用 addRow 添加控件
        
        self.save_image_path_label = QLabel(translations[self.language]['astrometry']['save_image_path_label'])
        self.save_image_path_label.setVisible(False)
        self.save_image_path_input = QLineEdit()
        self.save_image_path_input.setText(os.getcwd())
        self.save_image_path_input.setToolTip(translations[self.language]['astrometry']['save_image_path_tooltip'])
        self.save_image_path_input.setVisible(False)
        self.layout.addRow(self.save_image_path_label, self.save_image_path_input)  # 使用 addRow 添加控件
        
        self.save_image_name_label = QLabel(translations[self.language]['astrometry']['save_image_name_label'])
        self.save_image_name_label.setVisible(False)
        self.save_image_name_input = QLineEdit()
        self.save_image_name_input.setText("astrometry.fits")
        self.save_image_name_input.setToolTip(translations[self.language]['astrometry']['save_image_name_tooltip'])
        self.save_image_name_input.setVisible(False)
        self.layout.addRow(self.save_image_name_label, self.save_image_name_input)  # 使用 addRow 添加控件
      
        self.submit_button = QPushButton(translations[self.language]['astrometry']['submit_button'])
        self.submit_button.clicked.connect(self.on_submit)
        self.layout.addRow(self.submit_button)  # 添加提交按钮

    def on_submit(self):
        # 检查图像保存路径和图像名字是否为空
        if self.save_image_checkbox.isChecked():
            if not self.save_image_path_input.text() or not self.save_image_name_input.text() or self.save_image_path_input.text()=="" or self.save_image_name_input.text()=="" or self.save_image_path_input.text==' ' or self.save_image_name_input.text==' ':
                QMessageBox.warning(self, translations[self.language]['astrometry']['warning'], translations[self.language]['astrometry']['save_image_path_and_name_cannot_be_empty'])
                return  # 如果为空，显示警告并中止提交
        # 获取参数并启动解析过程
        params = self.get_parameters()
        if self.solver and params:
            self.accept()  # 关闭对话框
        else:
            self.reject()  # 关闭对话框，不执行操作

    def on_save_image_state_changed(self, state):
        self.save_image_path_label.setVisible(state==Qt.Checked)
        self.save_image_path_input.setVisible(state==Qt.Checked)
        self.save_image_name_label.setVisible(state==Qt.Checked)
        self.save_image_name_input.setVisible(state==Qt.Checked)

    def get_parameters(self):
        # 收集所有参数并返回一个字典
        return {
            'overwrite': '--overwrite' if self.overwrite_checkbox.isChecked() else '',
            'cpulimit': ['--cpulimit', self.cpulimit_input.value()] if self.cpulimit_input.value()!=0 else '',
            'scale_units': ['--scale-units', self.scale_units_input_type.currentText()] if self.scale_units_input_low.value()!=0 and self.scale_units_input_high.value()!=0 else '',
            'scale_low': ['--scale-low', self.scale_units_input_low.value()] if self.scale_units_input_low.value()!=0 else '',
            'scale_high': ['--scale-high', self.scale_units_input_high.value()] if self.scale_units_input_high.value()!=0 else '',
            'nsigmalimit': ['--nsigma', self.nsigmalimit_input.value()] if self.nsigmalimit_input.value()!=0 else '',
            'guess_scale': '--guess-scale' if self.guess_the_scale_checkbox.isChecked() else '',
            'downsample': '--downsample' if self.reduce_pixel_size_checkbox.isChecked() else '',
            'resort': '--resort' if self.resort_checkbox.isChecked() else '',
            'no_verify': '--no-verify' if self.no_verify_checkbox.isChecked() else '',
            'no_plots': '--no-plots' if self.no_plots_checkbox.isChecked() else '',
            'ra': ['--ra', self.local_angle_input_ra.value()] if self.local_angle_input_ra.value()!=0 else '',
            'dec': ['--dec', self.local_angle_input_dec.value()] if self.local_angle_input_dec.value()!=0 else '',
            'radius': ['--radius', self.local_angle_input_radius.value()] if self.local_angle_input_radius.value()!=0 else '',
            'timestamp': '--timestamp' if self.timestamp_label.isChecked() else '',
            'no_remove_lines': '--no-remove-lines' if self.no_remove_lines_checkbox.isChecked() else '',
            'uniformize': ['--uniformize', self.uniformize_input.value()] ,
            'save_image': [self.save_image_path_input.text(), self.save_image_name_input.text()] if self.save_image_checkbox.isChecked() else '',
        }


class AstrometrySolver(QThread):
    finished = pyqtSignal(str)
    star_info = pyqtSignal(str,WCS,bool)
    error = pyqtSignal(str)

    def __init__(self, language='en'):
        super().__init__()
        self.language = language
        self.temp_file = None
        self.image_data = None
        self.save_image = False
        self.save_image_path = None
        self.save_image_name = None
        

    def set_parameter(self, key, value):
        if value == '' or value is None or value == [] or value == ' ' :
            return
        if key == 'save_image':
            self.save_image = True
            self.save_image_path = value[0]
            self.save_image_name = value[1]
            print(f"save_image_path: {self.save_image_path}")
            print(f"save_image_name: {self.save_image_name}")
            return
        if not hasattr(self, 'params'):
            self.params = {}
        if isinstance(value, list):
            self.params[key] = [str(v) for v in value]
        else:
            self.params[key] = [str(value)]

    def start_solving(self, image_input, params=None):
        try:
            if isinstance(image_input, np.ndarray):
                self.image_data = image_input
            elif isinstance(image_input, str) and os.path.isfile(image_input):
                self.image_data = fits.getdata(image_input)
            else:
                raise ValueError(translations[self.language]['astrometry']['invalid_image_input'])
        except Exception as e:
            self.error.emit(f"{translations[self.language]['astrometry']['failed_to_load_image_data']}: {str(e)}")
            return

        if params:
            for key, value in params.items():
                self.set_parameter(key, value)
        self.start()

    def run(self):
        """ Save the image data to a temporary FITS file in the current directory, then run the solve-field command. """
        try:
            local_dir = os.getcwd()
            local_dir = local_dir
            # Create a temporary file in the current directory to save the FITS data
            with tempfile.NamedTemporaryFile(delete=False, suffix='.fits', dir=local_dir) as temp:
                self.temp_file = temp.name
                fits.writeto(self.temp_file, self.image_data, overwrite=True)
            # Construct the command with the path to the temporary FITS file
            cmd = ['solve-field', self.temp_file]
            for param in self.params.values():
                cmd.extend(param)
            result = subprocess.run(cmd, check=True, text=True, capture_output=True)
            self.finished.emit(result.stdout)
        except subprocess.CalledProcessError as e:
            self.error.emit(f"{translations[self.language]['astrometry']['solve_field_command_failed']}: {e.stderr}")
        except Exception as e:
            self.error.emit(f"{translations[self.language]['astrometry']['unexpected_error']}: {str(e)}")
        finally:
            try:    
                with fits.open(self.temp_file[:-5]+".wcs") as file:
                    wcs = WCS(file[0].header)
                wcs_tip = True
            except Exception as e:
                wcs = WCS()
                wcs_tip = False
                self.error.emit(f"{translations[self.language]['astrometry']['failed_to_calculate_wcs']}: {str(e)}")
                
            # Clean up the temporary file
            if self.temp_file and os.path.exists(self.temp_file):
                # Execute tablist command to get star coordinates and information
                axy_file = self.temp_file.replace('.fits', '.axy')
                tablist_cmd = ['tablist', axy_file]
                try:
                    result = subprocess.run(tablist_cmd, check=True, text=True, capture_output=True)
                    self.star_info.emit(result.stdout,wcs,wcs_tip)
                except subprocess.CalledProcessError as e:
                    self.error.emit(f"{translations[self.language]['astrometry']['tablist_command_failed']}: {e.stderr}")
            
            if self.save_image:
                try:
                    # 保存图像
                    if self.save_image_name[-5:]!='.fits':
                        self.save_image_name += '.fits'
                    save_image_cmd = ['mv',self.temp_file[:-5]+".new", os.path.join(self.save_image_path, self.save_image_name)]
                    subprocess.run(save_image_cmd, check=True, text=True, capture_output=True)
                except Exception as e:
                    self.error.emit(f"{translations[self.language]['astrometry']['failed_to_save_image']}: {str(e)}")
            
            try:
                # Remove all related temporary files
                base_file = self.temp_file.rsplit('.', 1)[0]
                for ext in ['fits', 'axy', 'corr', 'match', 'rdls', 'solved', 'wcs']:
                    file_to_remove = f"{base_file}.{ext}"
                    if os.path.exists(file_to_remove):
                        os.remove(file_to_remove)
                file_to_remove = f"{base_file}-indx.xyls"
                if os.path.exists(file_to_remove):
                    os.remove(file_to_remove)
            except Exception as e:
                self.error.emit(f"{translations[self.language]['astrometry']['failed_to_remove_temporary_files']}: {str(e)}")


