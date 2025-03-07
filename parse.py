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
    lines = markdown_text.split('\n')
    
    current_project = None
    project_name = None
    project_year = None
    project_description = None
    project_tags = None
    
    for i, line in enumerate(lines):
        if line.startswith('## '):  # Project name
            # Save previous project if exists
            if current_project:
                projects.append(current_project)
            
            # Start new project
            project_name = line.replace('## ', '').strip()
            current_project = {
                'name': project_name,
                'year': None,
                'description': None,
                'tags': []
            }
        
        elif line.startswith('**') and current_project and not current_project['year']:
            # Year line
            year_match = re.search(r'\*\*(\d{4})\*\*', line)
            if year_match:
                current_project['year'] = year_match.group(1)
        
        elif line and current_project and current_project['year'] and not current_project['description']:
            # Description line (first non-empty line after year)
            current_project['description'] = line.strip()
        
        elif '`' in line and current_project and current_project['description']:
            # Tags line
            tags = re.findall(r'`([^`]+)`', line)
            current_project['tags'] = tags
    
    # Add the last project
    if current_project:
        projects.append(current_project)
    
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
    description = project['description'] or ""
    tags = ' '.join([f"{tag}" for tag in project['tags']])
    
    # Format the card
    card = f"""
┌{'─' * (len(name) + 10)}┐
│ {name} {year.rjust(70 - len(name))} │
├{'─' * (len(name) + 10)}┤
│ {description[:67] + '...' if len(description) > 70 else description.ljust(70)} │
│ {tags[:67] + '...' if len(tags) > 70 else tags.ljust(70)} │
"""
    
    if score is not None:
        card += f"│ Score: {score}/10 {' ' * (60 - len(str(score)))} │\n"
    
    if reason:
        # Format reason to fit in the card
        reason_lines = []
        words = reason.split()
        current_line = "│ "
        for word in words:
            if len(current_line + word) > 69:
                reason_lines.append(current_line.ljust(70) + " │")
                current_line = "│ " + word + " "
            else:
                current_line += word + " "
        if current_line != "│ ":
            reason_lines.append(current_line.ljust(70) + " │")
        
        for line in reason_lines:
            card += line + "\n"
    
    card += f"└{'─' * (len(name) + 10)}┘\n"
    
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
