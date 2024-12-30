import pytest
from app import generate_anki_cards, BASIC_MODEL

def test_latex_preservation():
    # Test content with LaTeX math
    content = r"""
    \section{Test Section}
    \begin{definition}
    Let $f: X \to Y$ be a function between topological spaces.
    $f$ is continuous if $f^{-1}(U)$ is open in $X$ for every open set $U$ in $Y$.
    \end{definition}
    """
    
    cards = generate_anki_cards(content, 'tex')
    assert len(cards) > 0
    
    # Check if LaTeX math delimiters are preserved
    first_card = cards[0]
    assert '$' in first_card['fields'][0]  # Front should contain LaTeX
    assert '$' in first_card['fields'][1]  # Back should contain LaTeX
    
    # Check if specific mathematical symbols are preserved
    assert r'\to' in first_card['fields'][0] or r'\to' in first_card['fields'][1]
    assert r'f^{-1}' in first_card['fields'][0] or r'f^{-1}' in first_card['fields'][1]

def test_card_model():
    content = r"""
    \begin{theorem}
    The composition of continuous functions is continuous.
    \end{theorem}
    """
    
    cards = generate_anki_cards(content, 'tex')
    assert len(cards) > 0
    
    # Check if cards use the correct model
    first_card = cards[0]
    assert first_card['model'] == BASIC_MODEL
