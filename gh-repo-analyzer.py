#!/usr/bin/env python3
"""
GitHub Repository Analyzer
"""

import os
import re
import base64
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
import sys
import time
import platform
import threading

import json
from dotenv import load_dotenv
from github import Github, Repository, GithubException
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
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Initialize OpenAI client (new SDK 1.0+)
client = OpenAI(api_key=OPENAI_API_KEY)

# Determine if we're on Windows
IS_WINDOWS = platform.system() == 'Windows'

# Import platform-specific modules for keyboard input
if IS_WINDOWS:
    import msvcrt
else:
    import select
    import termios
    import tty

# Global variable to track skip request
skip_current_repo = False
skip_lock = threading.Lock()

def key_listener_thread():
    """Background thread that listens for 'S' key press to skip current repository."""
    global skip_current_repo
    
    try:
        while True:
            key = None
            
            # Platform-specific key detection
            if IS_WINDOWS:
                if msvcrt.kbhit():
                    key = msvcrt.getch().decode('utf-8').lower()
            else:
                # Unix implementation
                old_settings = None
                try:
                    fd = sys.stdin.fileno()
                    old_settings = termios.tcgetattr(fd)
                    tty.setraw(fd)
                    
                    if select.select([sys.stdin], [], [], 0.1)[0]:
                        key = sys.stdin.read(1).lower()
                finally:
                    # Restore terminal settings
                    if old_settings:
                        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            
            # Check if 'S' was pressed
            if key == 's':
                with skip_lock:
                    skip_current_repo = True
                    print("\nSkip requested. Will skip current repository when possible...")
            
            time.sleep(0.1)  # Small sleep to prevent CPU hogging
    except Exception as e:
        print(f"\nKey listener thread error: {e}")
        # Continue without key listening if there's an error

FRAMEWORK_PATTERNS = {
    "package.json": {"type": "json", "dependencies": ["dependencies", "devDependencies"],
                     "framework": "JavaScript/Node.js"},
    "requirements.txt": {"type": "text", "framework": "Python"},
    "pyproject.toml": {"type": "toml", "framework": "Python"},
    "Gemfile": {"type": "text", "framework": "Ruby"},
    "pom.xml": {"type": "xml", "framework": "Java/Maven"},
    "build.gradle": {"type": "text", "framework": "Java/Gradle"},
    "composer.json": {"type": "json", "dependencies": ["require", "require-dev"], "framework": "PHP"},
    "go.mod": {"type": "text", "framework": "Go"},
    "cargo.toml": {"type": "toml", "framework": "Rust"},
    ".csproj": {"type": "xml", "framework": "C#/.NET"},
    "pubspec.yaml": {"type": "yaml", "framework": "Dart/Flutter"}
}


class GitHubRepoAnalyzer:
    def __init__(self, github_token: str):
        self.github = Github(github_token)
        self.user = self.github.get_user()
        logger.info(f"Authenticated as GitHub user: {self.user.login}")

    def get_all_repositories(self) -> List[Repository.Repository]:
        try:
            repos = list(self.user.get_repos())
            logger.info(f"Found {len(repos)} repositories in user account")
            return repos
        except GithubException as e:
            logger.error(f"Error fetching repositories: {e}")
            return []

    def get_organization_repositories(self, org_name: str) -> List[Repository.Repository]:
        """Get repositories from a specific organization."""
        try:
            org = self.github.get_organization(org_name)
            repos = list(org.get_repos())
            logger.info(f"Found {len(repos)} repositories in organization {org_name}")
            return repos
        except GithubException as e:
            logger.error(f"Error fetching repositories from organization {org_name}: {e}")
            return []

    def get_repository_by_full_name(self, full_name: str) -> Optional[Repository.Repository]:
        """Get a specific repository by its full name (owner/repo)."""
        try:
            repo = self.github.get_repo(full_name)
            logger.info(f"Found repository: {full_name}")
            return repo
        except GithubException as e:
            logger.error(f"Error fetching repository {full_name}: {e}")
            return None

    def get_repo_languages(self, repo: Repository.Repository) -> Dict[str, int]:
        try:
            return repo.get_languages()
        except GithubException as e:
            logger.error(f"Error fetching languages for {repo.name}: {e}")
            return {}

    def get_file_content(self, repo: Repository.Repository, file_path: str) -> Optional[str]:
        try:
            content = repo.get_contents(file_path)
            if isinstance(content, list):
                return None
            return base64.b64decode(content.content).decode('utf-8')
        except GithubException as e:
            if e.status != 404:
                logger.error(f"Error fetching {file_path} from {repo.name}: {e}")
            return None
        except UnicodeDecodeError:
            logger.warning(f"Could not decode {file_path} as UTF-8 in {repo.name}")
            return None

    def get_readme_content(self, repo: Repository.Repository) -> Optional[str]:
        for readme_name in ["README.md", "README.MD", "Readme.md", "readme.md", "README", "readme"]:
            content = self.get_file_content(repo, readme_name)
            if content:
                return content
        return None

    def detect_frameworks(self, repo: Repository.Repository) -> Dict[str, List[str]]:
        frameworks = {}
        languages = self.get_repo_languages(repo)
        frameworks["languages"] = list(languages.keys())

        for file_pattern, pattern_info in FRAMEWORK_PATTERNS.items():
            content = self.get_file_content(repo, file_pattern)
            if content:
                framework_type = pattern_info["framework"]
                frameworks.setdefault(framework_type, [])
                if pattern_info["type"] == "json" and "dependencies" in pattern_info:
                    try:
                        data = json.loads(content)
                        for dep_key in pattern_info["dependencies"]:
                            frameworks[framework_type].extend(data.get(dep_key, {}).keys())
                    except json.JSONDecodeError:
                        logger.warning(f"Could not parse {file_pattern} as JSON in {repo.name}")
                elif pattern_info["type"] == "text" and file_pattern == "requirements.txt":
                    packages = [re.split(r'[=<>~]', line.strip())[0] for line in content.splitlines() if
                                line and not line.startswith('#')]
                    frameworks[framework_type].extend(packages)
        return frameworks

    def generate_fallback_summary(self, repo_data: Dict[str, Any]) -> str:
        """Generate a simple summary when OpenAI API is unavailable."""
        languages = ', '.join(repo_data.get('frameworks', {}).get('languages', [])) or "No languages detected"

        # Extract frameworks
        frameworks = repo_data.get('frameworks', {})
        frameworks_list = []
        for framework, libraries in frameworks.items():
            if framework != 'languages' and libraries:
                frameworks_list.append(f"{framework}: {', '.join(libraries)}")
        frameworks_str = ', '.join(frameworks_list) or "No specific frameworks detected"

        # Get a snippet of the README if available
        readme = repo_data.get('readme')
        readme_snippet = "No README available"
        if readme:
            # Get first paragraph or first 100 characters
            lines = readme.split('\n')
            non_empty_lines = [line for line in lines if line.strip()]
            if non_empty_lines:
                readme_snippet = non_empty_lines[0][:100] + "..." if len(non_empty_lines[0]) > 100 else non_empty_lines[
                    0]

        # Get code analysis information
        code_analysis = repo_data.get('code_analysis', {})
        total_files = code_analysis.get('total_files', 0)
        total_lines = code_analysis.get('total_lines', 0)
        main_file_types = code_analysis.get('main_file_types', [])

        # Create a simple JSON summary
        fallback_json = {
            "name": repo_data['name'],
            "year": repo_data['created_at'].strftime('%Y'),
            "purpose": f"A project using {languages}. {readme_snippet}",
            "technologies": languages.split(', '),
            "features": ["Unknown"],
            "architecture": f"Contains {total_files} files with approximately {total_lines} lines of code",
            "complexity": "Unknown"
        }
        
        return json.dumps(fallback_json, indent=2)

    def summarize_with_openai(self, repo_data: Dict[str, Any]) -> str:
        try:
            # Check if frameworks exists and is not None
            frameworks = repo_data.get('frameworks', {})
            if frameworks is None:
                frameworks = {}

            languages = ', '.join(frameworks.get('languages', [])) or "No languages detected"
            frameworks_list = []
            for framework, libraries in frameworks.items():
                if framework != 'languages' and libraries:
                    frameworks_list.append(f"{framework}: {', '.join(libraries)}")
            frameworks_str = '\n'.join(frameworks_list) or "No specific frameworks detected"

            # Fix for the NoneType error - ensure readme is a string before slicing
            readme = repo_data.get('readme')
            if readme is None:
                readme_excerpt = "No README available"
            else:
                readme_excerpt = readme[:1500]  # Increased from 1000 to get more context

            # Get code analysis information
            code_analysis = repo_data.get('code_analysis', {})
            total_files = code_analysis.get('total_files', 0)
            total_lines = code_analysis.get('total_lines', 0)
            main_file_types = code_analysis.get('main_file_types', [])
            
            # Get file types for better analysis
            file_types = code_analysis.get('file_types', {})
            file_types_str = "\n".join([f"{ext}: {count} files" for ext, count in file_types.items()]) if file_types else "No file types detected"

            # Get code samples for analysis - include more samples for better understanding
            code_samples = code_analysis.get('code_samples', {})
            code_samples_text = ""
            for ext, samples in code_samples.items():
                if samples:
                    # Take up to 3 samples per extension for better code understanding
                    for i, sample in enumerate(samples[:3]):
                        code_samples_text += f"\nSample {i+1} of {ext} code from {sample['path']}:\n```\n{sample['sample']}\n```\n"

            # Prepare file structure overview - include more files for better context
            structure_overview = code_analysis.get('structure_overview', [])
            structure_text = "\n".join(structure_overview[:50])  # Increased from 30 to 50 items

            prompt = f"""
You are a technical expert analyzing a software project. Based on the following information, make informed assumptions about the project's purpose, technologies, and functionality. Focus on analyzing the code, file names, and structure rather than just descriptions.

Project Name: {repo_data['name']}
Created On: {repo_data['created_at'].strftime('%Y-%m-%d')}
Languages: {languages}
Frameworks and Libraries:
{frameworks_str}

Code Analysis:
- Total Files: {total_files}
- Total Lines of Code: {total_lines}
- Main File Types: {', '.join(main_file_types) if main_file_types else "None detected"}

Detailed File Types:
{file_types_str}

File Structure Overview:
{structure_text}

{code_samples_text}

README Excerpt:
{readme_excerpt}

Based on the code samples, file names, and project structure, provide a detailed analysis of this project. Make intelligent assumptions about what the project does, how it works, and its purpose. Don't just rely on the README or project name.

Respond with a JSON object in the following format:
{{
  "name": "{repo_data['name']}",
  "year": {repo_data['created_at'].strftime('%Y')},
  "purpose": "A detailed description of what this project does and its main purpose. Avoid using the word 'repository'.",
  "technologies": ["List", "of", "key", "technologies", "used"],
  "features": ["List", "of", "main", "features", "or", "capabilities"],
  "architecture": "Brief description of the project's architecture or structure",
  "complexity": "Assessment of the project's technical complexity (Low, Medium, High)"
}}

Ensure your response is valid JSON. Make your purpose description detailed and specific, focusing on what the project actually does rather than generic descriptions.
"""
            try:
                response = client.chat.completions.create(
                    model="gpt-4-turbo",  # Using GPT-4 for better code analysis
                    messages=[
                        {"role": "system",
                         "content": "You are a technical expert with deep knowledge of software development, programming languages, and system architecture. Your task is to analyze project information and provide detailed, technically accurate assessments based on code analysis rather than descriptions."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,  # Lower temperature for more focused, precise output
                    max_tokens=1000,   # Increased token limit for more detailed responses
                    response_format={"type": "json_object"}  # Ensure JSON response
                )

                # Check if response has the expected structure
                if response is None:
                    logger.warning(f"OpenAI response is None for {repo_data['name']}, using fallback summary")
                    return self.generate_fallback_summary(repo_data)

                if not hasattr(response, 'choices') or not response.choices:
                    logger.warning(f"Invalid OpenAI response structure for {repo_data['name']}, using fallback summary")
                    return self.generate_fallback_summary(repo_data)

                return response.choices[0].message.content.strip()
            except Exception as api_error:
                logger.warning(f"OpenAI API error for {repo_data['name']}: {api_error}, using fallback summary")
                return self.generate_fallback_summary(repo_data)

        except Exception as e:
            logger.error(f"Error generating summary with OpenAI for {repo_data['name']}: {e}")
            return self.generate_fallback_summary(repo_data)

    def generate_json_report(self, repo_analyses: List[Dict[str, Any]],
                             output_file: str = "github_repo_analysis.json"):
        """Generate a JSON report of repository analyses."""
        # Sort repositories by creation date (newest first)
        sorted_repos = sorted(repo_analyses, key=lambda r: r['created_at'], reverse=True)
        
        # Prepare JSON data
        json_data = []
        for repo in sorted_repos:
            try:
                # Parse the JSON summary
                summary_json = json.loads(repo['summary'])
                json_data.append(summary_json)
            except json.JSONDecodeError:
                # If the summary is not valid JSON, create a basic entry
                json_data.append({
                    "name": repo['name'],
                    "year": repo['created_at'].strftime('%Y'),
                    "purpose": "Could not parse project information",
                    "technologies": repo['frameworks'].get('languages', []),
                    "features": [],
                    "architecture": "Unknown",
                    "complexity": "Unknown"
                })
        
        # Write the JSON file
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, indent=2)
        
        logger.info(f"JSON report generated: {output_file}")

    def analyze_repositories(self, limit: int = None, interactive: bool = False, specific_repos: List[str] = None):
        """
        Analyze GitHub repositories.

        Args:
            limit: Optional maximum number of repositories to analyze. If None, analyze all repositories.
            interactive: If True, allows skipping repositories by pressing 'S' at any time.
            specific_repos: Optional list of repository names to analyze. If provided, only these repositories will be analyzed.
                           Can include full repository names (owner/repo) for repositories in organizations.
        """
        global skip_current_repo
        
        try:
            # Get repositories based on specific_repos parameter
            if specific_repos:
                logger.info(f"Preparing to analyze {len(specific_repos)} specific repositories")
                repos = []
                
                for repo_name in specific_repos:
                    # Check if it's a full repository name (contains a slash)
                    if '/' in repo_name:
                        # It's a full repository name (owner/repo)
                        repo = self.get_repository_by_full_name(repo_name)
                        if repo:
                            repos.append(repo)
                    else:
                        # It's a repository name in the user's account
                        # We'll find it later when we get all user repos
                        pass
                
                # Get user repositories to find the ones specified by name only
                user_repos = self.get_all_repositories()
                
                # Add repositories from user account that match the names in specific_repos
                for repo in user_repos:
                    if repo.name in specific_repos and not any(r.name == repo.name for r in repos):
                        repos.append(repo)
                        logger.info(f"Found repository in user account: {repo.name}")
                
                # Check if we found all the repositories
                found_repo_names = set(repo.name for repo in repos) | set(repo.full_name for repo in repos)
                missing_repos = set(specific_repos) - found_repo_names
                
                if missing_repos:
                    logger.warning(f"Could not find {len(missing_repos)} repositories: {', '.join(missing_repos)}")
                    print(f"Warning: Could not find these repositories: {', '.join(missing_repos)}")
                
                logger.info(f"Analyzing {len(repos)} repositories from the specified list")
                print(f"Analyzing {len(repos)} repositories from the specified list")
            else:
                # Get all repositories from the user's account
                repos = self.get_all_repositories()
            
            # Sort repositories by creation date
            repos.sort(key=lambda r: r.created_at)

            # Limit the number of repositories if specified
            if limit is not None and limit > 0 and len(repos) > limit:
                logger.info(f"Limiting analysis to {limit} repositories")
                repos = repos[:limit]

            repo_analyses = []
            
            # Start key listener thread if in interactive mode
            listener_thread = None
            if interactive:
                logger.info("Interactive mode enabled. Press 'S' at any time to skip the current repository.")
                print("Interactive mode: Press 'S' at any time to skip the current repository being processed.")
                
                try:
                    listener_thread = threading.Thread(target=key_listener_thread, daemon=True)
                    listener_thread.start()
                except Exception as e:
                    logger.warning(f"Could not start key listener thread: {e}. Interactive mode may not work properly.")
            
            for repo in repos:
                try:
                    # Reset skip flag at the start of each repository
                    with skip_lock:
                        skip_current_repo = False
                    
                    logger.info(f"Analyzing repository: {repo.name}")
                    print(f"Analyzing repository: {repo.name}")
                    
                    # Basic repository data
                    repo_data = {
                        'name': repo.name,
                        'created_at': repo.created_at,
                        'frameworks': self.detect_frameworks(repo),
                        'readme': self.get_readme_content(repo)
                    }
                    
                    # Check if skip was requested
                    if interactive and skip_current_repo:
                        logger.info(f"Skipping repository: {repo.name}")
                        print(f"Skipping repository: {repo.name}")
                        continue

                    # Add code analysis
                    logger.info(f"Analyzing code content for {repo.name}")
                    repo_data['code_analysis'] = self.analyze_code_content(repo)
                    
                    # Check if skip was requested
                    if interactive and skip_current_repo:
                        logger.info(f"Skipping repository: {repo.name}")
                        print(f"Skipping repository: {repo.name}")
                        continue
                    
                    logger.info(
                        f"Found {repo_data['code_analysis']['total_files']} files with {repo_data['code_analysis']['total_lines']} lines of code in {repo.name}")

                    # Generate summary
                    logger.info(f"Generating summary for {repo.name}")
                    repo_data['summary'] = self.summarize_with_openai(repo_data)
                    
                    # Check if skip was requested
                    if interactive and skip_current_repo:
                        logger.info(f"Skipping repository: {repo.name}")
                        print(f"Skipping repository: {repo.name}")
                        continue
                    
                    repo_analyses.append(repo_data)
                    logger.info(f"Completed analysis of {repo.name}")
                    print(f"Completed analysis of {repo.name}")
                    
                except Exception as e:
                    logger.error(f"Error analyzing repository {repo.name}: {e}")

            if repo_analyses:
                self.generate_json_report(repo_analyses)
            else:
                logger.warning("No repositories were successfully analyzed.")
        except Exception as e:
            logger.error(f"Error in analyze_repositories: {e}")

    def analyze_code_content(self, repo: Repository.Repository) -> Dict[str, Any]:
        """
        Analyze the actual code content in the repository.

        Args:
            repo: The GitHub repository to analyze

        Returns:
            A dictionary containing code analysis results
        """
        code_analysis = {
            'file_types': {},
            'code_samples': {},
            'total_files': 0,
            'total_lines': 0,
            'main_file_types': [],
            'structure_overview': []
        }

        try:
            # Get the root contents
            contents = repo.get_contents("")

            # Skip certain directories and files
            skip_dirs = ['.git', 'node_modules', 'venv', '.venv', '__pycache__', 'dist', 'build']
            skip_extensions = ['.pyc', '.pyo', '.min.js', '.min.css', '.map', '.log', '.md']

            # Track file extensions and their counts
            file_extensions = {}

            # Process files recursively
            while contents:
                file_content = contents.pop(0)

                # Skip directories we don't want to analyze
                if file_content.path.split('/')[0] in skip_dirs:
                    continue

                if file_content.type == "dir":
                    # Add directory to structure overview
                    code_analysis['structure_overview'].append(f"Directory: {file_content.path}")
                    # Get contents of this directory and add them to our list
                    contents.extend(repo.get_contents(file_content.path))
                else:
                    # It's a file
                    code_analysis['total_files'] += 1

                    # Get file extension
                    _, ext = os.path.splitext(file_content.path)
                    if ext:
                        # Skip certain file extensions
                        if ext in skip_extensions:
                            continue

                        # Count file extensions
                        file_extensions[ext] = file_extensions.get(ext, 0) + 1

                    # Add file to structure overview
                    code_analysis['structure_overview'].append(f"File: {file_content.path}")

                    # Try to get content for code analysis (limit to certain file types and sizes)
                    if ext in ['.py', '.js', '.java', '.c', '.cpp', '.h', '.cs', '.php', '.rb', '.go', '.ts', '.html',
                               '.css', '.sql']:
                        try:
                            # Only process files smaller than 100KB to avoid timeouts
                            if file_content.size < 100000:
                                file_text = self.get_file_content(repo, file_content.path)
                                if file_text:
                                    # Count lines
                                    lines = file_text.count('\n') + 1
                                    code_analysis['total_lines'] += lines

                                    # Store a sample of the code (first 20 lines)
                                    sample_lines = file_text.split('\n')[:20]
                                    if len(sample_lines) > 0:
                                        # Only store up to 5 samples per extension to avoid excessive data
                                        if ext not in code_analysis['code_samples'] or len(
                                                code_analysis['code_samples'].get(ext, [])) < 5:
                                            if ext not in code_analysis['code_samples']:
                                                code_analysis['code_samples'][ext] = []
                                            code_analysis['code_samples'][ext].append({
                                                'path': file_content.path,
                                                'sample': '\n'.join(sample_lines),
                                                'lines': lines
                                            })
                        except Exception as e:
                            logger.warning(f"Error analyzing file {file_content.path}: {e}")

            # Store file type statistics
            code_analysis['file_types'] = file_extensions

            # Determine main file types (top 3 by count)
            main_types = sorted(file_extensions.items(), key=lambda x: x[1], reverse=True)[:3]
            code_analysis['main_file_types'] = [f"{ext} ({count} files)" for ext, count in main_types]

            # Limit structure overview to avoid excessive data
            if len(code_analysis['structure_overview']) > 50:
                code_analysis['structure_overview'] = code_analysis['structure_overview'][:50] + [
                    "... (more files/directories)"]

            return code_analysis

        except Exception as e:
            logger.error(f"Error analyzing code content for {repo.name}: {e}")
            return code_analysis


def main():
    parser = argparse.ArgumentParser(description='Analyze GitHub repositories and generate a summary report.')
    parser.add_argument('--limit', type=int, default=None, help='Maximum number of repositories to analyze (default: all)')
    parser.add_argument('--no-openai', action='store_true',
                        help='Skip OpenAI API calls and use fallback summaries only')
    parser.add_argument('--interactive', action='store_true',
                        help='Enable interactive mode to skip repositories during analysis')
    parser.add_argument('--repo-file', type=str, default='repos.txt',
                        help='Path to a text file containing repository names to analyze (one per line)')
    args = parser.parse_args()

    if GITHUB_TOKEN:
        analyzer = GitHubRepoAnalyzer(GITHUB_TOKEN)

        # If --no-openai flag is set, monkey patch the summarize_with_openai method
        if args.no_openai:
            logger.info("Using fallback summaries only (OpenAI API disabled)")
            analyzer.summarize_with_openai = analyzer.generate_fallback_summary

        # Check if repo file exists and has content
        specific_repos = []
        if args.repo_file and os.path.exists(args.repo_file):
            try:
                with open(args.repo_file, 'r') as f:
                    lines = f.readlines()
                    specific_repos = [line.strip() for line in lines 
                                     if line.strip() and not line.strip().startswith('#')]
                if specific_repos:
                    logger.info(f"Found {len(specific_repos)} repositories in {args.repo_file}")
                    print(f"Found {len(specific_repos)} repositories in {args.repo_file}")
            except Exception as e:
                logger.error(f"Error reading repo file {args.repo_file}: {e}")
                print(f"Error reading repo file {args.repo_file}: {e}")

        analyzer.analyze_repositories(limit=args.limit, interactive=args.interactive, specific_repos=specific_repos)
    else:
        logger.error("GitHub token not found. Please set the GITHUB_TOKEN environment variable.")


if __name__ == "__main__":
    main()
