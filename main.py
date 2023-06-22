import streamlit as st
import yk
import threading
from datetime import datetime
import csv
import io
from stqdm import stqdm

st.set_option('deprecation.showPyplotGlobalUse', False)

acq = yk.acq()

if 'runFlag' not in st.session_state:
    st.session_state['runFlag'] = 0
if 'figs' not in st.session_state:
    st.session_state['figs'] = None
if 'channel_data' not in st.session_state:
    st.session_state['channel_data'] = None
if 'timestamp' not in st.session_state:
    st.session_state['timestamp'] = None
if 'csv_bytes' not in st.session_state:
    st.session_state['csv_bytes'] = None


# Create a title
def get_csv_data(channel_data):
    channel_keys = channel_data.keys()
    key_sets = []
    for key in channel_keys:
        unique_keys = set()
        data = channel_data[key]
        unique_keys.update(data.keys())
        key_sets.append(unique_keys)

    headers = [f'C{channel} {item}' for channel, sets in zip(channel_keys, key_sets) for item in sets]

    max_data_length = max(
        [len(channel_data[channel][key]) for channel, sets in zip(channel_keys, key_sets) for key in sets])

    csv_rows = [
        [channel_data[channel][key][i] if i < len(channel_data[channel][key]) else ''
         for channel, sets in zip(channel_keys, key_sets) for key in sets]
        for i in stqdm(range(max_data_length))
    ]

    csv_string_io = io.StringIO()
    csv_writer = csv.writer(csv_string_io)
    csv_writer.writerow(headers)
    csv_writer.writerows(csv_rows)

    csv_string = csv_string_io.getvalue()
    csv_string_io.close()

    return csv_string


@st.cache_resource
def plot_figs(timestamp):
    print('started plotting')
    figs = st.session_state['figs']
    print('stopped plotting')
    return figs


st.title('Yokogawa DL850E Acquisition GUI')

# Create columns for dropdown
dd_col1, dd_col2, dd_col3 = st.columns([1, 1, 1.5])

options = yk.get_devices()
selected_option = dd_col1.selectbox('Select a device:', options)

channels = range(1, 9)
selected_channels = dd_col2.multiselect('Choose channels:', channels)

modes = ['time domain', 'frequency domain', 'X vs Y']
selected_mode = dd_col3.multiselect('Choose plot types:', modes)

gain = st.number_input('Amplifier Gain',
                       min_value=0,
                       value=1)

# Create columns for buttons
but_col1, but_col2 = st.columns([1, 10])
but_col2.empty()

# Create a run button
if but_col1.button('Run'):
    print('running data acquisition')
    st.session_state['runFlag'] = 0
    st.session_state['channel_data'] = None
    st.session_state['figs'] = None

    progress_bar = st.empty()

    instr = selected_option
    acq.channels = selected_channels
    acq.mode = selected_mode
    acq.amp_gain = gain

    acq_thread = threading.Thread(target=acq.run, args=(instr,))  # Pass instr as an argument
    acq_thread.start()  # Start the thread
    while acq_thread.is_alive():
        progress = acq.prog['prog']
        prog_text = str(acq.prog['iteration']) + '/' + str(len(acq.channels))
        progress_bar.progress(progress, text=prog_text)

    acq_thread.join()
    st.session_state['channel_data'] = acq.channel_data
    st.session_state['timestamp'] = datetime.now().strftime("%Y%m%d_%H%M%S")
    progress_bar.empty()
    print('finished data acquisition')
    st.session_state['runFlag'] = 1

# If the run button was pressed, plot the figure
if st.session_state['runFlag'] == 1:
    print('getting plots')
    figs = acq.plot()
    st.session_state['figs'] = figs
    print('finished getting plots')
    st.session_state['runFlag'] = 2

# Once plotting is done, save the plot to the session state, and display it, and show save button
if st.session_state['runFlag'] >= 2:
    figs = plot_figs(st.session_state['timestamp'])
    for fig in figs:
        st.plotly_chart(fig)
    if st.session_state['runFlag'] == 2:
        print('started csv')
        csv = get_csv_data(st.session_state['channel_data'])
        csv_bytes = csv.encode('utf-8')
        st.session_state['csv_bytes'] = csv_bytes
        st.session_state['runFlag'] = 3
        print('stopped csv')
    if st.session_state['runFlag'] == 3:
        but_col2.download_button("Download CSV",
                                 st.session_state['csv_bytes'],
                                 file_name=f"{st.session_state['timestamp']}_data.csv",
                                 key='download-csv'
                                 )
