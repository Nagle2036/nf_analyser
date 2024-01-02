# -*- coding: utf-8 -*-

###TO DO###
# Create Python script to automatically generate PSC / thermometer level plots and blindedly show whether group allocation (a/b) matched training directions from scan.
# Organise files in BIDS format.
# Upload analysis outputs back to Box account. Or maybe not. Might be best to leave this, in order to protect Box data in case anything gets messed up.
# Add percentage completion metric.
# Count files present in participant folder
# Output mri_processor.py Bash terminal outputs / prints into .txt log file

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

#region PREPARATION.
p_id = input("Enter the participant's ID (e.g. P001).\n")
working_dir = os.getcwd()
p_id_folder = os.path.join(os.getcwd(), p_id)
if not os.path.exists(p_id_folder):
    subprocess.run(['mkdir', f'{p_id}'])
susceptibility_folder = os.path.join(os.getcwd(), p_id, "analysis", "susceptibility")
if not os.path.exists(susceptibility_folder):
    subprocess.run(['mkdir', f'{p_id}/susceptibility'])
scc_analysis_folder = os.path.join(os.getcwd(), p_id, "analysis", "scc")
if not os.path.exists(scc_analysis_folder):
    subprocess.run(['mkdir', f'{p_id}/analysis/scc'])
group_folder = os.path.join(os.getcwd(), "group")
if not os.path.exists(group_folder):
    subprocess.run(['mkdir', 'group'])
mc_test_folder = os.path.join(os.getcwd(), "group", "mc_test")
if not os.path.exists(mc_test_folder):
    subprocess.run(['mkdir', 'group/ms_test'])
    
#endregion

#region DOWNLOAD BOX FILES TO SERVER.

answer2 = input("Would you like to update your files from Box? (y/n)\n")
if answer2 == 'y':
    
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
        while True:
            download_files_from_folder(parent_folder, save_directory, downloaded_files)
            # Get the updated folder information to check if all files have been downloaded
            parent_folder_info = client.folder(parent_folder.id).get()
            item_collection = parent_folder_info["item_collection"]
            total_items = item_collection["total_count"]
            # Check if all files have been downloaded
            if len(downloaded_files) == total_items:
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

#region SCC BOLD ANALYSIS.

answer3 = input("Would you like to execute SCC BOLD analysis? (y/n)\n")
if answer3 == 'y':

    # Step 1: Copy Run 1-4 dicoms into separate folders.
    path = os.path.join(os.getcwd(), p_id, "data", "neurofeedback")
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
        run01_folder = os.path.join(os.getcwd(), p_id, "analysis", "scc", "run01_dicoms")
        run02_folder = os.path.join(os.getcwd(), p_id, "analysis", "scc", "run02_dicoms")
        run03_folder = os.path.join(os.getcwd(), p_id, "analysis", "scc", "run03_dicoms")
        run04_folder = os.path.join(os.getcwd(), p_id, "analysis", "scc", "run04_dicoms")
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

    # Step 2: Convert DICOM files to Nifti format.
    destination_folder = os.path.join(os.getcwd(), p_id, "analysis", "scc", "run01_dicoms")
    output_folder = os.path.join(os.getcwd(), p_id, "analysis", "scc")
    output_file = os.path.join(output_folder, "run01.nii")
    if not os.path.exists(output_file):
        print("Converting Run01 DICOM files to Nifti format...")
        subprocess.run(['dcm2niix', '-o', output_folder, '-f', 'run01', '-b', 'n', destination_folder])
        print("Run01 DICOM files converted to Nifti format.")
    else:
        print("Run01 Nifti file already exists. Skipping conversion.")
    destination_folder = os.path.join(os.getcwd(), p_id, "analysis", "scc", "run02_dicoms")
    output_folder = os.path.join(os.getcwd(), p_id, "analysis", "scc")
    output_file = os.path.join(output_folder, "run02.nii")
    if not os.path.exists(output_file):
        print("Converting Run02 DICOM files to Nifti format...")
        subprocess.run(['dcm2niix', '-o', output_folder, '-f', 'run02', '-b', 'n', destination_folder])
        print("Run02 DICOM files converted to Nifti format.")
    else:
        print("Run02 Nifti file already exists. Skipping conversion.")
    destination_folder = os.path.join(os.getcwd(), p_id, "analysis", "scc", "run03_dicoms")
    output_folder = os.path.join(os.getcwd(), p_id, "analysis", "scc")
    output_file = os.path.join(output_folder, "run03.nii")
    if not os.path.exists(output_file):
        print("Converting Run03 DICOM files to Nifti format...")
        subprocess.run(['dcm2niix', '-o', output_folder, '-f', 'run03', '-b', 'n', destination_folder])
        print("Run03 DICOM files converted to Nifti format.")
    else:
        print("Run03 Nifti file already exists. Skipping conversion.")
    destination_folder = os.path.join(os.getcwd(), p_id, "analysis", "scc", "run04_dicoms")
    output_folder = os.path.join(os.getcwd(), p_id, "analysis", "scc")
    output_file = os.path.join(output_folder, "run04.nii")
    if not os.path.exists(output_file):
        print("Converting Run04 DICOM files to Nifti format...")
        subprocess.run(['dcm2niix', '-o', output_folder, '-f', 'run04', '-b', 'n', destination_folder])
        print("Run04 DICOM files converted to Nifti format.")
    else:
        print("Run04 Nifti file already exists. Skipping conversion.")
    
    # Step 3: Check Nifti orientation.
    runs = ['run01', 'run02', 'run03', 'run04']
    for run in runs:
        png_path = f'{p_id}/analysis/scc/{run}.png'
        nifti_path = f'{p_id}/analysis/scc/{run}.nii'
        if not os.path.exists(png_path):
            print(f"Saving {run} Nifti as PNG...")
            save_png = subprocess.run(['fsleyes', 'render', '--scene', 'ortho', '-of', png_path, nifti_path], capture_output=True, text=True)
            if save_png.returncode == 0:
                print("Screenshot saved as", png_path)
            else:
                print("Error encountered:", save_png.stderr)
        else:
            print('PNG files already created. Skipping conversion.')
    answer = input(f"Check PNG files in {p_id}/analysis/scc to see whether Niftis are in correct orientation. Anterior of brain should be facing right in sagittal view, right and left of brain should be swapped in coronal and transverse views, and anterior of the brain should be facing towards the top of the image in the transverse view. Other aspects should be easily viewable. Does all appear correct? (y/n)\n")
    if answer != 'y':
        print("Error: please first address incorrect Nifti orientation using 'fslreorient2std' or 'fslswapdim' commands before proceeding.\n")
        sys.exit()

    # Step 4: Brain extract structural Nifti.
    src_folder = os.path.join(path, cisc_folder)
    destination_folder = f'{p_id}/analysis/scc'
    new_filename = 'structural.nii'
    if not os.path.exists(f'{p_id}/analysis/scc/structural.nii'):
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
    bet_path = os.path.join(os.getcwd(), p_id, "analysis", "scc", "structural_brain.nii")
    structural_path = os.path.join(os.getcwd(), p_id, "analysis", "scc", "structural.nii")
    if not os.path.exists(f'{p_id}/analysis/scc/strutural_brain.nii.gz'):
        print("Performing brain extraction on structural image...")
        subprocess.run(['bet', structural_path, bet_path, '-m', '-R'])
        print("Structural image brain extracted.")
    else:
        print("Structural image already brain extracted. Skipping process.")

    # Step 5: Create onset files.
    onsetfile_sub = f'{p_id}/analysis/scc/onsetfile_sub.txt'
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
    onsetfile_guilt = f'{p_id}/analysis/scc/onsetfile_guilt.txt'
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
    onsetfile_indig = f'{p_id}/analysis/scc/onsetfile_indig.txt'
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

    # Step 6: Find optimal motion correction parameters.
    for run in runs:
        input_path = os.path.join(os.getcwd(), p_id, 'analysis', 'scc', f'{run}.nii')
        output_path = os.path.join(os.getcwd(), 'group', 'ms_test', f'{p_id}_{run}_ms_test')
        text_output_path = os.path.join(os.getcwd(), 'group', 'ms_test', f'{p_id}_{run}_ms_test.txt') 
        if not os.path.exists(output_path):
            print(f"Finding optimal motion correction parameters for {run} data...")
            subprocess.run(['fsl_motion_outliers', '-i', input_path, '-o', output_path, '-s', text_output_path, '--fd', '--thresh=0.9'])
            try:
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
                result_file = os.path.join(os.getcwd(), 'group', 'ms_test', 'ms_test_master.txt')
                file_exists = True
                try:
                    with open(result_file, "r") as f:
                        pass
                except FileNotFoundError:
                    file_exists = False
                with open(result_file, "a") as f:
                    if not file_exists:
                        f.write("p_id run use_middle_vol use_sinc_interp\n")
                    f.write(f"{p_id} {run} {use_middle_vol} {use_sinc_interp}\n")
            except FileNotFoundError:
                use_middle_vol = 1
                use_sinc_interp = 0
                result_file = os.path.join(os.getcwd(), 'group', 'ms_test', 'ms_test_master.txt')
                file_exists = True
                try:
                    with open(result_file, "r") as f:
                        pass
                except FileNotFoundError:
                    file_exists = False
                with open(result_file, "a") as f:
                    if not file_exists:
                        f.write("p_id run use_middle_vol use_sinc_interp\n")
                    f.write(f"{p_id} {run} {use_middle_vol} {use_sinc_interp}\n")
        else:
            print("Motion correction optimisation already performed. Skipping process.")
    
    # Step 7: Perform motion correction. 
    for run in runs:
        input_path = os.path.join(os.getcwd(), p_id, 'analysis', 'scc', f'{run}.nii')
        output_path = os.path.join (os.getcwd(), p_id, 'analysis', 'scc', f'{run}_mc') 
        if not os.path.exists(output_path):
            print(f"Performing motion correction on {run} data...")
            use_middle_vol_values = []
            use_sinc_interp_values = []
            with open(f"{result_file}", "r") as f:
                next(f)
                for line in f:
                    parts = line.split()
                    use_middle_vol_value = int(parts[2])
                    use_sinc_interp_value = int(parts[3])
                    use_middle_vol_values.append(use_middle_vol_value)
                    use_sinc_interp_values.append(use_sinc_interp_value)
            if all(use_middle_vol == 1 for use_middle_vol in use_middle_vol_values) and all(use_sinc_interp == 0 for use_sinc_interp in use_sinc_interp_values):
                subprocess.run(['mcflirt', '-in', input_path, '-out', output_path, '-mats'])
                print(f"{run} motion corrected with middle volume reference and no sinc interpolation.")
            elif all(use_middle_vol == 1 for use_middle_vol in use_middle_vol_values) and all(use_sinc_interp == 1 for use_sinc_interp in use_sinc_interp_values):
                subprocess.run(['mcflirt', '-in', input_path, '-out', output_path, '-stages', '4', '-mats'])
                print(f"{run} motion corrected with middle volume reference and sinc interpolation.")
            elif all(use_middle_vol == 0 for use_middle_vol in use_middle_vol_values) and all(use_sinc_interp == 0 for use_sinc_interp in use_sinc_interp_values):
                subprocess.run(['mcflirt', '-in', input_path, '-out', output_path, '-meanvol', '-mats'])
                print(f"{run} motion corrected with mean volume reference and no sinc interpolation.")
            elif all(use_middle_vol == 0 for use_middle_vol in use_middle_vol_values) and all(use_sinc_interp == 1 for use_sinc_interp in use_sinc_interp_values):
                subprocess.run(['mcflirt', '-in', input_path, '-out', output_path, '-meanvol', '-stages', '4', '-mats'])
                print(f"{run} motion corrected with mean volume reference and sinc interpolation.")
            else:
                print("Error: Not all use_middle_vol and use_sinc_interp values are 0 or 1. Cannot run MCFLIRT.")
                sys.exit()
        else:
            print(f"{run} already motion corrected. Skipping process.")

    # Step 8: Perform motion scrubbing.
    scrubbed_vols = []
    for run in runs:
        input_path = os.path.join (os.getcwd(), p_id, 'analysis', 'scc', f'{run}_mc')
        output_path = os.path.join (os.getcwd(), p_id, 'analysis', 'scc', f'{run}_mc_ms')
        text_output_path = os.path.join (os.getcwd(), p_id, 'analysis', 'scc', f'{run}_scrubbed_volumes.txt')
        if not os.path.exists(output_path):
            print(f"Performing motion scrubbing on {run} data...")
            subprocess.run(['fsl_motion_outliers', '-i', input_path, '-o', output_path, '-s', text_output_path, '--nomoco'])
            print(f'{run} motion scrubbed.')
        else:
            print (f'{run} already motion scrubbed. Skipping process.')
        with open(output_path, 'r') as file:
            first_row = file.readline().strip()
            print(first_row) #get rid
            num_columns = len(first_row.split('\t'))
            print(num_columns) #get rid
            scrubbed_vols.append(num_columns)
            print(scrubbed_vols) #get rid
    sum_scrubbed_vols = sum(scrubbed_vols)
    print(sum_scrubbed_vols) #get rid
    scrubbed_vols_perc = (sum_scrubbed_vols / 896) * 100
    print(scrubbed_vols_perc) #get rid
    if scrubbed_vols_perc > 15:
        print(f'Total percentage of volumes scrubbed is {scrubbed_vols_perc}%. This exceeds tolerable threshold of 15%. Remove participant from analysis.')
    else:
        print(f'Total percentage of volumes scrubbed is {scrubbed_vols_perc}%. This is within tolerable threshold of 15%. Analysis can continue.')
        



#endregion

#region SUSCEPTIBILITY.

answer4 = input("Would you like to execute susceptibility artifact analysis? (y/n)\n")
if answer4 == 'y':

    # Step 1: Find the 'CISC' folder in the 'neurofeedback' directory
    path = os.path.join(os.getcwd(), p_id, "data", "neurofeedback")
    cisc_folder = None
    for folder_name in os.listdir(path):
        if "CISC" in folder_name:
            cisc_folder = folder_name
            break
    if cisc_folder is None:
        print("No 'CISC' folder found in the 'neurofeedback' directory.")
        exit(1)

    # Step 2: Identify dicom series with 210 files
    series_numbers = []
    cisc_path = os.path.join(path, cisc_folder)
    for filename in os.listdir(cisc_path):
        if filename.endswith(".dcm"):
            series_number = filename.split("_")[1]
            series_numbers.append(series_number)
    series_counts = {series_number: series_numbers.count(series_number) for series_number in set(series_numbers)}
    series_with_210_files = [series_number for series_number, count in series_counts.items() if count == 210]
    if len(series_with_210_files) == 0:
        print("No dicom series with exactly 210 .dcm files found.")
        exit(1)

    # Step 3: Copy files from Run 1 to new folder
    if len(series_with_210_files) == 2:
        series_to_copy = min(series_with_210_files)
    else:
        series_to_copy = input("Input required: more than two runs contain 210 dicoms. Please specify which sequence number is Run 1 (e.g. 08, 09, 11).\n")
    destination_folder = os.path.join(os.getcwd(), p_id, "analysis", "susceptibility", "run01_dicoms")
    os.makedirs(destination_folder, exist_ok=True)
    existing_files = os.listdir(destination_folder)
    files_to_copy = []
    for filename in os.listdir(cisc_path):
        if filename.endswith(".dcm") and filename.split("_")[1] == series_to_copy:
            if filename not in existing_files:
                files_to_copy.append(filename)
    if len(files_to_copy) == 0:
        print("DICOM files already present in the destination folder. No files copied.")
    else:
        for filename in files_to_copy:
            source_path = os.path.join(cisc_path, filename)
            destination_path = os.path.join(destination_folder, filename)
            shutil.copy2(source_path, destination_path)
        print("DICOM files copied successfully.")

    # Step 4: Convert DICOM files to Nifti format
    output_folder = os.path.join(os.getcwd(), p_id, "analysis", "susceptibility")
    output_file = os.path.join(output_folder, "run01.nii")
    if not os.path.exists(output_file):
        subprocess.run(['dcm2niix', '-o', output_folder, '-f', 'run01', '-b', 'n', destination_folder])
        print("DICOM files converted to Nifti format.")
    else:
        print("Output file already exists. Skipping conversion.")

    # Step 5: Merge volumes using fslmaths
    nifti_file = os.path.join(output_folder, "run01.nii")
    averaged_file = os.path.join(output_folder, "run01_averaged.nii.gz")
    if not os.path.exists(averaged_file):
        subprocess.run(['fslmaths', nifti_file, '-Tmean', averaged_file])
        print("Volumes merged successfully.")
    else:
        print("Output file already exists. Skipping merging operation.")

    # Step 6: Read the .roi file and extract the voxel coordinates
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
    roi_file = f'{cisc_path}/depression_neurofeedback/target_folder_run-1/depnf_run-1.roi'
    voxel_coordinates = read_roi_file(roi_file)

    # Step 7: Get the dimensions of the functional data and create the subject space ROI.
    functional_image = f'{p_id}/analysis/susceptibility/run01_averaged.nii.gz'
    functional_image_info = nib.load(functional_image)
    functional_dims = functional_image_info.shape
    binary_volume = np.zeros(functional_dims)
    for voxel in voxel_coordinates:
        x, y, z = voxel
        binary_volume[x, y, z] = 1
    binary_volume = np.flip(binary_volume, axis=1) #flipping mask across the y-axis
    functional_affine = functional_image_info.affine
    binary_nifti = nib.Nifti1Image(binary_volume, affine=functional_affine)
    nib.save(binary_nifti, f'{p_id}/analysis/susceptibility/subject_space_ROI.nii.gz')

    # Step 8: Save screenshot of the subject-space ROI on EPI image.
    betted_file = os.path.join(output_folder, "run01_averaged_betted.nii.gz")
    if not os.path.exists(betted_file):
        subprocess.run(['bet', f'{p_id}/analysis/susceptibility/run01_averaged.nii.gz', betted_file, '-R'])
        print("Brain extraction completed.")
    else:
        print("Brain-extracted file already exists. Skipping BET operation.")
    functional_image_betted = f'{p_id}/analysis/susceptibility/run01_averaged_betted.nii.gz'
    binary_nifti_image = f'{p_id}/analysis/susceptibility/subject_space_ROI.nii.gz'
    screenshot_file = f'{p_id}/analysis/susceptibility/ROI_on_EPI.png'
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

    # Step 9: Calculate Percentage of ROI Voxels in Dropout Regions.
    bin_file = os.path.join(output_folder, "run01_averaged_betted_bin.nii.gz")
    if not os.path.exists(bin_file):
        threshold = input("Please enter a threshold value for functional image binarisation.\n")
        subprocess.run(['fslmaths', f'{p_id}/analysis/susceptibility/run01_averaged_betted.nii.gz', '-thr', threshold, '-bin', bin_file])
        print("EPI binarisation completed.")
    else:
        print("Binarised EPI already present. Skipping binarisation operation.")
    inverse_file = os.path.join(output_folder, "run01_averaged_betted_bin_inverse.nii.gz")
    if not os.path.exists(inverse_file):
        subprocess.run(['fslmaths', f'{p_id}/analysis/susceptibility/run01_averaged_betted_bin.nii.gz', '-sub', '1', '-abs', inverse_file])
        print("Binarised EPI successfully inverted.")
    else:
        print("Inverted binary EPI already present. Skipping inversion procedure.")
    result2 = subprocess.run(['fslstats', f'{p_id}/analysis/susceptibility/subject_space_ROI.nii.gz', '-k', f'{p_id}/susceptibility/run01_averaged_betted_bin_inverse.nii.gz', '-V'], capture_output=True, text=True)
    if result2.returncode == 0:
        result2_output = result2.stdout.strip()
    else:
        print("Error executing second fslstats command.")
    result2_output_values = result2_output.split()
    voxels_outside = float(result2_output_values[0])
    result3 = subprocess.run(['fslstats', f'{p_id}/analysis/susceptibility/subject_space_ROI.nii.gz', '-V'], capture_output=True, text=True)
    if result3.returncode == 0:
        result3_output = result3.stdout.strip()
    else:
        print("Error executing first fslstats command.")
    result3_output_values = result3_output.split()
    total_voxels_in_roi = float(result3_output_values[0])
    percentage_outside = (voxels_outside / total_voxels_in_roi) * 100
    percentage_file = os.path.join(output_folder, "percentage_outside.txt")
    if not os.path.exists(percentage_file):
        line1 = f"Threshold: {threshold}\n"
        line2 = f"Percentage of ROI voxels in signal dropout regions: {percentage_outside}"
        with open(percentage_file, "w") as file:
            file.writelines([line1, line2])
        print("Percentage of voxels outside the signal dropout mask saved to", percentage_file)
#endregion