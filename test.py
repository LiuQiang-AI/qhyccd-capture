import numpy as np
import matplotlib.pyplot as plt  # 导入matplotlib库用于显示图像

def find_possible_dimensions(total_pixels):
    possible_sizes = []
    for i in range(1, int(total_pixels**0.5) + 1):
        if total_pixels % i == 0:
            possible_sizes.append((i, total_pixels // i))
    return possible_sizes

def read_raw_image(path, image_width, image_height):
    # 使用numpy从文件读取二进制数据
    raw_image = np.fromfile(path, dtype=np.uint16)
    
    # 检查文件大小是否符合预期的图像尺寸
    if raw_image.size != image_width * image_height:
        raise ValueError("文件大小与提供的尺寸不匹配")
    
    # 重塑数组以匹配图像尺寸
    raw_image = raw_image.reshape((image_height, image_width))
    
    # 将16位数据中的高8位和低8位交换
    # raw_image = ((raw_image & 0xFF) << 8) | ((raw_image >> 8) & 0xFF)
    
    return raw_image

def display_image(image_array, size):
    print(f"显示尺寸: {size[0]} x {size[1]}")
    plt.imshow(image_array, cmap='gray')
    plt.title(f"尺寸: {size[0]} x {size[1]}")
    plt.show()

if __name__ == "__main__":
    image_path = "/home/q/work/qhyccd-capture/capture.raw"
    total_pixels = 8294400  # 总像素数
    sizes = find_possible_dimensions(total_pixels)
    
    for size in sizes:
        try:
            image_width, image_height = 3840, 2160
            image_array = read_raw_image(image_path, image_width, image_height)
            display_image(image_array, size)
        except ValueError as e:
            print(e)
        except Exception as e:
            print(f"在尺寸 {size[0]} x {size[1]} 处理时发生错误: {e}")
