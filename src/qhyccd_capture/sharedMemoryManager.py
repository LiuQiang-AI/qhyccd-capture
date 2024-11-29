from multiprocessing import shared_memory

class SharedMemoryManager:
    def __init__(self, name=None, size=0, create=False):
        self.name = name
        self.size = size
        self.create = create
        self.shm = None

    def __enter__(self):
        if self.create:
            self.shm = shared_memory.SharedMemory(create=True, size=self.size)
        else:
            self.shm = shared_memory.SharedMemory(name=self.name)
        return self.shm

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.shm is not None:    
            self.shm.close()
            if self.create:
                self.shm.unlink()