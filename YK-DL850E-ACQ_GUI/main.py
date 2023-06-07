import streamlit as st
import yk
import threading
from datetime import datetime
from io import BytesIO
import numpy as np
import os
import csv


def save_figure_to_bytes(fig):
    # Create a BytesIO object to store the PNG image data
    buffer = BytesIO()

    # Save the figure to the BytesIO object
    fig.savefig(buffer, format='png')
    buffer.seek(0)

    return buffer


acq = yk.acq()
if 'runFlag' not in st.session_state:
    st.session_state['runFlag'] = 0
if 'fig' not in st.session_state:
    st.session_state['fig'] = None
if 'data' not in st.session_state:
    st.session_state['data'] = None
if 'timestamp' not in st.session_state:
    st.session_state['timestamp'] = None

# Create a title
st.title('Yokogawa DL850E Acquisition GUI')

# Create a dropdown menu
options = yk.get_devices()
selected_option = st.selectbox('Select a device:', options)

# Create a run button
if st.button('Run'):
    st.session_state['runFlag'] = 0
    progress_bar = st.empty()
    instr = selected_option
    acq_thread = threading.Thread(target=acq.run, args=(instr,))  # Pass instr as an argument
    acq_thread.start()  # Start the thread
    while acq_thread.is_alive():
        progress = acq.get_progress()
        progress_bar.progress(progress)

    acq_thread.join()
    st.session_state['timestamp'] = datetime.now().strftime("%Y%m%d_%H%M%S")
    progress_bar.empty()
    st.session_state['runFlag'] = 1

initial_plot = st.empty()

# If the run button was pressed, plot the figure
if st.session_state['runFlag'] == 1:
    with st.spinner('Plotting...'):
        fig = acq.plot()
        st.session_state['data'] = acq.data
        st.session_state['fig'] = fig
        initial_plot = st.pyplot(fig)

        st.session_state['runFlag'] = 2

# Once plotting is done, save the plot to the session state, and display it, and show save buttons
if st.session_state['runFlag'] == 2:
    initial_plot.empty()
    st.pyplot(st.session_state['fig'])
    csv = acq.get_data()
    buffer = save_figure_to_bytes(st.session_state['fig'])

    col1, col2 = st.columns(2)
    col1.download_button("Download CSV",
                         csv,
                         file_name=f"{st.session_state['timestamp']}_data.csv",
                         key='download-csv'
                         )

    col2.download_button('Save Plot as PNG',
                         buffer,
                         file_name=f"{st.session_state['timestamp']}_fig.png",
                         key='download-png'
                         )
