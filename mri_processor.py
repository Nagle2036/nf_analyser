# -*- coding: utf-8 -*-

###TO DO###
# Create Python script to automatically generate PSC / thermometer level plots and blindedly show whether group allocation (a/b) matched training directions from scan.
# Organise files in BIDS format.
# Upload analysis outputs back to Box account.
# Add percentage completion metric.

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

#region INPUT INFORMATION.
p_id = input("Enter the participant's ID (e.g. P001).\n")
#endregion

#region CREATE FOLDERS.
working_dir = os.getcwd()
subprocess.run(['mkdir', f'{p_id}'])
subprocess.run(['mkdir', f'{p_id}/susceptibility'])
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

#region SUSCEPTIBILITY.

answer3 = input("Would you like to execute susceptibility artifact analysis? (y/n)\n")
if answer3 == 'y':

    # Step 1: Find the 'CISC' folder in the 'neurofeedback' directory
    path = os.path.join(os.getcwd(), p_id, "neurofeedback")
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
    destination_folder = os.path.join(os.getcwd(), p_id, "susceptibility", "run01_dicoms")
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
    output_folder = os.path.join(os.getcwd(), p_id, "susceptibility")
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
    functional_image = f'{p_id}/susceptibility/run01_averaged.nii.gz'
    functional_image_info = nib.load(functional_image)
    functional_dims = functional_image_info.shape
    binary_volume = np.zeros(functional_dims)
    for voxel in voxel_coordinates:
        x, y, z = voxel
        binary_volume[x, y, z] = 1
    binary_volume = np.flip(binary_volume, axis=1) #flipping mask across the y-axis
    functional_affine = functional_image_info.affine
    binary_nifti = nib.Nifti1Image(binary_volume, affine=functional_affine)
    nib.save(binary_nifti, f'{p_id}/susceptibility/subject_space_ROI.nii.gz')

    # Step 8: Save screenshot of the subject-space ROI on EPI image.
    binary_nifti_image = f'{p_id}/susceptibility/subject_space_ROI.nii.gz'
    screenshot_file = f'{p_id}/susceptibility/ROI_on_EPI.png'
    
    # Load the binary_nifti_image using nibabel
    binary_img = nib.load(binary_nifti_image)
    binary_data = binary_img.get_fdata()

    # Get the indices of the nonzero (signal) voxels
    indices = np.nonzero(binary_data)

    # Calculate the center coordinates based on the nonzero voxels
    center_x = int(np.mean(indices[0]))
    center_y = int(np.mean(indices[1]))
    center_z = int(np.mean(indices[2]))
    result4 = subprocess.run(['fsleyes', 'render', '--voxelLoc', f'{center_x}', f'{center_y}', f'{center_z}', '-dr', '50', '150', '-of', screenshot_file, functional_image, binary_nifti_image, '-ot', 'mask', '-mc', '1', '0', '0'], capture_output=True, text=True)
    if result4.returncode == 0:
        print("Screenshot saved as", screenshot_file)
    else:
        print("Error encountered:", result4.stderr)

"""
    # Specify the input image path
    input_image = f'{p_id}/susceptibility/run01_averaged.nii.gz'

    # Run the nipype Docker container with the external drive mounted
    subprocess.run(['docker', 'run', '-it', '--rm', '--name', 'nipype_container', '-v', '/its/home/bsms9pc4/Desktop/cisc2/projects/stone_depnf/neurofeedback/participant_data/P006/susceptibility:/output', 'nipype/nipype'])

    # Create a nipype workflow
    workflow = Workflow('brain_segmentation')

    # Create the SPM segment interface
    segment = Node(interface=spm.Segment(), name='segment')

    # Set the input image
    segment.inputs.data = input_image

    # Set the output directory within the container
    segment.inputs.output_dir = '/output/brain_segmentation'

    # Connect the nodes in the workflow
    workflow.connect(segment, 'native_class_images', 'outputnative')
    workflow.connect(segment, 'dartel_input_images', 'outputdartel')

    # Run the workflow
    workflow.run(plugin='MultiProc', plugin_args={'n_procs': 4})

    subprocess.run(['docker', 'stop', 'nipype_container'])
"""

#endregion