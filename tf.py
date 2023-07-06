import pyvisa
import re
import numpy as np
import scipy as sc
from tqdm import tqdm
import time
import sys
import pint
import os
import pandas as pd
from datetime import datetime
from tkinter import Tk
from tkinter.filedialog import asksaveasfilename

# Globals
ureg = pint.UnitRegistry()


# Function Definitions:

# extracts number in scientific notation from string
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


# Converts number to string +Hz
def convert_to_si_prefix(value):
    # Convert the value to the appropriate unit
    quantity = value * ureg.hertz

    # Get the SI prefix and value in that prefix
    prefix, scaled_value = quantity.to_compact()

    # Create the string representation
    string_value = f"{scaled_value:g}{prefix}Hz"

    return string_value


# converts time SI string to float
def convert_to_seconds(time_string):
    try:
        int_time = ureg(time_string)
        return int_time.to('second').magnitude
    except pint.errors.UndefinedUnitError:
        raise ValueError('Invalid unit')
    except pint.errors.DimensionalityError:
        raise ValueError('Invalid time string')


# Saves data to a .csv file
def save_data_to_csv(data):
    # Create a temporary directory to save the file
    temp_dir = os.path.join(os.getcwd(), 'temp')
    os.makedirs(temp_dir, exist_ok=True)

    # Generate a timestamp for the file name
    timestamp = datetime.now().strftime('%Y%m%d%H%M')
    file_name = f"{timestamp}_transfer_data.csv"

    # Create a dictionary to hold the data arrays
    data_dict = {}
    for i, arr in enumerate(data):
        var_name = f"variable_{i+1}"
        data_dict[var_name] = arr

    # Create a DataFrame using the data dictionary
    df = pd.DataFrame(data_dict)

    # Save the DataFrame to a CSV file in the temporary directory
    temp_file_path = os.path.join(temp_dir, file_name)
    df.to_csv(temp_file_path, index=False)

    print(f"Temporary file saved to: {temp_file_path}")

    # Open a file dialogue for the user to choose the save location
    try:
        Tk().withdraw()
        file_path = asksaveasfilename(
            defaultextension=".csv",
            initialdir=os.path.expanduser("~\\Documents"),
            initialfile=file_name,
            filetypes=[("CSV files", "*.csv")]
        )

        if file_path:
            # Copy the temporary file to the chosen save location
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            os.replace(temp_file_path, file_path)
            print(f"File saved to: {file_path}")
        else:
            print("File save operation cancelled.")
    except Exception as e:
        print(f"An error occurred while saving the file: {str(e)}")


class tf:
    def __init__(self):
        self.channel = str(1)
        self.yokogawaAddress = 'USB0::0x0B21::0x003F::39314B373135373833::INSTR'
        self.agilentAddress = 'USB0::0x0957::0x0407::MY44026553::INSTR'
        self.chunkSize = int(1E5)

    def open_instruments(self):
        rm = pyvisa.ResourceManager()
        resources = rm.list_resources()
        print(resources)
        if self.yokogawaAddress in resources:
            self.yk = rm.open_resource(self.yokogawaAddress)
        else:
            print('Failed to find Yokogawa!')
            sys.exit()
        if self.agilentAddress in resources:
            self.ag = rm.open_resource(self.agilentAddress)
        else:
            print('Failed to find Agilent!')
            sys.exit()

    def __initialize_yokogawa(self, sample_rate='10k', time_div='2s'):
        self.yk.write(':STOP')
        self.yk.write(':CALIBRATE:MODE OFF')
        self.yk.write(':WAVeform:TRACE ' + self.channel)

        self.yk.write(':TIMebase:TDIV ' + '1s')
        self.yk.write(':TIMebase:SRATE ' + sample_rate)
        self.yk.write(':TIMebase:TDIV ' + time_div)

        result = self.yk.query('WAVEFORM:RECord? MINimum')
        min_record = int(extract_number(result))

        self.yk.write(':WAVeform:RECord ' + str(min_record))

        self.yk.write('WAVEFORM:BYTEORDER LSBFIRST')
        self.yk.write(':WAVeform:FORMat WORD')

    def __initialize_agilent(self, voltage='10.0', shape='SINusoid', offset='0.0'):
        self.ag.write('*RST')
        self.ag.write('FUNCtion ' + shape)
        self.ag.write('VOLTage ' + voltage)
        self.ag.write('VOLTage:OFFSet ' + offset)
        self.ag.write('FREQuency 1')

    def initialize_instruments(self, sample_rate='10kHz', time_div='2s', voltage='10.0', shape='SINusoid', offset='0.0'):
        self.__sample_rate = sample_rate
        self.__time_div = time_div
        self.__initialize_agilent(voltage=voltage, shape=shape, offset=offset)
        self.__initialize_yokogawa(sample_rate=sample_rate, time_div=time_div)

    def __find_peak(self, frequency_of_interest, time_div, bin_size=0.5):
        # We change the TDIV to 1s to force a refresh and ensure we are getting the most current data
        self.yk.write(':TIMebase:TDIV ' + '1s')
        self.yk.write(':TIMebase:SRATE ' + self.__sample_rate)
        self.yk.write(':TIMebase:TDIV ' + time_div)

        # Waveform capture sequence
        self.yk.write(':START')
        if convert_to_seconds(time_div) < 0.5:
            time.sleep(12 * convert_to_seconds(time_div))
        else:
            time.sleep(11 * convert_to_seconds(time_div))
        self.yk.write(':STOP')

        # Download data from scope, convert it to an acceleration signal
        result = self.yk.query(':WAVeform:SRATe?')  # Get sampling rate
        sampling_rate = extract_number(result)

        result = self.yk.query('WAVEFORM:LENGth?')  # Get waveform length
        waveform_length = int(extract_number(result))

        n = int(np.floor(waveform_length / self.chunkSize))

        bit_data = []

        for i in range(n + 1):
            m = min(waveform_length, (i + 1) * self.chunkSize) - 1
            self.yk.write("WAVEFORM:START {};:WAVEFORM:END {}".format(i * self.chunkSize, m))
            buff = self.yk.query_binary_values('WAVEFORM:SEND?', datatype='h', container=list)
            bit_data.extend(buff)

        result = self.yk.query('WAVEFORM:OFFSET?')
        waveform_offset = extract_number(result)

        result = self.yk.query(':WAVeform:RANGe?')
        waveform_range = extract_number(result)

        voltage_data = waveform_range * np.array(
            bit_data) * 10 / 24000 + waveform_offset  # formula from the communication manual

        acceleration_data = 9.81 / 10 * voltage_data / 100
        time_data = np.array(range(len(acceleration_data))) / sampling_rate

        # Calculate position power spectral density
        freq, psd_acc = sc.signal.periodogram(acceleration_data,
                                              fs=sampling_rate
                                              )
        freq = freq[1:-1]
        psd_acc = psd_acc[1:-1]
        psd_pos = psd_acc / freq ** 2
        psd_data = psd_pos

        # Find the max value within bin range_width, centered on frequency_of_interest
        indices = np.where((freq >= frequency_of_interest - bin_size / 2) & (freq <= frequency_of_interest + bin_size / 2))
        psd_data_range = psd_data[indices]
        max_value = np.max(psd_data_range)

        return max_value

    def __measurement_cycle(self, frequency, num_iterations, time_div, bin_size=1):
        self.ag.write('FREQuency ' + str(frequency))
        self.ag.write('OUTPut ON')
        time.sleep(0.1)
        measurement_values = [self.__find_peak(frequency, time_div, bin_size=bin_size) for _ in tqdm(range(num_iterations))]
        self.ag.write('OUTPut OFF')
        return np.mean(measurement_values), np.std(measurement_values)

    def measure(self, frequencies, iterations, time_div, bin_size=1):
        results = []
        for freq, it, t in tqdm(zip(frequencies, iterations, time_div)):
            mean, std = self.__measurement_cycle(freq, it, t, bin_size=bin_size)
            results.append((mean, std))
        return results

    def close_instruments(self):
        self.ag.write('OUTPut OFF')
        self.yk.write(':STOP')


frequency = np.logspace(0, 2, num=300)
iterations = [3 if freq > 4 else 3 for freq in frequency]
time_divisions = ['2s' if freq < 2 else '500ms' if freq < 20 else '200ms' for freq in frequency]

tf = tf()
tf.open_instruments()
tf.initialize_instruments(voltage='1.0')
transfer_data = tf.measure(frequency, iterations, time_divisions, bin_size=1)
tf.close_instruments()
means, stds = zip(*transfer_data)

save_data_to_csv([frequency, means, stds])