import csv
from openai import OpenAI
from flask import Flask, render_template, request, jsonify
from TexSoup import TexSoup
import os
import logging

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


def generate_anki_prompt(text, card_type):
    type_template = {
        'definition': '[TERM]\n*****\n[DEFINITION]',
        'theorem': '[THEOREM NAME]\n*****\n[THEOREM STATEMENT]\n*****\n[PROOF]',
        'claim': '[CLAIM]\n*****\n[EXPLANATION]\n*****\n[PROOF/JUSTIFICATION]',
        'example': '[CONCEPT]\n*****\n[EXAMPLE]\n*****\n[EXPLANATION]',
        'formula': '[FORMULA NAME]\n*****\n[FORMULA]\n*****\n[VARIABLES EXPLANATION]\n*****\n[USAGE CONTEXT]'
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
def hello_world():  # put application's code here
    return extract_sections('uploads/Topology.tex')


if __name__ == '__main__':
    app.run()
