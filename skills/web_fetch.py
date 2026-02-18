"""
web_fetch Skill
Created: 2026-02-18 20:38:55
Updated: 2026-02-18 - Added detailed behavior spec
Description: Fetch and parse webpage content

Behavior:
- Fetches webpage content and extracts readable text
- Returns structured data including title, description, and content preview
- After receiving the result, you should analyze and summarize the content for the user
- Do not return raw content to user; always provide a helpful summary
"""

import requests
import re
import logging
import json


def execute(args=None):
    """
    Fetch webpage content and return structured data.
    
    The caller (AI Assistant) should:
    1. Extract key information from the result
    2. Provide a concise summary to the user
    3. Answer any specific questions about the content
    
    Args:
        args: URL to fetch
            Example: https://example.com

    Returns:
        dict: Structured page data with keys:
            - url: The fetched URL
            - title: Page title
            - description: Meta description (if available)
            - content: Extracted text content (first ~2000 chars)
            - content_length: Total content size
    """
    try:
        if not args:
            return {"error": "Please provide a URL"}

        url = args.strip()

        # Validate URL
        if not url.startswith(("http://", "https://")):
            return {"error": f"Invalid URL: {url}"}

        # Fetch webpage
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "DNT": "1",
            "Connection": "keep-alive",
        }

        response = requests.get(
            url, 
            headers=headers, 
            timeout=30,
            allow_redirects=True,
            verify=True
        )
        response.raise_for_status()
        
        # Ensure proper encoding
        if response.encoding is None:
            response.encoding = 'utf-8'

        # Extract content
        content_type = response.headers.get("content-type", "").lower()

        if "text/html" in content_type:
            return _process_html(response.text, url)
        elif "application/json" in content_type:
            return _process_json(response.text, url)
        else:
            # Other content type
            return {
                "url": url,
                "title": "Unknown",
                "description": None,
                "content": response.text[:2000],
                "content_length": len(response.text),
                "content_type": content_type
            }

    except requests.exceptions.Timeout:
        return {"error": "Request timeout (>30s). The server may be slow or unreachable."}
    except requests.exceptions.SSLError as e:
        return {"error": f"SSL Certificate error: {e}"}
    except requests.exceptions.ConnectionError as e:
        return {"error": f"Connection failed: {e}"}
    except requests.exceptions.RequestException as e:
        return {"error": f"Failed to fetch page: {e}"}
    except Exception as e:
        logging.error(f"Error in web_fetch: {e}", exc_info=True)
        return {"error": str(e)}


def _process_html(html, url):
    """Process HTML content and extract readable text."""
    # Remove script tags and their content
    html = re.sub(r'<script[^>]*>.*?</script>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
    # Remove style tags and their content  
    html = re.sub(r'<style[^>]*>.*?</style>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
    # Remove noscript tags
    html = re.sub(r'<noscript[^>]*>.*?</noscript>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
    # Remove iframe tags
    html = re.sub(r'<iframe[^>]*>.*?</iframe>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
    # Remove SVG content
    html = re.sub(r'<svg[^>]*>.*?</svg>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
    # Remove canvas tags
    html = re.sub(r'<canvas[^>]*>.*?</canvas>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
    
    # Extract title
    title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
    title = title_match.group(1).strip() if title_match else "No title"
    title = re.sub(r'\s+', ' ', title).strip()
    
    # Extract meta description
    desc_match = re.search(r'<meta[^>]*name=["\']description["\'][^>]*content=["\']([^"\']+)', html, re.IGNORECASE)
    if not desc_match:
        desc_match = re.search(r'<meta[^>]*content=["\']([^"\']+)["\'][^>]*name=["\']description["\']', html, re.IGNORECASE)
    meta_desc = desc_match.group(1).strip() if desc_match else None
    
    # Remove all remaining HTML tags
    text = re.sub(r'<[^>]+>', ' ', html)
    
    # Clean up whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    # Return structured data
    return {
        "url": url,
        "title": title,
        "description": meta_desc,
        "content": text[:3000],  # First 3000 chars
        "content_length": len(text)
    }


def _process_json(text, url):
    """Process JSON content."""
    try:
        data = json.loads(text)
        return {
            "url": url,
            "title": "JSON Data",
            "description": None,
            "content": json.dumps(data, indent=2, ensure_ascii=False)[:3000],
            "content_length": len(text),
            "is_json": True
        }
    except Exception as e:
        return {
            "url": url,
            "title": "JSON (parse error)",
            "description": str(e),
            "content": text[:3000],
            "content_length": len(text)
        }


def register_skills(skill_manager):
    """
    Register this skill with the skill manager.
    
    IMPORTANT: When this skill is called, you (the AI) should:
    1. Review the returned structured data (title, description, content)
    2. Extract the most relevant information based on the user's question
    3. Provide a clear, concise summary - DO NOT return raw JSON to the user
    4. If the user asked a specific question, answer it based on the content
    5. If content is truncated, mention that there's more content available
    
    Example workflow:
    User: "What does this page say? https://example.com"
    You: <call_skill>web_fetch:https://example.com</call_skill>
    System: Returns structured data
    You: "Based on the page content: [provide summary]"
    """
    skill_manager.register(
        "web_fetch",
        "Fetch webpage content and return structured data (title, description, content). YOU must analyze the result and provide a helpful summary to the user - never return raw data.",
        execute
    )
