"""
PiBot V3 - Enhanced Skills Module with Intelligent Template Generation
包含智能技能模板：自动识别常见模式并生成实用代码
"""

import os
import subprocess
import requests
from pathlib import Path
import time
from datetime import datetime
import re
import json
import logging

# ============================================================================
# Core Skills (Original)
# ============================================================================


def read_file(path):
    """Read file content (safe check)"""
    try:
        path = path.strip()
        if not os.path.exists(path):
            return f"Error: File '{path}' not found."
        with open(path, "r") as f:
            content = f.read(2048)  # Limit size
            if len(content) == 2048:
                content += "\n...(truncated)..."
            return content
    except Exception as e:
        return f"Error reading file: {e}"


def write_file(args):
    """Write/Append file. Format: PATH||CONTENT or PATH||APPEND||CONTENT"""
    try:
        parts = args.split("||")
        path = parts[0].strip()
        mode = "w"
        content = ""

        if len(parts) == 2:
            content = parts[1]
        elif len(parts) == 3 and parts[1].lower() == "append":
            mode = "a"
            content = parts[2]
        else:
            return "Error: Invalid format. Use PATH||CONTENT"

        with open(path, mode) as f:
            f.write(content)
        return f"Success: Wrote to {path}"
    except Exception as e:
        return f"Error writing file: {e}"


def run_shell(cmd):
    """Run shell command on Master (Local)"""
    try:
        res = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=10
        )
        return f"Output:\n{res.stdout}\nError:\n{res.stderr}"
    except Exception as e:
        return f"Error running shell: {e}"


def install_skill(url_args):
    """Download a skill from a URL. Args: url (or url|filename)"""
    try:
        if "|" in url_args:
            url, filename = url_args.split("|", 1)
        else:
            url = url_args
            filename = url.split("/")[-1]
            if not filename.endswith(".py"):
                filename = "new_skill.py"

        target_path = Path("skills") / filename
        target_path.parent.mkdir(parents=True, exist_ok=True)

        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            with open(target_path, "w") as f:
                f.write(response.text)
            return (
                f"Skill downloaded to {target_path}. Please restart Master to load it."
            )
        else:
            return f"Download failed: {response.status_code}"
    except Exception as e:
        return f"Install failed: {e}"


def take_photo(args=None):
    """Take a photo using system camera. Returns markdown image link."""
    try:
        timestamp = int(time.time())
        filename = f"photo_{timestamp}.jpg"
        static_dir = Path("static")
        static_dir.mkdir(exist_ok=True)
        filepath = static_dir / filename

        cmd1 = f"libcamera-jpeg -o {filepath} -t 1 --width 640 --height 480 --nopreview"
        res = subprocess.run(cmd1, shell=True, capture_output=True)

        if res.returncode != 0:
            cmd2 = f"fswebcam -r 640x480 --no-banner {filepath}"
            res = subprocess.run(cmd2, shell=True, capture_output=True)

        if filepath.exists() and filepath.stat().st_size > 0:
            return f"![Live Photo](/static/{filename})"
        else:
            return f"Photo failed. Libcamera: {res.stderr}"
    except Exception as e:
        return f"Photo Exception: {e}"


# ============================================================================
# Skill Template Generators (NEW - Smart Pattern Recognition)
# ============================================================================


def generate_web_fetch_skill(skill_name, description):
    """Generate web_fetch skill with actual implementation"""
    template = f'''"""
{skill_name.capitalize()} Skill
Created: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
Description: {description}
"""

import requests
import re
import logging

def execute(args=None):
    """
    Fetch and process webpage content.

    Args:
        args: URL only, or URL||instruction
            Examples:
            - https://example.com
            - https://example.com||Summarize this page

    Returns:
        str: Webpage content or processed result
    """
    try:
        if not args:
            return "Error: Please provide a URL. Usage: web_fetch:URL"

        # Parse args
        if "||" in args:
            url, instruction = args.split("||", 1)
            url = url.strip()
            instruction = instruction.strip()
        else:
            url = args.strip()
            instruction = None

        # Validate URL
        if not url.startswith(("http://", "https://")):
            return f"Error: Invalid URL: {{url}}"

        # Fetch webpage
        headers = {{
            "User-Agent": "Mozilla/5.0 (PiBot V3; WebFetch)"
        }}
        
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        # Extract content
        content_type = response.headers.get("content-type", "").lower()
        
        if "text/html" in content_type:
            # HTML page - extract text content
            text = re.sub(r'<[^<]+?>', ' ', response.text)  # Remove HTML tags
            text = re.sub(r'\\s+', ' ', text)  # Normalize whitespace
            text = text.strip()
            
            # Extract title
            title_match = re.search(r'<title>(.*?)</title>', response.text, re.IGNORECASE)
            title = title_match.group(1).strip() if title_match else "No title"
            
            # Get first 500 chars for preview
            preview = text[:500]
            if len(text) > 500:
                preview += "..."
            
            if instruction:
                return f"""📄 **{{title}}**

📝 Content Preview:
{{preview}}

💡 Instruction: {{instruction}}

✅ Fetched successfully ({{len(response.text)}} bytes)"""
            else:
                return f"""📄 **{{title}}**

📝 Content:
{{preview}}

✅ Fetched {{len(response.text)}} bytes from {{url}}"""
        elif "application/json" in content_type:
            # JSON data
            try:
                data = response.json()
                json_str = json.dumps(data, indent=2, ensure_ascii=False)[:500]
                if len(json.dumps(data)) > 500:
                    json_str += "..."
                return f"📦 JSON Data:\\n```json\\n{{json_str}}\\n```\\n✅ Fetched {{len(response.text)}} bytes"
            except:
                return f"📦 JSON (raw): {{response.text[:500]}}"
        else:
            # Other content type
            return f"📄 {{content_type}}\\nContent length: {{len(response.text)}} bytes\\nPreview: {{response.text[:200]}}..."
            
    except requests.exceptions.Timeout:
        return "Error: Request timeout (>15s). The server may be slow or unreachable."
    except requests.exceptions.RequestException as e:
        return f"Error: Failed to fetch page: {{e}}"
    except Exception as e:
        logging.error(f"Error in {skill_name}: {{e}}")
        return f"Error: {{e}}"


def register_skills(skill_manager):
    """
    Register this skill with the skill manager.

    Args:
        skill_manager: SkillManager instance
    """
    skill_manager.register(
        "{skill_name}",
        "{description}",
        execute
    )
'''

    return template


def generate_shell_cmd_skill(skill_name, description):
    """Generate shell command execution skill"""
    template = f'''"""
{skill_name.capitalize()} Skill
Created: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
Description: {description}
"""

import subprocess
import logging

def execute(args=None):
    """
    Execute shell command safely.

    Args:
        args: Command to execute

    Returns:
        str: Command output
    """
    try:
        if not args:
            return "Error: Please provide a command to execute"

        cmd = args.strip()
        
        # Security check: block dangerous commands
        dangerous_patterns = ["rm -rf /", "mkfs", "dd if=", ":(){" + ":|: };"]
        for pattern in dangerous_patterns:
            if pattern in cmd:
                return f"Error: Dangerous command blocked for safety: {{cmd[:50]}}"

        # Execute with timeout
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        
        output = result.stdout.strip()
        error = result.stderr.strip()
        
        if result.returncode == 0:
            if output:
                return f"✅ Command executed successfully.\\n\\nOutput:\\n{{output}}"
            else:
                return "✅ Command executed successfully (no output)"
        else:
            return f"⚠️ Command failed (exit code {{result.returncode}})\\n\\nError output:\\n{{error}}"
            
    except subprocess.TimeoutExpired:
        return "Error: Command timeout (>30s)"
    except Exception as e:
        logging.error(f"Error in {skill_name}: {{e}}")
        return f"Error: {{e}}"


def register_skills(skill_manager):
    """
    Register this skill with the skill manager.

    Args:
        skill_manager: SkillManager instance
    """
    skill_manager.register(
        "{skill_name}",
        "{description}",
        execute
    )
'''

    return template


def generate_default_skill(skill_name, description):
    """Generate generic skill template"""
    template = f'''"""
{skill_name.capitalize()} Skill
Created: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
Description: {description}
"""

import os
import subprocess
import logging

def execute(args=None):
    """
    Execute the {skill_name} skill.

    Args:
        args: Command arguments (string or None)

    Returns:
        str: Result message or output
    """
    try:
        # TODO: Implement your skill logic here
        # Examples:
        # - Process args
        # - Run commands
        # - Call APIs
        # - Read/write files

        if args:
            return f"Executed {skill_name} with args: {{args}}"
        else:
            return f"Executed {skill_name} (no args)"

    except Exception as e:
        logging.error(f"Error in {skill_name}: {{e}}")
        return f"Error: {{e}}"


def register_skills(skill_manager):
    """
    Register this skill with the skill manager.

    Args:
        skill_manager: SkillManager instance
    """
    skill_manager.register(
        "{skill_name}",
        "{description}",
        execute
    )
'''

    return template


# ============================================================================
# Enhanced Skill Management Skills
# ============================================================================


def create_skill(args):
    """
    Create a new skill with intelligent template generation.

    Recognizes common patterns:
    - web_fetch*: Auto-generates web scraping code
    - *fetch*: Auto-generates data fetching code
    - shell*: Auto-generates command execution code
    - *cmd*: Auto-generates command execution code
    - Others: Generic template

    Args:
        args: skill_name||description

    Examples:
        create_skill:web_fetch||Get webpage content
        create_skill:run_shell||Execute shell commands
        create_skill:my_skill||Custom skill
    """
    try:
        # Parse arguments
        if args and "||" in args:
            skill_name, description = args.split("||", 1)
        elif args:
            skill_name = args.strip()
            description = f"Skill: {skill_name}"
        else:
            return "Error: Please provide skill name.\nUsage: create_skill:name||description"

        # Validate skill name
        skill_name = skill_name.strip().lower().replace(" ", "_").replace("-", "_")
        if not skill_name.isidentifier() or not skill_name[0].isalpha():
            return f"Error: Invalid skill name '{skill_name}'.\nUse letters, numbers, underscores, start with letter."

        skills_dir = Path("skills")
        skills_dir.mkdir(exist_ok=True)
        skill_file = skills_dir / f"{skill_name}.py"

        # Check if skill already exists
        if skill_file.exists():
            return f"Error: Skill '{skill_name}' already exists at {skill_file}"

        # Intelligent template generation based on skill name pattern
        pattern_matchers = [
            (r"^web_fetch", generate_web_fetch_skill),
            (r".*_?fetch", generate_web_fetch_skill),
            (r"shell.*cmd", generate_shell_cmd_skill),
            (r".*_?cmd", generate_shell_cmd_skill),
        ]

        template = None
        for pattern, generator in pattern_matchers:
            if re.match(pattern, skill_name, re.IGNORECASE):
                logging.info(f"Matched pattern: {pattern}, using intelligent generator")
                template = generator(skill_name, description)
                break

        # Default to generic template if no pattern matched
        if template is None:
            logging.info(f"No pattern matched, using default template")
            template = generate_default_skill(skill_name, description)

        # Write skill file
        with open(skill_file, "w") as f:
            f.write(template)

        # Enhanced success message
        is_smart = (
            "✨ Smart template"
            if template != generate_default_skill(skill_name, description)
            else "📝 Standard template"
        )

        result = f"""✅ Skill '{skill_name}' created successfully! {is_smart}

📁 Location: {skill_file.absolute()}
📝 Description: {description}

📚 Implementation Details:
"""

        if template != generate_default_skill(skill_name, description):
            result += "\n🤖 Auto-generated implementation included:\n"
            result += "   - Web fetching with requests library\n"
            result += "   - HTML tag removal and text extraction\n"
            result += "   - JSON data support\n"
            result += "   - Error handling and timeouts\n"
        else:
            result += "\n📝 Next Steps:\n"
            result += "1. Edit the skill file to implement your logic\n"
            result += "   Command: nano skills/{skill_name}.py\n"
            result += "2. Find the execute() function and add your code\n"

        result += f"""
3. Test the skill
   Command: <call_skill>{skill_name}:test_args</call_skill>

4. Skills are auto-loaded on restart
   To reload: <call_skill>reload_skills</call_skill>

💡 Quick Test:
   <call_skill>{skill_name}:https://example.com</call_skill>
"""

        return result

    except Exception as e:
        return f"Error creating skill: {e}"


def list_skills(args=None):
    """
    List all available skills with descriptions and sizes.

    Args:
        args: Ignored (for consistency)

    Returns:
        str: Formatted list of skills
    """
    try:
        skills_dir = Path("skills")
        if not skills_dir.exists():
            return "No skills directory found."

        skill_files = list(skills_dir.glob("*.py"))
        if not skill_files:
            return "No skills found."

        result = "📚 Available Skills:\n\n"

        for skill_file in sorted(skill_files):
            if skill_file.name.startswith("__"):
                continue

            # Get file size
            try:
                size_kb = skill_file.stat().st_size / 1024
                size_info = f" ({size_kb:.1f}KB)"
            except:
                size_info = ""

            # Extract description
            try:
                with open(skill_file, "r") as f:
                    content = f.read()
                    if '"""' in content:
                        parts = content.split('"""')
                        if len(parts) >= 2:
                            docstring_lines = parts[1].strip().split("\n")
                            for line in docstring_lines[:5]:
                                if line.startswith("Description:"):
                                    desc = line.split("Description:", 1)[1].strip()
                                    break
                                elif line.strip() and not line.startswith("Created:"):
                                    desc = line.strip()
                                    break
                            else:
                                desc = "No description"
                        else:
                            desc = "No description"
                    else:
                        desc = "No description"
            except Exception as e:
                desc = f"Error reading: {e}"

            # Check if it has implementation beyond TODO
            try:
                with open(skill_file, "r") as f:
                    content = f.read()
                    has_impl = (
                        "# TODO:" not in content or 'return f"Executed' not in content
                    )
                impl_status = "✅" if has_impl else "🔧 Template"
            except:
                impl_status = "❓"

            result += f"• **{skill_file.stem}**{size_info} {impl_status}: {desc}\n"

        result += f"\n💡 Total: {len([f for f in skill_files if not f.name.startswith('__')])} skills"
        return result.strip()

    except Exception as e:
        return f"Error listing skills: {e}"


def reload_skills(args=None):
    """
    Signal skill manager to reload skills.
    Creates a marker file that master_hub.py checks.

    Args:
        args: Ignored

    Returns:
        str: Status message
    """
    try:
        marker = Path(".reload_skills")
        marker.touch()

        # Check current skills
        skills_dir = Path("skills")
        if skills_dir.exists():
            skill_count = len(list(skills_dir.glob("*.py")))
            if skill_count > 0:
                return f"""✅ Reload signal sent!

📊 Found {skill_count} skill files
💡 Skills will be reloaded on next API call
🔄 New chat requests will use updated skills
🔍 Tip: Use 'list_skills' to verify loaded skills"""
            else:
                return "✅ Reload signal sent! (No skills found)"
        else:
            return "✅ Reload signal sent! (No skills directory)"

    except Exception as e:
        return f"Error signaling reload: {e}"


def skill_help(args=None):
    """
    Show help for creating and managing skills.

    Args:
        args: Ignored

    Returns:
        str: Help text
    """
    return """🛠️ PiBot Skill Management Help

📌 Available Commands:

1️⃣ **create_skill** - Create a new skill (with smart templates)
   Usage: <call_skill>create_skill:name||description</call_skill>
   
   Smart Patterns:
   • web_fetch* → Auto-generates web scraping code
   • *fetch* → Auto-generates data fetching code
   • shell*cmd → Auto-generates command execution
   • Others → Generic template

   Examples:
   • <call_skill>create_skill:web_fetch||Get web content</call_skill>
   • <call_skill>create_skill:data_fetch||Fetch API data</call_skill>
   • <call_skill>create_skill:run_cmd||Execute commands</call_skill>

2️⃣ **list_skills** - List all skills with implementation status
   Usage: <call_skill>list_skills</call_skill>
   Shows: All skills with descriptions, sizes, and ✅/🔧 status

3️⃣ **reload_skills** - Reload skill registry
   Usage: <call_skill>reload_skills</call_skill>
   Effect: Skills reload on next chat request

4️⃣ **skill_help** - Show this help message
   Usage: <call_skill>skill_help</call_skill>

📚 Smart Templates:

🌐 **web_fetch Pattern** (Automatic web scraping)
```python
# When skill name contains "web_fetch" or ends with "fetch"
- Auto-generates requests-based implementation
- HTML tag removal and text extraction
- JSON data parsing
- Error handling and timeouts
- Instruction processing support

Example:
  <call_skill>create_skill:web_fetch||Get webpage content</call_skill>
  <call_skill>web_fetch:https://example.com</call_skill>
  <call_skill>web_fetch:https://example.com||Summarize</call_skill>
```

⚙️ **Shell Command Pattern** (Automatic command execution)
```python
# When skill name contains "shell" or "cmd"
- Auto-generates subprocess-based implementation
- Security checks for dangerous commands
- Timeout protection (30s)
- Stdout/stderr capture

Example:
  <call_skill>create_skill:run_cmd||Execute commands</call_skill>
  <call_skill>run_cmd:ls -la</call_skill>
```

🔧 **Generic Pattern** (Custom implementation)
```python
# All other skills
- Generates basic template with TODO comments
- Requires manual implementation
- Flexible structure for custom logic

Example:
  <call_skill>create_skill:my_skill||Custom task</call_skill>
```

💡 Best Practices:
• Use descriptive skill names with patterns for auto-implementation
• Test skills with safe inputs first
• Use reload_skills after editing to pick up changes
• Check implementation status with list_skills

🔍 Skill Discovery:
Skills are auto-loaded from skills/ directory on startup.
New skills appear after restart or reload.
"""


# ============================================================================
# Skill Registration
# ============================================================================


def register_skills(skill_manager):
    """
    Register all core skills including enhanced management skills.

    Args:
        skill_manager: SkillManager instance
    """
    # Original core skills
    skill_manager.register("read_file", "Read file content. Args: path", read_file)
    skill_manager.register(
        "write_file", "Write content to file. Args: path||content", write_file
    )
    skill_manager.register(
        "run_cmd", "Run shell command on Master. Args: cmd", run_shell
    )
    skill_manager.register(
        "install_skill", "Download python skill from URL. Args: url", install_skill
    )
    skill_manager.register("take_photo", "Take a photo. No args required.", take_photo)

    # Enhanced skill management skills
    skill_manager.register(
        "create_skill",
        "Create skill with smart templates. Args: name||description",
        create_skill,
    )
    skill_manager.register(
        "list_skills", "List all skills with status. No args", list_skills
    )
    skill_manager.register(
        "reload_skills", "Reload skill registry. No args", reload_skills
    )
    skill_manager.register(
        "skill_help", "Show skill management help. No args", skill_help
    )
