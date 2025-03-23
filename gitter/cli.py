import argparse
import os
import subprocess
import sys
import textwrap
from typing import Optional, List, Any
from dataclasses import dataclass

from gitter import base, data
from gitter.base import GitCommand
from gitter.data import GitDataManager


git = GitCommand()
git_data = GitDataManager()

@dataclass
class CommandResult:
    """Represents the result of a command execution"""
    success: bool
    message: Optional[str] = None
    error: Optional[str] = None

class RegisterCommand:
    """Base class for all git commands"""
    def add_parser(self, subparsers):
        """Add command parser to subparsers"""
        raise NotImplementedError

    def execute(self, args):
        """Execute the command"""
        raise NotImplementedError

class InitCommand(RegisterCommand):
    def add_parser(self, subparsers):
        parser = subparsers.add_parser(
            'init',
            # help='Create an empty Gitter repository',
            description=textwrap.dedent("""
                Create an empty Gitter repository in the current directory.
                
                This command creates an empty Gitter repository - basically a .ugit
                directory with subdirectories for objects, refs/heads, refs/tags,
                and template files.
            """).strip(),
            formatter_class=argparse.RawDescriptionHelpFormatter,
            usage='gitter init'
        )
        parser.set_defaults(func=self.execute)
        return parser

    def execute(self, args):
        git.init()
        return CommandResult(
            success=True,
            message=f'Initialized empty ugit repository in {os.getcwd()}/{git_data.GIT_DIR}'
        )

class CommitCommand(RegisterCommand):
    def add_parser(self, subparsers):
        parser = subparsers.add_parser(
            'commit',
            description=textwrap.dedent("""
                Record changes to the repository.
                
                Creates a new commit containing the current contents of the index and
                the given log message. The new commit is a direct child of HEAD.
                
                The -m option is required and must contain the commit message.
            """).strip(),
            formatter_class=argparse.RawDescriptionHelpFormatter,
            usage='gitter commit -m <message>'
        )
        parser.add_argument('-m', '--message', required=True, help='The commit message')
        parser.set_defaults(func=self.execute)
        return parser

    def execute(self, args):
        commit_hash = git.commit(args.message)
        return CommandResult(success=True, message=commit_hash)

class LogCommand(RegisterCommand):
    def add_parser(self, subparsers):
        parser = subparsers.add_parser(
            'log',
            description=textwrap.dedent("""
                Show commit logs.
                
                Shows the commit logs in chronological order. Each log entry includes
                the commit hash, author, date, and commit message. If a specific commit
                is provided, starts showing logs from that commit.
            """).strip(),
            formatter_class=argparse.RawDescriptionHelpFormatter,
            usage='gitter log [<commit>]'
        )
        parser.add_argument('oid', default='@', type=git.ref_utils.get_oid, nargs='?',
                           help='Commit hash to start showing logs from')
        parser.set_defaults(func=self.execute)
        return parser

    def execute(self, args):
        log_entries = git.log(args.oid)
        
        for oid, commit, refs in log_entries:
            GitPrinter.print_commit(oid, commit, refs)
        
        return CommandResult(success=True)

class DiffCommand(RegisterCommand):
    def add_parser(self, subparsers):
        parser = subparsers.add_parser(
            'diff',
            description=textwrap.dedent("""
                Show changes between commits, commit and working tree, etc.
                
                Show changes between the working tree and the index or a tree,
                changes between the index and a tree, changes between two trees.
                
                --cached  Show changes staged in the index
            """).strip(),
            formatter_class=argparse.RawDescriptionHelpFormatter,
            usage='gitter diff [--cached] [<commit>]'
        )
        parser.add_argument('--cached', action='store_true',
                           help='View changes staged in the index')
        parser.add_argument('commit', nargs='?',
                           help='Commit to compare against')
        parser.set_defaults(func=self.execute)
        return parser

    def execute(self, args):
        result = git.diff(commit=args.commit, cached=args.cached)
        
        # Output the diff
        sys.stdout.flush()
        sys.stdout.buffer.write(result)
        return CommandResult(success=True)

class StatusCommand(RegisterCommand):
    def add_parser(self, subparsers):
        parser = subparsers.add_parser(
            'status',
            description=textwrap.dedent("""
                Show the working tree status.
                
                Displays paths that have differences between the index file and the
                current HEAD commit, paths that have differences between the working
                tree and the index file, and paths in the working tree that are not
                tracked by Gitter.
            """).strip(),
            formatter_class=argparse.RawDescriptionHelpFormatter,
            usage='gitter status'
        )
        parser.set_defaults(func=self.execute)
        return parser

    def execute(self, args):
        git.status()        
        return CommandResult(success=True)

class AddCommand(RegisterCommand):
    def add_parser(self, subparsers):
        parser = subparsers.add_parser(
            'add',
            description=textwrap.dedent("""
                Add file contents to the index.
                
                This command updates the index using the current content found in
                the working tree, to prepare the content staged for the next commit.
                The "index" holds a snapshot of the content of the working tree.
            """).strip(),
            formatter_class=argparse.RawDescriptionHelpFormatter,
            usage='gitter add <file>...'
        )
        parser.add_argument('files', nargs='+',
                           help='Files to add to the index')
        parser.set_defaults(func=self.execute)
        return parser

    def execute(self, args):
        git.add(args.files)
        return CommandResult(success=True)

class GitPrinter:
    """Handles all output formatting"""
    @staticmethod
    def print_commit(oid: str, commit: Any, refs: Optional[List[str]] = None):
        refs_str = f' ({", ".join(refs)})' if refs else ''
        print(f'commit {oid}{refs_str}\n')
        print(textwrap.indent(commit.message, '    '))
        print('')

class GitCLI:
    """Main CLI class that handles command registration and execution"""
    def __init__(self):
        self.parser = argparse.ArgumentParser(
            description=textwrap.dedent("""
                These are common Gitter commands:
                   init       Create an empty Gitter repository
                   add        Add file contents to the index
                   status     Show the working tree status
                   commit     Record changes to the repository
                   log        Show commit logs
            """).strip(),
            formatter_class=argparse.RawDescriptionHelpFormatter,
            usage='gitter <command> [<args>]'
        )
        self.commands = {}
        self.setup_parser()

    def setup_parser(self):
        """Initialize the argument parser with all commands"""

        subparsers = self.parser.add_subparsers(dest='command')
        subparsers.required = True

        # Register all commands
        commands = [
            InitCommand(), CommitCommand(),
            LogCommand(), DiffCommand(), StatusCommand(), AddCommand()
        ]
        
        for command in commands:
            command.add_parser(subparsers)

    def execute(self):
        """Execute the CLI command"""
        try:
            with data.change_git_dir('.'):
                args = self.parser.parse_args()
                return args.func(args)
        except Exception as e:
            return CommandResult(success=False, error=str(e))

def main():
    """Entry point for the CLI application"""
    cli = GitCLI()
    result = cli.execute()
    
    if not result.success:
        print(f"Error: {result.error}", file=sys.stderr)
        sys.exit(1)
    
    if result.message:
        print(result.message)

if __name__ == '__main__':
    main()