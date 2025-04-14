from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, send_file, send_from_directory, flash
from werkzeug.utils import secure_filename
import os


import base64
from google import genai
from google.genai import types

### TTS
from google.cloud import texttospeech_v1
client_tts = texttospeech_v1.TextToSpeechClient()
###
def generate(filename, prompt):
    client = genai.Client(
        api_key=os.environ.get("GEMINI_API_KEY"),
    )

    files = [
        client.files.upload(file=filename),
    ]
    model = "gemini-2.0-flash"
    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_uri(
                    file_uri=files[0].uri,
                    mime_type=files[0].mime_type,
                ),
                types.Part.from_text(text=prompt),    
            ],
        ),
    ]
    generate_content_config = types.GenerateContentConfig(
        temperature=1,
        top_k=40,
        top_p=0.95,
        max_output_tokens=8192,
        response_mime_type="text/plain",
    )

    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=generate_content_config,
    )
    print(response)
    return response.text


app = Flask(__name__)

# Configure upload folder
UPLOAD_FOLDER = 'uploads'
BOOK_FOLDER = 'books'
AUDIO_FOLDER = 'audio'
RESPONSE_FOLDER = 'responses'
ALLOWED_EXTENSIONS = {'wav'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['BOOK_FOLDER'] = BOOK_FOLDER
app.config['AUDIO_FOLDER'] = AUDIO_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(BOOK_FOLDER, exist_ok=True)
os.makedirs(AUDIO_FOLDER, exist_ok=True)
os.makedirs(RESPONSE_FOLDER, exist_ok=True)


### TTS function
def synthesize_to_wav(llm_response, ssml=None):
    input = texttospeech_v1.SynthesisInput()
    if ssml:
      input.ssml = ssml
    else:
      input.text = llm_response

    voice = texttospeech_v1.VoiceSelectionParams()
    voice.language_code = "en-UK"
    # voice.ssml_gender = "MALE"

    audio_config = texttospeech_v1.AudioConfig()
    audio_config.audio_encoding = "LINEAR16"

    request = texttospeech_v1.SynthesizeSpeechRequest(
        input=input,
        voice=voice,
        audio_config=audio_config,
    )

    response = client_tts.synthesize_speech(request=request)

    return response.audio_content


###


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

    return files


@app.route('/')
def index():
    files = get_files()  
    book_filename = request.args.get('book')  # Retrieve book filename from query string

    # Read response.txt if it exists
    response_text = ""
    response_path = os.path.join(RESPONSE_FOLDER, "response.txt")
    if os.path.exists(response_path):
        with open(response_path, 'r') as file:
            response_text = file.read()

    audio_exists = os.path.exists(os.path.join(AUDIO_FOLDER, "response.wav"))

    return render_template('index.html', files=files, book=book_filename, response_text=response_text, audio_exists=audio_exists)  # Pass response_text



###
@app.route('/upload_book', methods=['POST'])
def upload_book():
    if 'book_pdf' not in request.files:
        return "No file part", 400
    file = request.files['book_pdf']
    if file.filename == '':
        return "No selected file", 400
    filename = secure_filename(file.filename)
    file.save(os.path.join(app.config['BOOK_FOLDER'], filename))
    return redirect(url_for('index', book=filename))  # Redirect with book filename


###

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

        prompt = """
        Please provide an exact trascript for the audio.

        Your response should follow the format:

        Text: USERS SPEECH TRANSCRIPTION

        """
        text = generate(file_path, prompt)
        f = open(file_path + ".txt", "w")
        f.write(text)
        f.close()

        # ------------------ START MODIFICATION ----------------------

        # Find latest PDF book
        book_files = sorted(os.listdir(BOOK_FOLDER), reverse=True)
        if not book_files:
            return "No book uploaded", 400
        book_path = os.path.join(BOOK_FOLDER, book_files[0])

        
        # Now send book + question to LLM
        question_text = text.split("Text:")[1].strip()  # Extract the question from the audio transcription
        llm_response = generate(book_path, question_text)  # Get the LLM responsecd 

        # Save the LLM response as a .txt file
        response_txt_path = os.path.join(RESPONSE_FOLDER, "response.txt")
        with open(response_txt_path, "w") as f:
            f.write(llm_response)  # Write the LLM response to a .txt file

        
        wav = synthesize_to_wav(llm_response)
        
        wav_filename = 'response.wav'
        tts_path = os.path.join(app.config['AUDIO_FOLDER'], wav_filename)
        
        # save audio
        f = open(tts_path,'wb')
        f.write(wav)
        f.close()
        


        # ------------------ END MODIFICATION ----------------------

    return redirect('/')  

@app.route('/script.js',methods=['GET'])
def scripts_js():
    return send_file('./script.js')

###

@app.route('/audio/response.wav',methods=['GET'])
def get_response_audio():
    return send_file('./audio/response.wav')

###

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    app.run(debug=True)
