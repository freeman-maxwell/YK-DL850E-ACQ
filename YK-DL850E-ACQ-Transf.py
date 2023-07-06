# -*- coding: utf-8 -*-
"""
Created on Fri May 19 14:51:12 2023

@author: freem
"""

import pyvisa
import re
import numpy as np
import matplotlib.pyplot as plt
import matplotlib
import scipy as sc
from tqdm import tqdm
import csv
from datetime import datetime
from tkinter import Tk, filedialog
import time as pytime
import pint

matplotlib.rcParams.update({'font.size': 8})

chunkSize = int(1E5)
channel = str(1)

plotType = ['resonance'] #'resonance', 'timeandfreq'

ureg = pint.UnitRegistry()

def damping_func(t, A, l, w, p):
    return A * np.exp(-1 * l * t) * np.cos(w * t - p)


def save_arrays_as_csv(arr_time, timeData, freq, psdData):
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
        for i in range(len(arr_time)):
            writer.writerow([arr_time[i], timeData[i], freq[i], psdData[i]])

    print(f"Arrays saved successfully to: {file_path}")

def plot_arrays(arr_time, timeData, freq, psdData):
    if 'resonance' in plotType:
        x = arr_time
        y = timeData

        popt, pcov = sc.optimize.curve_fit(damping_func, x, y)
        [A, l, w, p] = popt
        zeta = l / np.sqrt(l ** 2 + w ** 2)
        delta = 2 * 3.1416 * zeta / np.sqrt(1 - zeta ** 2)
        f = w / (2 * 3.1416)
        plt.plot(x, y)
        plt.plot(x, damping_func(x, A, l, w, p))
        titlestring = 'Resonance Measurement of QZS Flexure Component\n'
        #titlestring += r'$y = A \exp{-\lambda t} \cos{(\omega t - \varphi})$' + '\n'
        titlestring += rf'$A = {A:.2e}$' ', ' \
                       rf'$\lambda = {l:.2e}$' ', ' \
                       rf'$\omega = {w:.2e}$' ', ' \
                       rf'$\varphi = {p:.2e}$' '\n' \
                       rf'$f_n = {f:.2e}$' ', ' ', ' \
                       rf'$\delta = {delta:.2e}$'
        plt.title(titlestring)
        plt.xlabel('Time (s)')
        plt.ylabel('Acceleration ($m/s^2$)')
        plt.legend(['data', 'fit'])
        plt.show()

    if 'timeandfreq' in plotType:
        xlim = [0, 6E2]
        ylim = []

        i_xlim = np.argmax(freq > 1E3)
        ylim.append(1E-1 * np.min(psdData[0:i_xlim]))
        ylim.append(1E1 * np.max(psdData[0:i_xlim]))

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 8))

        ax1.plot(arr_time, timeData)
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

def convert_to_seconds(time_string):
    try:
        int_time = ureg(time_string)
        return int_time.to('second').magnitude
    except pint.errors.UndefinedUnitError:
        raise ValueError('Invalid unit')
    except pint.errors.DimensionalityError:
        raise ValueError('Invalid time string')

def initialize_instruments():
    rm = pyvisa.ResourceManager()
    resources = rm.list_resources()
    if 'USB0::0x0B21::0x003F::39314B373135373833::INSTR' in resources:
        yk = rm.open_resource('USB0::0x0B21::0x003F::39314B373135373833::INSTR')

yk.write(':STOP')

arr_time = []
timeData2=[]
timeData=[]
freq=[]
psdData=[]

def find_peak(time_div, samplerate, freq_of_interest, range_width):
    yk.write(':TIMebase:TDIV ' + '1s')
    yk.write(':TIMebase:SRATE ' + samplerate)
    yk.write(':TIMebase:TDIV ' + time_div)
    yk.write(':START')

    pytime.sleep(11 * convert_to_seconds(time_div))

    yk.write(':STOP')

    yk.write(':WAVeform:TRACE ' + channel)

    result = yk.query('WAVEFORM:RECord? MINimum')
    minRecord = int(extract_number(result))

    yk.write(':WAVeform:RECord ' + str(minRecord))

    result = yk.query('WAVEFORM:LENGth?')
    length = int(extract_number(result))

    yk.write('WAVEFORM:BYTEORDER LSBFIRST')

    yk.write(':WAVeform:FORMat WORD')

    result = yk.query(':WAVeform:SRATe?')  # Get sampling rate
    print(result)
    samplingRate = extract_number(result)

    if length > chunkSize:
        print("Transferring...", end=" ")

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


    timeData = wRange * np.array(
        timeData) * 10 / 24000 + offset  # some random bullshit formula in the communication manual

    timeData2 = 9.81 / 10 * timeData / 100
    time = np.array(range(len(timeData2))) / samplingRate

    freq, psdAcc = sc.signal.periodogram(timeData2,
                                         fs=samplingRate
                                         )
    freq = freq[1:-1]
    psdAcc = psdAcc[1:-1]
    psdPos = psdAcc / freq ** 2
    psdData = psdPos

    # Find the indices of the frequencies within the range of interest
    indices = np.where((freq >= freq_of_interest - range_width / 2) & (freq <= freq_of_interest + range_width / 2))

    # Extract the corresponding values from psdData
    psdData_range = psdData[indices]

    # Find the maximum value within the range
    max_value = np.max(psdData_range)

    return max_value

avg_arr = []
for i in range(3):


    '''
    print('iteration ' + str(i))
    x = find_peak('2s', '10kHz', 400, 1)
    print(x)
    avg_arr.append(x)
    '''

print('Done!')
print(np.mean(avg_arr))

