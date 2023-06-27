import pyvisa
import re
import numpy as np
import math
import plotly.graph_objects as go
import scipy as sc
from tqdm import tqdm

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


def average_reduce(array, factor):
    if isinstance(array, np.ndarray):
        array = array.tolist()  # Convert NumPy array to Python list

    reduced_array = []
    i = 0
    while i < len(array):
        chunk = array[i:i + factor]
        if chunk:
            average = sum(chunk) / len(chunk)
            reduced_array.append(average)
        i += factor
    return reduced_array


def damping_func(t, A, l, w, p):
    return A * np.exp(-1 * l * t) * np.cos(w * t - p)


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
        self.mode = ['time domain']
        self.amp_gain = 1

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

                    if 'time domain' or 'X vs Y' or 'resonance' in self.mode:
                        data['t_volt'] = t_data
                        if 'time domain' or 'resonance' in self.mode:
                            data['t'] = np.arange(len(t_data)) / sampling_rate

                    if 'frequency domain' or 'resonance' in self.mode:
                        data['t_acc'] = (9.81 / 10) * t_data / self.amp_gain
                        if 'frequency domain' in self.mode:
                            freq, psd_acc = sc.signal.periodogram(data['t_acc'], fs=sampling_rate)
                                # sc.signal.welch(data['t_acc'],fs=sampling_rate,nperseg=sampling_rate,window='blackman',noverlap=0)
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
        figs = []
        if 'time domain' in self.mode:
            for i, (key, data) in enumerate(self.channel_data.items()):
                # Time Domain Plot
                t = data['t']
                t_data = data['t_volt']
                fig = go.Figure(data=go.Scatter(
                    x=t,
                    y=t_data,
                    mode='lines'))
                fig.update_layout(
                    title_text='Time Domain Signal, Channel ' + str(key),
                    xaxis_title='Time (s)',
                    yaxis_title='Voltage (V)')
                figs.append(fig)

        if 'frequency domain' in self.mode:
            for i, (key, data) in enumerate(self.channel_data.items()):
                # Frequency Domain Plot
                f = data['f']
                psd_data = data['psd_pos']

                x_lim = [0, 6E2]
                y_lim = []
                i_xlim = np.argmax(f > 1E3)
                y_lim.append(1E-1 * np.min(psd_data[0:i_xlim]))
                y_lim.append(1E1 * np.max(psd_data[0:i_xlim]))
                log_y_lim = [math.log10(bound) for bound in y_lim]

                fig = go.Figure(data=go.Scatter(
                    x=f,
                    y=psd_data,
                    mode='lines'))
                fig.update_layout(
                    title='Frequency Domain Signal, Channel ' + str(key),
                    xaxis_title='Frequency (Hz)',
                    yaxis_title='Position PSD (m/√Hz)',
                    xaxis_range=x_lim,
                    yaxis_range=log_y_lim
                )
                fig.update_yaxes(type="log")
                figs.append(fig)

        if 'resonance' in self.mode:
            for i, (key, data) in enumerate(self.channel_data.items()):
                # Time Domain Plot
                t = data['t']
                t_data = data['t_acc']
                popt, pcov = sc.optimize.curve_fit(damping_func, t, t_data)
                [A, l, w, p] = popt
                zeta = l / np.sqrt(l ** 2 + w ** 2)
                delta = 2 * 3.1416 * zeta / np.sqrt(1 - zeta ** 2)
                t_fit = damping_func(t, A, l, w, p)
                data_trace = go.Scatter(
                    x=t,
                    y=t_data,
                    mode='lines')
                fit_trace = go.Scatter(
                    x=t,
                    y=t_fit,
                    mode='lines')
                fig = go.Figure(data=[data_trace, fit_trace])
                titlestring = 'Resonance Measurement of QZS Flexure Component, Channel ' + str(key) + '<br>'
                titlestring += r'fit to $y = A \exp{-\lambda t} \cos{\omega t - \varphi}$' + '<br>'
                titlestring += r"$A = ${:.5g}, $\lambda = ${:.5g}, $\omega = ${:.5g}, $\varphi = ${:.5g}, $\delta = ${:.5g}".format(A, l, w, p, delta)
                fig.update_layout(
                    title_text=titlestring,
                    xaxis_title='Time (s)',
                    yaxis_title='Acceleration (m/s^2)')
                figs.append(fig)

        if 'X vs Y' in self.mode:
            x = -7.766 * np.array(self.channel_data[self.channels[0]]['t_volt'])
            x = x - np.min(x)
            self.channel_data[self.channels[0]]['distance (mm)'] = x
            self.channel_data[self.channels[0]]['force (N)'] = []
            y = 4.108 * (np.array(self.channel_data[self.channels[1]]['t_volt']) - 4.547)
            self.channel_data[self.channels[1]]['force (N)'] = y
            self.channel_data[self.channels[1]]['distance (mm)'] = []

            x_reduced = average_reduce(x, 100)
            y_reduced = average_reduce(y, 100)
            fig = go.Figure(data=go.Scatter(
                x=x_reduced,
                y=y_reduced,
                mode='lines'))
            fig.update_layout(
                title_text='Force vs Distance',
                xaxis_title='Distance (mm)',
                yaxis_title='Force (N)')
            figs.append(fig)
        return figs


