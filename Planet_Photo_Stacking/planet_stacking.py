"""
Photo Stacking Jupiter to form a clear image with less noise
"""

import os
import re
import sys
import shutil
from PIL import Image, ImageOps

def del_folders(folder):
    content = os.listdir()
    for item in content:
        if os.path.isdir(item) and item.startswith(folder):
            shutil.rmtree(item)
    return

def crop_images():
    return

def clean_folder():
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
