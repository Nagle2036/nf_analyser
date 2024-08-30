# -*- coding: utf-8 -*-

### TO DO ###
# Add percentage completion metric.
# Output mri_processor.py Bash terminal outputs / prints into .txt log file.

#region 1) IMPORT PACKAGES.

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
from pingouin import rm_anova
import json
import textwrap
# import rpy2.robjects as ro
# from rpy2.robjects import pandas2ri
# from rpy2.robjects.packages import importr
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

#endregion

#region 2) INSTRUCTIONS.
print("\nWelcome to the MRI analysis processor. Please complete the following before proceeding:\n")
print("1. Upload the participant's data to Box.\n")
print("2. In the Bash terminal, change the working directory to the participant_data folder within the cisc2 drive.\n")
answer = input("Have the above steps been completed? (y/n)\n")
if answer != 'y':
    print('Error: please complete prerequisite steps before proceeding.\n')
    sys.exit()
#endregion

#region 3) BOX FILES DOWNLOAD TO SERVER.

answer = input("Would you like to update your files from Box? (y/n)\n")
if answer == 'y':
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
            specific_files = ['eCRF.xlsx', 'heuristic.py']
            for file in specific_files:
                file_path = f'/its/home/bsms9pc4/Desktop/cisc2/projects/stone_depnf/Neurofeedback/participant_data/{file}'
                if file not in downloaded_files:
                    file_item = next((item for item in client.folder(parent_folder.parent.id).get_items() if item.name == file), None)
                    if file_item:
                        retry_attempts = 0
                        while retry_attempts < MAX_RETRY_ATTEMPTS:
                            try:
                                with open(file_path, 'wb') as writeable_stream:
                                    file_item.download_to(writeable_stream)
                                    downloaded_files.add(file)
                                    print(f"Downloaded: {file}.")
                                break
                            except Exception as e:
                                print(f"An error occurred while downloading {file}: {str(e)}")
                                print("Retrying...")
                                time.sleep(RETRY_DELAY_SECONDS)
                                retry_attempts += 1
                        if retry_attempts == MAX_RETRY_ATTEMPTS:
                            print(f"Failed to download {file} after {MAX_RETRY_ATTEMPTS} attempts.")
                    else:
                        print(f"{file} not found in parent folder.")
                else:
                    print(f"{file} already downloaded.")
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

#region 4) THERMOMETER ANALYSIS.

answer = input("Would you like to execute thermometer analysis? (y/n)\n")
if answer == 'y':



    
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
        group_folder = os.path.join(os.getcwd(), 'group')
        if not os.path.exists(group_folder):
            subprocess.run(['mkdir', 'group'])
        group_therm_folder = os.path.join(os.getcwd(), 'group', 'therm')
        if not os.path.exists(group_therm_folder):
            subprocess.run(['mkdir', 'group', 'therm'])
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
    output_excel_path = '/its/home/bsms9pc4/Desktop/cisc2/projects/stone_depnf/Neurofeedback/participant_data/group/therm/therm_data.xlsx'
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

#region 5) BEHAVIOURAL ANALYSIS.

answer = input("Would you like to execute behavioural analysis? (y/n)\n")
if answer == 'y':
    p_id = input("Enter the participant's ID (e.g. P001). If you want to analyse all participants simultaneously, enter 'ALL'.\n")
    participants = ['P004', 'P006', 'P020', 'P030', 'P059', 'P078', 'P093', 'P094', 'P100', 'P107', 'P122', 'P125', 'P127', 'P128', 'P136', 'P145', 'P155', 'P199', 'P215', 'P216']
    runs = ['run01', 'run02', 'run03', 'run04']
    if p_id == 'ALL':
        participants_to_iterate = participants
    else:
        participants_to_iterate = [p_id]
    restart = input("Would you like to start the behavioural analysis from scratch for the selected participant(s)? This will remove all files from the 'p_id/analysis/behavioural' and 'group' folders associated with them. (y/n)\n")
    if restart == 'y':
        double_check = input("Are you sure? (y/n)\n")
        if double_check == 'y':
            for p_id in participants_to_iterate:
                behavioural_folder = os.path.join(os.getcwd(), p_id, 'analysis', 'behavioural')
                if os.path.exists(behavioural_folder):
                    print(f"Deleting {p_id} behavioural folder...")
                    shutil.rmtree(behavioural_folder)
                    print(f"{p_id} behavioural folder successfully deleted.")
                else:
                    print(f"{p_id} behavioural folder does not exist.")
                group_behavioural_folder = os.path.join(os.getcwd(), 'group', 'behavioural')
            if os.path.exists(group_behavioural_folder):
                print(f"Deleting {p_id} group/behavioural folder...")
                shutil.rmtree(group_behavioural_folder)
                print(f"{p_id} group/behavioural folder successfully deleted.")
            else:
                print(f"{p_id} group/behavioural folder does not exist.")
        else:
            sys.exit()

    # Step 1: Create directories.
    print("\n###### STEP 1: CREATE DIRECTORIES ######")
    for p_id in participants_to_iterate:
        p_id_folder = os.path.join(os.getcwd(), p_id)
        os.makedirs(p_id_folder, exist_ok=True)
        analysis_folder = os.path.join(os.getcwd(), p_id, 'analysis')
        os.makedirs(analysis_folder, exist_ok=True)
        behavioural_folder = os.path.join(os.getcwd(), p_id, 'analysis', 'behavioural')
        os.makedirs(behavioural_folder, exist_ok=True)
        group_folder = os.path.join(os.getcwd(), "group")
        os.makedirs(group_folder, exist_ok=True)
        group_behavioural_folder = os.path.join(os.getcwd(), "group", "behavioural")
        os.makedirs(group_behavioural_folder, exist_ok=True)

    # Step 2: Access eCRF document and extract relevant data into dataframe.
    print("\n###### STEP 2: ACCESS eCRF FILE AND CONVERT TO DATAFRAME ######")
    warnings.simplefilter("ignore", UserWarning)
    df_row_headers = ['dob', 'gender', 'handedness', 'exercise', 'education', 'work_status', 'panic', 'agoraphobia', 'social_anx', 'ocd', 'ptsd', 'gad', 'comorbid_anx', 'msm', 'psi_sociotropy', 'psi_autonomy', 'raads', 'panas_pos_vis_1', 'panas_neg_vis_1', 'qids_vis_1', 'gad_vis_1', 'rosenberg_vis_1', 'madrs_vis_1', 'pre_memory_intensity_guilt_1', 'pre_memory_intensity_guilt_2', 'pre_memory_intensity_indignation_1', 'pre_memory_intensity_indignation_2', 'intervention', 'techniques_guilt', 'techniques_indignation', 'perceived_success_guilt', 'perceived_success_indignation', 'post_memory_intensity_guilt_1', 'post_memory_intensity_guilt_2', 'post_memory_intensity_indignation_1', 'post_memory_intensity_indignation_2', 'rosenberg_vis_2', 'panas_pos_vis_3', 'panas_neg_vis_3', 'qids_vis_3', 'gad_vis_3', 'rosenberg_vis_3', 'madrs_vis_3', 'qids_vis_4', 'rosenberg_vis_4', 'qids_vis_5', 'rosenberg_vis_5']
    ecrf_df = pd.DataFrame(index = df_row_headers)
    ecrf_file_path = '/its/home/bsms9pc4/Desktop/cisc2/projects/stone_depnf/Neurofeedback/participant_data/eCRF.xlsx'
    password = 'SussexDepNF22'
    df_values_dict = {}
    location_dict = {
        'P004_vis_1_locations': {'dob': (77, 3), 'gender': (81, 3),  'handedness': (82, 3), 'exercise': (83, 3), 'education': (84, 3), 'work_status': (85, 3), 'panic': (132, 3), 'agoraphobia': (134, 3), 'social_anx': (135, 3), 'ocd': (137, 3), 'ptsd': (140, 3), 'gad': (141, 3), 'comorbid_anx': (142, 3), 'msm': (120, 3), 'psi_sociotropy': (151, 3), 'psi_autonomy': (152, 3), 'raads': (155, 3), 'panas_pos_vis_1': (161, 3), 'panas_neg_vis_1': (162, 3), 'qids_vis_1': (172, 3), 'gad_vis_1': (173, 3), 'rosenberg_vis_1': (174, 3), 'madrs_vis_1': (185, 3)},
        'P004_vis_2_locations': {'pre_memory_intensity_guilt_1': (38, 3), 'pre_memory_intensity_guilt_2': (43, 3), 'pre_memory_intensity_indignation_1': (49, 3), 'pre_memory_intensity_indignation_2': (54, 3), 'intervention': (78, 3), 'techniques_guilt': (84, 3), 'techniques_indignation': (85, 3), 'perceived_success_guilt': (86, 3), 'perceived_success_indignation': (87, 3), 'post_memory_intensity_guilt_1': (88, 3), 'post_memory_intensity_guilt 2': (92, 3), 'post_memory_intensity_indignation_1': (97, 3), 'post_memory_indignation_2': (101, 3), 'rosenberg_vis_2': (104, 3)},
        'P004_vis_3_locations': {'panas_pos_vis_3': (36, 3), 'panas_neg_vis_3': (37, 3), 'qids_vis_3': (47, 3), 'gad_vis_3': (48, 3), 'rosenberg_vis_3': (49, 3), 'madrs_vis_3': (60, 3)},
        'P004_vis_4_locations': {'qids_vis_4': (26, 3), 'rosenberg_vis_4': (27, 3)},
        'P004_vis_5_locations': {'qids_vis_5': (28, 3), 'rosenberg_vis_5': (29, 3)},

        'P006_vis_1_locations': {'dob': (77, 4), 'gender': (81, 4),  'handedness': (82, 4), 'exercise': (83, 4), 'education': (84, 4), 'work_status': (85, 4), 'panic': (132, 4), 'agoraphobia': (134, 4), 'social_anx': (135, 4), 'ocd': (137, 4), 'ptsd': (140, 4), 'gad': (141, 4), 'comorbid_anx': (142, 4), 'msm': (120, 4), 'psi_sociotropy': (151, 4), 'psi_autonomy': (152, 4), 'raads': (155, 4), 'panas_pos_vis_1': (161, 4), 'panas_neg_vis_1': (162, 4), 'qids_vis_1': (172, 4), 'gad_vis_1': (173, 4), 'rosenberg_vis_1': (174, 4), 'madrs_vis_1': (185, 4)},
        'P006_vis_2_locations': {'pre_memory_intensity_guilt_1': (38, 4), 'pre_memory_intensity_guilt_2': (43, 4), 'pre_memory_intensity_indignation_1': (49, 4), 'pre_memory_intensity_indignation_2': (54, 4), 'intervention': (78, 4), 'techniques_guilt': (84, 4), 'techniques_indignation': (85, 4), 'perceived_success_guilt': (86, 4), 'perceived_success_indignation': (87, 4), 'post_memory_intensity_guilt_1': (88, 4), 'post_memory_intensity_guilt 2': (92, 4), 'post_memory_intensity_indignation_1': (97, 4), 'post_memory_indignation_2': (101, 4), 'rosenberg_vis_2': (104, 4)},
        'P006_vis_3_locations': {'panas_pos_vis_3': (36, 4), 'panas_neg_vis_3': (37, 4), 'qids_vis_3': (47, 4), 'gad_vis_3': (48, 4), 'rosenberg_vis_3': (49, 4), 'madrs_vis_3': (60, 4)},
        'P006_vis_4_locations': {'qids_vis_4': (26, 4), 'rosenberg_vis_4': (27, 4)},
        'P006_vis_5_locations': {'qids_vis_5': (28, 4), 'rosenberg_vis_5': (29, 4)},

        'P020_vis_1_locations': {'dob': (77, 7), 'gender': (81, 7),  'handedness': (82, 7), 'exercise': (83, 7), 'education': (84, 7), 'work_status': (85, 7), 'panic': (132, 7), 'agoraphobia': (134, 7), 'social_anx': (135, 7), 'ocd': (137, 7), 'ptsd': (140, 7), 'gad': (141, 7), 'comorbid_anx': (142, 7), 'msm': (120, 7), 'psi_sociotropy': (151, 7), 'psi_autonomy': (152, 7), 'raads': (155, 7), 'panas_pos_vis_1': (161, 7), 'panas_neg_vis_1': (162, 7), 'qids_vis_1': (172, 7), 'gad_vis_1': (173, 7), 'rosenberg_vis_1': (174, 7), 'madrs_vis_1': (185, 7)},
        'P020_vis_2_locations': {'pre_memory_intensity_guilt_1': (38, 6), 'pre_memory_intensity_guilt_2': (43, 6), 'pre_memory_intensity_indignation_1': (49, 6), 'pre_memory_intensity_indignation_2': (54, 6), 'intervention': (78, 6), 'techniques_guilt': (84, 6), 'techniques_indignation': (85, 6), 'perceived_success_guilt': (86, 6), 'perceived_success_indignation': (87, 6), 'post_memory_intensity_guilt_1': (88, 6), 'post_memory_intensity_guilt 2': (92, 6), 'post_memory_intensity_indignation_1': (97, 6), 'post_memory_indignation_2': (101, 6), 'rosenberg_vis_2': (104, 6)},
        'P020_vis_3_locations': {'panas_pos_vis_3': (36, 6), 'panas_neg_vis_3': (37, 6), 'qids_vis_3': (47, 6), 'gad_vis_3': (48, 6), 'rosenberg_vis_3': (49, 6), 'madrs_vis_3': (60, 6)},
        'P020_vis_4_locations': {'qids_vis_4': (26, 6), 'rosenberg_vis_4': (27, 6)},
        'P020_vis_5_locations': {'qids_vis_5': (28, 6), 'rosenberg_vis_5': (29, 6)},

        'P030_vis_1_locations': {'dob': (77, 6), 'gender': (81, 6),  'handedness': (82, 6), 'exercise': (83, 6), 'education': (84, 6), 'work_status': (85, 6), 'panic': (132, 6), 'agoraphobia': (134, 6), 'social_anx': (135, 6), 'ocd': (137, 6), 'ptsd': (140, 6), 'gad': (141, 6), 'comorbid_anx': (142, 6), 'msm': (120, 6), 'psi_sociotropy': (151, 6), 'psi_autonomy': (152, 6), 'raads': (155, 6), 'panas_pos_vis_1': (161, 6), 'panas_neg_vis_1': (162, 6), 'qids_vis_1': (172, 6), 'gad_vis_1': (173, 6), 'rosenberg_vis_1': (174, 6), 'madrs_vis_1': (185, 6)},
        'P030_vis_2_locations': {'pre_memory_intensity_guilt_1': (38, 5), 'pre_memory_intensity_guilt_2': (43, 5), 'pre_memory_intensity_indignation_1': (49, 5), 'pre_memory_intensity_indignation_2': (54, 5), 'intervention': (78, 5), 'techniques_guilt': (84, 5), 'techniques_indignation': (85, 5), 'perceived_success_guilt': (86, 5), 'perceived_success_indignation': (87, 5), 'post_memory_intensity_guilt_1': (88, 5), 'post_memory_intensity_guilt 2': (92, 5), 'post_memory_intensity_indignation_1': (97, 5), 'post_memory_indignation_2': (101, 5), 'rosenberg_vis_2': (104, 5)},
        'P030_vis_3_locations': {'panas_pos_vis_3': (36, 5), 'panas_neg_vis_3': (37, 5), 'qids_vis_3': (47, 5), 'gad_vis_3': (48, 5), 'rosenberg_vis_3': (49, 5), 'madrs_vis_3': (60, 5)},
        'P030_vis_4_locations': {'qids_vis_4': (26, 5), 'rosenberg_vis_4': (27, 5)},
        'P030_vis_5_locations': {'qids_vis_5': (28, 5), 'rosenberg_vis_5': (29, 5)},

        'P059_vis_1_locations': {'dob': (77, 23), 'gender': (81, 23),  'handedness': (82, 23), 'exercise': (83, 23), 'education': (84, 23), 'work_status': (85, 23), 'panic': (132, 23), 'agoraphobia': (134, 23), 'social_anx': (135, 23), 'ocd': (137, 23), 'ptsd': (140, 23), 'gad': (141, 23), 'comorbid_anx': (142, 23), 'msm': (120, 23), 'psi_sociotropy': (151, 23), 'psi_autonomy': (152, 23), 'raads': (155, 23), 'panas_pos_vis_1': (161, 23), 'panas_neg_vis_1': (162, 23), 'qids_vis_1': (172, 23), 'gad_vis_1': (173, 23), 'rosenberg_vis_1': (174, 23), 'madrs_vis_1': (185, 23)},
        'P059_vis_2_locations': {'pre_memory_intensity_guilt_1': (38, 20), 'pre_memory_intensity_guilt_2': (43, 20), 'pre_memory_intensity_indignation_1': (49, 20), 'pre_memory_intensity_indignation_2': (54, 20), 'intervention': (78, 20), 'techniques_guilt': (84, 20), 'techniques_indignation': (85, 20), 'perceived_success_guilt': (86, 20), 'perceived_success_indignation': (87, 20), 'post_memory_intensity_guilt_1': (88, 20), 'post_memory_intensity_guilt 2': (92, 20), 'post_memory_intensity_indignation_1': (97, 20), 'post_memory_indignation_2': (101, 20), 'rosenberg_vis_2': (104, 20)},
        'P059_vis_3_locations': {'panas_pos_vis_3': (36, 19), 'panas_neg_vis_3': (37, 19), 'qids_vis_3': (47, 19), 'gad_vis_3': (48, 19), 'rosenberg_vis_3': (49, 19), 'madrs_vis_3': (60, 19)},
        'P059_vis_4_locations': {'qids_vis_4': (26, 19), 'rosenberg_vis_4': (27, 19)},
        'P059_vis_5_locations': {'qids_vis_5': (28, 19), 'rosenberg_vis_5': (29, 19)},

        'P078_vis_1_locations': {'dob': (77, 9), 'gender': (81, 9),  'handedness': (82, 9), 'exercise': (83, 9), 'education': (84, 9), 'work_status': (85, 9), 'panic': (132, 9), 'agoraphobia': (134, 9), 'social_anx': (135, 9), 'ocd': (137, 9), 'ptsd': (140, 9), 'gad': (141, 9), 'comorbid_anx': (142, 9), 'msm': (120, 9), 'psi_sociotropy': (151, 9), 'psi_autonomy': (152, 9), 'raads': (155, 9), 'panas_pos_vis_1': (161, 9), 'panas_neg_vis_1': (162, 9), 'qids_vis_1': (172, 9), 'gad_vis_1': (173, 9), 'rosenberg_vis_1': (174, 9), 'madrs_vis_1': (185, 9)},
        'P078_vis_2_locations': {'pre_memory_intensity_guilt_1': (38, 7), 'pre_memory_intensity_guilt_2': (43, 7), 'pre_memory_intensity_indignation_1': (49, 7), 'pre_memory_intensity_indignation_2': (54, 7), 'intervention': (78, 7), 'techniques_guilt': (84, 7), 'techniques_indignation': (85, 7), 'perceived_success_guilt': (86, 7), 'perceived_success_indignation': (87, 7), 'post_memory_intensity_guilt_1': (88, 7), 'post_memory_intensity_guilt 2': (92, 7), 'post_memory_intensity_indignation_1': (97, 7), 'post_memory_indignation_2': (101, 7), 'rosenberg_vis_2': (104, 7)},
        'P078_vis_3_locations': {'panas_pos_vis_3': (36, 7), 'panas_neg_vis_3': (37, 7), 'qids_vis_3': (47, 7), 'gad_vis_3': (48, 7), 'rosenberg_vis_3': (49, 7), 'madrs_vis_3': (60, 7)},
        'P078_vis_4_locations': {'qids_vis_4': (26, 7), 'rosenberg_vis_4': (27, 7)},
        'P078_vis_5_locations': {'qids_vis_5': (28, 7), 'rosenberg_vis_5': (29, 7)},

        'P093_vis_1_locations': {'dob': (77, 11), 'gender': (81, 11),  'handedness': (82, 11), 'exercise': (83, 11), 'education': (84, 11), 'work_status': (85, 11), 'panic': (132, 11), 'agoraphobia': (134, 11), 'social_anx': (135, 11), 'ocd': (137, 11), 'ptsd': (140, 11), 'gad': (141, 11), 'comorbid_anx': (142, 11), 'msm': (120, 11), 'psi_sociotropy': (151, 11), 'psi_autonomy': (152, 11), 'raads': (155, 11), 'panas_pos_vis_1': (161, 11), 'panas_neg_vis_1': (162, 11), 'qids_vis_1': (172, 11), 'gad_vis_1': (173, 11), 'rosenberg_vis_1': (174, 11), 'madrs_vis_1': (185, 11)},
        'P093_vis_2_locations': {'pre_memory_intensity_guilt_1': (38, 8), 'pre_memory_intensity_guilt_2': (43, 8), 'pre_memory_intensity_indignation_1': (49, 8), 'pre_memory_intensity_indignation_2': (54, 8), 'intervention': (78, 8), 'techniques_guilt': (84, 8), 'techniques_indignation': (85, 8), 'perceived_success_guilt': (86, 8), 'perceived_success_indignation': (87, 8), 'post_memory_intensity_guilt_1': (88, 8), 'post_memory_intensity_guilt 2': (92, 8), 'post_memory_intensity_indignation_1': (97, 8), 'post_memory_indignation_2': (101, 8), 'rosenberg_vis_2': (104, 8)},
        'P093_vis_3_locations': {'panas_pos_vis_3': (36, 8), 'panas_neg_vis_3': (37, 8), 'qids_vis_3': (47, 8), 'gad_vis_3': (48, 8), 'rosenberg_vis_3': (49, 8), 'madrs_vis_3': (60, 8)},
        'P093_vis_4_locations': {'qids_vis_4': (26, 8), 'rosenberg_vis_4': (27, 8)},
        'P093_vis_5_locations': {'qids_vis_5': (28, 8), 'rosenberg_vis_5': (29, 8)},

        'P094_vis_1_locations': {'dob': (77, 12), 'gender': (81, 12),  'handedness': (82, 12), 'exercise': (83, 12), 'education': (84, 12), 'work_status': (85, 12), 'panic': (132, 12), 'agoraphobia': (134, 12), 'social_anx': (135, 12), 'ocd': (137, 12), 'ptsd': (140, 12), 'gad': (141, 12), 'comorbid_anx': (142, 12), 'msm': (120, 12), 'psi_sociotropy': (151, 12), 'psi_autonomy': (152, 12), 'raads': (155, 12), 'panas_pos_vis_1': (161, 12), 'panas_neg_vis_1': (162, 12), 'qids_vis_1': (172, 12), 'gad_vis_1': (173, 12), 'rosenberg_vis_1': (174, 12), 'madrs_vis_1': (185, 12)},
        'P094_vis_2_locations': {'pre_memory_intensity_guilt_1': (38, 9), 'pre_memory_intensity_guilt_2': (43, 9), 'pre_memory_intensity_indignation_1': (49, 9), 'pre_memory_intensity_indignation_2': (54, 9), 'intervention': (78, 9), 'techniques_guilt': (84, 9), 'techniques_indignation': (85, 9), 'perceived_success_guilt': (86, 9), 'perceived_success_indignation': (87, 9), 'post_memory_intensity_guilt_1': (88, 9), 'post_memory_intensity_guilt 2': (92, 9), 'post_memory_intensity_indignation_1': (97, 9), 'post_memory_indignation_2': (101, 9), 'rosenberg_vis_2': (104, 9)},
        'P094_vis_3_locations': {'panas_pos_vis_3': (36, 9), 'panas_neg_vis_3': (37, 9), 'qids_vis_3': (47, 9), 'gad_vis_3': (48, 9), 'rosenberg_vis_3': (49, 9), 'madrs_vis_3': (60, 9)},
        'P094_vis_4_locations': {'qids_vis_4': (26, 9), 'rosenberg_vis_4': (27, 9)},
        'P094_vis_5_locations': {'qids_vis_5': (28, 9), 'rosenberg_vis_5': (29, 9)},

        'P100_vis_1_locations': {'dob': (77, 13), 'gender': (81, 13),  'handedness': (82, 13), 'exercise': (83, 13), 'education': (84, 13), 'work_status': (85, 13), 'panic': (132, 13), 'agoraphobia': (134, 13), 'social_anx': (135, 13), 'ocd': (137, 13), 'ptsd': (140, 13), 'gad': (141, 13), 'comorbid_anx': (142, 13), 'msm': (120, 13), 'psi_sociotropy': (151, 13), 'psi_autonomy': (152, 13), 'raads': (155, 13), 'panas_pos_vis_1': (161, 13), 'panas_neg_vis_1': (162, 13), 'qids_vis_1': (172, 13), 'gad_vis_1': (173, 13), 'rosenberg_vis_1': (174, 13), 'madrs_vis_1': (185, 13)},
        'P100_vis_2_locations': {'pre_memory_intensity_guilt_1': (38, 10), 'pre_memory_intensity_guilt_2': (43, 10), 'pre_memory_intensity_indignation_1': (49, 10), 'pre_memory_intensity_indignation_2': (54, 10), 'intervention': (78, 10), 'techniques_guilt': (84, 10), 'techniques_indignation': (85, 10), 'perceived_success_guilt': (86, 10), 'perceived_success_indignation': (87, 10), 'post_memory_intensity_guilt_1': (88, 10), 'post_memory_intensity_guilt 2': (92, 10), 'post_memory_intensity_indignation_1': (97, 10), 'post_memory_indignation_2': (101, 10), 'rosenberg_vis_2': (104, 10)},
        'P100_vis_3_locations': {'panas_pos_vis_3': (36, 10), 'panas_neg_vis_3': (37, 10), 'qids_vis_3': (47, 10), 'gad_vis_3': (48, 10), 'rosenberg_vis_3': (49, 10), 'madrs_vis_3': (60, 10)},
        'P100_vis_4_locations': {'qids_vis_4': (26, 10), 'rosenberg_vis_4': (27, 10)},
        'P100_vis_5_locations': {'qids_vis_5': (28, 10), 'rosenberg_vis_5': (29, 10)},

        'P107_vis_1_locations': {'dob': (77, 14), 'gender': (81, 14),  'handedness': (82, 14), 'exercise': (83, 14), 'education': (84, 14), 'work_status': (85, 14), 'panic': (132, 14), 'agoraphobia': (134, 14), 'social_anx': (135, 14), 'ocd': (137, 14), 'ptsd': (140, 14), 'gad': (141, 14), 'comorbid_anx': (142, 14), 'msm': (120, 14), 'psi_sociotropy': (151, 14), 'psi_autonomy': (152, 14), 'raads': (155, 14), 'panas_pos_vis_1': (161, 14), 'panas_neg_vis_1': (162, 14), 'qids_vis_1': (172, 14), 'gad_vis_1': (173, 14), 'rosenberg_vis_1': (174, 14), 'madrs_vis_1': (185, 14)},
        'P107_vis_2_locations': {'pre_memory_intensity_guilt_1': (38, 11), 'pre_memory_intensity_guilt_2': (43, 11), 'pre_memory_intensity_indignation_1': (49, 11), 'pre_memory_intensity_indignation_2': (54, 11), 'intervention': (78, 11), 'techniques_guilt': (84, 11), 'techniques_indignation': (85, 11), 'perceived_success_guilt': (86, 11), 'perceived_success_indignation': (87, 11), 'post_memory_intensity_guilt_1': (88, 11), 'post_memory_intensity_guilt 2': (92, 11), 'post_memory_intensity_indignation_1': (97, 11), 'post_memory_indignation_2': (101, 11), 'rosenberg_vis_2': (104, 11)},
        'P107_vis_3_locations': {'panas_pos_vis_3': (36, 11), 'panas_neg_vis_3': (37, 11), 'qids_vis_3': (47, 11), 'gad_vis_3': (48, 11), 'rosenberg_vis_3': (49, 11), 'madrs_vis_3': (60, 11)},
        'P107_vis_4_locations': {'qids_vis_4': (26, 11), 'rosenberg_vis_4': (27, 11)},
        'P107_vis_5_locations': {'qids_vis_5': (28, 11), 'rosenberg_vis_5': (29, 11)},

        'P122_vis_1_locations': {'dob': (77, 17), 'gender': (81, 17),  'handedness': (82, 17), 'exercise': (83, 17), 'education': (84, 17), 'work_status': (85, 17), 'panic': (132, 17), 'agoraphobia': (134, 17), 'social_anx': (135, 17), 'ocd': (137, 17), 'ptsd': (140, 17), 'gad': (141, 17), 'comorbid_anx': (142, 17), 'msm': (120, 17), 'psi_sociotropy': (151, 17), 'psi_autonomy': (152, 17), 'raads': (155, 17), 'panas_pos_vis_1': (161, 17), 'panas_neg_vis_1': (162, 17), 'qids_vis_1': (172, 17), 'gad_vis_1': (173, 17), 'rosenberg_vis_1': (174, 17), 'madrs_vis_1': (185, 17)},
        'P122_vis_2_locations': {'pre_memory_intensity_guilt_1': (38, 14), 'pre_memory_intensity_guilt_2': (43, 14), 'pre_memory_intensity_indignation_1': (49, 14), 'pre_memory_intensity_indignation_2': (54, 14), 'intervention': (78, 14), 'techniques_guilt': (84, 14), 'techniques_indignation': (85, 14), 'perceived_success_guilt': (86, 14), 'perceived_success_indignation': (87, 14), 'post_memory_intensity_guilt_1': (88, 14), 'post_memory_intensity_guilt 2': (92, 14), 'post_memory_intensity_indignation_1': (97, 14), 'post_memory_indignation_2': (101, 14), 'rosenberg_vis_2': (104, 14)},
        'P122_vis_3_locations': {'panas_pos_vis_3': (36, 14), 'panas_neg_vis_3': (37, 14), 'qids_vis_3': (47, 14), 'gad_vis_3': (48, 14), 'rosenberg_vis_3': (49, 14), 'madrs_vis_3': (60, 14)},
        'P122_vis_4_locations': {'qids_vis_4': (26, 14), 'rosenberg_vis_4': (27, 14)},
        'P122_vis_5_locations': {'qids_vis_5': (28, 14), 'rosenberg_vis_5': (29, 14)},

        'P125_vis_1_locations': {'dob': (77, 18), 'gender': (81, 18),  'handedness': (82, 18), 'exercise': (83, 18), 'education': (84, 18), 'work_status': (85, 18), 'panic': (132, 18), 'agoraphobia': (134, 18), 'social_anx': (135, 18), 'ocd': (137, 18), 'ptsd': (140, 18), 'gad': (141, 18), 'comorbid_anx': (142, 18), 'msm': (120, 18), 'psi_sociotropy': (151, 18), 'psi_autonomy': (152, 18), 'raads': (155, 18), 'panas_pos_vis_1': (161, 18), 'panas_neg_vis_1': (162, 18), 'qids_vis_1': (172, 18), 'gad_vis_1': (173, 18), 'rosenberg_vis_1': (174, 18), 'madrs_vis_1': (185, 18)},
        'P125_vis_2_locations': {'pre_memory_intensity_guilt_1': (38, 15), 'pre_memory_intensity_guilt_2': (43, 15), 'pre_memory_intensity_indignation_1': (49, 15), 'pre_memory_intensity_indignation_2': (54, 15), 'intervention': (78, 15), 'techniques_guilt': (84, 15), 'techniques_indignation': (85, 15), 'perceived_success_guilt': (86, 15), 'perceived_success_indignation': (87, 15), 'post_memory_intensity_guilt_1': (88, 15), 'post_memory_intensity_guilt 2': (92, 15), 'post_memory_intensity_indignation_1': (97, 15), 'post_memory_indignation_2': (101, 15), 'rosenberg_vis_2': (104, 15)},
        'P125_vis_3_locations': {'panas_pos_vis_3': (36, 15), 'panas_neg_vis_3': (37, 15), 'qids_vis_3': (47, 15), 'gad_vis_3': (48, 15), 'rosenberg_vis_3': (49, 15), 'madrs_vis_3': (60, 15)},
        'P125_vis_4_locations': {'qids_vis_4': (26, 15), 'rosenberg_vis_4': (27, 15)},
        'P125_vis_5_locations': {'qids_vis_5': (28, 15), 'rosenberg_vis_5': (29, 15)},

        'P127_vis_1_locations': {'dob': (77, 16), 'gender': (81, 16),  'handedness': (82, 16), 'exercise': (83, 16), 'education': (84, 16), 'work_status': (85, 16), 'panic': (132, 16), 'agoraphobia': (134, 16), 'social_anx': (135, 16), 'ocd': (137, 16), 'ptsd': (140, 16), 'gad': (141, 16), 'comorbid_anx': (142, 16), 'msm': (120, 16), 'psi_sociotropy': (151, 16), 'psi_autonomy': (152, 16), 'raads': (155, 16), 'panas_pos_vis_1': (161, 16), 'panas_neg_vis_1': (162, 16), 'qids_vis_1': (172, 16), 'gad_vis_1': (173, 16), 'rosenberg_vis_1': (174, 16), 'madrs_vis_1': (185, 16)},
        'P127_vis_2_locations': {'pre_memory_intensity_guilt_1': (38, 13), 'pre_memory_intensity_guilt_2': (43, 13), 'pre_memory_intensity_indignation_1': (49, 13), 'pre_memory_intensity_indignation_2': (54, 13), 'intervention': (78, 13), 'techniques_guilt': (84, 13), 'techniques_indignation': (85, 13), 'perceived_success_guilt': (86, 13), 'perceived_success_indignation': (87, 13), 'post_memory_intensity_guilt_1': (88, 13), 'post_memory_intensity_guilt 2': (92, 13), 'post_memory_intensity_indignation_1': (97, 13), 'post_memory_indignation_2': (101, 13), 'rosenberg_vis_2': (104, 13)},
        'P127_vis_3_locations': {'panas_pos_vis_3': (36, 13), 'panas_neg_vis_3': (37, 13), 'qids_vis_3': (47, 13), 'gad_vis_3': (48, 13), 'rosenberg_vis_3': (49, 13), 'madrs_vis_3': (60, 13)},
        'P127_vis_4_locations': {'qids_vis_4': (26, 13), 'rosenberg_vis_4': (27, 13)},
        'P127_vis_5_locations': {'qids_vis_5': (28, 13), 'rosenberg_vis_5': (29, 13)},

        'P128_vis_1_locations': {'dob': (77, 15), 'gender': (81, 15),  'handedness': (82, 15), 'exercise': (83, 15), 'education': (84, 15), 'work_status': (85, 15), 'panic': (132, 15), 'agoraphobia': (134, 15), 'social_anx': (135, 15), 'ocd': (137, 15), 'ptsd': (140, 15), 'gad': (141, 15), 'comorbid_anx': (142, 15), 'msm': (120, 15), 'psi_sociotropy': (151, 15), 'psi_autonomy': (152, 15), 'raads': (155, 15), 'panas_pos_vis_1': (161, 15), 'panas_neg_vis_1': (162, 15), 'qids_vis_1': (172, 15), 'gad_vis_1': (173, 15), 'rosenberg_vis_1': (174, 15), 'madrs_vis_1': (185, 15)},
        'P128_vis_2_locations': {'pre_memory_intensity_guilt_1': (38, 12), 'pre_memory_intensity_guilt_2': (43, 12), 'pre_memory_intensity_indignation_1': (49, 12), 'pre_memory_intensity_indignation_2': (54, 12), 'intervention': (78, 12), 'techniques_guilt': (84, 12), 'techniques_indignation': (85, 12), 'perceived_success_guilt': (86, 12), 'perceived_success_indignation': (87, 12), 'post_memory_intensity_guilt_1': (88, 12), 'post_memory_intensity_guilt 2': (92, 12), 'post_memory_intensity_indignation_1': (97, 12), 'post_memory_indignation_2': (101, 12), 'rosenberg_vis_2': (104, 12)},
        'P128_vis_3_locations': {'panas_pos_vis_3': (36, 12), 'panas_neg_vis_3': (37, 12), 'qids_vis_3': (47, 12), 'gad_vis_3': (48, 12), 'rosenberg_vis_3': (49, 12), 'madrs_vis_3': (60, 12)},
        'P128_vis_4_locations': {'qids_vis_4': (26, 12), 'rosenberg_vis_4': (27, 12)},
        'P128_vis_5_locations': {'qids_vis_5': (28, 12), 'rosenberg_vis_5': (29, 12)},

        'P136_vis_1_locations': {'dob': (77, 19), 'gender': (81, 19),  'handedness': (82, 19), 'exercise': (83, 19), 'education': (84, 19), 'work_status': (85, 19), 'panic': (132, 19), 'agoraphobia': (134, 19), 'social_anx': (135, 19), 'ocd': (137, 19), 'ptsd': (140, 19), 'gad': (141, 19), 'comorbid_anx': (142, 19), 'msm': (120, 19), 'psi_sociotropy': (151, 19), 'psi_autonomy': (152, 19), 'raads': (155, 19), 'panas_pos_vis_1': (161, 19), 'panas_neg_vis_1': (162, 19), 'qids_vis_1': (172, 19), 'gad_vis_1': (173, 19), 'rosenberg_vis_1': (174, 19), 'madrs_vis_1': (185, 19)},
        'P136_vis_2_locations': {'pre_memory_intensity_guilt_1': (38, 16), 'pre_memory_intensity_guilt_2': (43, 16), 'pre_memory_intensity_indignation_1': (49, 16), 'pre_memory_intensity_indignation_2': (54, 16), 'intervention': (78, 16), 'techniques_guilt': (84, 16), 'techniques_indignation': (85, 16), 'perceived_success_guilt': (86, 16), 'perceived_success_indignation': (87, 16), 'post_memory_intensity_guilt_1': (88, 16), 'post_memory_intensity_guilt 2': (92, 16), 'post_memory_intensity_indignation_1': (97, 16), 'post_memory_indignation_2': (101, 16), 'rosenberg_vis_2': (104, 16)},
        'P136_vis_3_locations': {'panas_pos_vis_3': (36, 16), 'panas_neg_vis_3': (37, 16), 'qids_vis_3': (47, 16), 'gad_vis_3': (48, 16), 'rosenberg_vis_3': (49, 16), 'madrs_vis_3': (60, 16)},
        'P136_vis_4_locations': {'qids_vis_4': (26, 16), 'rosenberg_vis_4': (27, 16)},
        'P136_vis_5_locations': {'qids_vis_5': (28, 16), 'rosenberg_vis_5': (29, 16)},

        'P145_vis_1_locations': {'dob': (77, 21), 'gender': (81, 21),  'handedness': (82, 21), 'exercise': (83, 21), 'education': (84, 21), 'work_status': (85, 21), 'panic': (132, 21), 'agoraphobia': (134, 21), 'social_anx': (135, 21), 'ocd': (137, 21), 'ptsd': (140, 21), 'gad': (141, 21), 'comorbid_anx': (142, 21), 'msm': (120, 21), 'psi_sociotropy': (151, 21), 'psi_autonomy': (152, 21), 'raads': (155, 21), 'panas_pos_vis_1': (161, 21), 'panas_neg_vis_1': (162, 21), 'qids_vis_1': (172, 21), 'gad_vis_1': (173, 21), 'rosenberg_vis_1': (174, 21), 'madrs_vis_1': (185, 21)},
        'P145_vis_2_locations': {'pre_memory_intensity_guilt_1': (38, 18), 'pre_memory_intensity_guilt_2': (43, 18), 'pre_memory_intensity_indignation_1': (49, 18), 'pre_memory_intensity_indignation_2': (54, 18), 'intervention': (78, 18), 'techniques_guilt': (84, 18), 'techniques_indignation': (85, 18), 'perceived_success_guilt': (86, 18), 'perceived_success_indignation': (87, 18), 'post_memory_intensity_guilt_1': (88, 18), 'post_memory_intensity_guilt 2': (92, 18), 'post_memory_intensity_indignation_1': (97, 18), 'post_memory_indignation_2': (101, 18), 'rosenberg_vis_2': (104, 18)},
        'P145_vis_3_locations': {'panas_pos_vis_3': (36, 17), 'panas_neg_vis_3': (37, 17), 'qids_vis_3': (47, 17), 'gad_vis_3': (48, 17), 'rosenberg_vis_3': (49, 17), 'madrs_vis_3': (60, 17)},
        'P145_vis_4_locations': {'qids_vis_4': (26, 17), 'rosenberg_vis_4': (27, 17)},
        'P145_vis_5_locations': {'qids_vis_5': (28, 17), 'rosenberg_vis_5': (29, 17)},

        'P155_vis_1_locations': {'dob': (77, 22), 'gender': (81, 22),  'handedness': (82, 22), 'exercise': (83, 22), 'education': (84, 22), 'work_status': (85, 22), 'panic': (132, 22), 'agoraphobia': (134, 22), 'social_anx': (135, 22), 'ocd': (137, 22), 'ptsd': (140, 22), 'gad': (141, 22), 'comorbid_anx': (142, 22), 'msm': (120, 22), 'psi_sociotropy': (151, 22), 'psi_autonomy': (152, 22), 'raads': (155, 22), 'panas_pos_vis_1': (161, 22), 'panas_neg_vis_1': (162, 22), 'qids_vis_1': (172, 22), 'gad_vis_1': (173, 22), 'rosenberg_vis_1': (174, 22), 'madrs_vis_1': (185, 22)},
        'P155_vis_2_locations': {'pre_memory_intensity_guilt_1': (38, 19), 'pre_memory_intensity_guilt_2': (43, 19), 'pre_memory_intensity_indignation_1': (49, 19), 'pre_memory_intensity_indignation_2': (54, 19), 'intervention': (78, 19), 'techniques_guilt': (84, 19), 'techniques_indignation': (85, 19), 'perceived_success_guilt': (86, 19), 'perceived_success_indignation': (87, 19), 'post_memory_intensity_guilt_1': (88, 19), 'post_memory_intensity_guilt 2': (92, 19), 'post_memory_intensity_indignation_1': (97, 19), 'post_memory_indignation_2': (101, 19), 'rosenberg_vis_2': (104, 19)},
        'P155_vis_3_locations': {'panas_pos_vis_3': (36, 18), 'panas_neg_vis_3': (37, 18), 'qids_vis_3': (47, 18), 'gad_vis_3': (48, 18), 'rosenberg_vis_3': (49, 18), 'madrs_vis_3': (60, 18)},
        'P155_vis_4_locations': {'qids_vis_4': (26, 18), 'rosenberg_vis_4': (27, 18)},
        'P155_vis_5_locations': {'qids_vis_5': (28, 18), 'rosenberg_vis_5': (29, 18)},

        'P199_vis_1_locations': {'dob': (77, 27), 'gender': (81, 27),  'handedness': (82, 27), 'exercise': (83, 27), 'education': (84, 27), 'work_status': (85, 27), 'panic': (132, 27), 'agoraphobia': (134, 27), 'social_anx': (135, 27), 'ocd': (137, 27), 'ptsd': (140, 27), 'gad': (141, 27), 'comorbid_anx': (142, 27), 'msm': (120, 27), 'psi_sociotropy': (151, 27), 'psi_autonomy': (152, 27), 'raads': (155, 27), 'panas_pos_vis_1': (161, 27), 'panas_neg_vis_1': (162, 27), 'qids_vis_1': (172, 27), 'gad_vis_1': (173, 27), 'rosenberg_vis_1': (174, 27), 'madrs_vis_1': (185, 27)},
        'P199_vis_2_locations': {'pre_memory_intensity_guilt_1': (38, 22), 'pre_memory_intensity_guilt_2': (43, 22), 'pre_memory_intensity_indignation_1': (49, 22), 'pre_memory_intensity_indignation_2': (54, 22), 'intervention': (78, 22), 'techniques_guilt': (84, 22), 'techniques_indignation': (85, 22), 'perceived_success_guilt': (86, 22), 'perceived_success_indignation': (87, 22), 'post_memory_intensity_guilt_1': (88, 22), 'post_memory_intensity_guilt 2': (92, 22), 'post_memory_intensity_indignation_1': (97, 22), 'post_memory_indignation_2': (101, 22), 'rosenberg_vis_2': (104, 22)},
        'P199_vis_3_locations': {'panas_pos_vis_3': (36, 21), 'panas_neg_vis_3': (37, 21), 'qids_vis_3': (47, 21), 'gad_vis_3': (48, 21), 'rosenberg_vis_3': (49, 21), 'madrs_vis_3': (60, 21)},
        'P199_vis_4_locations': {'qids_vis_4': (26, 21), 'rosenberg_vis_4': (27, 21)},
        'P199_vis_5_locations': {'qids_vis_5': (28, 21), 'rosenberg_vis_5': (29, 21)},

        'P215_vis_1_locations': {'dob': (77, 26), 'gender': (81, 26),  'handedness': (82, 26), 'exercise': (83, 26), 'education': (84, 26), 'work_status': (85, 26), 'panic': (132, 26), 'agoraphobia': (134, 26), 'social_anx': (135, 26), 'ocd': (137, 26), 'ptsd': (140, 26), 'gad': (141, 26), 'comorbid_anx': (142, 26), 'msm': (120, 26), 'psi_sociotropy': (151, 26), 'psi_autonomy': (152, 26), 'raads': (155, 26), 'panas_pos_vis_1': (161, 26), 'panas_neg_vis_1': (162, 26), 'qids_vis_1': (172, 26), 'gad_vis_1': (173, 26), 'rosenberg_vis_1': (174, 26), 'madrs_vis_1': (185, 26)},
        'P215_vis_2_locations': {'pre_memory_intensity_guilt_1': (38, 21), 'pre_memory_intensity_guilt_2': (43, 21), 'pre_memory_intensity_indignation_1': (49, 21), 'pre_memory_intensity_indignation_2': (54, 21), 'intervention': (78, 21), 'techniques_guilt': (84, 21), 'techniques_indignation': (85, 21), 'perceived_success_guilt': (86, 21), 'perceived_success_indignation': (87, 21), 'post_memory_intensity_guilt_1': (88, 21), 'post_memory_intensity_guilt 2': (92, 21), 'post_memory_intensity_indignation_1': (97, 21), 'post_memory_indignation_2': (101, 21), 'rosenberg_vis_2': (104, 21)},
        'P215_vis_3_locations': {'panas_pos_vis_3': (36, 20), 'panas_neg_vis_3': (37, 20), 'qids_vis_3': (47, 20), 'gad_vis_3': (48, 20), 'rosenberg_vis_3': (49, 20), 'madrs_vis_3': (60, 20)},
        'P215_vis_4_locations': {'qids_vis_4': (26, 20), 'rosenberg_vis_4': (27, 20)},
        'P215_vis_5_locations': {'qids_vis_5': (28, 20), 'rosenberg_vis_5': (29, 20)},

        'P216_vis_1_locations': {'dob': (77, 28), 'gender': (81, 28),  'handedness': (82, 28), 'exercise': (83, 28), 'education': (84, 28), 'work_status': (85, 28), 'panic': (132, 28), 'agoraphobia': (134, 28), 'social_anx': (135, 28), 'ocd': (137, 28), 'ptsd': (140, 28), 'gad': (141, 28), 'comorbid_anx': (142, 28), 'msm': (120, 28), 'psi_sociotropy': (151, 28), 'psi_autonomy': (152, 28), 'raads': (155, 28), 'panas_pos_vis_1': (161, 28), 'panas_neg_vis_1': (162, 28), 'qids_vis_1': (172, 28), 'gad_vis_1': (173, 28), 'rosenberg_vis_1': (174, 28), 'madrs_vis_1': (185, 28)},
        'P216_vis_2_locations': {'pre_memory_intensity_guilt_1': (38, 23), 'pre_memory_intensity_guilt_2': (43, 23), 'pre_memory_intensity_indignation_1': (49, 23), 'pre_memory_intensity_indignation_2': (54, 23), 'intervention': (78, 23), 'techniques_guilt': (84, 23), 'techniques_indignation': (85, 23), 'perceived_success_guilt': (86, 23), 'perceived_success_indignation': (87, 23), 'post_memory_intensity_guilt_1': (88, 23), 'post_memory_intensity_guilt 2': (92, 23), 'post_memory_intensity_indignation_1': (97, 23), 'post_memory_indignation_2': (101, 23), 'rosenberg_vis_2': (104, 23)},
        'P216_vis_3_locations': {'panas_pos_vis_3': (36, 22), 'panas_neg_vis_3': (37, 22), 'qids_vis_3': (47, 22), 'gad_vis_3': (48, 22), 'rosenberg_vis_3': (49, 22), 'madrs_vis_3': (60, 22)},
        'P216_vis_4_locations': {'qids_vis_4': (26, 22), 'rosenberg_vis_4': (27, 22)},
        'P216_vis_5_locations': {'qids_vis_5': (28, 22), 'rosenberg_vis_5': (29, 22)}
    }
    for x in participants_to_iterate:
        print(f'Extracting {x} data from eCRF.xlsx...')
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
        ecrf_sheet = workbook['Online 1']
        vis_4_values = [ecrf_sheet.cell(row=row, column=column).value for (row, column) in location_dict[f'{x}_vis_4_locations'].values()]
        ecrf_sheet = workbook['Online 2']
        vis_5_values = [ecrf_sheet.cell(row=row, column=column).value for (row, column) in location_dict[f'{x}_vis_5_locations'].values()]
        df_values_dict[f'{x}'] = vis_1_values + vis_2_values + vis_3_values + vis_4_values + vis_5_values
        for key, values in df_values_dict.items():
            ecrf_df[key] = values
        output_excel_path = '/its/home/bsms9pc4/Desktop/cisc2/projects/stone_depnf/Neurofeedback/participant_data/group/ecrf_data.xlsx'
        ecrf_df.to_excel(output_excel_path, index=True)
        workbook.close()
    warnings.resetwarnings()

    # Step 3: Run LMMs of Clinical Assessment Scores.
    print("\n###### STEP 3: RUN LMMs OF CLINICAL ASSESSMENT SCORES ######")
    columns = ['p_id', 'visit', 'intervention', 'rosenberg', 'qids', 'madrs', 'gad', 'panas_pos', 'panas_neg']
    rqmgp_df = pd.DataFrame(columns=columns)
    p_id_column = participants * 5
    visit_column = ['1'] * 20 + ['2'] * 20 + ['3'] * 20 + ['4'] * 20 + ['5'] * 20
    intervention_values = ecrf_df.loc['intervention'].tolist()
    intervention_column = list(intervention_values) * 5
    rosenberg_vis_1 = ecrf_df.loc['rosenberg_vis_1'].tolist()
    rosenberg_vis_2 = ecrf_df.loc['rosenberg_vis_2'].tolist()
    rosenberg_vis_3 = ecrf_df.loc['rosenberg_vis_3'].tolist()
    rosenberg_vis_4 = ecrf_df.loc['rosenberg_vis_4'].tolist()
    rosenberg_vis_5 = ecrf_df.loc['rosenberg_vis_5'].tolist()
    rosenberg_column = rosenberg_vis_1 + rosenberg_vis_2 + rosenberg_vis_3 + rosenberg_vis_4 + rosenberg_vis_5
    qids_vis_1 = ecrf_df.loc['qids_vis_1'].tolist()
    qids_vis_2 = [np.nan] * 20
    qids_vis_3 = ecrf_df.loc['qids_vis_3'].tolist()
    qids_vis_4 = ecrf_df.loc['qids_vis_4'].tolist()
    qids_vis_5 = ecrf_df.loc['qids_vis_5'].tolist()
    qids_column = qids_vis_1 + qids_vis_2 + qids_vis_3 + qids_vis_4 + qids_vis_5
    madrs_vis_1 = ecrf_df.loc['madrs_vis_1'].tolist()
    madrs_vis_2 = [np.nan] * 20
    madrs_vis_3 = ecrf_df.loc['madrs_vis_3'].tolist()
    madrs_vis_4 = [np.nan] * 20
    madrs_vis_5 = [np.nan] * 20
    madrs_column = madrs_vis_1 + madrs_vis_2 + madrs_vis_3 + madrs_vis_4 + madrs_vis_5
    gad_vis_1 = ecrf_df.loc['gad_vis_1'].tolist()
    gad_vis_2 = [np.nan] * 20
    gad_vis_3 = ecrf_df.loc['gad_vis_3'].tolist()
    gad_vis_4 = [np.nan] * 20
    gad_vis_5 = [np.nan] * 20
    gad_column = gad_vis_1 + gad_vis_2 + gad_vis_3 + gad_vis_4 + gad_vis_5
    panas_pos_vis_1 = ecrf_df.loc['panas_pos_vis_1'].tolist()
    panas_pos_vis_2 = [np.nan] * 20
    panas_pos_vis_3 = ecrf_df.loc['panas_pos_vis_3'].tolist()
    panas_pos_vis_4 = [np.nan] * 20
    panas_pos_vis_5 = [np.nan] * 20
    panas_pos_column = panas_pos_vis_1 + panas_pos_vis_2 + panas_pos_vis_3 + panas_pos_vis_4 + panas_pos_vis_5
    panas_neg_vis_1 = ecrf_df.loc['panas_neg_vis_1'].tolist()
    panas_neg_vis_2 = [np.nan] * 20
    panas_neg_vis_3 = ecrf_df.loc['panas_neg_vis_3'].tolist()
    panas_neg_vis_4 = [np.nan] * 20
    panas_neg_vis_5 = [np.nan] * 20
    panas_neg_column = panas_neg_vis_1 + panas_neg_vis_2 + panas_neg_vis_3 + panas_neg_vis_4 + panas_neg_vis_5
    rqmgp_df['p_id'] = p_id_column
    rqmgp_df['visit'] = visit_column
    rqmgp_df['intervention'] = intervention_column
    rqmgp_df['rosenberg'] = rosenberg_column
    rqmgp_df['qids'] = qids_column
    rqmgp_df['madrs'] = madrs_column
    rqmgp_df['gad'] = gad_column
    rqmgp_df['panas_pos'] = panas_pos_column
    rqmgp_df['panas_neg'] = panas_neg_column

    rosenberg_df = rqmgp_df.dropna(subset=['rosenberg'])
    visits = ['1', '2', '3', '4', '5']
    interventions = ['a', 'b']
    columns = ['vals', 'mean', 'std_error', 'shap_p']
    index = ['vis1_inta', 'vis2_inta', 'vis3_inta', 'vis4_inta', 'vis5_inta', 'vis1_intb', 'vis2_intb', 'vis3_intb', 'vis4_intb', 'vis5_intb']
    rosenberg_stats_df = pd.DataFrame(columns=columns, index=index)
    for visit in visits:
        for intervention in interventions:
            vals = rosenberg_df[(rosenberg_df['visit'] == visit) & (rosenberg_df['intervention'] == intervention)]['rosenberg'].tolist()
            mean = np.mean(vals)
            std_error = np.std(vals) / np.sqrt(len(vals))
            _, shap_p = stats.shapiro(vals)
            rosenberg_stats_df.loc[f'vis{visit}_int{intervention}', 'vals'] = vals
            rosenberg_stats_df.loc[f'vis{visit}_int{intervention}', 'mean'] = mean
            rosenberg_stats_df.loc[f'vis{visit}_int{intervention}', 'std_error'] = std_error
            rosenberg_stats_df.loc[f'vis{visit}_int{intervention}', 'shap_p'] = shap_p

    # os.environ['R_HOME'] = 'C:/Program Files/R/R-4.4.1'
    # pandas2ri.activate()
    # r = ro.r
    # utils = importr('utils')
    # utils.chooseCRANmirror(ind=1)
    # r_script = """
    # library(lme4)
    # library(lmerTest)
    # library(emmeans)
    # rosenberg_df <- as.data.frame(rosenberg_df)
    # model <- lmer(rosenberg~visit*intervention + (1|p_id), data = rosenberg_df)
    # residuals_model <- residuals(model)
    # shapiro_test_result <- shapiro.test(residuals_model)
    # print(shapiro_test_result)
    # if (shapiro_test_result$p.value > 0.05) {
    # print("Rosenberg LMM residuals meet normality assumptions.")
    # anova_result <- anova(model)
    # print(anova_result)
    # emmeans_results <- emmeans(model, pairwise ~ visit)
    # print(summary(emmeans_results))
    # } else {
    # print("Rosenberg LMM residuals do not meet normality assumptions.")
    # }
    # """
    # ro.globalenv['rosenberg_df'] = pandas2ri.py2rpy(rosenberg_df)
    # result = r(r_script)
    # print(result)

    data = {
        'visit': [1, 2, 3, 4, 5] * 2,
        'intervention': ['A'] * 5 + ['B'] * 5,
        'mean': [
            rosenberg_stats_df.loc['vis1_inta', 'mean'], rosenberg_stats_df.loc['vis2_inta', 'mean'], rosenberg_stats_df.loc['vis3_inta', 'mean'],
            rosenberg_stats_df.loc['vis4_inta', 'mean'], rosenberg_stats_df.loc['vis5_inta', 'mean'], 
            rosenberg_stats_df.loc['vis1_intb', 'mean'], rosenberg_stats_df.loc['vis2_intb', 'mean'], rosenberg_stats_df.loc['vis3_intb', 'mean'], 
            rosenberg_stats_df.loc['vis4_intb', 'mean'], rosenberg_stats_df.loc['vis5_intb', 'mean'], 
        ],
        'std_error': [
            rosenberg_stats_df.loc['vis1_inta', 'std_error'], rosenberg_stats_df.loc['vis2_inta', 'std_error'], rosenberg_stats_df.loc['vis3_inta', 'std_error'], 
            rosenberg_stats_df.loc['vis4_inta', 'std_error'], rosenberg_stats_df.loc['vis5_inta', 'std_error'], 
            rosenberg_stats_df.loc['vis1_intb', 'std_error'], rosenberg_stats_df.loc['vis2_intb', 'std_error'], rosenberg_stats_df.loc['vis3_intb', 'std_error'], 
            rosenberg_stats_df.loc['vis4_intb', 'std_error'], rosenberg_stats_df.loc['vis5_intb', 'std_error'], 
        ]
    }
    plot_data = pd.DataFrame(data)
    rosenberg_plot = (ggplot(plot_data, aes(x='visit', y='mean', color='intervention'))
            + geom_line(size=2)
            + geom_point(size=4)
            + geom_errorbar(aes(ymin='mean - std_error',
                            ymax='mean + std_error'), width=0.2)
            + labs(title='Rosenberg Scores Across Study Visits',
                x='Visit',
                y='Rosenberg Score',
                color='Intervention')
            + theme_classic()
            + scale_y_continuous(expand=(0, 0), limits=[18,28])
            )
    rosenberg_plot = rosenberg_plot + annotate("text", x=2, y=max(plot_data['mean']) + 2.5, label="*", size=16, color="black") + \
        annotate("segment", x=1, xend=3, y=max(plot_data['mean']) +2.25, yend=max(plot_data['mean']) + 2.25, color="black") + \
            annotate("text", x=2.5, y=max(plot_data['mean']) + 3.5, label="*", size=16, color="black") + \
                annotate("segment", x=2, xend=3, y=max(plot_data['mean']) +3.25, yend=max(plot_data['mean']) + 3.25, color="black")
    rosenberg_plot.save('group/behavioural/rosenberg_plot.png')

    qids_df = rqmgp_df.dropna(subset=['qids'])
    visits = ['1', '3', '4', '5']
    interventions = ['a', 'b']
    columns = ['vals', 'mean', 'std_error', 'shap_p']
    index = ['vis1_inta', 'vis3_inta', 'vis4_inta', 'vis5_inta', 'vis1_intb', 'vis3_intb', 'vis4_intb', 'vis5_intb']
    qids_stats_df = pd.DataFrame(columns=columns, index=index)
    for visit in visits:
        for intervention in interventions:
            vals = qids_df[(qids_df['visit'] == visit) & (qids_df['intervention'] == intervention)]['qids'].tolist()
            mean = np.mean(vals)
            std_error = np.std(vals) / np.sqrt(len(vals))
            _, shap_p = stats.shapiro(vals)
            qids_stats_df.loc[f'vis{visit}_int{intervention}', 'vals'] = vals
            qids_stats_df.loc[f'vis{visit}_int{intervention}', 'mean'] = mean
            qids_stats_df.loc[f'vis{visit}_int{intervention}', 'std_error'] = std_error
            qids_stats_df.loc[f'vis{visit}_int{intervention}', 'shap_p'] = shap_p
    
    # os.environ['R_HOME'] = 'C:/Program Files/R/R-4.4.1'
    # pandas2ri.activate()
    # r = ro.r
    # utils = importr('utils')
    # utils.chooseCRANmirror(ind=1)
    # r_script = """
    # library(lme4)
    # library(lmerTest)
    # library(emmeans)
    # qids_df <- as.data.frame(qids_df)
    # model <- lmer(qids~visit*intervention + (1|p_id), data = qids_df)
    # residuals_model <- residuals(model)
    # shapiro_test_result <- shapiro.test(residuals_model)
    # print(shapiro_test_result)
    # if (shapiro_test_result$p.value > 0.05) {
    # print("QIDS LMM residuals meet normality assumptions.")
    # anova_result <- anova(model)
    # print(anova_result)
    # emmeans_results <- emmeans(model, pairwise ~ visit)
    # print(summary(emmeans_results))
    # } else {
    # print("QIDS LMM residuals do not meet normality assumptions.")
    # }
    # """
    # ro.globalenv['qids_df'] = pandas2ri.py2rpy(qids_df)
    # result = r(r_script)
    # print(result)

    data = {
        'visit': [1, 2, 3, 4, 5] * 2,
        'intervention': ['A'] * 5 + ['B'] * 5,
        'mean': [
            qids_stats_df.loc['vis1_inta', 'mean'], np.nan, qids_stats_df.loc['vis3_inta', 'mean'], 
            qids_stats_df.loc['vis4_inta', 'mean'], qids_stats_df.loc['vis5_inta', 'mean'], 
            qids_stats_df.loc['vis1_intb', 'mean'], np.nan, qids_stats_df.loc['vis3_intb', 'mean'], 
            qids_stats_df.loc['vis4_intb', 'mean'], qids_stats_df.loc['vis5_intb', 'mean'], 
        ],
        'std_error': [
            qids_stats_df.loc['vis1_inta', 'std_error'], np.nan, qids_stats_df.loc['vis3_inta', 'std_error'], 
            qids_stats_df.loc['vis4_inta', 'std_error'], qids_stats_df.loc['vis5_inta', 'std_error'], 
            qids_stats_df.loc['vis1_intb', 'std_error'], np.nan, qids_stats_df.loc['vis3_intb', 'std_error'], 
            qids_stats_df.loc['vis4_intb', 'std_error'], qids_stats_df.loc['vis5_intb', 'std_error'], 
        ]
    }
    plot_data = pd.DataFrame(data)
    plot_data_line = plot_data[plot_data['visit'] != 2]
    qids_plot = (ggplot(plot_data, aes(x='visit', y='mean', color='intervention'))
            + geom_line(data=plot_data_line, size=2)
            + geom_point(size=4)
            + geom_errorbar(aes(ymin='mean - std_error',
                            ymax='mean + std_error'), width=0.2)
            + labs(title='QIDS Scores Across Study Visits',
                x='Visit',
                y='QIDS Score',
                color='Intervention')
            + theme_classic()
            + scale_y_continuous(expand=(0, 0), limits=[8,20], breaks=[8,10,12,14,16,18,20])
            )
    qids_plot = qids_plot + annotate("text", x=2, y=max(plot_data['mean']) + 2.5, label="**", size=16, color="black") + \
        annotate("segment", x=1, xend=3, y=max(plot_data['mean']) +2.25, yend=max(plot_data['mean']) + 2.25, color="black") + \
            annotate("text", x=2.5, y=max(plot_data['mean']) + 3.5, label="***", size=16, color="black") + \
                annotate("segment", x=1, xend=4, y=max(plot_data['mean']) +3.25, yend=max(plot_data['mean']) + 3.25, color="black") + \
                    annotate("text", x=3, y=max(plot_data['mean']) + 4.5, label="***", size=16, color="black") + \
                        annotate("segment", x=1, xend=5, y=max(plot_data['mean']) +4.25, yend=max(plot_data['mean']) + 4.25, color="black")
    qids_plot.save('group/behavioural/qids_plot.png')

    madrs_df = rqmgp_df.dropna(subset=['madrs'])
    visits = ['1', '3']
    interventions = ['a', 'b']
    columns = ['vals', 'mean', 'std_error', 'shap_p']
    index = ['vis1_inta', 'vis3_inta', 'vis1_intb', 'vis3_intb']
    madrs_stats_df = pd.DataFrame(columns=columns, index=index)
    for visit in visits:
        for intervention in interventions:
            vals = madrs_df[(madrs_df['visit'] == visit) & (madrs_df['intervention'] == intervention)]['madrs'].tolist()
            mean = np.mean(vals)
            std_error = np.std(vals) / np.sqrt(len(vals))
            _, shap_p = stats.shapiro(vals)
            madrs_stats_df.loc[f'vis{visit}_int{intervention}', 'vals'] = vals
            madrs_stats_df.loc[f'vis{visit}_int{intervention}', 'mean'] = mean
            madrs_stats_df.loc[f'vis{visit}_int{intervention}', 'std_error'] = std_error
            madrs_stats_df.loc[f'vis{visit}_int{intervention}', 'shap_p'] = shap_p

    # os.environ['R_HOME'] = 'C:/Program Files/R/R-4.4.1'
    # pandas2ri.activate()
    # r = ro.r
    # utils = importr('utils')
    # utils.chooseCRANmirror(ind=1)
    # r_script = """
    # library(lme4)
    # library(lmerTest)
    # library(emmeans)
    # madrs_df <- as.data.frame(madrs_df)
    # model <- lmer(madrs~visit*intervention + (1|p_id), data = madrs_df)
    # residuals_model <- residuals(model)
    # shapiro_test_result <- shapiro.test(residuals_model)
    # print(shapiro_test_result)
    # if (shapiro_test_result$p.value > 0.05) {
    # print("MADRS LMM residuals meet normality assumptions.")
    # anova_result <- anova(model)
    # print(anova_result)
    # } else {
    # print("MADRS LMM residuals do not meet normality assumptions.")
    # }
    # """
    # ro.globalenv['madrs_df'] = pandas2ri.py2rpy(madrs_df)
    # result = r(r_script)
    # print(result)

    data = {
        'visit': [1, 3] * 2,
        'intervention': ['A'] * 2 + ['B'] * 2,
        'mean': [
            madrs_stats_df.loc['vis1_inta', 'mean'], madrs_stats_df.loc['vis3_inta', 'mean'],
            madrs_stats_df.loc['vis1_intb', 'mean'], madrs_stats_df.loc['vis3_intb', 'mean']
        ],
        'std_error': [
            madrs_stats_df.loc['vis1_inta', 'std_error'], madrs_stats_df.loc['vis3_inta', 'std_error'], 
            madrs_stats_df.loc['vis1_intb', 'std_error'], madrs_stats_df.loc['vis3_intb', 'std_error']
        ]
    }
    plot_data = pd.DataFrame(data)
    plot_data['visit'] = pd.Categorical(
        plot_data['visit'], categories=[1, 3], ordered=True)
    madrs_plot = (ggplot(plot_data, aes(x='visit', y='mean', color='intervention', group='intervention'))
            + geom_line(size=2)
            + geom_point(size=4)
            + geom_errorbar(aes(ymin='mean - std_error',
                            ymax='mean + std_error'), width=0.2)
            + scale_x_discrete(name='Visit')
            + labs(title='MADRS Scores Across Study Visits',
                x='Visit',
                y='MADRS Score',
                color='Intervention')
            + theme_classic()
            + scale_y_continuous(expand=(0, 0), limits=[16,32])
            )
    madrs_plot = madrs_plot + annotate("text", x=1.5, y=max(plot_data['mean']) + 3.25, label="***", size=16, color="black") + \
        annotate("segment", x=1, xend=2, y=max(plot_data['mean']) +3, yend=max(plot_data['mean']) + 3, color="black")
    madrs_plot.save('group/behavioural/madrs_plot.png')

    gad_df = rqmgp_df.dropna(subset=['gad'])
    visits = ['1', '3']
    interventions = ['a', 'b']
    columns = ['vals', 'mean', 'std_error', 'shap_p']
    index = ['vis1_inta', 'vis3_inta', 'vis1_intb', 'vis3_intb']
    gad_stats_df = pd.DataFrame(columns=columns, index=index)
    for visit in visits:
        for intervention in interventions:
            vals = gad_df[(gad_df['visit'] == visit) & (gad_df['intervention'] == intervention)]['gad'].tolist()
            mean = np.mean(vals)
            std_error = np.std(vals) / np.sqrt(len(vals))
            _, shap_p = stats.shapiro(vals)
            gad_stats_df.loc[f'vis{visit}_int{intervention}', 'vals'] = vals
            gad_stats_df.loc[f'vis{visit}_int{intervention}', 'mean'] = mean
            gad_stats_df.loc[f'vis{visit}_int{intervention}', 'std_error'] = std_error
            gad_stats_df.loc[f'vis{visit}_int{intervention}', 'shap_p'] = shap_p

    # os.environ['R_HOME'] = 'C:/Program Files/R/R-4.4.1'
    # pandas2ri.activate()
    # r = ro.r
    # utils = importr('utils')
    # utils.chooseCRANmirror(ind=1)
    # r_script = """
    # library(lme4)
    # library(lmerTest)
    # library(emmeans)
    # gad_df <- as.data.frame(gad_df)
    # model <- lmer(gad~visit*intervention + (1|p_id), data = gad_df)
    # residuals_model <- residuals(model)
    # shapiro_test_result <- shapiro.test(residuals_model)
    # print(shapiro_test_result)
    # if (shapiro_test_result$p.value > 0.05) {
    # print("GAD LMM residuals meet normality assumptions.")
    # anova_result <- anova(model)
    # print(anova_result)
    # } else {
    # print("GAD LMM residuals do not meet normality assumptions.")
    # }
    # """
    # ro.globalenv['gad_df'] = pandas2ri.py2rpy(gad_df)
    # result = r(r_script)
    # print(result)

    data = {
        'visit': [1, 3] * 2,
        'intervention': ['A'] * 2 + ['B'] * 2,
        'mean': [
            gad_stats_df.loc['vis1_inta', 'mean'], gad_stats_df.loc['vis3_inta', 'mean'],
            gad_stats_df.loc['vis1_intb', 'mean'], gad_stats_df.loc['vis3_intb', 'mean']
        ],
        'std_error': [
            gad_stats_df.loc['vis1_inta', 'std_error'], gad_stats_df.loc['vis3_inta', 'std_error'], 
            gad_stats_df.loc['vis1_intb', 'std_error'], gad_stats_df.loc['vis3_intb', 'std_error']
        ]
    }
    plot_data = pd.DataFrame(data)
    plot_data['visit'] = pd.Categorical(
        plot_data['visit'], categories=[1, 3], ordered=True)
    gad_plot = (ggplot(plot_data, aes(x='visit', y='mean', color='intervention', group='intervention'))
            + geom_line(size=2)
            + geom_point(size=4)
            + geom_errorbar(aes(ymin='mean - std_error',
                            ymax='mean + std_error'), width=0.2)
            + scale_x_discrete(name='Visit')
            + labs(title='GAD Scores Across Study Visits',
                x='Visit',
                y='GAD Score',
                color='Intervention')
            + theme_classic()
            + scale_y_continuous(expand=(0, 0), limits=[4,12])
            )
    gad_plot.save('group/behavioural/gad_plot.png')

    panas_pos_df = rqmgp_df.dropna(subset=['panas_pos'])
    visits = ['1', '3']
    interventions = ['a', 'b']
    columns = ['vals', 'mean', 'std_error', 'shap_p']
    index = ['vis1_inta', 'vis3_inta', 'vis1_intb', 'vis3_intb']
    panas_pos_stats_df = pd.DataFrame(columns=columns, index=index)
    for visit in visits:
        for intervention in interventions:
            vals = panas_pos_df[(panas_pos_df['visit'] == visit) & (panas_pos_df['intervention'] == intervention)]['panas_pos'].tolist()
            mean = np.mean(vals)
            std_error = np.std(vals) / np.sqrt(len(vals))
            _, shap_p = stats.shapiro(vals)
            panas_pos_stats_df.loc[f'vis{visit}_int{intervention}', 'vals'] = vals
            panas_pos_stats_df.loc[f'vis{visit}_int{intervention}', 'mean'] = mean
            panas_pos_stats_df.loc[f'vis{visit}_int{intervention}', 'std_error'] = std_error
            panas_pos_stats_df.loc[f'vis{visit}_int{intervention}', 'shap_p'] = shap_p

    # os.environ['R_HOME'] = 'C:/Program Files/R/R-4.4.1'
    # pandas2ri.activate()
    # r = ro.r
    # utils = importr('utils')
    # utils.chooseCRANmirror(ind=1)
    # r_script = """
    # library(lme4)
    # library(lmerTest)
    # library(emmeans)
    # panas_pos_df <- as.data.frame(panas_pos_df)
    # model <- lmer(panas_pos~visit*intervention + (1|p_id), data = panas_pos_df)
    # residuals_model <- residuals(model)
    # shapiro_test_result <- shapiro.test(residuals_model)
    # print(shapiro_test_result)
    # if (shapiro_test_result$p.value > 0.05) {
    # print("PANAS Positive LMM residuals meet normality assumptions.")
    # anova_result <- anova(model)
    # print(anova_result)
    # } else {
    # print("PANAS Positive LMM residuals do not meet normality assumptions.")
    # }
    # """
    # ro.globalenv['panas_pos_df'] = pandas2ri.py2rpy(panas_pos_df)
    # result = r(r_script)
    # print(result)

    data = {
        'visit': [1, 3] * 2,
        'intervention': ['A'] * 2 + ['B'] * 2,
        'mean': [
            panas_pos_stats_df.loc['vis1_inta', 'mean'], panas_pos_stats_df.loc['vis3_inta', 'mean'],
            panas_pos_stats_df.loc['vis1_intb', 'mean'], panas_pos_stats_df.loc['vis3_intb', 'mean']
        ],
        'std_error': [
            panas_pos_stats_df.loc['vis1_inta', 'std_error'], panas_pos_stats_df.loc['vis3_inta', 'std_error'], 
            panas_pos_stats_df.loc['vis1_intb', 'std_error'], panas_pos_stats_df.loc['vis3_intb', 'std_error']
        ]
    }
    plot_data = pd.DataFrame(data)
    plot_data['visit'] = pd.Categorical(
        plot_data['visit'], categories=[1, 3], ordered=True)
    panas_pos_plot = (ggplot(plot_data, aes(x='visit', y='mean', color='intervention', group='intervention'))
            + geom_line(size=2)
            + geom_point(size=4)
            + geom_errorbar(aes(ymin='mean - std_error',
                            ymax='mean + std_error'), width=0.2)
            + scale_x_discrete(name='Visit')
            + labs(title='PANAS Positive Scores Across Study Visits',
                x='Visit',
                y='PANAS Positive Score',
                color='Intervention')
            + theme_classic()
            + scale_y_continuous(expand=(0, 0), limits=[18,28])
            )
    panas_pos_plot = panas_pos_plot + annotate("text", x=1.5, y=max(plot_data['mean']) + 3.25, label="*", size=16, color="black") + \
        annotate("segment", x=1, xend=2, y=max(plot_data['mean']) +3, yend=max(plot_data['mean']) + 3, color="black")
    panas_pos_plot.save('group/behavioural/panas_pos_plot.png')

    panas_neg_df = rqmgp_df.dropna(subset=['panas_neg'])
    visits = ['1', '3']
    interventions = ['a', 'b']
    columns = ['vals', 'mean', 'std_error', 'shap_p']
    index = ['vis1_inta', 'vis3_inta', 'vis1_intb', 'vis3_intb']
    panas_neg_stats_df = pd.DataFrame(columns=columns, index=index)
    for visit in visits:
        for intervention in interventions:
            vals = panas_neg_df[(panas_neg_df['visit'] == visit) & (panas_neg_df['intervention'] == intervention)]['panas_neg'].tolist()
            mean = np.mean(vals)
            std_error = np.std(vals) / np.sqrt(len(vals))
            _, shap_p = stats.shapiro(vals)
            panas_neg_stats_df.loc[f'vis{visit}_int{intervention}', 'vals'] = vals
            panas_neg_stats_df.loc[f'vis{visit}_int{intervention}', 'mean'] = mean
            panas_neg_stats_df.loc[f'vis{visit}_int{intervention}', 'std_error'] = std_error
            panas_neg_stats_df.loc[f'vis{visit}_int{intervention}', 'shap_p'] = shap_p

    # os.environ['R_HOME'] = 'C:/Program Files/R/R-4.4.1'
    # pandas2ri.activate()
    # r = ro.r
    # utils = importr('utils')
    # utils.chooseCRANmirror(ind=1)
    # r_script = """
    # library(lme4)
    # library(lmerTest)
    # library(emmeans)
    # panas_neg_df <- as.data.frame(panas_neg_df)
    # model <- lmer(panas_neg~visit*intervention + (1|p_id), data = panas_neg_df)
    # residuals_model <- residuals(model)
    # shapiro_test_result <- shapiro.test(residuals_model)
    # print(shapiro_test_result)
    # if (shapiro_test_result$p.value > 0.05) {
    # print("PANAS Negative LMM residuals meet normality assumptions.")
    # anova_result <- anova(model)
    # print(anova_result)
    # } else {
    # print("PANAS Negative LMM residuals do not meet normality assumptions.")
    # }
    # """
    # ro.globalenv['panas_neg_df'] = pandas2ri.py2rpy(panas_neg_df)
    # result = r(r_script)
    # print(result)

    data = {
        'visit': [1, 3] * 2,
        'intervention': ['A'] * 2 + ['B'] * 2,
        'mean': [
            panas_neg_stats_df.loc['vis1_inta', 'mean'], panas_neg_stats_df.loc['vis3_inta', 'mean'],
            panas_neg_stats_df.loc['vis1_intb', 'mean'], panas_neg_stats_df.loc['vis3_intb', 'mean']
        ],
        'std_error': [
            panas_neg_stats_df.loc['vis1_inta', 'std_error'], panas_neg_stats_df.loc['vis3_inta', 'std_error'], 
            panas_neg_stats_df.loc['vis1_intb', 'std_error'], panas_neg_stats_df.loc['vis3_intb', 'std_error']
        ]
    }
    plot_data = pd.DataFrame(data)
    plot_data['visit'] = pd.Categorical(
        plot_data['visit'], categories=[1, 3], ordered=True)
    panas_neg_plot = (ggplot(plot_data, aes(x='visit', y='mean', color='intervention', group='intervention'))
            + geom_line(size=2)
            + geom_point(size=4)
            + geom_errorbar(aes(ymin='mean - std_error',
                            ymax='mean + std_error'), width=0.2)
            + scale_x_discrete(name='Visit')
            + labs(title='PANAS Negative Scores Across Study Visits',
                x='Visit',
                y='PANAS Negative Score',
                color='Intervention')
            + theme_classic()
            + scale_y_continuous(expand=(0, 0), limits=[20,30])
            )
    panas_neg_plot.save('group/behavioural/panas_neg_plot.png')

    # Step 4: Run LMMs of Memory Intensity Ratings.
    columns = ['p_id', 'time', 'intervention', 'guilt_rating', 'indignation_rating']
    mem_intensity_df = pd.DataFrame(columns=columns)
    p_id_column = participants * 2
    time_column = ['pre'] * 20 + ['post'] * 20
    intervention_values = ecrf_df.loc['intervention'].tolist()
    intervention_column = list(intervention_values) * 2
    pre_memory_intensity_guilt_1 = ecrf_df.loc['pre_memory_intensity_guilt_1'].tolist()
    pre_memory_intensity_guilt_2 = ecrf_df.loc['pre_memory_intensity_guilt_2'].tolist()
    pre_memory_intensity_indignation_1 = ecrf_df.loc['pre_memory_intensity_indignation_1'].tolist()
    pre_memory_intensity_indignation_2 = ecrf_df.loc['pre_memory_intensity_indignation_2'].tolist()
    post_memory_intensity_guilt_1 = ecrf_df.loc['post_memory_intensity_guilt_1'].tolist()
    post_memory_intensity_guilt_2 = ecrf_df.loc['post_memory_intensity_guilt_2'].tolist()
    post_memory_intensity_indignation_1 = ecrf_df.loc['post_memory_intensity_indignation_1'].tolist()
    post_memory_intensity_indignation_2 = ecrf_df.loc['post_memory_intensity_indignation_2'].tolist()
    pre_guilt = [(a + b) / 2 for a, b in zip(pre_memory_intensity_guilt_1, pre_memory_intensity_guilt_2)]
    pre_indignation = [(a + b) / 2 for a, b in zip(pre_memory_intensity_indignation_1, pre_memory_intensity_indignation_2)]
    post_guilt = [(a + b) / 2 for a, b in zip(post_memory_intensity_guilt_1, post_memory_intensity_guilt_2)]
    post_indignation = [(a + b) / 2 for a, b in zip(post_memory_intensity_indignation_1, post_memory_intensity_indignation_2)]
    guilt_rating_column = pre_guilt + post_guilt
    indignation_rating_column = pre_indignation +  post_indignation
    mem_intensity_df['p_id'] = p_id_column
    mem_intensity_df['time'] = time_column
    mem_intensity_df['intervention'] = intervention_column
    mem_intensity_df['guilt_rating'] = guilt_rating_column
    mem_intensity_df['indignation_rating'] = indignation_rating_column

    time = ['pre', 'post']
    interventions = ['a', 'b']
    columns = ['rating', 'mean', 'std_error', 'shap_p']
    index = ['pre_inta', 'post_inta', 'pre_intb', 'post_intb']
    guilt_mem_intensity_stats_df = pd.DataFrame(columns=columns, index=index)
    for item in time:
        for intervention in interventions:
            ratings = mem_intensity_df[(mem_intensity_df['time'] == item) & (mem_intensity_df['intervention'] == intervention)]['guilt_rating'].tolist()
            mean = np.mean(ratings)
            std_error = np.std(ratings) / np.sqrt(len(ratings))
            _, shap_p = stats.shapiro(vals)
            guilt_mem_intensity_stats_df.loc[f'{item}_int{intervention}', 'rating'] = ratings
            guilt_mem_intensity_stats_df.loc[f'{item}_int{intervention}', 'mean'] = mean
            guilt_mem_intensity_stats_df.loc[f'{item}_int{intervention}', 'std_error'] = std_error
            guilt_mem_intensity_stats_df.loc[f'{item}_int{intervention}', 'shap_p'] = shap_p

    # os.environ['R_HOME'] = 'C:/Program Files/R/R-4.4.1'
    # pandas2ri.activate()
    # r = ro.r
    # utils = importr('utils')
    # utils.chooseCRANmirror(ind=1)
    # r_script = """
    # library(lme4)
    # library(lmerTest)
    # library(emmeans)
    # mem_intensity_df <- as.data.frame(mem_intensity_df)
    # model <- lmer(guilt_rating~time*intervention + (1|p_id), data = mem_intensity_df)
    # residuals_model <- residuals(model)
    # shapiro_test_result <- shapiro.test(residuals_model)
    # print(shapiro_test_result)
    # if (shapiro_test_result$p.value > 0.05) {
    # print("Guilt Memory Intensity LMM residuals meet normality assumptions.")
    # anova_result <- anova(model)
    # print(anova_result)
    # } else {
    # print("Guilt Memory Intensity LMM residuals do not meet normality assumptions.")
    # }
    # """
    # ro.globalenv['mem_intensity_df'] = pandas2ri.py2rpy(mem_intensity_df)
    # result = r(r_script)
    # print(result)

    data = {
        'time': ['Pre-neurofeedback', 'Post-neurofeedback'] * 2,
        'intervention': ['A'] * 2 + ['B'] * 2,
        'mean': [
            guilt_mem_intensity_stats_df.loc['pre_inta', 'mean'], guilt_mem_intensity_stats_df.loc['post_inta', 'mean'],
            guilt_mem_intensity_stats_df.loc['pre_intb', 'mean'], guilt_mem_intensity_stats_df.loc['post_intb', 'mean']
        ],
        'std_error': [
            guilt_mem_intensity_stats_df.loc['pre_inta', 'std_error'], guilt_mem_intensity_stats_df.loc['post_inta', 'std_error'], 
            guilt_mem_intensity_stats_df.loc['pre_intb', 'std_error'], guilt_mem_intensity_stats_df.loc['post_intb', 'std_error']
        ]
    }
    plot_data = pd.DataFrame(data)
    plot_data['time'] = pd.Categorical(
        plot_data['time'], categories=['Pre-neurofeedback', 'Post-neurofeedback'], ordered=True)
    guilt_mem_intensity_plot = (ggplot(plot_data, aes(x='time', y='mean', color='intervention', group='intervention'))
            + geom_line(size=2)
            + geom_point(size=4)
            + geom_errorbar(aes(ymin='mean - std_error',
                            ymax='mean + std_error'), width=0.2)
            + scale_x_discrete(name='Time')
            + labs(title='Guilt Memory Intensity Ratings Before and After Neurofeedback',
                x='Time',
                y='Mean Guilt Memory Intensity Rating',
                color='Intervention')
            + theme_classic()
            + scale_y_continuous(expand=(0, 0), limits=[5,7])
            )
    print(guilt_mem_intensity_plot)
    guilt_mem_intensity_plot.save('guilt_mem_intensity_plot.png')

    time = ['pre', 'post']
    interventions = ['a', 'b']
    columns = ['rating', 'mean', 'std_error', 'shap_p']
    index = ['pre_inta', 'post_inta', 'pre_intb', 'post_intb']
    indignation_mem_intensity_stats_df = pd.DataFrame(columns=columns, index=index)
    for item in time:
        for intervention in interventions:
            ratings = mem_intensity_df[(mem_intensity_df['time'] == item) & (mem_intensity_df['intervention'] == intervention)]['indignation_rating'].tolist()
            mean = np.mean(ratings)
            std_error = np.std(ratings) / np.sqrt(len(ratings))
            _, shap_p = stats.shapiro(vals)
            indignation_mem_intensity_stats_df.loc[f'{item}_int{intervention}', 'rating'] = ratings
            indignation_mem_intensity_stats_df.loc[f'{item}_int{intervention}', 'mean'] = mean
            indignation_mem_intensity_stats_df.loc[f'{item}_int{intervention}', 'std_error'] = std_error
            indignation_mem_intensity_stats_df.loc[f'{item}_int{intervention}', 'shap_p'] = shap_p

    # os.environ['R_HOME'] = 'C:/Program Files/R/R-4.4.1'
    # pandas2ri.activate()
    # r = ro.r
    # utils = importr('utils')
    # utils.chooseCRANmirror(ind=1)
    # r_script = """
    # library(lme4)
    # library(lmerTest)
    # library(emmeans)
    # mem_intensity_df <- as.data.frame(mem_intensity_df)
    # model <- lmer(indignation_rating~time*intervention + (1|p_id), data = mem_intensity_df)
    # residuals_model <- residuals(model)
    # shapiro_test_result <- shapiro.test(residuals_model)
    # print(shapiro_test_result)
    # if (shapiro_test_result$p.value > 0.05) {
    # print("Indignation Memory Intensity LMM residuals meet normality assumptions.")
    # anova_result <- anova(model)
    # print(anova_result)
    # } else {
    # print("Indignation Memory Intensity LMM residuals do not meet normality assumptions.")
    # }
    # """
    # ro.globalenv['mem_intensity_df'] = pandas2ri.py2rpy(mem_intensity_df)
    # result = r(r_script)
    # print(result)

    data = {
        'time': ['Pre-neurofeedback', 'Post-neurofeedback'] * 2,
        'intervention': ['A'] * 2 + ['B'] * 2,
        'mean': [
            indignation_mem_intensity_stats_df.loc['pre_inta', 'mean'], indignation_mem_intensity_stats_df.loc['post_inta', 'mean'],
            indignation_mem_intensity_stats_df.loc['pre_intb', 'mean'], indignation_mem_intensity_stats_df.loc['post_intb', 'mean']
        ],
        'std_error': [
            indignation_mem_intensity_stats_df.loc['pre_inta', 'std_error'], indignation_mem_intensity_stats_df.loc['post_inta', 'std_error'], 
            indignation_mem_intensity_stats_df.loc['pre_intb', 'std_error'], indignation_mem_intensity_stats_df.loc['post_intb', 'std_error']
        ]
    }
    plot_data = pd.DataFrame(data)
    plot_data['time'] = pd.Categorical(
        plot_data['time'], categories=['Pre-neurofeedback', 'Post-neurofeedback'], ordered=True)
    indignation_mem_intensity_plot = (ggplot(plot_data, aes(x='time', y='mean', color='intervention', group='intervention'))
            + geom_line(size=2)
            + geom_point(size=4)
            + geom_errorbar(aes(ymin='mean - std_error',
                            ymax='mean + std_error'), width=0.2)
            + scale_x_discrete(name='Time')
            + labs(title='Indignation Memory Intensity Ratings Before and After Neurofeedback',
                x='Time',
                y='Mean Indignation Memory Intensity Rating',
                color='Intervention')
            + theme_classic()
            + scale_y_continuous(expand=(0, 0), limits=[5,7])
            )
    print(indignation_mem_intensity_plot)
    indignation_mem_intensity_plot.save('indignation_mem_intensity_plot.png')

#endregion

#region 6) FMRI PREPARATION AND PREPROCESSING.

answer = input("Would you like to perform fMRI preparation and preprocessing? (y/n)\n")
if answer == 'y':
    p_id = input("Enter the participant's ID (e.g. P001). If you want to analyse all participants simultaneously, enter 'ALL'.\n")
    participants = ['P004', 'P006', 'P020', 'P030', 'P059', 'P078', 'P093', 'P094', 'P100', 'P107', 'P122', 'P125', 'P127', 'P128', 'P136', 'P145', 'P155', 'P199', 'P215', 'P216']
    runs = ['run01', 'run02', 'run03', 'run04']
    if p_id == 'ALL':
        participants_to_iterate = participants
    else:
        participants_to_iterate = [p_id]
    code_folder = 'code'
    bids_folder = os.path.join(os.getcwd(), 'bids')
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
                print(f"Deleting group/preproc folder...")
                shutil.rmtree(group_preproc_folder)
                print(f"group/preproc folder successfully deleted.")
            else:
                print(f"{p_id} group/preproc folder does not exist.")
            if p_id.startswith('P'):
                p_id_stripped = p_id.replace('P', '')
                p_id_stripped_bids_folder = os.path.join(os.getcwd(), 'bids', f'sub-{p_id_stripped}')
                shutil.rmtree(p_id_stripped_bids_folder)
            else:
                for item in os.listdir(bids_folder):
                    item_path = os.path.join(bids_folder, item)
                    if item != code_folder:
                        if os.path.exists(item_path):
                            print(f"Deleting bids/{item} folder...")
                            shutil.rmtree(item_path)
                            print(f"bids/{item} folder successfully deleted.")
                        else: 
                            print(f"bids/{item} folder does not exist.")
        else:
            sys.exit()
    
    # Step 1: Create Directories.
    print("\n###### STEP 1: CREATE DIRECTORIES ######")
    for p_id in participants_to_iterate:
        p_id_folder = os.path.join(os.getcwd(), p_id)
        os.makedirs(p_id_folder, exist_ok=True)
        analysis_folder = os.path.join(os.getcwd(), p_id, 'analysis')
        os.makedirs(analysis_folder, exist_ok=True)
        preproc_folder = os.path.join(os.getcwd(), p_id, 'analysis', 'preproc')
        os.makedirs(preproc_folder, exist_ok=True)
        group_folder = os.path.join(os.getcwd(), 'group')
        os.makedirs(group_folder, exist_ok=True)
        group_preproc_folder = os.path.join(os.getcwd(), 'group', 'preproc')
        os.makedirs(group_preproc_folder, exist_ok=True)
        bids_folder = os.path.join(os.getcwd(), 'bids')
        os.makedirs(bids_folder, exist_ok=True)
    print("Directories created.")
        
    # Step 2: Convert DICOMS to BIDS Format.
    print("\n###### STEP 2: CONVERT DICOMS TO BIDS FORMAT ######")
    for p_id in participants_to_iterate:
        path = os.path.join(os.getcwd(), f'{p_id}', 'data', 'neurofeedback')
        cisc_folder = None
        for folder_name in os.listdir(path):
            if "CISC" in folder_name:
                cisc_folder = folder_name
                break
        if cisc_folder is None:
            print("No 'CISC' folder found in the 'neurofeedback' directory.")
            exit(1)
        p_id_stripped = p_id.replace('P', '')
        if not os.path.exists(f"bids/sub-{p_id_stripped}"):
            print(f"Converting DICOMs to BIDS Nifti format for P{p_id_stripped}...")
            subprocess.run(['heudiconv', '-d', f'/its/home/bsms9pc4/Desktop/cisc2/projects/stone_depnf/Neurofeedback/participant_data/P{{subject}}/data/neurofeedback/{cisc_folder}/*.dcm', '-o', '/its/home/bsms9pc4/Desktop/cisc2/projects/stone_depnf/Neurofeedback/participant_data/bids/', '-f', '/its/home/bsms9pc4/Desktop/cisc2/projects/stone_depnf/Neurofeedback/participant_data/bids/code/heuristic.py', '-s', f'{p_id_stripped}', '-c', 'dcm2niix', '-b', '--overwrite'])
        else: 
            print(f"DICOMs already converted to BIDS Nifti format for P{p_id_stripped}. Skipping process.")
    print("BIDS conversion completed.")

    # Step 3: Label Fieldmaps.
    print("\n###### STEP 3: LABEL FIELDMAPS ######")
    good_participants = ['P059', 'P100', 'P107', 'P122', 'P125', 'P127', 'P128', 'P136', 'P145', 'P155', 'P199', 'P215', 'P216']
    for p_id in participants_to_iterate:
        if p_id in good_participants:
            print(f"Labelling fieldmap JSON files for {p_id}...")
            p_id_stripped = p_id.replace('P', '')
            func_directory = f"bids/sub-{p_id_stripped}/func"
            func_files = []
            for file_name in os.listdir(func_directory):
                if file_name.endswith(".nii.gz"):
                    file_path = os.path.join("func", file_name)
                    func_files.append(file_path)
            ap_fieldmap_json = f"bids/sub-{p_id_stripped}/fmap/sub-{p_id_stripped}_dir-AP_epi.json"
            pa_fieldmap_json = f"bids/sub-{p_id_stripped}/fmap/sub-{p_id_stripped}_dir-PA_epi.json"
            fieldmap_json_files = [ap_fieldmap_json, pa_fieldmap_json]
            for fieldmap_json in fieldmap_json_files:
                with open(fieldmap_json, 'r') as file:
                    json_data = json.load(file)
                if "IntendedFor" not in json_data:
                    items = list(json_data.items())
                    intended_for_item = ("IntendedFor", func_files)
                    insert_index = next((i for i, (key, _) in enumerate(items) if key > "IntendedFor"), len(items))
                    items.insert(insert_index, intended_for_item)
                    json_data = dict(items)
                    subprocess.run(['chmod', '+w', fieldmap_json], check=True)
                    with open(fieldmap_json, 'w') as file:
                        json.dump(json_data, file, indent=2)
                else:
                    print(f"{fieldmap_json} already labelled for P{p_id_stripped}. Skipping process.")

    # Step 4: Copy BIDS Niftis and singularity image to cluster server.
    print("\n###### STEP 4: COPY BIDS NIFTIS AND SINGULARITY IMAGE TO CLUSTER ######")
    if not os.path.exists('/mnt/lustre/scratch/bsms/bsms9pc4/stone_depnf/fmriprep/bids'):
        print("Copying BIDS files for all participants to cluster...")
        shutil.copytree('bids', '/mnt/lustre/scratch/bsms/bsms9pc4/stone_depnf/fmriprep/bids')
    if not os.path.exists('/mnt/lustre/scratch/bsms/bsms9pc4/stone_depnf/fmriprep/fmriprep_24.0.1.simg'):
        print("Copying fmriprep singularity image to cluster...")
        shutil.copy('/research/cisc2/shared/fmriprep_singularity/fmriprep_24.0.1.simg', '/mnt/lustre/scratch/bsms/bsms9pc4/stone_depnf/fmriprep/fmriprep_24.0.1.simg')
    print("BIDS Niftis and singularity image copied successfully.")

    # Step 5: Run fmriprep on cluster server.
    print("\n###### STEP 5: RUN FMRIPREP ON CLUSTER ######")
    fmriprep_cluster_script = r"""
    #!/bin/bash
    #$ -N bic_fmriprep          # job name #one subject test
    #$ -pe openmp 5             # parallel environment #how many CPU cores to use
    # # Logging directory o=stdout, e=stderror, -j join them together or not? yes/no (y/n)
    # #$ -j y
    #$ -o /mnt/lustre/scratch/bsms/bsms9pc4/stone_depnf/fmriprep/logs/
    #$ -e /mnt/lustre/scratch/bsms/bsms9pc4/stone_depnf/fmriprep/logs/
    # # Memory assigned soft but makes sure it is available
    #$ -l m_mem_free=8G 
    # # Memory HARD limit
    #$ -l h_vmem=8G
    #$ -l 'h=!node001&!node069&!node072&!node076&!node077' # nodes NOT to use 
    # # Syntax for task array start-stop:step eg. 1-1000:10 == [1,11,21,31,41...]
    #$ -t 1-20  #This sets SGE_TASK_ID! Set it equal to number of subjects #you can put 1 or 1-n
    # # Tasks Concurrent (Ie max number of concurrent)
    #$ -tc 20 #maximum tasks running simultaneously .
    #$ -jc test.long        # Short=2h, test.default= 8h, test.long=7d 21h, verlong.default=30d
    module add sge
    DATA_DIR=/mnt/lustre/scratch/bsms/bsms9pc4/stone_depnf/fmriprep/bids
    SCRATCH_DIR=/mnt/lustre/scratch/bsms/bsms9pc4/stone_depnf/fmriprep/scratch
    OUT_DIR=/mnt/lustre/scratch/bsms/bsms9pc4/stone_depnf/fmriprep/derivatives
    LICENSE=/research/cisc2/shared/fs_license/license.txt  
    cd ${DATA_DIR}
    SUBJLIST=$(find sub-* -maxdepth 0  -type d)
    len=${#SUBJLIST[@]}
    echo Number of subjects  = $len
    cd ${HOME}
    echo This is the task id $SGE_TASK_ID
    i=$(expr $SGE_TASK_ID - 1)
    echo this is i $i
    arr=($SUBJLIST)
    SUBJECT=${arr[i]}
    echo $SUBJECT
    singularity run --cleanenv \
            -B ${DATA_DIR}:/data \
            -B ${OUT_DIR}/:/out \
            -B ${SCRATCH_DIR}:/wd \
            -B ${LICENSE}:/license \
            /mnt/lustre/scratch/bsms/bsms9pc4/stone_depnf/fmriprep/fmriprep_24.0.1.simg \
            --skip_bids_validation \
            --participant-label ${SUBJECT} \
            --omp-nthreads 5 --nthreads 5 --mem_mb 30000 \
            --low-mem --use-aroma\
            --output-spaces MNI152NLin2009cAsym:res-2 \
            --fs-license-file /license \
            --work-dir /wd \
            --cifti-output 91k \
            /data /out/ participant
    echo Done
    exit
    """
    frmriprep_cluster_script = textwrap.dedent(fmriprep_cluster_script)
    with open('bids/fmriprep_cluster.sh', 'w') as f:
        f.write(fmriprep_cluster_script)
    subprocess.run(['ssh', '-Y', 'bsms9pc4@apollo2.hpc.susx.ac.uk', 'source /etc/profile; source ~/.bash_profile; qsub /research/cisc2/projects/stone_depnf/Neurofeedback/participant_data/bids/fmriprep_cluster.sh'])
    
    # Step X: XXX
    if p_id == 'ALL':
        participants_to_iterate = participants
    else:
        participants_to_iterate = [p_id]

    # fmriprep clean up
    # move remaining fmriprep output files back onto cisc2



#endregion

#region 7) FMRI ANALYSIS.

#endregion

#region 8) SUSCEPTIBILITY ANALYSIS.

answer = input("Would you like to execute susceptibility artifact analysis? (y/n)\n")
if answer == 'y':
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
        fnirt_folder = os.path.join(os.getcwd(), p_id, "analysis", "susceptibility", "fnirt_test")
        os.makedirs(fnirt_folder, exist_ok=True)
        susc_scc_folder = os.path.join(os.getcwd(), p_id, "analysis", "susceptibility", "susc_scc")
        os.makedirs(susc_scc_folder, exist_ok=True)
        nifti_folder = os.path.join(os.getcwd(), p_id, 'analysis', 'susceptibility', 'susc_scc', 'niftis')
        os.makedirs(nifti_folder, exist_ok=True)
        fnirt_folder_1 = os.path.join(os.getcwd(), p_id, "analysis", "susceptibility", "fnirt_test", "1")
        os.makedirs(fnirt_folder_1, exist_ok=True)
        fnirt_folder_2 = os.path.join(os.getcwd(), p_id, "analysis", "susceptibility", "fnirt_test", "2")
        os.makedirs(fnirt_folder_2, exist_ok=True)
        fnirt_folder_3 = os.path.join(os.getcwd(), p_id, "analysis", "susceptibility", "fnirt_test", "3")
        os.makedirs(fnirt_folder_3, exist_ok=True)
        fnirt_folder_4 = os.path.join(os.getcwd(), p_id, "analysis", "susceptibility", "fnirt_test", "4")
        os.makedirs(fnirt_folder_4, exist_ok=True)
        group_folder = os.path.join(os.getcwd(), "group")
        os.makedirs(group_folder, exist_ok=True)
        group_susceptibility_folder = os.path.join(os.getcwd(), "group", "susceptibility")
        os.makedirs(group_susceptibility_folder, exist_ok=True)
        group_susc_scc_folder = os.path.join(os.getcwd(), "group", "susceptibility", 'susc_scc')
        os.makedirs(group_susc_scc_folder, exist_ok=True)
        group_fnirt_folder = os.path.join(os.getcwd(), "group", "susceptibility", "fnirt_test")
        os.makedirs(group_fnirt_folder, exist_ok=True)
        group_fnirt_folder_1 = os.path.join(os.getcwd(), 'group', 'susceptibility', 'fnirt_test', '1')
        os.makedirs(group_fnirt_folder_1, exist_ok=True)
        group_fnirt_folder_2 = os.path.join(os.getcwd(), 'group', 'susceptibility', 'fnirt_test', '2')
        os.makedirs(group_fnirt_folder_2, exist_ok=True)
        group_fnirt_folder_3 = os.path.join(os.getcwd(), 'group', 'susceptibility', 'fnirt_test', '3')
        os.makedirs(group_fnirt_folder_3, exist_ok=True)
        group_fnirt_folder_4 = os.path.join(os.getcwd(), 'group', 'susceptibility', 'fnirt_test', '4')
        os.makedirs(group_fnirt_folder_4, exist_ok=True)
    print('Directories created.')

    # Step 2: Calculate percentage of ROI voxels outside the brain during neurofeedback.
    print("\n###### STEP 2: CALCULATE PERCENTAGE OF ROI VOXELS OUTSIDE BRAIN DURING NEUROFEEDBACK ######")
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
    def read_roi_file(roi_file):
        voxel_coordinates = []
        with open(roi_file, 'r') as file:
            content = file.read()
            matches = re.findall(r'(?<=\n)\s*\d+\s+\d+\s+\d+', content)
            for match in matches:
                coordinates = match.split()
                voxel_coordinates.append((int(coordinates[0]), int(coordinates[1]), int(coordinates[2])))
        return voxel_coordinates
    def process_participant(p_id, runs):
        path = os.path.join(os.getcwd(), p_id, 'data', 'neurofeedback')
        cisc_folder = None
        for folder_name in os.listdir(path):
            if "CISC" in folder_name:
                cisc_folder = folder_name
                break
        if cisc_folder is None:
            print(f"No 'CISC' folder found in the 'neurofeedback' directory for participant {p_id}.")
            return
        src_folder = os.path.join(path, cisc_folder)
        analysis_folder = os.path.join(os.getcwd(), p_id, 'analysis', 'susceptibility')
        dicoms_folder = os.path.join(analysis_folder, 'susc_scc', 'dicoms')
        os.makedirs(dicoms_folder, exist_ok=True)
        run_folders = {f"run0{num}_dicoms": os.path.join(dicoms_folder, f"run0{num}_dicoms") for num in range(1, 5)}
        for folder in run_folders.values():
            os.makedirs(folder, exist_ok=True)
        files = [f for f in os.listdir(src_folder) if f.endswith('.dcm')]
        seq_vol_counts = {}
        for file in files:
            sequence_number, volume_number = get_sequence_numbers(file)
            if sequence_number not in seq_vol_counts:
                seq_vol_counts[sequence_number] = []
            seq_vol_counts[sequence_number].append(volume_number)
        seq_210 = [seq for seq, vols in seq_vol_counts.items() if len(vols) == 210]
        seq_238 = [seq for seq, vols in seq_vol_counts.items() if len(vols) == 238]
        min_210, max_210 = min(seq_210), max(seq_210)
        min_238, max_238 = min(seq_238), max(seq_238)
        if not os.listdir(run_folders["run01_dicoms"]):
            print(f"Copying Run01 dicoms for participant {p_id}...")
            copy_files(src_folder, run_folders["run01_dicoms"], min_210)
        if not os.listdir(run_folders["run02_dicoms"]):
            print(f"Copying Run02 dicoms for participant {p_id}...")
            copy_files(src_folder, run_folders["run02_dicoms"], min_238)
        if not os.listdir(run_folders["run03_dicoms"]):
            print(f"Copying Run03 dicoms for participant {p_id}...")
            copy_files(src_folder, run_folders["run03_dicoms"], max_238)
        if not os.listdir(run_folders["run04_dicoms"]):
            print(f"Copying Run04 dicoms for participant {p_id}...")
            copy_files(src_folder, run_folders["run04_dicoms"], max_210)
        output_folder = os.path.join(analysis_folder, 'susc_scc', 'niftis')
        os.makedirs(output_folder, exist_ok=True)
        for run in runs:
            destination_folder = run_folders[f"{run}_dicoms"]
            output_file = os.path.join(output_folder, f"{run}.nii")
            if not os.path.exists(output_file):
                print(f"Converting {run.upper()} DICOM files to Nifti format for participant {p_id}...")
                subprocess.run(['dcm2niix', '-o', output_folder, '-f', f"{run}", '-b', 'n', destination_folder])
            averaged_file = os.path.join(output_folder, f"{run}_averaged.nii.gz")
            if not os.path.exists(averaged_file):
                subprocess.run(['fslmaths', output_file, '-Tmean', averaged_file])
        run_num = ['1', '2', '3', '4']
        for num in run_num:
            roi_file = os.path.join(os.getcwd(), p_id, 'data', 'neurofeedback', cisc_folder, 'depression_neurofeedback', f'target_folder_run-{num}', f'depnf_run-{num}.roi')
            voxel_coordinates = read_roi_file(roi_file)
            functional_image = f'{p_id}/analysis/susceptibility/susc_scc/niftis/run0{num}_averaged.nii.gz'
            functional_image_info = nib.load(functional_image)
            functional_dims = functional_image_info.shape
            binary_volume = np.zeros(functional_dims)
            for voxel in voxel_coordinates:
                x, y, z = voxel
                binary_volume[x, y, z] = 1
            binary_volume = np.flip(binary_volume, axis=1)
            functional_affine = functional_image_info.affine
            binary_nifti = nib.Nifti1Image(binary_volume, affine=functional_affine)
            nib.save(binary_nifti, f'{p_id}/analysis/susceptibility/susc_scc/niftis/run0{num}_subject_space_ROI.nii.gz')
        for run in runs:
            betted_file = os.path.join(output_folder, f"{run}_averaged_betted.nii.gz")
            if not os.path.exists(betted_file):
                subprocess.run(['bet', f'{p_id}/analysis/susceptibility/susc_scc/niftis/{run}_averaged.nii.gz', betted_file, '-R'])
            functional_image_betted = f'{p_id}/analysis/susceptibility/susc_scc/niftis/{run}_averaged_betted.nii.gz'
            binary_nifti_image = f'{p_id}/analysis/susceptibility/susc_scc/niftis/{run}_subject_space_ROI.nii.gz'
            screenshot_file = f'{p_id}/analysis/susceptibility/susc_scc/ROI_on_{run}_EPI.png'
            binary_img = nib.load(binary_nifti_image)
            binary_data = binary_img.get_fdata()
            indices = np.nonzero(binary_data)
            center_x = int(np.mean(indices[0]))
            center_y = int(np.mean(indices[1]))
            center_z = int(np.mean(indices[2]))
            result = subprocess.run(['fsleyes', 'render', '--scene', 'lightbox', '--voxelLoc', f'{center_x}', f'{center_y}', f'{center_z}', '-hc', '-hl', '-of', screenshot_file, functional_image_betted, binary_nifti_image, '-ot', 'mask', '-mc', '1', '0', '0'], capture_output=True, text=True)
            if result.returncode == 0:
                print(f"Screenshot saved as {screenshot_file}")
            else:
                print(f"Error encountered: {result.stderr}")
        for run in runs:
            bin_file = os.path.join(output_folder, f"{run}_averaged_betted_bin.nii.gz")
            threshold = '100'
            if not os.path.exists(bin_file):
                subprocess.run(['fslmaths', f'{p_id}/analysis/susceptibility/susc_scc/niftis/{run}_averaged_betted.nii.gz', '-thr', threshold, '-bin', bin_file])
            inverse_file = os.path.join(output_folder, f"{run}_averaged_betted_bin_inverse.nii.gz")
            if not os.path.exists(inverse_file):
                subprocess.run(['fslmaths', f'{p_id}/analysis/susceptibility/susc_scc/niftis/{run}_averaged_betted_bin.nii.gz', '-sub', '1', '-abs', inverse_file])
            result2 = subprocess.run(['fslstats', f'{p_id}/analysis/susceptibility/susc_scc/niftis/{run}_subject_space_ROI.nii.gz', '-k', f'{p_id}/analysis/susceptibility/susc_scc/niftis/{run}_averaged_betted_bin_inverse.nii.gz', '-V'], capture_output=True, text=True)
            if result2.returncode == 0:
                result2_output = result2.stdout.strip()
            else:
                print(f"Error executing second fslstats command for {run}.")
                continue
            result2_output_values = result2_output.split()
            voxels_outside = float(result2_output_values[0])
            result3 = subprocess.run(['fslstats', f'{p_id}/analysis/susceptibility/susc_scc/niftis/{run}_subject_space_ROI.nii.gz', '-V'], capture_output=True, text=True)
            if result3.returncode == 0:
                result3_output = result3.stdout.strip()
            else:
                print(f"Error executing first fslstats command for {run}.")
                continue
            result3_output_values = result3_output.split()
            total_voxels_in_roi = float(result3_output_values[0])
            percentage_outside = (voxels_outside / total_voxels_in_roi) * 100
            percentage_outside = round(percentage_outside, 2)
            percentage_file = f"{p_id}/analysis/susceptibility/susc_scc/percentage_outside.txt"
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
            print(f"Percentage of ROI voxels in dropout regions saved in percentage_outside.txt file for {run}.")
    screenshot_file = f'{p_id}/analysis/susceptibility/susc_scc/ROI_on_run01_EPI.png'
    if not os.path.exists(screenshot_file):
        if __name__ == "__main__":
            for p_id in participants_to_iterate:
                process_participant(p_id, runs)

    # Step 3: Test quality of alternate distortion correction method (Stage 1).
    print("\n###### STEP 3: TESTING ALTERNATE DISTORTION CORRECTION METHOD (STAGE 1) ######")
    good_participants = ['P059', 'P100', 'P107', 'P122', 'P125', 'P127', 'P128', 'P136', 'P145', 'P155', 'P199', 'P215', 'P216']
    perc_outside_pa_values = []
    perc_outside_rl_values = []
    column_headers = ['p_id', 'perc_outside_pa', 'perc_outside_rl']
    group_perc_outside_df = pd.DataFrame(columns = column_headers) 
    for p_id in participants_to_iterate:
        if p_id in good_participants:
            print(f"Preparing Stage 1 files for {p_id}...")
            pa_fieldmaps = f"{p_id}/analysis/preproc/fieldmaps/pa_fieldmaps.nii"
            rl_fieldmaps = f"{p_id}/analysis/preproc/fieldmaps/rl_fieldmaps.nii"
            averaged_pa_fieldmaps = f"{p_id}/analysis/susceptibility/fnirt_test/1/averaged_pa_fieldmaps.nii.gz"
            averaged_rl_fieldmaps = f"{p_id}/analysis/susceptibility/fnirt_test/1/averaged_rl_fieldmaps.nii.gz"
            if not os.path.exists(averaged_pa_fieldmaps) or not os.path.exists(averaged_rl_fieldmaps):
                subprocess.run(['fslmaths', pa_fieldmaps, '-Tmean', averaged_pa_fieldmaps])
                subprocess.run(['fslmaths', rl_fieldmaps, '-Tmean', averaged_rl_fieldmaps])
            betted_pa_fieldmaps = f"{p_id}/analysis/susceptibility/fnirt_test/1/betted_pa_fieldmaps.nii.gz"
            betted_rl_fieldmaps = f"{p_id}/analysis/susceptibility/fnirt_test/1/betted_rl_fieldmaps.nii.gz"
            if not os.path.exists(betted_pa_fieldmaps) or not os.path.exists(betted_rl_fieldmaps):
                subprocess.run(["bet", averaged_pa_fieldmaps, betted_pa_fieldmaps, "-m", "-R"])
                subprocess.run(["bet", averaged_rl_fieldmaps, betted_rl_fieldmaps, "-m", "-R"])
            flirted_pa_fieldmaps = f"{p_id}/analysis/susceptibility/fnirt_test/1/flirted_pa_fieldmaps.nii.gz"
            flirted_rl_fieldmaps = f"{p_id}/analysis/susceptibility/fnirt_test/1/flirted_rl_fieldmaps.nii.gz"
            t1_flirted_pa_fieldmaps_transformation = f"{p_id}/analysis/susceptibility/fnirt_test/1/t1_flirted_pa_fieldmaps_transformation.mat"
            t1_flirted_rl_fieldmaps_transformation = f"{p_id}/analysis/susceptibility/fnirt_test/1/t1_flirted_rl_fieldmaps_transformation.mat"
            structural_brain = f"{p_id}/analysis/preproc/structural/structural_brain.nii.gz"
            if not os.path.exists(flirted_pa_fieldmaps):
                subprocess.run(["flirt", "-in", betted_pa_fieldmaps, "-ref", structural_brain, "-out", flirted_pa_fieldmaps, "-omat", t1_flirted_pa_fieldmaps_transformation])
                subprocess.run(["flirt", "-in", betted_rl_fieldmaps, "-ref", structural_brain, "-out", flirted_rl_fieldmaps, "-omat", t1_flirted_rl_fieldmaps_transformation])
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
                run = f"{p_id}/analysis/preproc/niftis/run01_nh.nii.gz"
                subprocess.run(['fslmaths', run, '-Tmean', averaged_run])
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
            result1 = subprocess.run(['fslstats', transformed_roi_mask, '-V'], capture_output=True, text=True)
            if result1.returncode == 0:
                result1_output = result1.stdout.strip()
            else:
                print("Error executing fslstats command.")
            result1_output_values = result1_output.split()
            total_voxels_in_roi = float(result1_output_values[0])
            perc_outside_pa = (pa_voxels_outside / total_voxels_in_roi) * 100
            perc_outside_pa = round(perc_outside_pa, 2)
            perc_outside_pa_values.append(perc_outside_pa)
            perc_outside_rl = (rl_voxels_outside / total_voxels_in_roi) * 100
            perc_outside_rl = round(perc_outside_rl, 2)
            perc_outside_rl_values.append(perc_outside_rl)
            perc_outside_df = pd.DataFrame({'p_id': [p_id], 'perc_outside_pa': [perc_outside_pa], 'perc_outside_rl': [perc_outside_rl]})
            perc_outside_df.to_csv(f'{p_id}/analysis/susceptibility/fnirt_test/1/perc_outside_df.txt', sep='\t', index=False)
            group_perc_outside_df = pd.concat([group_perc_outside_df, perc_outside_df], ignore_index=True)
            pa_trimmed_roi_mask = f"{p_id}/analysis/susceptibility/fnirt_test/1/pa_trimmed_roi_mask.nii.gz"
            rl_trimmed_roi_mask = f"{p_id}/analysis/susceptibility/fnirt_test/1/rl_trimmed_roi_mask.nii.gz"
            if not os.path.exists(pa_trimmed_roi_mask) or not os.path.exists(rl_trimmed_roi_mask):
                subprocess.run(['fslmaths', transformed_roi_mask, '-mul', flirted_pa_fieldmaps_bin, pa_trimmed_roi_mask])
                subprocess.run(['fslmaths', transformed_roi_mask, '-mul', flirted_rl_fieldmaps_bin, rl_trimmed_roi_mask])
    group_perc_outside_df.to_csv('group/susceptibility/fnirt_test/1/group_perc_outside_df.txt', sep='\t', index=False)
    plot_data = pd.DataFrame({
        'Participant': good_participants * 2,
        'Perc_Outside': perc_outside_pa_values + perc_outside_rl_values,
        'Sequence': ['PA'] * len(good_participants) + ['RL'] * len(good_participants)
    })
    perc_outside_plot = (
        ggplot(plot_data, aes(x='Participant', y='Perc_Outside', fill='Sequence')) +
        geom_bar(stat='identity', position='dodge') +
        theme_classic() +
        labs(title='Percentage of Voxels in Signal Dropout Regions', x='Participant', y='Percentage of SCC Voxels in Signal Dropout') +
        theme(axis_text_x=element_text(rotation=45, hjust=1), text=element_text(size=12, color='black'), axis_title=element_text(size=12, color='black')) +
        scale_y_continuous(expand=(0, 0))
    )
    perc_outside_plot.save('group/susceptibility/fnirt_test/1/perc_outside_plot.png')
    perc_outside_pa_overall = np.mean(perc_outside_pa_values)
    perc_outside_rl_overall = np.mean(perc_outside_rl_values)
    pa_std_error = np.std(perc_outside_pa_values) / np.sqrt(len(perc_outside_pa_values))
    rl_std_error = np.std(perc_outside_rl_values) / np.sqrt(len(perc_outside_rl_values))
    _, perc_outside_pa_overall_shap_p = stats.shapiro(perc_outside_pa_values)
    _, perc_outside_rl_overall_shap_p = stats.shapiro(perc_outside_rl_values)
    if perc_outside_pa_overall_shap_p > 0.05 and perc_outside_rl_overall_shap_p > 0.05:
        print(f'Shapiro-Wilk test passed for perc_outside values. Running parametric t-test...')
        _, p_value = stats.ttest_ind(perc_outside_pa_values, perc_outside_rl_values)
        print(f"T-test p-value: {p_value}")
    else:
        print(f'Shapiro-Wilk test failed for perc_outside values. Running non-parametric Mann-Whitney U test...')
        _, p_value = stats.mannwhitneyu(perc_outside_pa_values, perc_outside_rl_values)
        print(f"Mann-Whitney U test p-value: {p_value}")
    plot_data = pd.DataFrame({'Sequence': ['PA', 'RL'], 'Perc_Outside': [perc_outside_pa_overall, perc_outside_rl_overall], 'Std_Error': [pa_std_error, rl_std_error]})
    group_perc_outside_plot = (ggplot(plot_data, aes(x='Sequence', y='Perc_Outside', fill='Sequence')) + 
                        geom_bar(stat='identity', position='dodge') +
                        geom_errorbar(aes(ymin='Perc_Outside - Std_Error', ymax='Perc_Outside + Std_Error'), width=0.2, color='black') +
                        theme_classic() +
                        labs(title='Percentage of Voxels in Signal Dropout Regions', y='Percentage of SCC Voxels in Signal Dropout') +
                        scale_y_continuous(expand=(0, 0), limits=[0,10]) +
                        scale_fill_manual(values={'PA': '#DB5F57', 'RL': '#57D3DB'})
                        )
    if p_value < 0.001:
        group_perc_outside_plot = group_perc_outside_plot + annotate("text", x=1.5, y=max(plot_data['Perc_Outside']) + 3.5, label="***", size=16, color="black") + \
            annotate("segment", x=1, xend=2, y=max(plot_data['Perc_Outside']) + 3, yend=max(plot_data['Perc_Outside']) + 3, color="black")
    elif p_value < 0.01:
        group_perc_outside_plot = group_perc_outside_plot + annotate("text", x=1.5, y=max(plot_data['Perc_Outside']) + 3.5, label="**", size=16, color="black") + \
            annotate("segment", x=1, xend=2, y=max(plot_data['Perc_Outside']) + 3, yend=max(plot_data['Perc_Outside']) + 3, color="black")
    elif p_value < 0.05:
        group_perc_outside_plot = group_perc_outside_plot + annotate("text", x=1.5, y=max(plot_data['Perc_Outside']) + 3.5, label="*", size=16, color="black") + \
            annotate("segment", x=1, xend=2, y=max(plot_data['Perc_Outside']) + 3, yend=max(plot_data['Perc_Outside']) + 3, color="black")    
    group_perc_outside_plot.save('group/susceptibility/fnirt_test/1/group_perc_outside_plot.png')
    
    column_headers = ['p_id', 'ssim_index', 'voxels_in_bin_ssim_mask', 'perc_roi_voxels_in_bin_ssim_mask']
    group_ssim_df = pd.DataFrame(columns = column_headers) 
    for p_id in participants_to_iterate:
        if p_id in good_participants:
            print(f"Running Stage 1 SSIM analysis for {p_id}...")
            def calculate_ssim(image1_path, image2_path, ssim_output_path):
                """Function to calculate SSIM between two Nifti images and save the SSIM map."""
                image1_nii = nib.load(image1_path)
                image2_nii = nib.load(image2_path)
                image1 = image1_nii.get_fdata()
                image2 = image2_nii.get_fdata()
                if image1.shape != image2.shape:
                    raise ValueError("Input images must have the same dimensions for SSIM calculation.")
                ssim_index, ssim_map = ssim(image1, image2, full=True, data_range=image1.max() - image1.min())
                ssim_map_nifti = nib.Nifti1Image(ssim_map, affine=image1_nii.affine, header=image1_nii.header)
                nib.save(ssim_map_nifti, ssim_output_path)
                return ssim_index
            ssim_output_path = f"{p_id}/analysis/susceptibility/fnirt_test/1/ssim_map.nii.gz"
            flirted_pa_fieldmaps = f"{p_id}/analysis/susceptibility/fnirt_test/1/flirted_pa_fieldmaps.nii.gz"
            flirted_rl_fieldmaps = f"{p_id}/analysis/susceptibility/fnirt_test/1/flirted_rl_fieldmaps.nii.gz"
            if not os.path.exists(ssim_output_path):
                ssim_index = calculate_ssim(flirted_rl_fieldmaps, flirted_pa_fieldmaps, ssim_output_path)
            else:
                df = pd.read_csv(f'{p_id}/analysis/susceptibility/fnirt_test/1/ssim_df.txt', delimiter='\t')
                ssim_index_series = df.loc[df['p_id'] == p_id, 'ssim_index']
                ssim_index = ssim_index_series.iloc[0]
            ssim_bin = f"{p_id}/analysis/susceptibility/fnirt_test/1/ssim_bin.nii.gz"
            if not os.path.exists(ssim_bin):
                subprocess.run(["fslmaths", ssim_output_path, "-thr", "0.8", "-binv", ssim_bin])
            combined_pa_rl_mask = f"{p_id}/analysis/susceptibility/fnirt_test/1/combined_pa_rl_mask.nii.gz"
            flirted_pa_fieldmaps_bin = f'{p_id}/analysis/susceptibility/fnirt_test/1/flirted_pa_fieldmaps_bin.nii.gz'
            flirted_rl_fieldmaps_bin = f'{p_id}/analysis/susceptibility/fnirt_test/1/flirted_rl_fieldmaps_bin.nii.gz'
            if not os.path.exists(combined_pa_rl_mask):
                subprocess.run(['fslmaths', flirted_pa_fieldmaps_bin, '-add', flirted_rl_fieldmaps_bin, combined_pa_rl_mask])
            bin_pa_rl_mask = f"{p_id}/analysis/susceptibility/fnirt_test/1/bin_pa_rl_mask.nii.gz"
            if not os.path.exists(bin_pa_rl_mask):
                subprocess.run(['fslmaths', combined_pa_rl_mask, '-bin', bin_pa_rl_mask])
            ssim_bin_trimmed = f"{p_id}/analysis/susceptibility/fnirt_test/1/ssim_bin_trimmed.nii.gz"
            if not os.path.exists(ssim_bin_trimmed):
                subprocess.run(['fslmaths', ssim_bin, '-mul', bin_pa_rl_mask, ssim_bin_trimmed])
            voxels_in_whole_mask = subprocess.run(["fslstats", ssim_bin_trimmed, "-V"], capture_output=True, text=True).stdout.split()[0]
            voxels_in_whole_mask = float(voxels_in_whole_mask)
            intersection_mask_path = f'{p_id}/analysis/susceptibility/fnirt_test/1/ssim_roi_intersect.nii.gz'
            transformed_roi_mask = f'{p_id}/analysis/susceptibility/fnirt_test/1/transformed_roi_mask.nii.gz'
            if not os.path.exists(intersection_mask_path):
                subprocess.run(["fslmaths", ssim_bin_trimmed, "-mas", transformed_roi_mask, intersection_mask_path])
            voxels_in_roi_in_mask = subprocess.run(["fslstats", intersection_mask_path, "-V"], capture_output=True, text=True).stdout.split()[0]
            voxels_in_roi_in_mask = float(voxels_in_roi_in_mask)
            perc_roi_voxels_in_mask = (voxels_in_roi_in_mask / total_voxels_in_roi) * 100
            ssim_df = pd.DataFrame({'p_id': [p_id], 'ssim_index': [ssim_index], 'voxels_in_bin_ssim_mask': [voxels_in_whole_mask], 'perc_roi_voxels_in_bin_ssim_mask': [perc_roi_voxels_in_mask]})
            ssim_df.to_csv(f'{p_id}/analysis/susceptibility/fnirt_test/1/ssim_df.txt', sep='\t', index=False)
            group_ssim_df = pd.concat([group_ssim_df, ssim_df], ignore_index=True)
    group_ssim_df.to_csv('group/susceptibility/fnirt_test/1/group_ssim_df.txt', sep='\t', index=False)
    ssim_indexes = group_ssim_df['ssim_index'].tolist()
    ssim_mean = np.mean(ssim_indexes)
    print(f"Mean SSIM index for Stage 1: {ssim_mean}")
    plot_data = pd.DataFrame({
        'Participant': good_participants,
        'SSIM': ssim_indexes,
    })
    ssim_index_plot = (
        ggplot(plot_data, aes(x='Participant', y='SSIM')) +
        geom_bar(stat='identity', position='dodge') +
        geom_hline(yintercept=ssim_mean, linetype='dashed', color='red') +
        theme_classic() +
        labs(title='SSIM Indexes', x='Participant', y='SSIM') +
        theme(axis_text_x=element_text(rotation=45, hjust=1), text=element_text(size=12, color='blue'), axis_title=element_text(size=12, face='bold')) +
        scale_y_continuous(expand=(0, 0), limits=[0.8,1])
    )
    ssim_index_plot.save('group/susceptibility/fnirt_test/1/ssim_index_plot.png')
    voxels = group_ssim_df['voxels_in_bin_ssim_mask'].tolist()
    voxels_mean = np.mean(voxels)
    plot_data = pd.DataFrame({
        'Participant': good_participants,
        'Voxels': voxels,
    })
    ssim_voxels_plot = (
        ggplot(plot_data, aes(x='Participant', y='Voxels')) +
        geom_bar(stat='identity', position='dodge') +
        geom_hline(yintercept=voxels_mean, linetype='dashed', color='red') +
        theme_classic() +
        labs(title='Number of Voxels in SSIM Mask', x='Participant', y='Voxels') +
        theme(axis_text_x=element_text(rotation=45, hjust=1), text=element_text(size=12, color='blue'), axis_title=element_text(size=12, face='bold')) +
        scale_y_continuous(expand=(0, 0))
    )
    ssim_voxels_plot.save('group/susceptibility/fnirt_test/1/ssim_voxels_plot.png')
    perc_voxels = group_ssim_df['perc_roi_voxels_in_bin_ssim_mask'].tolist()
    perc_voxels_mean = np.mean(perc_voxels)
    plot_data = pd.DataFrame({
        'Participant': good_participants,
        'Perc_Voxels': perc_voxels,
    })
    ssim_perc_voxels_plot = (
        ggplot(plot_data, aes(x='Participant', y='Perc_Voxels')) +
        geom_bar(stat='identity', position='dodge') +
        geom_hline(yintercept=perc_voxels_mean, linetype='dashed', color='red') +
        theme_classic() +
        labs(title='Percentage of ROI Voxels in SSIM Mask', x='Participant', y='Percentage of SCC Voxels in SSIM Mask') +
        theme(axis_text_x=element_text(rotation=45, hjust=1), text=element_text(size=12, color='black'), axis_title=element_text(size=12)) +
        scale_y_continuous(expand=(0, 0))
    )
    ssim_perc_voxels_plot.save('group/susceptibility/fnirt_test/1/ssim_perc_voxels_plot.png')

    overlap_perc_av_values = []
    column_headers = ['p_id', 'tissue_type', 'overlap_perc']
    group_overlap_perc_df = pd.DataFrame(columns = column_headers) 
    for p_id in participants_to_iterate:
        if p_id in good_participants:
            print(f'Running Stage 1 segmentation analysis for {p_id}...')
            pa_csf_pve_seg = f"{p_id}/analysis/susceptibility/fnirt_test/1/pa_seg_pve_0.nii.gz"
            pa_wm_pve_seg = f"{p_id}/analysis/susceptibility/fnirt_test/1/pa_seg_pve_1.nii.gz"
            pa_gm_pve_seg = f"{p_id}/analysis/susceptibility/fnirt_test/1/pa_seg_pve_2.nii.gz"
            rl_csf_pve_seg = f"{p_id}/analysis/susceptibility/fnirt_test/1/rl_seg_pve_0.nii.gz"
            rl_wm_pve_seg = f"{p_id}/analysis/susceptibility/fnirt_test/1/rl_seg_pve_1.nii.gz"
            rl_gm_pve_seg = f"{p_id}/analysis/susceptibility/fnirt_test/1/rl_seg_pve_2.nii.gz"
            if not os.path.exists(pa_csf_pve_seg):
                pa_seg = f"{p_id}/analysis/susceptibility/fnirt_test/1/pa_seg"
                rl_seg = f"{p_id}/analysis/susceptibility/fnirt_test/1/rl_seg"
                flirted_pa_fieldmaps = f"{p_id}/analysis/susceptibility/fnirt_test/1/flirted_pa_fieldmaps.nii.gz"
                flirted_rl_fieldmaps = f"{p_id}/analysis/susceptibility/fnirt_test/1/flirted_rl_fieldmaps.nii.gz"
                structural_brain = f"{p_id}/analysis/preproc/structural/structural_brain.nii.gz"
                subprocess.run(["fast", "-n", "3", "-o", pa_seg, structural_brain, flirted_pa_fieldmaps])
                subprocess.run(["fast", "-n", "3", "-o", rl_seg, structural_brain, flirted_rl_fieldmaps])
            pa_csf_pve_seg_bin = f"{p_id}/analysis/susceptibility/fnirt_test/1/pa_csf_pve_seg_bin.nii.gz"
            pa_wm_pve_seg_bin = f"{p_id}/analysis/susceptibility/fnirt_test/1/pa_wm_pve_seg_bin.nii.gz"
            pa_gm_pve_seg_bin = f"{p_id}/analysis/susceptibility/fnirt_test/1/pa_gm_pve_seg_bin.nii.gz"
            if not os.path.exists(pa_csf_pve_seg_bin):
                subprocess.run(['fslmaths', pa_csf_pve_seg, '-thr', '0.5', '-bin', pa_csf_pve_seg_bin])
                subprocess.run(['fslmaths', pa_wm_pve_seg, '-thr', '0.5', '-bin', pa_wm_pve_seg_bin])
                subprocess.run(['fslmaths', pa_gm_pve_seg, '-thr', '0.5', '-bin', pa_gm_pve_seg_bin])
            rl_csf_pve_seg_bin = f"{p_id}/analysis/susceptibility/fnirt_test/1/rl_csf_pve_seg_bin.nii.gz"
            rl_wm_pve_seg_bin = f"{p_id}/analysis/susceptibility/fnirt_test/1/rl_wm_pve_seg_bin.nii.gz"
            rl_gm_pve_seg_bin = f"{p_id}/analysis/susceptibility/fnirt_test/1/rl_gm_pve_seg_bin.nii.gz"
            if not os.path.exists(rl_csf_pve_seg_bin):
                subprocess.run(['fslmaths', rl_csf_pve_seg, '-thr', '0.5', '-bin', rl_csf_pve_seg_bin])
                subprocess.run(['fslmaths', rl_wm_pve_seg, '-thr', '0.5', '-bin', rl_wm_pve_seg_bin])
                subprocess.run(['fslmaths', rl_gm_pve_seg, '-thr', '0.5', '-bin', rl_gm_pve_seg_bin])
            csf_intersect_mask = f"{p_id}/analysis/susceptibility/fnirt_test/1/csf_intersect_mask.nii.gz"
            wm_intersect_mask = f"{p_id}/analysis/susceptibility/fnirt_test/1/wm_intersect_mask.nii.gz"
            gm_intersect_mask = f"{p_id}/analysis/susceptibility/fnirt_test/1/gm_intersect_mask.nii.gz"
            if not os.path.exists(csf_intersect_mask):
                subprocess.run(['fslmaths', pa_csf_pve_seg_bin, '-mul', rl_csf_pve_seg_bin, '-bin', csf_intersect_mask])
                subprocess.run(['fslmaths', pa_wm_pve_seg_bin, '-mul', rl_wm_pve_seg_bin, '-bin', wm_intersect_mask])
                subprocess.run(['fslmaths', pa_gm_pve_seg_bin, '-mul', rl_gm_pve_seg_bin, '-bin', gm_intersect_mask])
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
            if p_id == 'P122' or p_id == 'P136':
                values = np.array([wm_overlap_perc, gm_overlap_perc])
                overlap_perc_av = np.mean(values)
                overlap_perc_av_values.append(overlap_perc_av)
            overlap_perc_df = pd.DataFrame({'p_id': participant_col, 'tissue_type': tissue_type_col, 'overlap_perc': overlap_perc_col})
            overlap_perc_df.to_csv(f"{p_id}/analysis/susceptibility/fnirt_test/1/overlap_perc_df.txt", sep='\t', index=False)
            group_overlap_perc_df = pd.concat([group_overlap_perc_df, overlap_perc_df], ignore_index=True)
    group_overlap_perc_df.to_csv('group/susceptibility/fnirt_test/1/group_overlap_perc_df.txt', sep='\t', index=False)
    csf_values = []
    wm_values = []
    gm_values = []
    for p_id in participants_to_iterate:
        if p_id in good_participants:
            filtered_csf = group_overlap_perc_df.loc[(group_overlap_perc_df['tissue_type'] == 'csf') & (group_overlap_perc_df['p_id'] == p_id), 'overlap_perc'].values[0]
            filtered_csf = float(filtered_csf)
            csf_values.append(filtered_csf)
            filtered_wm = group_overlap_perc_df.loc[(group_overlap_perc_df['tissue_type'] == 'wm') & (group_overlap_perc_df['p_id'] == p_id), 'overlap_perc'].values[0]
            filtered_wm = float(filtered_wm)
            wm_values.append(filtered_wm)
            filtered_gm = group_overlap_perc_df.loc[(group_overlap_perc_df['tissue_type'] == 'gm') & (group_overlap_perc_df['p_id'] == p_id), 'overlap_perc'].values[0]
            filtered_gm = float(filtered_gm)
            gm_values.append(filtered_gm)
    plot_data = pd.DataFrame({
        'Participant': good_participants * 3,
        'Overlap_Perc': csf_values + wm_values + gm_values,
        'Tissue_Type': ['CSF'] * len(good_participants) + ['WM'] * len(good_participants) + ['GM'] * len(good_participants)
    })
    overlap_perc_plot = (
        ggplot(plot_data, aes(x='Participant', y='Overlap_Perc', fill='Tissue_Type')) +
        geom_bar(stat='identity', position='dodge') +
        theme_classic() +
        labs(title='Sequence Tissue Type Overlap', x='Participant', y='Tissue Overlap Percentage', fill='Tissue Type') +
        theme(axis_text_x=element_text(rotation=45, hjust=1, color='black'), text=element_text(size=12, color='black'), axis_title=element_text(size=12, color='black')) +
        scale_y_continuous(expand=(0, 0), limits=[0,100]) +
        scale_fill_manual(values={'CSF': '#F9DC5C', 'WM': '#db5f57', 'GM': '#57d3db'})
    )
    overlap_perc_plot.save('group/susceptibility/fnirt_test/1/overlap_perc_plot.png')
    filtered_csf = group_overlap_perc_df[group_overlap_perc_df['tissue_type'] == 'csf']['overlap_perc'].tolist()
    mean_csf = np.mean(filtered_csf)
    filtered_wm = group_overlap_perc_df[group_overlap_perc_df['tissue_type'] == 'wm']['overlap_perc'].tolist()
    mean_wm = np.mean(filtered_wm)
    filtered_gm = group_overlap_perc_df[group_overlap_perc_df['tissue_type'] == 'gm']['overlap_perc'].tolist()
    mean_gm = np.mean(filtered_gm)
    csf_std_error = np.std(filtered_csf) / np.sqrt(len(filtered_csf))
    wm_std_error = np.std(filtered_wm) / np.sqrt(len(filtered_wm))
    gm_std_error = np.std(filtered_gm) / np.sqrt(len(filtered_gm))
    group_overlap_perc_df['p_id'] = group_overlap_perc_df['p_id'].astype(str)
    group_overlap_perc_df['tissue_type'] = group_overlap_perc_df['tissue_type'].astype(str)
    group_overlap_perc_df['overlap_perc'] = pd.to_numeric(group_overlap_perc_df['overlap_perc'], errors='coerce')
    sphericity_test = rm_anova(data=group_overlap_perc_df, dv='overlap_perc', within='tissue_type', subject='p_id')
    epsilon_value = sphericity_test.loc[sphericity_test['Source'] == 'tissue_type', 'eps'].values[0]
    print(f'Stage 1 segmentation analysis sphericity test epsilon value: {epsilon_value}')
    normality_passed = True
    shapiro_results = group_overlap_perc_df.groupby('tissue_type')['overlap_perc'].apply(stats.shapiro)
    shapiro_p_values = shapiro_results.apply(lambda x: x.pvalue)
    if any(shapiro_p_values < 0.05):
        normality_passed = False
    print(f'Stage 1 segmentation analysis Shapiro-Wilk test of normality passed: {normality_passed}')
    _, p_value_levene = stats.levene(
        group_overlap_perc_df[group_overlap_perc_df['tissue_type'] == 'csf']['overlap_perc'],
        group_overlap_perc_df[group_overlap_perc_df['tissue_type'] == 'wm']['overlap_perc'],
        group_overlap_perc_df[group_overlap_perc_df['tissue_type'] == 'gm']['overlap_perc']
    )
    print(f'Stage 1 segmentation analysis Levene test p-value: {p_value_levene}')
    if normality_passed and p_value_levene > 0.05 and epsilon_value > 0.75:
        print('Stage 1 segmentation analysis parametric assumptions met. Proceeding with two-way ANOVA...')
        anova_result = rm_anova(data=group_overlap_perc_df, dv='overlap_perc', within='tissue_type', subject='p_id')
        print(anova_result)
    else:
        print('Stage 1 segmentation analysis parametric assumptions not met. Two-way ANOVA not run.')
    plot_data = pd.DataFrame({'Tissue_Type': ['CSF', 'WM', 'GM'], 'Overlap_Perc': [mean_csf, mean_wm, mean_gm], 'Std_Error': [csf_std_error, wm_std_error, gm_std_error]})
    group_overlap_perc_plot = (ggplot(plot_data, aes(x='Tissue_Type', y='Overlap_Perc', fill='Tissue_Type')) + 
                        geom_bar(stat='identity', position='dodge') +
                        geom_errorbar(aes(ymin='Overlap_Perc - Std_Error', ymax='Overlap_Perc + Std_Error'), width=0.2, color='black') +
                        theme_classic() +
                        labs(title='Sequence Tissue Type Overlap', x='Tissue Type', y='Tissue Overlap Percentage') +
                        scale_y_continuous(expand=(0, 0), limits=[0,100]) +
                        scale_fill_manual(values={'CSF': '#F9DC5C', 'WM': '#db5f57', 'GM': '#57d3db'})
                        )
    group_overlap_perc_plot.save('group/susceptibility/fnirt_test/1/group_overlap_perc_plot.png')
    ssim_values = group_ssim_df.loc[group_ssim_df['p_id'].isin(['P122', 'P136']), 'ssim_index'].tolist()
    plot_data = pd.DataFrame({
        'Participant': ['P122', 'P136'],
        'SSIM': ssim_values,
        'Overlap_Perc': overlap_perc_av_values
    })
    plot_data_sorted = plot_data.sort_values(by='Overlap_Perc', ascending=False)
    index_sorted = np.arange(len(plot_data_sorted))
    fig, ax1 = plt.subplots()
    bar_width = 0.35
    bar1 = ax1.bar(index_sorted, plot_data_sorted['SSIM'], bar_width, label='SSIM', color='#db5f57')
    ax1.set_ylabel('SSIM Index', color='#db5f57')
    ax1.tick_params(axis='y', labelcolor='#db5f57')
    ax1.set_ylim(0.94, 0.98)
    ax2 = ax1.twinx()
    bar2 = ax2.bar(index_sorted + bar_width, plot_data_sorted['Overlap_Perc'], bar_width, label='Overlap_Perc', color='#57d3db', alpha=1)
    ax2.set_ylabel(' Tissue Overlap Percentage', color='#57d3db')
    ax2.tick_params(axis='y', labelcolor='#57d3db')
    ax2.set_ylim(75, 95)
    ax1.set_xlabel('Participant')
    ax1.set_xticks(index_sorted + bar_width / 2)
    ax1.set_xticklabels(plot_data_sorted['Participant'], rotation=45, ha='right')
    plt.title('SSIM and Tissue Overlap Percentage Plot')
    fig.legend(loc='upper right', bbox_to_anchor=(1, 1), bbox_transform=ax1.transAxes)
    save_path = 'group/susceptibility/fnirt_test/1/ssim_overlap_perc_plot.png'
    plt.tight_layout()
    plt.savefig(save_path, bbox_inches='tight')

    column_headers = ['p_id', 'sequence', 'value']
    group_voxel_intensity_df = pd.DataFrame(columns = column_headers)   
    for p_id in participants_to_iterate:
        if p_id in good_participants:
            print(f'Running Stage 1 voxel signal intensity analysis for {p_id}...')
            def extract_voxel_intensities(epi_image_path, mask_image_path):
                epi_img = nib.load(epi_image_path)
                epi_data = epi_img.get_fdata()
                mask_img = nib.load(mask_image_path)
                mask_data = mask_img.get_fdata()
                mask_data = mask_data > 0
                roi_voxel_intensities = epi_data[mask_data]
                voxel_intensity_list = roi_voxel_intensities.tolist()
                return voxel_intensity_list
            flirted_pa_fieldmaps = f"{p_id}/analysis/susceptibility/fnirt_test/1/flirted_pa_fieldmaps.nii.gz"
            flirted_rl_fieldmaps = f"{p_id}/analysis/susceptibility/fnirt_test/1/flirted_rl_fieldmaps.nii.gz"
            pa_trimmed_roi_mask = f"{p_id}/analysis/susceptibility/fnirt_test/1/pa_trimmed_roi_mask.nii.gz"
            rl_trimmed_roi_mask = f"{p_id}/analysis/susceptibility/fnirt_test/1/rl_trimmed_roi_mask.nii.gz"
            pa_voxel_intensities = extract_voxel_intensities(flirted_pa_fieldmaps, pa_trimmed_roi_mask)
            rl_voxel_intensities = extract_voxel_intensities(flirted_rl_fieldmaps, rl_trimmed_roi_mask)
            values = pa_voxel_intensities + rl_voxel_intensities
            sequence = ['pa'] * len(pa_voxel_intensities) + ['rl'] * len(rl_voxel_intensities)
            subject = [f'{p_id}'] * len(pa_voxel_intensities) + [f'{p_id}'] * len(rl_voxel_intensities)
            voxel_intensity_df = pd.DataFrame({'p_id': subject, 'sequence': sequence, 'value': values})
            voxel_intensity_df.to_csv(f'{p_id}/analysis/susceptibility/fnirt_test/1/voxel_intensity_df.txt', sep='\t', index=False)
            group_voxel_intensity_df = pd.concat([group_voxel_intensity_df, voxel_intensity_df], ignore_index=True)
    group_voxel_intensity_df.to_csv('group/susceptibility/fnirt_test/1/group_voxel_intensity_df.txt', sep='\t', index=False)
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
            anderson_rl = stats.anderson(filtered_rl['value'])
            significance_level = 0.05
            is_pa_normal = anderson_pa.statistic < anderson_pa.critical_values[
                anderson_pa.significance_level.tolist().index(significance_level * 100)]
            is_rl_normal = anderson_rl.statistic < anderson_rl.critical_values[
                anderson_rl.significance_level.tolist().index(significance_level * 100)]
            if is_pa_normal and is_rl_normal:
                print(f'Anderson-Darling test passed for {p_id} voxel intensity values. Running parametric t-test...')
                _, p_value = stats.ttest_ind(filtered_pa['value'], filtered_rl['value'], equal_var=False)
                p_values.append(p_value)
            else:
                print(f'Anderson-Darling test failed for {p_id} voxel intensity values. Running non-parametric Mann Whitney U test...')
                _, p_value = stats.mannwhitneyu(filtered_pa['value'], filtered_rl['value'], alternative='two-sided')
                p_values.append(p_value)
            pa_std_error = np.std(filtered_pa['value']) / np.sqrt(len(filtered_pa['value']))
            pa_std_errors.append(pa_std_error)
            rl_std_error = np.std(filtered_rl['value']) / np.sqrt(len(filtered_rl['value']))
            rl_std_errors.append(rl_std_error)
    plot_data = pd.DataFrame({
        'Participant': good_participants * 2,
        'Mean_Value': pa_means + rl_means,
        'Sequence': ['PA'] * len(good_participants) + ['RL'] * len(good_participants),
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
    voxel_intensity_plot = (
        ggplot(plot_data, aes(x='Participant', y='Mean_Value', fill='Sequence')) +
        geom_bar(stat='identity', position='dodge') +
        geom_errorbar(aes(ymin='Mean_Value - Std_Error', ymax='Mean_Value + Std_Error'), position=position_dodge(width=0.9), width=0.2, color='black') +
        theme_classic() +
        labs(title='Mean SCC Voxel Intensity', x='Participant', y='Mean SCC Signal Intensity') +
        theme(axis_text_x=element_text(rotation=45, hjust=1), text=element_text(size=12, color='black'), axis_title=element_text(size=12)) +
        scale_y_continuous(expand=(0, 0), limits=[0,350]) +
        geom_text(
            aes(x='Participant', y='Mean_Value', label='Significance'),
            position=position_dodge(width=0.9),
            color='black',
            size=12,
            ha='center',
            va='bottom',
            show_legend=False))
    voxel_intensity_plot.save('group/susceptibility/fnirt_test/1/voxel_intensity_plot.png')
    pa_means_overall = np.mean(pa_means)
    rl_means_overall = np.mean(rl_means)
    pa_std_error_overall = np.std(pa_means) / np.sqrt(len(pa_means))
    rl_std_error_overall = np.std(rl_means) / np.sqrt(len(rl_means))
    _, pa_means_overall_shap_p = stats.shapiro(pa_means)
    _, rl_means_overall_shap_p = stats.shapiro(rl_means)
    if pa_means_overall_shap_p > 0.05 and rl_means_overall_shap_p > 0.05:
        print(f'Shapiro-Wilk test passed for voxel intensity values. Running parametric t-test...')
        _, p_value = stats.ttest_rel(pa_means, rl_means)
        print(f"T-test p-value: {p_value}")
    else:
        print(f'Shapiro-Wilk test failed for voxel intensity values. Running non-parametric Wilcoxon test...')
        _, p_value = stats.wilcoxon(pa_means, rl_means)
        print(f"Wilcoxon test p-value: {p_value}")
    plot_data = pd.DataFrame({'p_id': good_participants, 'pa_values': pa_means, 'rl_values': rl_means})
    data_long = pd.melt(plot_data, id_vars=['p_id'], value_vars=['pa_values', 'rl_values'], var_name='sequence', value_name='value')
    data_long['sequence'] = data_long['sequence'].map({'pa_values': 'PA', 'rl_values': 'RL'})
    group_voxel_intensity_ladder_plot = (
        ggplot(data_long, aes(x='sequence', y='value', group='p_id')) +
        geom_line(aes(group='p_id'), color='gray', size=1) +
        geom_point(aes(color='sequence'), size=4) +
        theme_light() +
        theme(
            panel_grid_major=element_blank(), 
            panel_grid_minor=element_blank(), 
            panel_border=element_blank(),
            axis_line_x=element_line(color='black'),  
            axis_line_y=element_line(color='black'),  
        ) +
        labs(title='Ladder Plot of PA and RL Sequences',
            x='Sequence',
            y='Mean SCC Signal Intensity') +
        scale_x_discrete(limits=['PA', 'RL']) +
        scale_y_continuous()
    )
    group_voxel_intensity_ladder_plot.save('group/susceptibility/fnirt_test/1/group_voxel_intensity_ladder_plot.png')                          
    plot_data = pd.DataFrame({'Sequence': ['PA', 'RL'], 'Mean': [pa_means_overall, rl_means_overall], 'Std_Error': [pa_std_error_overall, rl_std_error_overall]})
    group_voxel_intensity_plot = (ggplot(plot_data, aes(x='Sequence', y='Mean', fill='Sequence')) + 
                        geom_bar(stat='identity', position='dodge') +
                        geom_errorbar(aes(ymin='Mean - Std_Error', ymax='Mean + Std_Error'), width=0.2, color='black') +
                        theme_classic() +
                        labs(title='Mean of Voxel Intensities Across Participants', y='Mean SCC Signal Intensity') +
                        scale_y_continuous(expand=(0, 0), limits=[0,350]) +
                        scale_fill_manual(values={'PA': '#DB5F57', 'RL': '#57D3DB'})
                        )
    if p_value < 0.001:
        group_voxel_intensity_plot = group_voxel_intensity_plot + annotate("text", x=1.5, y=max(plot_data['Mean']) + 40, label="***", size=16, color="black") + \
            annotate("segment", x=1, xend=2, y=max(plot_data['Mean']) +30, yend=max(plot_data['Mean']) + 30, color="black")
    elif p_value < 0.01:
        group_voxel_intensity_plot = group_voxel_intensity_plot + annotate("text", x=1.5, y=max(plot_data['Mean']) + 40, label="**", size=16, color="black") + \
            annotate("segment", x=1, xend=2, y=max(plot_data['Mean']) +30, yend=max(plot_data['Mean']) + 30, color="black")
    elif p_value < 0.05:
        group_voxel_intensity_plot = group_voxel_intensity_plot + annotate("text", x=1.5, y=max(plot_data['Mean']) + 40, label="*", size=16, color="black") + \
            annotate("segment", x=1, xend=2, y=max(plot_data['Mean']) +30, yend=max(plot_data['Mean']) + 30, color="black")    
    group_voxel_intensity_plot.save('group/susceptibility/fnirt_test/1/group_voxel_intensity_plot.png')

    # Step 4: Test quality of alternate distortion correction method (Stage 2).
    print("\n###### STEP 4: TESTING ALTERNATE DISTORTION CORRECTION METHOD (STAGE 2) ######")
    perc_outside_corrected_values = []
    perc_outside_uncorrected_values = []
    column_headers = ['p_id', 'perc_outside_corrected', 'perc_outside_uncorrected']
    group_perc_outside_df = pd.DataFrame(columns = column_headers) 
    for p_id in participants_to_iterate:
        if p_id in good_participants:  
            print(f'Preparing Stage 2 files for {p_id}...')          
            averaged_run = f"{p_id}/analysis/susceptibility/fnirt_test/2/averaged_run.nii.gz"
            if not os.path.exists(averaged_run):
                run = f"{p_id}/analysis/preproc/niftis/run01_nh.nii.gz"
                subprocess.run(['fslmaths', run, '-Tmean', averaged_run])
            uncorrected_run = f"{p_id}/analysis/susceptibility/fnirt_test/2/uncorrected_run.nii.gz"
            if not os.path.exists(uncorrected_run):
                subprocess.run(["bet", averaged_run, uncorrected_run, "-m", "-R"])
            corrected_run = os.path.join(os.getcwd(), p_id, "analysis", "susceptibility", "fnirt_test", "2", "corrected_run.nii.gz")
            if not os.path.exists(corrected_run):
                subprocess.run(["applytopup", f"--imain={uncorrected_run}", f"--datain={p_id}/analysis/preproc/fieldmaps/acqparams.txt", "--inindex=6", f"--topup={p_id}/analysis/preproc/fieldmaps/topup_{p_id}", "--method=jac", f"--out={corrected_run}"])
            flirted_corrected_run = f"{p_id}/analysis/susceptibility/fnirt_test/2/flirted_corrected_run.nii.gz"
            flirted_uncorrected_run = f"{p_id}/analysis/susceptibility/fnirt_test/2/flirted_uncorrected_run.nii.gz"
            flirted_corrected_run_transformation = f"{p_id}/analysis/susceptibility/fnirt_test/2/flirted_corrected_run_transformation.mat"
            flirted_uncorrected_run_transformation = f"{p_id}/analysis/susceptibility/fnirt_test/2/flirted_uncorrected_run_transformation.mat"
            if not os.path.exists(flirted_corrected_run):
                structural_brain = f"{p_id}/analysis/preproc/structural/structural_brain.nii.gz"
                subprocess.run(["flirt", "-in", corrected_run, "-ref", structural_brain, "-out", flirted_corrected_run, "-omat", flirted_corrected_run_transformation])
                subprocess.run(["flirt", "-in", uncorrected_run, "-ref", structural_brain, "-out", flirted_uncorrected_run, "-omat", flirted_uncorrected_run_transformation])
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
            subprocess.run(['flirt', '-in', roi_mask, '-ref', structural_brain, '-applyxfm', '-init', flirted_uncorrected_run_transformation, '-out', transformed_roi_mask, '-interp', 'nearestneighbour'])
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
            result1 = subprocess.run(['fslstats', transformed_roi_mask, '-V'], capture_output=True, text=True)
            if result1.returncode == 0:
                result1_output = result1.stdout.strip()
            else:
                print("Error executing fslstats command.")
            result1_output_values = result1_output.split()
            total_voxels_in_roi = float(result1_output_values[0])
            perc_outside_corrected = (corrected_voxels_outside / total_voxels_in_roi) * 100
            perc_outside_corrected = round(perc_outside_corrected, 2)
            perc_outside_corrected_values.append(perc_outside_corrected)
            perc_outside_uncorrected = (uncorrected_voxels_outside / total_voxels_in_roi) * 100
            perc_outside_uncorrected = round(perc_outside_uncorrected, 2)
            perc_outside_uncorrected_values.append(perc_outside_uncorrected)
            perc_outside_df = pd.DataFrame({'p_id': [p_id], 'perc_outside_corrected': [perc_outside_corrected], 'perc_outside_uncorrected': [perc_outside_uncorrected]})
            perc_outside_df.to_csv(f'{p_id}/analysis/susceptibility/fnirt_test/2/perc_outside_df.txt', sep='\t', index=False)
            group_perc_outside_df = pd.concat([group_perc_outside_df, perc_outside_df], ignore_index=True)
            corrected_trimmed_roi_mask = f"{p_id}/analysis/susceptibility/fnirt_test/2/corrected_trimmed_roi_mask.nii.gz"
            uncorrected_trimmed_roi_mask = f"{p_id}/analysis/susceptibility/fnirt_test/2/uncorrected_trimmed_roi_mask.nii.gz"
            if not os.path.exists(corrected_trimmed_roi_mask) or not os.path.exists(uncorrected_trimmed_roi_mask):
                subprocess.run(['fslmaths', transformed_roi_mask, '-mul', flirted_corrected_bin, corrected_trimmed_roi_mask])
                subprocess.run(['fslmaths', transformed_roi_mask, '-mul', flirted_uncorrected_bin, uncorrected_trimmed_roi_mask])
    group_perc_outside_df.to_csv('group/susceptibility/fnirt_test/2/group_perc_outside_df.txt', sep='\t', index=False)
    plot_data = pd.DataFrame({
        'Participant': good_participants * 2,
        'Perc_Outside': perc_outside_corrected_values + perc_outside_uncorrected_values,
        'Sequence': ['corrected'] * len(good_participants) + ['uncorrected'] * len(good_participants)
    })
    perc_outside_plot = (
        ggplot(plot_data, aes(x='Participant', y='Perc_Outside', fill='Sequence')) +
        geom_bar(stat='identity', position='dodge') +
        theme_classic() +
        labs(title='Percentage of Voxels in Signal Dropout Regions', x='Participant', y='Percentage of SCC Voxels in Signal Dropout') +
        theme(axis_text_x=element_text(rotation=45, hjust=1), text=element_text(size=12, color='black'), axis_title=element_text(size=12)) +
        scale_y_continuous(expand=(0, 0))
    )
    perc_outside_plot.save('group/susceptibility/fnirt_test/2/perc_outside_plot.png')
    perc_outside_corrected_overall = np.mean(perc_outside_corrected_values)
    perc_outside_uncorrected_overall = np.mean(perc_outside_uncorrected_values)
    corrected_std_error = np.std(perc_outside_corrected_values) / np.sqrt(len(perc_outside_corrected_values))
    uncorrected_std_error = np.std(perc_outside_uncorrected_values) / np.sqrt(len(perc_outside_uncorrected_values))
    _, perc_outside_corrected_overall_shap_p = stats.shapiro(perc_outside_corrected_values)
    _, perc_outside_uncorrected_overall_shap_p = stats.shapiro(perc_outside_uncorrected_values)
    if perc_outside_corrected_overall_shap_p > 0.05 and perc_outside_uncorrected_overall_shap_p > 0.05:
        print(f'Shapiro-Wilk test passed for perc_outside values. Running parametric t-test...')
        _, p_value = stats.ttest_ind(perc_outside_corrected_values, perc_outside_uncorrected_values)
        print(f"T-test p-value: {p_value}")
    else:
        print(f'Shapiro-Wilk test failed for perc_outside values. Running non-parametric Mann-Whitney U test...')
        _, p_value = stats.mannwhitneyu(perc_outside_corrected_values, perc_outside_uncorrected_values)
        print(f"Mann-Whitney U test p-value: {p_value}")
    plot_data = pd.DataFrame({'Sequence': ['corrected', 'uncorrected'], 'Perc_Outside': [perc_outside_corrected_overall, perc_outside_uncorrected_overall], 'Std_Error': [corrected_std_error, uncorrected_std_error]})
    group_perc_outside_plot = (ggplot(plot_data, aes(x='Sequence', y='Perc_Outside', fill='Sequence')) + 
                        geom_bar(stat='identity', position='dodge') +
                        geom_errorbar(aes(ymin='Perc_Outside - Std_Error', ymax='Perc_Outside + Std_Error'), width=0.2, color='black') +
                        theme_classic() +
                        labs(title='Percentage of Voxels in Signal Dropout Regions', y='Percentage of SCC Voxels in Signal Dropout') +
                        scale_y_continuous(expand=(0, 0)) +
                        scale_fill_manual(values={'PA': '#DB5F57', 'RL': '#57D3DB'})
                        )
    if p_value < 0.001:
        group_perc_outside_plot = group_perc_outside_plot + annotate("text", x=1.5, y=max(plot_data['Perc_Outside']) + 3.5, label="***", size=16, color="black") + \
            annotate("segment", x=1, xend=2, y=max(plot_data['Perc_Outside']) + 3, yend=max(plot_data['Perc_Outside']) + 3, color="black")
    elif p_value < 0.01:
        group_perc_outside_plot = group_perc_outside_plot + annotate("text", x=1.5, y=max(plot_data['Perc_Outside']) + 3.5, label="**", size=16, color="black") + \
            annotate("segment", x=1, xend=2, y=max(plot_data['Perc_Outside']) + 3, yend=max(plot_data['Perc_Outside']) + 3, color="black")
    elif p_value < 0.05:
        group_perc_outside_plot = group_perc_outside_plot + annotate("text", x=1.5, y=max(plot_data['Perc_Outside']) + 3.5, label="*", size=16, color="black") + \
            annotate("segment", x=1, xend=2, y=max(plot_data['Perc_Outside']) + 3, yend=max(plot_data['Perc_Outside']) + 3, color="black")    
    group_perc_outside_plot.save('group/susceptibility/fnirt_test/2/group_perc_outside_plot.png')

    column_headers = ['p_id', 'ssim_index', 'voxels_in_bin_ssim_mask', 'perc_roi_voxels_in_bin_ssim_mask']
    group_ssim_df = pd.DataFrame(columns = column_headers)   
    for p_id in participants_to_iterate:
        if p_id in good_participants:   
            print(f'Running Stage 2 SSIM analysis for {p_id}...')        
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
                return ssim_index
            ssim_output_path = f"{p_id}/analysis/susceptibility/fnirt_test/2/ssim_map.nii.gz"
            flirted_corrected_run = f"{p_id}/analysis/susceptibility/fnirt_test/2/flirted_corrected_run.nii.gz"
            flirted_uncorrected_run = f"{p_id}/analysis/susceptibility/fnirt_test/2/flirted_uncorrected_run.nii.gz"
            if not os.path.exists(ssim_output_path):
                ssim_index = calculate_ssim(flirted_uncorrected_run, flirted_corrected_run, ssim_output_path)       
            ssim_bin = f"{p_id}/analysis/susceptibility/fnirt_test/2/ssim_bin.nii.gz"
            if not os.path.exists(ssim_bin):
                subprocess.run(["fslmaths", ssim_output_path, "-thr", "0.8", "-binv", ssim_bin])
            combined_corr_uncorr_mask = f"{p_id}/analysis/susceptibility/fnirt_test/2/combined_corr_uncorr_mask.nii.gz"
            flirted_corrected_bin = f'{p_id}/analysis/susceptibility/fnirt_test/2/flirted_corrected_bin.nii.gz'
            flirted_uncorrected_bin = f'{p_id}/analysis/susceptibility/fnirt_test/2/flirted_uncorrected_bin.nii.gz'
            if not os.path.exists(combined_corr_uncorr_mask):
                subprocess.run(['fslmaths', flirted_corrected_bin, '-add', flirted_uncorrected_bin, combined_corr_uncorr_mask])
            bin_corr_uncorr_mask = f"{p_id}/analysis/susceptibility/fnirt_test/2/bin_corr_uncorr_mask.nii.gz"
            if not os.path.exists(bin_corr_uncorr_mask):
                subprocess.run(['fslmaths', combined_corr_uncorr_mask, '-bin', bin_corr_uncorr_mask])
            ssim_bin_trimmed = f"{p_id}/analysis/susceptibility/fnirt_test/2/ssim_bin_trimmed.nii.gz"
            if not os.path.exists(ssim_bin_trimmed):
                subprocess.run(['fslmaths', ssim_bin, '-mul', bin_corr_uncorr_mask, ssim_bin_trimmed])
            voxels_in_whole_mask = subprocess.run(["fslstats", ssim_bin_trimmed, "-V"], capture_output=True, text=True).stdout.split()[0]
            voxels_in_whole_mask = float(voxels_in_whole_mask)
            intersection_mask_path = f'{p_id}/analysis/susceptibility/fnirt_test/2/ssim_roi_intersect.nii.gz'
            transformed_roi_mask = f'{p_id}/analysis/susceptibility/fnirt_test/2/transformed_roi_mask.nii.gz'
            if not os.path.exists(intersection_mask_path):
                subprocess.run(["fslmaths", ssim_bin_trimmed, "-mas", transformed_roi_mask, intersection_mask_path])
            voxels_in_roi_in_mask = subprocess.run(["fslstats", intersection_mask_path, "-V"], capture_output=True, text=True).stdout.split()[0]
            voxels_in_roi_in_mask = float(voxels_in_roi_in_mask)
            perc_roi_voxels_in_mask = (voxels_in_roi_in_mask / total_voxels_in_roi) * 100
            ssim_df = pd.DataFrame({'p_id': [p_id], 'ssim_index': [ssim_index], 'voxels_in_bin_ssim_mask': [voxels_in_whole_mask], 'perc_roi_voxels_in_bin_ssim_mask': [perc_roi_voxels_in_mask]})
            ssim_df.to_csv(f'{p_id}/analysis/susceptibility/fnirt_test/2/ssim_df.txt', sep='\t', index=False)
            group_ssim_df = pd.concat([group_ssim_df, ssim_df], ignore_index=True)
    group_ssim_df.to_csv('group/susceptibility/fnirt_test/2/group_ssim_df.txt', sep='\t', index=False)
    ssim_indexes = group_ssim_df['ssim_index'].tolist()
    ssim_mean = np.mean(ssim_indexes)
    print(f"Mean SSIM index for Stage 2: {ssim_mean}")
    plot_data = pd.DataFrame({
        'Participant': good_participants,
        'SSIM': ssim_indexes,
    })
    ssim_index_plot = (
        ggplot(plot_data, aes(x='Participant', y='SSIM')) +
        geom_bar(stat='identity', position='dodge') +
        geom_hline(yintercept=ssim_mean, linetype='dashed', color='red') +
        theme_classic() +
        labs(title='SSIM Indexes', x='Participant', y='SSIM') +
        theme(axis_text_x=element_text(rotation=45, hjust=1), text=element_text(size=12, color='blue'), axis_title=element_text(size=12, face='bold')) +
        scale_y_continuous(expand=(0, 0), limits=[0.8,1])
    )
    ssim_index_plot.save('group/susceptibility/fnirt_test/2/ssim_index_plot.png')
    voxels = group_ssim_df['voxels_in_bin_ssim_mask'].tolist()
    voxels_mean = np.mean(voxels)
    plot_data = pd.DataFrame({
        'Participant': good_participants,
        'Voxels': voxels,
    })
    ssim_voxels_plot = (
        ggplot(plot_data, aes(x='Participant', y='Voxels')) +
        geom_bar(stat='identity', position='dodge') +
        geom_hline(yintercept=voxels_mean, linetype='dashed', color='red') +
        theme_classic() +
        labs(title='Number of Voxels in SSIM Mask', x='Participant', y='Voxels') +
        theme(axis_text_x=element_text(rotation=45, hjust=1), text=element_text(size=12, color='blue'), axis_title=element_text(size=12, face='bold')) +
        scale_y_continuous(expand=(0, 0))
    )
    ssim_voxels_plot.save('group/susceptibility/fnirt_test/2/ssim_voxels_plot.png')
    perc_voxels = group_ssim_df['perc_roi_voxels_in_bin_ssim_mask'].tolist()
    perc_voxels_mean = np.mean(perc_voxels)
    plot_data = pd.DataFrame({
        'Participant': good_participants,
        'Perc_Voxels': perc_voxels,
    })
    ssim_perc_voxels_plot = (
        ggplot(plot_data, aes(x='Participant', y='Perc_Voxels')) +
        geom_bar(stat='identity', position='dodge') +
        geom_hline(yintercept=perc_voxels_mean, linetype='dashed', color='red') +
        theme_classic() +
        labs(title='Percentage of ROI Voxels in SSIM Mask', x='Participant', y='Percentage of SCC Voxels in SSIM Mask') +
        theme(axis_text_x=element_text(rotation=45, hjust=1), text=element_text(size=12, color='black'), axis_title=element_text(size=12)) +
        scale_y_continuous(expand=(0, 0))
    )
    ssim_perc_voxels_plot.save('group/susceptibility/fnirt_test/2/ssim_perc_voxels_plot.png')

    column_headers = ['p_id', 'sequence', 'value']
    group_voxel_intensity_df = pd.DataFrame(columns = column_headers)   
    for p_id in participants_to_iterate:
        if p_id in good_participants:    
            print(f'Running Stage 2 voxel signal intensity analysis for {p_id}...')         
            def extract_voxel_intensities(epi_image_path, mask_image_path):
                epi_img = nib.load(epi_image_path)
                epi_data = epi_img.get_fdata()
                mask_img = nib.load(mask_image_path)
                mask_data = mask_img.get_fdata()
                mask_data = mask_data > 0
                roi_voxel_intensities = epi_data[mask_data]
                voxel_intensity_list = roi_voxel_intensities.tolist()
                return voxel_intensity_list
            flirted_corrected_run = f"{p_id}/analysis/susceptibility/fnirt_test/2/flirted_corrected_run.nii.gz"
            flirted_uncorrected_run = f"{p_id}/analysis/susceptibility/fnirt_test/2/flirted_uncorrected_run.nii.gz"
            corrected_trimmed_roi_mask = f"{p_id}/analysis/susceptibility/fnirt_test/2/corrected_trimmed_roi_mask.nii.gz"
            uncorrected_trimmed_roi_mask = f"{p_id}/analysis/susceptibility/fnirt_test/2/uncorrected_trimmed_roi_mask.nii.gz"
            corrected_voxel_intensities = extract_voxel_intensities(flirted_corrected_run, corrected_trimmed_roi_mask)
            uncorrected_voxel_intensities = extract_voxel_intensities(flirted_uncorrected_run, uncorrected_trimmed_roi_mask)
            values = corrected_voxel_intensities + uncorrected_voxel_intensities
            sequence = ['corrected'] * len(corrected_voxel_intensities) + ['uncorrected'] * len(uncorrected_voxel_intensities)
            subject = [f'{p_id}'] * len(corrected_voxel_intensities) + [f'{p_id}'] * len(uncorrected_voxel_intensities)
            voxel_intensity_df = pd.DataFrame({'p_id': subject, 'sequence': sequence, 'value': values})
            voxel_intensity_df.to_csv(f'{p_id}/analysis/susceptibility/fnirt_test/2/voxel_intensity_df.txt', sep='\t', index=False)
            group_voxel_intensity_df = pd.concat([group_voxel_intensity_df, voxel_intensity_df], ignore_index=True)
    group_voxel_intensity_df.to_csv('group/susceptibility/fnirt_test/2/group_voxel_intensity_df.txt', sep='\t', index=False)
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
                print(f'Anderson-Darling test passed for {p_id} voxel intensity values. Running parametric t-test...')
                _, p_value = stats.ttest_ind(filtered_corrected['value'], filtered_uncorrected['value'], equal_var=False)
                p_values.append(p_value)
            else:
                print(f'Anderson-Darling test failed for {p_id} voxel intensity values. Running non-parametric Mann-Whitney U test...')
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
    voxel_intensity_plot = (
        ggplot(plot_data, aes(x='Participant', y='Mean_Value', fill='Sequence')) +
        geom_bar(stat='identity', position='dodge') +
        geom_errorbar(aes(ymin='Mean_Value - Std_Error', ymax='Mean_Value + Std_Error'), position=position_dodge(width=0.9), width=0.2, color='black') +
        theme_classic() +
        labs(title='Mean SCC Voxel Intensity', x='Participant', y='Mean SCC Signal Intensity') +
        theme(axis_text_x=element_text(rotation=45, hjust=1), text=element_text(size=12, color='black'), axis_title=element_text(size=12)) +
        scale_y_continuous(expand=(0, 0), limits=[0,350]) +
        geom_text(
            aes(x='Participant', y='Mean_Value', label='Significance'),
            position=position_dodge(width=0.9),
            color='black',
            size=12,
            ha='center',
            va='bottom',
            show_legend=False))
    voxel_intensity_plot.save('group/susceptibility/fnirt_test/2/voxel_intensity_plot.png')
    corrected_means_overall = np.mean(corrected_means)
    uncorrected_means_overall = np.mean(uncorrected_means)
    corrected_std_error_overall = np.std(corrected_means) / np.sqrt(len(corrected_means))
    uncorrected_std_error_overall = np.std(uncorrected_means) / np.sqrt(len(uncorrected_means))
    _, corrected_means_overall_shap_p = stats.shapiro(corrected_means)
    _, uncorrected_means_overall_shap_p = stats.shapiro(uncorrected_means)
    if corrected_means_overall_shap_p > 0.05 and uncorrected_means_overall_shap_p > 0.05:
        print(f'Shapiro-Wilk test passed for voxel intensity values. Running parametric t-test...')
        _, p_value = stats.ttest_rel(corrected_means, uncorrected_means)
        print(f"T-test p-value: {p_value}")
    else:
        print(f'Shapiro-Wilk test failed for voxel intensity values. Running non-parametric Wilcoxon test...')
        _, p_value = stats.wilcoxon(corrected_means, uncorrected_means)
        print(f"Wilcoxon test p-value: {p_value}")
    plot_data = pd.DataFrame({'p_id': good_participants, 'corrected_values': corrected_means, 'uncorrected_values': uncorrected_means})
    data_long = pd.melt(plot_data, id_vars=['p_id'], value_vars=['corrected_values', 'uncorrected_values'], var_name='sequence', value_name='value')
    data_long['sequence'] = data_long['sequence'].map({'corrected_values': 'CORR', 'uncorrected_values': 'UNCORR'})
    group_voxel_intensity_ladder_plot = (
        ggplot(data_long, aes(x='sequence', y='value', group='p_id')) +
        geom_line(aes(group='p_id'), color='gray', size=1) +
        geom_point(aes(color='sequence'), size=4) +
        theme_light() +
        theme(
            panel_grid_major=element_blank(), 
            panel_grid_minor=element_blank(), 
            panel_border=element_blank(),
            axis_line_x=element_line(color='black'),  
            axis_line_y=element_line(color='black'),  
        ) +
        labs(title='Ladder Plot of Corrected and Uncorrected PA Sequence',
            x='Sequence',
            y='Mean SCC Signal Intensity') +
        scale_x_discrete(limits=['CORR', 'UNCORR']) +
        scale_y_continuous()
    )
    group_voxel_intensity_ladder_plot.save('group/susceptibility/fnirt_test/2/group_voxel_intensity_ladder_plot.png')
    plot_data = pd.DataFrame({'Sequence': ['Corrected', 'Uncorrected'], 'Mean': [corrected_means_overall, uncorrected_means_overall], 'Std_Error': [corrected_std_error_overall, uncorrected_std_error_overall]})
    group_voxel_intensity_plot = (ggplot(plot_data, aes(x='Sequence', y='Mean', fill='Sequence')) + 
                        geom_bar(stat='identity', position='dodge') +
                        geom_errorbar(aes(ymin='Mean - Std_Error', ymax='Mean + Std_Error'), width=0.2, color='black') +
                        theme_classic() +
                        labs(title='Mean of Voxel Intensities Across Participants', y='Mean SCC Signal Intensity') +
                        scale_y_continuous(expand=(0, 0), limits=[0,350]) +
                        scale_fill_manual(values={'PA': '#DB5F57', 'RL': '#57D3DB'})
                        )
    if p_value < 0.001:
        group_voxel_intensity_plot = group_voxel_intensity_plot + annotate("text", x=1.5, y=max(plot_data['Mean']) + 40, label="***", size=16, color="black") + \
            annotate("segment", x=1, xend=2, y=max(plot_data['Mean']) +30, yend=max(plot_data['Mean']) + 30, color="black")
    elif p_value < 0.01:
        group_voxel_intensity_plot = group_voxel_intensity_plot + annotate("text", x=1.5, y=max(plot_data['Mean']) + 40, label="**", size=16, color="black") + \
            annotate("segment", x=1, xend=2, y=max(plot_data['Mean']) +30, yend=max(plot_data['Mean']) + 30, color="black")
    elif p_value < 0.05:
        group_voxel_intensity_plot = group_voxel_intensity_plot + annotate("text", x=1.5, y=max(plot_data['Mean']) + 40, label="*", size=16, color="black") + \
            annotate("segment", x=1, xend=2, y=max(plot_data['Mean']) +30, yend=max(plot_data['Mean']) + 30, color="black")    
    group_voxel_intensity_plot.save('group/susceptibility/fnirt_test/2/group_voxel_intensity_plot.png')

    # Step 5: Test quality of alternate distortion correction method (Stage 3).
    print("\n###### STEP 5: TESTING ALTERNATE DISTORTION CORRECTION METHOD (STAGE 3) ######")   
    bad_participants = ['P004', 'P006', 'P020', 'P030', 'P078', 'P093', 'P094']
    perc_outside_run01_values = []
    perc_outside_run04_values = []
    column_headers = ['p_id', 'perc_outside_run01', 'perc_outside_run04']
    group_perc_outside_df = pd.DataFrame(columns = column_headers) 
    for p_id in participants_to_iterate:
        if p_id in bad_participants:
            print(f"Preparing Stage 3 files for {p_id}...")
            run01 = f"{p_id}/analysis/preproc/niftis/run01_nh.nii"
            run04 = f"{p_id}/analysis/preproc/niftis/run04_nh.nii"
            averaged_run01 = f"{p_id}/analysis/susceptibility/fnirt_test/3/averaged_run01.nii.gz"
            averaged_run04 = f"{p_id}/analysis/susceptibility/fnirt_test/3/averaged_run04.nii.gz"
            if not os.path.exists(averaged_run01) or not os.path.exists(averaged_run04):
                subprocess.run(['fslmaths', run01, '-Tmean', averaged_run01])
                subprocess.run(['fslmaths', run04, '-Tmean', averaged_run04])
            betted_run01 = f"{p_id}/analysis/susceptibility/fnirt_test/3/betted_run01.nii.gz"
            betted_run04 = f"{p_id}/analysis/susceptibility/fnirt_test/3/betted_run04.nii.gz"
            if not os.path.exists(betted_run01) or not os.path.exists(betted_run04):
                subprocess.run(["bet", averaged_run01, betted_run01, "-m", "-R"])
                subprocess.run(["bet", averaged_run04, betted_run04, "-m", "-R"])
            flirted_run01 = f"{p_id}/analysis/susceptibility/fnirt_test/3/flirted_run01.nii.gz"
            flirted_run04 = f"{p_id}/analysis/susceptibility/fnirt_test/3/flirted_run04.nii.gz"
            t1_flirted_run01_transformation = f"{p_id}/analysis/susceptibility/fnirt_test/3/t1_flirted_run01_transformation.mat"
            t1_flirted_run04_transformation = f"{p_id}/analysis/susceptibility/fnirt_test/3/t1_flirted_run04_transformation.mat"
            structural_brain = f"{p_id}/analysis/preproc/structural/structural_brain.nii.gz"
            if not os.path.exists(flirted_run01):
                subprocess.run(["flirt", "-in", betted_run01, "-ref", structural_brain, "-out", flirted_run01, "-omat", t1_flirted_run01_transformation])
                subprocess.run(["flirt", "-in", betted_run04, "-ref", structural_brain, "-out", flirted_run04, "-omat", t1_flirted_run04_transformation])
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
            roi_file_run01 = f"{p_id}/data/neurofeedback/{cisc_folder}/depression_neurofeedback/target_folder_run-1/depnf_run-1.roi"
            voxel_coordinates_run01 = read_roi_file(roi_file_run01)
            run01_template = f"{p_id}/analysis/susceptibility/fnirt_test/3/run01_template.nii.gz"
            if not os.path.exists(run01_template):
                run = f"{p_id}/analysis/preproc/niftis/run01_nh.nii.gz"
                subprocess.run(['fslmaths', run, '-Tmean', run01_template])
            functional_image_info = nib.load(run01_template)
            functional_dims = functional_image_info.shape
            binary_volume = np.zeros(functional_dims)
            for voxel in voxel_coordinates:
                x, y, z = voxel
                binary_volume[x, y, z] = 1
            binary_volume = np.flip(binary_volume, axis=1)
            functional_affine = functional_image_info.affine
            binary_mask = nib.Nifti1Image(binary_volume, affine=functional_affine)
            nib.save(binary_mask, f'{p_id}/analysis/susceptibility/fnirt_test/3/run01_subject_space_ROI.nii.gz')
            roi_mask_run01 = f'{p_id}/analysis/susceptibility/fnirt_test/3/run01_subject_space_ROI.nii.gz'
            flirted_roi_run01 = f'{p_id}/analysis/susceptibility/fnirt_test/3/flirted_roi_run01.nii.gz'
            if not os.path.exists(flirted_roi_run01):
                subprocess.run(['flirt', '-in', roi_mask_run01, '-ref', structural_brain, '-applyxfm', '-init', t1_flirted_run01_transformation, '-out', flirted_roi_run01, '-interp', 'nearestneighbour'])
            roi_file_run04 = f"{p_id}/data/neurofeedback/{cisc_folder}/depression_neurofeedback/target_folder_run-4/depnf_run-4.roi"
            voxel_coordinates_run04 = read_roi_file(roi_file_run04)
            run04_template = f"{p_id}/analysis/susceptibility/fnirt_test/3/run04_template.nii.gz"
            if not os.path.exists(run04_template):
                run = f"{p_id}/analysis/preproc/niftis/run04_nh.nii.gz"
                subprocess.run(['fslmaths', run, '-Tmean', run04_template])
            functional_image_info = nib.load(run04_template)
            functional_dims = functional_image_info.shape
            binary_volume = np.zeros(functional_dims)
            for voxel in voxel_coordinates:
                x, y, z = voxel
                binary_volume[x, y, z] = 1
            binary_volume = np.flip(binary_volume, axis=1)
            functional_affine = functional_image_info.affine
            binary_mask = nib.Nifti1Image(binary_volume, affine=functional_affine)
            nib.save(binary_mask, f'{p_id}/analysis/susceptibility/fnirt_test/3/run04_subject_space_ROI.nii.gz')
            roi_mask_run04 = f'{p_id}/analysis/susceptibility/fnirt_test/3/run04_subject_space_ROI.nii.gz'
            flirted_roi_run04 = f'{p_id}/analysis/susceptibility/fnirt_test/3/flirted_roi_run04.nii.gz'
            if not os.path.exists(flirted_roi_run04):
                subprocess.run(['flirt', '-in', roi_mask_run04, '-ref', structural_brain, '-applyxfm', '-init', t1_flirted_run04_transformation, '-out', flirted_roi_run04, '-interp', 'nearestneighbour'])
            flirted_run01_bin = f'{p_id}/analysis/susceptibility/fnirt_test/3/flirted_run01_bin.nii.gz'
            if not os.path.exists(flirted_run01_bin):
                subprocess.run(['fslmaths', flirted_run01, '-thr', '100', '-bin', flirted_run01_bin])
            flirted_run04_bin = os.path.join(f'{p_id}/analysis/susceptibility/fnirt_test/3/flirted_run04_bin.nii.gz')
            if not os.path.exists(flirted_run04_bin):
                subprocess.run(['fslmaths', flirted_run04, '-thr', '100', '-bin', flirted_run04_bin])
            run01_bin_inv = f'{p_id}/analysis/susceptibility/fnirt_test/3/run01_bin_inv.nii.gz'
            if not os.path.exists(run01_bin_inv):
                subprocess.run(['fslmaths', flirted_run01_bin, '-sub', '1', '-abs', run01_bin_inv])
            run04_bin_inv = f'{p_id}/analysis/susceptibility/fnirt_test/3/run04_bin_inv.nii.gz'
            if not os.path.exists(run04_bin_inv):
                subprocess.run(['fslmaths', flirted_run04_bin, '-sub', '1', '-abs', run04_bin_inv])
            run01_result = subprocess.run(['fslstats', flirted_roi_run01, '-k', run01_bin_inv, '-V'], capture_output=True, text=True)
            if run01_result.returncode == 0:
                run01_result_output = run01_result.stdout.strip()
            else:
                print("Error executing fslstats command.")
            run01_result_output_values = run01_result_output.split()
            run01_voxels_outside = float(run01_result_output_values[0])
            run04_result = subprocess.run(['fslstats', flirted_roi_run04, '-k', run04_bin_inv, '-V'], capture_output=True, text=True)
            if run04_result.returncode == 0:
                run04_result_output = run04_result.stdout.strip()
            else:
                print("Error executing fslstats command.")
            run04_result_output_values = run04_result_output.split()
            run04_voxels_outside = float(run04_result_output_values[0])
            result1 = subprocess.run(['fslstats', flirted_roi_run01, '-V'], capture_output=True, text=True)
            if result1.returncode == 0:
                result1_output = result1.stdout.strip()
            else:
                print("Error executing fslstats command.")
            result1_output_values = result1_output.split()
            total_voxels_in_roi_run01 = float(result1_output_values[0])
            result2 = subprocess.run(['fslstats', flirted_roi_run04, '-V'], capture_output=True, text=True)
            if result2.returncode == 0:
                result2_output = result2.stdout.strip()
            else:
                print("Error executing fslstats command.")
            result2_output_values = result2_output.split()
            total_voxels_in_roi_run04 = float(result2_output_values[0])
            perc_outside_run01 = (run01_voxels_outside / total_voxels_in_roi_run01) * 100
            perc_outside_run01 = round(perc_outside_run01, 2)
            perc_outside_run01_values.append(perc_outside_run01)
            perc_outside_run04 = (run04_voxels_outside / total_voxels_in_roi_run04) * 100
            perc_outside_run04 = round(perc_outside_run04, 2)
            perc_outside_run04_values.append(perc_outside_run04)
            perc_outside_df = pd.DataFrame({'p_id': [p_id], 'perc_outside_run01': [perc_outside_run01], 'perc_outside_run04': [perc_outside_run04]})
            perc_outside_df.to_csv(f'{p_id}/analysis/susceptibility/fnirt_test/3/perc_outside_df.txt', sep='\t', index=False)
            group_perc_outside_df = pd.concat([group_perc_outside_df, perc_outside_df], ignore_index=True)
            run01_trimmed_roi_mask = f"{p_id}/analysis/susceptibility/fnirt_test/3/run01_trimmed_roi_mask.nii.gz"
            run04_trimmed_roi_mask = f"{p_id}/analysis/susceptibility/fnirt_test/3/run04_trimmed_roi_mask.nii.gz"
            if not os.path.exists(run01_trimmed_roi_mask) or not os.path.exists(run04_trimmed_roi_mask):
                subprocess.run(['fslmaths', transformed_roi_mask, '-mul', flirted_run01_bin, run01_trimmed_roi_mask])
                subprocess.run(['fslmaths', transformed_roi_mask, '-mul', flirted_run04_bin, run04_trimmed_roi_mask])
    group_perc_outside_df.to_csv('group/susceptibility/fnirt_test/3/group_perc_outside_df.txt', sep='\t', index=False)
    plot_data = pd.DataFrame({
        'Participant': bad_participants * 2,
        'Perc_Outside': perc_outside_run01_values + perc_outside_run04_values,
        'Sequence': ['run01'] * len(bad_participants) + ['run04'] * len(bad_participants)
    })
    perc_outside_plot = (
        ggplot(plot_data, aes(x='Participant', y='Perc_Outside', fill='Sequence')) +
        geom_bar(stat='identity', position='dodge') +
        theme_classic() +
        labs(title='Percentage of Voxels in Signal Dropout Regions', x='Participant', y='Percentage of SCC Voxels in Signal Dropout') +
        theme(axis_text_x=element_text(rotation=45, hjust=1), text=element_text(size=12, color='black'), axis_title=element_text(size=12)) +
        scale_y_continuous(expand=(0, 0))
    )
    perc_outside_plot.save('group/susceptibility/fnirt_test/3/perc_outside_plot.png')
    perc_outside_run01_overall = np.mean(perc_outside_run01_values)
    perc_outside_run04_overall = np.mean(perc_outside_run04_values)
    run01_std_error = np.std(perc_outside_run01_values) / np.sqrt(len(perc_outside_run01_values))
    run04_std_error = np.std(perc_outside_run04_values) / np.sqrt(len(perc_outside_run04_values))
    _, perc_outside_run01_overall_shap_p = stats.shapiro(perc_outside_run01_values)
    _, perc_outside_run04_overall_shap_p = stats.shapiro(perc_outside_run04_values)
    if perc_outside_run01_overall_shap_p > 0.05 and perc_outside_run04_overall_shap_p > 0.05:
        print(f'Shapiro-Wilk test passed for perc_outside values. Running parametric t-test...')
        _, p_value = stats.ttest_ind(perc_outside_run01_values, perc_outside_run04_values)
        print(f"T-test p-value: {p_value}")
    else:
        print(f'Shapiro-Wilk test failed for perc_outside values. Running non-parametric Mann-Whitney U test...')
        _, p_value = stats.mannwhitneyu(perc_outside_run01_values, perc_outside_run04_values)
        print(f"Mann-Whitney U test p-value: {p_value}")
    plot_data = pd.DataFrame({'Sequence': ['run01', 'run04'], 'Perc_Outside': [perc_outside_run01_overall, perc_outside_run04_overall], 'Std_Error': [run01_std_error, run04_std_error]})
    group_perc_outside_plot = (ggplot(plot_data, aes(x='Sequence', y='Perc_Outside', fill='Sequence')) + 
                        geom_bar(stat='identity', position='dodge') +
                        geom_errorbar(aes(ymin='Perc_Outside - Std_Error', ymax='Perc_Outside + Std_Error'), width=0.2, color='black') +
                        theme_classic() +
                        labs(title='Percentage of Voxels in Signal Dropout Regions', y='Percentage of SCC Voxels in Signal Dropout') +
                        scale_y_continuous(expand=(0, 0)) +
                        scale_fill_manual(values={'PA': '#DB5F57', 'RL': '#57D3DB'})
                        )
    if p_value < 0.001:
        group_perc_outside_plot = group_perc_outside_plot + annotate("text", x=1.5, y=max(plot_data['Perc_Outside']) + 3.5, label="***", size=16, color="black") + \
            annotate("segment", x=1, xend=2, y=max(plot_data['Perc_Outside']) + 3, yend=max(plot_data['Perc_Outside']) + 3, color="black")
    elif p_value < 0.01:
        group_perc_outside_plot = group_perc_outside_plot + annotate("text", x=1.5, y=max(plot_data['Perc_Outside']) + 3.5, label="**", size=16, color="black") + \
            annotate("segment", x=1, xend=2, y=max(plot_data['Perc_Outside']) + 3, yend=max(plot_data['Perc_Outside']) + 3, color="black")
    elif p_value < 0.05:
        group_perc_outside_plot = group_perc_outside_plot + annotate("text", x=1.5, y=max(plot_data['Perc_Outside']) + 3.5, label="*", size=16, color="black") + \
            annotate("segment", x=1, xend=2, y=max(plot_data['Perc_Outside']) + 3, yend=max(plot_data['Perc_Outside']) + 3, color="black")    
    group_perc_outside_plot.save('group/susceptibility/fnirt_test/3/group_perc_outside_plot.png')
    
    column_headers = ['p_id', 'ssim_index', 'voxels_in_bin_ssim_mask', 'perc_roi_voxels_in_bin_ssim_mask']
    group_ssim_df = pd.DataFrame(columns = column_headers) 
    for p_id in participants_to_iterate:
        if p_id in bad_participants:
            print(f"Running Stage 3 SSIM analysis for {p_id}...")
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
                return ssim_index
            ssim_output_path = f"{p_id}/analysis/susceptibility/fnirt_test/3/ssim_map.nii.gz"
            flirted_run01 = f"{p_id}/analysis/susceptibility/fnirt_test/3/flirted_run01.nii.gz"
            flirted_run04 = f"{p_id}/analysis/susceptibility/fnirt_test/3/flirted_run04.nii.gz"
            if not os.path.exists(ssim_output_path):
                ssim_index = calculate_ssim(flirted_run01, flirted_run04, ssim_output_path)
            ssim_bin = f"{p_id}/analysis/susceptibility/fnirt_test/3/ssim_bin.nii.gz"
            if not os.path.exists(ssim_bin):
                subprocess.run(["fslmaths", ssim_output_path, "-thr", "0.8", "-binv", ssim_bin])
            combined_run01_run04_mask = f"{p_id}/analysis/susceptibility/fnirt_test/3/combined_run01_run04_mask.nii.gz"
            flirted_run01_bin = f'{p_id}/analysis/susceptibility/fnirt_test/3/flirted_run01_bin.nii.gz'
            flirted_run04_bin = f'{p_id}/analysis/susceptibility/fnirt_test/3/flirted_run04_bin.nii.gz'
            if not os.path.exists(combined_run01_run04_mask):
                subprocess.run(['fslmaths', flirted_run01_bin, '-add', flirted_run04_bin, combined_run01_run04_mask])
            bin_run01_run04_mask = f"{p_id}/analysis/susceptibility/fnirt_test/3/bin_run01_run04_mask.nii.gz"
            if not os.path.exists(bin_run01_run04_mask):
                subprocess.run(['fslmaths', combined_run01_run04_mask, '-bin', bin_run01_run04_mask])
            ssim_bin_trimmed = f"{p_id}/analysis/susceptibility/fnirt_test/3/ssim_bin_trimmed.nii.gz"
            if not os.path.exists(ssim_bin_trimmed):
                subprocess.run(['fslmaths', ssim_bin, '-mul', bin_run01_run04_mask, ssim_bin_trimmed])
            voxels_in_whole_mask = subprocess.run(["fslstats", ssim_bin_trimmed, "-V"], capture_output=True, text=True).stdout.split()[0]
            voxels_in_whole_mask = float(voxels_in_whole_mask)
            intersection_mask_path_run01 = f'{p_id}/analysis/susceptibility/fnirt_test/3/ssim_roi_intersect_run01.nii.gz'
            intersection_mask_path_run04 = f'{p_id}/analysis/susceptibility/fnirt_test/3/ssim_roi_intersect_run04.nii.gz'
            run01_trimmed_roi_mask = f"{p_id}/analysis/susceptibility/fnirt_test/3/run01_trimmed_roi_mask.nii.gz"
            run04_trimmed_roi_mask = f"{p_id}/analysis/susceptibility/fnirt_test/3/run04_trimmed_roi_mask.nii.gz"
            if not os.path.exists(intersection_mask_path_run01):
                subprocess.run(["fslmaths", ssim_bin_trimmed, "-mas", run01_trimmed_roi_mask, intersection_mask_path_run01])
                subprocess.run(["fslmaths", ssim_bin_trimmed, "-mas", run04_trimmed_roi_mask, intersection_mask_path_run04])
            voxels_in_roi_in_mask_run01 = subprocess.run(["fslstats", intersection_mask_path_run01, "-V"], capture_output=True, text=True).stdout.split()[0]
            voxels_in_roi_in_mask_run01 = float(voxels_in_roi_in_mask_run01)
            perc_roi_voxels_in_mask_run01 = (voxels_in_roi_in_mask_run01 / total_voxels_in_roi_run01) * 100
            voxels_in_roi_in_mask_run04 = subprocess.run(["fslstats", intersection_mask_path_run04, "-V"], capture_output=True, text=True).stdout.split()[0]
            voxels_in_roi_in_mask_run04 = float(voxels_in_roi_in_mask_run04)
            perc_roi_voxels_in_mask_run04 = (voxels_in_roi_in_mask_run04 / total_voxels_in_roi_run04) * 100
            perc_roi_voxels_in_mask_av = (perc_roi_voxels_in_mask_run01 + perc_roi_voxels_in_mask_run04) / 2
            ssim_df = pd.DataFrame({'p_id': [p_id], 'ssim_index': [ssim_index], 'voxels_in_bin_ssim_mask': [voxels_in_whole_mask], 'perc_roi_voxels_in_bin_ssim_mask': [perc_roi_voxels_in_mask_av]})
            ssim_df.to_csv(f'{p_id}/analysis/susceptibility/fnirt_test/3/ssim_df.txt', sep='\t', index=False)
            group_ssim_df = pd.concat([group_ssim_df, ssim_df], ignore_index=True)
    group_ssim_df.to_csv('group/susceptibility/fnirt_test/3/group_ssim_df.txt', sep='\t', index=False)
    ssim_indexes = group_ssim_df['ssim_index'].tolist()
    ssim_mean = np.mean(ssim_indexes)
    print(f"Mean SSIM index for Stage 3: {ssim_mean}")
    plot_data = pd.DataFrame({
        'Participant': bad_participants,
        'SSIM': ssim_indexes,
    })
    ssim_index_plot = (
        ggplot(plot_data, aes(x='Participant', y='SSIM')) +
        geom_bar(stat='identity', position='dodge') +
        geom_hline(yintercept=ssim_mean, linetype='dashed', color='red') +
        theme_classic() +
        labs(title='SSIM Indexes', x='Participant', y='SSIM') +
        theme(axis_text_x=element_text(rotation=45, hjust=1), text=element_text(size=12, color='blue'), axis_title=element_text(size=12, face='bold')) +
        scale_y_continuous(expand=(0, 0), limits=[0.8,1])
    )
    ssim_index_plot.save('group/susceptibility/fnirt_test/3/ssim_index_plot.png')
    voxels = group_ssim_df['voxels_in_bin_ssim_mask'].tolist()
    voxels_mean = np.mean(voxels)
    plot_data = pd.DataFrame({
        'Participant': bad_participants,
        'Voxels': voxels,
    })
    ssim_voxels_plot = (
        ggplot(plot_data, aes(x='Participant', y='Voxels')) +
        geom_bar(stat='identity', position='dodge') +
        geom_hline(yintercept=voxels_mean, linetype='dashed', color='red') +
        theme_classic() +
        labs(title='Number of Voxels in SSIM Mask', x='Participant', y='Voxels') +
        theme(axis_text_x=element_text(rotation=45, hjust=1), text=element_text(size=12, color='blue'), axis_title=element_text(size=12, face='bold')) +
        scale_y_continuous(expand=(0, 0))
    )
    ssim_voxels_plot.save('group/susceptibility/fnirt_test/3/ssim_voxels_plot.png')
    perc_voxels = group_ssim_df['perc_roi_voxels_in_bin_ssim_mask'].tolist()
    perc_voxels_mean = np.mean(perc_voxels)
    plot_data = pd.DataFrame({
        'Participant': bad_participants,
        'Perc_Voxels': perc_voxels,
    })
    ssim_perc_voxels_plot = (
        ggplot(plot_data, aes(x='Participant', y='Perc_Voxels')) +
        geom_bar(stat='identity', position='dodge') +
        geom_hline(yintercept=perc_voxels_mean, linetype='dashed', color='red') +
        theme_classic() +
        labs(title='Percentage of ROI Voxels in SSIM Mask', x='Participant', y='Percentage of SCC Voxels in SSIM Mask') +
        theme(axis_text_x=element_text(rotation=45, hjust=1), text=element_text(size=12, color='black'), axis_title=element_text(size=12)) +
        scale_y_continuous(expand=(0, 0))
    )
    ssim_perc_voxels_plot.save('group/susceptibility/fnirt_test/3/ssim_perc_voxels_plot.png')

    column_headers = ['p_id', 'sequence', 'value']
    group_voxel_intensity_df = pd.DataFrame(columns = column_headers)   
    for p_id in participants_to_iterate:
        if p_id in bad_participants:
            print(f'Running Stage 3 voxel signal intensity analysis for {p_id}...')
            def extract_voxel_intensities(epi_image_path, mask_image_path):
                epi_img = nib.load(epi_image_path)
                epi_data = epi_img.get_fdata()
                mask_img = nib.load(mask_image_path)
                mask_data = mask_img.get_fdata()
                mask_data = mask_data > 0
                roi_voxel_intensities = epi_data[mask_data]
                voxel_intensity_list = roi_voxel_intensities.tolist()
                return voxel_intensity_list
            flirted_run01 = f"{p_id}/analysis/susceptibility/fnirt_test/3/flirted_run01.nii.gz"
            flirted_run04 = f"{p_id}/analysis/susceptibility/fnirt_test/3/flirted_run04.nii.gz"
            run01_trimmed_roi_mask = f"{p_id}/analysis/susceptibility/fnirt_test/3/run01_trimmed_roi_mask.nii.gz"
            run04_trimmed_roi_mask = f"{p_id}/analysis/susceptibility/fnirt_test/3/run04_trimmed_roi_mask.nii.gz"
            run01_voxel_intensities = extract_voxel_intensities(flirted_run01, run01_trimmed_roi_mask)
            run04_voxel_intensities = extract_voxel_intensities(flirted_run04, run04_trimmed_roi_mask)
            values = run01_voxel_intensities + run04_voxel_intensities
            sequence = ['run01'] * len(run01_voxel_intensities) + ['run04'] * len(run04_voxel_intensities)
            subject = [f'{p_id}'] * len(run01_voxel_intensities) + [f'{p_id}'] * len(run04_voxel_intensities)
            voxel_intensity_df = pd.DataFrame({'p_id': subject, 'sequence': sequence, 'value': values})
            voxel_intensity_df.to_csv(f'{p_id}/analysis/susceptibility/fnirt_test/3/voxel_intensity_df.txt', sep='\t', index=False)
            group_voxel_intensity_df = pd.concat([group_voxel_intensity_df, voxel_intensity_df], ignore_index=True)
    group_voxel_intensity_df.to_csv('group/susceptibility/fnirt_test/3/group_voxel_intensity_df.txt', sep='\t', index=False)
    run01_means = []
    run04_means= []
    p_values = []
    run01_std_errors = []
    run04_std_errors = []
    for p_id in participants_to_iterate:
        if p_id in bad_participants:
            filtered_run01 = group_voxel_intensity_df[(group_voxel_intensity_df['p_id'] == f'{p_id}') & (group_voxel_intensity_df['sequence'] == 'run01')]
            mean_value_run01 = filtered_run01['value'].mean()
            run01_means.append(mean_value_run01)
            filtered_run04 = group_voxel_intensity_df[(group_voxel_intensity_df['p_id'] == f'{p_id}') & (group_voxel_intensity_df['sequence'] == 'run04')]
            mean_value_run04 = filtered_run04['value'].mean()
            run04_means.append(mean_value_run04)
            anderson_run01 = stats.anderson(filtered_run01['value'])
            anderson_run04 = stats.anderson(filtered_run04['value'])
            significance_level = 0.05
            is_run01_normal = anderson_run01.statistic < anderson_pa.critical_values[
                anderson_pa.significance_level.tolist().index(significance_level * 100)]
            is_run04_normal = anderson_run04.statistic < anderson_rl.critical_values[
                anderson_rl.significance_level.tolist().index(significance_level * 100)]
            if is_run01_normal and is_run04_normal:
                print(f'Anderson-Darling test passed for {p_id} voxel intensity values. Running parametric t-test...')
                _, p_value = stats.ttest_ind(filtered_run01['value'], filtered_run04['value'], equal_var=False)
                p_values.append(p_value)
            else:
                print(f'Anderson-Darling test failed for {p_id} voxel intensity values. Running non-parametric Mann Whitney U test...')
                _, p_value = stats.mannwhitneyu(filtered_run01['value'], filtered_run04['value'], alternative='two-sided')
                p_values.append(p_value)
            run01_std_error = np.std(filtered_run01['value']) / np.sqrt(len(filtered_run01['value']))
            run01_std_errors.append(run01_std_error)
            run04_std_error = np.std(filtered_run04['value']) / np.sqrt(len(filtered_run04['value']))
            run04_std_errors.append(run04_std_error)
    plot_data = pd.DataFrame({
        'Participant': bad_participants * 2,
        'Mean_Value': run01_means + run04_means,
        'Sequence': ['RUN01'] * len(bad_participants) + ['RUN04'] * len(bad_participants),
        'Significance': ['' for _ in range(len(bad_participants) * 2)],
        'Std_Error': run01_std_errors + run04_std_errors
    })
    for idx, p_value in enumerate(p_values):
        if p_value < 0.001:
            plot_data.at[idx, 'Significance'] = '***'
        elif p_value < 0.01:
            plot_data.at[idx, 'Significance'] = '**'
        elif p_value < 0.05:
            plot_data.at[idx, 'Significance'] = '*'
    voxel_intensity_plot = (
        ggplot(plot_data, aes(x='Participant', y='Mean_Value', fill='Sequence')) +
        geom_bar(stat='identity', position='dodge') +
        geom_errorbar(aes(ymin='Mean_Value - Std_Error', ymax='Mean_Value + Std_Error'), position=position_dodge(width=0.9), width=0.2, color='black') +
        theme_classic() +
        labs(title='Mean SCC Voxel Intensity', x='Participant', y='Mean SCC Signal Intensity') +
        theme(axis_text_x=element_text(rotation=45, hjust=1), text=element_text(size=12, color='black'), axis_title=element_text(size=12)) +
        scale_y_continuous(expand=(0, 0), limits=[0,350]) +
        geom_text(
            aes(x='Participant', y='Mean_Value', label='Significance'),
            position=position_dodge(width=0.9),
            color='black',
            size=12,
            ha='center',
            va='bottom',
            show_legend=False))
    voxel_intensity_plot.save('group/susceptibility/fnirt_test/3/voxel_intensity_plot.png')
    run01_means_overall = np.mean(run01_means)
    run04_means_overall = np.mean(run04_means)
    run01_std_error_overall = np.std(run01_means) / np.sqrt(len(run01_means))
    run04_std_error_overall = np.std(run04_means) / np.sqrt(len(run04_means))
    _, run01_means_overall_shap_p = stats.shapiro(run01_means)
    _, run04_means_overall_shap_p = stats.shapiro(run04_means)
    if run01_means_overall_shap_p > 0.05 and run04_means_overall_shap_p > 0.05:
        print(f'Shapiro-Wilk test passed for voxel intensity values. Running parametric t-test...')
        _, p_value = stats.ttest_rel(run01_means, run04_means)
        print(f"T-test p-value: {p_value}")
    else:
        print(f'Shapiro-Wilk test failed for voxel intensity values. Running non-parametric Wilcoxon test...')
        _, p_value = stats.wilcoxon(run01_means, run04_means)
        print(f"Wilcoxon test p-value: {p_value}")
    plot_data = pd.DataFrame({'p_id': bad_participants, 'run01_values': run01_means, 'run04_values': run04_means})
    data_long = pd.melt(plot_data, id_vars=['p_id'], value_vars=['run01_values', 'run04_values'], var_name='sequence', value_name='value')
    data_long['sequence'] = data_long['sequence'].map({'run01_values': 'RUN01', 'run04_values': 'RUN04'})
    group_voxel_intensity_ladder_plot = (
        ggplot(data_long, aes(x='sequence', y='value', group='p_id')) +
        geom_line(aes(group='p_id'), color='gray', size=1) +
        geom_point(aes(color='sequence'), size=4) +
        theme_light() +
        theme(
            panel_grid_major=element_blank(), 
            panel_grid_minor=element_blank(), 
            panel_border=element_blank(),
            axis_line_x=element_line(color='black'),  
            axis_line_y=element_line(color='black'),  
        ) +
        labs(title='Ladder Plot of RUN01 and RUN04 Sequences',
            x='Sequence',
            y='Mean SCC Signal Intensity') +
        scale_x_discrete(limits=['RUN01', 'RUN04']) +
        scale_y_continuous()
    )
    group_voxel_intensity_ladder_plot.save('group/susceptibility/fnirt_test/3/group_voxel_intensity_ladder_plot.png')
    plot_data = pd.DataFrame({'Sequence': ['RUN01', 'RUN04'], 'Mean': [run01_means_overall, run04_means_overall], 'Std_Error': [run01_std_error_overall, run04_std_error_overall]})
    group_voxel_intensity_plot = (ggplot(plot_data, aes(x='Sequence', y='Mean', fill='Sequence')) + 
                        geom_bar(stat='identity', position='dodge') +
                        geom_errorbar(aes(ymin='Mean - Std_Error', ymax='Mean + Std_Error'), width=0.2, color='black') +
                        theme_classic() +
                        labs(title='Mean of Voxel Intensities Across Participants', y='Mean SCC Signal Intensity') +
                        scale_y_continuous(expand=(0, 0), limits=[0,350]) +
                        scale_fill_manual(values={'PA': '#DB5F57', 'RL': '#57D3DB'})
                        )
    if p_value < 0.001:
        group_voxel_intensity_plot = group_voxel_intensity_plot + annotate("text", x=1.5, y=max(plot_data['Mean']) + 40, label="***", size=16, color="black") + \
            annotate("segment", x=1, xend=2, y=max(plot_data['Mean']) +30, yend=max(plot_data['Mean']) + 30, color="black")
    elif p_value < 0.01:
        group_voxel_intensity_plot = group_voxel_intensity_plot + annotate("text", x=1.5, y=max(plot_data['Mean']) + 40, label="**", size=16, color="black") + \
            annotate("segment", x=1, xend=2, y=max(plot_data['Mean']) +30, yend=max(plot_data['Mean']) + 30, color="black")
    elif p_value < 0.05:
        group_voxel_intensity_plot = group_voxel_intensity_plot + annotate("text", x=1.5, y=max(plot_data['Mean']) + 40, label="*", size=16, color="black") + \
            annotate("segment", x=1, xend=2, y=max(plot_data['Mean']) +30, yend=max(plot_data['Mean']) + 30, color="black")    
    group_voxel_intensity_plot.save('group/susceptibility/fnirt_test/3/group_voxel_intensity_plot.png')

    # Step 6: Test quality of alternate distortion correction method (Stage 4).
    print("\n###### STEP 5: TESTING ALTERNATE DISTORTION CORRECTION METHOD (STAGE 4) ######")   
    bad_participants = ['P004', 'P006', 'P020', 'P030', 'P078', 'P093', 'P094']
    perc_outside_run01_values = []
    perc_outside_run04_values = []
    column_headers = ['p_id', 'perc_outside_run01', 'perc_outside_run04']
    group_perc_outside_df = pd.DataFrame(columns = column_headers) 
    for p_id in participants_to_iterate:
        if p_id in bad_participants:
            print(f"Preparing Stage 4 files for {p_id}...")
            run01 = f"{p_id}/analysis/preproc/niftis/run01_nh.nii.gz"
            run04 = f"{p_id}/analysis/preproc/niftis/run04_nh.nii.gz"
            averaged_run01 = f"{p_id}/analysis/susceptibility/fnirt_test/4/averaged_run01.nii.gz"
            averaged_run04 = f"{p_id}/analysis/susceptibility/fnirt_test/4/averaged_run04.nii.gz"
            if not os.path.exists(averaged_run01) or not os.path.exists(averaged_run04):
                subprocess.run(['fslmaths', run01, '-Tmean', averaged_run01])
                subprocess.run(['fslmaths', run04, '-Tmean', averaged_run04])
            
            # betted_run01 = f"{p_id}/analysis/susceptibility/fnirt_test/4/betted_run01.nii.gz"
            # betted_run04 = f"{p_id}/analysis/susceptibility/fnirt_test/4/betted_run04.nii.gz"
            # if not os.path.exists(betted_run01) or not os.path.exists(betted_run04):
            #     subprocess.run(["bet", averaged_run01, betted_run01, "-m", "-R"])
            #     subprocess.run(["bet", averaged_run04, betted_run04, "-m", "-R"])
            
            spm_bet_folder = os.path.join(os.getcwd(), p_id, "analysis", "susceptibility", "fnirt_test", "4", "spm_bet")
            os.makedirs(spm_bet_folder, exist_ok=True)
            structural_path = f"{p_id}/analysis/preproc/structural/structural.nii"
            structural_spm = f"{p_id}/analysis/susceptibility/fnirt_test/4/spm_bet/structural.nii"
            if not os.path.exists(structural_spm):
                shutil.copy(structural_path, structural_spm)
            structural_brain_spm = f"{p_id}/analysis/susceptibility/fnirt_test/4/spm_bet/structural_brain.nii.gz"
            if not os.path.exists(structural_brain_spm):
                subprocess.run(['/home/bsms1623/scripts_for_alex/spm_brain_extract', structural_spm])
            averaged_run01_spm = f"{p_id}/analysis/susceptibility/fnirt_test/4/spm_bet/averaged_run01.nii.gz"
            averaged_run04_spm = f"{p_id}/analysis/susceptibility/fnirt_test/4/spm_bet/averaged_run04.nii.gz"
            if not os.path.exists(averaged_run01_spm) or not os.path.exists(averaged_run04_spm):
                shutil.copy(averaged_run01, averaged_run01_spm)
                shutil.copy(averaged_run04, averaged_run04_spm)
            betted_run01_spm = f"{p_id}/analysis/susceptibility/fnirt_test/4/spm_bet/averaged_run01_brain.nii.gz"
            betted_run04_spm = f"{p_id}/analysis/susceptibility/fnirt_test/4/spm_bet/averaged_run04_brain.nii.gz"
            if not os.path.exists(betted_run01_spm) or not os.path.exists(betted_run04_spm):
                subprocess.run(['/home/bsms1623/scripts_for_alex/spm_brain_extract', averaged_run01_spm])
                subprocess.run(['/home/bsms1623/scripts_for_alex/spm_brain_extract', averaged_run04_spm])
            structural_brain_downsampled = f"{p_id}/data/neurofeedback/fnirt_4_structural_downsampled/structural_brain_downsampled.nii.gz"
            structural_downsampled = f"{p_id}/data/neurofeedback/fnirt_4_structural_downsampled/structural_downsampled.nii"
            flirted_run01 = f"{p_id}/analysis/susceptibility/fnirt_test/4/flirted_run01.nii.gz"
            flirted_run04 = f"{p_id}/analysis/susceptibility/fnirt_test/4/flirted_run04.nii.gz"
            flirted_run01_matrix = f"{p_id}/analysis/susceptibility/fnirt_test/4/flirted_run01_matrix.mat"
            flirted_run04_matrix = f"{p_id}/analysis/susceptibility/fnirt_test/4/flirted_run04_matrix.mat"
            if not os.path.exists(flirted_run01):
                subprocess.run(['flirt', '-in', betted_run01_spm, '-ref', structural_brain_downsampled, '-out', flirted_run01, '-omat', flirted_run01_matrix, '-dof', '6'])
                subprocess.run(['flirt', '-in', betted_run04_spm, '-ref', structural_brain_downsampled, '-out', flirted_run04, '-omat', flirted_run04_matrix, '-dof', '6'])
            nonlin_run01 = f"{p_id}/analysis/susceptibility/fnirt_test/4/nonlin_run01.nii.gz"
            nonlin_run04 = f"{p_id}/analysis/susceptibility/fnirt_test/4/nonlin_run04.nii.gz"
            warp_run01 = f"{p_id}/analysis/susceptibility/fnirt_test/4/warp_run01"
            warp_run04 = f"{p_id}/analysis/susceptibility/fnirt_test/4/warp_run04"
            if not os.path.exists(nonlin_run01):
                subprocess.run(['fnirt', f'--in={averaged_run01}', f'--ref={structural_downsampled}', f'--aff={flirted_run01_matrix}', f'--cout={warp_run01}'])
                subprocess.run(['fnirt', f'--in={averaged_run04}', f'--ref={structural_downsampled}', f'--aff={flirted_run04_matrix}', f'--cout={warp_run04}'])
            fnirted_run01 = f"{p_id}/analysis/susceptibility/fnirt_test/4/fnirted_run01.nii.gz"
            fnirted_run04 = f"{p_id}/analysis/susceptibility/fnirt_test/4/fnirted_run04.nii.gz"
            if not os.path.exists(fnirted_run01):
                subprocess.run(['applywarp', f'--in={averaged_run01}', f'--ref={structural_downsampled}', f'--warp={warp_run01}', f'--out={fnirted_run01}'])
                subprocess.run(['applywarp', f'--in={averaged_run04}', f'--ref={structural_downsampled}', f'--warp={warp_run04}', f'--out={fnirted_run04}'])
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
            roi_file_run01 = f"{p_id}/data/neurofeedback/{cisc_folder}/depression_neurofeedback/target_folder_run-1/depnf_run-1.roi"
            voxel_coordinates_run01 = read_roi_file(roi_file_run01)
            run01_template = f"{p_id}/analysis/susceptibility/fnirt_test/4/run01_template.nii.gz"
            if not os.path.exists(run01_template):
                run = f"{p_id}/analysis/preproc/niftis/run01_nh.nii.gz"
                subprocess.run(['fslmaths', run, '-Tmean', run01_template])
            functional_image_info = nib.load(run01_template)
            functional_dims = functional_image_info.shape
            binary_volume = np.zeros(functional_dims)
            for voxel in voxel_coordinates:
                x, y, z = voxel
                binary_volume[x, y, z] = 1
            binary_volume = np.flip(binary_volume, axis=1)
            functional_affine = functional_image_info.affine
            binary_mask = nib.Nifti1Image(binary_volume, affine=functional_affine)
            nib.save(binary_mask, f'{p_id}/analysis/susceptibility/fnirt_test/4/run01_subject_space_ROI.nii.gz')
            roi_mask_run01 = f'{p_id}/analysis/susceptibility/fnirt_test/4/run01_subject_space_ROI.nii.gz'
            fnirted_roi_run01 = f'{p_id}/analysis/susceptibility/fnirt_test/4/fnirted_roi_run01.nii.gz'
            if not os.path.exists(fnirted_roi_run01):
                subprocess.run(['applywarp', f'--in={roi_mask_run01}', f'--ref={structural_brain_downsampled}', f'--warp={warp_run01}', f'--out={fnirted_roi_run01}'], check=True)
            fnirted_roi_run01_bin = f'{p_id}/analysis/susceptibility/fnirt_test/4/fnirted_roi_run01_bin.nii.gz'
            if not os.path.exists(fnirted_roi_run01_bin):
                subprocess.run(['fslmaths', fnirted_roi_run01, '-thr', '0.5', '-bin', fnirted_roi_run01_bin])
            roi_file_run04 = f"{p_id}/data/neurofeedback/{cisc_folder}/depression_neurofeedback/target_folder_run-4/depnf_run-4.roi"
            voxel_coordinates_run04 = read_roi_file(roi_file_run04)
            run04_template = f"{p_id}/analysis/susceptibility/fnirt_test/4/run04_template.nii.gz"
            if not os.path.exists(run04_template):
                run = f"{p_id}/analysis/preproc/niftis/run04_nh.nii.gz"
                subprocess.run(['fslmaths', run, '-Tmean', run04_template])
            functional_image_info = nib.load(run04_template)
            functional_dims = functional_image_info.shape
            binary_volume = np.zeros(functional_dims)
            for voxel in voxel_coordinates:
                x, y, z = voxel
                binary_volume[x, y, z] = 1
            binary_volume = np.flip(binary_volume, axis=1)
            functional_affine = functional_image_info.affine
            binary_mask = nib.Nifti1Image(binary_volume, affine=functional_affine)
            nib.save(binary_mask, f'{p_id}/analysis/susceptibility/fnirt_test/4/run04_subject_space_ROI.nii.gz')
            roi_mask_run04 = f'{p_id}/analysis/susceptibility/fnirt_test/4/run04_subject_space_ROI.nii.gz'
            fnirted_roi_run04 = f'{p_id}/analysis/susceptibility/fnirt_test/4/fnirted_roi_run04.nii.gz'
            if not os.path.exists(fnirted_roi_run04):
                subprocess.run(['applywarp', f'--in={roi_mask_run04}', f'--ref={structural_brain_downsampled}', f'--warp={warp_run04}', f'--out={fnirted_roi_run04}'], check=True)
            fnirted_roi_run04_bin = f'{p_id}/analysis/susceptibility/fnirt_test/4/fnirted_roi_run04_bin.nii.gz'
            if not os.path.exists(fnirted_roi_run04_bin):
                subprocess.run(['fslmaths', fnirted_roi_run04, '-thr', '0.5', '-bin', fnirted_roi_run04_bin])
            fnirted_run01_bin = f'{p_id}/analysis/susceptibility/fnirt_test/4/fnirted_run01_bin.nii.gz'
            if not os.path.exists(fnirted_run01_bin):
                subprocess.run(['fslmaths', fnirted_run01, '-thr', '100', '-bin', fnirted_run01_bin])
            fnirted_run04_bin = os.path.join(f'{p_id}/analysis/susceptibility/fnirt_test/4/fnirted_run04_bin.nii.gz')
            if not os.path.exists(fnirted_run04_bin):
                subprocess.run(['fslmaths', fnirted_run04, '-thr', '100', '-bin', fnirted_run04_bin])
            run01_bin_inv = f'{p_id}/analysis/susceptibility/fnirt_test/4/run01_bin_inv.nii.gz'
            if not os.path.exists(run01_bin_inv):
                subprocess.run(['fslmaths', fnirted_run01_bin, '-sub', '1', '-abs', run01_bin_inv])
            run04_bin_inv = f'{p_id}/analysis/susceptibility/fnirt_test/4/run04_bin_inv.nii.gz'
            if not os.path.exists(run04_bin_inv):
                subprocess.run(['fslmaths', fnirted_run04_bin, '-sub', '1', '-abs', run04_bin_inv])
            run01_result = subprocess.run(['fslstats', fnirted_roi_run01_bin, '-k', run01_bin_inv, '-V'], capture_output=True, text=True)
            if run01_result.returncode == 0:
                run01_result_output = run01_result.stdout.strip()
            else:
                print("Error executing fslstats command.")
            run01_result_output_values = run01_result_output.split()
            run01_voxels_outside = float(run01_result_output_values[0])
            run04_result = subprocess.run(['fslstats', fnirted_roi_run04_bin, '-k', run04_bin_inv, '-V'], capture_output=True, text=True)
            if run04_result.returncode == 0:
                run04_result_output = run04_result.stdout.strip()
            else:
                print("Error executing fslstats command.")
            run04_result_output_values = run04_result_output.split()
            run04_voxels_outside = float(run04_result_output_values[0])
            result1 = subprocess.run(['fslstats', fnirted_roi_run01_bin, '-V'], capture_output=True, text=True)
            if result1.returncode == 0:
                result1_output = result1.stdout.strip()
            else:
                print("Error executing fslstats command.")
            result1_output_values = result1_output.split()
            total_voxels_in_roi_run01 = float(result1_output_values[0])
            result2 = subprocess.run(['fslstats', fnirted_roi_run04_bin, '-V'], capture_output=True, text=True)
            if result2.returncode == 0:
                result2_output = result2.stdout.strip()
            else:
                print("Error executing fslstats command.")
            result2_output_values = result2_output.split()
            total_voxels_in_roi_run04 = float(result2_output_values[0])
            perc_outside_run01 = (run01_voxels_outside / total_voxels_in_roi_run01) * 100
            perc_outside_run01 = round(perc_outside_run01, 2)
            perc_outside_run01_values.append(perc_outside_run01)
            perc_outside_run04 = (run04_voxels_outside / total_voxels_in_roi_run04) * 100
            perc_outside_run04 = round(perc_outside_run04, 2)
            perc_outside_run04_values.append(perc_outside_run04)
            perc_outside_df = pd.DataFrame({'p_id': [p_id], 'perc_outside_run01': [perc_outside_run01], 'perc_outside_run04': [perc_outside_run04]})
            perc_outside_df.to_csv(f'{p_id}/analysis/susceptibility/fnirt_test/4/perc_outside_df.txt', sep='\t', index=False)
            group_perc_outside_df = pd.concat([group_perc_outside_df, perc_outside_df], ignore_index=True)
            run01_trimmed_roi_mask = f"{p_id}/analysis/susceptibility/fnirt_test/4/run01_trimmed_roi_mask.nii.gz"
            run04_trimmed_roi_mask = f"{p_id}/analysis/susceptibility/fnirt_test/4/run04_trimmed_roi_mask.nii.gz"
            if not os.path.exists(run01_trimmed_roi_mask) or not os.path.exists(run04_trimmed_roi_mask):
                subprocess.run(['fslmaths', fnirted_roi_run01_bin, '-mul', fnirted_run01_bin, run01_trimmed_roi_mask])
                subprocess.run(['fslmaths', fnirted_roi_run04_bin, '-mul', fnirted_run04_bin, run04_trimmed_roi_mask])
    group_perc_outside_df.to_csv('group/susceptibility/fnirt_test/4/group_perc_outside_df.txt', sep='\t', index=False)
    plot_data = pd.DataFrame({
        'Participant': bad_participants * 2,
        'Perc_Outside': perc_outside_run01_values + perc_outside_run04_values,
        'Sequence': ['run01'] * len(bad_participants) + ['run04'] * len(bad_participants)
    })
    perc_outside_plot = (
        ggplot(plot_data, aes(x='Participant', y='Perc_Outside', fill='Sequence')) +
        geom_bar(stat='identity', position='dodge') +
        theme_classic() +
        labs(title='Percentage of Voxels in Signal Dropout Regions', x='Participant', y='Percentage of SCC Voxels in Signal Dropout') +
        theme(axis_text_x=element_text(rotation=45, hjust=1), text=element_text(size=12, color='black'), axis_title=element_text(size=12)) +
        scale_y_continuous(expand=(0, 0))
    )
    perc_outside_plot.save('group/susceptibility/fnirt_test/4/perc_outside_plot.png')
    perc_outside_run01_overall = np.mean(perc_outside_run01_values)
    perc_outside_run04_overall = np.mean(perc_outside_run04_values)
    run01_std_error = np.std(perc_outside_run01_values) / np.sqrt(len(perc_outside_run01_values))
    run04_std_error = np.std(perc_outside_run04_values) / np.sqrt(len(perc_outside_run04_values))
    _, perc_outside_run01_overall_shap_p = stats.shapiro(perc_outside_run01_values)
    _, perc_outside_run04_overall_shap_p = stats.shapiro(perc_outside_run04_values)
    if perc_outside_run01_overall_shap_p > 0.05 and perc_outside_run04_overall_shap_p > 0.05:
        print(f'Shapiro-Wilk test passed for perc_outside values. Running parametric t-test...')
        _, p_value = stats.ttest_ind(perc_outside_run01_values, perc_outside_run04_values)
        print(f"T-test p-value: {p_value}")
    else:
        print(f'Shapiro-Wilk test failed for perc_outside values. Running non-parametric Mann-Whitney U test...')
        _, p_value = stats.mannwhitneyu(perc_outside_run01_values, perc_outside_run04_values)
        print(f"Mann-Whitney U test p-value: {p_value}")
    plot_data = pd.DataFrame({'Sequence': ['run01', 'run04'], 'Perc_Outside': [perc_outside_run01_overall, perc_outside_run04_overall], 'Std_Error': [run01_std_error, run04_std_error]})
    group_perc_outside_plot = (ggplot(plot_data, aes(x='Sequence', y='Perc_Outside', fill='Sequence')) + 
                        geom_bar(stat='identity', position='dodge') +
                        geom_errorbar(aes(ymin='Perc_Outside - Std_Error', ymax='Perc_Outside + Std_Error'), width=0.2, color='black') +
                        theme_classic() +
                        labs(title='Percentage of Voxels in Signal Dropout Regions', y='Percentage of SCC Voxels in Signal Dropout') +
                        scale_y_continuous(expand=(0, 0)) +
                        scale_fill_manual(values={'PA': '#DB5F57', 'RL': '#57D3DB'})
                        )
    if p_value < 0.001:
        group_perc_outside_plot = group_perc_outside_plot + annotate("text", x=1.5, y=max(plot_data['Perc_Outside']) + 3.5, label="***", size=16, color="black") + \
            annotate("segment", x=1, xend=2, y=max(plot_data['Perc_Outside']) + 3, yend=max(plot_data['Perc_Outside']) + 3, color="black")
    elif p_value < 0.01:
        group_perc_outside_plot = group_perc_outside_plot + annotate("text", x=1.5, y=max(plot_data['Perc_Outside']) + 3.5, label="**", size=16, color="black") + \
            annotate("segment", x=1, xend=2, y=max(plot_data['Perc_Outside']) + 3, yend=max(plot_data['Perc_Outside']) + 3, color="black")
    elif p_value < 0.05:
        group_perc_outside_plot = group_perc_outside_plot + annotate("text", x=1.5, y=max(plot_data['Perc_Outside']) + 3.5, label="*", size=16, color="black") + \
            annotate("segment", x=1, xend=2, y=max(plot_data['Perc_Outside']) + 3, yend=max(plot_data['Perc_Outside']) + 3, color="black")    
    group_perc_outside_plot.save('group/susceptibility/fnirt_test/4/group_perc_outside_plot.png')
    
    column_headers = ['p_id', 'ssim_index', 'voxels_in_bin_ssim_mask', 'perc_roi_voxels_in_bin_ssim_mask']
    group_ssim_df = pd.DataFrame(columns = column_headers) 
    for p_id in participants_to_iterate:
        if p_id in bad_participants:
            print(f"Running Stage 4 SSIM analysis for {p_id}...")
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
                return ssim_index
            ssim_output_path = f"{p_id}/analysis/susceptibility/fnirt_test/4/ssim_map.nii.gz"
            fnirted_run01 = f"{p_id}/analysis/susceptibility/fnirt_test/4/fnirted_run01.nii.gz"
            fnirted_run04 = f"{p_id}/analysis/susceptibility/fnirt_test/4/fnirted_run04.nii.gz"
            if not os.path.exists(ssim_output_path):
                ssim_index = calculate_ssim(fnirted_run01, fnirted_run04, ssim_output_path)
            ssim_bin = f"{p_id}/analysis/susceptibility/fnirt_test/4/ssim_bin.nii.gz"
            if not os.path.exists(ssim_bin):
                subprocess.run(["fslmaths", ssim_output_path, "-thr", "0.8", "-binv", ssim_bin])
            combined_run01_run04_mask = f"{p_id}/analysis/susceptibility/fnirt_test/4/combined_run01_run04_mask.nii.gz"
            fnirted_run01_bin = f"{p_id}/analysis/susceptibility/fnirt_test/4/fnirted_run01_bin.nii.gz"
            fnirted_run04_bin = f"{p_id}/analysis/susceptibility/fnirt_test/4/fnirted_run04_bin.nii.gz"
            if not os.path.exists(combined_run01_run04_mask):
                subprocess.run(['fslmaths', fnirted_run01_bin, '-add', fnirted_run04_bin, combined_run01_run04_mask])
            bin_run01_run04_mask = f"{p_id}/analysis/susceptibility/fnirt_test/4/bin_run01_run04_mask.nii.gz"
            if not os.path.exists(bin_run01_run04_mask):
                subprocess.run(['fslmaths', combined_run01_run04_mask, '-bin', bin_run01_run04_mask])
            ssim_bin_trimmed = f"{p_id}/analysis/susceptibility/fnirt_test/4/ssim_bin_trimmed.nii.gz"
            if not os.path.exists(ssim_bin_trimmed):
                subprocess.run(['fslmaths', ssim_bin, '-mul', bin_run01_run04_mask, ssim_bin_trimmed])
            voxels_in_whole_mask = subprocess.run(["fslstats", ssim_bin_trimmed, "-V"], capture_output=True, text=True).stdout.split()[0]
            voxels_in_whole_mask = float(voxels_in_whole_mask)
            intersection_mask_path_run01 = f'{p_id}/analysis/susceptibility/fnirt_test/4/ssim_roi_intersect_run01.nii.gz'
            intersection_mask_path_run04 = f'{p_id}/analysis/susceptibility/fnirt_test/4/ssim_roi_intersect_run04.nii.gz'
            run01_trimmed_roi_mask = f"{p_id}/analysis/susceptibility/fnirt_test/4/run01_trimmed_roi_mask.nii.gz"
            run04_trimmed_roi_mask = f"{p_id}/analysis/susceptibility/fnirt_test/4/run04_trimmed_roi_mask.nii.gz"
            if not os.path.exists(intersection_mask_path_run01):
                subprocess.run(["fslmaths", ssim_bin_trimmed, "-mas", run01_trimmed_roi_mask, intersection_mask_path_run01])
                subprocess.run(["fslmaths", ssim_bin_trimmed, "-mas", run04_trimmed_roi_mask, intersection_mask_path_run04])
            voxels_in_roi_in_mask_run01 = subprocess.run(["fslstats", intersection_mask_path_run01, "-V"], capture_output=True, text=True).stdout.split()[0]
            voxels_in_roi_in_mask_run01 = float(voxels_in_roi_in_mask_run01)
            perc_roi_voxels_in_mask_run01 = (voxels_in_roi_in_mask_run01 / total_voxels_in_roi_run01) * 100
            voxels_in_roi_in_mask_run04 = subprocess.run(["fslstats", intersection_mask_path_run04, "-V"], capture_output=True, text=True).stdout.split()[0]
            voxels_in_roi_in_mask_run04 = float(voxels_in_roi_in_mask_run04)
            perc_roi_voxels_in_mask_run04 = (voxels_in_roi_in_mask_run04 / total_voxels_in_roi_run04) * 100
            perc_roi_voxels_in_mask_av = (perc_roi_voxels_in_mask_run01 + perc_roi_voxels_in_mask_run04) / 2
            ssim_df = pd.DataFrame({'p_id': [p_id], 'ssim_index': [ssim_index], 'voxels_in_bin_ssim_mask': [voxels_in_whole_mask], 'perc_roi_voxels_in_bin_ssim_mask': [perc_roi_voxels_in_mask_av]})
            ssim_df.to_csv(f'{p_id}/analysis/susceptibility/fnirt_test/4/ssim_df.txt', sep='\t', index=False)
            group_ssim_df = pd.concat([group_ssim_df, ssim_df], ignore_index=True)
    group_ssim_df.to_csv('group/susceptibility/fnirt_test/4/group_ssim_df.txt', sep='\t', index=False)
    ssim_indexes = group_ssim_df['ssim_index'].tolist()
    ssim_mean = np.mean(ssim_indexes)
    print(f"Mean SSIM index for Stage 4: {ssim_mean}")
    plot_data = pd.DataFrame({
        'Participant': bad_participants,
        'SSIM': ssim_indexes,
    })
    ssim_index_plot = (
        ggplot(plot_data, aes(x='Participant', y='SSIM')) +
        geom_bar(stat='identity', position='dodge') +
        geom_hline(yintercept=ssim_mean, linetype='dashed', color='red') +
        theme_classic() +
        labs(title='SSIM Indexes', x='Participant', y='SSIM') +
        theme(axis_text_x=element_text(rotation=45, hjust=1), text=element_text(size=12, color='blue'), axis_title=element_text(size=12, face='bold')) +
        scale_y_continuous(expand=(0, 0), limits=[0.8,1])
    )
    ssim_index_plot.save('group/susceptibility/fnirt_test/4/ssim_index_plot.png')
    voxels = group_ssim_df['voxels_in_bin_ssim_mask'].tolist()
    voxels_mean = np.mean(voxels)
    plot_data = pd.DataFrame({
        'Participant': bad_participants,
        'Voxels': voxels,
    })
    ssim_voxels_plot = (
        ggplot(plot_data, aes(x='Participant', y='Voxels')) +
        geom_bar(stat='identity', position='dodge') +
        geom_hline(yintercept=voxels_mean, linetype='dashed', color='red') +
        theme_classic() +
        labs(title='Number of Voxels in SSIM Mask', x='Participant', y='Voxels') +
        theme(axis_text_x=element_text(rotation=45, hjust=1), text=element_text(size=12, color='blue'), axis_title=element_text(size=12, face='bold')) +
        scale_y_continuous(expand=(0, 0))
    )
    ssim_voxels_plot.save('group/susceptibility/fnirt_test/4/ssim_voxels_plot.png')
    perc_voxels = group_ssim_df['perc_roi_voxels_in_bin_ssim_mask'].tolist()
    perc_voxels_mean = np.mean(perc_voxels)
    plot_data = pd.DataFrame({
        'Participant': bad_participants,
        'Perc_Voxels': perc_voxels,
    })
    ssim_perc_voxels_plot = (
        ggplot(plot_data, aes(x='Participant', y='Perc_Voxels')) +
        geom_bar(stat='identity', position='dodge') +
        geom_hline(yintercept=perc_voxels_mean, linetype='dashed', color='red') +
        theme_classic() +
        labs(title='Percentage of ROI Voxels in SSIM Mask', x='Participant', y='Percentage of SCC Voxels in SSIM Mask') +
        theme(axis_text_x=element_text(rotation=45, hjust=1), text=element_text(size=12, color='black'), axis_title=element_text(size=12)) +
        scale_y_continuous(expand=(0, 0))
    )
    ssim_perc_voxels_plot.save('group/susceptibility/fnirt_test/4/ssim_perc_voxels_plot.png')

    column_headers = ['p_id', 'sequence', 'value']
    group_voxel_intensity_df = pd.DataFrame(columns = column_headers)   
    for p_id in participants_to_iterate:
        if p_id in bad_participants:
            print(f'Running Stage 4 voxel signal intensity analysis for {p_id}...')
            def extract_voxel_intensities(epi_image_path, mask_image_path):
                epi_img = nib.load(epi_image_path)
                epi_data = epi_img.get_fdata()
                mask_img = nib.load(mask_image_path)
                mask_data = mask_img.get_fdata()
                mask_data = mask_data > 0
                roi_voxel_intensities = epi_data[mask_data]
                voxel_intensity_list = roi_voxel_intensities.tolist()
                return voxel_intensity_list
            fnirted_run01 = f"{p_id}/analysis/susceptibility/fnirt_test/4/fnirted_run01.nii.gz"
            fnirted_run04 = f"{p_id}/analysis/susceptibility/fnirt_test/4/fnirted_run04.nii.gz"
            run01_trimmed_roi_mask = f"{p_id}/analysis/susceptibility/fnirt_test/4/run01_trimmed_roi_mask.nii.gz"
            run04_trimmed_roi_mask = f"{p_id}/analysis/susceptibility/fnirt_test/4/run04_trimmed_roi_mask.nii.gz"
            run01_voxel_intensities = extract_voxel_intensities(fnirted_run01, run01_trimmed_roi_mask)
            run04_voxel_intensities = extract_voxel_intensities(fnirted_run04, run04_trimmed_roi_mask)
            values = run01_voxel_intensities + run04_voxel_intensities
            sequence = ['run01'] * len(run01_voxel_intensities) + ['run04'] * len(run04_voxel_intensities)
            subject = [f'{p_id}'] * len(run01_voxel_intensities) + [f'{p_id}'] * len(run04_voxel_intensities)
            voxel_intensity_df = pd.DataFrame({'p_id': subject, 'sequence': sequence, 'value': values})
            voxel_intensity_df.to_csv(f'{p_id}/analysis/susceptibility/fnirt_test/4/voxel_intensity_df.txt', sep='\t', index=False)
            group_voxel_intensity_df = pd.concat([group_voxel_intensity_df, voxel_intensity_df], ignore_index=True)
    group_voxel_intensity_df.to_csv('group/susceptibility/fnirt_test/4/group_voxel_intensity_df.txt', sep='\t', index=False)
    run01_means = []
    run04_means= []
    p_values = []
    run01_std_errors = []
    run04_std_errors = []
    for p_id in participants_to_iterate:
        if p_id in bad_participants:
            filtered_run01 = group_voxel_intensity_df[(group_voxel_intensity_df['p_id'] == f'{p_id}') & (group_voxel_intensity_df['sequence'] == 'run01')]
            mean_value_run01 = filtered_run01['value'].mean()
            run01_means.append(mean_value_run01)
            filtered_run04 = group_voxel_intensity_df[(group_voxel_intensity_df['p_id'] == f'{p_id}') & (group_voxel_intensity_df['sequence'] == 'run04')]
            mean_value_run04 = filtered_run04['value'].mean()
            run04_means.append(mean_value_run04)
            anderson_run01 = stats.anderson(filtered_run01['value'])
            anderson_run04 = stats.anderson(filtered_run04['value'])
            significance_level = 0.05
            is_run01_normal = anderson_run01.statistic < anderson_pa.critical_values[
                anderson_pa.significance_level.tolist().index(significance_level * 100)]
            is_run04_normal = anderson_run04.statistic < anderson_rl.critical_values[
                anderson_rl.significance_level.tolist().index(significance_level * 100)]
            if is_run01_normal and is_run04_normal:
                print(f'Anderson-Darling test passed for {p_id} voxel intensity values. Running parametric t-test...')
                _, p_value = stats.ttest_ind(filtered_run01['value'], filtered_run04['value'], equal_var=False)
                p_values.append(p_value)
            else:
                print(f'Anderson-Darling test failed for {p_id} voxel intensity values. Running non-parametric Mann Whitney U test...')
                _, p_value = stats.mannwhitneyu(filtered_run01['value'], filtered_run04['value'], alternative='two-sided')
                p_values.append(p_value)
            run01_std_error = np.std(filtered_run01['value']) / np.sqrt(len(filtered_run01['value']))
            run01_std_errors.append(run01_std_error)
            run04_std_error = np.std(filtered_run04['value']) / np.sqrt(len(filtered_run04['value']))
            run04_std_errors.append(run04_std_error)
    plot_data = pd.DataFrame({
        'Participant': bad_participants * 2,
        'Mean_Value': run01_means + run04_means,
        'Sequence': ['RUN01'] * len(bad_participants) + ['RUN04'] * len(bad_participants),
        'Significance': ['' for _ in range(len(bad_participants) * 2)],
        'Std_Error': run01_std_errors + run04_std_errors
    })
    for idx, p_value in enumerate(p_values):
        if p_value < 0.001:
            plot_data.at[idx, 'Significance'] = '***'
        elif p_value < 0.01:
            plot_data.at[idx, 'Significance'] = '**'
        elif p_value < 0.05:
            plot_data.at[idx, 'Significance'] = '*'
    voxel_intensity_plot = (
        ggplot(plot_data, aes(x='Participant', y='Mean_Value', fill='Sequence')) +
        geom_bar(stat='identity', position='dodge') +
        geom_errorbar(aes(ymin='Mean_Value - Std_Error', ymax='Mean_Value + Std_Error'), position=position_dodge(width=0.9), width=0.2, color='black') +
        theme_classic() +
        labs(title='Mean SCC Voxel Intensity', x='Participant', y='Mean SCC Signal Intensity') +
        theme(axis_text_x=element_text(rotation=45, hjust=1), text=element_text(size=12, color='black'), axis_title=element_text(size=12)) +
        scale_y_continuous(expand=(0, 0), limits=[0,350]) +
        geom_text(
            aes(x='Participant', y='Mean_Value', label='Significance'),
            position=position_dodge(width=0.9),
            color='black',
            size=12,
            ha='center',
            va='bottom',
            show_legend=False))
    voxel_intensity_plot.save('group/susceptibility/fnirt_test/4/voxel_intensity_plot.png')
    run01_means_overall = np.mean(run01_means)
    run04_means_overall = np.mean(run04_means)
    run01_std_error_overall = np.std(run01_means) / np.sqrt(len(run01_means))
    run04_std_error_overall = np.std(run04_means) / np.sqrt(len(run04_means))
    _, run01_means_overall_shap_p = stats.shapiro(run01_means)
    _, run04_means_overall_shap_p = stats.shapiro(run04_means)
    if run01_means_overall_shap_p > 0.05 and run04_means_overall_shap_p > 0.05:
        print(f'Shapiro-Wilk test passed for voxel intensity values. Running parametric t-test...')
        _, p_value = stats.ttest_rel(run01_means, run04_means)
        print(f"T-test p-value: {p_value}")
    else:
        print(f'Shapiro-Wilk test failed for voxel intensity values. Running non-parametric Wilcoxon test...')
        _, p_value = stats.wilcoxon(run01_means, run04_means)
        print(f"Wilcoxon test p-value: {p_value}")
    plot_data = pd.DataFrame({'p_id': bad_participants, 'run01_values': run01_means, 'run04_values': run04_means})
    data_long = pd.melt(plot_data, id_vars=['p_id'], value_vars=['run01_values', 'run04_values'], var_name='sequence', value_name='value')
    data_long['sequence'] = data_long['sequence'].map({'run01_values': 'RUN01', 'run04_values': 'RUN04'})
    group_voxel_intensity_ladder_plot = (
        ggplot(data_long, aes(x='sequence', y='value', group='p_id')) +
        geom_line(aes(group='p_id'), color='gray', size=1) +
        geom_point(aes(color='sequence'), size=4) +
        theme_light() +
        theme(
            panel_grid_major=element_blank(), 
            panel_grid_minor=element_blank(), 
            panel_border=element_blank(),
            axis_line_x=element_line(color='black'),  
            axis_line_y=element_line(color='black'),  
        ) +
        labs(title='Ladder Plot of FNIRTed RUN01 and RUN04 Sequences',
            x='Sequence',
            y='Mean SCC Signal Intensity') +
        scale_x_discrete(limits=['RUN01', 'RUN04']) +
        scale_y_continuous()
    )
    group_voxel_intensity_ladder_plot.save('group/susceptibility/fnirt_test/4/group_voxel_intensity_ladder_plot.png')
    plot_data = pd.DataFrame({'Sequence': ['RUN01', 'RUN04'], 'Mean': [run01_means_overall, run04_means_overall], 'Std_Error': [run01_std_error_overall, run04_std_error_overall]})
    group_voxel_intensity_plot = (ggplot(plot_data, aes(x='Sequence', y='Mean', fill='Sequence')) + 
                        geom_bar(stat='identity', position='dodge') +
                        geom_errorbar(aes(ymin='Mean - Std_Error', ymax='Mean + Std_Error'), width=0.2, color='black') +
                        theme_classic() +
                        labs(title='Mean of Voxel Intensities Across Participants', y='Mean SCC Signal Intensity') +
                        scale_y_continuous(expand=(0, 0), limits=[0,350]) +
                        scale_fill_manual(values={'PA': '#DB5F57', 'RL': '#57D3DB'})
                        )
    if p_value < 0.001:
        group_voxel_intensity_plot = group_voxel_intensity_plot + annotate("text", x=1.5, y=max(plot_data['Mean']) + 40, label="***", size=16, color="black") + \
            annotate("segment", x=1, xend=2, y=max(plot_data['Mean']) +30, yend=max(plot_data['Mean']) + 30, color="black")
    elif p_value < 0.01:
        group_voxel_intensity_plot = group_voxel_intensity_plot + annotate("text", x=1.5, y=max(plot_data['Mean']) + 40, label="**", size=16, color="black") + \
            annotate("segment", x=1, xend=2, y=max(plot_data['Mean']) +30, yend=max(plot_data['Mean']) + 30, color="black")
    elif p_value < 0.05:
        group_voxel_intensity_plot = group_voxel_intensity_plot + annotate("text", x=1.5, y=max(plot_data['Mean']) + 40, label="*", size=16, color="black") + \
            annotate("segment", x=1, xend=2, y=max(plot_data['Mean']) +30, yend=max(plot_data['Mean']) + 30, color="black")    
    group_voxel_intensity_plot.save('group/susceptibility/fnirt_test/4/group_voxel_intensity_plot.png')

#endregion