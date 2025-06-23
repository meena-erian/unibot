## Basic Tool Template

```python
def summarize_webpage(url: str, max_sentences: int = 3) -> str:
    """Fetches and summarizes webpage content"""
    response = requests.get(url, timeout=10)
    soup = BeautifulSoup(response.text, 'html.parser')
    text = soup.get_text(separator=' ')
    sentences = re.split(r'(?<=[.!?]) +', text)
    return ' '.join(sentences[:max_sentences])

tool_definition = {
    "name": "summarize_webpage",
    "description": "Fetches a web page and returns a summary",
    "parameters": {
        "url": {
            "type": "string", 
            "description": "The URL to summarize"
        },
        "max_sentences": {
            "type": "integer", 
            "description": "Maximum sentences",
            "default": 3
        }
    },
    "run": summarize_webpage
}
```
