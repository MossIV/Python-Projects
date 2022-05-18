""" This scripts removes the airplane from the moon by taking the median RGB values of the moon"""
import os
from PIL import Image

print("\n Removing plane...")

os.chdir('moon_cropped')
images = os.listdir()

red_data = []
green_data = []
blue_data = []
for image in images:
    with Image.open(image) as img:
        if image == image[0]: # gets size of first cropped image
            img_size = img.size
        red_data.append(list(img.getdata(0)))
        green_data.append(list(img.getdata(1)))
        blue_data.append(list(img.getdata(2)))
med_red = [x[len(red_data/2)] for x in zip(*red_data)]
med_green = [x[len(green_data)] for x in zip(*green_data)]
med_blue = [x[len(blue_data)] for x in zip(*blue_data)]

merged_data = list(zip(med_red,med_green,med_blue))
stacked = Image.new('RGB', (img_size))
stacked.putdata(merged_data)
stacked.show()

os.chdir('..')
stacked.save('moon_no_plane.tif','TIFF')
print('done')
