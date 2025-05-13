import queue
import streamlit as st
from websocket import create_connection, WebSocketException
import threading
import time

st.title("WebSocket Chat App")

# Initialize session state
if 'messages' not in st.session_state:
    st.session_state.messages = []

if 'message_queue' not in st.session_state:
    st.session_state.message_queue = queue.Queue()

# WebSocket URL input
ws_url = st.text_input("WebSocket URL", "ws://localhost:8200/chat")

# Establish connection once
if 'ws' not in st.session_state:
    try:
        ws = create_connection(ws_url, ping_interval=20, ping_timeout=10)
        st.session_state.ws = ws
    except Exception as e:
        st.error(f"Connection error: {e}")

# Function to continuously receive messages
def receive_messages(ws, msg_queue):
    if not ws:
        return
    while True:
        try:
            message = ws.recv()
            msg_queue.put(message)
        except WebSocketException:
            break

# Start listener thread once
if 'listener_started' not in st.session_state and st.session_state.get('ws'):
    threading.Thread(target=receive_messages, args=(st.session_state.ws, st.session_state.message_queue), daemon=True).start()
    st.session_state.listener_started = True

# Message input and send button
message = st.text_input("Your message", key="message_input")
if st.button("Send"):
    ws = st.session_state.get('ws')
    if ws:
        try:
            ws.send(message)
            st.session_state.messages.append(f"You: {message}")
        except WebSocketException:
            st.error("Failed to send message. Connection may be closed.")

# Display chat history
chat_placeholder = st.empty()

# Update chat history
def update_chat():
    while not st.session_state.message_queue.empty():
        new_message = st.session_state.message_queue.get()
        st.session_state.messages.append(new_message)

    with chat_placeholder.container():
        st.write("### Chat History")
        for msg in st.session_state.messages:
            st.write(msg)

# Call it initially
update_chat()

# Auto-refresh chat every 2 seconds
time.sleep(2)
st.rerun()
