# GitHub Repository Analyzer

A powerful tool that analyzes your GitHub repositories and generates comprehensive reports about their structure, technologies, and codebase.

## Overview

GitHub Repository Analyzer is a Python-based tool that connects to your GitHub account, analyzes your repositories, and generates detailed markdown reports. It provides insights into:

- Languages used in each repository
- Frameworks and libraries detected
- Code structure and organization
- File types and line counts
- AI-generated summaries of repository purpose and functionality

## Features

- **Repository Discovery**: Automatically fetches all repositories from your GitHub account
- **Language Detection**: Identifies programming languages used in each repository
- **Framework Detection**: Recognizes common frameworks and libraries (Node.js, Python, Ruby, Java, etc.)
- **Code Analysis**: Counts files, lines of code, and analyzes file types
- **AI-Powered Summaries**: Uses OpenAI to generate intelligent summaries of repository purpose and structure
- **Markdown Reports**: Creates well-formatted markdown reports with all analysis results

## Requirements

- Python 3.6+
- GitHub Personal Access Token
- OpenAI API Key (optional, for AI-powered summaries)

## Installation

1. Clone this repository:
   ```
   git clone https://github.com/yourusername/github-repo-analyzer.git
   cd github-repo-analyzer
   ```

2. Create a virtual environment and install dependencies:
   ```
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Create a `.env.local` file with your credentials:
   ```
   GITHUB_TOKEN=your_github_personal_access_token
   OPENAI_API_KEY=your_openai_api_key
   ```

## Usage

Run the analyzer with default settings:

```
python gh-repo-analyzer.py
```

### Command Line Options

- `--limit N`: Analyze only N repositories (if not specified, analyzes all repositories)
- `--no-openai`: Skip OpenAI API calls and use fallback summaries only
- `--interactive`: Enable interactive mode to skip repositories during analysis
- `--repo-file FILE`: Path to a text file containing repository names to analyze (default: repos.txt)

Examples:

```
# Analyze all repositories (default behavior)
python gh-repo-analyzer.py

# Analyze 10 repositories
python gh-repo-analyzer.py --limit 10

# Analyze without using OpenAI
python gh-repo-analyzer.py --no-openai

# Enable interactive mode to skip repositories
python gh-repo-analyzer.py --interactive

# Analyze only specific repositories listed in a file
python gh-repo-analyzer.py --repo-file my_repos.txt
```

## Analyzing Specific Repositories

You can create a text file (default name: `repos.txt`) containing the names of specific repositories you want to analyze:

```
# This is a comment (lines starting with # are ignored)
repo-name-1
repo-name-2
repo-name-3
```

For repositories in GitHub Organizations or other accounts, use the full repository name with the owner:

```
# Repositories in your account
your-repo-1
your-repo-2

# Repositories in organizations or other accounts
organization-name/repo-name
another-org/their-repo
username/personal-repo
```

When you run the analyzer with the `--repo-file` option, it will only process the repositories listed in this file:

```
python gh-repo-analyzer.py --repo-file my_repos.txt
```

If the file is empty or doesn't exist, the analyzer will process all repositories in your account as usual.

This feature is useful when:
- You only want to analyze a few specific repositories
- You want to analyze repositories from different organizations
- You want to re-analyze repositories that had errors
- You want to create different groups of repositories for separate analyses

## Interactive Mode

When running with the `--interactive` flag, the analyzer will continuously process repositories while allowing you to skip the current one at any time by pressing 'S'. This is useful when:

- You want to skip large repositories that take too long to analyze
- You want to skip repositories that are causing errors
- You only want to analyze specific repositories of interest

The interactive mode runs a background thread that constantly listens for keyboard input, so there are no pauses or prompts - the analysis runs at full speed until you decide to skip a repository.

When you press 'S':
- The current repository's analysis will be skipped as soon as possible
- You'll see a confirmation message that the skip was requested
- The analyzer will move on to the next repository

Example usage:
```
python gh-repo-analyzer.py --interactive
```

During execution, you'll see progress messages for each repository, and you can press 'S' at any time to skip the current one.

## Output

The tool generates a markdown report file named `github_repo_analysis.md` containing:

- Repository names and creation dates
- Languages used in each repository
- Frameworks and libraries detected
- Code statistics (files, lines, file types)
- File structure overview
- AI-generated or fallback summary of each repository

## How It Works

1. Authenticates with GitHub using your personal access token
2. Retrieves your repositories (with optional limit)
3. For each repository:
   - Detects languages and frameworks
   - Analyzes code structure and content
   - Extracts README content
   - Generates a summary using OpenAI or fallback method
4. Compiles all information into a markdown report

## Dependencies

- `github`: GitHub API client for Python
- `openai`: OpenAI API client
- `python-dotenv`: For loading environment variables
- Other standard Python libraries

## License

[MIT License](LICENSE)

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.