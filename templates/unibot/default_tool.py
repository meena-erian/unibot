# Default tool template for new Tool.code fields

import requests
from bs4 import BeautifulSoup
import re

def summarize_webpage(url: str, max_sentences: int = 3) -> str:
    """
    Fetches the web page at the given URL and returns a summary of its content.
    """
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        # Remove scripts/styles
        for tag in soup(['script', 'style']):
            tag.decompose()
        text = soup.get_text(separator=' ')
        # Collapse whitespace and split into sentences
        text = re.sub(r'\s+', ' ', text)
        sentences = re.split(r'(?<=[.!?]) +', text)
        summary = ' '.join(sentences[:max_sentences])
        return summary if summary else 'No summary could be generated.'
    except Exception as e:
        return f"Error fetching or summarizing the web page: {e}"


tool_definition = {
    "name": "summarize_webpage",
    "description": "Fetches a web page and returns a summary of its content.",
    "parameters": {
        "url": {"type": "str", "description": "The URL of the web page to summarize."},
        "max_sentences": {"type": "int", "description": "Maximum number of sentences in the summary.", "default": 3}
    },
    "run": summarize_webpage
} 