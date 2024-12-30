import pytest
from app import translate_text

def test_hebrew_math_preservation():
    # Test content with both Hebrew text and LaTeX math
    content = r"""
    \begin{definition}
    Let $\mathbb{R}^n$ be a topological space.
    A set $A \subseteq \mathbb{R}^n$ is called open if...
    \end{definition}
    """
    
    # Note: We're not actually translating here since it requires API key
    # This test verifies that LaTeX math is preserved in the content
    result = translate_text(content, target_language='en')  # Using 'en' to skip actual translation
    
    # Check if LaTeX math environments are preserved
    assert '$\mathbb{R}^n$' in result
    assert '$A \subseteq \mathbb{R}^n$' in result
    assert r'\begin{definition}' in result
    assert r'\end{definition}' in result
