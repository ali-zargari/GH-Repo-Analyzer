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

- `--limit N`: Analyze only the N most recent repositories (default: 5)
- `--no-openai`: Skip OpenAI API calls and use fallback summaries only

Examples:

```
# Analyze all repositories
python gh-repo-analyzer.py --limit 0

# Analyze 10 repositories
python gh-repo-analyzer.py --limit 10

# Analyze without using OpenAI
python gh-repo-analyzer.py --no-openai
```

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