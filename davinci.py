
#!/usr/bin/env python3

import boto3
import os
import pvcobra
import pvleopard
import pvporcupine
import pyaudio
import random
import struct
import sys
import textwrap
import threading
import time
import requests  # Importing requests to interact with GroqCloud

import RPi.GPIO as GPIO

from os import environ
environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
import pygame

from colorama import Fore, Style
from pvleopard import *
from pvrecorder import PvRecorder
from threading import Thread, Event
from time import sleep

GPIO.setwarnings(False)

GPIO.setmode(GPIO.BCM)
led1_pin=18
led2_pin=24

GPIO.setup(led1_pin, GPIO.OUT)
GPIO.output(led1_pin, GPIO.LOW)

GPIO.setup(led2_pin, GPIO.OUT)
GPIO.output(led2_pin, GPIO.LOW)

audio_stream = None
cobra = None
pa = None
polly = boto3.client('polly')
porcupine = None
recorder = None
wav_file = None

groqcloud_api_key = ""
groqcloud_api_url = "https://api.groq.com/openai/v1/models"  # Replace with GroqCloud API endpoint

# Update with the GroqCloud chat model identifier
groqcloud_model = "llama-3.3-70b-versatile"

# Update the function to use GroqCloud API
def GroqCloudChat(query):
    headers = {
        "Authorization": f"Bearer {groqcloud_api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": groqcloud_model,
        "messages": [
            {"role": "user", "content": query},
        ]
    }

    response = requests.post(groqcloud_api_url, headers=headers, json=payload)

    if response.status_code == 200:
        result = response.json()
        return result['choices'][0]['message']['content']
    else:
        print("Error with GroqCloud API:", response.status_code)
        return None
   
def responseprinter(chat):
    wrapper = textwrap.TextWrapper(width=70)  # Adjust the width to your preference
    paragraphs = res.split('\n')
    wrapped_chat = "\n".join([wrapper.fill(p) for p in paragraphs])
    for word in wrapped_chat:
       time.sleep(0.06)
       print(word, end="", flush=True)
    print()

# DaVinci will 'remember' earlier queries so that it has greater continuity in its response
# the following will delete that 'memory' five minutes after the start of the conversation
def append_clear_countdown():
    sleep(300)
    global chat_log
    chat_log.clear()
    chat_log = [
        {"role": "system", "content": "Your name is DaVinci. You are a helpful assistant. If asked about yourself, you include your name in your response."},
    ]
    global count
    count = 0
    t_count.join

def voice(chat):
    voiceResponse = polly.synthesize_speech(Text=chat, OutputFormat="mp3",
                    VoiceId="Matthew")  # Other options include Amy, Joey, Nicole, Raveena, and Russell
    if "AudioStream" in voiceResponse:
        with voiceResponse["AudioStream"] as stream:
            output_file = "speech.mp3"
            try:
                with open(output_file, "wb") as file:
                    file.write(stream.read())
            except IOError as error:
                print(error)
    else:
        print("did not work")

    pygame.mixer.init()    
    pygame.mixer.music.load(output_file)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        pass
    sleep(0.2)

def fade_leds(event):
    pwm1 = GPIO.PWM(led1_pin, 200)
    pwm2 = GPIO.PWM(led2_pin, 200)

    event.clear()

    while not event.is_set():
        pwm1.start(0)
        pwm2.start(0)
        for dc in range(0, 101, 5):
            pwm1.ChangeDutyCycle(dc)  
            pwm2.ChangeDutyCycle(dc)
            time.sleep(0.05)
        time.sleep(0.75)
        for dc in range(100, -1, -5):
            pwm1.ChangeDutyCycle(dc)                
            pwm2.ChangeDutyCycle(dc)
            time.sleep(0.05)
        time.sleep(0.75)
       
def wake_word():
   
    keywords = ["computer", "jarvis", "DaVinci"]
    porcupine = pvporcupine.create(keywords=keywords,
                            access_key=pv_access_key,
                            sensitivities=[0.1, 0.1, 0.1],  # Adjust sensitivities
                                   )
    devnull = os.open(os.devnull, os.O_WRONLY)
    old_stderr = os.dup(2)
    sys.stderr.flush()
    os.dup2(devnull, 2)
    os.close(devnull)
   
    wake_pa = pyaudio.PyAudio()

    porcupine_audio_stream = wake_pa.open(
                    rate=porcupine.sample_rate,
                    channels=1,
                    format=pyaudio.paInt16,
                    input=True,
                    frames_per_buffer=porcupine.frame_length)
   
    Detect = True

    while Detect:
        porcupine_pcm = porcupine_audio_stream.read(porcupine.frame_length)
        porcupine_pcm = struct.unpack_from("h" * porcupine.frame_length, porcupine_pcm)

        porcupine_keyword_index = porcupine.process(porcupine_pcm)

        if porcupine_keyword_index >= 0:

            GPIO.output(led1_pin, GPIO.HIGH)
            GPIO.output(led2_pin, GPIO.HIGH)
            keyword = keywords[porcupine_keyword_index]
            print(Fore.GREEN + "\n" + keyword + " detected\n")
            porcupine_audio_stream.stop_stream
            porcupine_audio_stream.close()
            porcupine.delete()        
            os.dup2(old_stderr, 2)
            os.close(old_stderr)
            Detect = False

def listen():
    cobra = pvcobra.create(access_key=pv_access_key)

    listen_pa = pyaudio.PyAudio()

    listen_audio_stream = listen_pa.open(
                rate=cobra.sample_rate,
                channels=1,
                format=pyaudio.paInt16,
                input=True,
                frames_per_buffer=cobra.frame_length)

    print("Listening...")

    while True:
        listen_pcm = listen_audio_stream.read(cobra.frame_length)
        listen_pcm = struct.unpack_from("h" * cobra.frame_length, listen_pcm)
           
        if cobra.process(listen_pcm) > 0.3:
            print("Voice detected")
            listen_audio_stream.stop_stream
            listen_audio_stream.close()
            cobra.delete()
            break

def detect_silence():
    cobra = pvcobra.create(access_key=pv_access_key)

    silence_pa = pyaudio.PyAudio()

    cobra_audio_stream = silence_pa.open(
                    rate=cobra.sample_rate,
                    channels=1,
                    format=pyaudio.paInt16,
                    input=True,
                    frames_per_buffer=cobra.frame_length)

    last_voice_time = time.time()

    while True:
        cobra_pcm = cobra_audio_stream.read(cobra.frame_length)
        cobra_pcm = struct.unpack_from("h" * cobra.frame_length, cobra_pcm)
           
        if cobra.process(cobra_pcm) > 0.2:
            last_voice_time = time.time()
        else:
            silence_duration = time.time() - last_voice_time
            if silence_duration > 1.3:
                print("End of query detected\n")
                GPIO.output(led1_pin, GPIO.LOW)
                GPIO.output(led2_pin, GPIO.LOW)
                cobra_audio_stream.stop_stream                
                cobra_audio_stream.close()
                cobra.delete()
                last_voice_time=None
                break

# Main loop
try:
    o = create(
        access_key=pv_access_key,
        enable_automatic_punctuation=True,
    )

    event = threading.Event()

    count = 0

    while True:

        try:

            if count == 0:
                t_count = threading.Thread(target=append_clear_countdown)
                t_count.start()
            else:
                pass  
            count += 1
            wake_word()
            voice(random.choice(prompt))
            recorder = Recorder()
            recorder.start()
            listen()
            detect_silence()
            transcript, words = o.process(recorder.stop())
            t_fade = threading.Thread(target=fade_leds, args=(event,))
            t_fade.start()
            recorder.stop()
            print(transcript)
            (res) = GroqCloudChat(transcript)  # Using GroqCloud's response
            print("\nGroqCloud's response is:\n")        
            t1 = threading.Thread(target=voice, args=(res,))
            t2 = threading.Thread(target=responseprinter, args=(res,))
            t1.start()
            t2.start()
            t1.join()
            t2.join()
            event.set()
            GPIO.output(led1_pin, GPIO.LOW)
            GPIO.output(led2_pin, GPIO.LOW)        
            recorder.stop()
            o.delete()
            recorder = None

        except requests.exceptions.RequestException as e:
            print(f"\nThere was an error with the API request: {e
