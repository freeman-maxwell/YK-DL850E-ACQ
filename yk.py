import pyvisa
import re
import numpy as np
import matplotlib.pyplot as plt
import scipy as sc
from tqdm import tqdm
from tkinter import messagebox
from io import StringIO
import csv
import pandas as pd

chunkSize = int(1E5)
channel = str(1)


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

def dict_to_csv_string(data):
    # Create a StringIO object to store the CSV data
    csv_string = StringIO()

    # Create a CSV writer
    writer = csv.writer(csv_string)

    # Write the header row
    header = list(data.keys())
    writer.writerow(header)

    # Find the maximum length of any array in the dictionary
    max_length = max(len(arr) for arr in data.values())

    # Write the data rows
    for i in range(max_length):
        row = [data[key][i] if i < len(data[key]) else '' for key in header]
        writer.writerow(row)

    return csv_string.getvalue()


def get_devices():
    try:
        rm = pyvisa.ResourceManager()
        resources = rm.list_resources()
        return resources
    except:
        return ['No devices found!']


class acq:
    def __init__(self):
        self.prog = 0
        self.data = {
            't': np.array([]),
            't_volt': np.array([]),
            't_acc': np.array([]),
            'f': np.array([]),
            'psd_acc': np.array([]),
            'psd_pos': np.array([])
        }

    def get_progress(self):
        return self.prog

    def run(self, instr):
        flag = True

        try:
            rm = pyvisa.ResourceManager()
            yk = rm.open_resource(str(instr))
        except:
            flag = False
            messagebox.showerror("Error", "Instrument not found!")

        if flag:
            try:
                yk.write(':STOP')

                yk.write(':WAVeform:TRACE ' + channel)

                result = yk.query('WAVEFORM:RECord? MINimum')
                minRecord = int(extract_number(result))

                yk.write(':WAVeform:RECord ' + str(minRecord))

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

                result = yk.query(':WAVeform:SRATe?')  # Get sampling rate
                sampling_rate = extract_number(result)
            except:
                flag = False
                messagebox.showerror("Error", "Some bullshit happened!")

        if flag:
            if length > chunkSize:
                print("Transferring...", end=" ")

            n = int(np.floor(length / chunkSize))
            t_data = []

            for i in tqdm(range(n + 1)):
                m = min(length, (i + 1) * chunkSize) - 1

                yk.write("WAVEFORM:START {};:WAVEFORM:END {}".format(i * chunkSize, m))
                buff = yk.query_binary_values('WAVEFORM:SEND?', datatype='h', container=list)

                t_data.extend(buff)
                self.prog = (i + 1) / (n + 1)

            result = yk.query('WAVEFORM:OFFSET?')
            offset = extract_number(result)

            result = yk.query(':WAVeform:RANGe?')
            w_range = extract_number(result)

            yk.close()

            t_data = w_range * np.array(
                t_data) * 10 / 24000 + offset  # some random bullshit formula in the communication manual
            self.data['t_volt'] = t_data
            self.data['t_acc'] = 9.81 / 10 * t_data  # /100
            self.data['t'] = np.arange(len(t_data)) / sampling_rate

            freq, psd_acc = sc.signal.welch(self.data['t_acc'],
                                            fs=sampling_rate,
                                            nperseg=sampling_rate,
                                            window='blackman',
                                            noverlap=0
                                            )
            freq = freq[1:-1]
            psd_acc = psd_acc[1:-1]

            self.data['f'] = freq
            self.data['psd_acc'] = psd_acc
            self.data['psd_pos'] = psd_acc / freq ** 2

    def plot(self):
        xlim = [0, 6E2]
        ylim = []

        t = self.data['t']
        t_data = self.data['t_volt']
        f = self.data['f']
        psd_data = self.data['psd_pos']

        i_xlim = np.argmax(f > 1E3)
        ylim.append(1E-1 * np.min(psd_data[0:i_xlim]))
        ylim.append(1E1 * np.max(psd_data[0:i_xlim]))

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 8))

        ax1.plot(t, t_data)
        ax1.set_title('Time Domain Signal')
        ax1.set_xlabel('time (s)')
        ax1.set_ylabel('Voltage (V)')

        ax2.set_xlabel('Frequency (Hz)')
        ax2.set_ylabel(r'Position PSD ($m/\sqrt{Hz}$)')
        ax2.set_title('Power Spectral Density')
        ax2.set_xlim(xlim[0], xlim[1])
        ax2.set_ylim(ylim[0], ylim[1])
        ax2.semilogy(f, psd_data)

        # Adjust the spacing between subplots
        plt.subplots_adjust(hspace=0.4)

        return fig

    def get_data(self):
        return dict_to_csv_string(self.data)


