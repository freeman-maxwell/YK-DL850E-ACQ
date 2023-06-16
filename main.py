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
    st.session_state['figs'] = None
if 'data' not in st.session_state:
    st.session_state['data'] = None
if 'timestamp' not in st.session_state:
    st.session_state['timestamp'] = None

# Create a title
st.title('Yokogawa DL850E Acquisition GUI')

# Create columns for dropdown
dd_col1, dd_col2 = st.columns([1, 1])

options = yk.get_devices()
selected_option = dd_col1.selectbox('Select a device:', options)


channels = range(1, 9)
acq.channels = dd_col2.multiselect('Choose Channels:', channels)

# Create columns for buttons
but_col1, but_col2 = st.columns([1, 10])
but_col2.empty()

# Create a run button
if but_col1.button('Run'):
    st.session_state['runFlag'] = 0
    st.session_state['data'] = None
    st.session_state['figs'] = None
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
        figs = acq.plot()
        st.session_state['figs'] = figs
        st.session_state['runFlag'] = 2

# Once plotting is done, save the plot to the session state, and display it, and show save button
if st.session_state['runFlag'] >= 2:
    figs = st.session_state['figs']
    for fig in figs:
        st.plotly_chart(fig)
    csv = acq.get_data()
    st.session_state['runFlag'] = 3
    but_col2.download_button("Download CSV",
                            csv,
                            file_name=f"{st.session_state['timestamp']}_data.csv",
                            key='download-csv'
                            )




