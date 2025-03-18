import speech_recognition as sr

recognizer = sr.Recognizer()

with sr.Microphone() as source:
    print("Listening... Speak now!")

    try:
        audio = recognizer.listen(source)
        
        # Recognize the speech using Google's speech recognition
        text = recognizer.recognize_google(audio)
        print("You said:", text)

    except sr.UnknownValueError:
        print("Sorry, I could not understand the audio.")
    except sr.RequestError:
        print("Could not request results, check your internet connection.")
