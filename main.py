import streamlit as st
import yk
import threading
from datetime import datetime
from io import BytesIO
import matplotlib
matplotlib.use('agg')
st.set_option('deprecation.showPyplotGlobalUse', False)

def save_figure_to_bytes(fig):
    # Create a BytesIO object to store the PNG image data
    buffer = BytesIO()

    # Save the figure to the BytesIO object
    fig.savefig(buffer, format='png')
    buffer.seek(0)

    return buffer


acq = yk.acq()
#acq.channels = [1]
acq.xy_mode = 0

if 'runFlag' not in st.session_state:
    st.session_state['runFlag'] = 0
if 'figs' not in st.session_state:
    st.session_state['fig'] = None
if 'data' not in st.session_state:
    st.session_state['data'] = None
if 'timestamp' not in st.session_state:
    st.session_state['timestamp'] = None

# Create a title
st.title('Yokogawa DL850E Acquisition GUI')

#Create columns
col1, col2 = st.columns([1, 1])

options = yk.get_devices()
selected_option = col1.selectbox('Select a device:', options)


channels = range(1, 9)
acq.channels = col2.multiselect('Choose Channels:', channels)

# Create a run button
if st.button('Run'):
    st.session_state['runFlag'] = 0
    st.session_state['data'] = None
    st.session_state['fig'] = None
    progress_bar = st.empty()
    instr = selected_option
    acq_thread = threading.Thread(target=acq.run, args=(instr,))  # Pass instr as an argument
    acq_thread.start()  # Start the thread
    while acq_thread.is_alive():
        progress = acq.prog['prog']
        prog_text = str(acq.prog['iteration']) + '/' + str(len(acq.channels))
        progress_bar.progress(progress, text=prog_text)

    acq_thread.join()
    st.session_state['timestamp'] = datetime.now().strftime("%Y%m%d_%H%M%S")
    progress_bar.empty()
    st.session_state['runFlag'] = 1

# If the run button was pressed, plot the figure
if st.session_state['runFlag'] == 1:
    with st.spinner('Plotting...'):
        fig = acq.plot()
        st.session_state['fig'] = fig
        st.session_state['runFlag'] = 2

# Once plotting is done, save the plot to the session state, and display it, and show save buttons
if st.session_state['runFlag'] == 2:
    initial_plot = st.empty()
    fig = st.session_state['fig']
    initial_plot = st.pyplot(fig)
    csv = acq.get_data()
    #print('finished CSV')
    #buffer = save_figure_to_bytes(st.session_state['figs'])

    st.download_button("Download CSV",
                         csv,
                         file_name=f"{st.session_state['timestamp']}_data.csv",
                         key='download-csv'
                         )

