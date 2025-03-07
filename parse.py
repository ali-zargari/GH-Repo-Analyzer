import os
import logging
import re
from dotenv import load_dotenv
from openai import OpenAI
import argparse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv(dotenv_path='.env.local')
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Initialize OpenAI client (new SDK 1.0+)
client = OpenAI(api_key=OPENAI_API_KEY)


# Load the markdown file
def load_markdown_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read()
    except Exception as e:
        logger.error(f"Error loading markdown file: {e}")
        return None


# Split the markdown file into individual project sections
def split_projects(markdown_text):
    projects = []
    sections = re.split(r'##\s+', markdown_text)
    
    # Skip the first section (it's the title)
    for section in sections[1:]:
        if not section.strip():
            continue
            
        lines = section.strip().split('\n')
        if not lines:
            continue
            
        # First line is the project name
        project_name = lines[0].strip()
        
        # Initialize project data
        project = {
            'name': project_name,
            'year': None,
            'description': None,
            'tags': []
        }
        
        # Process remaining lines
        description_lines = []
        in_description = False
        
        for line in lines[1:]:
            # Year line
            if line.startswith('**') and '**' in line and not project['year']:
                year_match = re.search(r'\*\*(\d{4})\*\*', line)
                if year_match:
                    project['year'] = year_match.group(1)
            
            # Tag line (contains backticks)
            elif '`' in line and not line.startswith('```'):
                tags = re.findall(r'`([^`]+)`', line)
                project['tags'].extend(tags)
            
            # Description line (not empty, not year, not tags, not separator)
            elif line.strip() and not line.startswith('**') and '`' not in line and '---' not in line:
                description_lines.append(line.strip())
        
        # Join description lines
        if description_lines:
            project['description'] = ' '.join(description_lines).strip()
        
        # Add project to list if it has a name
        if project['name']:
            projects.append(project)
    
    return projects


# Evaluate a project using OpenAI GPT
def evaluate_project(project):
    prompt = f"""
You are an expert project evaluator. Assess the following GitHub project and rate how impressive it is on a scale of 1 (not impressive) to 10 (extremely impressive), considering technical complexity, uniqueness, and potential impact.

After the rating, briefly explain why you gave that score in 2-3 sentences.

Project Name: {project['name']}
Year: {project['year']}
Description: {project['description']}
Technologies: {', '.join(project['tags'])}

Respond in the following format:
Score: <number>
Reason: <your explanation>
"""
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are an expert project evaluator."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=300
        )
        
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Error calling OpenAI API: {e}")
        return f"Error evaluating project: {str(e)}"


# Extract score from evaluation
def extract_score(evaluation):
    match = re.search(r'Score:\s*(\d+(?:\.\d+)?)', evaluation)
    if match:
        return float(match.group(1))
    return 0


# Format project as a card for display
def format_project_card(project, score=None, reason=None):
    # Create a card-like display for the project
    name = project['name']
    year = project['year'] or ""
    description = project['description'] or "No description available."
    tags = ' '.join([f"{tag}" for tag in project['tags']])
    
    # Calculate width based on name length (minimum 70)
    width = max(70, len(name) + 20)
    
    # Format the card
    card = f"""
┌{'─' * width}┐
│ {name} {year.rjust(width - len(name) - 1)} │
├{'─' * width}┤
"""
    
    # Add description with word wrapping
    desc_words = description.split()
    current_line = "│ "
    for word in desc_words:
        if len(current_line + word) > width - 1:
            card += current_line.ljust(width + 1) + "│\n"
            current_line = "│ " + word + " "
        else:
            current_line += word + " "
    if current_line != "│ ":
        card += current_line.ljust(width + 1) + "│\n"
    
    # Add empty line
    card += "│".ljust(width + 2) + "│\n"
    
    # Add tags with word wrapping if there are any
    if tags:
        tag_words = tags.split()
        current_line = "│ "
        for word in tag_words:
            if len(current_line + word) > width - 1:
                card += current_line.ljust(width + 1) + "│\n"
                current_line = "│ " + word + " "
            else:
                current_line += word + " "
        if current_line != "│ ":
            card += current_line.ljust(width + 1) + "│\n"
    
    # Add score if provided
    if score is not None:
        card += "│".ljust(width + 2) + "│\n"
        card += f"│ Score: {score}/10 {' ' * (width - len(str(score)) - 10)} │\n"
    
    # Add reason if provided
    if reason:
        card += "│".ljust(width + 2) + "│\n"
        reason_words = reason.split()
        current_line = "│ "
        for word in reason_words:
            if len(current_line + word) > width - 1:
                card += current_line.ljust(width + 1) + "│\n"
                current_line = "│ " + word + " "
            else:
                current_line += word + " "
        if current_line != "│ ":
            card += current_line.ljust(width + 1) + "│\n"
    
    card += f"└{'─' * width}┘\n"
    
    return card


# Main function to process the markdown file
def main():
    parser = argparse.ArgumentParser(description='Evaluate GitHub repository projects and display the most impressive ones.')
    parser.add_argument('--file', type=str, default='github_repo_analysis.md', 
                        help='Path to the markdown report file (default: github_repo_analysis.md)')
    parser.add_argument('--top', type=int, default=10,
                        help='Number of top projects to display (default: 10)')
    parser.add_argument('--no-evaluate', action='store_true',
                        help='Skip evaluation and just display the projects')
    args = parser.parse_args()
    
    logger.info(f"Loading markdown file: {args.file}")
    markdown_text = load_markdown_file(args.file)
    if not markdown_text:
        logger.error("Failed to load markdown file. Exiting.")
        return

    logger.info("Extracting projects...")
    projects = split_projects(markdown_text)
    logger.info(f"Found {len(projects)} projects.")

    if args.no_evaluate:
        # Just display the projects without evaluation
        print(f"\n--- My GitHub Projects ({len(projects)}) ---\n")
        for project in projects:
            print(format_project_card(project))
    else:
        # Evaluate and display top projects
        logger.info("Evaluating projects...")
        results = []
        for idx, project in enumerate(projects, 1):
            logger.info(f"Evaluating Project {idx}: {project['name']}...")
            evaluation = evaluate_project(project)
            score = extract_score(evaluation)
            reason = evaluation.split('Reason:')[1].strip() if 'Reason:' in evaluation else ''
            results.append((project, score, reason))

        # Sort projects by score in descending order
        sorted_results = sorted(results, key=lambda x: x[1], reverse=True)
        
        # Display top N projects
        top_n = min(args.top, len(sorted_results))
        print(f"\n--- Top {top_n} Most Impressive Projects ---\n")
        
        for i, (project, score, reason) in enumerate(sorted_results[:top_n], 1):
            print(format_project_card(project, score, reason))


if __name__ == "__main__":
    main()
