# -*- coding: utf-8 -*-

###TO DO###
# Create Python script to automatically generate PSC / thermometer level plots and blindedly show whether group allocation (a/b) matched training directions from scan.
# Organise files in BIDS format.
# Register to GitHub for version control.
# Upload analysis outputs back to Box account.
# Add percentage completion metric

# %% IMPORT PACKAGES.

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
import nibabel as nib
import matplotlib.pyplot as plt

# %% INSTRUCTIONS.
print("\nWelcome to the MRI analysis processor. Please complete the following before proceeding:\n")
print("1. Upload the participant's data to Box.\n")
print("2. In the Bash terminal, change the working directory to the participant_data folder within the cisc2 drive.\n")
answer = input("Have the above steps been completed? (y/n)\n")
if answer != 'y':
    print('Error: please complete prerequisite steps before proceeding.\n')
    sys.exit()

# %% INPUT INFORMATION.
p_id = input("Enter the participant's ID (e.g. P001).\n")

# %% CREATE FOLDERS.
working_dir = os.getcwd()
subprocess.run(['mkdir', f'{p_id}'])
subprocess.run(['mkdir', f'{p_id}/susceptibility'])

# %% DOWNLOAD BOX FILES TO SERVER.

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
            # Check if the access token needs refreshing
            if oauth.access_token_expires_at - time.time() < 60:  # Refresh if token expires within 60 seconds
                oauth.refresh(oauth.access_token, oauth.refresh_token)
                # Update the Box client with the refreshed token
                client = Client(oauth)
            else:
                break  # Break the loop if the token is still valid
    else:
        print(f"Parent folder '{parent_folder_name}' not found.")
    # Wait for the web server thread to complete
    server_thread.join()

# %% SUSCEPTIBILITY.

import subprocess

# Generate path to dicom files.
target_folder_name = f'{p_id}'  # Set the target folder name
# Create the path to the target folder
target_folder_path = os.path.join(working_dir, target_folder_name, 'neurofeedback')
if not os.path.isdir(target_folder_path):  # Check if the target folder exists
    print(f"Target folder '{target_folder_path}' not found.")
    exit()
# Initialize a variable to store the name of the folder containing 'CISC'
cisc_directory_name = None
# Initialize a variable to store the path of the folder containing 'CISC'
cisc_directory_path = None
# Recursively search for the folder containing 'CISC' within the target folder
for root, directories, _ in os.walk(target_folder_path):
    for directory in directories:
        if 'CISC' in directory:
            cisc_directory_name = directory
            cisc_directory_path = os.path.join(root, directory)
            break
    if cisc_directory_name:
        break

# Create table of sequences from the scan.
file_list = os.listdir(cisc_directory_path)
seq_no_table = pd.DataFrame([[]])
for item in file_list:
    if item.endswith('.dcm'):
        seq_no = item[8:10]
        if seq_no not in seq_no_table.columns:
            seq_no_table[f'{seq_no}'] = np.nan
        seq_no_table[f'{seq_no}'] = f'{item}'

# Find the sequences which only have 210 Dicoms (Runs 1 and 4).
seq_no_table_210 = seq_no_table.loc[:, seq_no_table.applymap(
    lambda x: '210' in str(x)).any()]

# Remove Run 4 from the table, or ask for input to specify Run 1 and subsequently remove the other run columns.
if seq_no_table_210.shape[1] == 2:
    seq_no_table_run1 = seq_no_table_210.iloc[:, 0]
    # Copy Run 1 dicoms to separate folder 
    run1_dicom_folder_path = f'{p_id}/susceptibility/run01_dicoms'
    matching_files = [
        file for file in os.listdir(cisc_directory_path)
        if file.endswith('.dcm') and seq_no_table_run1.name in file
    ]
    for file in matching_files:
        source_path = os.path.join(cisc_directory_path, file)
        destination_path = os.path.join(run1_dicom_folder_path, file)
        subprocess.run(['cp', source_path, destination_path])
    # Convert Run 1 dicoms to Nifti.
    subprocess.run(['dcm2niix', '-o', f'{p_id}/susceptibility/run01', run1_dicom_folder_path])
else:
    run_1_number = input("Input required: more than two runs contain 210 dicoms. Please specify which sequence number is Run 1 (e.g. 08, 09, 11).\n")
    if run_1_number in seq_no_table_210.columns:
        seq_no_table_run1 = seq_no_table_210.filter(like=run_1_number)
        # Copy Run 1 dicoms to separate folder 
        run1_dicom_folder_path = f'{p_id}/susceptibility/run01_dicoms'
        matching_files = [
            file for file in os.listdir(cisc_directory_path)
            if file.endswith('.dcm') and seq_no_table_run1.name in file
        ]
        for file in matching_files:
            source_path = os.path.join(cisc_directory_path, file)
            destination_path = os.path.join(run1_dicom_folder_path, file)
            subprocess.run(['cp', source_path, destination_path])
        # Convert Run 1 dicoms to Nifti.
        subprocess.run(['dcm2niix', '-o', f'{p_id}/susceptibility/run01', run1_dicom_folder_path])


# Merge Run 1 Nifi volumes.
subprocess.run(['fslmaths', f'{p_id}/susceptibility/run01.nii',
               '-Tmean', f'{p_id}/susceptibility/run01_averaged'])
# Read the .roi file and extract the voxel coordinates.
def read_roi_file(roi_file):
    voxel_coordinates = []
    with open(roi_file, 'r') as file:
        lines = file.readlines()
        for line in lines:
            if line.strip().isdigit():
                coordinates = line.strip().split()
                voxel_coordinates.append(
                    (int(coordinates[0]), int(coordinates[1]), int(coordinates[2])))
    return voxel_coordinates
roi_file = f'{p_id}/neurofeedback/{cisc_directory_name}/depression_neurofeedback/target_folder_run-1/depnf_run-1.roi'
voxel_coordinates = read_roi_file(roi_file)
# Get the dimensions of the functional data.
functional_image = f'{p_id}/susceptibility/run01_averaged.nii.gz'
functional_image_info = nib.load(functional_image)
functional_dims = functional_image_info.shape
# Create an empty binary volume.
binary_volume = np.zeros(functional_dims)
# Assign a value of 1 to the voxel coordinates in the binary volume.
for voxel in voxel_coordinates:
    x, y, z = voxel
    binary_volume[x, y, z] = 1
# Save the binary volume as a NIfTI file.
# Assuming an identity affine (i.e. that there is no rotation, scaling, or translation applied to the image data. In other words, it assumes that the voxel coordinates directly correspond to the physical world coordinates without any additional transformation.)
binary_nifti = nib.Nifti1Image(binary_volume, affine=np.eye(4))
nib.save(binary_nifti, f'{p_id}/susceptibility/subject_space_ROI.nii.gz')
# Load the reference functional data.
functional_data = functional_image_info.get_fdata()
# Load the binary mask volume.
binary_mask_image = f'{p_id}/susceptibility/subject_space_ROI.nii.gz'
binary_mask_image_info = nib.load(binary_mask_image)
binary_mask_data = binary_mask_image_info.get_fdata()
# Overlay the binary mask onto the first volume of functional data.
first_volume = functional_data[..., 0]
overlay = np.ma.masked_where(binary_mask_data == 0, first_volume)
# Plot the overlay.
plt.figure()
plt.imshow(first_volume, cmap='gray')
plt.imshow(overlay, cmap='jet', alpha=0.5)
plt.colorbar()
plt.title('Overlay of Binary Mask on First Functional Volume')
plt.savefig(f'{p_id}/susceptibility/overlay_plot.png')
# Verify the orientation and alignment.
plt.figure()
plt.imshow(binary_mask_data[..., 0], cmap='gray')
plt.title('Binary Mask Volume')
plt.savefig(f'{p_id}/susceptibility/binary_mask_plot.png')
# Flip the y-axis if required
flipped_mask_data = np.flipud(binary_mask_data)
# Plot the flipped binary mask
plt.figure()
plt.imshow(flipped_mask_data[..., 0], cmap='gray')
plt.title('Flipped Binary Mask Volume')
plt.savefig(f'{p_id}/susceptibility/flipped_binary_mask_plot.png')
