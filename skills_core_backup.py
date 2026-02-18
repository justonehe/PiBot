import os
import subprocess
import requests
import json
from pathlib import Path
import time
from datetime import datetime

# ============================================================================
# Original Skills
# ============================================================================

def read_file(path):
    """Read file content (safe check)"""
    try:
        path = path.strip()
        if not os.path.exists(path):
            return f"Error: File '{path}' not found."
        with open(path, 'r') as f:
            content = f.read(2048) # Limit size
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
        # Security: Be careful with this!
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        return f"Output:\n{res.stdout}\nError:\n{res.stderr}"
    except Exception as e:
        return f"Error running shell: {e}"

def install_skill(url_args):
    """
    Download a skill from a URL.
    Args: url (or url|filename)
    """
    try:
        if "|" in url_args:
            url, filename = url_args.split("|", 1)
        else:
            url = url_args
            filename = url.split("/")[-1]
            if not filename.endswith(".py"):
                filename = "new_skill.py"

        # Security check: only allow writing to skills/ dir
        target_path = Path("skills") / filename
        target_path.parent.mkdir(parents=True, exist_ok=True)

        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            with open(target_path, "w") as f:
                f.write(response.text)
            return f"Skill downloaded to {target_path}. Please restart Master to load it."
        else:
            return f"Download failed: {response.status_code}"
    except Exception as e:
        return f"Install failed: {e}"

def take_photo(args=None):
    """
    Take a photo using system camera.
    Returns markdown image link.
    """
    try:
        timestamp = int(time.time())
        filename = f"photo_{timestamp}.jpg"
        # Ensure static dir exists in HOME/static
        # Since this runs on Master, we assume CWD is HOME or we use absolute path
        # skill_manager.py runs in ~/master_hub.py context usually
        static_dir = Path("static")
        static_dir.mkdir(exist_ok=True)

        filepath = static_dir / filename

        # Try libcamera (RPi) first, then fswebcam (USB)
        cmd1 = f"libcamera-jpeg -o {filepath} -t 1 --width 640 --height 480 --nopreview"
        res = subprocess.run(cmd1, shell=True, capture_output=True)

        if res.returncode != 0:
            # Fallback to fswebcam
            cmd2 = f"fswebcam -r 640x480 --no-banner {filepath}"
            res = subprocess.run(cmd2, shell=True, capture_output=True)

        if filepath.exists() and filepath.stat().st_size > 0:
            return f"![Live Photo](/static/{filename})"
        else:
            return f"Photo failed. Libcamera: {res.stderr}"
    except Exception as e:
        return f"Photo Exception: {e}"

# ============================================================================
# New Skill Management Skills
# ============================================================================

def create_skill(args):
    """
    Create a new skill from template.
    Args: skill_name||description or skill_name (uses default description)

    Examples:
    - create_skill: weather||Get weather information
    - create_skill: calculator
    """
    try:
        # Parse arguments
        if args and "||" in args:
            skill_name, description = args.split("||", 1)
        elif args:
            skill_name = args.strip()
            description = f"Skill: {skill_name}"
        else:
            return "Error: Please provide skill name. Usage: create_skill: name||description"

        # Validate skill name
        skill_name = skill_name.strip().lower().replace(" ", "_").replace("-", "_")
        if not skill_name.isidentifier() or not skill_name[0].isalpha():
            return f"Error: Invalid skill name '{skill_name}'. Use letters, numbers, underscores, start with letter."

        skills_dir = Path("skills")
        skills_dir.mkdir(exist_ok=True)

        skill_file = skills_dir / f"{skill_name}.py"

        # Check if skill already exists
        if skill_file.exists():
            return f"Error: Skill '{skill_name}' already exists at {skill_file}"

        # Generate skill template
        template = f'''"""
{skill_name.capitalize()} Skill
Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
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
        # Example: Process args, run commands, call APIs, etc.

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

        # Write skill file
        with open(skill_file, 'w') as f:
            f.write(template)

        # Success message
        result = f"""✅ Skill '{skill_name}' created successfully!

📁 Location: {skill_file.absolute()}
📝 Description: {description}

📚 Next Steps:
1. Edit the skill file to implement your logic
2. Find the execute() function and add your code
3. Reload skills: Restart Master or send 'reload_skills' command
4. Test: Try using <call_skill>{skill_name}:your_args</call_skill>

💡 Tips:
- Keep execute() simple and focused
- Return clear, human-readable messages
- Use try/except to handle errors gracefully
- Add logging for debugging

🔍 Example Usage:
  <call_skill>{skill_name}:test_argument</call_skill>
"""

        return result

    except Exception as e:
        return f"Error creating skill: {e}"


def list_skills(args=None):
    """
    List all available skills with descriptions.

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

            # Try to extract description from file
            try:
                with open(skill_file, 'r') as f:
                    content = f.read()
                    # Extract docstring description
                    if '"""' in content:
                        desc_lines = content.split('"""')[1].strip().split('\n')
                        desc = desc_lines[0] if desc_lines else "No description"
                    else:
                        desc = "No description"
            except:
                desc = "Error reading description"

            result += f"• **{skill_file.stem}**: {desc}\n"

        return result.strip()

    except Exception as e:
        return f"Error listing skills: {e}"


def reload_skills(args=None):
    """
    Signal skill manager to reload skills.
    Note: This creates a marker file that master_hub.py checks.

    Args:
        args: Ignored

    Returns:
        str: Status message
    """
    try:
        # Create a marker file
        marker = Path(".reload_skills")
        marker.touch()

        return "✅ Reload signal sent. Skills will be reloaded on next API call.\n💡 Note: This doesn't immediately reload running processes, but new chat requests will use updated skills."

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
    return """🛠️ Skill Management Help

📌 Available Commands:

1. **create_skill** - Create a new skill template
   Usage: <call_skill>create_skill:name||description</call_skill>
   Example: <call_skill>create_skill:weather||Get weather info</call_skill>

2. **list_skills** - List all available skills
   Usage: <call_skill>list_skills</call_skill>

3. **reload_skills** - Reload skill registry
   Usage: <call_skill>reload_skills</call_skill>

📚 Skill Structure:
```python
# skills/my_skill.py

def execute(args=None):
    """Your skill logic here"""
    # Process args
    # Return result
    return "Result"

def register_skills(skill_manager):
    """Register with skill_manager"""
    skill_manager.register(
        "skill_name",
        "Description",
        execute
    )
```

💡 Best Practices:
- Keep skills focused on single responsibility
- Use clear, descriptive names
- Handle errors gracefully
- Return human-readable messages
- Add logging for debugging

🔍 Skill Discovery:
Skills are auto-loaded from skills/ directory on startup.
Each .py file should have register_skills() function.
"""


# ============================================================================
# Skill Registration
# ============================================================================

def register_skills(skill_manager):
    """Register all core skills including new management skills"""
    # Original skills
    skill_manager.register("read_file", "Read file content. Args: path", read_file)
    skill_manager.register("write_file", "Write content to file. Args: path||content", write_file)
    skill_manager.register("run_cmd", "Run shell command on Master. Args: cmd", run_shell)
    skill_manager.register("install_skill", "Download python skill from URL. Args: url", install_skill)
    skill_manager.register("take_photo", "Take a photo. No args required.", take_photo)

    # New skill management skills
    skill_manager.register("create_skill", "Create a new skill template. Args: name||description", create_skill)
    skill_manager.register("list_skills", "List all available skills. No args", list_skills)
    skill_manager.register("reload_skills", "Reload skill registry. No args", reload_skills)
    skill_manager.register("skill_help", "Show skill management help. No args", skill_help)
