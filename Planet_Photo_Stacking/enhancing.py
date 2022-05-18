"""This script improves the quality of the final stacked image"""
from PIL import Image, ImageFilter, ImageEnhance

def main():
    """
    Main function for opening file
    """
    in_file = 'jupiter_stacked.tif'
    img = Image.open(in_file)
    img_enh = enhance_image(img)
    img_enh.show()
    img_enh.save('enhanced.tif', 'TIFF')

def enhance_image(image):
    """
    modifies the image with filters
    """
    enhancer = ImageEnhance.Brightness(image)
    img_enh = enhancer.enhance(0.75)

    enhancer = ImageEnhance.Contrast(img_enh)
    img_enh = enhancer.enhance(1.6)

    enhancer = ImageEnhance.Color(img_enh)
    img_enh = enhancer.enhance(1.7)

    img_enh = img_enh.rotate(angle=133, expand=True)

    img_enh = img_enh.filter(ImageFilter.SHARPEN)

    return img_enh

if __name__ == '__main__':
    main()
