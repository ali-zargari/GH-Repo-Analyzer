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
            logger.info(f"Found {len(repos)} repositories")
            return repos
        except GithubException as e:
            logger.error(f"Error fetching repositories: {e}")
            return []

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

        # Create a simple summary
        summary = f"This repository is named '{repo_data['name']}' and was created on {repo_data['created_at'].strftime('%Y-%m-%d')}. "
        summary += f"It primarily uses {languages}. "

        if frameworks_list:
            summary += f"The project utilizes {frameworks_str}. "

        # Add code analysis information
        if total_files > 0:
            summary += f"The codebase consists of {total_files} files with approximately {total_lines} lines of code. "
            if main_file_types:
                summary += f"The main file types are {', '.join(main_file_types)}. "

        if readme_snippet != "No README available":
            summary += f"README excerpt: {readme_snippet}"

        return summary

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
                readme_excerpt = readme[:1000]

            # Get code analysis information
            code_analysis = repo_data.get('code_analysis', {})
            total_files = code_analysis.get('total_files', 0)
            total_lines = code_analysis.get('total_lines', 0)
            main_file_types = code_analysis.get('main_file_types', [])

            # Get code samples for analysis
            code_samples = code_analysis.get('code_samples', {})
            code_samples_text = ""
            for ext, samples in code_samples.items():
                if samples:
                    # Take just the first sample for each file type to keep the prompt size reasonable
                    sample = samples[0]
                    code_samples_text += f"\nSample {ext} code from {sample['path']}:\n```\n{sample['sample']}\n```\n"

            # Prepare file structure overview
            structure_overview = code_analysis.get('structure_overview', [])
            structure_text = "\n".join(structure_overview[:30])  # Limit to 30 items to keep prompt size reasonable

            prompt = f"""
You are a technical documentation assistant. Given the following repository details, generate a concise and informative summary:

Repository Name: {repo_data['name']}
Created On: {repo_data['created_at'].strftime('%Y-%m-%d')}
Languages: {languages}
Frameworks and Libraries:
{frameworks_str}

Code Analysis:
- Total Files: {total_files}
- Total Lines of Code: {total_lines}
- Main File Types: {', '.join(main_file_types) if main_file_types else "None detected"}

File Structure Overview:
{structure_text}

{code_samples_text}

README Excerpt:
{readme_excerpt}

Provide a clear, well-structured summary highlighting:
1. The repository's purpose and main functionality
2. Key technologies and programming languages used
3. Code organization and architecture
4. Notable features or patterns observed in the code
5. Any other relevant insights from the code analysis
"""
            try:
                response = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system",
                         "content": "You are a helpful technical documentation writer with expertise in code analysis."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.7,
                    max_tokens=500
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

    def generate_markdown_report(self, repo_analyses: List[Dict[str, Any]],
                                 output_file: str = "github_repo_analysis.md"):
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("# My GitHub Projects\n\n")
            
            # Sort repositories by creation date (newest first)
            sorted_repos = sorted(repo_analyses, key=lambda r: r['created_at'], reverse=True)
            
            for repo in sorted_repos:
                # Get creation year
                year = repo['created_at'].strftime('%Y')
                
                # Get languages as tags
                languages = repo['frameworks'].get('languages', [])
                language_tags = ' '.join([f"`{lang}`" for lang in languages[:3]])  # Limit to top 3 languages
                
                # Get frameworks as additional tags
                framework_tags = []
                for fw, libs in repo['frameworks'].items():
                    if fw != 'languages' and libs:
                        # Take up to 2 libraries per framework
                        for lib in libs[:2]:
                            framework_tags.append(f"`{lib}`")
                
                # Combine all tags, limit to 5 total
                all_tags = ' '.join(framework_tags[:max(0, 5 - len(languages))])
                
                # Generate a short description (first 150 chars of summary)
                summary = repo['summary']
                short_description = summary.split('.')[0] + '.' if summary else ""
                if len(short_description) > 150:
                    short_description = short_description[:147] + "..."
                
                # Write project card
                f.write(f"## {repo['name']}\n\n")
                f.write(f"**{year}**\n\n")
                f.write(f"{short_description}\n\n")
                f.write(f"{language_tags} {all_tags}\n\n")
                f.write("---\n\n")
            
            logger.info(f"Report generated: {output_file}")

    def analyze_repositories(self, limit: int = None):
        """
        Analyze GitHub repositories.

        Args:
            limit: Optional maximum number of repositories to analyze. If None, analyze all repositories.
        """
        try:
            repos = self.get_all_repositories()
            repos.sort(key=lambda r: r.created_at)

            # Limit the number of repositories if specified
            if limit is not None and limit > 0:
                logger.info(f"Limiting analysis to {limit} repositories")
                repos = repos[:limit]

            repo_analyses = []
            for repo in repos:
                try:
                    logger.info(f"Analyzing repository: {repo.name}")

                    # Basic repository data
                    repo_data = {
                        'name': repo.name,
                        'created_at': repo.created_at,
                        'frameworks': self.detect_frameworks(repo),
                        'readme': self.get_readme_content(repo)
                    }

                    # Add code analysis
                    logger.info(f"Analyzing code content for {repo.name}")
                    repo_data['code_analysis'] = self.analyze_code_content(repo)
                    logger.info(
                        f"Found {repo_data['code_analysis']['total_files']} files with {repo_data['code_analysis']['total_lines']} lines of code in {repo.name}")

                    # Generate summary
                    repo_data['summary'] = self.summarize_with_openai(repo_data)
                    repo_analyses.append(repo_data)
                except Exception as e:
                    logger.error(f"Error analyzing repository {repo.name}: {e}")

            if repo_analyses:
                self.generate_markdown_report(repo_analyses)
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
    args = parser.parse_args()

    if GITHUB_TOKEN:
        analyzer = GitHubRepoAnalyzer(GITHUB_TOKEN)

        # If --no-openai flag is set, monkey patch the summarize_with_openai method
        if args.no_openai:
            logger.info("Using fallback summaries only (OpenAI API disabled)")
            analyzer.summarize_with_openai = analyzer.generate_fallback_summary

        analyzer.analyze_repositories(limit=args.limit)
    else:
        logger.error("GitHub token not found. Please set the GITHUB_TOKEN environment variable.")


if __name__ == "__main__":
    main()
