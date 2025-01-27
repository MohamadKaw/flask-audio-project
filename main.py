from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, send_file, send_from_directory, flash
from werkzeug.utils import secure_filename
import os

# Import Google APIs
from google.cloud import speech
from google.cloud import texttospeech

app = Flask(__name__)

# Configure upload folder
UPLOAD_FOLDER = 'uploads'
TTS_FOLDER = 'tts'  # Directory for text-to-speech files
ALLOWED_EXTENSIONS = {'wav'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(TTS_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_files():
    # Get .wav files from the 'uploads' folder
    files = []
    for filename in os.listdir(UPLOAD_FOLDER):
        if allowed_file(filename):
            files.append(filename)
    files.sort(reverse=True)  # Sort the files by timestamp (most recent first)

    # Get .wav files from the 'tts' folder (Text-to-Speech generated files)
    tts_files = []
    for filename in os.listdir(TTS_FOLDER):
        if filename.endswith('.wav'):  # Only include .wav files
            tts_files.append(filename)
    tts_files.sort(reverse=True)  # Sort TTS files as well

    return files, tts_files


@app.route('/')
def index():
    files, tts_files = get_files()  # Get both sets of files
    return render_template('index.html', files=files, tts_files=tts_files)


@app.route('/upload', methods=['POST'])
def upload_audio():
    if 'audio_data' not in request.files:
        flash('No audio data')
        return redirect(request.url)
    file = request.files['audio_data']
    if file.filename == '':
        flash('No selected file')
        return redirect(request.url)
    if file:
        # Save the audio file with a timestamped filename
        filename = datetime.now().strftime("%Y%m%d-%I%M%S%p") + '.wav'
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        print(f"File saved at: {file_path}")

        # ------------------ MODIFICATION FOR SPEECH-TO-TEXT ----------------------
        # Use Google Cloud Speech-to-Text API for long-running recognition
        client = speech.SpeechClient()

        # Read audio file in binary mode
        with open(file_path, "rb") as f:
            content = f.read()

        audio = speech.RecognitionAudio(content=content)
        config = speech.RecognitionConfig(
            language_code="en-US",
            model="latest_long",
            audio_channel_count=1,
            enable_word_confidence=True,
            enable_word_time_offsets=True,
        )

        # Perform long-running recognize operation
        operation = client.long_running_recognize(config=config, audio=audio)
        response = operation.result(timeout=90)

        # Process and save the transcription
        transcript = ''
        for result in response.results:
            transcript += result.alternatives[0].transcript + '\n'

        # Save the transcript as a text file with the same name as the audio file
        transcript_filename = file_path.replace('.wav', '.txt')
        with open(transcript_filename, 'w') as transcript_file:
            transcript_file.write(transcript)
        print(f"Transcript saved at: {transcript_filename}")
        # ------------------ END MODIFICATION FOR SPEECH-TO-TEXT ----------------------

    return redirect('/')  # Redirect to the homepage

@app.route('/upload/<filename>')
def get_file(filename):
    return send_file(filename)

@app.route('/uploads/<filename>.txt')
def get_transcription_file(filename):
    transcript_file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename + '.txt')
    if os.path.exists(transcript_file_path):
        return send_file(transcript_file_path)
    else:
        return "Transcription not found", 404

@app.route('/upload_text', methods=['POST'])
def upload_text():
    text = request.form['text']
    print(f"Text received: {text}")
    # ------------------ MODIFICATION FOR TEXT-TO-SPEECH ----------------------
    # Use Google Cloud Text-to-Speech API to convert the input text to speech
    client = texttospeech.TextToSpeechClient()

    # Prepare the input text for synthesis
    synthesis_input = texttospeech.SynthesisInput(text=text)

    # Define the voice parameters (optional)
    voice = texttospeech.VoiceSelectionParams(
        language_code="en-US", 
        ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL
    )

    # Set audio configuration (set the encoding to LINEAR16 for WAV output)
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.LINEAR16
    )

    # Perform the text-to-speech synthesis
    response = client.synthesize_speech(
        input=synthesis_input,
        voice=voice,
        audio_config=audio_config
    )

    # Save the audio file generated from the text
    tts_filename = datetime.now().strftime("%Y%m%d-%I%M%S%p") + '.wav'
    tts_file_path = os.path.join(TTS_FOLDER, tts_filename)
    with open(tts_file_path, "wb") as out:
        out.write(response.audio_content)
    print(f"TTS Audio saved at: {tts_file_path}")

    # Save the input text as a .txt file in the TTS folder
    tts_text_path = os.path.join(TTS_FOLDER, tts_filename + '.txt')
    with open(tts_text_path, "w") as text_file:
        text_file.write(text)
    print(f"TTS Text saved at: {tts_text_path}")



    # ------------------ END MODIFICATION FOR TEXT-TO-SPEECH ----------------------

    return redirect('/')  # Redirect to the homepage

@app.route('/script.js', methods=['GET'])
def scripts_js():
    return send_file('./script.js')

# Route to serve both uploaded audio (.wav) and transcription (.txt) files
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    # Serve the file based on its extension
    if filename.endswith('.txt'):
        # Serve transcription files (.txt)
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
    elif filename.endswith('.wav'):
        # Serve audio files (.wav)
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
    else:
        return "File type not supported", 404


@app.route('/tts/<filename>')
def tts_file(filename):
    # Serve files from the TTS_FOLDER
    file_path = os.path.join(TTS_FOLDER, filename)
    if os.path.exists(file_path):
        return send_from_directory(TTS_FOLDER, filename)
    else:
        return "File not found", 404


if __name__ == '__main__':
    app.run(debug=True)
