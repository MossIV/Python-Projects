"""
Photo Stacking Jupiter to form a clear image with less noise
"""

import os
import re
import sys
import shutil
from PIL import Image, ImageOps

def del_folders(folder):
    """
    Delete folders if it matches the parameter
    """
    content = os.listdir()
    for item in content:
        if os.path.isdir(item) and item.startswith(folder):
            shutil.rmtree(item)
    return

def crop_images():
    """
    Crops and scale images of a planet to box around a planet
    """
    files = os.listdir()
    for file_num, file in enumerate(files, start=1):
        with Image.open(file) as img:
            gray = img.convert('L')
            bw = gray.point(lambda x: 0 if x< 90 else 255)
            box = bw.getbbox()
            padded_box = (box[0]-20,box[1]-20,box[2]+20,box[3]+20)
            cropped = img.crop(padded_box)
            scaled = ImageOps.fit(cropped,(860,860),Image.LANCZOS,0,(0.5,0.5))
            file_name = f'cropped_{file_num}.jpg'
            scaled.save(file_name, "JPEG")
    return

def clean_folder(prefix_to_save):
    """
    Removes files that dont have the defined prefix
    """
    files = os.listdir()
    for file in files:
        if not file.startswith(prefix_to_save):
            os.remove(file)
    return

def main():
    """ Get starting folder, copy folder, run crop function and clean folder."""

    frames_folder = 'video_frames'

    # preparing files and folders
    del_folders('cropped')
    shutil.copytree(frames_folder, 'cropped')

    # run cropping function
    print("Start cropping and scaling...")
    os.chdir('cropped')
    crop_images()
    clean_folder()

    print("Done \n")
