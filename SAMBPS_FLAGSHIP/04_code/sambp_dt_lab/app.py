"""
SAMBPS DTaaS - Anthropic Connection Module
Connects to Anthropic Claude API for AI-powered analysis
"""

import os
from dotenv import load_dotenv
from anthropic import Anthropic

# Load environment variables
load_dotenv()

# Get API key from environment
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

def get_anthropic_client():
    """
    Initialize and return an Anthropic client.
    Requires ANTHROPIC_API_KEY to be set in .env file.
    """
    if not ANTHROPIC_API_KEY:
        raise ValueError(
            "ANTHROPIC_API_KEY not found. Please set it in a .env file:\n"
            "ANTHROPIC_API_KEY=your_api_key_here"
        )
    
    return Anthropic(api_key=ANTHROPIC_API_KEY)

def test_connection():
    """Test the Anthropic API connection."""
    client = get_anthropic_client()
    
    # Send a simple test message
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=100,
        messages=[{"role": "user", "content": "Hello, please respond with 'Connection successful!'"}]
    )
    
    return message.content[0].text

if __name__ == "__main__":
    try:
        print("Testing Anthropic connection...")
        response = test_connection()
        print(f"Response: {response}")
    except Exception as e:
        print(f"Error: {e}")