# -*- coding: utf-8 -*-
"""
Created on Fri May 19 14:51:12 2023

@author: freem
"""

import pyvisa
import re
import numpy as np
import matplotlib.pyplot as plt
import scipy as sc
from tqdm import tqdm
import csv
from datetime import datetime
from tkinter import Tk, filedialog

chunkSize = int(1E5)
channel = str(1)



def save_arrays_as_csv(time, timeData, freq, psdData):
    # Get current timestamp
    timestamp = datetime.now().strftime('%Y%m%d%H%M')

    # Open file dialog to choose save location
    root = Tk()
    root.withdraw()
    default_dir = '~/Documents'  # Default save location
    file_path = filedialog.asksaveasfilename(initialdir=default_dir, defaultextension=".csv",
                                             initialfile=f"{timestamp}_exp", filetypes=[("CSV Files", "*.csv")])
    root.destroy()

    # Write arrays to the CSV file
    with open(file_path, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['Time', 'Time Data', 'Frequency', 'PSD Data'])  # Write header
        for i in range(len(time)):
            writer.writerow([time[i], timeData[i], freq[i], psdData[i]])

    print(f"Arrays saved successfully to: {file_path}")

def plot_arrays(time, timeData, freq, psdData):
    xlim = [0, 6E2]
    ylim = []

    i_xlim = np.argmax(freq > 1E3)
    ylim.append(1E-1 * np.min(psdData[0:i_xlim]))
    ylim.append(1E1 * np.max(psdData[0:i_xlim]))

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 8))

    ax1.plot(time, timeData)
    ax1.set_title('Time Domain Signal')
    ax1.set_xlabel('time (s)')
    ax1.set_ylabel('voltage (V)')

    ax2.set_xlabel('Frequency (Hz)')
    ax2.set_ylabel(r'Position PSD $m/\sqrt{Hz}$')
    ax2.set_title('Power Spectral Density')
    ax2.set_xlim(xlim[0], xlim[1])
    ax2.set_ylim(ylim[0], ylim[1])
    ax2.semilogy(freq, psdData)

    # Adjust the spacing between subplots
    plt.subplots_adjust(hspace=0.4)

    plt.show()

def extract_number(string):
    pattern = r'[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?'
    match = re.search(pattern, string)
    if match:
        number_str = match.group()
        try:
            number = float(number_str)
            return number
        except ValueError:
            pass
    return None


rm = pyvisa.ResourceManager()
resources = rm.list_resources()
print("using: ", resources[0])
yk = rm.open_resource(resources[0]) #I'm a lazy fuck who only has one USB port

yk.write(':STOP')

yk.write(':WAVeform:TRACE ' + channel)

result = yk.query('WAVEFORM:RECord? MINimum')
minRecord = int(extract_number(result))

yk.write(':WAVeform:RECord '+ str(minRecord))

result = yk.query('WAVEFORM:RANGE?')
dV = extract_number(result)

result = yk.query('WAVEFORM:OFFSET?')
offset = extract_number(result)

result = yk.query('WAVEFORM:LENGth?')
length = int(extract_number(result))

result = yk.query('WAVEFORM:TRIGGER?')
trigpos = extract_number(result)

yk.write('WAVEFORM:FORMAT WORD')

result = yk.query('WAVEFORM:BITS?')
bitlength = extract_number(result)
bitlength = 0x10 if bitlength == 16 else 0x08

yk.write('WAVEFORM:BYTEORDER LSBFIRST')

yk.write(':WAVeform:FORMat WORD')

result = yk.query(':WAVeform:SRATe?') #Get sampling rate
print(result)
samplingRate = extract_number(result)

if length > chunkSize:
    print("Transferring...", end =" ")

dataTemp = np.empty(chunkSize + 1)
w = np.empty(length)
i = 0
n = int(np.floor(length / chunkSize))
m = 0
numtrans = 0

timeData = []

for i in tqdm(range(n + 1)):
    
    m = min(length, (i + 1) * chunkSize) - 1
    yk.write("WAVEFORM:START {};:WAVEFORM:END {}".format(i * chunkSize, m))
    
    buff = yk.query_binary_values('WAVEFORM:SEND?', datatype='h', container=list)
    
    timeData.extend(buff)
    
result = yk.query('WAVEFORM:OFFSET?')
offset = extract_number(result)

result = yk.query(':WAVeform:RANGe?')
wRange = extract_number(result)

yk.close()

timeData = wRange * np.array(timeData) * 10 / 24000 + offset #some random bullshit formula in the communication manual

timeData = 9.81 / 10 * timeData #/100
time = np.array(range(len(timeData))) / samplingRate

freq, psdAcc = sc.signal.welch(timeData, fs = samplingRate, nperseg = samplingRate, window = 'blackman', noverlap = 0)
freq = freq[1:-1]
psdAcc = psdAcc[1:-1]
psdPos = psdAcc / freq**2
psdData = psdPos

plot_arrays(time, timeData, freq, psdData)
save_arrays_as_csv(time, timeData, freq, psdData)



