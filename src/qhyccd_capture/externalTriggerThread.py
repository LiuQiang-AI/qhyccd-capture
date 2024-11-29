import numpy as np
import ctypes
from ctypes import byref
from .language import translations
import threading
import time

class ExternalTriggerThread(threading.Thread):
    def __init__(self, camhandle, qhyccddll,sdk_output_queue,trigger_interface_id,use_trigger_output,image_data,language='cn'):
        super().__init__()
        self.language = language
        self.camhandle = camhandle
        self.qhyccddll = qhyccddll
        self.sdk_output_queue = sdk_output_queue
        self.trigger_interface_id = trigger_interface_id
        self.use_trigger_output = use_trigger_output
        self.image_w,self.image_h,self.image_c,self.camera_bit = image_data
        self.trigger_state = True
        self.running = threading.Event()
        self.running.set()
        self.capture_thread = None
        self.set_trigger_function(self.trigger_state)
        self.update_trigger_interface(self.trigger_interface_id)
        self.enable_trigger_output(self.use_trigger_output)
        
    def run(self):
        self.capture_thread = threading.Thread(target=self.capture_frame)
        self.capture_thread.start()

    def capture_frame(self):
        while self.running.is_set():
            ret = self.qhyccddll.ExpQHYCCDSingleFrame(self.camhandle)
            if ret != 0:
                self.sdk_output_queue.put({"order":"error","data":f"exp_qhyccd_single_frame_failed: {ret}"})
                return
            w, h, b, c = ctypes.c_uint32(), ctypes.c_uint32(), ctypes.c_uint32(), ctypes.c_uint32()
            length = int(self.image_h * self.image_w * self.image_c * (self.camera_bit // 8))
            imgdata = (ctypes.c_ubyte * length)()
            ret = self.qhyccddll.GetQHYCCDSingleFrame(self.camhandle, byref(w), byref(h), byref(b), byref(c), imgdata)
            if ret != 0:
                self.sdk_output_queue.put({"order":"error","data":f"get_single_frame_failed: {ret}"})
                return
            img_size = w.value * h.value * c.value * (b.value // 8)
            img = np.ctypeslib.as_array(imgdata, shape=(img_size,))
            if c.value == 3:
                img = img.reshape((h.value, w.value, c.value))
                img = img[:, :, ::-1]  # BGR to RGB
            else:
                img = img.reshape((h.value, w.value)) if b.value != 16 else img.view(np.uint16).reshape((h.value, w.value))
            self.sdk_output_queue.put({"order":"success",'data':{'img':img,'w':w.value,'h':h.value,'c':c.value,'b':b.value}})

    def update_trigger_interface(self,trigger_interface_id):
        ret = self.qhyccddll.SetQHYCCDTrigerInterface(self.camhandle,trigger_interface_id)
        if ret != 0:
            self.sdk_output_queue.put({"order":"error","data":f"{translations[self.language]['externalTriggerThread']['set_trigger_interface_failed']}: {ret}"})
            return
        self.sdk_output_queue.put({"order":"tip","data":f"{translations[self.language]['externalTriggerThread']['set_trigger_interface_success']}:{trigger_interface_id}:{trigger_interface_id}"})
    
    def set_trigger_function(self,trigger_state):
        ret = self.qhyccddll.SetQHYCCDTrigerFunction(self.camhandle,trigger_state)
        if ret != 0:
            self.sdk_output_queue.put({"order":"error","data":f"{translations[self.language]['externalTriggerThread']['set_trigger_function_failed']}: {ret}"})
            return
        self.sdk_output_queue.put({"order":"tip","data":f"{translations[self.language]['externalTriggerThread']['set_trigger_function_success']}:{trigger_state}:{trigger_state}"})
        
    def enable_trigger_output(self,use_trigger_output):
        ret = self.qhyccddll.EnableQHYCCDTrigerOut(self.camhandle)
        if ret != 0:
            self.sdk_output_queue.put({"order":"error","data":f"{translations[self.language]['externalTriggerThread']['enable_trigger_output_failed']}: {ret}"})
            return
        self.sdk_output_queue.put({"order":"tip","data":f"{translations[self.language]['externalTriggerThread']['enable_trigger_output_success']}:{use_trigger_output}:{use_trigger_output}"})
        
    def set_image_data(self,image_data):
        self.image_w,self.image_h,self.image_c,self.camera_bit = image_data
    
    def cancel_qhyccd_exposing_and_readout(self):
        ret = self.qhyccddll.CancelQHYCCDExposingAndReadout(self.camhandle)
        if ret != 0:
            self.sdk_output_queue.put({"order":"error","data":f"{translations[self.language]['externalTriggerThread']['cancel_qhyccd_exposing_and_readout_failed']}: {ret}"})
            return
        self.sdk_output_queue.put({"order":"tip","data":f"{translations[self.language]['externalTriggerThread']['cancel_qhyccd_exposing_and_readout_success']}:{ret}:{ret}"})
        
    def stop(self):
        if self.capture_thread is not None:
            self.running.clear()
            ret = self.qhyccddll.CancelQHYCCDExposingAndReadout(self.camhandle)
            if ret != 0:
                self.sdk_output_queue.put({"order":"error","data":f"{translations[self.language]['externalTriggerThread']['cancel_qhyccd_exposing_and_readout_failed']}: {ret}"})
                return
            self.sdk_output_queue.put({"order":"tip","data":f"{translations[self.language]['externalTriggerThread']['set_trigger_function_success']}:False"})
            self.capture_thread.join()
        self.trigger_state = False
        ret = self.qhyccddll.SetQHYCCDTrigerFunction(self.camhandle,False)
        if ret != 0:
            self.sdk_output_queue.put({"order":"error","data":f"{translations[self.language]['externalTriggerThread']['set_trigger_function_failed']}: {ret}"})
            return
        
        self.join()
