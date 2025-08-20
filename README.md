# Unibot - Django AI Bot Framework

A Django app for creating and managing AI-powered bots with tool integration, credential management, and message handling.

## Overview

Unibot provides a framework for building AI bots that can:
- Execute custom tools and functions
- Manage encrypted credentials securely
- Handle message processing with OpenAI integration
- Provide administrative interfaces for bot and tool management
- Support credential setup workflows

## Dependencies

### Required Django Apps
- **unicom**: Core messaging and account management system
  - Provides `Account`, `Message`, `RequestCategory` models
  - Provides `get_public_origin` service

### Required Python Packages
- `django>=4.2`
- `openai` - OpenAI API integration
- `cryptography>=42.0.0` - For credential encryption
- `django-reversion>=5.0.0` - Model versioning
- `python-dotenv>=1.0.0` - Environment variable management

### Optional Dependencies
- `django-ace` - Code editor widget for admin interface

## Configuration

### Environment Variables
Add these to your Django settings:

```python
# OpenAI API Key
OPENAI_API_KEY = 'your-openai-api-key'

# Credential encryption key (URL-safe base64-encoded 32-byte key)
CREDENTIAL_ENCRYPTION_KEY = 'your-encryption-key'
```

### Django Settings
Add to your `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    # ... other apps
    'unicom',  # Required dependency
    'unibot',
    'reversion',  # Required for model versioning
]
```

Add to your `MIDDLEWARE`:

```python
MIDDLEWARE = [
    # ... other middleware
    'reversion.middleware.RevisionMiddleware',
]
```

### URL Configuration
Include unibot URLs in your main `urls.py`:

```python
from django.urls import path, include

urlpatterns = [
    # ... other URLs
    path('unibot/', include('unibot.urls')),
]
```

## Models

### Core Models
- **Bot**: AI bot configurations with custom code and tool associations
- **Tool**: Reusable functions that bots can execute
- **EncryptedCredential**: Secure storage for API keys and sensitive data
- **CredentialFieldDefinition**: Schema definitions for credential fields
- **CredentialSetupSession**: Time-limited sessions for credential configuration

## Getting Started

### 1. Installation
Ensure all dependencies are installed in your Django project:

```bash
pip install django>=4.2 openai cryptography>=42.0.0 django-reversion>=5.0.0
```

### 2. Database Migration
Run migrations to create the necessary database tables:

```bash
python manage.py migrate unibot
```

### 3. Create Superuser (if needed)
```bash
python manage.py createsuperuser
```

### 4. Access Admin Interface
Navigate to `/admin/` and look for the "Unibot" section to start creating bots and tools.

### 5. Create Admin Tools
Run the management command to create default admin tools:

```bash
python manage.py create_admin_tools
```

## Usage

### Creating Bots
1. Go to Django admin → Unibot → Bots
2. Create a new bot with custom Python code
3. Associate tools with your bot
4. The bot will automatically get a RequestCategory for message routing

### Creating Tools
1. Go to Django admin → Unibot → Tools
2. Create reusable tools with Python code
3. Tools must define a `tool_definition` dictionary
4. See template examples in `templates/unibot/`

### Managing Credentials
1. Define credential field schemas using CredentialFieldDefinition
2. Create setup sessions for users to input credentials
3. Credentials are automatically encrypted and stored securely

### Running Bot Worker
To process incoming requests:

```bash
python manage.py run_worker
```

## Templates and Examples

The app includes template files in `templates/unibot/`:
- Bot templates with examples
- Tool templates for common use cases
- Credential setup forms
- Documentation files (`BOT_TEMPLATES_README.md`, `TOOL_TEMPLATES_README.md`)

## Integration with Other Projects

To use this app in another Django project:

1. Ensure you have the `unicom` app or equivalent models
2. Install all required dependencies
3. Add `unibot` to your `INSTALLED_APPS`
4. Configure environment variables
5. Run migrations
6. Include URLs if needed

## Security Notes

- All credentials are encrypted using Fernet encryption
- API keys and sensitive data are never stored in plain text
- Credential setup sessions are time-limited and attempt-limited
- Bot code execution is isolated but should be reviewed for security

## API Integration

The app integrates with:
- OpenAI API for language model functionality
- Custom tool execution framework
- Django's admin interface for management

## Development

### File Structure
```
unibot/
├── models.py          # Core models
├── admin.py           # Django admin configuration
├── views.py           # Web views for credential setup
├── urls.py            # URL routing
├── services/          # Business logic services
│   ├── llm_handler.py     # OpenAI integration
│   ├── credentials.py     # Credential management
│   └── tool_result_handler.py  # Tool execution
├── management/
│   └── commands/
│       └── run_worker.py  # Background worker
├── templates/
│   └── unibot/        # Templates and examples
└── migrations/        # Database migrations
```

## License

[Add your license information here]