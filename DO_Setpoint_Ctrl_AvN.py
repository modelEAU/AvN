# -*- coding: utf-8 -*-
"""
Created on Mon Aug  5 14:00:58 2019

@author: NINIC2
"""

# -*- coding: utf-8 -*-
"""
Created on Tue Jul 30 16:23:40 2019

@author: NINIC2
"""

import datetime
import pandas as pd
import numpy as np
import os

from connectDatEUAbase import *

#%%  PC CHECK
#Determine on which PC the script is running
PC_name = os.environ['COMPUTERNAME']

if PC_name == 'MODELEAU':
    #Define in which folder the intermediate data is stored
    path_intermData = 'C:/Users/Admin/Documents/Python Scripts/AvN Control/Data/'
    #Define in which folder the final control action is stored
    path_ctrlAction = 'D:/DataReadFile/'
elif PC_name == 'GCI-MODELEAU-08':
    #Define in which folder the intermediate data is stored
    path_intermData = 'C:/Users/NINIC2/Documents/Python Scripts/'
    #Define in which folder the final control action is stored
    path_ctrlAction = 'C:/Users/NINIC2/Documents/Python Scripts/'
else:
    print('Add directories to PATH')
    exit()

#%%  GET DATA FROM datEAUbase
#Initialise connection with the datEAUbase
cursor, conn = create_connection()

#Get measurement data over a specific interval
intrvl = 3 #minutes
delay = 2 #minutes
stopDateTime = datetime.datetime.now() - datetime.timedelta(hours=0, minutes=delay, seconds=0)
startDateTime = stopDateTime - datetime.timedelta(hours=0, minutes=intrvl, seconds=0)
Start = date_to_epoch(startDateTime.strftime("%Y-%m-%d %H:%M:%S"))
End = date_to_epoch(stopDateTime.strftime("%Y-%m-%d %H:%M:%S"))

#Define the requested parameters
Location = 'Copilote effluent'
Project = 'pilEAUte'
param_list = ['NH4-N','NO3-N']
equip_list = ['Varion_001','Varion_001']

#Extract the specified parameters from the datEAUbase
extract_list={}
for i in range(len(param_list)):
    extract_list[i] = {
        'Start':Start,
        'End':End,
        'Project':Project,
        'Location':Location,
        'Parameter':param_list[i],
        'Equipment':equip_list[i]
    }
    
#Create a new pandas dataframe
#print('ready to extract')
df = extract_data(conn, extract_list)
df.columns = param_list
df = df*1000 #set the units correctly to mg/L

#Replace all zero values for NaNs
df = df.replace(0.0, np.nan)

#%%  GET INTERMEDIATE DATA STORED LOCALLY
#Try to get previous control values saved in an existing txt file
try:    
    stored_vals = pd.read_csv(path_intermData+'intermDataAvNCtrl.csv', sep=',')
    stored_vals.set_index('datetime', drop=True, inplace=True)
    DOsp_1  = stored_vals['DOsp_1'].iloc[-1]
    error_1 = stored_vals['error_1'].iloc[-1]
    error_2 = stored_vals['error_2'].iloc[-1]
    NH4_1 = stored_vals['NH4_1'].iloc[-1]
    NO3_1 = stored_vals['NO3_1'].iloc[-1]
    P = stored_vals['P'].iloc[-1]
    I = stored_vals['I'].iloc[-1]
    D = stored_vals['D'].iloc[-1]

    #Prevent errors when database read communication results in NaN
    i = 2
    if np.isnan(DOsp_1) or np.isnan(error_1):
           DOsp_1  = stored_vals['DOsp_1'].iloc[-i]
           error_1 = stored_vals['error_1'].iloc[-i]
           error_2 = stored_vals['error_2'].iloc[-i]
           NH4_1 = stored_vals['NH4_1'].iloc[-i]
           NO3_1 = stored_vals['NO3_1'].iloc[-i]
           P = stored_vals['P'].iloc[-i]
           I = stored_vals['I'].iloc[-i]
           D = stored_vals['D'].iloc[-i]

#Catch error if file is not existing              
except FileNotFoundError as e:
    DOsp_1 = 0.1
    error_1 = 0
    error_2 = 0
    NH4_1 = 0
    NO3_1 = 0
    stored_vals = pd.DataFrame(
        data={
            'datetime':[datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
            'DOsp_1':[DOsp_1],
            'error_1':[error_1],
            'error_2':[error_2],
            'NH4_1':[NH4_1],
            'NO3_1':[NO3_1],
            'P':[0],
            'I':[0],
            'D':[0],
            }
        )
    stored_vals.set_index('datetime', inplace=True)
    with open(path_intermData+'intermDataAvNCtrl.csv', 'a') as f:
        stored_vals.to_csv(f, header=True)

#%%  FILTER DATA
#Filter the data to get a representative value for control action calculation
Fs = 6 #sample frequency in samples per minute
Nfltr = 1*Fs #filter length in minutes

NH4 = df['NH4-N'].iloc[-Nfltr:].mean()
NO3 = df['NO3-N'].iloc[-Nfltr:].mean()

#%%  PID CONTROL
#PID control action calculation using filtered value
error_mode = "diff" #Determines the way the AvN error is calculated: "ratio" or "diff"
operating_mode = "auto" #Determines the operating mode of the controller: "man" or "auto"

Ts = 1.0 #Sampling period
alpha = 1.0 
beta = 0.0

P = 0.1#0.02
I = 0.0025#0.0005
D = 0.1

c0 = P + (I*Ts + D/Ts)
c1 = -(P + 2*D/Ts)
c2 = D/Ts

if error_mode == "ratio":
    error = NH4/(alpha*NO3)- beta - 1 #ratio should be equal to 1, therefore subtract by 1
else:
    error = NH4 - (alpha*NO3) - beta #difference
  
DOsp = DOsp_1 + (error*c0 + error_1*c1 + error_2*c2) #note the negative gain of the process

#Clipping of the control action according to the physical limiations system
DOsp_min = 0.05 #s
DOsp_max = 0.5
DOsp = np.clip(DOsp, a_min=DOsp_min, a_max=DOsp_max)

DOsp_man = 0.1 #Manual mode setpoint
if operating_mode == "auto":
    DOsp = DOsp
else:
    DOsp = DOsp_man
	
if np.isnan(DOsp): #If for some reason the calculated value is NaN
    DOsp = DOsp_1

#%% APPLY SETPOINT
#Overwrite CSV file DO setpoints continuous DO control
write_delay = 61
write_time = datetime.datetime.now() + datetime.timedelta(seconds=write_delay)

write_time_red1 = datetime.datetime.now() + datetime.timedelta(seconds=15)
write_time_red2 = datetime.datetime.now() + datetime.timedelta(seconds=30)
write_time_red3 = datetime.datetime.now() + datetime.timedelta(seconds=45)

new_DOsp = pd.DataFrame(
    data={
        'date':[datetime.datetime.now().strftime("%Y.%m.%d"),datetime.datetime.now().strftime("%Y.%m.%d"),datetime.datetime.now().strftime("%Y.%m.%d"),datetime.datetime.now().strftime("%Y.%m.%d")], 
        'hour':[write_time.strftime("%H:%M:%S"),write_time_red1.strftime("%H:%M:%S"),write_time_red2.strftime("%H:%M:%S"),write_time_red3.strftime("%H:%M:%S")],
        'DOsp':[round(DOsp,2),round(DOsp,2),round(DOsp,2),round(DOsp,2)],
        }
    )

with open(path_ctrlAction+'AIC_341_Data.csv', 'a', newline='') as f:
    new_DOsp.to_csv(f, index=False, header=False)

#%% STORE INTERMEDIATE DATA LOCALLY
#Store control values
new_vals = pd.DataFrame(
    data={
        'datetime':[datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
        'DOsp_1':[round(DOsp,4)],
        'error_1':[round(error,4)],
        'error_2':[round(error_1,4)],
        'NH4_1':[round(NH4,4)],
        'NO3_1':[round(NO3,4)],
        'P':[P],
        'I':[I],
        'D':[D],
        }
    )
new_vals.set_index('datetime', drop=True, inplace=True)    

with open(path_intermData+'intermDataAvNCtrl.csv', 'a', newline='') as f:
    new_vals.to_csv(f, header=False)
    