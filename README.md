# Gitter

A lightweight Git-like version control system implemented in Python. Gitter provides basic version control functionality including commit history, branching, and working directory management.

## Features

- Repository initialization
- File staging and committing
- Commit history viewing
- Status checking
- File diff comparison
- Basic index management
- Command-line interface similar to Git

## Requirements

- Python 3.8 or higher
- pip (Python package installer)

## Installation

UnZip the repository and install using pip:

```bash
unzip the file
cd gitter
pip install -e .
```

## Usage

Gitter provides a command-line interface similar to Git. Here are the main commands:

## Initialize a Repository
```bash
gitter init
```
Creates a new Gitter repository in the current directory.

## Add Files to Staging
```bash
gitter add <file>
```
Stages files for commit. Multiple files can be specified.

## Commit Changes
```bash
gitter commit -m "commit message"
```
Creates a new commit with the staged changes.

## View Status
```bash
gitter status
```
Shows the current status of the working directory and staged changes.

## View Commit History
```bash
gitter log [<commit>]
```
Displays the commit history. Optionally start from a specific commit.

## View Changes
```bash
gitter diff [--cached] [<commit>]
```
Shows changes between commits, working directory, and staged changes.
