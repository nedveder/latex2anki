import os
from flask import Flask, render_template, request, flash, redirect, url_for, send_file
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import logging
from openai import OpenAI
from TexSoup import TexSoup
import fitz  # PyMuPDF for PDF processing
import genanki
import random
from google.cloud import translate_v2 as translate
import re

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {'tex', 'pdf', 'lyx'}
UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER', 'uploads')
MAX_CONTENT_LENGTH = int(os.getenv('MAX_CONTENT_LENGTH', 16777216))

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
app.secret_key = os.urandom(24)

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# Initialize Google Translate client
translate_client = translate.Client()

SYSTEM_PROMPT = """
You are an expert educator and Anki card creator. Your task is to generate Anki cards in a precise format. Always adhere to the following rules:
1. Use the exact template provided for each card type.
2. Maintain LaTeX formatting where appropriate.
3. Ensure content is concise yet comprehensive.
4. Use clear and precise language.
5. Do not add any explanatory text or deviate from the requested format.
"""

client = OpenAI()
app = Flask(__name__)
# Configure OpenAI API from environment variable
client.api_key = os.getenv('OPENAI_API_KEY')
# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def translate_text(text, target_language='en'):
    if target_language == 'en':
        return text
    
    try:
        result = translate_client.translate(text, target_language=target_language)
        return result['translatedText']
    except Exception as e:
        logger.error(f"Translation error: {e}")
        return text

def extract_content_from_pdf(pdf_path):
    content = []
    try:
        doc = fitz.open(pdf_path)
        for page in doc:
            content.append(page.get_text())
        return "\n".join(content)
    except Exception as e:
        logger.error(f"PDF extraction error: {e}")
        return ""

def parse_lyx_file(lyx_path):
    # Basic LyX parsing - you might need to enhance this based on your needs
    with open(lyx_path, 'r', encoding='utf-8') as file:
        content = file.read()
    # Extract the latex content from LyX format
    # This is a simplified version - you might need to adjust based on your LyX files
    latex_content = re.findall(r'\\begin_layout.*?\n(.*?)\\end_layout', content, re.DOTALL)
    return "\n".join(latex_content)

def generate_anki_cards(content, content_type):
    cards = []
    
    # Define card templates
    templates = {
        'definition': {
            'front': '{{Term}}',
            'back': '{{Definition}}'
        },
        'theorem': {
            'front': '{{Theorem}}',
            'back': '{{Proof}}'
        },
        'example': {
            'front': '{{Concept}}',
            'back': '{{Example}}\n{{Explanation}}'
        }
    }

    prompt = f"""Generate an Anki card for the following LaTeX content:
    ```
    {text}
    ```
    Please create the card in the EXACT format below, maintaining LaTeX formatting where appropriate:
    
    {type_template[card_type]}
    
    Additional instructions:
    1. Ensure the content is concise yet comprehensive.
    2. For definitions, provide a clear and precise explanation.
    3. For theorems and claims, include key points of the proof or justification.
    4. Use bullet points or numbered lists for clarity when appropriate.
    5. Include relevant formulas, diagrams, or examples if they enhance understanding.
    6. Avoid unnecessary information or verbose explanations.
    7. Use LaTeX formatting for mathematical symbols, equations, and special characters.
    8. Proofread the card for accuracy and clarity before submission.
    
    Make sure to follow the format strictly to create effective Anki cards.
    """
    return prompt


def generate_card(text, type):
    logger.info("Generating quiz questions")
    prompt = generate_anki_prompt(text, type)
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        temperature=0.2,
        max_tokens=500,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0
    ).choices[0].message.content
    return response


def extract_sections(tex_file_path):
    with open(tex_file_path, 'r', encoding='utf-8') as file:
        soup = TexSoup(file.read())
    csv_file_path = 'uploads/Topology.csv'
    # Prepare the CSV file
    with open(csv_file_path, 'w', newline='', encoding='utf-8') as csvfile:
        csvwriter = csv.writer(csvfile)
        # Write header
        csvwriter.writerow(['Type', 'Title', 'Subject', 'Tags',])

        current_subject = ""
        for item in soup.find_all(['section', 'definition', 'theorem', 'claim']):
            if item.name == 'section':
                current_subject = str(item.string).strip()
            elif item.name in ['definition', 'theorem', 'claim']:
                # TODO
                csvwriter.writerow([type_, title, front_data, back_data, current_subject, tags])


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        flash('No file part', 'error')
        return redirect(url_for('index'))
    
    file = request.files['file']
    if file.filename == '':
        flash('No selected file', 'error')
        return redirect(url_for('index'))
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        try:
            # Process the file based on its type
            file_ext = filename.rsplit('.', 1)[1].lower()
            if file_ext == 'pdf':
                content = extract_content_from_pdf(filepath)
            elif file_ext == 'tex':
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
            elif file_ext == 'lyx':
                content = parse_lyx_file(filepath)
            
            # Translate if necessary
            language = request.form.get('language', 'en')
            if language != 'en':
                content = translate_text(content)
            
            # Generate Anki cards
            cards = generate_anki_cards(content, file_ext)
            
            # Create Anki deck
            deck_id = random.randrange(1 << 30, 1 << 31)
            deck = genanki.Deck(deck_id, f"Math Cards - {filename}")
            
            # Add cards to deck
            for card in cards:
                note = genanki.Note(
                    model=card['model'],
                    fields=card['fields']
                )
                deck.add_note(note)
            
            # Save the deck
            deck_filename = f"math_deck_{filename}.apkg"
            deck_path = os.path.join(app.config['UPLOAD_FOLDER'], deck_filename)
            genanki.Package(deck).write_to_file(deck_path)
            
            # Clean up the original file
            os.remove(filepath)
            
            return send_file(deck_path, as_attachment=True)
            
        except Exception as e:
            logger.error(f"Error processing file: {e}")
            flash('Error processing file', 'error')
            return redirect(url_for('index'))
    
    flash('Invalid file type', 'error')
    return redirect(url_for('index'))

if __name__ == '__main__':
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    app.run(debug=True)
