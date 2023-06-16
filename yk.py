import pyvisa
import re
import numpy as np
import matplotlib.pyplot as plt
import matplotlib
from plotly.subplots import make_subplots
import plotly.graph_objects as go
import scipy as sc
from tqdm import tqdm
from tkinter import messagebox
from io import StringIO
import csv
import pandas as pd

matplotlib.use('agg')
matplotlib.rcParams['agg.path.chunksize'] = 10000

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

def get_devices():
    try:
        rm = pyvisa.ResourceManager()
        resources = rm.list_resources()
        return resources
    except:
        return ['No devices found!']


class acq:
    def __init__(self):
        self.prog = {}
        self.chunkSize = int(1E5)
        self.channels = [1]
        self.channel_data = {}
        self.xy_mode = None

    def run(self, instr):

        flag = True
        self.channel_data = {}
        self.prog = {
            'iteration': 1,
            'prog': 0
        }
        for channel in self.channels:
            self.channel_data[channel] = None

        try:
            rm = pyvisa.ResourceManager()
            yk = rm.open_resource(str(instr))
        except:
            flag = False

        yk.write(':STOP')
        #self.xy_mode = extract_number(yk.query(':XY:WINDOW1:MODE?'))
        yk.write(':WAVEFORM:FORMAT WORD')
        yk.write(':WAVEFORM:BYTEORDER LSBFIRST')
        yk.write(':WAVeform:FORMat WORD')

        for channel in self.channels:
            if flag:
                try:
                    yk.write(':WAVeform:TRACE ' + str(channel))
                    result = yk.query('WAVEFORM:RECord? MINimum')
                    min_record = int(extract_number(result))
                    yk.write(':WAVeform:RECord ' + str(min_record))
                    result = yk.query(':WAVEFORM:LENGth?')
                    length = int(extract_number(result))
                    result = yk.query(':WAVeform:SRATe?')  # Get sampling rate
                    sampling_rate = extract_number(result)
                except:
                    flag = False

            if flag:
                try:
                    data = {}

                    n = int(np.floor(length / self.chunkSize))
                    t_data = []

                    for i in tqdm(range(n + 1)):
                        m = min(length, (i + 1) * self.chunkSize) - 1

                        yk.write(":WAVEFORM:START {};:WAVEFORM:END {}".format(i * self.chunkSize, m))
                        buff = yk.query_binary_values(':WAVEFORM:SEND?', datatype='h', container=list)

                        t_data.extend(buff)
                        self.prog['prog'] = (i + 1) / (n + 1)

                    result = yk.query(':WAVEFORM:OFFSET?')
                    offset = extract_number(result)

                    result = yk.query(':WAVeform:RANGe?')
                    w_range = extract_number(result)

                    t_data = w_range * np.array(
                        t_data) * 10 / 24000 + offset  # some random bullshit formula in the communication manual
                    data['t_volt'] = t_data
                    data['t'] = np.arange(len(t_data)) / sampling_rate

                    if self.xy_mode != 1:
                        data['t_acc'] = 9.81 / 10 * t_data  # /100
                        freq, psd_acc = sc.signal.welch(data['t_acc'],
                                                        fs=sampling_rate,
                                                        nperseg=sampling_rate,
                                                        window='blackman',
                                                        noverlap=0
                                                        )
                        freq = freq[1:-1]
                        psd_acc = psd_acc[1:-1]

                        data['f'] = freq
                        data['psd_acc'] = psd_acc
                        data['psd_pos'] = psd_acc / freq ** 2
                    self.channel_data[channel] = data
                except:
                    flag = False
            self.prog['iteration'] += 1
            print('Channel completed')
        yk.close()

    def plot(self):
        if self.xy_mode == 1:
            x = -7.766 * np.array(self.channel_data[1]['t_volt'])
            x = x - np.min(x)
            self.channel_data[1]['t_volt'] = x
            y = 4.108 * (np.array(self.channel_data[3]['t_volt']) - 4.547)
            self.channel_data[3]['t_volt'] = y

            fig, ax = plt.subplots()
            ax.plot(x, y)
            ax.set_title('Force vs Distance')
            ax.set_xlabel('Distance (mm)')
            ax.set_ylabel('Force (N)')

        else:
            fig, axes = plt.subplots(2 * len(self.channels), 1, figsize=(8, 8 * len(self.channels)))
            plt.subplots_adjust(hspace=0.4)

            for i, (key, data) in enumerate(self.channel_data.items()):
                i = 2 * i
                ax = axes[i]
                t = data['t']
                t_data = data['t_volt']
                ax.plot(t, t_data)
                ax.set_title('Time Domain Signal, Channel ' + str(key))
                ax.set_xlabel('time (s)')
                ax.set_ylabel('Voltage (V)')

                print(i + 1)
                ax = axes[i + 1]

                x_lim = [0, 6E2]
                y_lim = []
                f = data['f']
                psd_data = data['psd_pos']

                i_xlim = np.argmax(f > 1E3)
                y_lim.append(1E-1 * np.min(psd_data[0:i_xlim]))
                y_lim.append(1E1 * np.max(psd_data[0:i_xlim]))

                ax.set_xlabel('Frequency (Hz)')
                ax.set_ylabel(r'Position PSD ($m/\sqrt{Hz}$)')
                ax.set_title('Power Spectral Density, Channel ' + str(key))
                ax.set_xlim(x_lim[0], x_lim[1])
                ax.set_ylim(y_lim[0], y_lim[1])
                ax.semilogy(f, psd_data)
        return fig

    def get_data(self):
        csv_string = ""

        # Extract all unique keys from the nested dictionaries
        nested_keys = set()
        for channel_dict in self.channel_data.values():
            if channel_dict is not None:
                nested_keys.update(channel_dict.keys())
        nested_keys = list(nested_keys)
        nested_keys.reverse()

        # Write the header row
        headers = [f'C{channel} {key}' for channel in self.channel_data.keys() for key in nested_keys]
        csv_string += ','.join(headers) + '\n'

        # Write the data rows
        max_data_length = max([len(channel_dict[key]) for channel_dict in self.channel_data.values() for key in nested_keys])
        for i in range(max_data_length):
            row = []
            for channel in self.channel_data.keys():
                channel_dict = self.channel_data[channel]
                for key in nested_keys:
                    channel_data_array = channel_dict.get(key, np.array([]))
                    data = channel_data_array[i] if i < len(channel_data_array) else np.nan
                    row.append(data)
            csv_string += ','.join([str(value) for value in row]) + '\n'

        return csv_string


