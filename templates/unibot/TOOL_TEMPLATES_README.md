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

## Using Credentials in a Tool

If your tool requires credentials, use `get_credentials`:

```python
from unibot.services.credentials import get_credentials

def fetch_data_with_openai_api_key(query: str):
    creds = get_credentials([
        {"key": "OPENAI_API_KEY_FOR_SUMMARIZER_TOOL", "label": "OpenAI API Key for Summarizer Tool", "type": "password", "placeholder": "Enter your OpenAI API key for summarization"}
    ])
    if creds is None:
        return "Please set up your OpenAI API key to use this tool."
    api_key = creds["OPENAI_API_KEY_FOR_SUMMARIZER_TOOL"]
    # Use api_key to fetch data from OpenAI...
```

You can require multiple fields and use advanced options:

```python
def create_github_issue():
    creds = get_credentials([
        {"key": "GITHUB_PERSONAL_ACCESS_TOKEN_FOR_ISSUE_CREATOR", "type": "password", "min_length": 40, "max_length": 100, "description": "Your GitHub personal access token for creating issues", "required": True},
        {"key": "GITHUB_USERNAME_FOR_ISSUE_CREATOR", "type": "text", "min_length": 4, "max_length": 39, "description": "Your GitHub username for issue creation", "required": True}
    ])
    if creds is None:
        return "Please set up your GitHub credentials."
    token = creds["GITHUB_PERSONAL_ACCESS_TOKEN_FOR_ISSUE_CREATOR"]
    username = creds["GITHUB_USERNAME_FOR_ISSUE_CREATOR"]
    # Use token and username to create a GitHub issue...
```
