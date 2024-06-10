# -*- coding: utf-8 -*-

###TO DO###
# Organise files in BIDS format.
# Add percentage completion metric.
# Output mri_processor.py Bash terminal outputs / prints into .txt log file
# Add option to run analysis for all subjects. E.g. for fMRI preprocessing, the input question could be: "Enter the participant's ID (e.g. P001), or write 'ALL' to execute for all participants."
# Potentially recreate preprocessing pipeline with fmriprep just to show that I ca n use it. And maybe compare analysis results after my preprocessing and fmriprep preprocessing

#region IMPORT PACKAGES.

import time
import urllib.parse
import webbrowser
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import boxsdk
from boxsdk import OAuth2, Client
from boxsdk.object.file import File
from boxsdk.object.folder import Folder
import psutil
import signal
import sys
import subprocess
import pandas as pd
import shutil
import numpy as np
import re
import nibabel as nib
import matplotlib.pyplot as plt
import fnmatch
from collections import defaultdict
import io
import msoffcrypto
import openpyxl
import warnings
import pydicom
import random
import nibabel as nib
from skimage.metrics import structural_similarity as ssim
from plotnine import *
from scipy import stats

#endregion

#region INSTRUCTIONS.
print("\nWelcome to the MRI analysis processor. Please complete the following before proceeding:\n")
print("1. Upload the participant's data to Box.\n")
print("2. In the Bash terminal, change the working directory to the participant_data folder within the cisc2 drive.\n")
answer = input("Have the above steps been completed? (y/n)\n")
if answer != 'y':
    print('Error: please complete prerequisite steps before proceeding.\n')
    sys.exit()
#endregion

#region DOWNLOAD BOX FILES TO SERVER.

answer2 = input("Would you like to update your files from Box? (y/n)\n")
if answer2 == 'y':
    p_id = input("Enter the participant's ID (e.g. P001).\n")
    working_dir = os.getcwd()
    p_id_folder = os.path.join(os.getcwd(), p_id)
    if not os.path.exists(p_id_folder):
        os.makedirs(p_id_folder)
    
    # Define the signal handler function
    def signal_handler(sig, frame):
        # Kill the process using port 8080
        for proc in psutil.process_iter():
            try:
                connections = proc.connections()
                for conn in connections:
                    if conn.laddr.port == 8080:
                        proc.kill()
            except psutil.AccessDenied:
                pass
        # Exit the script
        exit(0)
    # Register the signal handler function for SIGINT and SIGTSTP signals
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTSTP, signal_handler)
    # Set up OAuth2 credentials
    CLIENT_ID = 'hv3z8wjk584zopc89fgsc29ikb6m0emp'
    CLIENT_SECRET = 'IpbJPrsXb0LnhtJW36Z0bfXQFhIObgpH'
    REDIRECT_URI = 'http://localhost:8080'
    # Create the OAuth2 object
    oauth = OAuth2(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        store_tokens=None,
    )
    # Create a simple HTTP server to handle the OAuth2 callback
    class CallbackHandler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            # Suppress log messages from the web server. Note that when troubleshooting, try to comment out this function as it may be suppressing error messages that can shine a light on the issue. 
            pass
        def do_GET(self):
            if self.path.startswith('/'):
                # Extract the authorization code from the URL
                query = urllib.parse.urlparse(self.path).query
                params = urllib.parse.parse_qs(query)
                if 'code' in params:
                    authorization_code = params['code'][0]
                    # Exchange the authorization code for an access token
                    access_token, refresh_token = oauth.authenticate(
                        authorization_code)
                    # Shut down the HTTP server after the code is retrieved
                    self.send_response(200)
                    self.send_header('Content-type', 'text/html')
                    self.end_headers()
                    self.wfile.write(
                        b'<html><head><title>Authorization Successful</title></head><body><h1>Authorization Successful</h1><p>You can close this window now.</p></body></html>')
                    threading.Thread(target=self.server.shutdown).start()
                else:
                    self.send_response(400)
                    self.send_header('Content-type', 'text/html')
                    self.end_headers()
                    self.wfile.write(
                        b'<html><head><title>Bad Request</title></head><body><h1>Bad Request</h1></body></html>')
            else:
                self.send_response(400)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(
                    b'<html><head><title>Bad Request</title></head><body><h1>Bad Request</h1></body></html>')
    # Start the local web server to handle the OAuth2 callback
    server = HTTPServer(('localhost', 8080), CallbackHandler)
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.start()
    # Perform the authentication flow
    auth_url, _ = oauth.get_authorization_url(REDIRECT_URI)
    # Open the authorization URL in a web browser
    webbrowser.open(auth_url)
    # Wait for the user to complete the authorization flow
    print("Waiting for authorisation...")
    input("Press Enter to continue once authorised...")
    # Shut down the local web server
    server.shutdown()
    # Create the Box client using the access token
    client = Client(oauth)
    # Get the folder ID by name
    folder_name = f'{p_id}'
    search_results = client.search().query(query=folder_name, type='folder')
    folder = next(
        (item for item in search_results if item.name == folder_name), None)
    # Define get_downloaded_files function
    def get_downloaded_files(save_directory):
        downloaded_files = set()
        for root, dirs, files in os.walk(save_directory):
            for file in files:
                downloaded_files.add(file)
        return downloaded_files
    # Define download_files_from_folder function
    def download_files_from_folder(folder, save_directory, downloaded_files):
        MAX_RETRY_ATTEMPTS = 3
        RETRY_DELAY_SECONDS = 5
        items = list(client.folder(folder.id).get_items(limit=1000, offset=0))
        for item in items:
            if isinstance(item, File):
                if item.name in downloaded_files:
                    continue
                file_path = f'{save_directory}/{item.name}'
                retry_attempts = 0
                while retry_attempts < MAX_RETRY_ATTEMPTS:
                    try:
                        with open(file_path, 'wb') as writeable_stream:
                            item.download_to(writeable_stream)
                            downloaded_files.add(item.name)
                            print(f"Downloaded: {item.name}")
                        break
                    except Exception as e:
                        print(f"An error occurred while downloading '{item.name}': {str(e)}")
                        print("Retrying...")
                        time.sleep(RETRY_DELAY_SECONDS)
                        retry_attempts += 1
                if retry_attempts == MAX_RETRY_ATTEMPTS:
                    print(f"Failed to download '{item.name}' after {MAX_RETRY_ATTEMPTS} attempts.")
            elif isinstance(item, Folder):
                subdirectory = f'{save_directory}/{item.name}'
                os.makedirs(subdirectory, exist_ok=True)
                download_files_from_folder(item, subdirectory, downloaded_files)
    # Specify the parent folder name
    parent_folder_name = f'{p_id}'
    # Retrieve the parent folder
    search_results = client.search().query(query=parent_folder_name, type='folder')
    parent_folder = next((item for item in search_results if item.name == parent_folder_name), None)
    if parent_folder:
        # Specify the save directory
        save_directory = f'/its/home/bsms9pc4/Desktop/cisc2/projects/stone_depnf/Neurofeedback/participant_data/{p_id}'
        # Get the set of downloaded files
        downloaded_files = get_downloaded_files(save_directory)
        # Download files recursively from the parent folder and its subfolders
        MAX_RETRY_ATTEMPTS = 3
        RETRY_DELAY_SECONDS = 5
        while True:
            download_files_from_folder(parent_folder, save_directory, downloaded_files)
            # Download the specific file eCRF.xlsx
            ecrf_file_name = 'eCRF.xlsx'
            ecrf_file_path = f'/its/home/bsms9pc4/Desktop/cisc2/projects/stone_depnf/Neurofeedback/participant_data/{ecrf_file_name}'
            if ecrf_file_name not in downloaded_files:
                ecrf_item = next((item for item in client.folder(parent_folder.parent.id).get_items() if item.name == ecrf_file_name), None)
                if ecrf_item:             
                    retry_attempts = 0
                    while retry_attempts < MAX_RETRY_ATTEMPTS:
                        try:
                            with open(ecrf_file_path, 'wb') as writeable_stream:
                                ecrf_item.download_to(writeable_stream)
                                downloaded_files.add(ecrf_file_name)
                                print(f"Downloaded: {ecrf_file_name}")
                            break
                        except Exception as e:
                            print(f"An error occurred while downloading '{ecrf_file_name}': {str(e)}")
                            print("Retrying...")
                            time.sleep(RETRY_DELAY_SECONDS)
                            retry_attempts += 1
                    if retry_attempts == MAX_RETRY_ATTEMPTS:
                        print(f"Failed to download '{ecrf_file_name}' after {MAX_RETRY_ATTEMPTS} attempts.")
                else:
                    print(f'eCRF.xlsx not found in parent folder.')
            else:
                print(f'eCRF.xlsx already downloaded.')
            # Get the updated folder information to check if all files have been downloaded
            parent_folder_info = client.folder(parent_folder.id).get()
            item_collection = parent_folder_info["item_collection"]
            total_items = item_collection["total_count"]
            # Check if all files have been downloaded
            if len(downloaded_files) == total_items + 1:
                break  # Break the loop if all files have been downloaded
            # Check if the access token needs refreshing
            try:
                if oauth.access_token_expires_at - time.time() < 60:  # Refresh if token expires within 60 seconds
                    oauth.refresh(oauth.access_token, oauth.refresh_token)
                    # Update the Box client with the refreshed token
                    client = Client(oauth)
            except AttributeError:
                pass  # Ignore the AttributeError if the access_token_expires_at attribute is not present
                break
    else:
        print(f"Parent folder '{parent_folder_name}' not found.")
    # Wait for the web server thread to complete
    server_thread.join()
#endregion

#region FMRI PREPROCESSING.

answer3 = input("Would you like to execute fMRI preprocessing? (y/n)\n")
if answer3 == 'y':
    p_id = input("Enter the participant's ID (e.g. P001). If you want to analyse all participants simultaneously, enter 'ALL'.\n")
    participants = ['P004', 'P006', 'P020', 'P030', 'P059', 'P078', 'P093', 'P094', 'P100', 'P107', 'P122', 'P125', 'P127', 'P128', 'P136', 'P145', 'P155', 'P199', 'P215', 'P216']
    runs = ['run01', 'run02', 'run03', 'run04']
    if p_id == 'ALL':
        participants_to_iterate = participants
    else:
        participants_to_iterate = [p_id]
    restart = input("Would you like to start the preprocessing from scratch for the selected participant(s)? This will remove all files from the 'p_id/analysis/preproc' and 'group' folders associated with them. (y/n)\n")
    if restart == 'y':
        double_check = input("Are you sure? (y/n)\n")
        if double_check == 'y':
            for p_id in participants_to_iterate:
                preproc_folder = os.path.join(os.getcwd(), p_id, 'analysis', 'preproc')
                if os.path.exists(preproc_folder):
                    print(f"Deleting {p_id} preproc folder...")
                    shutil.rmtree(preproc_folder)
                    print(f"{p_id} preproc folder successfully deleted.")
                else:
                    print(f"{p_id} preproc folder does not exist.")
            group_preproc_folder = os.path.join(os.getcwd(), 'group', 'preproc')
            if os.path.exists(group_preproc_folder):
                print(f"Deleting {p_id} group/preproc folder...")
                shutil.rmtree(group_preproc_folder)
                print(f"{p_id} group/preproc folder successfully deleted.")
            else:
                print(f"{p_id} group/preproc folder does not exist.")
        else:
            sys.exit()

    # Step 1: Create directories.
    print("\n###### STEP 1: CREATING DIRECTORIES ######")
    for p_id in participants_to_iterate:
        p_id_folder = os.path.join(os.getcwd(), p_id)
        os.makedirs(p_id_folder, exist_ok=True)
        analysis_folder = os.path.join(os.getcwd(), p_id, 'analysis')
        os.makedirs(analysis_folder, exist_ok=True)
        preproc_folder = os.path.join(os.getcwd(), p_id, 'analysis', 'preproc')
        os.makedirs(preproc_folder, exist_ok=True)
        png_folder = os.path.join(os.getcwd(), p_id, 'analysis', 'preproc', 'pngs')
        os.makedirs(png_folder, exist_ok=True)
        nifti_folder = os.path.join(os.getcwd(), p_id, 'analysis', 'preproc', 'niftis')
        os.makedirs(nifti_folder, exist_ok=True)
        structural_folder = os.path.join(os.getcwd(), p_id, "analysis", "preproc", "structural")
        os.makedirs(structural_folder, exist_ok=True)
        onset_folder = os.path.join(os.getcwd(), p_id, "analysis", "preproc", "onset_files")
        os.makedirs(onset_folder, exist_ok=True)
        mc_ms_folder = os.path.join(os.getcwd(), p_id, "analysis", "preproc", "mc_ms")
        os.makedirs(mc_ms_folder, exist_ok=True)
        bet_folder = os.path.join(os.getcwd(), p_id, "analysis", "preproc", "bet")
        os.makedirs(bet_folder, exist_ok=True)
        fieldmaps_folder = os.path.join(os.getcwd(), p_id, "analysis", "preproc", "fieldmaps")
        os.makedirs(fieldmaps_folder, exist_ok=True)
        group_folder = os.path.join(os.getcwd(), 'group')
        os.makedirs(group_folder, exist_ok=True)
        group_preproc_folder = os.path.join(os.getcwd(), 'group', 'preproc')
        os.makedirs(group_preproc_folder, exist_ok=True)
        ms_test_folder = os.path.join(os.getcwd(), 'group', 'preproc', 'ms_test')
        os.makedirs(ms_test_folder, exist_ok=True)
    print("Directories created.")

    # Step 2: Prepare Nifti files.
    print("\n###### STEP 2: PREPARING NIFTI FILES ######")
    for p_id in participants_to_iterate:
        print(f"Preparing Nifti files for {p_id}...")
        path = os.path.join(os.getcwd(), p_id, 'data', 'neurofeedback')
        cisc_folder = None
        for folder_name in os.listdir(path):
            if "CISC" in folder_name:
                cisc_folder = folder_name
                break
        if cisc_folder is None:
            print("No 'CISC' folder found in the 'neurofeedback' directory.")
            exit(1)
        def get_sequence_numbers(file_name):
            parts = file_name.split('_')
            return int(parts[1]), int(parts[2].split('.')[0])
        def copy_files(src_folder, dest_folder, sequence_number):
            src_pattern = f'*_{sequence_number:06d}_*.dcm'
            matching_files = [f for f in os.listdir(src_folder) if fnmatch.fnmatch(f, src_pattern)]
            for file in matching_files:
                src_path = os.path.join(src_folder, file)
                dest_path = os.path.join(dest_folder, file)
                shutil.copy(src_path, dest_path)
        def main():
            src_folder = os.path.join(path, cisc_folder)
            dicoms_folder = os.path.join(os.getcwd(), p_id, 'analysis', 'preproc', 'dicoms')
            run01_folder = os.path.join(os.getcwd(), p_id, 'analysis', 'preproc', 'dicoms', 'run01_dicoms')
            run02_folder = os.path.join(os.getcwd(), p_id, 'analysis', 'preproc', 'dicoms', 'run02_dicoms')
            run03_folder = os.path.join(os.getcwd(), p_id, 'analysis', 'preproc', 'dicoms', 'run03_dicoms')
            run04_folder = os.path.join(os.getcwd(), p_id, 'analysis', 'preproc', 'dicoms', 'run04_dicoms')
            os.makedirs(dicoms_folder, exist_ok=True)
            os.makedirs(run01_folder, exist_ok=True)
            os.makedirs(run02_folder, exist_ok=True)
            os.makedirs(run03_folder, exist_ok=True)
            os.makedirs(run04_folder, exist_ok=True)
            files = [f for f in os.listdir(src_folder) if f.endswith('.dcm')]
            seq_vol_counts = {}
            for file in files:
                sequence_number, volume_number = get_sequence_numbers(file)
                if sequence_number not in seq_vol_counts:
                    seq_vol_counts[sequence_number] = []
                seq_vol_counts[sequence_number].append(volume_number)
            seq_210 = [sequence_number for sequence_number, volume_numbers in seq_vol_counts.items() if len(volume_numbers) == 210]
            seq_238 = [sequence_number for sequence_number, volume_numbers in seq_vol_counts.items() if len(volume_numbers) == 238]
            min_210 = min(seq_210)
            max_210 = max(seq_210)
            min_238 = min(seq_238)
            max_238 = max(seq_238)
            if not os.listdir(run01_folder):
                print(f"Copying Run01 dicoms for {p_id}...")
                copy_files(src_folder, run01_folder, min_210)
                print(f"{p_id} Run01 dicoms copied. Number of files:", str(len(os.listdir(run01_folder))) + ".", "Sequence number:", min_210)
            if not os.listdir(run02_folder):
                print(f"Copying Run02 dicoms for {p_id}...")
                copy_files(src_folder, run02_folder, min_238)
                print(f"{p_id} Run02 dicoms copied. Number of files:", str(len(os.listdir(run02_folder))) + ".", "Sequence number:", min_238)
            if not os.listdir(run03_folder):
                print(f"Copying Run03 dicoms for {p_id}...")
                copy_files(src_folder, run03_folder, max_238)
                print(f"{p_id} Run03 dicoms copied. Number of files:", str(len(os.listdir(run03_folder))) + ".", "Sequence number:", max_238)
            if not os.listdir(run04_folder):
                print(f"Copying Run04 dicoms for {p_id}...")
                copy_files(src_folder, run04_folder, max_210)
                print(f"{p_id} Run04 dicoms copied. Number of files:", str(len(os.listdir(run04_folder))) + ".", "Sequence number:", max_210)
        if __name__ == "__main__":
            main()
        for run in runs:
            destination_folder = os.path.join(os.getcwd(), p_id, "analysis", "preproc", "dicoms", f"{run}_dicoms")
            output_folder = os.path.join(os.getcwd(), p_id, "analysis", "preproc", "niftis")
            output_file = os.path.join(output_folder, f"{run}.nii")
            if not os.path.exists(output_file):
                print(f"Converting {run.upper()} DICOM files to Nifti format for {p_id}...")
                subprocess.run(['dcm2niix', '-o', output_folder, '-f', run, '-b', 'n', destination_folder])
                print(f"{p_id} {run.upper()} DICOM files converted to Nifti format.")
            else:
                print(f"{p_id} {run.upper()} Nifti file already exists. Skipping conversion.")
            png_path = f'{p_id}/analysis/preproc/pngs/{run}.png'
            nifti_path = f'{p_id}/analysis/preproc/niftis/{run}.nii'
            if not os.path.exists(png_path):
                print(f"Saving {p_id} {run} Nifti as PNG...")
                save_png = subprocess.run(['fsleyes', 'render', '--scene', 'ortho', '-of', png_path, nifti_path], capture_output=True, text=True)
                if save_png.returncode == 0:
                    print("Screenshot saved as", png_path)
                else:
                    print("Error encountered:", save_png.stderr)
            else:
                print('PNG files already created. Skipping conversion.')
        print(f"Check PNG files in {p_id}/analysis/preproc/pngs to see whether Niftis are in correct orientation. Anterior of brain should be facing right in sagittal view, right and left of brain should be swapped in coronal and transverse views, and anterior of the brain should be facing towards the top of the image in the transverse view. Other aspects should be easily viewable. Incorrect orientations can be corrected for using 'fslreorient2std' or 'fslswapdim' commands.")

    # Step 3: Brain extract structural Nifti.
    print("\n###### STEP 3: BRAIN EXTRACTING STRUCTURAL NIFTI ######")
    for p_id in participants_to_iterate:
        src_folder = os.path.join(path, cisc_folder)
        destination_folder = f'{p_id}/analysis/preproc/structural'
        new_filename = 'structural.nii'
        if not os.path.exists(f'{p_id}/analysis/preproc/structural/structural.nii'):
            nifti_folder = os.path.join(src_folder, 'depression_neurofeedback', 'nifti')
            nii_files = [f for f in os.listdir(nifti_folder) if f.endswith('.nii')]
            if len(nii_files) == 1:
                source_file = os.path.join(nifti_folder, nii_files[0])
                shutil.copy(source_file, destination_folder)
                copied_file_path = os.path.join(destination_folder, os.path.basename(source_file))
                new_file_path = os.path.join(destination_folder, new_filename)
                os.rename(copied_file_path, new_file_path)
                print('T1 Nifti copied and renamed to structural.nii.')
            else:
                print("No .nii file found or multiple .nii files found in the 'nifti' folder.")
        else:
            print('Structural Nifti file already exists. Skipping process.')
        bet_path = os.path.join(os.getcwd(), p_id, "analysis", "preproc", "structural", "structural_brain.nii")
        structural_path = os.path.join(os.getcwd(), p_id, "analysis", "preproc", "structural", "structural.nii")
        if not os.path.exists(f'{p_id}/analysis/preproc/structural/structural_brain.nii.gz'):
            print("Performing brain extraction on structural image...")
            subprocess.run(['bet', structural_path, bet_path, '-m', '-R'])
            print("Structural image brain extracted.")
        else:
            print("Structural image already brain extracted. Skipping process.")

    # Step 4: Check and correct for binary number overflow in functional data.
    print("\n###### STEP 4: CORRECTING EPI BINARY NUMBER OVERFLOW ######")
    for p_id in participants_to_iterate:
        def get_nifti_data_type(file_path):
            try:
                result = subprocess.run(['fslinfo', file_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                if result.returncode == 0:
                    lines = result.stdout.splitlines()
                    for line in lines:
                        if 'data_type' in line:
                            data_type = line.split()[-1].strip()
                            return data_type
                        else:
                            print("Error: Unable to extract data_type from fslinfo output.")
                else:
                    print(f"Error: fslinfo command failed with the following error:\n{result.stderr}")
            except Exception as e:
                print(f"Error: An exception occurred - {str(e)}")
        for run in runs:
            nifti_file_path = os.path.join(os.getcwd(), p_id, 'analysis', 'preproc', 'niftis', f'{run}.nii')
            data_type_value = get_nifti_data_type(nifti_file_path)
            output_path = os.path.join(os.getcwd(), p_id, 'analysis', 'preproc', 'niftis', f'{run}_nh.nii.gz')
            if not os.path.exists(output_path):
                if data_type_value == 'INT16':
                    print(f'Filling holes in {run} raw Nifti image.')
                    subprocess.run(['fslmaths', nifti_file_path, '-mul', '-1', '-thr', '0', '-bin', '-mul', '65536', '-add', nifti_file_path, output_path])
                    print(f'Holes filled in {run} raw Nifti image.')
                else:
                    print(f'Data type for {run} Nifti image is not INT16. Cannot complete hole filling process.')
                    sys.exit()
            else:
                print(f'Holes already filled in {run} raw Nifti image. Skipping process.')

    # Step 5: Perform motion correction.
    print("\n###### STEP 5: PERFORMING MOTION CORRECTION ######")
    for p_id in participants_to_iterate:
        use_middle_vol_vals = []
        use_sinc_interp_vals = []
        for run in runs:
            input_path = os.path.join(os.getcwd(), p_id, 'analysis', 'preproc', 'niftis', f'{run}_nh.nii.gz')
            output_path = os.path.join(os.getcwd(), 'group', 'preproc', 'ms_test', f'{p_id}_{run}_ms_test_output.txt')
            text_output_path = os.path.join(os.getcwd(), 'group', 'preproc', 'ms_test', f'{p_id}_{run}_ms_test_log.txt') 
            if not os.path.exists(text_output_path):
                print(f"Finding optimal motion correction parameters for {run} data...")
                subprocess.run(['fsl_motion_outliers', '-i', input_path, '-o', output_path, '-s', text_output_path, '--fd', '--thresh=0.9'])
                df = pd.read_csv(text_output_path, delim_whitespace=True, names=["vol_fd"])
                use_middle_vol = 0
                use_sinc_interp = 0
                if len(df) % 2 == 0:
                    middle_vol = len(df) // 2 - 1
                    middle_vol_fd = df["vol_fd"].iloc[middle_vol]
                    if middle_vol_fd <= 0.9:
                        use_middle_vol = 1
                else:
                    middle_vol = len(df) // 2
                    middle_vol_fd = df["vol_fd"].iloc[middle_vol]
                    if middle_vol_fd <= 0.9:
                        use_middle_vol = 1
                high_motion_vols = 0
                for value in df ["vol_fd"]:
                    if value > 0.9:
                        high_motion_vols += 1
                percentage_outliers = (high_motion_vols / len(df)) * 100
                if percentage_outliers > 20:
                    use_sinc_interp = 1
                use_middle_vol_vals.append(use_middle_vol)
                use_sinc_interp_vals.append(use_sinc_interp)           
                result_file = os.path.join(os.getcwd(), 'group', 'preproc', 'ms_test', 'ms_test_master.txt')
                if not os.path.exists(result_file):
                    with open(result_file, "a") as f:
                        f.write("p_id run use_middle_vol use_sinc_interp\n")
                        f.write(f"{p_id} {run} {use_middle_vol} {use_sinc_interp}\n")
                else:
                    with open(result_file, "r") as f:
                        lines = f.readlines()
                    matching_lines = [line for line in lines if line.startswith(f"{p_id} {run}")]  
                    if matching_lines:
                        with open(result_file, "w") as f:
                            for index, line in enumerate(lines):
                                if index not in matching_lines:
                                    f.write(line)
                            f.write(f"{p_id} {run} {use_middle_vol} {use_sinc_interp}\n")
                    else:
                        with open(result_file, "a") as f:
                            f.write(f"{p_id} {run} {use_middle_vol} {use_sinc_interp}\n")
            else:
                print(f"Motion correction optimisation for {run} already performed. Skipping process.")
        for run in runs:
            input_path = os.path.join(os.getcwd(), p_id, 'analysis', 'preproc', 'niftis', f'{run}_nh.nii.gz')
            output_path = os.path.join (os.getcwd(), p_id, 'analysis', 'preproc', 'mc_ms', f'{run}_nh_mc.nii.gz') 
            if not os.path.exists(output_path):
                print(f"Performing motion correction on {run} data...")
                if run == 'run01':
                    if use_middle_vol_vals[0] == 1 and use_sinc_interp_vals[0] == 0:
                        subprocess.run(['mcflirt', '-in', input_path, '-out', output_path, '-mats'])
                        print(f"{run} motion corrected with middle volume reference and no sinc interpolation.")
                    elif use_middle_vol_vals[0] == 1 and use_sinc_interp_vals[0] == 1:
                        subprocess.run(['mcflirt', '-in', input_path, '-out', output_path, '-stages', '4', '-mats'])
                        print(f"{run} motion corrected with middle volume reference and sinc interpolation.")
                    elif use_middle_vol_vals[0] == 0 and use_sinc_interp_vals[0] == 0:
                        subprocess.run(['mcflirt', '-in', input_path, '-out', output_path, '-meanvol', '-mats'])
                        print(f"{run} motion corrected with mean volume reference and no sinc interpolation.")
                    elif use_middle_vol_vals[0] == 0 and use_sinc_interp_vals[0] == 1:
                        subprocess.run(['mcflirt', '-in', input_path, '-out', output_path, '-meanvol', '-stages', '4', '-mats'])
                        print(f"{run} motion corrected with mean volume reference and sinc interpolation.")
                if run == 'run02':
                    if use_middle_vol_vals[1] == 1 and use_sinc_interp_vals[1] == 0:
                        subprocess.run(['mcflirt', '-in', input_path, '-out', output_path, '-mats'])
                        print(f"{run} motion corrected with middle volume reference and no sinc interpolation.")
                    elif use_middle_vol_vals[1] == 1 and use_sinc_interp_vals[1] == 1:
                        subprocess.run(['mcflirt', '-in', input_path, '-out', output_path, '-stages', '4', '-mats'])
                        print(f"{run} motion corrected with middle volume reference and sinc interpolation.")
                    elif use_middle_vol_vals[1] == 0 and use_sinc_interp_vals[1] == 0:
                        subprocess.run(['mcflirt', '-in', input_path, '-out', output_path, '-meanvol', '-mats'])
                        print(f"{run} motion corrected with mean volume reference and no sinc interpolation.")
                    elif use_middle_vol_vals[1] == 0 and use_sinc_interp_vals[1] == 1:
                        subprocess.run(['mcflirt', '-in', input_path, '-out', output_path, '-meanvol', '-stages', '4', '-mats'])
                        print(f"{run} motion corrected with mean volume reference and sinc interpolation.")
                if run == 'run03':
                    if use_middle_vol_vals[2] == 1 and use_sinc_interp_vals[2] == 0:
                        subprocess.run(['mcflirt', '-in', input_path, '-out', output_path, '-mats'])
                        print(f"{run} motion corrected with middle volume reference and no sinc interpolation.")
                    elif use_middle_vol_vals[2] == 1 and use_sinc_interp_vals[2] == 1:
                        subprocess.run(['mcflirt', '-in', input_path, '-out', output_path, '-stages', '4', '-mats'])
                        print(f"{run} motion corrected with middle volume reference and sinc interpolation.")
                    elif use_middle_vol_vals[2] == 0 and use_sinc_interp_vals[2] == 0:
                        subprocess.run(['mcflirt', '-in', input_path, '-out', output_path, '-meanvol', '-mats'])
                        print(f"{run} motion corrected with mean volume reference and no sinc interpolation.")
                    elif use_middle_vol_vals[2] == 0 and use_sinc_interp_vals[2] == 1:
                        subprocess.run(['mcflirt', '-in', input_path, '-out', output_path, '-meanvol', '-stages', '4', '-mats'])
                        print(f"{run} motion corrected with mean volume reference and sinc interpolation.")
                if run == 'run04':
                    if use_middle_vol_vals[3] == 1 and use_sinc_interp_vals[3] == 0:
                        subprocess.run(['mcflirt', '-in', input_path, '-out', output_path, '-mats'])
                        print(f"{run} motion corrected with middle volume reference and no sinc interpolation.")
                    elif use_middle_vol_vals[3] == 1 and use_sinc_interp_vals[3] == 1:
                        subprocess.run(['mcflirt', '-in', input_path, '-out', output_path, '-stages', '4', '-mats'])
                        print(f"{run} motion corrected with middle volume reference and sinc interpolation.")
                    elif use_middle_vol_vals[3] == 0 and use_sinc_interp_vals[3] == 0:
                        subprocess.run(['mcflirt', '-in', input_path, '-out', output_path, '-meanvol', '-mats'])
                        print(f"{run} motion corrected with mean volume reference and no sinc interpolation.")
                    elif use_middle_vol_vals[3] == 0 and use_sinc_interp_vals[3] == 1:
                        subprocess.run(['mcflirt', '-in', input_path, '-out', output_path, '-meanvol', '-stages', '4', '-mats'])
                        print(f"{run} motion corrected with mean volume reference and sinc interpolation.")
            else:
                print(f"{run} already motion corrected. Skipping process.")

    # Step 6: Perform motion scrubbing.
    print("\n###### STEP 6: PERFORMING MOTION SCRUBBING ######")
    for p_id in participants_to_iterate:
        scrubbed_vols = []
        for run in runs:
            input_path = os.path.join (os.getcwd(), p_id, 'analysis', 'preproc', 'mc_ms', f'{run}_nh_mc')
            output_path = os.path.join (os.getcwd(), p_id, 'analysis', 'preproc', 'mc_ms', f'{run}_nh_mc_ms')
            text_output_path = os.path.join (os.getcwd(), p_id, 'analysis', 'preproc', 'mc_ms', f'{run}_scrubbed_volumes.txt')
            if not os.path.exists(output_path):
                print(f"Performing motion scrubbing on {run} data...")
                subprocess.run(['fsl_motion_outliers', '-i', input_path, '-o', output_path, '-s', text_output_path, '--nomoco'])
                print(f'{run} motion scrubbed.')
            else:
                print (f'{run} already motion scrubbed. Skipping process.')
            with open(output_path, 'r') as file:
                first_row = file.readline().strip()
                num_columns = len(first_row.split('   '))
                scrubbed_vols.append(num_columns)
                if run == 'run01' or 'run04':
                    vol_num = 210
                elif run == 'run02' or 'run03':
                    vol_num = 238
                run_scrubbed_vols_perc = (num_columns / vol_num) * 100
                if run_scrubbed_vols_perc > 15:
                    print(f'Percentage of volumes scrubbed for {run} is {run_scrubbed_vols_perc}%. This exceeds tolerable threshold of 15%. Remove this run from analysis.')
                    sys.exit()
                else:
                    print(f'Percentage of volumes scrubbed for {run} is {run_scrubbed_vols_perc}%. This is within the tolerable threshold of 15%. Analysis of this run can continue.')
        sum_scrubbed_vols = sum(scrubbed_vols)
        scrubbed_vols_perc = (sum_scrubbed_vols / 896) * 100
        if scrubbed_vols_perc > 15:
            print(f'Total percentage of volumes scrubbed is {scrubbed_vols_perc}%. This exceeds tolerable threshold of 15%. Remove participant from analysis.')
            sys.exit()
        else:
            print(f'Total percentage of volumes scrubbed is {scrubbed_vols_perc}%. This is within tolerable threshold of 15%. Analysis can continue.')
        
    # # Step 7: Brain extraction of functional images.
    # print("\n###### STEP 7: BRAIN EXTRACTING FUNCTIONAL IMAGES ######")
    # for p_id in participants_to_iterate:
    #     for run in runs:
    #         output_path = os.path.join(os.getcwd(), p_id, "analysis", "preproc", "bet", f"{run}_nh_mc_bet.nii.gz")
    #         input_path = os.path.join(os.getcwd(), p_id, "analysis", "preproc", "mc_ms", f"{run}_nh_mc.nii.gz")
    #         if not os.path.exists(output_path):
    #             print(f"Performing brain extraction on {run} functional image.")
    #             subprocess.run(["bet", input_path, output_path, "-m", "-R"])
    #             print(f"{run} functional image brain extracted.")
    #         else:
    #             print(f"{run} functional image already brain extracted. Skipping process.")

    # Step 8: Confirm sequence phase encoding directions for stratification of distortion correction method.
    print("\n###### STEP 8: DETERMINING PHASE ENCODING DIRECTIONS ######")
    bad_participants = ['P004', 'P006', 'P020', 'P030', 'P078', 'P093', 'P094']
    def copy_2_dicoms(source_folder, destination_folder1, destination_folder2, target_volume_count=5):
                sequences2 = defaultdict(list)
                last_two_sets = []
                for filename in os.listdir(source_folder):
                    if filename.endswith('.dcm'):
                        file_parts = filename.split('_')
                        if len(file_parts) == 3:
                            sequence_number = int(file_parts[1])
                            volume_number = int(file_parts[2].split('.')[0])
                            sequences2[sequence_number].append((filename, volume_number))
                for sequence_number, files_info in sequences2.items():
                    if len(files_info) == target_volume_count:
                        last_two_sets.append(files_info)
                        if len(last_two_sets) > 2:
                            last_two_sets.pop(0)
                for idx, files_info in enumerate(last_two_sets):
                    for filename, _ in files_info:
                        if idx == 0:
                            destination_folder = destination_folder1
                        else:
                            destination_folder = destination_folder2
                        source_path = os.path.join(source_folder, filename)
                        destination_path = os.path.join(destination_folder, filename)
                        shutil.copy2(source_path, destination_path)
                        print(f"Copied {filename} to {destination_folder}")
    for p_id in participants_to_iterate:
        if p_id in bad_participants:
            print(f"Copying {p_id} fieldmap DICOMS to separate folder...")
            ap_fieldmaps_dicoms_folder = os.path.join(os.getcwd(), p_id, "analysis", "preproc", "dicoms", "fieldmaps", "ap")
            pa_fieldmaps_dicoms_folder = os.path.join(os.getcwd(), p_id, "analysis", "preproc", "dicoms", "fieldmaps", "badpa")
            os.makedirs(ap_fieldmaps_dicoms_folder, exist_ok=True)
            os.makedirs(pa_fieldmaps_dicoms_folder, exist_ok=True)
            path = os.path.join(os.getcwd(), p_id, 'data', 'neurofeedback')
            cisc_folder = None
            for folder_name in os.listdir(path):
                if "CISC" in folder_name:
                    cisc_folder = folder_name
                    break
            if cisc_folder is None:
                print("No 'CISC' folder found in the 'neurofeedback' directory.")
                exit(1)
            source_folder = os.path.join(path, cisc_folder)
            if not os.listdir(ap_fieldmaps_dicoms_folder) or not os.listdir(pa_fieldmaps_dicoms_folder):
                copy_2_dicoms(source_folder, ap_fieldmaps_dicoms_folder, pa_fieldmaps_dicoms_folder, target_volume_count=5)
                print(f"{p_id} fieldmap DICOMS successfully copied.")
            else:
                print(f"{p_id} fieldmap DICOMS already copied. Skipping process.")
            pe_list = ['ap', 'badpa']
            for pe in pe_list:
                destination_folder = os.path.join(os.getcwd(), p_id, "analysis", "preproc", "dicoms", "fieldmaps", pe)
                output_folder = os.path.join(os.getcwd(), p_id, "analysis", "preproc", "fieldmaps")
                output_file = os.path.join(output_folder, f"{pe}_fieldmaps.nii")
                if not os.path.exists(output_file):
                    print(f"Converting {p_id} {pe.upper()} fieldmaps DICOM files to Nifti format...")
                    subprocess.run(['dcm2niix', '-o', output_folder, '-f', f'{pe}_fieldmaps', '-b', 'n', destination_folder])
                    print(f"{p_id} {pe.upper()} fieldmaps DICOM files converted to Nifti format.")
                else:
                    print(f"{p_id} {pe.upper()} fieldmaps Nifti file already exists. Skipping conversion.")
    def copy_3_dicoms(source_folder, destination_folder1, destination_folder2, destination_folder3, target_volume_count=5):
            sequences3 = defaultdict(list)
            last_three_sets = [] 
            for filename in os.listdir(source_folder):
                if filename.endswith('.dcm'):
                    file_parts = filename.split('_')
                    if len(file_parts) == 3:
                        sequence_number = int(file_parts[1])
                        volume_number = int(file_parts[2].split('.')[0])
                        sequences3[sequence_number].append((filename, volume_number))
            for sequence_number, files_info in sequences3.items():
                if len(files_info) == target_volume_count:
                    last_three_sets.append(files_info)
                    if len(last_three_sets) > 3:
                        last_three_sets.pop(0)
            for idx, files_info in enumerate(last_three_sets):
                if idx == 0:
                    destination_folder = destination_folder1
                elif idx == 1:
                    destination_folder = destination_folder2
                else:
                    destination_folder = destination_folder3
                for filename, _ in files_info:
                    source_path = os.path.join(source_folder, filename)
                    destination_path = os.path.join(destination_folder, filename)
                    shutil.copy2(source_path, destination_path)
                    print(f"Copied {filename} to {destination_folder}")
    for p_id in participants_to_iterate:
        if p_id not in bad_participants:
            ap_fieldmaps_dicoms_folder = os.path.join(os.getcwd(), p_id, "analysis", "preproc", "dicoms", "fieldmaps", "ap")
            pa_fieldmaps_dicoms_folder = os.path.join(os.getcwd(), p_id, "analysis", "preproc", "dicoms", "fieldmaps", "pa")
            rl_fieldmaps_dicoms_folder = os.path.join(os.getcwd(), p_id, "analysis", "preproc", "dicoms", "fieldmaps", "rl")
            os.makedirs(ap_fieldmaps_dicoms_folder, exist_ok=True)
            os.makedirs(pa_fieldmaps_dicoms_folder, exist_ok=True)
            os.makedirs(rl_fieldmaps_dicoms_folder, exist_ok=True)
            path = os.path.join(os.getcwd(), p_id, 'data', 'neurofeedback')
            cisc_folder = None
            for folder_name in os.listdir(path):
                if "CISC" in folder_name:
                    cisc_folder = folder_name
                    break
            if cisc_folder is None:
                print("No 'CISC' folder found in the 'neurofeedback' directory.")
                exit(1)
            source_folder = os.path.join(path, cisc_folder)
            if not os.listdir(ap_fieldmaps_dicoms_folder) or not os.listdir(pa_fieldmaps_dicoms_folder) or not os.listdir(rl_fieldmaps_dicoms_folder):
                copy_3_dicoms(source_folder, ap_fieldmaps_dicoms_folder, pa_fieldmaps_dicoms_folder, rl_fieldmaps_dicoms_folder, target_volume_count=5)
            pe_list = ['ap', 'pa', 'rl']
            for pe in pe_list:
                destination_folder = os.path.join(os.getcwd(), p_id, "analysis", "preproc", "dicoms", "fieldmaps", pe)
                output_folder = os.path.join(os.getcwd(), p_id, "analysis", "preproc", "fieldmaps")
                output_file = os.path.join(output_folder, f"{pe}_fieldmaps.nii")
                if not os.path.exists(output_file):
                    print(f"Converting {pe.upper()} fieldmaps DICOM files to Nifti format...")
                    subprocess.run(['dcm2niix', '-o', output_folder, '-f', f'{pe}_fieldmaps', '-b', 'n', destination_folder])
                    print(f"{pe.upper()} fieldmaps DICOM files converted to Nifti format.")
                else:
                    print(f"{pe.upper()} fieldmaps Nifti file already exists. Skipping conversion.")
    for p_id in participants_to_iterate:
        if p_id in bad_participants:
            ap_fieldmaps = f"{p_id}/analysis/preproc/dicoms/fieldmaps/ap"
            pa_fieldmaps = f"{p_id}/analysis/preproc/dicoms/fieldmaps/badpa"
            run01 = f"{p_id}/analysis/preproc/dicoms/run01_dicoms"
            run02 = f"{p_id}/analysis/preproc/dicoms/run02_dicoms"
            run03 = f"{p_id}/analysis/preproc/dicoms/run03_dicoms"
            run04 = f"{p_id}/analysis/preproc/dicoms/run04_dicoms"
            folder_list = [ap_fieldmaps, pa_fieldmaps, run01, run02, run03, run04]
            pe_file = os.path.join(os.getcwd(), p_id, 'analysis', 'preproc', 'fieldmaps', 'pe_axes.txt')
            pe_axes = []
            for folder in folder_list:
                dicom_files = [os.path.join(folder, f) for f in os.listdir(folder) if f.endswith('.dcm')]
                if len(dicom_files) == 0:
                    print("No DICOM files found in the directory.")
                else:
                    random_file = random.choice(dicom_files)
                    ds = pydicom.dcmread(random_file)
                    pe_axis = ds.InPlanePhaseEncodingDirection
                    pe_axes.append(pe_axis)
                    start_index = folder.rfind('/') + 1  
                    end_index = folder.rfind('_')  
                    if end_index == -1 or end_index < start_index:
                        folder = folder[start_index:] + "_fieldmaps"
                    else:
                        folder = folder[start_index:end_index]
                    print(f"Phase Encoding Axis for {folder}: ", pe_axis)
                if not os.path.exists(pe_file):
                    with open(pe_file, "a") as f:
                        f.write("sequence pe_axis\n")
                        f.write(f"{folder} {pe_axis}\n")
                else: 
                    with open(pe_file, "r") as f:
                        lines = f.readlines()
                    matching_lines = [line for line in lines if line.startswith(f"{folder}")]
                    if matching_lines:
                        with open(pe_file, "w") as f:
                            for index, line in enumerate(lines):
                                if index not in matching_lines:
                                    f.write(line)
                            f.write(f"{folder} {pe_axis}\n")
                    else:
                        with open(pe_file, "a") as f:
                            f.write(f"{folder} {pe_axis}\n")
            print("Sequence PE axes saved to pe_axes.txt file.")
            if pe_axes == ['COL', 'ROW', 'ROW', 'ROW', 'ROW', 'COL']:
                print('Sequence PE directions are incorrect as expected (AP, RL, RL, RL, RL, AP) for this participant. Stratification of distortion correction method can now take place.')
            elif pe_axes == ['COL', 'ROW', 'ROW', 'ROW', 'ROW', 'ROW']:
                print('Sequence PE directions are incorrect as expected (AP, RL, RL, RL, RL, RL) for this participant. Stratification of distortion correction method can now take place.')
            else:
                print('Sequence PE directions are not as expected. Please investigate.')
                sys.exit()
        if p_id not in bad_participants:
            ap_fieldmaps = f"{p_id}/analysis/preproc/dicoms/fieldmaps/ap"
            pa_fieldmaps = f"{p_id}/analysis/preproc/dicoms/fieldmaps/pa"
            rl_fieldmaps = f"{p_id}/analysis/preproc/dicoms/fieldmaps/rl"
            run01 = f"{p_id}/analysis/preproc/dicoms/run01_dicoms"
            run02 = f"{p_id}/analysis/preproc/dicoms/run02_dicoms"
            run03 = f"{p_id}/analysis/preproc/dicoms/run03_dicoms"
            run04 = f"{p_id}/analysis/preproc/dicoms/run04_dicoms"
            folder_list = [ap_fieldmaps, pa_fieldmaps, rl_fieldmaps, run01, run02, run03, run04]
            pe_file = os.path.join(os.getcwd(), p_id, 'analysis', 'preproc', 'fieldmaps', 'pe_axes.txt')
            pe_axes = []
            for folder in folder_list:
                dicom_files = [os.path.join(folder, f) for f in os.listdir(folder) if f.endswith('.dcm')]
                if len(dicom_files) == 0:
                    print("No DICOM files found in the directory.")
                else:
                    random_file = random.choice(dicom_files)
                    ds = pydicom.dcmread(random_file)
                    pe_axis = ds.InPlanePhaseEncodingDirection
                    pe_axes.append(pe_axis)
                    start_index = folder.rfind('/') + 1  
                    end_index = folder.rfind('_')  
                    if end_index == -1 or end_index < start_index:
                        folder = folder[start_index:] + "_fieldmaps"
                    else:
                        folder = folder[start_index:end_index]
                    print(f"Phase Encoding Axis for {folder}: ", pe_axis)
                if not os.path.exists(pe_file):
                    with open(pe_file, "a") as f:
                        f.write("sequence pe_axis\n")
                        f.write(f"{folder} {pe_axis}\n")
                else: 
                    with open(pe_file, "r") as f:
                        lines = f.readlines()
                    matching_lines = [line for line in lines if line.startswith(f"{folder}")]
                    if matching_lines:
                        with open(pe_file, "w") as f:
                            for index, line in enumerate(lines):
                                if index not in matching_lines:
                                    f.write(line)
                            f.write(f"{folder} {pe_axis}\n")
                    else:
                        with open(pe_file, "a") as f:
                            f.write(f"{folder} {pe_axis}\n")
            print("Sequence PE axes saved to pe_axes.txt file.")
            if pe_axes == ['COL', 'COL', 'ROW', 'COL', 'COL', 'COL', 'COL']:
                print('Sequence PE directions are correct as expected (AP, PA, RL, PA, PA, PA, PA) for this participant. Stratification of distortion correction method can now take place.')
            else:
                print('Sequence PE directions are not as expected. Please investigate.')
                sys.exit()

    # Step 9: Calculate and apply fieldmaps for relevant participants.
    print("\n###### STEP 9: APPLYING FIELDMAPS ######")
    for p_id in participants_to_iterate:
        if p_id not in bad_participants:
            ap_fieldmaps = os.path.join(os.getcwd(), p_id, 'analysis', 'preproc', 'fieldmaps', 'ap_fieldmaps.nii')
            pa_fieldmaps = os.path.join(os.getcwd(), p_id, 'analysis', 'preproc', 'fieldmaps', 'pa_fieldmaps.nii')
            output_file = os.path.join(os.getcwd(), p_id, 'analysis', 'preproc', 'fieldmaps', 'merged_fieldmaps.nii.gz')
            if not os.path.exists(output_file):
                print("Merging fieldmap sequences...")
                subprocess.run(['fslmerge', '-t', output_file, ap_fieldmaps, pa_fieldmaps])
                print("Fieldmap sequences merging completed.")
            else:
                print("Fieldmap sequences already merged. Skipping process.")
            fov_phase = 1
            base_res = 64
            phase_res = 1
            echo_spacing = 0.54
            pe_steps = (fov_phase * base_res * phase_res) - 1
            readout_time_s = (pe_steps * echo_spacing) / 1000
            acqparams_file = os.path.join(os.getcwd(), p_id, 'analysis', 'preproc', 'fieldmaps', 'acqparams.txt')
            if not os.path.exists(acqparams_file):
                with open(acqparams_file, "a") as f:
                    f.write(f"0 -1 0 {readout_time_s}\n")
                    f.write(f"0 -1 0 {readout_time_s}\n")
                    f.write(f"0 -1 0 {readout_time_s}\n")
                    f.write(f"0 -1 0 {readout_time_s}\n")
                    f.write(f"0 -1 0 {readout_time_s}\n")
                    f.write(f"0 1 0 {readout_time_s}\n")
                    f.write(f"0 1 0 {readout_time_s}\n")
                    f.write(f"0 1 0 {readout_time_s}\n")
                    f.write(f"0 1 0 {readout_time_s}\n")
                    f.write(f"0 1 0 {readout_time_s}")
            fieldcoef_output_file = os.path.join(os.getcwd(), p_id, 'analysis', 'preproc', 'fieldmaps', f'topup_{p_id}_fieldcoef.nii.gz')
            movpar_output_file = os.path.join(os.getcwd(), p_id, 'analysis', 'preproc', 'fieldmaps', f'topup_{p_id}_movpar.txt')
            if not os.path.exists(fieldcoef_output_file) or not os.path.exists(movpar_output_file):
                print("Calculating fieldmaps...")
                subprocess.run(["topup", f"--imain={p_id}/analysis/preproc/fieldmaps/merged_fieldmaps.nii", f"--datain={p_id}/analysis/preproc/fieldmaps/acqparams.txt", "--config=b02b0.cnf", f"--out={p_id}/analysis/preproc/fieldmaps/topup_{p_id}", f"--iout={p_id}/analysis/preproc/fieldmaps/topup_{p_id}_unwarped"])
                print("Fieldmap calculation completed.")
                for run in runs:
                    print("Applying fieldmaps...")
                    subprocess.run(["applytopup", f"--imain={p_id}/analysis/preproc/bet/{run}_nh_mc_bet.nii.gz", f"--datain={p_id}/analysis/preproc/fieldmaps/acqparams.txt", "--inindex=6", f"--topup={p_id}/analysis/preproc/fieldmaps/topup_{p_id}", "--method=jac", f"--out={p_id}/analysis/preproc/fieldmaps/{run}_nh_mc_bet_dc"])
                    print("Fieldmap application completed.")
            else:
                print("Fieldmaps already calculated and applied. Skipping process.")
    
    # Step 10: Create onset files.
    print("\n###### STEP 10: CREATING ONSET FILES ######")
    onsetfile_sub = f'{p_id}/analysis/preproc/onset_files/onsetfile_sub.txt'
    with open(onsetfile_sub, 'w') as file:
        data_rows = [
            ['0', '20', '1'],
            ['50', '20', '1'],
            ['100', '20', '1'],
            ['150', '20', '1'],
            ['200', '20', '1'],
            ['250', '20', '1'],
            ['300', '20', '1'],
            ['350', '20', '1'],
            ['400', '20', '1']
        ]
        for row in data_rows:
            formatted_row = "\t".join(row) + "\n"
            file.write(formatted_row)
    onsetfile_guilt = f'{p_id}/analysis/preproc/onset_files/onsetfile_guilt.txt'
    with open(onsetfile_guilt, 'w') as file:
        data_rows = [
            ['20', '30', '1'],
            ['120', '30', '1'],
            ['220', '30', '1'],
            ['320', '30', '1']
        ]
        for row in data_rows:
            formatted_row = "\t".join(row) + "\n"
            file.write(formatted_row)
    onsetfile_indig = f'{p_id}/analysis/preproc/onset_files/onsetfile_indig.txt'
    with open(onsetfile_indig, 'w') as file:
        data_rows = [
            ['70', '30', '1'],
            ['170', '30', '1'],
            ['270', '30', '1'],
            ['370', '30', '1']
        ]
        for row in data_rows:
            formatted_row = "\t".join(row) + "\n"
            file.write(formatted_row)
    print('Onset files created.')


# See if quality of the neurofeedback and ability to move the thermometer correlates negatively with the number of ROI voxels that lie within signal dropout regions of the EPI images.
# Have to remove voxels from ROI that are sitting in signal dropout regions and make note of this. Perhaps ROIs with 50% of voxels removed (for example) would have 50% of the normal weighting in the analysis - perhaps this weighting can be done quantitatively, or perhaps just noted qualitatively in the discussion.

#endregion

#region THERM ANALYSIS.

answer4 = input("Would you like to execute thermometer analysis? (y/n)\n")
if answer4 == 'y':
    
    # Step 1: Access Run 2 and 3 tbv_script thermometer files and extract relevant data into dataframe.
    participants = ['P004', 'P006', 'P020', 'P030', 'P059', 'P078', 'P093', 'P094', 'P100', 'P107', 'P122', 'P125', 'P127', 'P128', 'P136', 'P145', 'P155', 'P199', 'P215', 'P216']
    def find_second_and_third_largest(files):
        sorted_files = sorted(files, key=lambda x: int(x.split('_')[-1].split('.')[0]), reverse=True)
        second_largest_path = os.path.join(folder_path, sorted_files[-2])
        third_largest_path = os.path.join(folder_path, sorted_files[-3])
        return second_largest_path, third_largest_path
    df = pd.DataFrame(columns=participants)
    for x in participants:
        analysis_folder = os.path.join(os.getcwd(), f'{x}', 'analysis')
        if not os.path.exists(analysis_folder):
            subprocess.run(['mkdir', f'{x}/analysis'])
        therm_folder = os.path.join(os.getcwd(), f'{x}', 'analysis', 'therm')
        if not os.path.exists(therm_folder):
            subprocess.run(['mkdir', f'{x}/analysis/therm'])
        folder_path = os.path.join(os.getcwd(), f'{x}', 'data', 'neurofeedback', 'tbv_script', 'data')
        files = [f for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f))]
        if len(files) == 4:
            run2_path, run3_path = find_second_and_third_largest(files)
        else:
            print("Error: The folder should contain exactly 4 files.")
        def process_file(file_path):
            if os.path.exists(file_path):
                with open(file_path, 'r') as file:
                    lines = file.readlines()[12:]
                current_value = None
                value_counter = {}
                for line in lines:
                    values = line.strip().split(',')
                    if values[2] != current_value:
                        current_value = values[2]
                        value_counter[current_value] = value_counter.get(current_value, 0) + 1
                    condition = f"{current_value.lower()}{value_counter[current_value]:02d}"
                    if 'rest' in condition:
                        condition = condition.replace('rest', 'sub')
                    if 'guilt first' in condition:
                        condition = condition.replace('guilt first', 'guilt_first')
                    if 'guilt second' in condition:
                        condition = condition.replace('guilt second', 'guilt_second')
                    if 'indignation first' in condition:
                        condition = condition.replace('indignation first', 'indig_first')
                    if 'indignation second' in condition:
                        condition = condition.replace('indignation second', 'indig_second')
                    row_header = 'r' + values[1] + '_' + condition + '_' + 'vol' + values[3] + '_val'
                    feedback_lvl_header = 'r' + values[1] + '_' + condition + '_' + 'vol' + values[3] + '_lvl'
                    value = float(values[8])
                    feedback_lvl = float(values[9])
                    if row_header not in df.index:
                        df.loc[row_header] = [None] * len(participants)
                    df.at[row_header, f'{x}'] = value
                    if feedback_lvl_header not in df.index:
                        df.loc[feedback_lvl_header] = [None] * len(participants)
                    df.at[feedback_lvl_header, f'{x}'] = feedback_lvl
        process_file(run2_path)
        process_file(run3_path)
    output_excel_path = '/its/home/bsms9pc4/Desktop/cisc2/projects/stone_depnf/Neurofeedback/participant_data/group/therm_data.xlsx'
    df.to_excel(output_excel_path, index=True)
    
    # Step 2: Access eCRF document and extract relevant data into dataframe.
    warnings.simplefilter("ignore", UserWarning)
    df_row_headers = ['dob', 'gender', 'handedness', 'exercise', 'education', 'work_status', 'panic', 'agoraphobia', 'social_anx', 'ocd', 'ptsd', 'gad', 'comorbid_anx', 'msm', 'psi_sociotropy', 'psi_autonomy', 'raads', 'panas_pos_vis_1', 'panas_neg_vis_1', 'qids_vis_1', 'gad_vis_1', 'rosenberg_vis_1', 'madrs_vis_1', 'pre_memory_intensity_guilt_1', 'pre_memory_intensity_guilt_2', 'pre_memory_intensity_indignation_1', 'pre_memory_intensity_indignation_2', 'intervention', 'techniques_guilt', 'techniques_indignation', 'perceived_success_guilt', 'perceived_success_indignation', 'post_memory_intensity_guilt_1', 'post_memory_intensity_guilt_2', 'post_memory_intensity_indignation_1', 'post_memory_intensity_indignation_2', 'rosenberg_vis_2', 'panas_pos_vis_3', 'panas_neg_vis_3', 'qids_vis_3', 'gad_vis_3', 'rosenberg_vis_3', 'madrs_vis_3']
    data_df = pd.DataFrame(index = df_row_headers)
    ecrf_file_path = '/its/home/bsms9pc4/Desktop/cisc2/projects/stone_depnf/Neurofeedback/participant_data/eCRF.xlsx'
    password = 'SussexDepNF22'
    df_values_dict = {}
    location_dict = {
        'P004_vis_1_locations': {'dob': (77, 3), 'gender': (81, 3),  'handedness': (82, 3), 'exercise': (83, 3), 'education': (84, 3), 'work_status': (85, 3), 'panic': (132, 3), 'agoraphobia': (134, 3), 'social_anx': (135, 3), 'ocd': (137, 3), 'ptsd': (140, 3), 'gad': (141, 3), 'comorbid_anx': (142, 3), 'msm': (120, 3), 'psi_sociotropy': (151, 3), 'psi_autonomy': (152, 3), 'raads': (155, 3), 'panas_pos_vis_1': (161, 3), 'panas_neg_vis_1': (162, 3), 'qids_vis_1': (172, 3), 'gad_vis_1': (173, 3), 'rosenberg_vis_1': (174, 3), 'madrs_vis_1': (185, 3)},
        'P004_vis_2_locations': {'pre_memory_intensity_guilt_1': (38, 3), 'pre_memory_intensity_guilt_2': (43, 3), 'pre_memory_intensity_indignation_1': (49, 3), 'pre_memory_intensity_indignation_2': (54, 3), 'intervention': (78, 3), 'techniques_guilt': (84, 3), 'techniques_indignation': (85, 3), 'perceived_success_guilt': (86, 3), 'perceived_success_indignation': (87, 3), 'post_memory_intensity_guilt_1': (88, 3), 'post_memory_intensity_guilt 2': (92, 3), 'post_memory_intensity_indignation_1': (97, 3), 'post_memory_indignation_2': (101, 3), 'rosenberg_vis_2': (104, 3)},
        'P004_vis_3_locations': {'panas_pos_vis_3': (36, 3), 'panas_neg_vis_3': (37, 3), 'qids_vis_3': (47, 3), 'gad_vis_3': (48, 3), 'rosenberg_vis_3': (49, 3), 'madrs_vis_3': (60, 3)},
        
        'P006_vis_1_locations': {'dob': (77, 4), 'gender': (81, 4),  'handedness': (82, 4), 'exercise': (83, 4), 'education': (84, 4), 'work_status': (85, 4), 'panic': (132, 4), 'agoraphobia': (134, 4), 'social_anx': (135, 4), 'ocd': (137, 4), 'ptsd': (140, 4), 'gad': (141, 4), 'comorbid_anx': (142, 4), 'msm': (120, 4), 'psi_sociotropy': (151, 4), 'psi_autonomy': (152, 4), 'raads': (155, 4), 'panas_pos_vis_1': (161, 4), 'panas_neg_vis_1': (162, 4), 'qids_vis_1': (172, 4), 'gad_vis_1': (173, 4), 'rosenberg_vis_1': (174, 4), 'madrs_vis_1': (185, 4)},
        'P006_vis_2_locations': {'pre_memory_intensity_guilt_1': (38, 4), 'pre_memory_intensity_guilt_2': (43, 4), 'pre_memory_intensity_indignation_1': (49, 4), 'pre_memory_intensity_indignation_2': (54, 4), 'intervention': (78, 4), 'techniques_guilt': (84, 4), 'techniques_indignation': (85, 4), 'perceived_success_guilt': (86, 4), 'perceived_success_indignation': (87, 4), 'post_memory_intensity_guilt_1': (88, 4), 'post_memory_intensity_guilt 2': (92, 4), 'post_memory_intensity_indignation_1': (97, 4), 'post_memory_indignation_2': (101, 4), 'rosenberg_vis_2': (104, 4)},
        'P006_vis_3_locations': {'panas_pos_vis_3': (36, 4), 'panas_neg_vis_3': (37, 4), 'qids_vis_3': (47, 4), 'gad_vis_3': (48, 4), 'rosenberg_vis_3': (49, 4), 'madrs_vis_3': (60, 4)},
    
        'P020_vis_1_locations': {'dob': (77, 7), 'gender': (81, 7),  'handedness': (82, 7), 'exercise': (83, 7), 'education': (84, 7), 'work_status': (85, 7), 'panic': (132, 7), 'agoraphobia': (134, 7), 'social_anx': (135, 7), 'ocd': (137, 7), 'ptsd': (140, 7), 'gad': (141, 7), 'comorbid_anx': (142, 7), 'msm': (120, 7), 'psi_sociotropy': (151, 7), 'psi_autonomy': (152, 7), 'raads': (155, 7), 'panas_pos_vis_1': (161, 7), 'panas_neg_vis_1': (162, 7), 'qids_vis_1': (172, 7), 'gad_vis_1': (173, 7), 'rosenberg_vis_1': (174, 7), 'madrs_vis_1': (185, 7)},
        'P020_vis_2_locations': {'pre_memory_intensity_guilt_1': (38, 6), 'pre_memory_intensity_guilt_2': (43, 6), 'pre_memory_intensity_indignation_1': (49, 6), 'pre_memory_intensity_indignation_2': (54, 6), 'intervention': (78, 6), 'techniques_guilt': (84, 6), 'techniques_indignation': (85, 6), 'perceived_success_guilt': (86, 6), 'perceived_success_indignation': (87, 6), 'post_memory_intensity_guilt_1': (88, 6), 'post_memory_intensity_guilt 2': (92, 6), 'post_memory_intensity_indignation_1': (97, 6), 'post_memory_indignation_2': (101, 6), 'rosenberg_vis_2': (104, 6)},
        'P020_vis_3_locations': {'panas_pos_vis_3': (36, 6), 'panas_neg_vis_3': (37, 6), 'qids_vis_3': (47, 6), 'gad_vis_3': (48, 6), 'rosenberg_vis_3': (49, 6), 'madrs_vis_3': (60, 6)},
    
        'P030_vis_1_locations': {'dob': (77, 6), 'gender': (81, 6),  'handedness': (82, 6), 'exercise': (83, 6), 'education': (84, 6), 'work_status': (85, 6), 'panic': (132, 6), 'agoraphobia': (134, 6), 'social_anx': (135, 6), 'ocd': (137, 6), 'ptsd': (140, 6), 'gad': (141, 6), 'comorbid_anx': (142, 6), 'msm': (120, 6), 'psi_sociotropy': (151, 6), 'psi_autonomy': (152, 6), 'raads': (155, 6), 'panas_pos_vis_1': (161, 6), 'panas_neg_vis_1': (162, 6), 'qids_vis_1': (172, 6), 'gad_vis_1': (173, 6), 'rosenberg_vis_1': (174, 6), 'madrs_vis_1': (185, 6)},
        'P030_vis_2_locations': {'pre_memory_intensity_guilt_1': (38, 5), 'pre_memory_intensity_guilt_2': (43, 5), 'pre_memory_intensity_indignation_1': (49, 5), 'pre_memory_intensity_indignation_2': (54, 5), 'intervention': (78, 5), 'techniques_guilt': (84, 5), 'techniques_indignation': (85, 5), 'perceived_success_guilt': (86, 5), 'perceived_success_indignation': (87, 5), 'post_memory_intensity_guilt_1': (88, 5), 'post_memory_intensity_guilt 2': (92, 5), 'post_memory_intensity_indignation_1': (97, 5), 'post_memory_indignation_2': (101, 5), 'rosenberg_vis_2': (104, 5)},
        'P030_vis_3_locations': {'panas_pos_vis_3': (36, 5), 'panas_neg_vis_3': (37, 5), 'qids_vis_3': (47, 5), 'gad_vis_3': (48, 5), 'rosenberg_vis_3': (49, 5), 'madrs_vis_3': (60, 5)},
    
        'P059_vis_1_locations': {'dob': (77, 23), 'gender': (81, 23),  'handedness': (82, 23), 'exercise': (83, 23), 'education': (84, 23), 'work_status': (85, 23), 'panic': (132, 23), 'agoraphobia': (134, 23), 'social_anx': (135, 23), 'ocd': (137, 23), 'ptsd': (140, 23), 'gad': (141, 23), 'comorbid_anx': (142, 23), 'msm': (120, 23), 'psi_sociotropy': (151, 23), 'psi_autonomy': (152, 23), 'raads': (155, 23), 'panas_pos_vis_1': (161, 23), 'panas_neg_vis_1': (162, 23), 'qids_vis_1': (172, 23), 'gad_vis_1': (173, 23), 'rosenberg_vis_1': (174, 23), 'madrs_vis_1': (185, 23)},
        'P059_vis_2_locations': {'pre_memory_intensity_guilt_1': (38, 20), 'pre_memory_intensity_guilt_2': (43, 20), 'pre_memory_intensity_indignation_1': (49, 20), 'pre_memory_intensity_indignation_2': (54, 20), 'intervention': (78, 20), 'techniques_guilt': (84, 20), 'techniques_indignation': (85, 20), 'perceived_success_guilt': (86, 20), 'perceived_success_indignation': (87, 20), 'post_memory_intensity_guilt_1': (88, 20), 'post_memory_intensity_guilt 2': (92, 20), 'post_memory_intensity_indignation_1': (97, 20), 'post_memory_indignation_2': (101, 20), 'rosenberg_vis_2': (104, 20)},
        'P059_vis_3_locations': {'panas_pos_vis_3': (36, 19), 'panas_neg_vis_3': (37, 19), 'qids_vis_3': (47, 19), 'gad_vis_3': (48, 19), 'rosenberg_vis_3': (49, 19), 'madrs_vis_3': (60, 19)},
    
        'P078_vis_1_locations': {'dob': (77, 9), 'gender': (81, 9),  'handedness': (82, 9), 'exercise': (83, 9), 'education': (84, 9), 'work_status': (85, 9), 'panic': (132, 9), 'agoraphobia': (134, 9), 'social_anx': (135, 9), 'ocd': (137, 9), 'ptsd': (140, 9), 'gad': (141, 9), 'comorbid_anx': (142, 9), 'msm': (120, 9), 'psi_sociotropy': (151, 9), 'psi_autonomy': (152, 9), 'raads': (155, 9), 'panas_pos_vis_1': (161, 9), 'panas_neg_vis_1': (162, 9), 'qids_vis_1': (172, 9), 'gad_vis_1': (173, 9), 'rosenberg_vis_1': (174, 9), 'madrs_vis_1': (185, 9)},
        'P078_vis_2_locations': {'pre_memory_intensity_guilt_1': (38, 7), 'pre_memory_intensity_guilt_2': (43, 7), 'pre_memory_intensity_indignation_1': (49, 7), 'pre_memory_intensity_indignation_2': (54, 7), 'intervention': (78, 7), 'techniques_guilt': (84, 7), 'techniques_indignation': (85, 7), 'perceived_success_guilt': (86, 7), 'perceived_success_indignation': (87, 7), 'post_memory_intensity_guilt_1': (88, 7), 'post_memory_intensity_guilt 2': (92, 7), 'post_memory_intensity_indignation_1': (97, 7), 'post_memory_indignation_2': (101, 7), 'rosenberg_vis_2': (104, 7)},
        'P078_vis_3_locations': {'panas_pos_vis_3': (36, 7), 'panas_neg_vis_3': (37, 7), 'qids_vis_3': (47, 7), 'gad_vis_3': (48, 7), 'rosenberg_vis_3': (49, 7), 'madrs_vis_3': (60, 7)},
    
        'P093_vis_1_locations': {'dob': (77, 11), 'gender': (81, 11),  'handedness': (82, 11), 'exercise': (83, 11), 'education': (84, 11), 'work_status': (85, 11), 'panic': (132, 11), 'agoraphobia': (134, 11), 'social_anx': (135, 11), 'ocd': (137, 11), 'ptsd': (140, 11), 'gad': (141, 11), 'comorbid_anx': (142, 11), 'msm': (120, 11), 'psi_sociotropy': (151, 11), 'psi_autonomy': (152, 11), 'raads': (155, 11), 'panas_pos_vis_1': (161, 11), 'panas_neg_vis_1': (162, 11), 'qids_vis_1': (172, 11), 'gad_vis_1': (173, 11), 'rosenberg_vis_1': (174, 11), 'madrs_vis_1': (185, 11)},
        'P093_vis_2_locations': {'pre_memory_intensity_guilt_1': (38, 8), 'pre_memory_intensity_guilt_2': (43, 8), 'pre_memory_intensity_indignation_1': (49, 8), 'pre_memory_intensity_indignation_2': (54, 8), 'intervention': (78, 8), 'techniques_guilt': (84, 8), 'techniques_indignation': (85, 8), 'perceived_success_guilt': (86, 8), 'perceived_success_indignation': (87, 8), 'post_memory_intensity_guilt_1': (88, 8), 'post_memory_intensity_guilt 2': (92, 8), 'post_memory_intensity_indignation_1': (97, 8), 'post_memory_indignation_2': (101, 8), 'rosenberg_vis_2': (104, 8)},
        'P093_vis_3_locations': {'panas_pos_vis_3': (36, 8), 'panas_neg_vis_3': (37, 8), 'qids_vis_3': (47, 8), 'gad_vis_3': (48, 8), 'rosenberg_vis_3': (49, 8), 'madrs_vis_3': (60, 8)},
    
        'P094_vis_1_locations': {'dob': (77, 12), 'gender': (81, 12),  'handedness': (82, 12), 'exercise': (83, 12), 'education': (84, 12), 'work_status': (85, 12), 'panic': (132, 12), 'agoraphobia': (134, 12), 'social_anx': (135, 12), 'ocd': (137, 12), 'ptsd': (140, 12), 'gad': (141, 12), 'comorbid_anx': (142, 12), 'msm': (120, 12), 'psi_sociotropy': (151, 12), 'psi_autonomy': (152, 12), 'raads': (155, 12), 'panas_pos_vis_1': (161, 12), 'panas_neg_vis_1': (162, 12), 'qids_vis_1': (172, 12), 'gad_vis_1': (173, 12), 'rosenberg_vis_1': (174, 12), 'madrs_vis_1': (185, 12)},
        'P094_vis_2_locations': {'pre_memory_intensity_guilt_1': (38, 9), 'pre_memory_intensity_guilt_2': (43, 9), 'pre_memory_intensity_indignation_1': (49, 9), 'pre_memory_intensity_indignation_2': (54, 9), 'intervention': (78, 9), 'techniques_guilt': (84, 9), 'techniques_indignation': (85, 9), 'perceived_success_guilt': (86, 9), 'perceived_success_indignation': (87, 9), 'post_memory_intensity_guilt_1': (88, 9), 'post_memory_intensity_guilt 2': (92, 9), 'post_memory_intensity_indignation_1': (97, 9), 'post_memory_indignation_2': (101, 9), 'rosenberg_vis_2': (104, 9)},
        'P094_vis_3_locations': {'panas_pos_vis_3': (36, 9), 'panas_neg_vis_3': (37, 9), 'qids_vis_3': (47, 9), 'gad_vis_3': (48, 9), 'rosenberg_vis_3': (49, 9), 'madrs_vis_3': (60, 9)},
    
        'P100_vis_1_locations': {'dob': (77, 13), 'gender': (81, 13),  'handedness': (82, 13), 'exercise': (83, 13), 'education': (84, 13), 'work_status': (85, 13), 'panic': (132, 13), 'agoraphobia': (134, 13), 'social_anx': (135, 13), 'ocd': (137, 13), 'ptsd': (140, 13), 'gad': (141, 13), 'comorbid_anx': (142, 13), 'msm': (120, 13), 'psi_sociotropy': (151, 13), 'psi_autonomy': (152, 13), 'raads': (155, 13), 'panas_pos_vis_1': (161, 13), 'panas_neg_vis_1': (162, 13), 'qids_vis_1': (172, 13), 'gad_vis_1': (173, 13), 'rosenberg_vis_1': (174, 13), 'madrs_vis_1': (185, 13)},
        'P100_vis_2_locations': {'pre_memory_intensity_guilt_1': (38, 10), 'pre_memory_intensity_guilt_2': (43, 10), 'pre_memory_intensity_indignation_1': (49, 10), 'pre_memory_intensity_indignation_2': (54, 10), 'intervention': (78, 10), 'techniques_guilt': (84, 10), 'techniques_indignation': (85, 10), 'perceived_success_guilt': (86, 10), 'perceived_success_indignation': (87, 10), 'post_memory_intensity_guilt_1': (88, 10), 'post_memory_intensity_guilt 2': (92, 10), 'post_memory_intensity_indignation_1': (97, 10), 'post_memory_indignation_2': (101, 10), 'rosenberg_vis_2': (104, 10)},
        'P100_vis_3_locations': {'panas_pos_vis_3': (36, 10), 'panas_neg_vis_3': (37, 10), 'qids_vis_3': (47, 10), 'gad_vis_3': (48, 10), 'rosenberg_vis_3': (49, 10), 'madrs_vis_3': (60, 10)},
    
        'P107_vis_1_locations': {'dob': (77, 14), 'gender': (81, 14),  'handedness': (82, 14), 'exercise': (83, 14), 'education': (84, 14), 'work_status': (85, 14), 'panic': (132, 14), 'agoraphobia': (134, 14), 'social_anx': (135, 14), 'ocd': (137, 14), 'ptsd': (140, 14), 'gad': (141, 14), 'comorbid_anx': (142, 14), 'msm': (120, 14), 'psi_sociotropy': (151, 14), 'psi_autonomy': (152, 14), 'raads': (155, 14), 'panas_pos_vis_1': (161, 14), 'panas_neg_vis_1': (162, 14), 'qids_vis_1': (172, 14), 'gad_vis_1': (173, 14), 'rosenberg_vis_1': (174, 14), 'madrs_vis_1': (185, 14)},
        'P107_vis_2_locations': {'pre_memory_intensity_guilt_1': (38, 11), 'pre_memory_intensity_guilt_2': (43, 11), 'pre_memory_intensity_indignation_1': (49, 11), 'pre_memory_intensity_indignation_2': (54, 11), 'intervention': (78, 11), 'techniques_guilt': (84, 11), 'techniques_indignation': (85, 11), 'perceived_success_guilt': (86, 11), 'perceived_success_indignation': (87, 11), 'post_memory_intensity_guilt_1': (88, 11), 'post_memory_intensity_guilt 2': (92, 11), 'post_memory_intensity_indignation_1': (97, 11), 'post_memory_indignation_2': (101, 11), 'rosenberg_vis_2': (104, 11)},
        'P107_vis_3_locations': {'panas_pos_vis_3': (36, 11), 'panas_neg_vis_3': (37, 11), 'qids_vis_3': (47, 11), 'gad_vis_3': (48, 11), 'rosenberg_vis_3': (49, 11), 'madrs_vis_3': (60, 11)},
    
        'P122_vis_1_locations': {'dob': (77, 17), 'gender': (81, 17),  'handedness': (82, 17), 'exercise': (83, 17), 'education': (84, 17), 'work_status': (85, 17), 'panic': (132, 17), 'agoraphobia': (134, 17), 'social_anx': (135, 17), 'ocd': (137, 17), 'ptsd': (140, 17), 'gad': (141, 17), 'comorbid_anx': (142, 17), 'msm': (120, 17), 'psi_sociotropy': (151, 17), 'psi_autonomy': (152, 17), 'raads': (155, 17), 'panas_pos_vis_1': (161, 17), 'panas_neg_vis_1': (162, 17), 'qids_vis_1': (172, 17), 'gad_vis_1': (173, 17), 'rosenberg_vis_1': (174, 17), 'madrs_vis_1': (185, 17)},
        'P122_vis_2_locations': {'pre_memory_intensity_guilt_1': (38, 14), 'pre_memory_intensity_guilt_2': (43, 14), 'pre_memory_intensity_indignation_1': (49, 14), 'pre_memory_intensity_indignation_2': (54, 14), 'intervention': (78, 14), 'techniques_guilt': (84, 14), 'techniques_indignation': (85, 14), 'perceived_success_guilt': (86, 14), 'perceived_success_indignation': (87, 14), 'post_memory_intensity_guilt_1': (88, 14), 'post_memory_intensity_guilt 2': (92, 14), 'post_memory_intensity_indignation_1': (97, 14), 'post_memory_indignation_2': (101, 14), 'rosenberg_vis_2': (104, 14)},
        'P122_vis_3_locations': {'panas_pos_vis_3': (36, 14), 'panas_neg_vis_3': (37, 14), 'qids_vis_3': (47, 14), 'gad_vis_3': (48, 14), 'rosenberg_vis_3': (49, 14), 'madrs_vis_3': (60, 14)},
    
        'P125_vis_1_locations': {'dob': (77, 18), 'gender': (81, 18),  'handedness': (82, 18), 'exercise': (83, 18), 'education': (84, 18), 'work_status': (85, 18), 'panic': (132, 18), 'agoraphobia': (134, 18), 'social_anx': (135, 18), 'ocd': (137, 18), 'ptsd': (140, 18), 'gad': (141, 18), 'comorbid_anx': (142, 18), 'msm': (120, 18), 'psi_sociotropy': (151, 18), 'psi_autonomy': (152, 18), 'raads': (155, 18), 'panas_pos_vis_1': (161, 18), 'panas_neg_vis_1': (162, 18), 'qids_vis_1': (172, 18), 'gad_vis_1': (173, 18), 'rosenberg_vis_1': (174, 18), 'madrs_vis_1': (185, 18)},
        'P125_vis_2_locations': {'pre_memory_intensity_guilt_1': (38, 15), 'pre_memory_intensity_guilt_2': (43, 15), 'pre_memory_intensity_indignation_1': (49, 15), 'pre_memory_intensity_indignation_2': (54, 15), 'intervention': (78, 15), 'techniques_guilt': (84, 15), 'techniques_indignation': (85, 15), 'perceived_success_guilt': (86, 15), 'perceived_success_indignation': (87, 15), 'post_memory_intensity_guilt_1': (88, 15), 'post_memory_intensity_guilt 2': (92, 15), 'post_memory_intensity_indignation_1': (97, 15), 'post_memory_indignation_2': (101, 15), 'rosenberg_vis_2': (104, 15)},
        'P125_vis_3_locations': {'panas_pos_vis_3': (36, 15), 'panas_neg_vis_3': (37, 15), 'qids_vis_3': (47, 15), 'gad_vis_3': (48, 15), 'rosenberg_vis_3': (49, 15), 'madrs_vis_3': (60, 15)},
    
        'P127_vis_1_locations': {'dob': (77, 16), 'gender': (81, 16),  'handedness': (82, 16), 'exercise': (83, 16), 'education': (84, 16), 'work_status': (85, 16), 'panic': (132, 16), 'agoraphobia': (134, 16), 'social_anx': (135, 16), 'ocd': (137, 16), 'ptsd': (140, 16), 'gad': (141, 16), 'comorbid_anx': (142, 16), 'msm': (120, 16), 'psi_sociotropy': (151, 16), 'psi_autonomy': (152, 16), 'raads': (155, 16), 'panas_pos_vis_1': (161, 16), 'panas_neg_vis_1': (162, 16), 'qids_vis_1': (172, 16), 'gad_vis_1': (173, 16), 'rosenberg_vis_1': (174, 16), 'madrs_vis_1': (185, 16)},
        'P127_vis_2_locations': {'pre_memory_intensity_guilt_1': (38, 13), 'pre_memory_intensity_guilt_2': (43, 13), 'pre_memory_intensity_indignation_1': (49, 13), 'pre_memory_intensity_indignation_2': (54, 13), 'intervention': (78, 13), 'techniques_guilt': (84, 13), 'techniques_indignation': (85, 13), 'perceived_success_guilt': (86, 13), 'perceived_success_indignation': (87, 13), 'post_memory_intensity_guilt_1': (88, 13), 'post_memory_intensity_guilt 2': (92, 13), 'post_memory_intensity_indignation_1': (97, 13), 'post_memory_indignation_2': (101, 13), 'rosenberg_vis_2': (104, 13)},
        'P127_vis_3_locations': {'panas_pos_vis_3': (36, 13), 'panas_neg_vis_3': (37, 13), 'qids_vis_3': (47, 13), 'gad_vis_3': (48, 13), 'rosenberg_vis_3': (49, 13), 'madrs_vis_3': (60, 13)},
   
        'P128_vis_1_locations': {'dob': (77, 15), 'gender': (81, 15),  'handedness': (82, 15), 'exercise': (83, 15), 'education': (84, 15), 'work_status': (85, 15), 'panic': (132, 15), 'agoraphobia': (134, 15), 'social_anx': (135, 15), 'ocd': (137, 15), 'ptsd': (140, 15), 'gad': (141, 15), 'comorbid_anx': (142, 15), 'msm': (120, 15), 'psi_sociotropy': (151, 15), 'psi_autonomy': (152, 15), 'raads': (155, 15), 'panas_pos_vis_1': (161, 15), 'panas_neg_vis_1': (162, 15), 'qids_vis_1': (172, 15), 'gad_vis_1': (173, 15), 'rosenberg_vis_1': (174, 15), 'madrs_vis_1': (185, 15)},
        'P128_vis_2_locations': {'pre_memory_intensity_guilt_1': (38, 12), 'pre_memory_intensity_guilt_2': (43, 12), 'pre_memory_intensity_indignation_1': (49, 12), 'pre_memory_intensity_indignation_2': (54, 12), 'intervention': (78, 12), 'techniques_guilt': (84, 12), 'techniques_indignation': (85, 12), 'perceived_success_guilt': (86, 12), 'perceived_success_indignation': (87, 12), 'post_memory_intensity_guilt_1': (88, 12), 'post_memory_intensity_guilt 2': (92, 12), 'post_memory_intensity_indignation_1': (97, 12), 'post_memory_indignation_2': (101, 12), 'rosenberg_vis_2': (104, 12)},
        'P128_vis_3_locations': {'panas_pos_vis_3': (36, 12), 'panas_neg_vis_3': (37, 12), 'qids_vis_3': (47, 12), 'gad_vis_3': (48, 12), 'rosenberg_vis_3': (49, 12), 'madrs_vis_3': (60, 12)},
    
        'P136_vis_1_locations': {'dob': (77, 19), 'gender': (81, 19),  'handedness': (82, 19), 'exercise': (83, 19), 'education': (84, 19), 'work_status': (85, 19), 'panic': (132, 19), 'agoraphobia': (134, 19), 'social_anx': (135, 19), 'ocd': (137, 19), 'ptsd': (140, 19), 'gad': (141, 19), 'comorbid_anx': (142, 19), 'msm': (120, 19), 'psi_sociotropy': (151, 19), 'psi_autonomy': (152, 19), 'raads': (155, 19), 'panas_pos_vis_1': (161, 19), 'panas_neg_vis_1': (162, 19), 'qids_vis_1': (172, 19), 'gad_vis_1': (173, 19), 'rosenberg_vis_1': (174, 19), 'madrs_vis_1': (185, 19)},
        'P136_vis_2_locations': {'pre_memory_intensity_guilt_1': (38, 16), 'pre_memory_intensity_guilt_2': (43, 16), 'pre_memory_intensity_indignation_1': (49, 16), 'pre_memory_intensity_indignation_2': (54, 16), 'intervention': (78, 16), 'techniques_guilt': (84, 16), 'techniques_indignation': (85, 16), 'perceived_success_guilt': (86, 16), 'perceived_success_indignation': (87, 16), 'post_memory_intensity_guilt_1': (88, 16), 'post_memory_intensity_guilt 2': (92, 16), 'post_memory_intensity_indignation_1': (97, 16), 'post_memory_indignation_2': (101, 16), 'rosenberg_vis_2': (104, 16)},
        'P136_vis_3_locations': {'panas_pos_vis_3': (36, 16), 'panas_neg_vis_3': (37, 16), 'qids_vis_3': (47, 16), 'gad_vis_3': (48, 16), 'rosenberg_vis_3': (49, 16), 'madrs_vis_3': (60, 16)},
    
        'P145_vis_1_locations': {'dob': (77, 21), 'gender': (81, 21),  'handedness': (82, 21), 'exercise': (83, 21), 'education': (84, 21), 'work_status': (85, 21), 'panic': (132, 21), 'agoraphobia': (134, 21), 'social_anx': (135, 21), 'ocd': (137, 21), 'ptsd': (140, 21), 'gad': (141, 21), 'comorbid_anx': (142, 21), 'msm': (120, 21), 'psi_sociotropy': (151, 21), 'psi_autonomy': (152, 21), 'raads': (155, 21), 'panas_pos_vis_1': (161, 21), 'panas_neg_vis_1': (162, 21), 'qids_vis_1': (172, 21), 'gad_vis_1': (173, 21), 'rosenberg_vis_1': (174, 21), 'madrs_vis_1': (185, 21)},
        'P145_vis_2_locations': {'pre_memory_intensity_guilt_1': (38, 18), 'pre_memory_intensity_guilt_2': (43, 18), 'pre_memory_intensity_indignation_1': (49, 18), 'pre_memory_intensity_indignation_2': (54, 18), 'intervention': (78, 18), 'techniques_guilt': (84, 18), 'techniques_indignation': (85, 18), 'perceived_success_guilt': (86, 18), 'perceived_success_indignation': (87, 18), 'post_memory_intensity_guilt_1': (88, 18), 'post_memory_intensity_guilt 2': (92, 18), 'post_memory_intensity_indignation_1': (97, 18), 'post_memory_indignation_2': (101, 18), 'rosenberg_vis_2': (104, 18)},
        'P145_vis_3_locations': {'panas_pos_vis_3': (36, 17), 'panas_neg_vis_3': (37, 17), 'qids_vis_3': (47, 17), 'gad_vis_3': (48, 17), 'rosenberg_vis_3': (49, 17), 'madrs_vis_3': (60, 17)},
    
        'P155_vis_1_locations': {'dob': (77, 22), 'gender': (81, 22),  'handedness': (82, 22), 'exercise': (83, 22), 'education': (84, 22), 'work_status': (85, 22), 'panic': (132, 22), 'agoraphobia': (134, 22), 'social_anx': (135, 22), 'ocd': (137, 22), 'ptsd': (140, 22), 'gad': (141, 22), 'comorbid_anx': (142, 22), 'msm': (120, 22), 'psi_sociotropy': (151, 22), 'psi_autonomy': (152, 22), 'raads': (155, 22), 'panas_pos_vis_1': (161, 22), 'panas_neg_vis_1': (162, 22), 'qids_vis_1': (172, 22), 'gad_vis_1': (173, 22), 'rosenberg_vis_1': (174, 22), 'madrs_vis_1': (185, 22)},
        'P155_vis_2_locations': {'pre_memory_intensity_guilt_1': (38, 19), 'pre_memory_intensity_guilt_2': (43, 19), 'pre_memory_intensity_indignation_1': (49, 19), 'pre_memory_intensity_indignation_2': (54, 19), 'intervention': (78, 19), 'techniques_guilt': (84, 19), 'techniques_indignation': (85, 19), 'perceived_success_guilt': (86, 19), 'perceived_success_indignation': (87, 19), 'post_memory_intensity_guilt_1': (88, 19), 'post_memory_intensity_guilt 2': (92, 19), 'post_memory_intensity_indignation_1': (97, 19), 'post_memory_indignation_2': (101, 19), 'rosenberg_vis_2': (104, 19)},
        'P155_vis_3_locations': {'panas_pos_vis_3': (36, 18), 'panas_neg_vis_3': (37, 18), 'qids_vis_3': (47, 18), 'gad_vis_3': (48, 18), 'rosenberg_vis_3': (49, 18), 'madrs_vis_3': (60, 18)},
    
        'P199_vis_1_locations': {'dob': (77, 27), 'gender': (81, 27),  'handedness': (82, 27), 'exercise': (83, 27), 'education': (84, 27), 'work_status': (85, 27), 'panic': (132, 27), 'agoraphobia': (134, 27), 'social_anx': (135, 27), 'ocd': (137, 27), 'ptsd': (140, 27), 'gad': (141, 27), 'comorbid_anx': (142, 27), 'msm': (120, 27), 'psi_sociotropy': (151, 27), 'psi_autonomy': (152, 27), 'raads': (155, 27), 'panas_pos_vis_1': (161, 27), 'panas_neg_vis_1': (162, 27), 'qids_vis_1': (172, 27), 'gad_vis_1': (173, 27), 'rosenberg_vis_1': (174, 27), 'madrs_vis_1': (185, 27)},
        'P199_vis_2_locations': {'pre_memory_intensity_guilt_1': (38, 22), 'pre_memory_intensity_guilt_2': (43, 22), 'pre_memory_intensity_indignation_1': (49, 22), 'pre_memory_intensity_indignation_2': (54, 22), 'intervention': (78, 22), 'techniques_guilt': (84, 22), 'techniques_indignation': (85, 22), 'perceived_success_guilt': (86, 22), 'perceived_success_indignation': (87, 22), 'post_memory_intensity_guilt_1': (88, 22), 'post_memory_intensity_guilt 2': (92, 22), 'post_memory_intensity_indignation_1': (97, 22), 'post_memory_indignation_2': (101, 22), 'rosenberg_vis_2': (104, 22)},
        'P199_vis_3_locations': {'panas_pos_vis_3': (36, 21), 'panas_neg_vis_3': (37, 21), 'qids_vis_3': (47, 21), 'gad_vis_3': (48, 21), 'rosenberg_vis_3': (49, 21), 'madrs_vis_3': (60, 21)},

        'P215_vis_1_locations': {'dob': (77, 26), 'gender': (81, 26),  'handedness': (82, 26), 'exercise': (83, 26), 'education': (84, 26), 'work_status': (85, 26), 'panic': (132, 26), 'agoraphobia': (134, 26), 'social_anx': (135, 26), 'ocd': (137, 26), 'ptsd': (140, 26), 'gad': (141, 26), 'comorbid_anx': (142, 26), 'msm': (120, 26), 'psi_sociotropy': (151, 26), 'psi_autonomy': (152, 26), 'raads': (155, 26), 'panas_pos_vis_1': (161, 26), 'panas_neg_vis_1': (162, 26), 'qids_vis_1': (172, 26), 'gad_vis_1': (173, 26), 'rosenberg_vis_1': (174, 26), 'madrs_vis_1': (185, 26)},
        'P215_vis_2_locations': {'pre_memory_intensity_guilt_1': (38, 21), 'pre_memory_intensity_guilt_2': (43, 21), 'pre_memory_intensity_indignation_1': (49, 21), 'pre_memory_intensity_indignation_2': (54, 21), 'intervention': (78, 21), 'techniques_guilt': (84, 21), 'techniques_indignation': (85, 21), 'perceived_success_guilt': (86, 21), 'perceived_success_indignation': (87, 21), 'post_memory_intensity_guilt_1': (88, 21), 'post_memory_intensity_guilt 2': (92, 21), 'post_memory_intensity_indignation_1': (97, 21), 'post_memory_indignation_2': (101, 21), 'rosenberg_vis_2': (104, 21)},
        'P215_vis_3_locations': {'panas_pos_vis_3': (36, 20), 'panas_neg_vis_3': (37, 20), 'qids_vis_3': (47, 20), 'gad_vis_3': (48, 20), 'rosenberg_vis_3': (49, 20), 'madrs_vis_3': (60, 20)},

        'P216_vis_1_locations': {'dob': (77, 28), 'gender': (81, 28),  'handedness': (82, 28), 'exercise': (83, 28), 'education': (84, 28), 'work_status': (85, 28), 'panic': (132, 28), 'agoraphobia': (134, 28), 'social_anx': (135, 28), 'ocd': (137, 28), 'ptsd': (140, 28), 'gad': (141, 28), 'comorbid_anx': (142, 28), 'msm': (120, 28), 'psi_sociotropy': (151, 28), 'psi_autonomy': (152, 28), 'raads': (155, 28), 'panas_pos_vis_1': (161, 28), 'panas_neg_vis_1': (162, 28), 'qids_vis_1': (172, 28), 'gad_vis_1': (173, 28), 'rosenberg_vis_1': (174, 28), 'madrs_vis_1': (185, 28)},
        'P216_vis_2_locations': {'pre_memory_intensity_guilt_1': (38, 23), 'pre_memory_intensity_guilt_2': (43, 23), 'pre_memory_intensity_indignation_1': (49, 23), 'pre_memory_intensity_indignation_2': (54, 23), 'intervention': (78, 23), 'techniques_guilt': (84, 23), 'techniques_indignation': (85, 23), 'perceived_success_guilt': (86, 23), 'perceived_success_indignation': (87, 23), 'post_memory_intensity_guilt_1': (88, 23), 'post_memory_intensity_guilt 2': (92, 23), 'post_memory_intensity_indignation_1': (97, 23), 'post_memory_indignation_2': (101, 23), 'rosenberg_vis_2': (104, 23)},
        'P216_vis_3_locations': {'panas_pos_vis_3': (36, 22), 'panas_neg_vis_3': (37, 22), 'qids_vis_3': (47, 22), 'gad_vis_3': (48, 22), 'rosenberg_vis_3': (49, 22), 'madrs_vis_3': (60, 22)}
    }
    for x in participants:
        print(f'Extracting {x} data from eCRF.xlsx.')
        decrypted_workbook = io.BytesIO()
        with open(ecrf_file_path, 'rb') as file:
            office_file = msoffcrypto.OfficeFile(file)
            office_file.load_key(password=password)
            office_file.decrypt(decrypted_workbook)
        workbook = openpyxl.load_workbook(decrypted_workbook, data_only = True)
        ecrf_sheet = workbook['Visit 1']
        vis_1_values = [ecrf_sheet.cell(row=row, column=column).value for (row, column) in location_dict[f'{x}_vis_1_locations'].values()]
        ecrf_sheet = workbook['Visit 2']
        vis_2_values = [ecrf_sheet.cell(row=row, column=column).value for (row, column) in location_dict[f'{x}_vis_2_locations'].values()]
        ecrf_sheet = workbook['Visit 3']
        vis_3_values = [ecrf_sheet.cell(row=row, column=column).value for (row, column) in location_dict[f'{x}_vis_3_locations'].values()]
        df_values_dict[f'{x}'] = vis_1_values + vis_2_values + vis_3_values
        for key, values in df_values_dict.items():
            data_df[key] = values
        output_excel_path = '/its/home/bsms9pc4/Desktop/cisc2/projects/stone_depnf/Neurofeedback/participant_data/group/ecrf_data.xlsx'
        data_df.to_excel(output_excel_path, index=True)
        print(f'{x} data from eCRF.xlsx successfully extracted.')
        workbook.close()
    warnings.resetwarnings()

    # Step 3: Calculate and plot thermometer movement success for each participant. 

    
    # Could the participants move the thermometer?
    # How did this differ between guilt and indignation tasks?
    # How did this differ between the two intervention groups?
    # Did it vary based on any demographic or clinical factors?
    # Did their actual success correlate with perceived success?
    # Does thermometer movement success change between run 2 and run 3? i.e. Do participants reach somewhat of a breakthrough moment?
    # Try different metrics for thermometer movement success (e.g. mean level, median level, level stability, level stability + mean / median level). Can also include a threshold for successful movement which is based on the movement of the thermometer if left to chance(?). Maybe favour mean over median because it is not possible to have major outliers in the data (the thermometer level can only be between 0 and 10).
    # Can also try: number of volumes where thermometer level was above 5. Or plot histogram of the frequency of different thermometer levels. Can include levels that are also outside of the thermometer range, and have these values in a slightly more faded colour.
    # Find amount of time that participant spent above or below thermometer range to test whether thermometer range was suitable.
    # Does thermometer movement success vary in accordance with memory intensity?
    # Test if MeanSignal stabilises each time during rest blocks.
    # Clearly define MeanSignal, Baseline, Value, Thermometer Level etc from tbv_script text file.
    # Calculate the average number of blocks that the thermometer goes up or down each volume, in order to ascertain how erratically or stably the thermometer is moving. 
    # Could create a heatmap overlayed onto the thermometer in order to provide a visual demonstration of the thermometer levels that were most frequently occupied.
    # How well does thermometer success correlate with the different techniques used. Can try to classify the qualitative reports into several categories of techniques.
    # Does perceived success correlate with any demographic or clinical factors?
    # Does actual or perceived success correlate with improvements in self-esteem / depression ratings?
    # If you have high success with guilt thermometer, does that predict low success with indignation thermometer, and vice versa. I.e. is it difficult to be good at moving thermometer under both conditions, or is one condition always favoured.



#endregion

#region SUSCEPTIBILITY ANALYSIS.

answer5 = input("Would you like to execute susceptibility artifact analysis? (y/n)\n")
if answer5 == 'y':
    p_id = input("Enter the participant's ID (e.g. P001). If you want to analyse all participants simultaneously, enter 'ALL'.\n")
    participants = ['P004', 'P006', 'P020', 'P030', 'P059', 'P078', 'P093', 'P094', 'P100', 'P107', 'P122', 'P125', 'P127', 'P128', 'P136', 'P145', 'P155', 'P199', 'P215', 'P216']
    runs = ['run01', 'run02', 'run03', 'run04']
    if p_id == 'ALL':
        participants_to_iterate = participants
    else:
        participants_to_iterate = [p_id]
    restart = input("Would you like to start the preprocessing from scratch for the selected participant(s)? This will remove all files from the 'p_id/analysis/susceptibility' and 'group' folders associated with them. (y/n)\n")
    if restart == 'y':
        double_check = input("Are you sure? (y/n)\n")
        if double_check == 'y':
            for p_id in participants_to_iterate:
                susceptibility_folder = os.path.join(os.getcwd(), p_id, 'analysis', 'susceptibility')
                if os.path.exists(susceptibility_folder):
                    print(f"Deleting {p_id} susceptibility folder...")
                    shutil.rmtree(susceptibility_folder)
                    print(f"{p_id} susceptibility folder successfully deleted.")
                else:
                    print(f"{p_id} susceptibility folder does not exist.")
                group_susceptibility_folder = os.path.join(os.getcwd(), 'group', 'susceptibility')
            if os.path.exists(group_susceptibility_folder):
                print(f"Deleting {p_id} group/susceptibility folder...")
                shutil.rmtree(group_susceptibility_folder)
                print(f"{p_id} group/susceptibility folder successfully deleted.")
            else:
                print(f"{p_id} group/susceptibility folder does not exist.")
        else:
            sys.exit()

    # Step 1: Create directories.
    print("\n###### STEP 1: CREATE DIRECTORIES ######")
    for p_id in participants_to_iterate:
        p_id_folder = os.path.join(os.getcwd(), p_id)
        os.makedirs(p_id_folder, exist_ok=True)
        analysis_folder = os.path.join(os.getcwd(), p_id, 'analysis')
        os.makedirs(analysis_folder, exist_ok=True)
        susceptibility_folder = os.path.join(os.getcwd(), p_id, 'analysis', 'susceptibility')
        os.makedirs(susceptibility_folder, exist_ok=True)
        nifti_folder = os.path.join(os.getcwd(), p_id, 'analysis', 'susceptibility', 'niftis')
        os.makedirs(nifti_folder, exist_ok=True)
        fnirt_folder = os.path.join(os.getcwd(), p_id, "analysis", "susceptibility", "fnirt_test")
        os.makedirs(fnirt_folder, exist_ok=True)
        fnirt_folder_1 = os.path.join(os.getcwd(), p_id, "analysis", "susceptibility", "fnirt_test", "1")
        os.makedirs(fnirt_folder_1, exist_ok=True)
        fnirt_folder_2 = os.path.join(os.getcwd(), p_id, "analysis", "susceptibility", "fnirt_test", "2")
        os.makedirs(fnirt_folder_2, exist_ok=True)
        fnirt_folder_3 = os.path.join(os.getcwd(), p_id, "analysis", "susceptibility", "fnirt_test", "3")
        os.makedirs(fnirt_folder_3, exist_ok=True)
        group_folder = os.path.join(os.getcwd(), p_id, "analysis", "susceptibility", "group")
        os.makedirs(group_folder, exist_ok=True)
        group_fnirt_folder = os.path.join(os.getcwd(), p_id, "analysis", "susceptibility", "group", "fnirt_test")
        os.makedirs(group_fnirt_folder, exist_ok=True)
        group_fnirt_folder_1 = os.path.join(os.getcwd(), 'group', 'susceptibility', 'fnirt_test', '1')
        os.makedirs(group_fnirt_folder_1, exist_ok=True)
        group_fnirt_folder_2 = os.path.join(os.getcwd(), 'group', 'susceptibility', 'fnirt_test', '2')
        os.makedirs(group_fnirt_folder_2, exist_ok=True)
        group_fnirt_folder_3 = os.path.join(os.getcwd(), 'group', 'susceptibility', 'fnirt_test', '3')
        os.makedirs(group_fnirt_folder_3, exist_ok=True)
    print('Directories created.')

    # Step 2: Calculate percentage of ROI voxels outside the brain during neurofeedback.
    print("\n###### STEP 2: CALCULATE PERCENTAGE OF ROI VOXELS OUTSIDE BRAIN DURING NEUROFEEDBACK ######")
    path = os.path.join(os.getcwd(), p_id, 'data', 'neurofeedback')
    cisc_folder = None
    for folder_name in os.listdir(path):
        if "CISC" in folder_name:
            cisc_folder = folder_name
            break
    if cisc_folder is None:
        print("No 'CISC' folder found in the 'neurofeedback' directory.")
        exit(1)
    def get_sequence_numbers(file_name):
        parts = file_name.split('_')
        return int(parts[1]), int(parts[2].split('.')[0])
    def copy_files(src_folder, dest_folder, sequence_number):
        src_pattern = f'*_{sequence_number:06d}_*.dcm'
        matching_files = [f for f in os.listdir(src_folder) if fnmatch.fnmatch(f, src_pattern)]
        for file in matching_files:
            src_path = os.path.join(src_folder, file)
            dest_path = os.path.join(dest_folder, file)
            shutil.copy(src_path, dest_path)
    def main():
        src_folder = os.path.join(path, cisc_folder)
        dicoms_folder = os.path.join(os.getcwd(), p_id, 'analysis', 'susceptibility', 'dicoms')
        run01_folder = os.path.join(os.getcwd(), p_id, 'analysis', 'susceptibility', 'dicoms', 'run01_dicoms')
        run02_folder = os.path.join(os.getcwd(), p_id, 'analysis', 'susceptibility', 'dicoms', 'run02_dicoms')
        run03_folder = os.path.join(os.getcwd(), p_id, 'analysis', 'susceptibility', 'dicoms', 'run03_dicoms')
        run04_folder = os.path.join(os.getcwd(), p_id, 'analysis', 'susceptibility', 'dicoms', 'run04_dicoms')
        os.makedirs(dicoms_folder, exist_ok=True)
        os.makedirs(run01_folder, exist_ok=True)
        os.makedirs(run02_folder, exist_ok=True)
        os.makedirs(run03_folder, exist_ok=True)
        os.makedirs(run04_folder, exist_ok=True)
        files = [f for f in os.listdir(src_folder) if f.endswith('.dcm')]
        seq_vol_counts = {}
        for file in files:
            sequence_number, volume_number = get_sequence_numbers(file)
            if sequence_number not in seq_vol_counts:
                seq_vol_counts[sequence_number] = []
            seq_vol_counts[sequence_number].append(volume_number)
        seq_210 = [sequence_number for sequence_number, volume_numbers in seq_vol_counts.items() if len(volume_numbers) == 210]
        seq_238 = [sequence_number for sequence_number, volume_numbers in seq_vol_counts.items() if len(volume_numbers) == 238]
        min_210 = min(seq_210)
        max_210 = max(seq_210)
        min_238 = min(seq_238)
        max_238 = max(seq_238)
        if not os.listdir(run01_folder):
            print("Copying Run01 dicoms...")
            copy_files(src_folder, run01_folder, min_210)
            print("Run01 dicoms copied. Number of files:", str(len(os.listdir(run01_folder))) + ".", "Sequence number:", min_210)
        if not os.listdir(run02_folder):
            print("Copying Run02 dicoms...")
            copy_files(src_folder, run02_folder, min_238)
            print("Run02 dicoms copied. Number of files:", str(len(os.listdir(run02_folder))) + ".", "Sequence number:", min_238)
        if not os.listdir(run03_folder):
            print("Copying Run03 dicoms...")
            copy_files(src_folder, run03_folder, max_238)
            print("Run03 dicoms copied. Number of files:", str(len(os.listdir(run03_folder))) + ".", "Sequence number:", max_238)
        if not os.listdir(run04_folder):
            print("Copying Run04 dicoms...")
            copy_files(src_folder, run04_folder, max_210)
            print("Run04 dicoms copied. Number of files:", str(len(os.listdir(run04_folder))) + ".", "Sequence number:", max_210)
    if __name__ == "__main__":
        main()
    for run in runs:
        destination_folder = os.path.join(os.getcwd(), p_id, "analysis", "susceptibility", "dicoms", f"{run}_dicoms")
        output_folder = os.path.join(os.getcwd(), p_id, "analysis", "susceptibility", "niftis")
        output_file = os.path.join(output_folder, f"{run}.nii")
        if not os.path.exists(output_file):
            print(f"Converting {run.upper()} DICOM files to Nifti format...")
            subprocess.run(['dcm2niix', '-o', output_folder, '-f', run, '-b', 'n', destination_folder])
            print(f"{run.upper()} DICOM files converted to Nifti format.")
        else:
            print(f"{run.upper()} Nifti file already exists. Skipping conversion.")
        averaged_file = os.path.join(output_folder, f"{run}_averaged.nii.gz")
        if not os.path.exists(averaged_file):
            subprocess.run(['fslmaths', output_file, '-Tmean', averaged_file])
            print(f"{run} Nifti volumes merged successfully.")
        else:
            print(f"{run} averaged Nifti already exists. Skipping merging operation.")
    ##################################################################################### Need to do brain extraction?
    def read_roi_file(roi_file):
        voxel_coordinates = []
        with open(roi_file, 'r') as file:
            content = file.read()
            matches = re.findall(r'(?<=\n)\s*\d+\s+\d+\s+\d+', content)
            for match in matches:
                coordinates = match.split()
                voxel_coordinates.append(
                    (int(coordinates[0]), int(coordinates[1]), int(coordinates[2])))
        return voxel_coordinates
    run_num = ['1', '2', '3', '4']
    for num in run_num:
        roi_file = os.path.join(os.getcwd(), p_id, 'data', 'neurofeedback', cisc_folder, 'depression_neurofeedback', f'target_folder_run-{num}', f'depnf_run-{num}.roi')
        voxel_coordinates = read_roi_file(roi_file)
        functional_image = f'{p_id}/analysis/susceptibility/niftis/{run}_averaged.nii.gz'
        functional_image_info = nib.load(functional_image)
        functional_dims = functional_image_info.shape
        binary_volume = np.zeros(functional_dims)
        for voxel in voxel_coordinates:
            x, y, z = voxel
            binary_volume[x, y, z] = 1
        binary_volume = np.flip(binary_volume, axis=1)
        functional_affine = functional_image_info.affine
        binary_nifti = nib.Nifti1Image(binary_volume, affine=functional_affine)
        nib.save(binary_nifti, f'{p_id}/analysis/susceptibility/niftis/run0{num}_subject_space_ROI.nii.gz')
    for run in runs:
        betted_file = os.path.join(output_folder, f"{run}_averaged_betted.nii.gz")
        if not os.path.exists(betted_file):
            subprocess.run(['bet', f'{p_id}/analysis/susceptibility/niftis/{run}_averaged.nii.gz', betted_file, '-R'])
            print(f"{run} brain extraction completed.")
        else:
            print(f"{run} brain-extracted file already exists. Skipping BET operation.")
        functional_image_betted = f'{p_id}/analysis/susceptibility/niftis/{run}_averaged_betted.nii.gz'
        binary_nifti_image = f'{p_id}/analysis/susceptibility/niftis/{run}_subject_space_ROI.nii.gz'
        screenshot_file = f'{p_id}/analysis/susceptibility/ROI_on_{run}_EPI.png'
        binary_img = nib.load(binary_nifti_image)
        binary_data = binary_img.get_fdata()
        indices = np.nonzero(binary_data)
        center_x = int(np.mean(indices[0]))
        center_y = int(np.mean(indices[1]))
        center_z = int(np.mean(indices[2]))
        result = subprocess.run(['fsleyes', 'render', '--scene', 'lightbox', '--voxelLoc', f'{center_x}', f'{center_y}', f'{center_z}', '-hc', '-hl', '-of', screenshot_file, functional_image, binary_nifti_image, '-ot', 'mask', '-mc', '1', '0', '0'], capture_output=True, text=True)
        if result.returncode == 0:
            print("Screenshot saved as", screenshot_file)
        else:
            print("Error encountered:", result.stderr)
    for run in runs:
        bin_file = os.path.join(output_folder, f"{run}_averaged_betted_bin.nii.gz")
        threshold = '100'
        if not os.path.exists(bin_file):
            subprocess.run(['fslmaths', f'{p_id}/analysis/susceptibility/niftis/{run}_averaged_betted.nii.gz', '-thr', threshold, '-bin', bin_file])
            print(f"{run} EPI binarisation completed.")
        else:
            print(f"{run} binarised EPI already present. Skipping binarisation operation.")
        inverse_file = os.path.join(output_folder, f"{run}_averaged_betted_bin_inverse.nii.gz")
        if not os.path.exists(inverse_file):
            subprocess.run(['fslmaths', f'{p_id}/analysis/susceptibility/niftis/{run}_averaged_betted_bin.nii.gz', '-sub', '1', '-abs', inverse_file])
            print(f"{run} binarised EPI successfully inverted.")
        else:
            print(f"{run} inverted binary EPI already present. Skipping inversion procedure.")
        result2 = subprocess.run(['fslstats', f'{p_id}/analysis/susceptibility/niftis/{run}_subject_space_ROI.nii.gz', '-k', f'{p_id}/analysis/susceptibility/niftis/{run}_averaged_betted_bin_inverse.nii.gz', '-V'], capture_output=True, text=True)
        if result2.returncode == 0:
            result2_output = result2.stdout.strip()
        else:
            print(f"Error executing second fslstats command for {run}.")
        result2_output_values = result2_output.split()
        voxels_outside = float(result2_output_values[0])
        result3 = subprocess.run(['fslstats', f'{p_id}/analysis/susceptibility/niftis/{run}_subject_space_ROI.nii.gz', '-V'], capture_output=True, text=True)
        if result3.returncode == 0:
            result3_output = result3.stdout.strip()
        else:
            print(f"Error executing first fslstats command for {run}.")
        result3_output_values = result3_output.split()
        total_voxels_in_roi = float(result3_output_values[0])
        percentage_outside = (voxels_outside / total_voxels_in_roi) * 100
        percentage_outside = round(percentage_outside, 2)
        percentage_file = os.path.join(susceptibility_folder, "percentage_outside.txt")
        if not os.path.exists(percentage_file):
            with open(percentage_file, "a") as f:
                f.write("Percentage of ROI voxels in signal dropout regions of merged EPI images.\n\n")
                f.write("run threshold percentage_outside\n")
                f.write(f"{run} {threshold} {percentage_outside}\n")
        else:
            with open(percentage_file, "r") as f:
                lines = f.readlines()
                matching_lines = [line for line in lines if line.startswith(f"{run}")]
                if matching_lines:
                    with open(percentage_file, "w") as f:
                        for index, line in enumerate(lines):
                            if index not in matching_lines:
                                f.write(line)
                        f.write(f"{run} {threshold} {percentage_outside}\n")
                else:
                    with open(percentage_file, "a") as f:
                        f.write(f"{run} {threshold} {percentage_outside}\n")
        print("Percentage of ROI voxels in dropout regions saved in percentage_outside.txt file.")

    # Step 3: Test quality of alternate distortion correction method (Stage 1).
    print("\n###### STEP 3: TESTING ALTERNATE DISTORTION CORRECTION METHOD (STAGE 1) ######")
    good_participants = ['P059', 'P100', 'P107', 'P122', 'P125', 'P127', 'P128', 'P136', 'P145', 'P155', 'P199', 'P215', 'P216']
    group_participant_col = []
    group_tissue_type_col = []
    group_overlap_perc_col = []
    for p_id in participants_to_iterate:
        if p_id in good_participants:
            ap_fieldmaps = f"{p_id}/analysis/preproc/fieldmaps/ap_fieldmaps.nii"
            pa_fieldmaps = f"{p_id}/analysis/preproc/fieldmaps/pa_fieldmaps.nii"
            rl_fieldmaps = f"{p_id}/analysis/preproc/fieldmaps/rl_fieldmaps.nii"
            averaged_pa_fieldmaps = f"{p_id}/analysis/susceptibility/fnirt_test/1/averaged_pa_fieldmaps.nii.gz"
            averaged_rl_fieldmaps = f"{p_id}/analysis/susceptibility/fnirt_test/1/averaged_rl_fieldmaps.nii.gz"
            if not os.path.exists(averaged_pa_fieldmaps) or not os.path.exists(averaged_rl_fieldmaps):
                print(f"{p_id} fieldmaps images being averaged...")
                subprocess.run(['fslmaths', pa_fieldmaps, '-Tmean', averaged_pa_fieldmaps])
                subprocess.run(['fslmaths', rl_fieldmaps, '-Tmean', averaged_rl_fieldmaps])
                print(f"{p_id} fieldmaps images successfully averaged.")
            else:
                print(f"{p_id} fieldmaps images already averaged. Skipping process.")
            betted_pa_fieldmaps = f"{p_id}/analysis/susceptibility/fnirt_test/1/betted_pa_fieldmaps.nii.gz"
            betted_rl_fieldmaps = f"{p_id}/analysis/susceptibility/fnirt_test/1/betted_rl_fieldmaps.nii.gz"
            if not os.path.exists(betted_pa_fieldmaps) or not os.path.exists(betted_rl_fieldmaps):
                print(f"Fieldmaps sequences for {p_id} being brain extracted for distortion correction test 1.")
                subprocess.run(["bet", averaged_pa_fieldmaps, betted_pa_fieldmaps, "-m", "-R"])
                subprocess.run(["bet", averaged_rl_fieldmaps, betted_rl_fieldmaps, "-m", "-R"])
                print(f"Fieldmaps sequences for {p_id} successfully brain extracted.")
            else: 
                print(f"Fieldmaps sequences for {p_id} already brain extracted. Skipping process.")
            flirted_pa_fieldmaps = f"{p_id}/analysis/susceptibility/fnirt_test/1/flirted_pa_fieldmaps.nii.gz"
            flirted_rl_fieldmaps = f"{p_id}/analysis/susceptibility/fnirt_test/1/flirted_rl_fieldmaps.nii.gz"
            t1_flirted_pa_fieldmaps_transformation = f"{p_id}/analysis/susceptibility/fnirt_test/1/t1_flirted_pa_fieldmaps_transformation.mat"
            t1_flirted_rl_fieldmaps_transformation = f"{p_id}/analysis/susceptibility/fnirt_test/1/t1_flirted_rl_fieldmaps_transformation.mat"
            structural_brain = f"{p_id}/analysis/preproc/structural/structural_brain.nii.gz"
            if not os.path.exists(flirted_pa_fieldmaps):
                print(f"Aligning PA and RL fieldmaps to structural image for {p_id} distortion correction test 1...")
                subprocess.run(["flirt", "-in", betted_pa_fieldmaps, "-ref", structural_brain, "-out", flirted_pa_fieldmaps, "-omat", t1_flirted_pa_fieldmaps_transformation])
                subprocess.run(["flirt", "-in", betted_rl_fieldmaps, "-ref", structural_brain, "-out", flirted_rl_fieldmaps, "-omat", t1_flirted_rl_fieldmaps_transformation])
                print(f"PA and RL fieldmaps aligned to structural image successfully for {p_id}.")
            else:
                print(f"PA and RL fieldmaps have already been aligned to structural image for {p_id}. Skipping process.")
            pa_csf_pve_seg = f"{p_id}/analysis/susceptibility/fnirt_test/1/pa_seg_pve_0.nii.gz"
            pa_wm_pve_seg = f"{p_id}/analysis/susceptibility/fnirt_test/1/pa_seg_pve_1.nii.gz"
            pa_gm_pve_seg = f"{p_id}/analysis/susceptibility/fnirt_test/1/pa_seg_pve_2.nii.gz"
            rl_csf_pve_seg = f"{p_id}/analysis/susceptibility/fnirt_test/1/rl_seg_pve_0.nii.gz"
            rl_wm_pve_seg = f"{p_id}/analysis/susceptibility/fnirt_test/1/rl_seg_pve_1.nii.gz"
            rl_gm_pve_seg = f"{p_id}/analysis/susceptibility/fnirt_test/1/rl_seg_pve_2.nii.gz"
            if not os.path.exists(pa_csf_pve_seg):
                print(f"Segmenting {p_id} PA and RL fieldmaps...")
                pa_seg = f"{p_id}/analysis/susceptibility/fnirt_test/1/pa_seg"
                rl_seg = f"{p_id}/analysis/susceptibility/fnirt_test/1/rl_seg"
                subprocess.run(["fast", "-n", "3", "-o", pa_seg, structural_brain, flirted_pa_fieldmaps])
                subprocess.run(["fast", "-n", "3", "-o", rl_seg, structural_brain, flirted_rl_fieldmaps])
                print(f"{p_id} segmentation of PA and RL fieldmaps completed.")
            else:
                print(f"{p_id} segmentation of PA and RL fieldmaps already completed. Skipping process.")
            pa_csf_pve_seg_bin = f"{p_id}/analysis/susceptibility/fnirt_test/1/pa_csf_pve_seg_bin.nii.gz"
            pa_wm_pve_seg_bin = f"{p_id}/analysis/susceptibility/fnirt_test/1/pa_wm_pve_seg_bin.nii.gz"
            pa_gm_pve_seg_bin = f"{p_id}/analysis/susceptibility/fnirt_test/1/pa_gm_pve_seg_bin.nii.gz"
            if not os.path.exists(pa_csf_pve_seg_bin):
                print(f"Binarising {p_id} CSF, WM and GM segmented PVE masks for PA fieldmaps...")
                subprocess.run(['fslmaths', pa_csf_pve_seg, '-thr', '0.5', '-bin', pa_csf_pve_seg_bin])
                subprocess.run(['fslmaths', pa_wm_pve_seg, '-thr', '0.5', '-bin', pa_wm_pve_seg_bin])
                subprocess.run(['fslmaths', pa_gm_pve_seg, '-thr', '0.5', '-bin', pa_gm_pve_seg_bin])
                print(f"{p_id} CSF, WM, and GM segmented PVE masks for PA fieldmaps successfully binarised.")
            else:
                print(f"{p_id} binarisation of CSF, WM and GM segmented PVE masks for PA fieldmaps already completed. Skipping process.")
            rl_csf_pve_seg_bin = f"{p_id}/analysis/susceptibility/fnirt_test/1/rl_csf_pve_seg_bin.nii.gz"
            rl_wm_pve_seg_bin = f"{p_id}/analysis/susceptibility/fnirt_test/1/rl_wm_pve_seg_bin.nii.gz"
            rl_gm_pve_seg_bin = f"{p_id}/analysis/susceptibility/fnirt_test/1/rl_gm_pve_seg_bin.nii.gz"
            if not os.path.exists(rl_csf_pve_seg_bin):
                print(f"Binarising {p_id} CSF, WM and GM segmented PVE masks for RL fieldmaps...")
                subprocess.run(['fslmaths', rl_csf_pve_seg, '-thr', '0.5', '-bin', rl_csf_pve_seg_bin])
                subprocess.run(['fslmaths', rl_wm_pve_seg, '-thr', '0.5', '-bin', rl_wm_pve_seg_bin])
                subprocess.run(['fslmaths', rl_gm_pve_seg, '-thr', '0.5', '-bin', rl_gm_pve_seg_bin])
                print(f"{p_id} CSF, WM, and GM segmented PVE masks for RL fieldmaps successfully binarised.")
            else:
                print(f"{p_id} binarisation of CSF, WM and GM segmented PVE masks for RL fieldmaps already completed. Skipping process.")
            csf_intersect_mask = f"{p_id}/analysis/susceptibility/fnirt_test/1/csf_intersect_mask.nii.gz"
            wm_intersect_mask = f"{p_id}/analysis/susceptibility/fnirt_test/1/wm_intersect_mask.nii.gz"
            gm_intersect_mask = f"{p_id}/analysis/susceptibility/fnirt_test/1/gm_intersect_mask.nii.gz"
            if not os.path.exists(csf_intersect_mask):
                print(f"Creating Intersect masks for {p_id}...")
                subprocess.run(['fslmaths', pa_csf_pve_seg_bin, '-mul', rl_csf_pve_seg_bin, '-bin', csf_intersect_mask])
                subprocess.run(['fslmaths', pa_wm_pve_seg_bin, '-mul', rl_wm_pve_seg_bin, '-bin', wm_intersect_mask])
                subprocess.run(['fslmaths', pa_gm_pve_seg_bin, '-mul', rl_gm_pve_seg_bin, '-bin', gm_intersect_mask])
                print(f"Intersect masks for {p_id} successfully created.")
            else:
                print(f"Intersect masks for {p_id} already created. Skipping process.")
            csf_intersect_vol = float(subprocess.run(['fslstats', csf_intersect_mask, '-V'], capture_output=True, text=True).stdout.split()[0])
            wm_intersect_vol = float(subprocess.run(['fslstats', wm_intersect_mask, '-V'], capture_output=True, text=True).stdout.split()[0])
            gm_intersect_vol = float(subprocess.run(['fslstats', gm_intersect_mask, '-V'], capture_output=True, text=True).stdout.split()[0])
            pa_csf_mask_vol = float(subprocess.run(['fslstats', pa_csf_pve_seg_bin, '-V'], capture_output=True, text=True).stdout.split()[0])
            rl_csf_mask_vol = float(subprocess.run(['fslstats', rl_csf_pve_seg_bin, '-V'], capture_output=True, text=True).stdout.split()[0])
            if pa_csf_mask_vol < rl_csf_mask_vol:
                csf_overlap_perc = (csf_intersect_vol / pa_csf_mask_vol) * 100
            else: 
                csf_overlap_perc = (csf_intersect_vol / rl_csf_mask_vol) * 100
            pa_wm_mask_vol = float(subprocess.run(['fslstats', pa_wm_pve_seg_bin, '-V'], capture_output=True, text=True).stdout.split()[0])
            rl_wm_mask_vol = float(subprocess.run(['fslstats', rl_wm_pve_seg_bin, '-V'], capture_output=True, text=True).stdout.split()[0])
            if pa_wm_mask_vol < rl_wm_mask_vol:
                wm_overlap_perc = (wm_intersect_vol / pa_wm_mask_vol) * 100
            else: 
                wm_overlap_perc = (wm_intersect_vol / rl_wm_mask_vol) * 100
            pa_gm_mask_vol = float(subprocess.run(['fslstats', pa_gm_pve_seg_bin, '-V'], capture_output=True, text=True).stdout.split()[0])
            rl_gm_mask_vol = float(subprocess.run(['fslstats', rl_gm_pve_seg_bin, '-V'], capture_output=True, text=True).stdout.split()[0])
            if pa_gm_mask_vol < rl_gm_mask_vol:
                gm_overlap_perc = (gm_intersect_vol / pa_gm_mask_vol) * 100
            else: 
                gm_overlap_perc = (gm_intersect_vol / rl_gm_mask_vol) * 100
            overlap_perc_file = f"{p_id}/analysis/susceptibility/fnirt_test/1/overlap_perc.txt"
            participant_col = []
            tissue_type_col = []
            overlap_perc_col = []
            participant_col.append(p_id)
            participant_col.append(p_id)
            participant_col.append(p_id)
            tissue_type_col.append('csf')
            tissue_type_col.append('wm')
            tissue_type_col.append('gm')
            overlap_perc_col.append(csf_overlap_perc)
            overlap_perc_col.append(wm_overlap_perc)
            overlap_perc_col.append(gm_overlap_perc)
            overlap_perc_df = pd.DataFrame({'p_id': participant_col, 'tissue_type': tissue_type_col, 'overlap_perc': overlap_perc_col})
            overlap_perc_df.to_csv(overlap_perc_file, sep='\t', index=False)
            print(f"Percentage of overlap between PA and RL fieldmap segmentation masks for {p_id} saved to susceptibility/fnirt_test/1 folder.")
            group_overlap_perc_file = "group/susceptibility/fnirt_test/1/overlap_perc.txt"     
            if p_id not in group_participant_col:
                group_participant_col.append(p_id)
                group_participant_col.append(p_id)
                group_participant_col.append(p_id)
                group_tissue_type_col.append('csf')
                group_tissue_type_col.append('wm')
                group_tissue_type_col.append('gm')
                group_overlap_perc_col.append(csf_overlap_perc) 
                group_overlap_perc_col.append(wm_overlap_perc) 
                group_overlap_perc_col.append(gm_overlap_perc)          
                group_overlap_perc_df = pd.DataFrame({'p_id': group_participant_col, 'tissue_type': group_tissue_type_col, 'overlap_perc': group_overlap_perc_col})
                group_overlap_perc_df.to_csv(group_overlap_perc_file, sep='\t', index=False)
                print(f"Percentage of overlap between PA and RL fieldmap segmentation masks for {p_id} appended to group file in group/susceptibility/fnirt_test/1 folder.")
            else:
                print(f"Percentage of overlap between PA and RL fieldmap segmentation masks for {p_id} already appended to group file in group/susceptibility/fnirt_test/1 folder. Skipping process.")
    
    percentage_outside_pa_list = []
    percentage_outside_rl_list = []
    column_headers = ['p_id', 'ssim_index', 'voxels_in_bin_ssim_mask', 'perc_roi_voxels_in_bin_ssim_mask']
    group_ssim_df = pd.DataFrame(columns = column_headers) 
    for p_id in participants_to_iterate:
        if p_id in good_participants:
            def read_roi_file(roi_file):
                voxel_coordinates = []
                with open(roi_file, 'r') as file:
                    content = file.read()
                    matches = re.findall(r'(?<=\n)\s*\d+\s+\d+\s+\d+', content)
                    for match in matches:
                        coordinates = match.split()
                        voxel_coordinates.append(
                            (int(coordinates[0]), int(coordinates[1]), int(coordinates[2])))
                return voxel_coordinates
            path = os.path.join(os.getcwd(), p_id, 'data', 'neurofeedback')
            cisc_folder = None
            for folder_name in os.listdir(path):
                if "CISC" in folder_name:
                    cisc_folder = folder_name
                    break
            if cisc_folder is None:
                print("No 'CISC' folder found in the 'neurofeedback' directory.")
                exit(1)
            roi_file = f"{p_id}/data/neurofeedback/{cisc_folder}/depression_neurofeedback/target_folder_run-1/depnf_run-1.roi"
            voxel_coordinates = read_roi_file(roi_file)
            averaged_run = f"{p_id}/analysis/susceptibility/fnirt_test/1/averaged_run.nii.gz"
            if not os.path.exists(averaged_run):
                print(f"{p_id} Run 1 images being averaged...")
                run = f"{p_id}/analysis/preproc/niftis/run01_nh.nii.gz"
                subprocess.run(['fslmaths', run, '-Tmean', averaged_run])
                print(f"{p_id} Run 1 images successfully averaged.")
            else:
                print(f"{p_id} Run 1 images already averaged. Skipping process.")
            functional_image_info = nib.load(averaged_run)
            functional_dims = functional_image_info.shape
            binary_volume = np.zeros(functional_dims)
            for voxel in voxel_coordinates:
                x, y, z = voxel
                binary_volume[x, y, z] = 1
            binary_volume = np.flip(binary_volume, axis=1)
            functional_affine = functional_image_info.affine
            binary_mask = nib.Nifti1Image(binary_volume, affine=functional_affine)
            nib.save(binary_mask, f'{p_id}/analysis/susceptibility/fnirt_test/1/run01_subject_space_ROI.nii.gz')
            roi_mask = f'{p_id}/analysis/susceptibility/fnirt_test/1/run01_subject_space_ROI.nii.gz'
            transformed_roi_mask = f'{p_id}/analysis/susceptibility/fnirt_test/1/transformed_roi_mask.nii.gz'
            temp_file = f'{p_id}/analysis/susceptibility/fnirt_test/1/temp_file.nii.gz'
            roi_transformation = f'{p_id}/analysis/susceptibility/fnirt_test/1/roi_transformation.mat'
            subprocess.run(['flirt', '-in', averaged_run, '-ref', structural_brain, '-out', temp_file, '-omat', roi_transformation])
            subprocess.run(['flirt', '-in', roi_mask, '-ref', structural_brain, '-applyxfm', '-init', roi_transformation, '-out', transformed_roi_mask, '-interp', 'nearestneighbour'])
            flirted_pa_fieldmaps_bin = f'{p_id}/analysis/susceptibility/fnirt_test/1/flirted_pa_fieldmaps_bin.nii.gz'
            if not os.path.exists(flirted_pa_fieldmaps_bin):
                subprocess.run(['fslmaths', flirted_pa_fieldmaps, '-thr', '100', '-bin', flirted_pa_fieldmaps_bin])
            flirted_rl_fieldmaps_bin = os.path.join(f'{p_id}/analysis/susceptibility/fnirt_test/1/flirted_rl_fieldmaps_bin.nii.gz')
            if not os.path.exists(flirted_rl_fieldmaps_bin):
                subprocess.run(['fslmaths', flirted_rl_fieldmaps, '-thr', '100', '-bin', flirted_rl_fieldmaps_bin])
            pa_bin_inv = f'{p_id}/analysis/susceptibility/fnirt_test/1/pa_bin_inv.nii.gz'
            if not os.path.exists(pa_bin_inv):
                subprocess.run(['fslmaths', flirted_pa_fieldmaps_bin, '-sub', '1', '-abs', pa_bin_inv])
            rl_bin_inv = f'{p_id}/analysis/susceptibility/fnirt_test/1/rl_bin_inv.nii.gz'
            if not os.path.exists(rl_bin_inv):
                subprocess.run(['fslmaths', flirted_rl_fieldmaps_bin, '-sub', '1', '-abs', rl_bin_inv])
            pa_result = subprocess.run(['fslstats', transformed_roi_mask, '-k', pa_bin_inv, '-V'], capture_output=True, text=True)
            if pa_result.returncode == 0:
                pa_result_output = pa_result.stdout.strip()
            else:
                print("Error executing fslstats command.")
            pa_result_output_values = pa_result_output.split()
            pa_voxels_outside = float(pa_result_output_values[0])
            rl_result = subprocess.run(['fslstats', transformed_roi_mask, '-k', rl_bin_inv, '-V'], capture_output=True, text=True)
            if rl_result.returncode == 0:
                rl_result_output = rl_result.stdout.strip()
            else:
                print("Error executing fslstats command.")
            rl_result_output_values = rl_result_output.split()
            rl_voxels_outside = float(rl_result_output_values[0])
            result2 = subprocess.run(['fslstats', transformed_roi_mask, '-V'], capture_output=True, text=True)
            if result2.returncode == 0:
                result2_output = result2.stdout.strip()
            else:
                print("Error executing fslstats command.")
            result2_output_values = result2_output.split()
            total_voxels_in_roi = float(result2_output_values[0])
            percentage_outside_pa = (pa_voxels_outside / total_voxels_in_roi) * 100
            percentage_outside_pa = round(percentage_outside_pa, 2)
            percentage_outside_pa_list.append(percentage_outside_pa)
            percentage_outside_rl = (rl_voxels_outside / total_voxels_in_roi) * 100
            percentage_outside_rl = round(percentage_outside_rl, 2)
            percentage_outside_rl_list.append(percentage_outside_rl)
            pa_trimmed_roi_mask = f"{p_id}/analysis/susceptibility/fnirt_test/1/pa_trimmed_roi_mask.nii.gz"
            rl_trimmed_roi_mask = f"{p_id}/analysis/susceptibility/fnirt_test/1/rl_trimmed_roi_mask.nii.gz"
            if not os.path.exists(pa_trimmed_roi_mask) or not os.path.exists(rl_trimmed_roi_mask):
                subprocess.run(['fslmaths', transformed_roi_mask, '-mul', flirted_pa_fieldmaps_bin, pa_trimmed_roi_mask])
                subprocess.run(['fslmaths', transformed_roi_mask, '-mul', flirted_rl_fieldmaps_bin, rl_trimmed_roi_mask])
            def calculate_ssim(image1_path, image2_path, ssim_output_path):
                """Function to calculate SSIM between two NIfTI images and save the SSIM map."""
                image1_nii = nib.load(image1_path)
                image2_nii = nib.load(image2_path)
                image1 = image1_nii.get_fdata()
                image2 = image2_nii.get_fdata()
                if image1.shape != image2.shape:
                    raise ValueError("Input images must have the same dimensions for SSIM calculation.")
                ssim_index, ssim_map = ssim(image1, image2, full=True, data_range=image1.max() - image1.min())
                ssim_map_nifti = nib.Nifti1Image(ssim_map, affine=image1_nii.affine, header=image1_nii.header)
                nib.save(ssim_map_nifti, ssim_output_path)
                print(f"SSIM Index: {ssim_index}")
                print(f"SSIM map saved to: {ssim_output_path}")
                return ssim_index
            ssim_output_path = f"{p_id}/analysis/susceptibility/fnirt_test/1/ssim_map.nii.gz"
            if not os.path.exists(ssim_output_path):
                print(f"Calculating SSIM between PA and RL images for {p_id}...")
                ssim_index = calculate_ssim(flirted_rl_fieldmaps, flirted_pa_fieldmaps, ssim_output_path)
                print(f'SSIM between PA and RL images for {p_id} successfully calculated.')
            else:
                print(f"SSIM between PA and RL images for {p_id} already calculated. Skipping process.")
            binarised_ssim_output_path = f"{p_id}/analysis/susceptibility/fnirt_test/1/binarised_ssim_mask.nii.gz"
            if not os.path.exists(binarised_ssim_output_path):
                print(f'Binarising {p_id} SSIM mask...')
                subprocess.run(["fslmaths", ssim_output_path, "-thr", "0.8", "-binv", binarised_ssim_output_path])
                print(f'{p_id} SSIM mask successfully binarised.')
            else:
                print(f'{p_id} SSIM mask already binarised. Skipping process.')
            print(f'Counting voxels in binarised SSIM mask...')
            voxels_in_whole_mask = subprocess.run(["fslstats", binarised_ssim_output_path, "-V"], capture_output=True, text=True).stdout.split()[0]
            print(f'Voxels in whole binarised SSIM mask for {p_id}:', voxels_in_whole_mask)
            intersection_mask_path = f'{p_id}/analysis/susceptibility/fnirt_test/1/ssim_roi_intersect.nii.gz'
            if not os.path.exists(intersection_mask_path):
                print(f'Creating intersect mask of SSIM and ROI for {p_id}...')
                subprocess.run(["fslmaths", binarised_ssim_output_path, "-mas", transformed_roi_mask, intersection_mask_path])
                print(f'Intersect mask of SSIM and ROI for {p_id} successfully created.')
            else:
                print(f'Intersect mask of SSIM and ROI for {p_id} already exists. Skipping process.')
            print(f'Counting voxels in transformed ROI mask for {p_id}...')
            voxels_in_roi_in_mask = subprocess.run(["fslstats", intersection_mask_path, "-V"], capture_output=True, text=True).stdout.split()[0]
            print(f'Number of transformed ROI mask voxels present in SSIM intersect mask for {p_id}:', voxels_in_roi_in_mask)
            voxels_in_roi_in_mask = float(voxels_in_roi_in_mask)
            perc_roi_voxels_in_mask = (voxels_in_roi_in_mask / total_voxels_in_roi) * 100
            ssim_df = pd.DataFrame({'p_id': p_id, 'ssim_index': ssim_index, 'voxels_in_bin_ssim_mask': voxels_in_whole_mask, 'perc_roi_voxels_in_bin_ssim_mask': perc_roi_voxels_in_mask})
            ssim_df.tocsv(f'{p_id}/analysis/susceptibility/fnirt_test/1/ssim_df.txt', sep='\t', index=False)
            group_ssim_df = pd.concat([group_ssim_df, ssim_df], ignore_index=True)
    group_ssim_df.to_csv('group/susceptibility/fnirt_test/1/group_ssim_df.txt', sep='\t', index=False)
        
    column_headers = ['p_id', 'sequence', 'value']
    group_voxel_intensity_df = pd.DataFrame(columns = column_headers)   
    for p_id in participants_to_iterate:
        if p_id in good_participants:     
            def extract_voxel_intensities(epi_image_path, mask_image_path):
                epi_img = nib.load(epi_image_path)
                epi_data = epi_img.get_fdata()
                mask_img = nib.load(mask_image_path)
                mask_data = mask_img.get_fdata()
                mask_data = mask_data > 0
                roi_voxel_intensities = epi_data[mask_data]
                voxel_intensity_list = roi_voxel_intensities.tolist()
                return voxel_intensity_list
            pa_voxel_intensities = extract_voxel_intensities(flirted_pa_fieldmaps, pa_trimmed_roi_mask)
            rl_voxel_intensities = extract_voxel_intensities(flirted_rl_fieldmaps, rl_trimmed_roi_mask)
            pa_voxel_intensities_mean = np.mean(pa_voxel_intensities)
            rl_voxel_intensities_mean = np.mean(rl_voxel_intensities)
            print(f"Average voxel intensity within ROI for {p_id} PA fieldmap sequence: {pa_voxel_intensities_mean}")
            print(f"Average voxel intensity within ROI for {p_id} RL fieldmap sequence: {rl_voxel_intensities_mean}")
            values = pa_voxel_intensities + rl_voxel_intensities
            sequence = ['pa'] * len(pa_voxel_intensities) + ['rl'] * len(rl_voxel_intensities)
            subject = [f'{p_id}'] * len(pa_voxel_intensities) + [f'{p_id}'] * len(rl_voxel_intensities)
            voxel_intensity_df = pd.DataFrame({'p_id': subject, 'sequence': sequence, 'value': values})
            voxel_intensity_df.to_csv(f'{p_id}/analysis/susceptibility/fnirt_test/1/voxel_intensity_df.txt', sep='\t', index=False)
            group_voxel_intensity_df = pd.concat([group_voxel_intensity_df, voxel_intensity_df], ignore_index=True)
    group_voxel_intensity_df.to_csv('group/susceptibility/fnirt_test/1/group_voxel_intensity_df.txt', sep='\t', index=False)
    print('Percentage of ROI voxels in signal dropout regions for each of the 13 good participants in PA fieldmap sequence:', percentage_outside_pa_list)
    print('Percentage of ROI voxels in signal dropout regions for each of the 13 good participants in RL fieldmap sequence:', percentage_outside_rl_list)
    pa_means = []
    rl_means= []
    p_values = []
    pa_std_errors = []
    rl_std_errors = []
    for p_id in participants_to_iterate:
        if p_id in good_participants:
            filtered_pa = group_voxel_intensity_df[(group_voxel_intensity_df['p_id'] == f'{p_id}') & (group_voxel_intensity_df['sequence'] == 'pa')]
            mean_value_pa = filtered_pa['value'].mean()
            pa_means.append(mean_value_pa)
            filtered_rl = group_voxel_intensity_df[(group_voxel_intensity_df['p_id'] == f'{p_id}') & (group_voxel_intensity_df['sequence'] == 'rl')]
            mean_value_rl = filtered_rl['value'].mean()
            rl_means.append(mean_value_rl)
            anderson_pa = stats.anderson(filtered_pa['value'])
            print(f"Anderson-Darling test for PA sequence values: Statistic={anderson_pa.statistic}, Critical Values={anderson_pa.critical_values}, Significance Levels={anderson_pa.significance_level}")
            anderson_rl = stats.anderson(filtered_rl['value'])
            print(f"Anderson-Darling test for RL sequence values: Statistic={anderson_rl.statistic}, Critical Values={anderson_rl.critical_values}, Significance Levels={anderson_rl.significance_level}")
            significance_level = 0.05
            is_pa_normal = anderson_pa.statistic < anderson_pa.critical_values[
                anderson_pa.significance_level.tolist().index(significance_level * 100)]
            is_rl_normal = anderson_rl.statistic < anderson_rl.critical_values[
                anderson_rl.significance_level.tolist().index(significance_level * 100)]
            if is_pa_normal and is_rl_normal:
                print(f'Running t-test for {p_id}...')
                _, p_value = stats.ttest_ind(filtered_pa['value'], filtered_rl['value'], equal_var=False)
                p_values.append(p_value)
            else:
                print(f'Running Mann Whitney U test for {p_id}...')
                _, p_value = stats.mannwhitneyu(filtered_pa['value'], filtered_rl['value'], alternative='two-sided')
                p_values.append(p_value)
            pa_std_error = np.std(filtered_pa['value']) / np.sqrt(len(filtered_pa['value']))
            pa_std_errors.append(pa_std_error)
            rl_std_error = np.std(filtered_rl['value']) / np.sqrt(len(filtered_rl['value']))
            rl_std_errors.append(rl_std_error)
    plot_data = pd.DataFrame({
        'Participant': good_participants * 2,
        'Mean_Value': pa_means + rl_means,
        'Sequence': ['Corrected'] * len(good_participants) + ['Uncorrected'] * len(good_participants),
        'Significance': ['' for _ in range(len(good_participants) * 2)],
        'Std_Error': pa_std_errors + rl_std_errors
    })
    for idx, p_value in enumerate(p_values):
        if p_value < 0.001:
            plot_data.at[idx, 'Significance'] = '***'
        elif p_value < 0.01:
            plot_data.at[idx, 'Significance'] = '**'
        elif p_value < 0.05:
            plot_data.at[idx, 'Significance'] = '*'
    mean_plot = (
        ggplot(plot_data, aes(x='Participant', y='Mean_Value', fill='Sequence')) +
        geom_bar(stat='identity', position='dodge') +
        geom_errorbar(aes(ymin='Mean_Value - Std_Error', ymax='Mean_Value + Std_Error'), position=position_dodge(width=0.9), width=0.2, color='black') +
        theme_classic() +
        labs(title='Mean SCC Voxel Intensity', x='Participant', y='Mean Value') +
        theme(axis_text_x=element_text(rotation=45, hjust=1), text=element_text(size=12, color='blue'), axis_title=element_text(size=14, face='bold')) +
        scale_y_continuous(expand=(0, 0), limits=[0,350]) +
        geom_text(
            aes(x='Participant', y='Mean_Value', label='Significance'),
            position=position_dodge(width=0.9),
            color='black',
            size=12,
            ha='center',
            va='bottom',
            show_legend=False))
    mean_plot.save('group/susceptibility/fnirt_test/1/mean_plot.png')
    pa_means_overall = np.mean(pa_means)
    rl_means_overall = np.mean(rl_means)
    pa_std_error_overall = np.std(pa_means) / np.sqrt(len(pa_means))
    rl_std_error_overall = np.std(rl_means) / np.sqrt(len(rl_means))
    _, pa_means_overall_shap_p = stats.shapiro(pa_means)
    _, rl_means_overall_shap_p = stats.shapiro(rl_means)
    if pa_means_overall_shap_p > 0.05 and rl_means_overall_shap_p > 0.5:
        print(f'Running t-test for {p_id}...')
        _, p_value = stats.ttest_ind(pa_means, rl_means)
    else:
        print(f'Running Mann-Whitney U test for {p_id}...')
        _, p_value = stats.mannwhitneyu(pa_means, rl_means)
    plot_data = pd.DataFrame({'Sequence': ['PA', 'RL'], 'Mean': [pa_means_overall, rl_means_overall], 'Std_Error': [pa_std_error_overall, rl_std_error_overall]})
    overall_mean_plot = (ggplot(plot_data, aes(x='Sequence', y='Mean')) + 
                        geom_bar(stat='identity', position='dodge') +
                        geom_errorbar(aes(ymin='Mean - Std_Error', ymax='Mean + Std_Error'), width=0.2, color='black') +
                        theme_classic() +
                        labs(title='Mean of Voxel Intensities Across Participants.') +
                        scale_y_continuous(expand=(0, 0), limits=[0,350])
                        )
    if p_value < 0.001:
        overall_mean_plot = overall_mean_plot + annotate("text", x=1.5, y=max(plot_data['Mean']) + 40, label="***", size=16, color="black") + \
            annotate("segment", x=1, xend=2, y=max(plot_data['Mean']) +30, yend=max(plot_data['Mean']) + 30, color="black")
    elif p_value < 0.01:
        overall_mean_plot = overall_mean_plot + annotate("text", x=1.5, y=max(plot_data['Mean']) + 40, label="**", size=16, color="black") + \
            annotate("segment", x=1, xend=2, y=max(plot_data['Mean']) +30, yend=max(plot_data['Mean']) + 30, color="black")
    elif p_value < 0.05:
        overall_mean_plot = overall_mean_plot + annotate("text", x=1.5, y=max(plot_data['Mean']) + 40, label="*", size=16, color="black") + \
            annotate("segment", x=1, xend=2, y=max(plot_data['Mean']) +30, yend=max(plot_data['Mean']) + 30, color="black")    
    overall_mean_plot.save('group/susceptibility/fnirt_test/1/overall_mean_plot.png')

    # Step 4: Test quality of alternate distortion correction method (Stage 2).
    print("\n###### STEP 4: TESTING ALTERNATE DISTORTION CORRECTION METHOD (STAGE 2) ######")
    percentage_outside_corrected_list = []
    percentage_outside_uncorrected_list = []
    column_headers = ['p_id', 'ssim_index', 'voxels_in_bin_ssim_mask', 'perc_roi_voxels_in_bin_ssim_mask']
    group_ssim_df = pd.DataFrame(columns = column_headers) 
    for p_id in participants_to_iterate:
        if p_id in good_participants:            
            averaged_run = f"{p_id}/analysis/susceptibility/fnirt_test/2/averaged_run.nii.gz"
            if not os.path.exists(averaged_run):
                print(f"{p_id} Run 1 images being averaged...")
                run = f"{p_id}/analysis/preproc/niftis/run01_nh.nii.gz"
                subprocess.run(['fslmaths', run, '-Tmean', averaged_run])
                print(f"{p_id} Run 1 images successfully averaged.")
            else:
                print(f"{p_id} Run 1 images already averaged. Skipping process.")
            uncorrected_run = f"{p_id}/analysis/susceptibility/fnirt_test/2/uncorrected_run.nii.gz"
            if not os.path.exists(uncorrected_run):
                print(f"Performing brain extraction on Run 1 functional image.")
                subprocess.run(["bet", averaged_run, uncorrected_run, "-m", "-R"])
                print("Run 1 functional image brain extracted.")
            else:
                print("Run 1 functional image already brain extracted. Skipping process.")
            corrected_run = os.path.join(os.getcwd(), p_id, "analysis", "susceptibility", "fnirt_test", "2", "corrected_run.nii.gz")
            if not os.path.exists(corrected_run):
                print("Applying fieldmaps...")
                subprocess.run(["applytopup", f"--imain={uncorrected_run}", f"--datain={p_id}/analysis/preproc/fieldmaps/acqparams.txt", "--inindex=6", f"--topup={p_id}/analysis/preproc/fieldmaps/topup_{p_id}", "--method=jac", f"--out={corrected_run}"])
                print("Fieldmap application completed.")
            else:
                print("Fieldmaps already calculated and applied. Skipping process.")
            flirted_corrected_run = f"{p_id}/analysis/susceptibility/fnirt_test/2/flirted_corrected_run.nii.gz"
            flirted_uncorrected_run = f"{p_id}/analysis/susceptibility/fnirt_test/2/flirted_uncorrected_run.nii.gz"
            flirted_corrected_run_transformation = f"{p_id}/analysis/susceptibility/fnirt_test/2/flirted_corrected_run_transformation.mat"
            flirted_uncorrected_run_transformation = f"{p_id}/analysis/susceptibility/fnirt_test/2/flirted_uncorrected_run_transformation.mat"
            if not os.path.exists(flirted_corrected_run):
                print(f"Aligning corrected and uncorrected Run 1 sequences to structural image for {p_id} distortion correction test 2...")
                structural_brain = f"{p_id}/analysis/preproc/structural/structural_brain.nii.gz"
                subprocess.run(["flirt", "-in", corrected_run, "-ref", structural_brain, "-out", flirted_corrected_run, "-omat", flirted_corrected_run_transformation])
                subprocess.run(["flirt", "-in", uncorrected_run, "-ref", structural_brain, "-out", flirted_uncorrected_run, "-omat", flirted_uncorrected_run_transformation])
                print(f"Corrected and uncorrected Run 1 sequence aligned to structural image successfully for {p_id}.")
            else:
                print(f"Corrected and uncorrected Run 1 sequences have already been aligned to structural image for {p_id}. Skipping process.")
            def read_roi_file(roi_file):
                voxel_coordinates = []
                with open(roi_file, 'r') as file:
                    content = file.read()
                    matches = re.findall(r'(?<=\n)\s*\d+\s+\d+\s+\d+', content)
                    for match in matches:
                        coordinates = match.split()
                        voxel_coordinates.append(
                            (int(coordinates[0]), int(coordinates[1]), int(coordinates[2])))
                return voxel_coordinates
            path = os.path.join(os.getcwd(), p_id, 'data', 'neurofeedback')
            cisc_folder = None
            for folder_name in os.listdir(path):
                if "CISC" in folder_name:
                    cisc_folder = folder_name
                    break
            if cisc_folder is None:
                print("No 'CISC' folder found in the 'neurofeedback' directory.")
                exit(1)
            roi_file = f"{p_id}/data/neurofeedback/{cisc_folder}/depression_neurofeedback/target_folder_run-1/depnf_run-1.roi"            
            voxel_coordinates = read_roi_file(roi_file)
            functional_image_info = nib.load(averaged_run)
            functional_dims = functional_image_info.shape
            binary_volume = np.zeros(functional_dims)
            for voxel in voxel_coordinates:
                x, y, z = voxel
                binary_volume[x, y, z] = 1
            binary_volume = np.flip(binary_volume, axis=1)
            functional_affine = functional_image_info.affine
            binary_mask = nib.Nifti1Image(binary_volume, affine=functional_affine)
            nib.save(binary_mask, f'{p_id}/analysis/susceptibility/fnirt_test/2/run01_subject_space_ROI.nii.gz')
            roi_mask = f'{p_id}/analysis/susceptibility/fnirt_test/2/run01_subject_space_ROI.nii.gz'
            transformed_roi_mask = f'{p_id}/analysis/susceptibility/fnirt_test/2/transformed_roi_mask.nii.gz'
            temp_file = f'{p_id}/analysis/susceptibility/fnirt_test/2/temp_file.nii.gz'
            roi_transformation = f'{p_id}/analysis/susceptibility/fnirt_test/2/roi_transformation.mat'
            subprocess.run(['flirt', '-in', averaged_run, '-ref', structural_brain, '-out', temp_file, '-omat', roi_transformation])
            subprocess.run(['flirt', '-in', roi_mask, '-ref', structural_brain, '-applyxfm', '-init', roi_transformation, '-out', transformed_roi_mask, '-interp', 'nearestneighbour'])
            flirted_corrected_bin = f'{p_id}/analysis/susceptibility/fnirt_test/2/flirted_corrected_bin.nii.gz'
            if not os.path.exists(flirted_corrected_bin):
                subprocess.run(['fslmaths', flirted_corrected_run, '-thr', '100', '-bin', flirted_corrected_bin])
            flirted_uncorrected_bin = os.path.join(f'{p_id}/analysis/susceptibility/fnirt_test/2/flirted_uncorrected_bin.nii.gz')
            if not os.path.exists(flirted_uncorrected_bin):
                subprocess.run(['fslmaths', flirted_uncorrected_run, '-thr', '100', '-bin', flirted_uncorrected_bin])
            corrected_bin_inv = f'{p_id}/analysis/susceptibility/fnirt_test/2/corrected_bin_inv.nii.gz'
            if not os.path.exists(corrected_bin_inv):
                subprocess.run(['fslmaths', flirted_corrected_bin, '-sub', '1', '-abs', corrected_bin_inv])
            uncorrected_bin_inv = f'{p_id}/analysis/susceptibility/fnirt_test/2/uncorrected_bin_inv.nii.gz'
            if not os.path.exists(uncorrected_bin_inv):
                subprocess.run(['fslmaths', flirted_uncorrected_bin, '-sub', '1', '-abs', uncorrected_bin_inv])
            corrected_result = subprocess.run(['fslstats', transformed_roi_mask, '-k', corrected_bin_inv, '-V'], capture_output=True, text=True)
            if corrected_result.returncode == 0:
                corrected_result_output = corrected_result.stdout.strip()
            else:
                print("Error executing fslstats command.")
            corrected_result_output_values = corrected_result_output.split()
            corrected_voxels_outside = float(corrected_result_output_values[0])
            uncorrected_result = subprocess.run(['fslstats', transformed_roi_mask, '-k', uncorrected_bin_inv, '-V'], capture_output=True, text=True)
            if uncorrected_result.returncode == 0:
                uncorrected_result_output = uncorrected_result.stdout.strip()
            else:
                print("Error executing fslstats command.")
            uncorrected_result_output_values = uncorrected_result_output.split()
            uncorrected_voxels_outside = float(uncorrected_result_output_values[0])
            result2 = subprocess.run(['fslstats', transformed_roi_mask, '-V'], capture_output=True, text=True)
            if result2.returncode == 0:
                result2_output = result2.stdout.strip()
            else:
                print("Error executing fslstats command.")
            result2_output_values = result2_output.split()
            total_voxels_in_roi = float(result2_output_values[0])
            percentage_outside_corrected = (corrected_voxels_outside / total_voxels_in_roi) * 100
            percentage_outside_corrected = round(percentage_outside_corrected, 2)
            percentage_outside_corrected_list.append(percentage_outside_corrected)
            percentage_outside_uncorrected = (uncorrected_voxels_outside / total_voxels_in_roi) * 100
            percentage_outside_uncorrected = round(percentage_outside_uncorrected, 2)
            percentage_outside_uncorrected_list.append(percentage_outside_uncorrected)
            corrected_trimmed_roi_mask = f"{p_id}/analysis/susceptibility/fnirt_test/2/corrected_trimmed_roi_mask.nii.gz"
            uncorrected_trimmed_roi_mask = f"{p_id}/analysis/susceptibility/fnirt_test/2/uncorrected_trimmed_roi_mask.nii.gz"
            if not os.path.exists(corrected_trimmed_roi_mask) or not os.path.exists(uncorrected_trimmed_roi_mask):
                subprocess.run(['fslmaths', transformed_roi_mask, '-mul', flirted_corrected_bin, corrected_trimmed_roi_mask])
                subprocess.run(['fslmaths', transformed_roi_mask, '-mul', flirted_uncorrected_bin, uncorrected_trimmed_roi_mask])
            def calculate_ssim(image1_path, image2_path, ssim_output_path):
                """Function to calculate SSIM between two NIfTI images and save the SSIM map."""
                image1_nii = nib.load(image1_path)
                image2_nii = nib.load(image2_path)
                image1 = image1_nii.get_fdata()
                image2 = image2_nii.get_fdata()
                if image1.shape != image2.shape:
                    raise ValueError("Input images must have the same dimensions for SSIM calculation.")
                ssim_index, ssim_map = ssim(image1, image2, full=True, data_range=image1.max() - image1.min())
                ssim_map_nifti = nib.Nifti1Image(ssim_map, affine=image1_nii.affine, header=image1_nii.header)
                nib.save(ssim_map_nifti, ssim_output_path)
                print(f"SSIM Index: {ssim_index}")
                print(f"SSIM map saved to: {ssim_output_path}")
                return ssim_index
            ssim_output_path = f"{p_id}/analysis/susceptibility/fnirt_test/2/ssim_map.nii.gz"
            if not os.path.exists(ssim_output_path):
                print(f"Calculating SSIM between corrected and uncorrected images for {p_id}...")
                ssim_index = calculate_ssim(flirted_uncorrected_run, flirted_corrected_run, ssim_output_path)
                print(f'SSIM between corrected and uncorrected images for {p_id} successfully calculated.')
            else:
                print(f"SSIM between uncorrected and corrected images for {p_id} already calculated. Skipping process.")
            binarised_ssim_output_path = f"{p_id}/analysis/susceptibility/fnirt_test/2/binarised_ssim_mask.nii.gz"
            if not os.path.exists(binarised_ssim_output_path):
                print(f'Binarising {p_id} SSIM mask...')
                subprocess.run(["fslmaths", ssim_output_path, "-thr", "0.8", "-binv", binarised_ssim_output_path])
                print(f'{p_id} SSIM mask successfully binarised.')
            else:
                print(f'{p_id} SSIM mask already binarised. Skipping process.')
            print(f'Counting voxels in binarised SSIM mask...')
            voxels_in_whole_mask = subprocess.run(["fslstats", binarised_ssim_output_path, "-V"], capture_output=True, text=True).stdout.split()[0]
            print(f'Voxels in whole binarised SSIM mask for {p_id}:', voxels_in_whole_mask)
            intersection_mask_path = f'{p_id}/analysis/susceptibility/fnirt_test/2/ssim_roi_intersect.nii.gz'
            if not os.path.exists(intersection_mask_path):
                print(f'Creating intersect mask of SSIM and ROI for {p_id}...')
                subprocess.run(["fslmaths", binarised_ssim_output_path, "-mas", transformed_roi_mask, intersection_mask_path])
                print(f'Intersect mask of SSIM and ROI for {p_id} successfully created.')
            else:
                print(f'Intersect mask of SSIM and ROI for {p_id} already exists. Skipping process.')
            print(f'Counting voxels in transformed ROI mask for {p_id}...')
            voxels_in_roi_in_mask = subprocess.run(["fslstats", intersection_mask_path, "-V"], capture_output=True, text=True).stdout.split()[0]
            print(f'Number of transformed ROI mask voxels present in SSIM intersect mask for {p_id}:', voxels_in_roi_in_mask)
            voxels_in_roi_in_mask = float(voxels_in_roi_in_mask)
            perc_roi_voxels_in_mask = (voxels_in_roi_in_mask / total_voxels_in_roi) * 100
            ssim_df = pd.DataFrame({'p_id': p_id, 'ssim_index': ssim_index, 'voxels_in_bin_ssim_mask': voxels_in_whole_mask, 'perc_roi_voxels_in_bin_ssim_mask': perc_roi_voxels_in_mask})
            ssim_df.tocsv(f'{p_id}/analysis/susceptibility/fnirt_test/2/ssim_df.txt', sep='\t', index=False)
            group_ssim_df = pd.concat([group_ssim_df, ssim_df], ignore_index=True)
    group_ssim_df.to_csv('group/susceptibility/fnirt_test/2/group_ssim_df.txt', sep='\t', index=False)

    column_headers = ['p_id', 'sequence', 'value']
    group_voxel_intensity_df = pd.DataFrame(columns = column_headers)   
    for p_id in participants_to_iterate:
        if p_id in good_participants:             
            def extract_voxel_intensities(epi_image_path, mask_image_path):
                epi_img = nib.load(epi_image_path)
                epi_data = epi_img.get_fdata()
                mask_img = nib.load(mask_image_path)
                mask_data = mask_img.get_fdata()
                mask_data = mask_data > 0
                roi_voxel_intensities = epi_data[mask_data]
                voxel_intensity_list = roi_voxel_intensities.tolist()
                return voxel_intensity_list
            corrected_voxel_intensities = extract_voxel_intensities(flirted_corrected_run, corrected_trimmed_roi_mask)
            uncorrected_voxel_intensities = extract_voxel_intensities(flirted_uncorrected_run, uncorrected_trimmed_roi_mask)
            corrected_voxel_intensities_mean = np.mean(corrected_voxel_intensities)
            uncorrected_voxel_intensities_mean = np.mean(uncorrected_voxel_intensities)
            print(f"Average voxel intensity within ROI for {p_id} fieldmap-corrected sequence: {corrected_voxel_intensities_mean}")
            print(f"Average voxel intensity within ROI for {p_id} uncorrected sequence: {uncorrected_voxel_intensities_mean}")
            values = corrected_voxel_intensities + uncorrected_voxel_intensities
            sequence = ['corrected'] * len(corrected_voxel_intensities) + ['uncorrected'] * len(uncorrected_voxel_intensities)
            subject = [f'{p_id}'] * len(corrected_voxel_intensities) + [f'{p_id}'] * len(uncorrected_voxel_intensities)
            voxel_intensity_df = pd.DataFrame({'p_id': subject, 'sequence': sequence, 'value': values})
            voxel_intensity_df.to_csv(f'{p_id}/analysis/susceptibility/fnirt_test/2/voxel_intensity_df.txt', sep='\t', index=False)
            group_voxel_intensity_df = pd.concat([group_voxel_intensity_df, voxel_intensity_df], ignore_index=True)
    group_voxel_intensity_df.to_csv('group/susceptibility/fnirt_test/2/group_voxel_intensity_df.txt', sep='\t', index=False)
    print('Percentage of ROI voxels in signal dropout regions for each of the 13 good participants following fieldmap correction:', percentage_outside_corrected_list)
    print('Percentage of ROI voxels in signal dropout regions for each of the 13 good participants in absence of fieldmap correction:', percentage_outside_uncorrected_list)
    corrected_means = []
    uncorrected_means= []
    p_values = []
    corrected_std_errors = []
    uncorrected_std_errors = []
    for p_id in participants_to_iterate:
        if p_id in good_participants:
            filtered_corrected = group_voxel_intensity_df[(group_voxel_intensity_df['p_id'] == f'{p_id}') & (group_voxel_intensity_df['sequence'] == 'corrected')]
            mean_value_corrected = filtered_corrected['value'].mean()
            corrected_means.append(mean_value_corrected)
            filtered_uncorrected = group_voxel_intensity_df[(group_voxel_intensity_df['p_id'] == f'{p_id}') & (group_voxel_intensity_df['sequence'] == 'uncorrected')]
            mean_value_uncorrected = filtered_uncorrected['value'].mean()
            uncorrected_means.append(mean_value_uncorrected)
            anderson_corrected = stats.anderson(filtered_corrected['value'])
            print(f"Anderson-Darling test for corrected values: Statistic={anderson_corrected.statistic}, Critical Values={anderson_corrected.critical_values}, Significance Levels={anderson_corrected.significance_level}")
            anderson_uncorrected = stats.anderson(filtered_uncorrected['value'])
            print(f"Anderson-Darling test for uncorrected values: Statistic={anderson_uncorrected.statistic}, Critical Values={anderson_uncorrected.critical_values}, Significance Levels={anderson_uncorrected.significance_level}")
            significance_level = 0.05
            is_corrected_normal = anderson_corrected.statistic < anderson_corrected.critical_values[
                anderson_corrected.significance_level.tolist().index(significance_level * 100)]
            is_uncorrected_normal = anderson_uncorrected.statistic < anderson_uncorrected.critical_values[
                anderson_uncorrected.significance_level.tolist().index(significance_level * 100)]
            if is_corrected_normal and is_uncorrected_normal:
                print(f'Running t-test for {p_id}...')
                _, p_value = stats.ttest_ind(filtered_corrected['value'], filtered_uncorrected['value'], equal_var=False)
                p_values.append(p_value)
            else:
                print(f'Running Mann Whitney U test for {p_id}...')
                _, p_value = stats.mannwhitneyu(filtered_corrected['value'], filtered_uncorrected['value'], alternative='two-sided')
                p_values.append(p_value)
            corrected_std_error = np.std(filtered_corrected['value']) / np.sqrt(len(filtered_corrected['value']))
            corrected_std_errors.append(corrected_std_error)
            uncorrected_std_error = np.std(filtered_uncorrected['value']) / np.sqrt(len(filtered_uncorrected['value']))
            uncorrected_std_errors.append(uncorrected_std_error)
    plot_data = pd.DataFrame({
        'Participant': good_participants * 2,
        'Mean_Value': corrected_means + uncorrected_means,
        'Sequence': ['Corrected'] * len(good_participants) + ['Uncorrected'] * len(good_participants),
        'Significance': ['' for _ in range(len(good_participants) * 2)],
        'Std_Error': corrected_std_errors + uncorrected_std_errors
    })
    for idx, p_value in enumerate(p_values):
        if p_value < 0.001:
            plot_data.at[idx, 'Significance'] = '***'
        elif p_value < 0.01:
            plot_data.at[idx, 'Significance'] = '**'
        elif p_value < 0.05:
            plot_data.at[idx, 'Significance'] = '*'
    mean_plot = (
        ggplot(plot_data, aes(x='Participant', y='Mean_Value', fill='Sequence')) +
        geom_bar(stat='identity', position='dodge') +
        geom_errorbar(aes(ymin='Mean_Value - Std_Error', ymax='Mean_Value + Std_Error'), position=position_dodge(width=0.9), width=0.2, color='black') +
        theme_classic() +
        labs(title='Mean SCC Voxel Intensity', x='Participant', y='Mean Value') +
        theme(axis_text_x=element_text(rotation=45, hjust=1), text=element_text(size=12, color='blue'), axis_title=element_text(size=14, face='bold')) +
        scale_y_continuous(expand=(0, 0), limits=[0,350]) +
        geom_text(
            aes(x='Participant', y='Mean_Value', label='Significance'),
            position=position_dodge(width=0.9),
            color='black',
            size=12,
            ha='center',
            va='bottom',
            show_legend=False))
    mean_plot.save('group/susceptibility/fnirt_test/2/mean_plot.png')
    corrected_means_overall = np.mean(corrected_means)
    uncorrected_means_overall = np.mean(uncorrected_means)
    corrected_std_error_overall = np.std(corrected_means) / np.sqrt(len(corrected_means))
    uncorrected_std_error_overall = np.std(uncorrected_means) / np.sqrt(len(uncorrected_means))
    _, corrected_means_overall_shap_p = stats.shapiro(corrected_means)
    _, uncorrected_means_overall_shap_p = stats.shapiro(uncorrected_means)
    if corrected_means_overall_shap_p > 0.05 and uncorrected_means_overall_shap_p > 0.5:
        _, p_value = stats.ttest_ind(corrected_means, uncorrected_means)
    else:
        _, p_value = stats.mannwhitneyu(corrected_means, uncorrected_means)
    plot_data = pd.DataFrame({'Sequence': ['Corrected', 'Uncorrected'], 'Mean': [corrected_means_overall, uncorrected_means_overall], 'Std_Error': [corrected_std_error_overall, uncorrected_std_error_overall]})
    overall_mean_plot = (ggplot(plot_data, aes(x='Sequence', y='Mean')) + 
                        geom_bar(stat='identity', position='dodge') +
                        geom_errorbar(aes(ymin='Mean - Std_Error', ymax='Mean + Std_Error'), width=0.2, color='black') +
                        theme_classic() +
                        labs(title='Mean of Voxel Intensities Across Participants.') +
                        scale_y_continuous(expand=(0, 0), limits=[0,350])
                        )
    if p_value < 0.001:
        overall_mean_plot = overall_mean_plot + annotate("text", x=1.5, y=max(plot_data['Mean']) + 40, label="***", size=16, color="black") + \
            annotate("segment", x=1, xend=2, y=max(plot_data['Mean']) +30, yend=max(plot_data['Mean']) + 30, color="black")
    elif p_value < 0.01:
        overall_mean_plot = overall_mean_plot + annotate("text", x=1.5, y=max(plot_data['Mean']) + 40, label="**", size=16, color="black") + \
            annotate("segment", x=1, xend=2, y=max(plot_data['Mean']) +30, yend=max(plot_data['Mean']) + 30, color="black")
    elif p_value < 0.05:
        overall_mean_plot = overall_mean_plot + annotate("text", x=1.5, y=max(plot_data['Mean']) + 40, label="*", size=16, color="black") + \
            annotate("segment", x=1, xend=2, y=max(plot_data['Mean']) +30, yend=max(plot_data['Mean']) + 30, color="black")    
    overall_mean_plot.save('group/susceptibility/fnirt_test/2/overall_mean_plot.png')

    # Step 5: Test quality of alternate distortion correction method (Stage 3).
    print("\n###### STEP 5: TESTING ALTERNATE DISTORTION CORRECTION METHOD (STAGE 3) ######")
    percentage_outside_pa_list = []
    percentage_outside_rl_list = []
    column_headers = ['p_id', 'ssim_index', 'voxels_in_bin_ssim_mask', 'perc_roi_voxels_in_bin_ssim_mask']
    group_ssim_df = pd.DataFrame(columns = column_headers) 
    for p_id in participants_to_iterate:
        if p_id in good_participants:
            ap_fieldmaps = f"{p_id}/analysis/preproc/fieldmaps/ap_fieldmaps.nii"
            pa_fieldmaps = f"{p_id}/analysis/preproc/fieldmaps/pa_fieldmaps.nii"
            rl_fieldmaps = f"{p_id}/analysis/preproc/fieldmaps/rl_fieldmaps.nii"
            averaged_pa_fieldmaps = f"{p_id}/analysis/susceptibility/fnirt_test/3/averaged_pa_fieldmaps.nii.gz"
            averaged_rl_fieldmaps = f"{p_id}/analysis/susceptibility/fnirt_test/3/averaged_rl_fieldmaps.nii.gz"
            if not os.path.exists(averaged_pa_fieldmaps) or not os.path.exists(averaged_rl_fieldmaps):
                print(f"{p_id} fieldmaps images being averaged...")
                subprocess.run(['fslmaths', pa_fieldmaps, '-Tmean', averaged_pa_fieldmaps])
                subprocess.run(['fslmaths', rl_fieldmaps, '-Tmean', averaged_rl_fieldmaps])
                print(f"{p_id} fieldmaps images successfully averaged.")
            else:
                print(f"{p_id} fieldmaps images already averaged. Skipping process.")
            betted_pa_fieldmaps = f"{p_id}/analysis/susceptibility/fnirt_test/3/betted_pa_fieldmaps.nii.gz"
            betted_rl_fieldmaps = f"{p_id}/analysis/susceptibility/fnirt_test/3/betted_rl_fieldmaps.nii.gz"
            if not os.path.exists(betted_pa_fieldmaps) or not os.path.exists(betted_rl_fieldmaps):
                print(f"Fieldmaps sequences for {p_id} being brain extracted for distortion correction test 1.")
                subprocess.run(["bet", averaged_pa_fieldmaps, betted_pa_fieldmaps, "-m", "-R"])
                subprocess.run(["bet", averaged_rl_fieldmaps, betted_rl_fieldmaps, "-m", "-R"])
                print(f"Fieldmaps sequences for {p_id} successfully brain extracted.")
            else: 
                print(f"Fieldmaps sequences for {p_id} already brain extracted. Skipping process.")
            corrected_pa_fieldmaps = f"{p_id}/analysis/susceptibility/fnirt_test/3/corrected_pa_fieldmaps.nii.gz"            
            if not os.path.exists(corrected_pa_fieldmaps):
                print("Applying fieldmaps...")
                subprocess.run(["applytopup", f"--imain={betted_pa_fieldmaps}", f"--datain={p_id}/analysis/preproc/fieldmaps/acqparams.txt", "--inindex=6", f"--topup={p_id}/analysis/preproc/fieldmaps/topup_{p_id}", "--method=jac", f"--out={corrected_pa_fieldmaps}"])
                print("Fieldmap application completed.")
            else:
                print("Fieldmaps already calculated and applied. Skipping process.")
            rl_to_pa_affine = f"{p_id}/analysis/susceptibility/fnirt_test/3/rl_to_pa_affine.mat"
            flirted_rl_fieldmaps = f"{p_id}/analysis/susceptibility/fnirt_test/3/flirted_rl_fieldmaps.nii.gz"
            rl_to_pa_warp = f"{p_id}/analysis/susceptibility/fnirt_test/3/rl_to_pa_warp.nii.gz"
            fnirted_rl_fieldmaps = f"{p_id}/analysis/susceptibility/fnirt_test/3/fnirted_rl_fieldmaps.nii.gz"
            if not os.path.exists(fnirted_rl_fieldmaps):
                subprocess.run(['flirt', '-in', betted_rl_fieldmaps, '-ref', corrected_pa_fieldmaps, '-omat', rl_to_pa_affine, '-out', flirted_rl_fieldmaps, '-dof', '6'])
                subprocess.run(['fnirt', f'--in={betted_rl_fieldmaps}', f'--ref={corrected_pa_fieldmaps}', f'--aff={rl_to_pa_affine}', f'--cout={rl_to_pa_warp}'])
                subprocess.run(['applywarp', f'--in={betted_rl_fieldmaps}', f'--ref={corrected_pa_fieldmaps}', f'--warp={rl_to_pa_warp}', f'--out={fnirted_rl_fieldmaps}'])
            FSLDIR = os.getenv('FSLDIR')
            if not FSLDIR:
                raise EnvironmentError("FSLDIR is not set. Make sure FSL is installed and FSLDIR is set correctly.")
            structural_brain = f"{p_id}/analysis/preproc/structural/structural_brain.nii.gz"
            mni_template = f"{FSLDIR}/data/standard/MNI152_T1_2mm_brain.nii.gz"
            pa_func2struct = f"{p_id}/analysis/susceptibility/fnirt_test/3/pa_func2struct.mat"
            pa_struct2standard_mat = f"{p_id}/analysis/susceptibility/fnirt_test/3/pa_struct2standard.mat"
            pa_warp_struct2standard = f"{p_id}/analysis/susceptibility/fnirt_test/3/pa_warp_struct2standard.nii.gz"
            standard_pa_fieldmaps = f"{p_id}/analysis/susceptibility/fnirt_test/3/standard_pa_fieldmaps.nii.gz"
            if not os.path.exists(standard_pa_fieldmaps):
                subprocess.run(['flirt', '-in', corrected_pa_fieldmaps, '-ref', structural_brain, '-omat', pa_func2struct, '-dof', '6'])
                subprocess.run(['flirt', '-in', structural_brain, '-ref', mni_template, '-omat', pa_struct2standard_mat])
                subprocess.run(['fnirt', f'--in={structural_brain}', f'--ref={mni_template}', f'--aff={pa_struct2standard_mat}', '--config=T1_2_MNI152_2mm', '--lambda=400,200,150,75,60,45', f'--cout={pa_warp_struct2standard}'])
                subprocess.run(['applywarp', f'--in={corrected_pa_fieldmaps}', f'--ref={mni_template}', f'--warp={pa_warp_struct2standard}', f'--premat={pa_func2struct}', f'--out={standard_pa_fieldmaps}'])
            rl_func2struct = f"{p_id}/analysis/susceptibility/fnirt_test/3/rl_func2struct.mat"
            rl_struct2standard_mat = f"{p_id}/analysis/susceptibility/fnirt_test/3/rl_struct2standard.mat"
            rl_warp_struct2standard = f"{p_id}/analysis/susceptibility/fnirt_test/3/rl_warp_struct2standard.nii.gz"
            standard_rl_fieldmaps = f"{p_id}/analysis/susceptibility/fnirt_test/3/standard_rl_fieldmaps.nii.gz"
            if not os.path.exists(standard_rl_fieldmaps):
                subprocess.run(['flirt', '-in', fnirted_rl_fieldmaps, '-ref', structural_brain, '-omat', rl_func2struct, '-dof', '6'])
                subprocess.run(['flirt', '-in', structural_brain, '-ref', mni_template, '-omat', rl_struct2standard_mat])
                subprocess.run(['fnirt', f'--in={structural_brain}', f'--ref={mni_template}', f'--aff={rl_struct2standard_mat}', '--config=T1_2_MNI152_2mm', '--lambda=400,200,150,75,60,45', f'--cout={rl_warp_struct2standard}'])
                subprocess.run(['applywarp', f'--in={fnirted_rl_fieldmaps}', f'--ref={mni_template}', f'--warp={rl_warp_struct2standard}', f'--premat={rl_func2struct}', f'--out={standard_rl_fieldmaps}']) 
            def read_roi_file(roi_file):
                voxel_coordinates = []
                with open(roi_file, 'r') as file:
                    content = file.read()
                    matches = re.findall(r'(?<=\n)\s*\d+\s+\d+\s+\d+', content)
                    for match in matches:
                        coordinates = match.split()
                        voxel_coordinates.append(
                            (int(coordinates[0]), int(coordinates[1]), int(coordinates[2])))
                return voxel_coordinates
            path = os.path.join(os.getcwd(), p_id, 'data', 'neurofeedback')
            cisc_folder = None
            for folder_name in os.listdir(path):
                if "CISC" in folder_name:
                    cisc_folder = folder_name
                    break
            if cisc_folder is None:
                print("No 'CISC' folder found in the 'neurofeedback' directory.")
                exit(1)
            roi_file = f"{p_id}/data/neurofeedback/{cisc_folder}/depression_neurofeedback/target_folder_run-1/depnf_run-1.roi"            
            voxel_coordinates = read_roi_file(roi_file)
            averaged_run = f"{p_id}/analysis/susceptibility/fnirt_test/3/averaged_run.nii.gz"
            if not os.path.exists(averaged_run):
                print(f"{p_id} Run 1 images being averaged...")
                run = f"{p_id}/analysis/preproc/niftis/run01_nh.nii.gz"
                subprocess.run(['fslmaths', run, '-Tmean', averaged_run])
                print(f"{p_id} Run 1 images successfully averaged.")
            else:
                print(f"{p_id} Run 1 images already averaged. Skipping process.")
            functional_image_info = nib.load(averaged_run)
            functional_dims = functional_image_info.shape
            binary_volume = np.zeros(functional_dims)
            for voxel in voxel_coordinates:
                x, y, z = voxel
                binary_volume[x, y, z] = 1
            binary_volume = np.flip(binary_volume, axis=1)
            functional_affine = functional_image_info.affine
            binary_mask = nib.Nifti1Image(binary_volume, affine=functional_affine)
            nib.save(binary_mask, f'{p_id}/analysis/susceptibility/fnirt_test/3/run01_subject_space_ROI.nii.gz')
            roi_mask = f'{p_id}/analysis/susceptibility/fnirt_test/3/run01_subject_space_ROI.nii.gz'
            transformed_roi_mask = f'{p_id}/analysis/susceptibility/fnirt_test/3/transformed_roi_mask.nii.gz'
            temp_file = f'{p_id}/analysis/susceptibility/fnirt_test/3/temp_file.nii.gz'
            roi_transformation = f'{p_id}/analysis/susceptibility/fnirt_test/3/roi_transformation.mat'
            subprocess.run(['flirt', '-in', averaged_run, '-ref', structural_brain, '-out', temp_file, '-omat', roi_transformation])
            subprocess.run(['flirt', '-in', roi_mask, '-ref', structural_brain, '-applyxfm', '-init', roi_transformation, '-out', transformed_roi_mask, '-interp', 'nearestneighbour'])
            run1_struct2standard_mat = f"{p_id}/analysis/susceptibility/fnirt_test/3/run1_struct2standard.mat"
            run1_warp_struct2standard = f"{p_id}/analysis/susceptibility/fnirt_test/3/run1_warp_struct2standard.nii.gz"
            temp_file2 = f'{p_id}/analysis/susceptibility/fnirt_test/3/temp_file2.nii.gz'
            subprocess.run(['flirt', '-in', structural_brain, '-ref', mni_template, '-omat', run1_struct2standard_mat])
            subprocess.run(['fnirt', f'--in={structural_brain}', f'--ref={mni_template}', f'--aff={run1_struct2standard_mat}', '--config=T1_2_MNI152_2mm', '--lambda=400,200,150,75,60,45', f'--cout={run1_warp_struct2standard}'])
            subprocess.run(['applywarp', f'--in={averaged_run}', f'--ref={mni_template}', f'--warp={rl_warp_struct2standard}', f'--premat={roi_transformation}', f'--out={temp_file2}'])
            standard_roi_mask = f'{p_id}/analysis/susceptibility/fnirt_test/3/standard_roi_mask.nii.gz'
            subprocess.run(['applywarp', f'--in={transformed_roi_mask}', f'--ref={mni_template}', f'--warp={run1_warp_struct2standard}', f'--out={standard_roi_mask}'])
            standard_pa_fieldmaps_bin = f'{p_id}/analysis/susceptibility/fnirt_test/3/standard_pa_fieldmaps_bin.nii.gz'
            if not os.path.exists(standard_pa_fieldmaps_bin):
                subprocess.run(['fslmaths', standard_pa_fieldmaps, '-thr', '100', '-bin', standard_pa_fieldmaps_bin])
            standard_rl_fieldmaps_bin = os.path.join(f'{p_id}/analysis/susceptibility/fnirt_test/3/standard_rl_fieldmaps_bin.nii.gz')
            if not os.path.exists(standard_rl_fieldmaps_bin):
                subprocess.run(['fslmaths', standard_rl_fieldmaps, '-thr', '100', '-bin', standard_rl_fieldmaps_bin])
            pa_bin_inv = f'{p_id}/analysis/susceptibility/fnirt_test/3/pa_bin_inv.nii.gz'
            if not os.path.exists(pa_bin_inv):
                subprocess.run(['fslmaths', standard_pa_fieldmaps_bin, '-sub', '1', '-abs', pa_bin_inv])
            rl_bin_inv = f'{p_id}/analysis/susceptibility/fnirt_test/3/rl_bin_inv.nii.gz'
            if not os.path.exists(rl_bin_inv):
                subprocess.run(['fslmaths', standard_rl_fieldmaps_bin, '-sub', '1', '-abs', rl_bin_inv])
            pa_result = subprocess.run(['fslstats', standard_roi_mask, '-k', pa_bin_inv, '-V'], capture_output=True, text=True)
            if pa_result.returncode == 0:
                pa_result_output = pa_result.stdout.strip()
            else:
                print("Error executing fslstats command.")
            pa_result_output_values = pa_result_output.split()
            pa_voxels_outside = float(pa_result_output_values[0])
            rl_result = subprocess.run(['fslstats', standard_roi_mask, '-k', rl_bin_inv, '-V'], capture_output=True, text=True)
            if rl_result.returncode == 0:
                rl_result_output = rl_result.stdout.strip()
            else:
                print("Error executing fslstats command.")
            rl_result_output_values = rl_result_output.split()
            rl_voxels_outside = float(rl_result_output_values[0])
            result2 = subprocess.run(['fslstats', standard_roi_mask, '-V'], capture_output=True, text=True)
            if result2.returncode == 0:
                result2_output = result2.stdout.strip()
            else:
                print("Error executing fslstats command.")
            result2_output_values = result2_output.split()
            total_voxels_in_roi = float(result2_output_values[0])
            percentage_outside_pa = (pa_voxels_outside / total_voxels_in_roi) * 100
            percentage_outside_pa = round(percentage_outside_pa, 2)
            percentage_outside_pa_list.append(percentage_outside_pa)
            percentage_outside_rl = (rl_voxels_outside / total_voxels_in_roi) * 100
            percentage_outside_rl = round(percentage_outside_rl, 2)
            percentage_outside_rl_list.append(percentage_outside_rl)
            pa_trimmed_roi_mask = f"{p_id}/analysis/susceptibility/fnirt_test/3/pa_trimmed_roi_mask.nii.gz"
            rl_trimmed_roi_mask = f"{p_id}/analysis/susceptibility/fnirt_test/3/rl_trimmed_roi_mask.nii.gz"
            if not os.path.exists(pa_trimmed_roi_mask) or not os.path.exists(rl_trimmed_roi_mask):
                subprocess.run(['fslmaths', standard_roi_mask, '-mul', standard_pa_fieldmaps_bin, pa_trimmed_roi_mask])
                subprocess.run(['fslmaths', standard_roi_mask, '-mul', standard_rl_fieldmaps_bin, rl_trimmed_roi_mask])
            def calculate_ssim(image1_path, image2_path, ssim_output_path):
                """Function to calculate SSIM between two NIfTI images and save the SSIM map."""
                image1_nii = nib.load(image1_path)
                image2_nii = nib.load(image2_path)
                image1 = image1_nii.get_fdata()
                image2 = image2_nii.get_fdata()
                if image1.shape != image2.shape:
                    raise ValueError("Input images must have the same dimensions for SSIM calculation.")
                ssim_index, ssim_map = ssim(image1, image2, full=True, data_range=image1.max() - image1.min())
                ssim_map_nifti = nib.Nifti1Image(ssim_map, affine=image1_nii.affine, header=image1_nii.header)
                nib.save(ssim_map_nifti, ssim_output_path)
                print(f"SSIM Index: {ssim_index}")
                print(f"SSIM map saved to: {ssim_output_path}")
                return ssim_index
            ssim_output_path = f"{p_id}/analysis/susceptibility/fnirt_test/3/ssim_map.nii.gz"
            if not os.path.exists(ssim_output_path):
                print(f"Calculating SSIM between PA and RL images for {p_id}...")
                ssim_index = calculate_ssim(standard_rl_fieldmaps, standard_pa_fieldmaps, ssim_output_path)
                print(f'SSIM between PA and RL images for {p_id} successfully calculated.')
            else:
                print(f"SSIM between PA and RL images for {p_id} already calculated. Skipping process.")
            binarised_ssim_output_path = f"{p_id}/analysis/susceptibility/fnirt_test/3/binarised_ssim_mask.nii.gz"
            if not os.path.exists(binarised_ssim_output_path):
                print(f'Binarising {p_id} SSIM mask...')
                subprocess.run(["fslmaths", ssim_output_path, "-thr", "0.8", "-binv", binarised_ssim_output_path])
                print(f'{p_id} SSIM mask successfully binarised.')
            else:
                print(f'{p_id} SSIM mask already binarised. Skipping process.')
            print(f'Counting voxels in binarised SSIM mask...')
            voxels_in_whole_mask = subprocess.run(["fslstats", binarised_ssim_output_path, "-V"], capture_output=True, text=True).stdout.split()[0]
            print(f'Voxels in whole binarised SSIM mask for {p_id}:', voxels_in_whole_mask)
            intersection_mask_path = f'{p_id}/analysis/susceptibility/fnirt_test/3/ssim_roi_intersect.nii.gz'
            if not os.path.exists(intersection_mask_path):
                print(f'Creating intersect mask of SSIM and ROI for {p_id}...')
                subprocess.run(["fslmaths", binarised_ssim_output_path, "-mas", standard_roi_mask, intersection_mask_path])
                print(f'Intersect mask of SSIM and ROI for {p_id} successfully created.')
            else:
                print(f'Intersect mask of SSIM and ROI for {p_id} already exists. Skipping process.')
            print(f'Counting voxels in transformed ROI mask for {p_id}...')
            voxels_in_roi_in_mask = subprocess.run(["fslstats", intersection_mask_path, "-V"], capture_output=True, text=True).stdout.split()[0]
            print(f'Number of transformed ROI mask voxels present in SSIM intersect mask for {p_id}:', voxels_in_roi_in_mask)
            voxels_in_roi_in_mask = float(voxels_in_roi_in_mask)
            perc_roi_voxels_in_mask = (voxels_in_roi_in_mask / total_voxels_in_roi) * 100
            ssim_df = pd.DataFrame({'p_id': p_id, 'ssim_index': ssim_index, 'voxels_in_bin_ssim_mask': voxels_in_whole_mask, 'perc_roi_voxels_in_bin_ssim_mask': perc_roi_voxels_in_mask})
            ssim_df.tocsv(f'{p_id}/analysis/susceptibility/fnirt_test/3/ssim_df.txt', sep='\t', index=False)
            group_ssim_df = pd.concat([group_ssim_df, ssim_df], ignore_index=True)
    group_ssim_df.to_csv('group/susceptibility/fnirt_test/3/group_ssim_df.txt', sep='\t', index=False)

    column_headers = ['p_id', 'sequence', 'value']
    group_voxel_intensity_df = pd.DataFrame(columns = column_headers)   
    for p_id in participants_to_iterate:
        if p_id in good_participants:             
            def extract_voxel_intensities(epi_image_path, mask_image_path):
                epi_img = nib.load(epi_image_path)
                epi_data = epi_img.get_fdata()
                mask_img = nib.load(mask_image_path)
                mask_data = mask_img.get_fdata()
                mask_data = mask_data > 0
                roi_voxel_intensities = epi_data[mask_data]
                voxel_intensity_list = roi_voxel_intensities.tolist()
                return voxel_intensity_list
            pa_voxel_intensities = extract_voxel_intensities(standard_pa_fieldmaps, pa_trimmed_roi_mask)
            rl_voxel_intensities = extract_voxel_intensities(standard_rl_fieldmaps, rl_trimmed_roi_mask)
            pa_voxel_intensities_mean = np.mean(pa_voxel_intensities)
            rl_voxel_intensities_mean = np.mean(rl_voxel_intensities)
            print(f"Average voxel intensity within ROI for {p_id} PA fieldmap sequence: {pa_voxel_intensities_mean}")
            print(f"Average voxel intensity within ROI for {p_id} RL fieldmap sequence: {rl_voxel_intensities_mean}")
            values = pa_voxel_intensities + rl_voxel_intensities
            sequence = ['pa'] * len(pa_voxel_intensities) + ['rl'] * len(rl_voxel_intensities)
            subject = [f'{p_id}'] * len(pa_voxel_intensities) + [f'{p_id}'] * len(rl_voxel_intensities)
            voxel_intensity_df = pd.DataFrame({'p_id': subject, 'sequence': sequence, 'value': values})
            voxel_intensity_df.to_csv(f'{p_id}/analysis/susceptibility/fnirt_test/3/voxel_intensity_df.txt', sep='\t', index=False)
            group_voxel_intensity_df = pd.concat([group_voxel_intensity_df, voxel_intensity_df], ignore_index=True)
    group_voxel_intensity_df.to_csv('group/susceptibility/fnirt_test/3/group_voxel_intensity_df.txt', sep='\t', index=False)
    print('Percentage of ROI voxels in signal dropout regions for each of the 13 good participants in PA fieldmap sequence:', percentage_outside_pa_list)
    print('Percentage of ROI voxels in signal dropout regions for each of the 13 good participants in RL fieldmap sequence:', percentage_outside_rl_list)
    
    pa_means = []
    rl_means= []
    p_values = []
    pa_std_errors = []
    rl_std_errors = []
    for p_id in participants_to_iterate:
        if p_id in good_participants:
            filtered_pa = group_voxel_intensity_df[(group_voxel_intensity_df['p_id'] == f'{p_id}') & (group_voxel_intensity_df['sequence'] == 'pa')]
            mean_value_pa = filtered_pa['value'].mean()
            pa_means.append(mean_value_pa)
            filtered_rl = group_voxel_intensity_df[(group_voxel_intensity_df['p_id'] == f'{p_id}') & (group_voxel_intensity_df['sequence'] == 'rl')]
            mean_value_rl = filtered_rl['value'].mean()
            rl_means.append(mean_value_rl)
            anderson_pa = stats.anderson(filtered_pa['value'])
            print(f"Anderson-Darling test for PA sequence values: Statistic={anderson_pa.statistic}, Critical Values={anderson_pa.critical_values}, Significance Levels={anderson_pa.significance_level}")
            anderson_rl = stats.anderson(filtered_rl['value'])
            print(f"Anderson-Darling test for RL sequence values: Statistic={anderson_rl.statistic}, Critical Values={anderson_rl.critical_values}, Significance Levels={anderson_rl.significance_level}")
            significance_level = 0.05
            is_pa_normal = anderson_pa.statistic < anderson_pa.critical_values[
                anderson_pa.significance_level.tolist().index(significance_level * 100)]
            is_rl_normal = anderson_rl.statistic < anderson_rl.critical_values[
                anderson_rl.significance_level.tolist().index(significance_level * 100)]
            if is_pa_normal and is_rl_normal:
                print(f'Running t-test for {p_id}...')
                _, p_value = stats.ttest_ind(filtered_pa['value'], filtered_rl['value'], equal_var=False)
                p_values.append(p_value)
            else:
                print(f'Running Mann Whitney U test for {p_id}...')
                _, p_value = stats.mannwhitneyu(filtered_pa['value'], filtered_rl['value'], alternative='two-sided')
                p_values.append(p_value)
            pa_std_error = np.std(filtered_pa['value']) / np.sqrt(len(filtered_pa['value']))
            pa_std_errors.append(pa_std_error)
            rl_std_error = np.std(filtered_rl['value']) / np.sqrt(len(filtered_rl['value']))
            rl_std_errors.append(rl_std_error)
    plot_data = pd.DataFrame({
        'Participant': good_participants * 2,
        'Mean_Value': pa_means + rl_means,
        'Sequence': ['Corrected'] * len(good_participants) + ['Uncorrected'] * len(good_participants),
        'Significance': ['' for _ in range(len(good_participants) * 2)],
        'Std_Error': pa_std_errors + rl_std_errors
    })
    for idx, p_value in enumerate(p_values):
        if p_value < 0.001:
            plot_data.at[idx, 'Significance'] = '***'
        elif p_value < 0.01:
            plot_data.at[idx, 'Significance'] = '**'
        elif p_value < 0.05:
            plot_data.at[idx, 'Significance'] = '*'
    mean_plot = (
        ggplot(plot_data, aes(x='Participant', y='Mean_Value', fill='Sequence')) +
        geom_bar(stat='identity', position='dodge') +
        geom_errorbar(aes(ymin='Mean_Value - Std_Error', ymax='Mean_Value + Std_Error'), position=position_dodge(width=0.9), width=0.2, color='black') +
        theme_classic() +
        labs(title='Mean SCC Voxel Intensity', x='Participant', y='Mean Value') +
        theme(axis_text_x=element_text(rotation=45, hjust=1), text=element_text(size=12, color='blue'), axis_title=element_text(size=14, face='bold')) +
        scale_y_continuous(expand=(0, 0), limits=[0,350]) +
        geom_text(
            aes(x='Participant', y='Mean_Value', label='Significance'),
            position=position_dodge(width=0.9),
            color='black',
            size=12,
            ha='center',
            va='bottom',
            show_legend=False))
    mean_plot.save('group/susceptibility/fnirt_test/3/mean_plot.png')
    pa_means_overall = np.mean(pa_means)
    rl_means_overall = np.mean(rl_means)
    pa_std_error_overall = np.std(pa_means) / np.sqrt(len(pa_means))
    rl_std_error_overall = np.std(rl_means) / np.sqrt(len(rl_means))
    _, pa_means_overall_shap_p = stats.shapiro(pa_means)
    _, rl_means_overall_shap_p = stats.shapiro(rl_means)
    if pa_means_overall_shap_p > 0.5 and rl_means_overall_shap_p > 0.5:
        print(f'Running t-test for {p_id}...')
        _, p_value = stats.ttest_ind(pa_means, rl_means)
    else:
        print(f'Running Mann-Whitney U test for {p_id}...')
        _, p_value = stats.mannwhitneyu(pa_means, rl_means)
    plot_data = pd.DataFrame({'Sequence': ['PA', 'RL'], 'Mean': [pa_means_overall, rl_means_overall], 'Std_Error': [pa_std_error_overall, rl_std_error_overall]})
    overall_mean_plot = (ggplot(plot_data, aes(x='Sequence', y='Mean')) + 
                        geom_bar(stat='identity', position='dodge') +
                        geom_errorbar(aes(ymin='Mean - Std_Error', ymax='Mean + Std_Error'), width=0.2, color='black') +
                        theme_classic() +
                        labs(title='Mean of Voxel Intensities Across Participants.') +
                        scale_y_continuous(expand=(0, 0), limits=[0,350])
                        )
    if p_value < 0.001:
        overall_mean_plot = overall_mean_plot + annotate("text", x=1.5, y=max(plot_data['Mean']) + 40, label="***", size=16, color="black") + \
            annotate("segment", x=1, xend=2, y=max(plot_data['Mean']) +30, yend=max(plot_data['Mean']) + 30, color="black")
    elif p_value < 0.01:
        overall_mean_plot = overall_mean_plot + annotate("text", x=1.5, y=max(plot_data['Mean']) + 40, label="**", size=16, color="black") + \
            annotate("segment", x=1, xend=2, y=max(plot_data['Mean']) +30, yend=max(plot_data['Mean']) + 30, color="black")
    elif p_value < 0.05:
        overall_mean_plot = overall_mean_plot + annotate("text", x=1.5, y=max(plot_data['Mean']) + 40, label="*", size=16, color="black") + \
            annotate("segment", x=1, xend=2, y=max(plot_data['Mean']) +30, yend=max(plot_data['Mean']) + 30, color="black")    
    overall_mean_plot.save('group/susceptibility/fnirt_test/3/overall_mean_plot.png')

#endregion