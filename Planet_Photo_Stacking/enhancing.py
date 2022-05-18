"""This script improves the quality of the final stacked image"""
from PIL import Image, ImageFilter, ImageEnhance

def main():
    in_file = 'jupiter_stacked.tif'
    img = Image.open(in_file)
    img_enh = enhance_image(img)
    img_enh.show()
    img_enh.save('enhanced.tif', 'TIFF')

def enhance_image(image):
    return