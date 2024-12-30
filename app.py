import os
import csv
from flask import Flask, render_template, request, flash, redirect, url_for, send_file
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import logging
import anthropic
from TexSoup import TexSoup
import genanki
import random
import re
from pypdf import PdfReader

# Configure logging first
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {'tex', 'pdf', 'lyx'}
UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER', 'uploads')
MAX_CONTENT_LENGTH = int(os.getenv('MAX_CONTENT_LENGTH', 16777216))

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
app.secret_key = os.urandom(24)

# Load environment variables
load_dotenv()

# Initialize clients
api_key = os.getenv('ANTHROPIC_API_KEY')
if not api_key:
    logger.error("ANTHROPIC_API_KEY environment variable is not set")
    api_key = "dummy_key"  # For development/testing only
client = anthropic.Client(api_key=api_key)

# Ensure upload folder exists with proper permissions
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.chmod(UPLOAD_FOLDER, 0o755)


SYSTEM_PROMPT = """
You are an expert educator and Anki card creator. Your task is to generate Anki cards in a precise format. Always adhere to the following rules:
1. Use the exact template provided for each card type.
2. Maintain LaTeX formatting where appropriate.
3. Ensure content is concise yet comprehensive.
4. Use clear and precise language.
5. Do not add any explanatory text or deviate from the requested format.
"""



def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def translate_text(text, target_language='en'):
    """Translate text using Anthropic's API if target language is not English."""
    if target_language == 'en':
        return text
    
    try:
        # Create a translation prompt for Claude
        language_map = {
            'he': 'Hebrew',
            # Add more language mappings as needed
        }
        target_language_name = language_map.get(target_language, target_language)
        
        prompt = f"""Translate the following text to {target_language_name}. 
        Maintain all LaTeX formatting and mathematical notation exactly as is. 
        Only translate the natural language parts:

        {text}"""
        
        try:
            # Limit content length
            if len(prompt) > 4000:
                logger.warning("Content too long, truncating...")
                prompt = prompt[:4000] + "..."

            response = client.messages.create(
                model="claude-3-opus-20240229",
                max_tokens=1500,
                temperature=0.2,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                timeout=30  # 30 second timeout
            )
        except Exception as e:
            logger.error(f"Translation failed: {str(e)}")
            return text
        
        translated_text = response.content
        return translated_text
        
    except Exception as e:
        logger.error(f"Translation error: {str(e)}")
        flash('Translation failed, proceeding with original text', 'warning')
        return text

def extract_content_from_pdf(pdf_path):
    content = []
    try:
        reader = PdfReader(pdf_path)
        for page in reader.pages:
            content.append(page.extract_text())
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

# Define Anki note models
BASIC_MODEL = genanki.Model(
    1607392319,
    'Basic Math Card',
    fields=[
        {'name': 'Front'},
        {'name': 'Back'},
    ],
    templates=[
        {
            'name': 'Card 1',
            'qfmt': '[latex]{{Front}}[/latex]',
            'afmt': '[latex]{{FrontSide}}[/latex]<hr id="answer">[latex]{{Back}}[/latex]',
        },
    ],
    css="""
        .card {
            font-family: arial;
            font-size: 20px;
            text-align: center;
            color: black;
            background-color: white;
        }
    """)

def generate_anki_cards(content, content_type):
    """Generate Anki cards from LaTeX content.
    
    Args:
        content (str): LaTeX content to process
        content_type (str): Type of content ('tex', 'pdf', etc)
        
    Returns:
        list: List of card dictionaries, empty list if no cards could be generated
    """
    cards = []
    sections = re.split(r'\n(?=\\(?:section|subsection|definition|theorem|example))', content)
    
    for section in sections:
        if not section.strip():
            continue
            
        try:
            # Determine content type from section
            section_type = 'definition'
            if '\\theorem' in section:
                section_type = 'theorem'
            elif '\\example' in section:
                section_type = 'example'
                
            prompt = f"""Create an Anki card from this LaTeX content:
            {section}
            
            Format for {section_type}:
            Front: [Concise title/question in LaTeX format]
            Back: [Detailed explanation]
            
            Important rules:
            1. Preserve ALL mathematical expressions in LaTeX format using $ or $$ delimiters
            2. Keep ALL original LaTeX commands and environments
            3. Ensure equations and mathematical symbols are properly formatted
            4. Do not convert LaTeX math to plain text
            5. Keep the original LaTeX formatting intact"""
            
            try:
                # Limit content length
                if len(prompt) > 4000:  # Reasonable limit for API request
                    logger.warning("Content too long, truncating...")
                    prompt = prompt[:4000] + "..."

                response = client.messages.create(
                    model="claude-3-opus-20240229",
                    max_tokens=1000,
                    temperature=0.2,
                    system=SYSTEM_PROMPT,
                    messages=[
                        {"role": "user", "content": prompt}
                    ],
                    timeout=30  # 30 second timeout
                )
            except Exception as e:
                logger.error(f"API request failed: {str(e)}")
                continue
            
            # Parse the response and create card
            card_content = response.content
            
            # Handle both direct string and TextBlock responses
            if isinstance(card_content, list):
                # If it's a list of TextBlocks, get the first one's text
                if len(card_content) > 0 and hasattr(card_content[0], 'text'):
                    card_content = card_content[0].text
            elif hasattr(card_content, 'text'):
                card_content = card_content.text
                
            if 'Front:' in card_content and 'Back:' in card_content:
                # Extract content between Front: and Back:
                front = re.search(r'Front:(.*?)(?=Back:)', card_content, re.DOTALL).group(1).strip()
                # Extract everything after Back:
                back = re.search(r'Back:(.*)', card_content, re.DOTALL).group(1).strip()
                
                # Ensure LaTeX content is properly formatted
                def validate_latex(text):
                    # Ensure math environments are properly wrapped
                    if '$' not in text and '\\[' not in text and '\\begin{' not in text:
                        # If no LaTeX delimiters found, wrap the whole content
                        return f"$${text}$$"
                    return text
                
                front = validate_latex(front)
                back = validate_latex(back)
                
                cards.append({
                    'model': BASIC_MODEL,
                    'fields': [front, back]
                })
            else:
                logger.warning(f"Unexpected card format: {card_content[:100]}...")
                
        except Exception as e:
            logger.error(f"Error generating card: {e}")
            continue
    
    return cards




def extract_sections(tex_file_path):
    with open(tex_file_path, 'r', encoding='utf-8') as file:
        soup = TexSoup(file.read())
    csv_file_path = 'uploads/Topology.csv'
    # Prepare the CSV file
    with open(csv_file_path, 'w', newline='', encoding='utf-8') as csvfile:
        csvwriter = csv.writer(csvfile)
        # Write header
        csvwriter.writerow(['Type', 'Title', 'Subject', 'Tags'])

        current_subject = ""
        for item in soup.find_all(['section', 'definition', 'theorem', 'claim']):
            if item.name == 'section':
                current_subject = str(item.string).strip()
            elif item.name in ['definition', 'theorem', 'claim']:
                item_type = item.name
                item_title = str(item.string).strip() if item.string else ""
                tags = [current_subject, item_type]
                csvwriter.writerow([item_type, item_title, current_subject, ",".join(tags)])


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
            
            # Clean up files
            try:
                os.remove(filepath)
                response = send_file(deck_path, as_attachment=True)
                @response.call_on_close
                def cleanup():
                    try:
                        os.remove(deck_path)
                    except:
                        pass
                return response
            except Exception as e:
                logger.error(f"Error cleaning up files: {e}")
                flash('Error during file cleanup', 'warning')
                return redirect(url_for('index'))
            
        except Exception as e:
            logger.error(f"Error processing file: {e}")
            flash('Error processing file', 'error')
            return redirect(url_for('index'))
    
    flash('Invalid file type', 'error')
    return redirect(url_for('index'))

if __name__ == '__main__':
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    port = int(os.getenv('FLASK_PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
