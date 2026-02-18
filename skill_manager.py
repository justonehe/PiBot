
import os
import importlib.util
import inspect
import logging

class SkillManager:
    def __init__(self, skills_dir=None):
        if not skills_dir:
            # Default to 'skills' directory relative to this file
            self.skills_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "skills")
        else:
            self.skills_dir = skills_dir
            
        self.skills = {}
        self.skill_descriptions = {}

    def load_skills(self):
        """Load all python skills from skills directory"""
        if not os.path.exists(self.skills_dir):
            logging.warning(f"Skills directory {self.skills_dir} not found.")
            return

        logging.info(f"Loading skills from {self.skills_dir}...")
        
        for filename in os.listdir(self.skills_dir):
            if filename.endswith(".py") and not filename.startswith("__"):
                module_name = filename[:-3]
                file_path = os.path.join(self.skills_dir, filename)
                
                try:
                    spec = importlib.util.spec_from_file_location(module_name, file_path)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    
                    if hasattr(module, "register_skills"):
                        # Smart detection of signature
                        sig = inspect.signature(module.register_skills)
                        if len(sig.parameters) >= 1:
                            # New format: register_skills(manager)
                            module.register_skills(self)
                        else:
                            # Old format: returns list of tuples
                            skills_list = module.register_skills()
                            for name, func, desc in skills_list:
                                self.register(name, desc, func)
                                
                        logging.info(f"Loaded skills from {module_name}")
                    else:
                        logging.warning(f"No register_skills found in {module_name}")
                        
                except Exception as e:
                    logging.error(f"Failed to load skill {module_name}: {e}", exc_info=True)

    def register(self, name, description, func):
        self.skills[name] = func
        self.skill_descriptions[name] = description
        # logging.info(f"Registered skill: {name}")

    def get_prompt(self):
        """Return prompt section describing available skills"""
        if not self.skills:
            return "No skills available."
            
        prompt = "Available Skills (Context Tools):\n"
        for name, desc in self.skill_descriptions.items():
            prompt += f"- {name}: {desc}\n"
        
        prompt += "\nTo call a skill, output: <call_skill>skill_name:args</call_skill>\n"
        prompt += "Example: <call_skill>read_file:/var/log/syslog</call_skill>"
        return prompt

    def execute(self, skill_name, args=None):
        if skill_name not in self.skills:
            return f"Error: Skill '{skill_name}' not found."
        
        try:
            func = self.skills[skill_name]
            # Check if func accepts args
            sig = inspect.signature(func)
            if len(sig.parameters) > 0:
                return func(args) if args else func(None) # Handle Optional args safely? 
                # Better: Check if args provided properly. 
                # For now assume func handles its args (string usually)
            else:
                return func()
        except Exception as e:
            logging.error(f"Error executing skill {skill_name}: {e}", exc_info=True)
            return f"Error executing {skill_name}: {e}"
